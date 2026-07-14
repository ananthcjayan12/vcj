from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mav_schema import LAB_ROOT

DEFAULT_INPUT_PATH = LAB_ROOT / "input" / "facts.json"


def read_facts_payload(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return {"facts": payload}
    if isinstance(payload, dict) and isinstance(payload.get("facts"), list):
        return payload
    raise ValueError(f"{path} must be a JSON list or an object with a facts list")


def facts_from_file(path: Path) -> list[dict[str, str]]:
    return read_facts_payload(path)["facts"]


def read_pipeline_inputs(path: Path | None = None) -> dict[str, Any]:
    """Read a repo-local educational facts packet.

    Pass ``--facts`` explicitly, or place a packet at
    ``template_lab/input/facts.json``. A packet may also supply topic and tone.
    """
    input_path = (path or DEFAULT_INPUT_PATH).expanduser().resolve()
    if not input_path.exists():
        raise FileNotFoundError(
            "No facts packet was supplied. Pass --facts path/to/facts.json or "
            f"create {DEFAULT_INPUT_PATH}."
        )
    payload = read_facts_payload(input_path)
    topic = str(payload.get("topic", "")).strip()
    if not topic:
        raise ValueError(f"{input_path} must include a non-empty top-level topic when used as the default input")
    return {
        "topic": topic,
        "tone": str(payload.get("tone") or "patient, precise IGCSE Physics teacher"),
        "facts": payload["facts"],
        "narrative_mode": str(payload.get("narrative_mode") or "concept_mastery"),
        "source": str(input_path),
    }
