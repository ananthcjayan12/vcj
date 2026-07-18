from __future__ import annotations

from typing import Any


STRING = {"type": "string"}
STRING_ARRAY = {"type": "array", "items": STRING}

CANDIDATES_SCHEMA = {
    "type": "object", "required": ["candidates"],
    "properties": {"candidates": {"type": "array", "minItems": 3, "maxItems": 5, "items": {
        "type": "object", "required": ["id", "title", "idea", "opening", "ending", "source_paragraph_ids", "source_claim_ids"],
        "properties": {"id": STRING, "title": STRING, "idea": STRING, "opening": STRING, "ending": STRING,
                       "source_paragraph_ids": STRING_ARRAY, "source_claim_ids": STRING_ARRAY},
    }}},
}

TREATMENT_SCHEMA = {
    "type": "object", "required": ["title", "treatment", "source_paragraph_ids", "source_claim_ids"],
    "properties": {"title": STRING, "treatment": STRING, "source_paragraph_ids": STRING_ARRAY, "source_claim_ids": STRING_ARRAY},
}

NARRATION_SCHEMA = {
    "type": "object", "required": ["title", "target_duration_seconds", "spoken_word_count", "paragraphs", "source_claim_ids", "elevenlabs_narration"],
    "properties": {
        "title": STRING, "target_duration_seconds": {"type": "number"}, "spoken_word_count": {"type": "integer"},
        "paragraphs": {"type": "array", "minItems": 3, "maxItems": 9, "items": {
            "type": "object", "required": ["id", "text"], "properties": {"id": STRING, "text": STRING},
        }},
        "source_claim_ids": STRING_ARRAY, "elevenlabs_narration": STRING,
    },
}

SHOT_PLAN_SCHEMA = {
    "type": "object", "required": ["shots"],
    "properties": {"shots": {"type": "array", "minItems": 1, "items": {
        "type": "object", "required": ["id", "narration_paragraph_ids", "description"],
        "properties": {"id": STRING, "narration_paragraph_ids": STRING_ARRAY, "description": STRING},
    }}},
}


def validate_candidates(payload: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not 3 <= len(candidates) <= 5:
        raise RuntimeError("Reel analysis must return 3–5 candidates")
    ids = set()
    for index, item in enumerate(candidates, 1):
        if not isinstance(item, dict):
            raise RuntimeError("Every Reel candidate must be an object")
        item["id"] = f"candidate_{index:02d}"
        if not all(str(item.get(key) or "").strip() for key in ("title", "idea", "opening", "ending")):
            raise RuntimeError(f"{item['id']} is missing useful creative text")
        if item["id"] in ids:
            raise RuntimeError("Duplicate Reel candidate id")
        ids.add(item["id"])
        _validate_sources(item, source)
    return payload


def _validate_sources(payload: dict[str, Any], source: dict[str, Any]) -> None:
    unknown_paragraphs = set(payload.get("source_paragraph_ids") or []) - set(source["paragraph_ids"])
    unknown_claims = set(payload.get("source_claim_ids") or []) - set(source["claim_ids"])
    if unknown_paragraphs:
        raise RuntimeError(f"Unsupported parent paragraph ids: {sorted(unknown_paragraphs)}")
    if unknown_claims:
        raise RuntimeError(f"Unsupported grounded claim ids: {sorted(unknown_claims)}")


def validate_treatment(payload: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    if not str(payload.get("title") or "").strip() or len(str(payload.get("treatment") or "").split()) < 25:
        raise RuntimeError("Reel treatment is missing or too shallow")
    _validate_sources(payload, source)
    return payload


def validate_narration(payload: dict[str, Any], source: dict[str, Any], *, maximum_words: int = 150) -> dict[str, Any]:
    paragraphs = payload.get("paragraphs") or []
    if not 3 <= len(paragraphs) <= 9:
        raise RuntimeError("Reel narration must contain 3–9 paragraphs")
    for index, paragraph in enumerate(paragraphs, 1):
        expected = f"paragraph_{index:02d}"
        if not isinstance(paragraph, dict) or paragraph.get("id") != expected or not str(paragraph.get("text") or "").strip():
            raise RuntimeError(f"Reel narration paragraph ids must be sequential; expected {expected}")
    spoken = " ".join(str(item["text"]) for item in paragraphs)
    word_count = len(spoken.replace("[", " ").replace("]", " ").split())
    if word_count > maximum_words:
        raise RuntimeError(f"Reel narration exceeds {maximum_words} words")
    payload["spoken_word_count"] = word_count
    payload["elevenlabs_narration"] = spoken
    unknown_claims = set(payload.get("source_claim_ids") or []) - set(source["claim_ids"])
    if unknown_claims:
        raise RuntimeError(f"Unsupported grounded claim ids: {sorted(unknown_claims)}")
    return payload


def validate_shot_plan(payload: dict[str, Any], timeline: dict[str, Any]) -> dict[str, Any]:
    shots = payload.get("shots") or []
    expected = [str(item["scene_id"]) for item in timeline.get("shots") or []]
    actual = [str(item.get("id")) for item in shots]
    if actual != expected:
        raise RuntimeError(f"Shot plan must preserve immutable shot ids and order: {expected}")
    for item in shots:
        if len(str(item.get("description") or "").split()) < 12:
            raise RuntimeError(f"{item.get('id')} needs a detailed visual description")
    return payload
