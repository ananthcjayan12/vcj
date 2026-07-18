from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

LAB_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = LAB_ROOT / "scripts"
for entry in (LAB_ROOT, SCRIPTS_ROOT):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mav_audio import generate_audio
from mav_models import call_model_json
from mav_schema import read_json, run_dir, write_json
from mav_timing import derive_timing
from motion_canvas.pipeline import (
    _apply_frame_aligned_timing,
    _write_chapter_cues,
    generate as generate_motion_canvas,
    render_video,
    render_profile_fingerprint,
    resolve_render_profile,
    validate_and_assemble,
)

from .schemas import (
    CANDIDATES_SCHEMA,
    NARRATION_SCHEMA,
    SHOT_PLAN_SCHEMA,
    TREATMENT_SCHEMA,
    validate_candidates,
    validate_narration,
    validate_shot_plan,
    validate_treatment,
)
from .source import load_parent_source
from .timeline import build_immutable_shot_timeline, validate_immutable_shot_timeline
from .validation import assert_reel_source_isolation, invalidate

PROMPT_ROOT = LAB_ROOT / "prompts"
PORTRAIT_PROFILE = resolve_render_profile("reel_portrait")


def _render_template(name: str, **values: Any) -> str:
    text = (PROMPT_ROOT / name).read_text(encoding="utf-8")
    for key, value in values.items():
        rendered = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        text = text.replace("{" + key + "}", rendered)
    return text


def _model_json(run_path: Path, task: str, system_name: str, user_name: str, schema: dict[str, Any], **values: Any) -> dict[str, Any]:
    system = (PROMPT_ROOT / system_name).read_text(encoding="utf-8")
    user = _render_template(user_name, **values)
    debug = run_path / "debug"
    debug.mkdir(parents=True, exist_ok=True)
    (debug / f"{task}.prompt.txt").write_text(f"SYSTEM\n{system}\n\nUSER\n{user}\n", encoding="utf-8")
    response = call_model_json(task=task, system=system, user=user, output_schema=schema)
    if not isinstance(response, dict):
        raise RuntimeError(f"{task} returned no JSON object")
    write_json(debug / f"{task}.response.json", response)
    return response


def _source_fingerprint(source: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(source, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def analyze_parent(parent_run_id: str, *, candidate_count: int = 4, minimum_seconds: int = 25, maximum_seconds: int = 50) -> dict[str, Any]:
    parent_path = run_dir(parent_run_id)
    source = load_parent_source(parent_path)
    candidate_count = max(3, min(int(candidate_count), 5))
    user_values = {
        "candidate_count": str(candidate_count), "topic": source["topic"], "audience": source["audience"],
        "duration_guidance": f"{minimum_seconds}–{maximum_seconds} seconds",
        "narration_json": source["narration"], "grounded_facts_json": source["grounded_facts"],
        "paragraph_ids_json": source["paragraph_ids"], "claim_ids_json": source["claim_ids"],
    }
    prompt = _render_template("reel_candidate_analysis.user.txt", **user_values)
    assert_reel_source_isolation(prompt, parent_path)
    payload = _model_json(parent_path, "reel_candidate_analysis", "reel_candidate_analysis.system.txt", "reel_candidate_analysis.user.txt", CANDIDATES_SCHEMA, **user_values)
    payload = validate_candidates(payload, source)
    payload.update({
        "reel_pipeline_version": "native-portrait-v2",
        "parent_run_id": parent_run_id,
        "source_fingerprint": _source_fingerprint(source),
        "duration_range_seconds": [minimum_seconds, maximum_seconds],
    })
    write_json(parent_path / "reel_candidates.json", payload)
    return payload


def create_reel(parent_run_id: str, candidate_id: str, reel_run_id: str) -> dict[str, Any]:
    parent_path = run_dir(parent_run_id)
    source = load_parent_source(parent_path)
    candidates = read_json(parent_path / "reel_candidates.json")
    candidate = next((item for item in candidates.get("candidates") or [] if item.get("id") == candidate_id), None)
    if not candidate:
        raise RuntimeError(f"Unknown Reel candidate: {candidate_id}")
    child_path = run_dir(reel_run_id)
    if child_path.exists() and any(child_path.iterdir()):
        raise FileExistsError(f"Reel run already exists: {reel_run_id}")
    child_path.mkdir(parents=True, exist_ok=True)
    input_payload = {
        "run_id": reel_run_id, "content_format": "reel", "animation_mode": "motion-canvas",
        "reel_pipeline_version": "native-portrait-v2",
        "render_profile": "reel_portrait", "parent_run_id": parent_run_id, "topic": source["topic"],
        "audience": source["audience"], "target_duration_seconds": 38,
        "source_paragraph_ids": list(candidate["source_paragraph_ids"]), "source_claim_ids": list(candidate["source_claim_ids"]),
        "parent_source_fingerprint": _source_fingerprint(source), "selected_candidate_id": candidate_id,
        "facts": source["grounded_facts"],
    }
    write_json(child_path / "input.json", input_payload)
    write_json(child_path / "reel_candidate.json", candidate)
    write_json(child_path / "parent_source.json", source)
    return input_payload


def _load_child(reel_run_id: str) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    child_path = run_dir(reel_run_id)
    input_payload = read_json(child_path / "input.json")
    if input_payload.get("content_format") != "reel" or input_payload.get("reel_pipeline_version") != "native-portrait-v2":
        raise RuntimeError(f"{reel_run_id} is not a native Reel run")
    source = load_parent_source(run_dir(str(input_payload["parent_run_id"])))
    if _source_fingerprint(source) != input_payload.get("parent_source_fingerprint"):
        write_json(child_path / "source_status.json", {"status": "stale", "reason": "Parent narration or grounded facts changed"})
        raise RuntimeError("Parent lesson source changed; this Reel is stale. Analyze and create a new Reel rather than silently regenerating it.")
    return child_path, input_payload, source


def _prepare_motion_canvas(run_path: Path, timeline: dict[str, Any], shot_plan: dict[str, Any], *, batch_size: int = 2) -> dict[str, Any]:
    root = run_path / "motion_canvas"
    shots = [{**shot, "description": next(item["description"] for item in shot_plan["shots"] if item["id"] == shot["scene_id"])} for shot in timeline["shots"]]
    batches = [{"id": f"batch_{index // batch_size + 1:02d}", "chapter_ids": [item["scene_id"] for item in shots[index:index + batch_size]], "status": "pending"} for index in range(0, len(shots), batch_size)]
    manifest = {
        "version": "3.0", "content_format": "reel", "timeline_mode": "immutable_shots",
        "timeline_id": timeline["timeline_id"], "render_profile": PORTRAIT_PROFILE, "render_fps": PORTRAIT_PROFILE["fps"],
        "render_profile_fingerprint": render_profile_fingerprint(PORTRAIT_PROFILE),
        "source_audio": str((run_path / "voiceover.mp3").resolve()), "source_timestamps": str((run_path / "audio_word_timestamps.json").resolve()),
        "shots": shots, "shot_plan": shot_plan["shots"], "batches": batches,
    }
    _apply_frame_aligned_timing(manifest)
    write_json(root / "timeline.json", timeline)
    write_json(root / "manifest.json", manifest)
    _write_chapter_cues(root, shots, directory="shots")
    shutil.copy2(run_path / "voiceover.mp3", root / "voiceover.mp3")
    return manifest


def generate_reel(
    reel_run_id: str, *, from_step: int = 1, stop_after_step: int = 8, allow_model_call: bool = True,
    force: bool = False, target_shot_id: str | None = None, instruction: str = "", audio_provider: str = "gemini",
) -> dict[str, Any]:
    if not 1 <= from_step <= stop_after_step <= 8:
        raise ValueError("Reel steps must satisfy 1 <= from <= stop <= 8")
    run_path, input_payload, source = _load_child(reel_run_id)
    if from_step <= 1:
        invalidate(run_path, "narration")
        for name in ("narration.json", "narration.txt", "narration_elevenlabs.txt", "reel_treatment.json"):
            (run_path / name).unlink(missing_ok=True)
    elif from_step <= 2:
        invalidate(run_path, "narration")
    elif from_step <= 3:
        invalidate(run_path, "audio")
    elif from_step <= 6:
        invalidate(run_path, "shot_plan")
    elif target_shot_id:
        invalidate(run_path, "shot_tsx", shot_id=target_shot_id)
    candidate = read_json(run_path / "reel_candidate.json")
    selected_source = {
        "paragraphs": [item for item in source["narration"]["paragraphs"] if item["id"] in candidate["source_paragraph_ids"]],
        "story_skeleton": source["story_skeleton"], "grounded_facts": source["grounded_facts"], "valid_claim_ids": source["claim_ids"],
    }
    if from_step <= 1:
        if not allow_model_call:
            raise RuntimeError("Narrative treatment requires a configured model")
        treatment = _model_json(run_path, "reel_story_structure", "reel_story_structure.system.txt", "reel_story_structure.user.txt", TREATMENT_SCHEMA,
                                candidate_json=candidate, topic=source["topic"], audience=source["audience"], source_json=selected_source, instruction=instruction or "No additional instruction.")
        write_json(run_path / "reel_treatment.json", validate_treatment(treatment, source))
    else:
        treatment = read_json(run_path / "reel_treatment.json")
    if stop_after_step == 1: return {"run_id": reel_run_id, "stopped_after_step": 1, "artifact": "reel_treatment.json"}

    if from_step <= 2:
        narration = _model_json(run_path, "reel_script_writing", "reel_script_writing.system.txt", "reel_script_writing.user.txt", NARRATION_SCHEMA,
                                topic=source["topic"], audience=source["audience"], candidate_json=candidate, treatment_json=treatment,
                                source_json=selected_source, target_duration_seconds=input_payload.get("target_duration_seconds", 38), maximum_words=150,
                                instruction=instruction or "No additional instruction.")
        narration = validate_narration(narration, source)
        write_json(run_path / "narration.json", narration)
        (run_path / "narration.txt").write_text("\n\n".join(item["text"] for item in narration["paragraphs"]) + "\n", encoding="utf-8")
        (run_path / "narration_elevenlabs.txt").write_text(narration["elevenlabs_narration"] + "\n", encoding="utf-8")
    else:
        narration = read_json(run_path / "narration.json")
    if stop_after_step == 2: return {"run_id": reel_run_id, "stopped_after_step": 2, "artifact": "narration.json"}

    if from_step <= 3:
        audio = generate_audio(run_path, narration, target_duration=float(input_payload.get("target_duration_seconds", 38)), audio_provider=audio_provider, content_format="reel")
    else:
        audio = read_json(run_path / "audio_generation.json")
    if stop_after_step == 3: return {"run_id": reel_run_id, "stopped_after_step": 3, "artifact": "voiceover.mp3", "audio": audio}

    if from_step <= 4:
        timing = derive_timing(run_path, narration, fallback_duration=float(audio["audio_duration_seconds"]))
    else:
        timing = read_json(run_path / "audio_timing.json")
    if stop_after_step == 4: return {"run_id": reel_run_id, "stopped_after_step": 4, "artifact": "audio_word_timestamps.json"}

    if from_step <= 5:
        timeline = build_immutable_shot_timeline(read_json(run_path / "audio_word_timestamps.json"), timing)
        validate_immutable_shot_timeline(timeline)
        write_json(run_path / "reel_timeline.json", timeline)
    else:
        timeline = read_json(run_path / "reel_timeline.json")
    if stop_after_step == 5: return {"run_id": reel_run_id, "stopped_after_step": 5, "artifact": "reel_timeline.json", "shots": len(timeline["shots"])}

    if from_step <= 6:
        mapping = [{"id": item["scene_id"], "narration_paragraph_ids": item["source_paragraph_ids"], "narration": item["narration"]} for item in timeline["shots"]]
        shot_plan = _model_json(run_path, "reel_shot_planning", "reel_shot_planning.system.txt", "reel_shot_planning.user.txt", SHOT_PLAN_SCHEMA,
                                treatment_json=treatment, narration_json=narration, shot_mapping_json=mapping, source_json=selected_source,
                                profile_json=PORTRAIT_PROFILE, instruction=instruction or "No additional instruction.")
        shot_plan = validate_shot_plan(shot_plan, timeline)
        write_json(run_path / "reel_shot_plan.json", shot_plan)
    else:
        shot_plan = read_json(run_path / "reel_shot_plan.json")
    if stop_after_step == 6: return {"run_id": reel_run_id, "stopped_after_step": 6, "artifact": "reel_shot_plan.json"}

    manifest = _prepare_motion_canvas(run_path, timeline, shot_plan)
    if from_step <= 7:
        generation = generate_motion_canvas(run_path, manifest, allow_model_call=allow_model_call, force=force,
                                            workers=max(1, min(int(os.getenv("MAV_MOTION_CANVAS_WORKERS", "2")), 3)),
                                            target_chapter_id=target_shot_id, instruction=instruction)
        if generation.get("status") != "generated":
            raise RuntimeError(f"Reel Motion Canvas generation incomplete: {generation.get('failures')}")
    else:
        generation = read_json(run_path / "motion_canvas" / "generation-report.json")
    if stop_after_step == 7: return {"run_id": reel_run_id, "stopped_after_step": 7, "artifact": "motion_canvas/generation-report.json"}

    validation = validate_and_assemble(run_path, manifest, allow_model_repair=allow_model_call, max_model_repairs=2)
    summary = {"run_id": reel_run_id, "content_format": "reel", "render_profile": "reel_portrait", "status": "completed",
               "shots": len(timeline["shots"]), "audio_duration_seconds": timing["audio_duration_seconds"], "validation": validation["status"]}
    write_json(run_path / "generation_summary.json", summary)
    return summary


def render_reel(reel_run_id: str) -> dict[str, Any]:
    run_path, _, _ = _load_child(reel_run_id)
    return render_video(run_path)
