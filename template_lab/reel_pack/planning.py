from __future__ import annotations

import json
import os
import re
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
    save_pack,
    write_json_file,
    write_text,
)
from .schema import require_reel_id, validate_plan, validate_script

from mav_audio import generate_audio
from mav_models import call_model_text
from mav_timing import derive_timing


REEL_GEMINI_TTS_PROMPT_PREFIX = (
    "Read the following narration exactly as written for a modern vertical educational Reel. "
    "Use a brisk, energetic, confident teaching pace around 155-170 words per minute. "
    "Sound curious at questions, create a short suspenseful hold before reversals, and land the "
    "final payoff clearly. Keep articulation crisp and natural, never frantic, theatrical, or robotic. "
    "Do not add, remove, or rewrite words.\n\n"
)


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
            "version": "2.0",
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


def _script_batches(records: list[dict[str, Any]], size: int = 1):
    for offset in range(0, len(records), size):
        yield records[offset:offset + size]


def _paragraph_from_script(brief: dict[str, Any], script: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": brief["reel_id"],
        "reel_id": brief["reel_id"],
        "title": script["title"],
        "text": script["narration"],
        "narration": script["narration"],
        "claim_ids": brief["fact_ids"],
        "objective_ids": brief["objective_ids"],
        "hook": script.get("hook") or brief["hook"],
        "retention_device": script.get("retention_device", ""),
        "open_loop": script.get("open_loop", ""),
        "learning_payoff": brief["learning_payoff"],
        "visual_concept": script.get("visual_direction") or brief["visual_concept"],
        "target_duration_seconds": script["target_duration_seconds"],
        "central_question": brief["central_question"],
        "misconception": brief["misconception"],
        "answer": brief["answer"],
        "continuity_entity": brief["continuity_entity"],
        "visual_thesis": brief["visual_thesis"],
        "beats": script["beats"],
    }


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
    existing_narration = read_json(run_path / "narration.json", {}) or {}
    paragraph_by_id = {
        str(item.get("id") or item.get("reel_id")): item
        for item in existing_narration.get("paragraphs", [])
        if isinstance(item, dict)
    }
    batch_size = max(1, int(pack.get("script_batch_size", 1)))
    for batch_number, batch in enumerate(_script_batches(pack["reels"], size=batch_size), start=1):
        missing = [
            brief for brief in batch
            if force or brief["reel_id"] not in paragraph_by_id
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
            paragraph_by_id[parent_id] = _paragraph_from_script(brief, script)
            record = next(item for item in pack["reels"] if item["reel_id"] == parent_id)
            record.update({**brief, **script, "status": "scripted", "path": "."})
    ordered = [
        paragraph_by_id[record["reel_id"]]
        for record in pack["reels"]
        if record["reel_id"] in paragraph_by_id
    ]
    if ordered:
        narration = {
            "version": "3.0",
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


def _chapter_duration(record: dict[str, Any]) -> float:
    if record.get("duration") is not None:
        return float(record["duration"])
    if record.get("absolute_start") is not None and record.get("absolute_end") is not None:
        return float(record["absolute_end"]) - float(record["absolute_start"])
    if record.get("speech_duration") is not None:
        return float(record["speech_duration"]) + float(record.get("trailing_pause") or 0)
    return 0.0


def _validate_audio_durations(run_path: Path, pack: dict[str, Any]) -> None:
    manifest = read_json(run_path / "audio_chunks" / "manifest.json", {}) or {}
    chapters = {str(item.get("id")): item for item in manifest.get("chapters", []) if isinstance(item, dict)}
    for record in active_reels(pack):
        chapter = chapters.get(record["reel_id"])
        if not chapter:
            raise RuntimeError(f"Audio chunk manifest omitted {record['reel_id']}")
        actual = _chapter_duration(chapter)
        target = float(record.get("target_duration_seconds") or DEFAULT_DURATION_SECONDS)
        if actual < target * 0.8 or actual > target * 1.2:
            raise RuntimeError(
                f"{record['reel_id']} audio duration {actual:.1f}s is outside the allowed "
                f"{target * 0.8:.1f}-{target * 1.2:.1f}s range for a {target:.1f}s Reel"
            )
        record["audio_duration_seconds"] = round(actual, 3)


def generate_pack_audio(
    run_path: Path,
    *,
    audio_provider: str | None = None,
    force: bool = False,
    workers: int = 1,
    target_reel_id: str | None = None,
) -> dict[str, Any]:
    del workers
    pack = load_pack(run_path)
    input_payload = read_json(run_path / "input.json", {}) or {}
    selected = [
        record for record in active_reels(pack)
        if target_reel_id is None or record["reel_id"] == require_reel_id(target_reel_id)
    ]
    if not selected:
        return pack
    try:
        narration = active_narration(read_json(run_path / "narration.json", {}) or {}, pack)
        if force or not (run_path / "audio_generation.json").exists():
            selected_provider = audio_provider or input_payload.get("audio_provider", "gemini")
            original_prompt = os.environ.get("GEMINI_TTS_PROMPT_PREFIX")
            if selected_provider == "gemini":
                os.environ["GEMINI_TTS_PROMPT_PREFIX"] = os.getenv(
                    "MAV_REEL_TTS_PROMPT_PREFIX",
                    REEL_GEMINI_TTS_PROMPT_PREFIX,
                )
            try:
                generate_audio(
                    run_path,
                    narration,
                    target_duration=float(input_payload.get("target_duration_seconds") or DEFAULT_DURATION_SECONDS),
                    audio_provider=selected_provider,
                )
            finally:
                if selected_provider == "gemini":
                    if original_prompt is None:
                        os.environ.pop("GEMINI_TTS_PROMPT_PREFIX", None)
                    else:
                        os.environ["GEMINI_TTS_PROMPT_PREFIX"] = original_prompt
        _validate_audio_durations(run_path, pack)
        for item in selected:
            item["status"] = "audio_ready"
            item.pop("error", None)
    except Exception as exc:
        for item in selected:
            item["status"] = "failed"
            item["error"] = str(exc)
        pack["status"] = "partial"
        save_pack(run_path, pack)
        raise
    pack["status"] = "audio_ready"
    pack["current_step"] = max(int(pack.get("current_step", 2)), 3)
    return save_pack(run_path, pack)


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:['’][a-z0-9]+)?", str(text).lower())


def derive_reel_beat_timing(run_path: Path, pack: dict[str, Any]) -> dict[str, Any]:
    timestamps = read_json(run_path / "audio_word_timestamps.json", {}) or {}
    audio_manifest = read_json(run_path / "audio_chunks" / "manifest.json", {}) or {}
    words_by_id: dict[str, list[dict[str, Any]]] = {}
    for word in timestamps.get("words", []):
        if not isinstance(word, dict):
            continue
        words_by_id.setdefault(str(word.get("paragraph_id") or ""), []).append(word)
    chapters = {
        str(item.get("id")): item
        for item in audio_manifest.get("chapters", [])
        if isinstance(item, dict)
    }
    result: dict[str, Any] = {"version": "1.0", "reels": {}}
    for record in active_reels(pack):
        reel = record["reel_id"]
        words = sorted(words_by_id.get(reel, []), key=lambda item: float(item.get("start") or 0))
        beats = list(record.get("beats") or [])
        if not words:
            raise RuntimeError(f"No aligned words were found for {reel}")
        if not beats:
            raise RuntimeError(f"No scripted beat structure was found for {reel}")
        chapter = chapters.get(reel, {})
        origin = float(chapter.get("absolute_start") if chapter.get("absolute_start") is not None else words[0]["start"])
        requested_counts = [len(_tokens(item.get("spoken_text", ""))) for item in beats]
        requested_total = sum(requested_counts)
        tolerance = max(2, round(len(words) * 0.05))
        if abs(requested_total - len(words)) > tolerance:
            raise RuntimeError(
                f"{reel} beat text has {requested_total} words but alignment contains {len(words)}; "
                "regenerate timing from the approved narration"
            )
        cursor = 0
        timed = []
        for index, (beat, requested_count) in enumerate(zip(beats, requested_counts)):
            end_cursor = len(words) if index == len(beats) - 1 else min(len(words), cursor + requested_count)
            selected_words = words[cursor:end_cursor]
            if not selected_words:
                raise RuntimeError(f"{reel} beat {beat['id']} has no aligned audio words")
            start = max(0.0, float(selected_words[0]["start"]) - origin)
            end = max(start, float(selected_words[-1]["end"]) - origin)
            timed.append({
                **beat,
                "start": round(start, 3),
                "end": round(end, 3),
                "duration": round(end - start, 3),
                "start_word_index": cursor,
                "end_word_index": end_cursor,
            })
            cursor = end_cursor
        duration = _chapter_duration(chapter) or max(float(words[-1]["end"]) - origin, 0.0)
        result["reels"][reel] = {
            "reel_id": reel,
            "duration": round(duration, 3),
            "beats": timed,
        }
        record["timed_beats"] = timed
    write_json_file(run_path / "beat_timing.json", result)
    return result


def derive_pack_timing(
    run_path: Path,
    *,
    force: bool = False,
    target_reel_id: str | None = None,
) -> dict[str, Any]:
    pack = load_pack(run_path)
    selected = [
        record for record in active_reels(pack)
        if target_reel_id is None or record["reel_id"] == require_reel_id(target_reel_id)
    ]
    try:
        narration = active_narration(read_json(run_path / "narration.json", {}) or {}, pack)
        timing_exists = (run_path / "audio_timing.json").exists() and (run_path / "audio_word_timestamps.json").exists()
        if force or not timing_exists:
            audio = read_json(run_path / "audio_generation.json", {}) or {}
            fallback = float(
                audio.get("audio_duration_seconds")
                or audio.get("estimated_duration_seconds")
                or DEFAULT_DURATION_SECONDS * len(pack["reels"])
            )
            derive_timing(run_path, narration, fallback_duration=fallback)
        derive_reel_beat_timing(run_path, pack)
        for record in selected:
            record["status"] = "timed"
            record.pop("error", None)
    except Exception as exc:
        for record in selected:
            record["status"] = "failed"
            record["error"] = str(exc)
        pack["status"] = "partial"
        save_pack(run_path, pack)
        raise
    pack["status"] = "timing_ready"
    pack["current_step"] = max(int(pack.get("current_step", 3)), 4)
    return save_pack(run_path, pack)
