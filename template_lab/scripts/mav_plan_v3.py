"""V3 generative scene planner: asks the model for HTML, CSS, and GSAP per scene."""
from __future__ import annotations

import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

LAB_ROOT = Path(__file__).resolve().parents[1]
if str(LAB_ROOT) not in sys.path:
    sys.path.insert(0, str(LAB_ROOT))

from prompts import load as load_prompt

from mav_schema import read_json, run_dir, write_json


def _log(message: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] MAV V3: {message}", file=sys.stderr, flush=True)


def _load_word_timestamps(run_path: Path, narration_ids: list[str]) -> list[dict[str, Any]]:
    """Load word timestamps for specific narration paragraphs."""
    path = run_path / "audio_word_timestamps.json"
    if not path.exists():
        return []
    payload = read_json(path)
    id_set = set(narration_ids)
    return [word for word in payload.get("words", []) if word.get("paragraph_id") in id_set]


def _format_word_timestamps(words: list[dict[str, Any]]) -> str:
    """Format word timestamps as a compact list for the prompt."""
    if not words:
        return "(no word-level timestamps available; use narration timing)"
    lines = []
    for word in words:
        lines.append(f"  {float(word.get('start', 0)):.2f}s: \"{word.get('word', '')}\"")
    return "\n".join(lines)


def _merge_narration_timing(narration: dict[str, Any], timing: dict[str, Any]) -> list[dict[str, Any]]:
    """Merge narration paragraphs with timing info."""
    timing_by_id = {item["id"]: item for item in timing.get("paragraphs", [])}
    result = []
    for paragraph in narration.get("paragraphs", []):
        timing_item = timing_by_id.get(paragraph["id"], {})
        result.append(
            {
                "id": paragraph["id"],
                "text": paragraph["text"],
                "beat_label": paragraph.get("beat_label", ""),
                "start": float(timing_item.get("start", 0) or 0),
                "end": float(timing_item.get("end", 0) or 0),
                "duration": float(timing_item.get("duration", 0) or 0),
            }
        )
    return result


def _extract_scene_html(response_text: str) -> str | None:
    """Extract the HTML block between scene markers."""
    match = re.search(r"<!--SCENE_HTML_START-->(.*?)<!--SCENE_HTML_END-->", response_text, re.DOTALL)
    if not match:
        return None
    scene_html = match.group(1).strip()
    if "<style" not in scene_html.lower():
        orphan_styles = re.findall(r"<style\b[^>]*>.*?</style>", response_text, flags=re.DOTALL | re.IGNORECASE)
        if orphan_styles:
            scene_html = scene_html.rstrip() + "\n\n" + "\n".join(orphan_styles)
    return scene_html


def _extract_scene_gsap(response_text: str) -> str | None:
    """Extract the GSAP block between scene markers."""
    match = re.search(r"<!--SCENE_GSAP_START-->(.*?)<!--SCENE_GSAP_END-->", response_text, re.DOTALL)
    return match.group(1).strip() if match else None


def _positive_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if not raw_value:
        return default
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a positive integer") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be a positive integer")
    return value


def _default_visual_identity() -> dict[str, Any]:
    return {
        "persona": "experienced IGCSE Physics teacher and scientific animation director",
        "composition_style": "clean science-notebook explainer with precise diagrams, graphs, experiments, and equations",
        "motion_style": "prediction pauses, causal motion, progressive diagram construction, and restrained camera movement",
        "required_elements": ["physically_meaningful_diagram", "direct_labels_with_units"],
        "forbidden_elements": ["decorative_data", "unlabelled_axis", "text_wall"],
    }


def _load_template_visual_identity(template_id: str) -> dict[str, Any]:
    """Load the visual_identity block from the template's config.json."""
    config_path = LAB_ROOT / "templates" / template_id / "config.json"
    if not config_path.exists():
        _log(f"template config not found for '{template_id}', using default visual identity")
        return _default_visual_identity()
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        identity = config.get("visual_identity")
        if identity:
            return identity
        _log(f"no visual_identity in '{template_id}' config, using default")
    except Exception as exc:  # noqa: BLE001
        _log(f"failed to load template config for '{template_id}': {exc}")
    return _default_visual_identity()


def _group_beats_into_scenes(
    paragraphs: list[dict[str, Any]],
    beats_per_scene: int = 3,
) -> list[list[dict[str, Any]]]:
    """Group consecutive narration paragraphs into multi-beat scene groups."""
    groups: list[list[dict[str, Any]]] = []
    for i in range(0, len(paragraphs), beats_per_scene):
        groups.append(paragraphs[i : i + beats_per_scene])
    return groups


def _validate_layout_json(layout: dict[str, Any], scene_id: str) -> None:
    """Validate that element IDs and GSAP target_ids match across all beats."""
    for beat in layout.get("beats", []):
        beat_id = beat.get("beat_id", "?")
        element_ids = {el["id"] for el in beat.get("layout", {}).get("elements", [])}
        gsap_targets = {entry["target_id"] for entry in beat.get("gsap_choreography", [])}
        # Warn on mismatches but do not hard-fail; the coder may still resolve them
        unmatched_targets = gsap_targets - element_ids
        if unmatched_targets:
            _log(
                f"WARNING {scene_id} beat {beat_id}: GSAP targets not in elements: "
                + ", ".join(sorted(unmatched_targets))
            )


def load_v3_plan_with_scene_files(run_path: Path) -> dict[str, Any]:
    """Load scene_plan_v3.json and apply editable per-scene JSON overrides."""
    plan = read_json(run_path / "scene_plan_v3.json")
    scene_dir = run_path / "v3_scenes"
    if not scene_dir.exists():
        return plan
    merged_scenes = []
    for scene in plan.get("scenes", []):
        scene_path = scene_dir / f"{scene['id']}.json"
        if scene_path.exists():
            override = read_json(scene_path)
            for key in ("id", "paragraph_id", "start", "duration", "beat_label", "narration_text"):
                override.setdefault(key, scene.get(key))
            merged_scenes.append(override)
        else:
            merged_scenes.append(scene)
    plan["scenes"] = merged_scenes
    plan["scene_count"] = len(merged_scenes)
    return plan


def generate_v3_scenes(
    input_payload: dict[str, Any],
    narration: dict[str, Any],
    timing: dict[str, Any],
    *,
    target_scene_id: str | None = None,
) -> dict[str, Any]:
    """Generate V3 scenes using the two-step GLM-5.2 (creative director) → Kimi K2 (coder) pipeline."""
    from mav_models import call_model_json, call_model_text

    run_path = run_dir(input_payload["run_id"])
    paragraphs_with_timing = _merge_narration_timing(narration, timing)
    template_id = input_payload.get("template_id", "physics")
    visual_identity = _load_template_visual_identity(template_id)

    # Build system prompts with visual identity injected
    design_system = load_prompt("v3_design_system")
    creative_director_system = load_prompt(
        "v3_creative_director.system",
        design_system=design_system,
        template_persona=visual_identity["persona"],
        template_composition_style=visual_identity["composition_style"],
        template_required_elements=", ".join(visual_identity.get("required_elements", [])) or "(none specified)",
        template_forbidden_elements=", ".join(visual_identity.get("forbidden_elements", [])) or "(none specified)",
    )
    coder_system = load_prompt("v3_scene_coder.system")
    scene_regen_instruction = os.getenv("MAV_SCENE_REGEN_INSTRUCTION", "").strip()
    step_regen_instruction = os.getenv("MAV_STEP_REGEN_INSTRUCTION", "").strip()
    director_instruction = scene_regen_instruction or step_regen_instruction

    title = narration.get("title", input_payload.get("topic", ""))
    topic = input_payload.get("topic", "")

    # Group beats into multi-beat scene groups
    beats_per_scene = int(os.getenv("MAV_V3_BEATS_PER_SCENE", "2"))
    scene_groups = _group_beats_into_scenes(paragraphs_with_timing, beats_per_scene)
    total_scenes = len(scene_groups)

    existing_scenes: dict[str, dict[str, Any]] = {}
    if target_scene_id:
        existing_path = run_path / "scene_plan_v3.json"
        if not existing_path.exists():
            raise RuntimeError("--v3-scene-id requires an existing scene_plan_v3.json")
        existing_plan = load_v3_plan_with_scene_files(run_path)
        existing_scenes = {scene["id"]: scene for scene in existing_plan.get("scenes", [])}

    _log(
        f"starting scene generation: run={input_payload['run_id']} "
        f"beats={len(paragraphs_with_timing)} beats_per_scene={beats_per_scene} "
        f"scene_groups={total_scenes} template={template_id}"
        + (f" target_scene={target_scene_id}" if target_scene_id else "")
    )

    def generate_scene_group(group_index: int, beat_group: list[dict[str, Any]]) -> dict[str, Any]:
        scene_id = f"scene_{group_index + 1:02d}"
        scene_number = group_index + 1
        canvas_start = beat_group[0]["start"]
        canvas_end = beat_group[-1]["end"]
        canvas_duration = canvas_end - canvas_start

        # Collect word timestamps for all beats in this group
        all_para_ids = [p["id"] for p in beat_group]
        word_ts = _load_word_timestamps(run_path, all_para_ids)
        word_timestamps = _format_word_timestamps(word_ts)

        # Build beats summary for creative director prompt
        beats_summary_lines = []
        for beat_index, paragraph in enumerate(beat_group):
            beat_num = f"b{beat_index + 1:02d}"
            beats_summary_lines.append(
                f"BEAT {beat_num} [{paragraph['beat_label']}] "
                f"time={paragraph['start']:.2f}s\u2013{paragraph['end']:.2f}s "
                f"({paragraph['duration']:.2f}s):\n{paragraph['text']}"
            )
        beats_summary = "\n\n".join(beats_summary_lines)

        creative_user_prompt = (
            f"SCENE: {scene_id}\n"
            f"SCENE GROUP: {scene_number} of {total_scenes}\n"
            f"CANVAS START: {canvas_start:.3f}s\n"
            f"CANVAS DURATION: {canvas_duration:.3f}s\n"
            f"BEATS IN THIS SCENE: {len(beat_group)}\n"
            f"VIDEO TITLE: {title}\n"
            f"TOPIC: {topic}\n\n"
            f"=== BEATS ===\n{beats_summary}\n\n"
            f"=== WORD TIMESTAMPS ===\n{word_timestamps}\n\n"
            "Design the layout JSON for this multi-beat scene. "
            "Use beat IDs b01, b02, b03 etc. and prefix all element IDs with the beat number."
        )
        if director_instruction:
            creative_user_prompt += (
                "\n\n=== DIRECTOR OVERRIDE ===\n"
                f"{director_instruction}\n"
                "Honor this direction while preserving beat namespacing and the ID contract."
            )

        _log(
            f"{scene_id} ({scene_number}/{total_scenes}): step 1 \u2014 creative director "
            f"beats={len(beat_group)} canvas={canvas_duration:.1f}s"
        )

        # STEP 1: GLM-5.2 creative director → Layout JSON
        layout_json = call_model_json(
            task="v3_creative_director",
            system=creative_director_system,
            user=creative_user_prompt,
            max_tokens=16000,
        )
        if not layout_json:
            raise RuntimeError(f"Creative director returned no output for {scene_id}")

        _validate_layout_json(layout_json, scene_id)
        _log(f"{scene_id}: step 1 complete — layout JSON has {len(layout_json.get('beats', []))} beats")

        # STEP 2: Kimi K2 coder → HTML/CSS/GSAP
        coder_user_prompt = (
            f"Translate this Layout JSON into production HTML/CSS/GSAP code for scene {scene_id}:\n\n"
            f"{json.dumps(layout_json, indent=2)}"
        )
        _log(f"{scene_id}: step 2 \u2014 Kimi K2 code generation")
        code_response = call_model_text(
            task="v3_scene_coder",
            system=coder_system,
            user=coder_user_prompt,
            max_tokens=32000,
        )
        if not code_response:
            raise RuntimeError(f"Scene coder returned no output for {scene_id}")

        scene_html = _extract_scene_html(code_response)
        scene_gsap = _extract_scene_gsap(code_response)
        if not scene_html:
            raise RuntimeError(f"Scene coder did not return valid HTML for {scene_id}")
        if not scene_gsap:
            raise RuntimeError(f"Scene coder did not return valid GSAP for {scene_id}")

        _log(
            f"{scene_id}: step 2 complete "
            f"(html={len(scene_html):,} chars, gsap={len(scene_gsap):,} chars)"
        )

        scene = {
            "id": scene_id,
            "paragraph_id": beat_group[0]["id"],
            "beat_ids": [p["id"] for p in beat_group],
            "start": canvas_start,
            "duration": canvas_duration,
            "beat_label": beat_group[0]["beat_label"],
            "narration_text": " ".join(p["text"] for p in beat_group),
            "scene_html": scene_html,
            "scene_gsap": scene_gsap,
            "layout_json": layout_json,
            "raw_code_response": code_response,
        }
        write_json(run_path / "v3_scenes" / f"{scene_id}.json", scene)
        _log(f"{scene_id}: saved v3_scenes/{scene_id}.json")
        return scene

    scenes: list[dict[str, Any] | None] = [None] * total_scenes
    generation_jobs: list[tuple[int, list[dict[str, Any]]]] = []
    for group_index, beat_group in enumerate(scene_groups):
        scene_id = f"scene_{group_index + 1:02d}"
        if target_scene_id and scene_id != target_scene_id:
            if scene_id not in existing_scenes:
                raise RuntimeError(f"Cannot preserve {scene_id}: missing from existing V3 plan")
            scenes[group_index] = existing_scenes[scene_id]
            continue
        generation_jobs.append((group_index, beat_group))

    # Sequential execution to leverage Z.AI context caching on the creative director system prompt
    workers = _positive_int_env("MAV_V3_SCENE_CONCURRENCY", 1)
    _log(f"dispatching {len(generation_jobs)} scene group(s) with concurrency={workers}")
    if workers == 1:
        for group_index, beat_group in generation_jobs:
            scenes[group_index] = generate_scene_group(group_index, beat_group)
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_index = {
                executor.submit(generate_scene_group, gi, bg): gi for gi, bg in generation_jobs
            }
            try:
                for future in as_completed(future_to_index):
                    scenes[future_to_index[future]] = future.result()
            except Exception:
                for future in future_to_index:
                    future.cancel()
                raise

    ordered_scenes = [scene for scene in scenes if scene is not None]
    if len(ordered_scenes) != total_scenes:
        raise RuntimeError("V3 scene generation ended with missing scene outputs")

    plan = {
        "version": "3.0",
        "planner_mode": "v3_two_model_pipeline",
        "run_id": input_payload["run_id"],
        "title": title,
        "template_id": template_id,
        "beats_per_scene": beats_per_scene,
        "duration": timing["audio_duration_seconds"],
        "scene_count": len(ordered_scenes),
        "scenes": ordered_scenes,
    }
    write_json(run_path / "scene_plan_v3.json", plan)
    _log(f"wrote scene_plan_v3.json with {len(ordered_scenes)} scene groups ({beats_per_scene} beats each)")
    return plan
