from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .schema import (
    CONTENT_PRODUCT,
    DEFAULT_DURATION_SECONDS,
    DEFAULT_REEL_COUNT,
    RENDER_PROFILE,
    bounded_duration,
    bounded_reel_count,
    reel_id,
    require_reel_id,
    status_summary,
)

LAB_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = LAB_ROOT / "scripts"
REPO_ROOT = LAB_ROOT.parent
RUNS_ROOT = LAB_ROOT / "runs"
PROMPT_ROOT = Path(__file__).with_name("prompts")
RUNTIME_ROOT = REPO_ROOT / "motion_canvas_runtime"
PACK_VERSION = "1.0"
INTERNAL_SCENE_ID = "reel_001"
CANVAS = {"width": 1080, "height": 1920, "fps": 30}

for candidate in (str(LAB_ROOT), str(SCRIPTS_ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_file(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".tmp-{os.getpid()}-{time.time_ns()}")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".tmp-{os.getpid()}-{time.time_ns()}")
    temporary.write_text(text.rstrip() + "\n", encoding="utf-8")
    temporary.replace(path)


def extract_json(response: str) -> dict[str, Any]:
    cleaned = response.replace("```json", "").replace("```", "").strip()
    start = cleaned.find("{")
    if start < 0:
        raise RuntimeError("Model response did not contain a JSON object")
    try:
        payload, _ = json.JSONDecoder().raw_decode(cleaned[start:])
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Model response contained invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Model response JSON must be an object")
    return payload


def extract_marked_source(response: str, marker: str) -> str:
    if "```" in response:
        raise RuntimeError("Visual model response contains Markdown fences")
    token = f"=== {marker}.tsx ==="
    if response.count(token) != 1:
        raise RuntimeError(f"Expected exactly one {token!r} marker")
    source = response.split(token, 1)[1].strip()
    if not source:
        raise RuntimeError("Visual model returned an empty TSX source")
    return source


def pack_path(run_id: str) -> Path:
    normalized = str(run_id or "").strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,95}", normalized):
        raise ValueError("Invalid Reel-pack run ID")
    return RUNS_ROOT / normalized


def reel_path(run_path: Path, parent_reel_id: str) -> Path:
    return run_path / "reels" / require_reel_id(parent_reel_id)


def load_pack(run_path: Path) -> dict[str, Any]:
    payload = read_json(run_path / "reel_pack.json")
    if not isinstance(payload, dict):
        raise RuntimeError(f"Missing Reel-pack manifest at {run_path / 'reel_pack.json'}")
    return payload


def save_pack(run_path: Path, pack: dict[str, Any]) -> dict[str, Any]:
    pack["updated_at"] = now()
    pack["summary"] = status_summary(pack)
    write_json_file(run_path / "reel_pack.json", pack)
    write_json_file(run_path / "generation_summary.json", {
        "run_id": pack["run_id"],
        "content_product": CONTENT_PRODUCT,
        "status": pack.get("status"),
        "current_step": pack.get("current_step", 0),
        "reel_count": len(pack.get("reels", [])),
        "summary": pack["summary"],
        "render_profile": RENDER_PROFILE,
    })
    return pack


def fact_id(record: Any) -> str:
    if not isinstance(record, dict):
        return ""
    return str(record.get("id") or record.get("fact_id") or record.get("claim_id") or record.get("objective_id") or "").strip()


def facts_for_brief(input_payload: dict[str, Any], brief: dict[str, Any]) -> list[dict[str, Any]]:
    facts = [item for item in input_payload.get("facts", []) if isinstance(item, dict)]
    requested = set(brief.get("fact_ids", []))
    selected = [item for item in facts if fact_id(item) in requested]
    return selected or facts


def active_reels(pack: dict[str, Any]) -> list[dict[str, Any]]:
    """Return Reels that have not been explicitly rejected by the user."""
    return [record for record in pack.get("reels", []) if record.get("status") != "rejected"]


def active_narration(narration: dict[str, Any], pack: dict[str, Any]) -> dict[str, Any]:
    """Keep script review data complete while excluding rejected Reels downstream."""
    active_ids = {str(record.get("reel_id")) for record in active_reels(pack)}
    filtered = {
        key: value for key, value in narration.items() if key != "paragraphs"
    }
    filtered["paragraphs"] = [
        paragraph for paragraph in narration.get("paragraphs", [])
        if str(paragraph.get("id") or paragraph.get("reel_id")) in active_ids
    ]
    filtered["elevenlabs_narration"] = " ".join(
        str(paragraph.get("text") or paragraph.get("narration") or "").strip()
        for paragraph in filtered["paragraphs"]
        if str(paragraph.get("text") or paragraph.get("narration") or "").strip()
    )
    return filtered


def create_pack(
    *,
    run_id: str,
    topic: str,
    topic_ref: str,
    objective_ids: list[str],
    facts: list[dict[str, Any]],
    physics_context: dict[str, Any],
    tone: str,
    reel_count: int = DEFAULT_REEL_COUNT,
    target_duration_seconds: float = DEFAULT_DURATION_SECONDS,
    audio_provider: str = "gemini",
) -> dict[str, Any]:
    run_path = pack_path(run_id)
    if run_path.exists() and any(run_path.iterdir()):
        raise FileExistsError(f"Run already exists: {run_id}")
    run_path.mkdir(parents=True, exist_ok=True)
    count = bounded_reel_count(reel_count)
    duration = bounded_duration(target_duration_seconds)
    input_payload = {
        "version": PACK_VERSION,
        "run_id": run_id,
        "content_product": CONTENT_PRODUCT,
        "animation_mode": "motion-canvas",
        "render_profile": RENDER_PROFILE,
        "canvas": CANVAS,
        "topic": str(topic).strip(),
        "topic_ref": str(topic_ref).strip(),
        "objective_ids": list(dict.fromkeys(str(item).strip() for item in objective_ids if str(item).strip())),
        "facts": facts,
        "physics_context": physics_context,
        "tone": str(tone).strip(),
        "reel_count": count,
        "target_duration_seconds": duration,
        "visual_batch_size": 2,
        "audio_provider": audio_provider,
    }
    write_json_file(run_path / "input.json", input_payload)
    pack = {
        "version": PACK_VERSION,
        "run_id": run_id,
        "content_product": CONTENT_PRODUCT,
        "status": "created",
        "current_step": 1,
        "created_at": now(),
        "render_profile": RENDER_PROFILE,
        "canvas": CANVAS,
        "topic": input_payload["topic"],
        "topic_ref": input_payload["topic_ref"],
        "target_reel_count": count,
        "visual_batch_size": 2,
        "reels": [{
            "reel_id": reel_id(index),
            "status": "planned",
            "target_duration_seconds": duration,
            "path": ".",
        } for index in range(1, count + 1)],
    }
    return save_pack(run_path, pack)
