from __future__ import annotations

import re
from typing import Any

CONTENT_PRODUCT = "topic-reel-pack"
RENDER_PROFILE = "portrait-short-v1"
DEFAULT_REEL_COUNT = 5
MIN_REEL_COUNT = 1
MAX_REEL_COUNT = 24
MIN_DURATION_SECONDS = 20.0
DEFAULT_DURATION_SECONDS = 35.0
MAX_DURATION_SECONDS = 75.0
MIN_BLUEPRINT_BEATS = 5
MAX_BLUEPRINT_BEATS = 7
REEL_ID_RE = re.compile(r"^reel_(\d{3})$")

PACK_STATES = {
    "created",
    "planned",
    "scripts_ready",
    "audio_ready",
    "timing_ready",
    "visuals_ready",
    "screened",
    "needs_review",
    "approved",
    "rendering",
    "complete",
    "partial",
    "failed",
}

REEL_STATES = {
    "planned",
    "scripted",
    "rejected",
    "audio_ready",
    "timed",
    "visual_ready",
    "flagged",
    "repaired_pending_review",
    "approved",
    "rendered",
    "failed",
}


def reel_id(index: int) -> str:
    if index < 1 or index > MAX_REEL_COUNT:
        raise ValueError(f"Reel index must be between 1 and {MAX_REEL_COUNT}")
    return f"reel_{index:03d}"


def require_reel_id(value: str) -> str:
    normalized = str(value or "").strip()
    if not REEL_ID_RE.fullmatch(normalized):
        raise ValueError(f"Invalid standalone Reel ID: {value!r}")
    return normalized


def bounded_reel_count(value: Any) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("reel_count must be an integer") from exc
    if not MIN_REEL_COUNT <= count <= MAX_REEL_COUNT:
        raise ValueError(f"reel_count must be between {MIN_REEL_COUNT} and {MAX_REEL_COUNT}")
    return count


def bounded_duration(value: Any) -> float:
    try:
        duration = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("target duration must be numeric") from exc
    if not MIN_DURATION_SECONDS <= duration <= MAX_DURATION_SECONDS:
        raise ValueError(
            f"target duration must be between {MIN_DURATION_SECONDS:g} and {MAX_DURATION_SECONDS:g} seconds"
        )
    return round(duration, 3)


def _required_text(raw: dict[str, Any], key: str, *, fallback: str = "") -> str:
    value = str(raw.get(key) or fallback).strip()
    if not value:
        raise ValueError(f"Reel blueprint must include {key}")
    return value


def _normalize_beat(raw: dict[str, Any], *, index: int) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"Blueprint beat {index} must be an object")
    beat_id = str(raw.get("id") or "").strip()
    narrative_job = str(raw.get("narrative_job") or "").strip()
    visual_job = str(raw.get("visual_job") or "").strip()
    transition = str(raw.get("transition_intent") or "continuous transformation").strip()
    if not beat_id or not narrative_job or not visual_job:
        raise ValueError(f"Blueprint beat {index} must include id, narrative_job, and visual_job")
    try:
        time_budget = float(raw.get("time_budget"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Blueprint beat {beat_id} must include a numeric time_budget") from exc
    try:
        energy = int(raw.get("energy"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Blueprint beat {beat_id} must include an integer energy") from exc
    if time_budget <= 0:
        raise ValueError(f"Blueprint beat {beat_id} time_budget must be positive")
    if not 1 <= energy <= 5:
        raise ValueError(f"Blueprint beat {beat_id} energy must be between 1 and 5")
    return {
        "id": beat_id,
        "time_budget": round(time_budget, 3),
        "narrative_job": narrative_job,
        "visual_job": visual_job,
        "energy": energy,
        "transition_intent": transition,
    }


def normalize_brief(raw: dict[str, Any], *, expected_id: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"{expected_id} brief must be an object")
    received_id = require_reel_id(str(raw.get("reel_id") or expected_id))
    if received_id != expected_id:
        raise ValueError(f"Expected {expected_id}, received {received_id}")
    title = str(raw.get("working_title") or raw.get("title") or "").strip()
    hook = str(raw.get("hook") or "").strip()
    payoff = str(raw.get("learning_payoff") or raw.get("payoff") or "").strip()
    visual = str(raw.get("visual_concept") or "").strip()
    if not title or not hook or not payoff or not visual:
        raise ValueError(f"{expected_id} must include title, hook, learning_payoff, and visual_concept")
    objective_ids = list(dict.fromkeys(str(item).strip() for item in raw.get("objective_ids", []) if str(item).strip()))
    fact_ids = list(dict.fromkeys(str(item).strip() for item in raw.get("fact_ids", []) if str(item).strip()))
    relationships = [
        str(item).strip()
        for item in raw.get("required_scientific_relationships", [])
        if str(item).strip()
    ]
    target_duration = bounded_duration(raw.get("target_duration_seconds", DEFAULT_DURATION_SECONDS))
    beats = [
        _normalize_beat(item, index=index)
        for index, item in enumerate(raw.get("beats") or [], start=1)
    ]
    if not MIN_BLUEPRINT_BEATS <= len(beats) <= MAX_BLUEPRINT_BEATS:
        raise ValueError(
            f"{expected_id} blueprint must contain {MIN_BLUEPRINT_BEATS}-{MAX_BLUEPRINT_BEATS} beats"
        )
    beat_ids = [item["id"] for item in beats]
    if len(set(beat_ids)) != len(beat_ids):
        raise ValueError(f"{expected_id} blueprint contains duplicate beat IDs")
    budget_total = sum(item["time_budget"] for item in beats)
    validation_warnings: list[str] = []
    if budget_total > target_duration * 1.2:
        validation_warnings.append(
            f"{expected_id} beat budgets total {budget_total:g}s, above the allowed target range"
        )
    return {
        "reel_id": expected_id,
        "working_title": title,
        "hook": hook,
        "learning_payoff": payoff,
        "objective_ids": objective_ids,
        "fact_ids": fact_ids,
        "angle": str(raw.get("angle") or "standalone-concept").strip(),
        "visual_concept": visual,
        "required_scientific_relationships": relationships,
        "target_duration_seconds": target_duration,
        "central_question": _required_text(raw, "central_question", fallback=hook),
        "misconception": _required_text(raw, "misconception"),
        "answer": _required_text(raw, "answer", fallback=payoff),
        "continuity_entity": _required_text(raw, "continuity_entity"),
        "visual_thesis": _required_text(raw, "visual_thesis", fallback=visual),
        "beats": beats,
        "validation_warnings": validation_warnings,
        "independent": True,
        "status": "planned",
    }


def validate_plan(payload: dict[str, Any], *, reel_count: int) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise ValueError("Reel-pack planner response must be an object")
    records = payload.get("reels")
    if not isinstance(records, list) or len(records) != reel_count:
        raise ValueError(f"Planner must return exactly {reel_count} Reel briefs")
    normalized = [
        normalize_brief(record, expected_id=reel_id(index))
        for index, record in enumerate(records, start=1)
    ]
    fingerprints: set[tuple[str, str]] = set()
    for brief in normalized:
        fingerprint = (
            brief["hook"].lower().strip(),
            brief["learning_payoff"].lower().strip(),
        )
        if fingerprint in fingerprints:
            raise ValueError("Reel-pack planner returned duplicate hook/payoff pairs")
        fingerprints.add(fingerprint)
    return normalized


def validate_script(raw: dict[str, Any], *, brief: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"{brief['reel_id']} script must be an object")
    reel = require_reel_id(str(raw.get("reel_id") or brief["reel_id"]))
    if reel != brief["reel_id"]:
        raise ValueError(f"Script ID mismatch for {brief['reel_id']}")
    narration = str(raw.get("narration") or "").strip()
    if not narration:
        raise ValueError(f"{reel} narration is empty")
    forbidden = (
        "previous reel",
        "next reel",
        "as we saw before",
        "continuing from",
        "in part ",
        "in the last video",
    )
    lowered = narration.lower()
    if any(phrase in lowered for phrase in forbidden):
        raise ValueError(f"{reel} depends on another Reel and is not standalone")
    target_duration = bounded_duration(raw.get("target_duration_seconds", brief["target_duration_seconds"]))
    validation_warnings = list(brief.get("validation_warnings") or [])
    raw_beats = raw.get("beats")
    if not isinstance(raw_beats, list):
        raise ValueError(f"{reel} script must contain a beats array")
    expected_beats = list(brief.get("beats") or [])
    expected_ids = [str(item["id"]) for item in expected_beats]
    received_ids = [str(item.get("id") or "") for item in raw_beats if isinstance(item, dict)]
    if received_ids != expected_ids:
        raise ValueError(f"{reel} script beat IDs must exactly match the approved blueprint")
    merged_beats = []
    for blueprint, scripted in zip(expected_beats, raw_beats):
        spoken_text = str(scripted.get("spoken_text") or "").strip()
        delivery = str(scripted.get("delivery") or "curious").strip()
        if not spoken_text:
            raise ValueError(f"{reel} beat {blueprint['id']} has no spoken_text")
        merged_beats.append({**blueprint, "spoken_text": spoken_text, "delivery": delivery})
    beat_narration = " ".join(item["spoken_text"] for item in merged_beats).strip()
    if " ".join(beat_narration.split()) != " ".join(narration.split()):
        validation_warnings.append(
            f"{reel} narration differed from its beat spoken_text values; "
            "the beat text was used as the canonical narration"
        )
        narration = beat_narration
    word_count = len(narration.split())
    minimum_words = round(target_duration * 2.0)
    maximum_words = round(target_duration * 2.7)
    if not minimum_words <= word_count <= maximum_words:
        validation_warnings.append(
            f"{reel} has {word_count} words; expected {minimum_words}-{maximum_words} "
            f"for a {target_duration:g}-second Reel"
        )
    return {
        "reel_id": reel,
        "title": str(raw.get("title") or brief["working_title"]).strip(),
        "hook": str(raw.get("hook") or brief["hook"]).strip(),
        "narration": narration,
        "narration_word_count": word_count,
        "closing_line": str(raw.get("closing_line") or "").strip(),
        "visual_direction": str(raw.get("visual_direction") or brief["visual_concept"]).strip(),
        "beats": merged_beats,
        "fact_ids": brief["fact_ids"],
        "objective_ids": brief["objective_ids"],
        "target_duration_seconds": target_duration,
        "validation_warnings": validation_warnings,
        "status": "scripted",
    }


def status_summary(pack: dict[str, Any]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for record in pack.get("reels", []):
        status = str(record.get("status") or "planned")
        summary[status] = summary.get(status, 0) + 1
    return summary
