from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ALLOWED_PARENT_FILES = ("input.json", "narration.json", "story_skeleton.json")


def _read(path: Path, *, required: bool = True) -> dict[str, Any]:
    if not path.exists():
        if required:
            raise FileNotFoundError(path)
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected a JSON object: {path}")
    return value


def _claims(input_payload: dict[str, Any]) -> list[dict[str, Any]]:
    facts = input_payload.get("facts")
    if isinstance(facts, dict):
        for key in ("claims", "grounded_claims", "facts"):
            value = facts.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    if isinstance(facts, list):
        return [item for item in facts if isinstance(item, dict)]
    return []


def load_parent_source(parent_run_path: Path) -> dict[str, Any]:
    """Load an allowlisted factual source without touching parent visual artifacts."""
    parent_run_path = parent_run_path.resolve()
    input_payload = _read(parent_run_path / "input.json")
    narration = _read(parent_run_path / "narration.json")
    story = _read(parent_run_path / "story_skeleton.json", required=False)
    paragraphs = narration.get("paragraphs") or []
    if not paragraphs or not all(isinstance(item, dict) and item.get("id") and item.get("text") for item in paragraphs):
        raise RuntimeError("Parent narration must contain approved paragraphs with ids and text")
    claims = _claims(input_payload)
    claim_ids = []
    for item in claims:
        value = item.get("claim_id") or item.get("id")
        if value:
            claim_ids.append(str(value))
    return {
        "parent_run_id": str(input_payload.get("run_id") or parent_run_path.name),
        "topic": str(input_payload.get("topic") or narration.get("title") or "Physics lesson"),
        "audience": str(input_payload.get("audience") or "Cambridge IGCSE Physics students aged 14–16"),
        "narration": narration,
        "story_skeleton": story,
        "grounded_facts": input_payload.get("facts") or {},
        "claim_ids": list(dict.fromkeys(claim_ids)),
        "paragraph_ids": [str(item["id"]) for item in paragraphs],
    }
