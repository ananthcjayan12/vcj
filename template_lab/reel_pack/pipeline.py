"""Additive standalone Reel-pack pipeline.

The long-form lesson pipeline remains the default and is not imported or invoked
by this module unless shared low-level Motion Canvas utilities are needed.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import (
    CONTENT_PRODUCT,
    DEFAULT_REEL_COUNT,
    RENDER_PROFILE,
    create_pack,
    load_pack,
    pack_path,
    read_json,
    reel_path,
    write_json_file,
)
from .planning import derive_pack_timing, generate_pack_audio, plan_pack, write_scripts
from .review import approve_reel, reject_reel, restore_reel, screen_pack
from .schema import require_reel_id
from .visuals import generate_visual_sources, render_pack, validate_visuals


def publishing_manifest(run_path: Path) -> dict[str, Any]:
    pack = load_pack(run_path)
    payload = {
        "version": "1.0",
        "content_product": CONTENT_PRODUCT,
        "topic": pack.get("topic"),
        "topic_ref": pack.get("topic_ref"),
        "render_profile": RENDER_PROFILE,
        "reels": [],
    }
    narration = read_json(run_path / "narration.json", {}) or {}
    scripts = {str(item.get("id")): item for item in narration.get("paragraphs", [])}
    manifest = read_json(run_path / "motion_canvas" / "manifest.json", {}) or {}
    for record in pack["reels"]:
        script = scripts.get(record["reel_id"], {})
        output = run_path / "motion_canvas" / "renders" / f"{record['reel_id']}.mp4"
        payload["reels"].append({
            "reel_id": record["reel_id"],
            "title": script.get("title") or record.get("working_title"),
            "video": str(output.relative_to(run_path)) if output.exists() else None,
            "status": record.get("status"),
            "fact_ids": record.get("fact_ids", []),
            "objective_ids": record.get("objective_ids", []),
            "timeline": next((item for item in manifest.get("reels", []) if item.get("scene_id") == record["reel_id"]), None),
        })
    write_json_file(run_path / "publishing_manifest.json", payload)
    return payload


def run_pack_step(
    run_path: Path,
    *,
    step: int,
    allow_model_call: bool,
    force: bool = False,
    target_reel_id: str | None = None,
    audio_provider: str | None = None,
    workers: int = 1,
    auto_repair: bool = True,
    render_all: bool = False,
) -> dict[str, Any]:
    if target_reel_id:
        require_reel_id(target_reel_id)
    if step == 1:
        return load_pack(run_path)
    if step == 2:
        plan_pack(run_path, allow_model_call=allow_model_call, force=force)
        return write_scripts(run_path, allow_model_call=allow_model_call, force=force)
    if step == 3:
        return generate_pack_audio(
            run_path,
            audio_provider=audio_provider,
            force=force,
            workers=workers,
            target_reel_id=target_reel_id,
        )
    if step == 4:
        return derive_pack_timing(run_path, force=force, target_reel_id=target_reel_id)
    if step == 5:
        return generate_visual_sources(
            run_path,
            allow_model_call=allow_model_call,
            force=force,
            target_reel_id=target_reel_id,
        )
    if step == 6:
        return validate_visuals(
            run_path,
            target_reel_id=target_reel_id,
            allow_model_call=allow_model_call,
        )
    if step == 7:
        return screen_pack(run_path, allow_repairs=auto_repair)
    if step == 8:
        result = render_pack(
            run_path,
            target_reel_id=target_reel_id,
            render_all=render_all,
        )
        publishing_manifest(run_path)
        return result
    raise ValueError(f"Unknown Reel-pack step: {step}")


__all__ = [
    "CONTENT_PRODUCT",
    "DEFAULT_REEL_COUNT",
    "approve_reel",
    "reject_reel",
    "restore_reel",
    "create_pack",
    "load_pack",
    "pack_path",
    "publishing_manifest",
    "run_pack_step",
]
