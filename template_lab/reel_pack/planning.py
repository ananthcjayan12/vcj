from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from .common import (
    DEFAULT_DURATION_SECONDS,
    PROMPT_ROOT,
    active_narration,
    active_reels,
    extract_json,
    facts_for_brief,
    load_pack,
    read_json,
    reel_path,
    save_pack,
    write_json_file,
    write_text,
)
from .schema import require_reel_id, validate_plan, validate_script

from mav_audio import generate_audio
from mav_models import call_model_text
from mav_timing import derive_timing


def plan_pack(
    run_path: Path,
    *,
    allow_model_call: bool,
    force: bool = False,
    model_call: Any = call_model_text,
) -> dict[str, Any]:
    input_payload = read_json(run_path / "input.json", {}) or {}
    pack = load_pack(run_path)
    plan_path = run_path / "pack_plan.json"
    if plan_path.exists() and not force:
        plan = read_json(plan_path, {}) or {}
        briefs = validate_plan(plan, reel_count=int(input_payload["reel_count"]))
    else:
        if not allow_model_call:
            raise RuntimeError("Reel-pack plan cache is missing and model calls are not authorized")
        system = (PROMPT_ROOT / "pack_plan.system.txt").read_text(encoding="utf-8")
        user = json.dumps({
            "requested_reel_count": input_payload["reel_count"],
            "topic": input_payload["topic"],
            "topic_ref": input_payload["topic_ref"],
            "objective_ids": input_payload["objective_ids"],
            "grounded_facts": input_payload["facts"],
            "physics_context": input_payload["physics_context"],
            "target_duration_seconds": input_payload["target_duration_seconds"],
        }, ensure_ascii=False)
        response = model_call(task="script_structure", system=system, user=user, max_tokens=24_000)
        if not response:
            raise RuntimeError("Reel-pack planner returned no response")
        write_text(run_path / "responses" / "pack-plan.txt", response)
        payload = extract_json(response)
        briefs = validate_plan(payload, reel_count=int(input_payload["reel_count"]))
        plan = {
            "version": "1.0",
            "pack_title": str(payload.get("pack_title") or input_payload["topic"]).strip(),
            "coverage_notes": str(payload.get("coverage_notes") or "").strip(),
            "reels": briefs,
        }
        write_json_file(plan_path, plan)
    by_id = {item["reel_id"]: item for item in briefs}
    for record in pack["reels"]:
        record.update(by_id[record["reel_id"]])
    pack["status"] = "planned"
    pack["current_step"] = max(int(pack.get("current_step", 1)), 2)
    return save_pack(run_path, pack)


def _script_batches(records: list[dict[str, Any]], size: int = 4):
    for offset in range(0, len(records), size):
        yield records[offset:offset + size]


def write_scripts(
    run_path: Path,
    *,
    allow_model_call: bool,
    force: bool = False,
    model_call: Any = call_model_text,
) -> dict[str, Any]:
    input_payload = read_json(run_path / "input.json", {}) or {}
    pack = load_pack(run_path)
    system = (PROMPT_ROOT / "reel_script.system.txt").read_text(encoding="utf-8")
    all_paragraphs: list[dict[str, Any]] = []
    for batch_number, batch in enumerate(_script_batches(pack["reels"]), start=1):
        cached_ids = {
            str(item.get("id"))
            for item in (read_json(run_path / "narration.json", {}) or {}).get("paragraphs", [])
            if isinstance(item, dict)
        }
        missing = [brief for brief in batch if force or brief["reel_id"] not in cached_ids]
        if not missing:
            continue
        if not allow_model_call:
            raise RuntimeError(f"Script cache missing for {[item['reel_id'] for item in missing]}")
        user = json.dumps({
            "topic": input_payload["topic"],
            "tone": input_payload["tone"],
            "briefs": [{**brief, "grounded_facts": facts_for_brief(input_payload, brief)} for brief in missing],
        }, ensure_ascii=False)
        response = model_call(task="script_writing", system=system, user=user, max_tokens=24_000)
        if not response:
            raise RuntimeError("Reel script writer returned no response")
        write_text(run_path / "responses" / f"scripts-{batch_number:02d}.txt", response)
        payload = extract_json(response)
        raw_scripts = payload.get("reels")
        if not isinstance(raw_scripts, list):
            raise RuntimeError("Reel script response must contain a reels array")
        raw_by_id = {str(item.get("reel_id")): item for item in raw_scripts if isinstance(item, dict)}
        for brief in missing:
            parent_id = brief["reel_id"]
            if parent_id not in raw_by_id:
                raise RuntimeError(f"Script response omitted {parent_id}")
            script = validate_script(raw_by_id[parent_id], brief=brief)
            paragraph = {
                "id": parent_id,
                "reel_id": parent_id,
                "title": script["title"],
                "text": script["narration"],
                "claim_ids": brief["fact_ids"],
                "objective_ids": brief["objective_ids"],
                "hook": script.get("hook") or brief["hook"],
                "retention_device": script.get("retention_device", ""),
                "open_loop": script.get("open_loop", ""),
                "learning_payoff": brief["learning_payoff"],
                "visual_concept": script.get("visual_direction") or brief["visual_concept"],
                "target_duration_seconds": script["target_duration_seconds"],
            }
            all_paragraphs.append(paragraph)
            record = next(item for item in pack["reels"] if item["reel_id"] == parent_id)
            record.update({**brief, **script, "status": "scripted", "path": "."})
    if not all_paragraphs:
        all_paragraphs = [
            {
                "id": record["reel_id"],
                "reel_id": record["reel_id"],
                "title": record.get("title") or record.get("working_title", record["reel_id"]),
                "text": record.get("narration", ""),
                "claim_ids": record.get("fact_ids", []),
                "objective_ids": record.get("objective_ids", []),
                "hook": record.get("hook", ""),
                "learning_payoff": record.get("learning_payoff", ""),
                "visual_concept": record.get("visual_concept", ""),
                "target_duration_seconds": record.get("target_duration_seconds", DEFAULT_DURATION_SECONDS),
            }
            for record in pack["reels"] if record.get("narration")
        ]
    if all_paragraphs:
        ordered = [next(item for item in all_paragraphs if item["id"] == record["reel_id"]) for record in pack["reels"] if any(item["id"] == record["reel_id"] for item in all_paragraphs)]
        narration = {
            "version": "2.0",
            "title": pack.get("topic", "Independent Reels"),
            "content_product": "topic-reel-pack",
            "paragraphs": ordered,
            "elevenlabs_narration": " ".join(item["text"] for item in ordered),
        }
        write_json_file(run_path / "narration.json", narration)
        write_text(run_path / "narration.txt", "\n\n".join(item["text"] for item in ordered))
        write_text(run_path / "narration_elevenlabs.txt", narration["elevenlabs_narration"])
    pack["status"] = "scripts_ready"
    pack["current_step"] = max(int(pack.get("current_step", 2)), 2)
    return save_pack(run_path, pack)


def generate_pack_audio(
    run_path: Path,
    *,
    audio_provider: str | None = None,
    force: bool = False,
    workers: int = 1,
    target_reel_id: str | None = None,
) -> dict[str, Any]:
    pack = load_pack(run_path)
    input_payload = read_json(run_path / "input.json", {}) or {}
    selected = [
        record for record in active_reels(pack)
        if target_reel_id is None or record["reel_id"] == require_reel_id(target_reel_id)
    ]

    def generate_one(record: dict[str, Any]):
        parent_id = record["reel_id"]
        if (run_path / "audio_generation.json").exists() and not force:
            return parent_id, "audio_ready", None
        try:
            narration = active_narration(read_json(run_path / "narration.json", {}) or {}, pack)
            generate_audio(
                run_path,
                narration,
                target_duration=float(input_payload.get("target_duration_seconds") or DEFAULT_DURATION_SECONDS),
                audio_provider=audio_provider or input_payload.get("audio_provider", "gemini"),
            )
            return parent_id, "audio_ready", None
        except Exception as exc:
            return parent_id, "failed", str(exc)

    # Audio is one concatenated master file with one independent chapter chunk
    # per Reel. Generate it once; the chunk manifest preserves per-Reel ranges.
    results = [generate_one(selected[0])] if selected else []
    errors = []
    by_id = {item["reel_id"]: item for item in pack["reels"]}
    for parent_id, status, error in results:
        for item in selected:
            by_id[item["reel_id"]]["status"] = status
        if error:
            for item in selected:
                by_id[item["reel_id"]]["error"] = error
            errors.append(f"{parent_id}: {error}")
    pack["status"] = "partial" if errors else "audio_ready"
    pack["current_step"] = max(int(pack.get("current_step", 2)), 3)
    save_pack(run_path, pack)
    if errors:
        raise RuntimeError("; ".join(errors))
    return pack


def derive_pack_timing(
    run_path: Path,
    *,
    force: bool = False,
    target_reel_id: str | None = None,
) -> dict[str, Any]:
    pack = load_pack(run_path)
    errors = []
    narration = active_narration(read_json(run_path / "narration.json", {}) or {}, pack)
    for record in active_reels(pack):
        parent_id = record["reel_id"]
        if target_reel_id and parent_id != require_reel_id(target_reel_id):
            continue
        if (run_path / "audio_timing.json").exists() and (run_path / "audio_word_timestamps.json").exists() and not force:
            record["status"] = "timed"
            continue
        try:
            narration = active_narration(read_json(run_path / "narration.json", {}) or {}, pack)
            audio = read_json(run_path / "audio_generation.json", {}) or {}
            fallback = float(audio.get("audio_duration_seconds") or audio.get("estimated_duration_seconds") or DEFAULT_DURATION_SECONDS * len(pack["reels"]))
            derive_timing(run_path, narration, fallback_duration=fallback)
            record["status"] = "timed"
        except Exception as exc:
            record["status"] = "failed"
            record["error"] = str(exc)
            errors.append(f"{parent_id}: {exc}")
    pack["status"] = "partial" if errors else "timing_ready"
    pack["current_step"] = max(int(pack.get("current_step", 3)), 4)
    save_pack(run_path, pack)
    if errors:
        raise RuntimeError("; ".join(errors))
    return pack
