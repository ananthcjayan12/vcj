"""Validation helpers for independent standalone topic Reel packs."""
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
        "target_duration_seconds": bounded_duration(
            raw.get("target_duration_seconds", DEFAULT_DURATION_SECONDS)
        ),
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
    # Narration length is a soft production target, not a schema gate. Natural
    # wording can run longer or shorter than the target; generated audio and
    # derived timing are the source of truth for the final Reel duration.
    word_count = len(narration.split())
    return {
        "reel_id": reel,
        "title": str(raw.get("title") or brief["working_title"]).strip(),
        "hook": str(raw.get("hook") or brief["hook"]).strip(),
        "narration": narration,
        "narration_word_count": word_count,
        "closing_line": str(raw.get("closing_line") or "").strip(),
        "visual_direction": str(raw.get("visual_direction") or brief["visual_concept"]).strip(),
        "fact_ids": brief["fact_ids"],
        "objective_ids": brief["objective_ids"],
        "target_duration_seconds": bounded_duration(
            raw.get("target_duration_seconds", brief["target_duration_seconds"])
        ),
        "status": "scripted",
    }


def status_summary(pack: dict[str, Any]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for record in pack.get("reels", []):
        status = str(record.get("status") or "planned")
        summary[status] = summary.get(status, 0) + 1
    return summary
