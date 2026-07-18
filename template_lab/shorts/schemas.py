from __future__ import annotations

import re
from typing import Any

from .constants import (ARCHETYPES, DEPENDENT_PHRASES, MAX_SHORT_DURATION,
                        MAX_SOURCE_REELS, MIN_SHORT_DURATION, SCORE_WEIGHTS)


class ShortsValidationError(ValueError):
    pass


def words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)?", text.lower())


def claim_ids(parent: dict[str, Any]) -> set[str]:
    found: set[str] = set()
    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "claim_ids" and isinstance(child, list):
                    found.update(map(str, child))
                else: walk(child)
        elif isinstance(value, list):
            for child in value: walk(child)
    walk(parent)
    return found


def validate_candidate(item: dict[str, Any], known_claims: set[str]) -> dict[str, Any]:
    if item.get("archetype") not in ARCHETYPES:
        raise ShortsValidationError("Unsupported Short archetype")
    text = " ".join(str(item.get(k, "")) for k in ("hook", "promise", "payoff")).lower()
    if any(phrase in text for phrase in DEPENDENT_PHRASES):
        raise ShortsValidationError("Candidate depends on previous lesson context")
    unknown = set(map(str, item.get("claim_ids") or [])) - known_claims
    if unknown: raise ShortsValidationError(f"Unknown claim IDs: {', '.join(sorted(unknown))}")
    reels = [str(s.get("reel_id")) for s in item.get("source_segments") or []]
    if len(set(reels)) > MAX_SOURCE_REELS: raise ShortsValidationError("A Short may use at most two reels")
    scores = item.get("scores") or {}
    for key in SCORE_WEIGHTS:
        value = float(scores.get(key, 0))
        if not 0 <= value <= 100: raise ShortsValidationError(f"{key} must be within 0–100")
    scores["overall_score"] = round(sum(float(scores[k]) * w for k, w in SCORE_WEIGHTS.items()))
    item["scores"] = scores
    return item


def validate_script(script: dict[str, Any], known_claims: set[str]) -> dict[str, Any]:
    lines = script.get("lines") or []
    if not lines: raise ShortsValidationError("Short script has no lines")
    roles = {str(line.get("role")) for line in lines}
    if "hook" not in roles: raise ShortsValidationError("Short script has no hook")
    if not roles.intersection({"payoff", "answer", "reveal"}): raise ShortsValidationError("Short script has no payoff")
    all_text = " ".join(str(line.get("text", "")) for line in lines)
    if len(words(all_text)) > 170: raise ShortsValidationError("Short script exceeds 170 spoken words")
    if any(p in all_text.lower() for p in DEPENDENT_PHRASES): raise ShortsValidationError("Script uses dependent chapter language")
    duration = float(script.get("target_duration_seconds", 0))
    if not MIN_SHORT_DURATION <= duration <= MAX_SHORT_DURATION: raise ShortsValidationError("Duration must be 20–60 seconds")
    unknown = set(map(str, script.get("claim_ids") or [])) - known_claims
    if unknown: raise ShortsValidationError(f"Unknown claim IDs: {', '.join(sorted(unknown))}")
    for line in lines:
        if line.get("audio_source") == "reuse" and not (line.get("source_paragraph_id") and line.get("source_word_start") is not None and line.get("source_word_end") is not None):
            raise ShortsValidationError(f"Reusable line {line.get('line_id')} has no source range")
    return script
