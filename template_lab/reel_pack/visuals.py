from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

from .common import (
    CANVAS,
    CONTENT_PRODUCT,
    INTERNAL_SCENE_ID,
    PROMPT_ROOT,
    RENDER_PROFILE,
    RUNTIME_ROOT,
    active_narration,
    active_reels,
    extract_marked_source,
    load_pack,
    read_json,
    reel_path,
    save_pack,
    write_json_file,
    write_text,
)
from .schema import require_reel_id

from mav_models import call_model_text
from motion_canvas import pipeline as motion_pipeline
from motion_canvas.lesson_review import extract_visual_contract


def prepare_child(run_path: Path, record: dict[str, Any], *, force: bool) -> tuple[Path, dict[str, Any]]:
    parent_id = record["reel_id"]
    child = reel_path(run_path, parent_id)
    manifest_path = child / "motion_canvas" / "manifest.json"
    narration = read_json(child / "narration.json", {}) or {}
    manifest = (
        read_json(manifest_path, {}) or {}
        if manifest_path.exists() and not force
        else motion_pipeline.prepare(child, narration, batch_size=1)
    )
    manifest.update({
        "content_product": CONTENT_PRODUCT,
        "standalone": True,
        "standalone_reel_id": parent_id,
        "parent_pack_run_id": run_path.name,
        "render_profile": RENDER_PROFILE,
        "canvas": CANVAS,
    })
    write_json_file(manifest_path, manifest)
    return child, manifest


def visual_user_prompt(
    run_path: Path,
    child: Path,
    record: dict[str, Any],
    manifest: dict[str, Any],
    *,
    current_source: str | None = None,
    repair_findings: list[dict[str, Any]] | None = None,
) -> str:
    child_input = read_json(child / "input.json", {}) or {}
    brief = read_json(child / "brief.json", {}) or record
    script = read_json(child / "script.json", {}) or {}
    narration = read_json(child / "narration.json", {}) or {}
    unit = list(manifest.get("reels") or manifest.get("chapters") or [])[0]
    directory = "reels" if manifest.get("timeline_mode") == "immutable_reels" else "chapters"
    cues_path = child / "motion_canvas" / directory / f"{INTERNAL_SCENE_ID}.cues.ts"
    approved = (Path(motion_pipeline.__file__).with_name("prompts") / "approved-api.md").read_text(encoding="utf-8")
    payload = {
        "parent_reel_id": record["reel_id"],
        "internal_scene_id": INTERNAL_SCENE_ID,
        "topic": child_input.get("topic"),
        "topic_ref": child_input.get("topic_ref"),
        "brief": brief,
        "script": script,
        "narration": narration,
        "grounded_facts": child_input.get("facts", []),
        "physics_context": child_input.get("physics_context", {}),
        "fixed_timeline_unit": unit,
        "exact_cues_module": cues_path.read_text(encoding="utf-8") if cues_path.exists() else "",
        "canvas": CANVAS,
    }
    prompt = (
        f"Return exactly this marker followed by one complete file:\n=== {INTERNAL_SCENE_ID}.tsx ===\n\n"
        f"APPROVED API\n{approved}\n\n"
        f"STANDALONE REEL PAYLOAD\n{json.dumps(payload, ensure_ascii=False)}"
    )
    if current_source is not None:
        prompt += (
            "\n\nPROVEN RENDERED FINDINGS\n"
            + json.dumps(repair_findings or [], indent=2, ensure_ascii=False)
            + "\n\nCURRENT SOURCE\n"
            + current_source
        )
    return prompt


def generate_visual_sources(
    run_path: Path,
    *,
    allow_model_call: bool,
    force: bool = False,
    target_reel_id: str | None = None,
    model_call: Any = call_model_text,
) -> dict[str, Any]:
    pack = load_pack(run_path)
    narration = active_narration(read_json(run_path / "narration.json", {}) or {}, pack)
    if not narration:
        raise RuntimeError("Shared Reel-pack narration.json is missing")
    manifest_path = run_path / "motion_canvas" / "manifest.json"
    manifest = (
        read_json(manifest_path, {}) or {}
        if manifest_path.exists() and not force
        else motion_pipeline.prepare(run_path, narration, batch_size=int(pack.get("visual_batch_size", 2)))
    )
    manifest.update({"content_product": CONTENT_PRODUCT, "standalone": True, "render_profile": RENDER_PROFILE, "canvas": CANVAS})
    write_json_file(manifest_path, manifest)
    report = motion_pipeline.generate(
        run_path,
        manifest,
        allow_model_call=allow_model_call,
        force=force,
        workers=max(1, min(int(pack.get("workers", 2)), 3)),
        model_call=model_call,
        target_chapter_id=target_reel_id,
    )
    failed = {str(item.get("id")) for item in report.get("failures", [])}
    for record in active_reels(pack):
        record["status"] = "failed" if record["reel_id"] in failed else "visual_ready"
    pack["status"] = "partial" if failed else "visuals_ready"
    pack["current_step"] = max(int(pack.get("current_step", 4)), 5)
    save_pack(run_path, pack)
    if failed:
        raise RuntimeError("; ".join(str(item) for item in report.get("failures", [])))
    return pack


def runtime_env(child: Path, manifest: dict[str, Any]) -> dict[str, str]:
    env = os.environ.copy()
    width = int((manifest.get("canvas") or {}).get("width") or CANVAS["width"])
    height = int((manifest.get("canvas") or {}).get("height") or CANVAS["height"])
    env.update({
        "MAV_MOTION_RUN_ROOT": str((child / "motion_canvas").resolve()),
        "MAV_MOTION_CANVAS_WIDTH": str(width),
        "MAV_MOTION_CANVAS_HEIGHT": str(height),
        "VITE_MAV_CANVAS_WIDTH": str(width),
        "VITE_MAV_CANVAS_HEIGHT": str(height),
    })
    node_bin = motion_pipeline._modern_node_bin()
    if node_bin:
        env["PATH"] = str(node_bin) + os.pathsep + env.get("PATH", "")
    return env


def npm(child: Path, manifest: dict[str, Any], script: str, timeout: int) -> dict[str, Any]:
    result = subprocess.run(
        ["npm", "run", script],
        cwd=RUNTIME_ROOT,
        env=runtime_env(child, manifest),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return {
        "script": script,
        "returncode": result.returncode,
        "stdout": result.stdout[-12_000:],
        "stderr": result.stderr[-12_000:],
    }


def validate_visuals(run_path: Path, *, target_reel_id: str | None = None) -> dict[str, Any]:
    pack = load_pack(run_path)
    manifest = read_json(run_path / "motion_canvas" / "manifest.json", {}) or {}
    if not manifest:
        raise RuntimeError("Shared Motion Canvas manifest is missing")
    try:
        validation = motion_pipeline.validate_and_assemble(run_path, manifest, allow_model_repair=False, max_model_repairs=0)
    except Exception as exc:
        if target_reel_id:
            for record in pack["reels"]:
                if record["reel_id"] == require_reel_id(target_reel_id):
                    record["status"] = "failed"
                    record["error"] = str(exc)
        pack["status"] = "partial"
        save_pack(run_path, pack)
        raise
    for record in active_reels(pack):
        if not target_reel_id or record["reel_id"] == require_reel_id(target_reel_id):
            record["status"] = "visual_ready"
            record.pop("error", None)
    pack["status"] = "visuals_ready"
    pack["current_step"] = max(int(pack.get("current_step", 5)), 6)
    write_json_file(run_path / "validation-report.json", validation)
    save_pack(run_path, pack)
    return pack


def repair_visual(
    run_path: Path,
    record: dict[str, Any],
    findings: list[dict[str, Any]],
    *,
    model_call: Any = call_model_text,
) -> None:
    parent_id = record["reel_id"]
    child = reel_path(run_path, parent_id)
    manifest = read_json(child / "motion_canvas" / "manifest.json", {}) or {}
    unit = list(manifest.get("reels") or manifest.get("chapters") or [])[0]
    source_path = motion_pipeline._unit_path(child / "motion_canvas", str(unit["scene_id"]), ".tsx", manifest)
    previous = source_path.read_text(encoding="utf-8")
    response = model_call(
        task="motion_canvas_repair",
        system=(PROMPT_ROOT / "reel_repair.system.txt").read_text(encoding="utf-8"),
        user=visual_user_prompt(
            run_path, child, record, manifest,
            current_source=previous, repair_findings=findings,
        ),
        max_tokens=64_000,
    )
    if not response:
        raise RuntimeError("Standalone Reel repair model returned no response")
    write_text(child / "motion_canvas" / "responses" / f"screen-repair-{time.time_ns()}.txt", response)
    source = extract_marked_source(response, INTERNAL_SCENE_ID)
    source = motion_pipeline._normalize_chapter_source(source)
    source = motion_pipeline._enforce_manifest_duration(source, unit)
    motion_pipeline._validate_chapter_source(source, str(unit["scene_id"]))
    motion_pipeline._validate_cue_references(child / "motion_canvas", source, str(unit["scene_id"]))
    contract, warnings = extract_visual_contract(source, parent_id)
    if warnings or not contract:
        raise RuntimeError("; ".join(warnings) or "Repaired Reel omitted MAV_VISUAL_CONTRACT")
    write_text(source_path, source)
    try:
        validate_visuals(run_path, target_reel_id=parent_id)
    except Exception:
        write_text(source_path, previous)
        motion_pipeline.assemble(child, manifest)
        raise


def render_pack(run_path: Path, *, target_reel_id: str | None = None, render_all: bool = False) -> dict[str, Any]:
    pack = load_pack(run_path)
    errors = []
    for record in pack["reels"]:
        parent_id = record["reel_id"]
        if target_reel_id and parent_id != require_reel_id(target_reel_id):
            continue
        if not render_all and record.get("status") not in {"approved", "rendered"}:
            continue
        try:
            from mav_render import render_reel_mp4
            final = render_reel_mp4(run_path.name, parent_id)
            if not final.exists():
                raise RuntimeError(f"Portrait renderer did not produce {parent_id}.mp4")
            record["status"] = "rendered"
            record["output"] = str(final.relative_to(run_path))
        except Exception as exc:
            record["status"] = "failed"
            record["error"] = str(exc)
            errors.append(f"{parent_id}: {exc}")
    rendered = sum(item.get("status") == "rendered" for item in pack["reels"])
    active_count = sum(item.get("status") != "rejected" for item in pack["reels"])
    pack["status"] = "complete" if rendered == active_count else "partial" if errors else "approved"
    pack["current_step"] = max(int(pack.get("current_step", 7)), 8)
    save_pack(run_path, pack)
    if errors:
        raise RuntimeError("; ".join(errors))
    return pack
