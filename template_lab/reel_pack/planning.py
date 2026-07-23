from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from .common import (
    DEFAULT_DURATION_SECONDS,
    PROMPT_ROOT,
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
    for batch_number, batch in enumerate(_script_batches(pack["reels"]), start=1):
        missing = [
            brief for brief in batch
            if force or not (reel_path(run_path, brief["reel_id"]) / "script.json").exists()
        ]
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
            child = reel_path(run_path, parent_id)
            child.mkdir(parents=True, exist_ok=True)
            child_input = {
                **input_payload,
                "run_id": f"{input_payload['run_id']}--{parent_id}",
                "parent_pack_run_id": input_payload["run_id"],
                "parent_reel_id": parent_id,
                "objective_ids": brief["objective_ids"],
                "facts": facts_for_brief(input_payload, brief),
                "target_duration_seconds": script["target_duration_seconds"],
                "content_product": "topic-reel-pack",
                "standalone": True,
            }
            narration = {
                "version": "1.0",
                "title": script["title"],
                "paragraphs": [{
                    "id": "standalone_reel",
                    "text": script["narration"],
                    "claim_ids": brief["fact_ids"],
                }],
                "elevenlabs_narration": script["narration"],
            }
            write_json_file(child / "input.json", child_input)
            write_json_file(child / "brief.json", brief)
            write_json_file(child / "script.json", script)
            write_json_file(child / "narration.json", narration)
            write_text(child / "narration.txt", script["narration"])
            write_text(child / "narration_elevenlabs.txt", script["narration"])
            brief["status"] = "scripted"
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
        record for record in pack["reels"]
        if target_reel_id is None or record["reel_id"] == require_reel_id(target_reel_id)
    ]

    def generate_one(record: dict[str, Any]):
        parent_id = record["reel_id"]
        child = reel_path(run_path, parent_id)
        if (child / "audio_generation.json").exists() and not force:
            return parent_id, "audio_ready", None
        try:
            narration = read_json(child / "narration.json", {}) or {}
            script = read_json(child / "script.json", {}) or {}
            generate_audio(
                child,
                narration,
                target_duration=float(script.get("target_duration_seconds") or DEFAULT_DURATION_SECONDS),
                audio_provider=audio_provider or input_payload.get("audio_provider", "gemini"),
            )
            return parent_id, "audio_ready", None
        except Exception as exc:
            return parent_id, "failed", str(exc)

    with ThreadPoolExecutor(max_workers=max(1, min(int(workers), 3))) as executor:
        results = [future.result() for future in as_completed(
            [executor.submit(generate_one, record) for record in selected]
        )]
    errors = []
    by_id = {item["reel_id"]: item for item in pack["reels"]}
    for parent_id, status, error in results:
        by_id[parent_id]["status"] = status
        if error:
            by_id[parent_id]["error"] = error
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
    for record in pack["reels"]:
        parent_id = record["reel_id"]
        if target_reel_id and parent_id != require_reel_id(target_reel_id):
            continue
        child = reel_path(run_path, parent_id)
        if (child / "audio_timing.json").exists() and (child / "audio_word_timestamps.json").exists() and not force:
            record["status"] = "timed"
            continue
        try:
            narration = read_json(child / "narration.json", {}) or {}
            audio = read_json(child / "audio_generation.json", {}) or {}
            fallback = float(audio.get("audio_duration_seconds") or audio.get("estimated_duration_seconds") or DEFAULT_DURATION_SECONDS)
            derive_timing(child, narration, fallback_duration=fallback)
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
