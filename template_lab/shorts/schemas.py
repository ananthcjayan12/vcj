from __future__ import annotations

import re
from typing import Any

from .constants import (ARCHETYPES, DEPENDENT_PHRASES, MAX_SHORT_DURATION,
                        MAX_SOURCE_REELS, MIN_SHORT_DURATION, SCORE_WEIGHTS)


class ShortsValidationError(ValueError):
    pass


SCRIPT_ROLES = {
    "hook", "setup", "context", "tension", "prediction", "explanation",
    "evidence", "payoff", "answer", "reveal", "loop",
}


def words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)?", text.lower())


def claim_ids(parent: dict[str, Any]) -> set[str]:
    found: set[str] = set()
    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "claim_ids" and isinstance(child, list):
                    found.update(map(str, child))
                else:
                    walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(parent)
    return found


def validate_candidate(item: dict[str, Any], known_claims: set[str]) -> dict[str, Any]:
    if item.get("archetype") not in ARCHETYPES:
        raise ShortsValidationError("Unsupported Short archetype")
    text = " ".join(str(item.get(k, "")) for k in ("hook", "promise", "payoff")).lower()
    if any(phrase in text for phrase in DEPENDENT_PHRASES):
        raise ShortsValidationError("Candidate depends on previous lesson context")
    unknown = set(map(str, item.get("claim_ids") or [])) - known_claims
    if unknown and known_claims:
        raise ShortsValidationError(f"Unknown claim IDs: {', '.join(sorted(unknown))}")
    reels = [str(s.get("reel_id")) for s in item.get("source_segments") or []]
    if len(set(reels)) > MAX_SOURCE_REELS:
        raise ShortsValidationError("A Short may use at most two reels")
    scores = item.get("scores") or {}
    for key in SCORE_WEIGHTS:
        value = float(scores.get(key, 0))
        if not 0 <= value <= 100:
            raise ShortsValidationError(f"{key} must be within 0–100")
    scores["overall_score"] = round(sum(float(scores[k]) * w for k, w in SCORE_WEIGHTS.items()))
    item["scores"] = scores
    return item


def validate_script(script: dict[str, Any], known_claims: set[str], *, candidate_claims: set[str] | None = None) -> dict[str, Any]:
    lines = script.get("lines") or []
    if not lines:
        raise ShortsValidationError("Short script has no lines")
    line_ids = [str(line.get("line_id") or "") for line in lines]
    if any(not lid for lid in line_ids):
        raise ShortsValidationError("Every script line needs a line_id")
    if len(set(line_ids)) != len(line_ids):
        raise ShortsValidationError("Script line_ids must be unique")
    roles = {str(line.get("role")) for line in lines}
    if "hook" not in roles:
        raise ShortsValidationError("Short script has no hook")
    if not roles.intersection({"payoff", "answer", "reveal"}):
        raise ShortsValidationError("Short script has no payoff")
    unsupported = roles - SCRIPT_ROLES
    if unsupported:
        raise ShortsValidationError(f"Unsupported script roles: {', '.join(sorted(unsupported))}")
    all_text = " ".join(str(line.get("text", "")) for line in lines)
    if len(words(all_text)) > 170:
        raise ShortsValidationError("Short script exceeds 170 spoken words")
    if any(p in all_text.lower() for p in DEPENDENT_PHRASES):
        raise ShortsValidationError("Script uses dependent chapter language")
    banned = ("today we will", "in this video", "in this short", "follow for more", "like and subscribe")
    if any(p in all_text.lower() for p in banned):
        raise ShortsValidationError("Script uses generic intro/CTA language")
    duration = float(script.get("target_duration_seconds", 0))
    if not MIN_SHORT_DURATION <= duration <= MAX_SHORT_DURATION:
        raise ShortsValidationError("Duration must be 20–60 seconds")
    unknown = set(map(str, script.get("claim_ids") or [])) - known_claims
    if unknown and known_claims:
        raise ShortsValidationError(f"Unknown claim IDs: {', '.join(sorted(unknown))}")
    allowed_line_claims = set(map(str, candidate_claims or script.get("claim_ids") or []))
    for line in lines:
        role = str(line.get("role") or "")
        if role not in SCRIPT_ROLES:
            raise ShortsValidationError(f"Unsupported role on {line.get('line_id')}")
        line_claims = set(map(str, line.get("claim_ids") or []))
        if known_claims and line_claims - known_claims:
            raise ShortsValidationError(f"Unknown claim IDs on {line.get('line_id')}")
        if allowed_line_claims and line_claims - allowed_line_claims:
            raise ShortsValidationError(f"Line {line.get('line_id')} introduces claims outside the candidate")
        if line.get("audio_source") == "reuse":
            has_range = line.get("source_paragraph_id") and line.get("source_word_start") is not None and line.get("source_word_end") is not None
            if not has_range and not line.get("clause_id"):
                raise ShortsValidationError(f"Reusable line {line.get('line_id')} has no source range or clause_id")
        elif line.get("audio_source") not in {"generate", "reuse"}:
            raise ShortsValidationError(f"Line {line.get('line_id')} has invalid audio_source")
    explanatory = roles.intersection({"explanation", "evidence", "setup", "tension", "context", "prediction"})
    if not explanatory and len(lines) < 3:
        raise ShortsValidationError("Script needs more than a hook and payoff")
    return script
