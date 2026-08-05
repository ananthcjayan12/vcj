from __future__ import annotations

import json
import os
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from .common import (
    CANVAS,
    CONTENT_PRODUCT,
    PROMPT_ROOT,
    RENDER_PROFILE,
    RUNTIME_ROOT,
    active_narration,
    active_reels,
    extract_marked_source,
    load_pack,
    read_json,
    save_pack,
    write_json_file,
    write_text,
)
from .schema import require_reel_id

from mav_models import call_model_text
from motion_canvas import pipeline as motion_pipeline
from motion_canvas.lesson_review import extract_visual_contract


def _timeline_units(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return list(manifest.get("reels") or manifest.get("chapters") or [])


def _unit_for(manifest: dict[str, Any], reel_id: str) -> dict[str, Any]:
    unit = next(
        (
            item for item in _timeline_units(manifest)
            if str(item.get("source_id") or item.get("source_paragraph_id")) == reel_id
        ),
        None,
    )
    if unit is None:
        unit = next((item for item in _timeline_units(manifest) if str(item.get("scene_id")) == reel_id), None)
    if unit is None:
        raise RuntimeError(f"Motion Canvas manifest omitted {reel_id}")
    return unit


def _paragraph_for(run_path: Path, reel_id: str) -> dict[str, Any]:
    narration = read_json(run_path / "narration.json", {}) or {}
    return next(
        (
            item for item in narration.get("paragraphs", [])
            if str(item.get("id") or item.get("reel_id")) == reel_id
        ),
        {},
    )


def _timed_beats_for(run_path: Path, reel_id: str) -> list[dict[str, Any]]:
    payload = read_json(run_path / "beat_timing.json", {}) or {}
    return list(((payload.get("reels") or {}).get(reel_id) or {}).get("beats") or [])


def visual_user_prompt(
    run_path: Path,
    record: dict[str, Any],
    manifest: dict[str, Any],
    *,
    current_source: str | None = None,
    repair_findings: list[dict[str, Any]] | None = None,
) -> str:
    parent_id = record["reel_id"]
    input_payload = read_json(run_path / "input.json", {}) or {}
    paragraph = _paragraph_for(run_path, parent_id)
    unit = _unit_for(manifest, parent_id)
    scene_id = str(unit["scene_id"])
    directory = "reels" if manifest.get("timeline_mode") == "immutable_reels" else "chapters"
    cues_path = run_path / "motion_canvas" / directory / f"{scene_id}.cues.ts"
    motion_prompt_root = Path(motion_pipeline.__file__).with_name("prompts")
    approved = (motion_prompt_root / "approved-api.md").read_text(encoding="utf-8")
    scaffold = (motion_prompt_root / "scene-template.txt").read_text(encoding="utf-8")
    fact_ids = set(record.get("fact_ids", []))
    payload = {
        "reel_id": parent_id,
        "topic": input_payload.get("topic"),
        "topic_ref": input_payload.get("topic_ref"),
        "reel_blueprint": {
            "central_question": record.get("central_question"),
            "misconception": record.get("misconception"),
            "answer": record.get("answer"),
            "continuity_entity": record.get("continuity_entity"),
            "visual_thesis": record.get("visual_thesis"),
            "beats": record.get("beats", []),
        },
        "script": paragraph,
        "timed_beats": _timed_beats_for(run_path, parent_id),
        "grounded_facts": [
            item for item in input_payload.get("facts", [])
            if not fact_ids
            or str(item.get("id") or item.get("fact_id") or item.get("claim_id")) in fact_ids
        ],
        "physics_context": input_payload.get("physics_context", {}),
        "required_scientific_relationships": record.get("required_scientific_relationships", []),
        "fixed_timeline_unit": unit,
        "exact_cues_module": cues_path.read_text(encoding="utf-8") if cues_path.exists() else "",
        "canvas": CANVAS,
    }
    prompt = (
        f"Return exactly this marker followed by one complete file:\n=== {scene_id}.tsx ===\n\n"
        f"APPROVED API\n{approved}\n\n"
        "MANDATORY SOURCE SCAFFOLD\n"
        "Start the returned file from this exact import-ownership and scene-clock structure, "
        "then adapt only the used components, exact cue filename, duration, and scene body:\n"
        f"{scaffold}\n\n"
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


def _prepare_manifest(run_path: Path, pack: dict[str, Any], *, force: bool) -> dict[str, Any]:
    narration = active_narration(read_json(run_path / "narration.json", {}) or {}, pack)
    if not narration:
        raise RuntimeError("Shared Reel-pack narration.json is missing")
    manifest_path = run_path / "motion_canvas" / "manifest.json"
    manifest = read_json(manifest_path, {}) or {} if manifest_path.exists() and not force else {}
    expected_ids = [
        str(item.get("id") or item.get("reel_id"))
        for item in narration.get("paragraphs", [])
    ]
    units = _timeline_units(manifest)
    legacy_reindexed = bool(units) and any(
        str(item.get("source_id") or item.get("source_paragraph_id") or item.get("scene_id"))
        != str(item.get("scene_id"))
        for item in units
    )
    manifest_ids = [str(item.get("scene_id")) for item in units]
    rebuild = force or not manifest or legacy_reindexed or manifest_ids != expected_ids
    if rebuild:
        if legacy_reindexed:
            stale_root = run_path / "motion_canvas" / "legacy-reindexed"
            stale_root.mkdir(parents=True, exist_ok=True)
            for source in (run_path / "motion_canvas" / "reels").glob("*.tsx"):
                destination = stale_root / source.name
                if destination.exists():
                    destination = stale_root / f"{source.stem}-{time.time_ns()}{source.suffix}"
                source.replace(destination)
            print(
                "WARNING: Rebuilt a legacy reindexed Reel manifest after a rejection; "
                f"previous mismatched TSX files were preserved in {stale_root}",
                flush=True,
            )
        manifest = motion_pipeline.prepare(run_path, narration, batch_size=1)
    manifest.update({
        "content_product": CONTENT_PRODUCT,
        "standalone": True,
        "render_profile": RENDER_PROFILE,
        "canvas": CANVAS,
        "visual_generation_mode": "reel-blueprint-v2",
    })
    write_json_file(manifest_path, manifest)
    return manifest


def _generate_one_reel(
    run_path: Path,
    record: dict[str, Any],
    manifest: dict[str, Any],
    *,
    allow_model_call: bool,
    force: bool,
    model_call: Any,
) -> list[str]:
    parent_id = record["reel_id"]
    unit = _unit_for(manifest, parent_id)
    scene_id = str(unit["scene_id"])
    source_path = motion_pipeline._unit_path(
        run_path / "motion_canvas",
        scene_id,
        ".tsx",
        manifest,
    )
    if source_path.exists() and not force:
        source = source_path.read_text(encoding="utf-8")
    else:
        if not allow_model_call:
            raise RuntimeError(f"Accepted visual source cache missing for {parent_id}")
        response = model_call(
            task="motion_canvas_batch",
            system=(PROMPT_ROOT / "reel_visual.system.txt").read_text(encoding="utf-8"),
            user=visual_user_prompt(run_path, record, manifest),
            max_tokens=64_000,
        )
        if not response:
            raise RuntimeError(f"{parent_id} visual model returned no response")
        response_path = run_path / "motion_canvas" / "responses" / f"{scene_id}.txt"
        write_text(response_path, response)
        source = extract_marked_source(response, scene_id)
    source = motion_pipeline._normalize_chapter_source(source)
    source = motion_pipeline._enforce_manifest_duration(source, unit)
    validation_warnings = motion_pipeline._validate_chapter_source(source, scene_id)
    motion_pipeline._validate_cue_references(run_path / "motion_canvas", source, scene_id)
    contract, warnings = extract_visual_contract(source, scene_id)
    if warnings or not contract:
        raise RuntimeError("; ".join(warnings) or f"{parent_id} omitted MAV_VISUAL_CONTRACT")
    write_text(source_path, source)
    return validation_warnings


def generate_visual_sources(
    run_path: Path,
    *,
    allow_model_call: bool,
    force: bool = False,
    target_reel_id: str | None = None,
    model_call: Any = call_model_text,
) -> dict[str, Any]:
    pack = load_pack(run_path)
    manifest = _prepare_manifest(run_path, pack, force=force)
    target = require_reel_id(target_reel_id) if target_reel_id else None
    records = [
        record for record in active_reels(pack)
        if target is None or record["reel_id"] == target
    ]
    failures: list[str] = []
    max_workers = max(1, min(int(pack.get("workers", 2)), 3, len(records) or 1))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_by_record = {
            executor.submit(
                _generate_one_reel,
                run_path,
                record,
                manifest,
                allow_model_call=allow_model_call,
                force=force,
                model_call=model_call,
            ): record
            for record in records
        }
        for future in as_completed(future_by_record):
            record = future_by_record[future]
            try:
                source_warnings = future.result()
                stored_warnings = record.setdefault("validation_warnings", [])
                for warning in source_warnings:
                    if warning not in stored_warnings:
                        stored_warnings.append(warning)
                    print(f"WARNING: {warning}", flush=True)
                record["status"] = "visual_ready"
                record.pop("error", None)
            except Exception as exc:
                record["status"] = "failed"
                record["error"] = str(exc)
                failures.append(f"{record['reel_id']}: {exc}")
    if not failures:
        motion_pipeline.assemble(run_path, manifest)
    pack["status"] = "partial" if failures else "visuals_ready"
    pack["current_step"] = max(int(pack.get("current_step", 4)), 5)
    save_pack(run_path, pack)
    if failures:
        for failure in failures:
            print(f"WARNING: {failure}", flush=True)
    return pack


def runtime_env(run_path: Path, manifest: dict[str, Any]) -> dict[str, str]:
    env = os.environ.copy()
    width = int((manifest.get("canvas") or {}).get("width") or CANVAS["width"])
    height = int((manifest.get("canvas") or {}).get("height") or CANVAS["height"])
    env.update({
        "MAV_MOTION_RUN_ROOT": str((run_path / "motion_canvas").resolve()),
        "MAV_MOTION_CANVAS_WIDTH": str(width),
        "MAV_MOTION_CANVAS_HEIGHT": str(height),
        "VITE_MAV_CANVAS_WIDTH": str(width),
        "VITE_MAV_CANVAS_HEIGHT": str(height),
    })
    node_bin = motion_pipeline._modern_node_bin()
    if node_bin:
        env["PATH"] = str(node_bin) + os.pathsep + env.get("PATH", "")
    return env


def npm(run_path: Path, manifest: dict[str, Any], script: str, timeout: int) -> dict[str, Any]:
    result = subprocess.run(
        ["npm", "run", script],
        cwd=RUNTIME_ROOT,
        env=runtime_env(run_path, manifest),
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


def _compiler_errors_by_reel(output: str) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for line in output.splitlines():
        match = re.search(
            r"src/generated/(?:reels|chapters)/((?:reel|chapter)_\d+)\.tsx",
            line,
        )
        if match:
            grouped.setdefault(match.group(1), []).append(line)
    return grouped


def validate_visuals(
    run_path: Path,
    *,
    target_reel_id: str | None = None,
    allow_model_call: bool = False,
    model_call: Any = call_model_text,
    max_compile_repairs: int = 3,
) -> dict[str, Any]:
    pack = load_pack(run_path)
    manifest = read_json(run_path / "motion_canvas" / "manifest.json", {}) or {}
    if not manifest:
        raise RuntimeError("Shared Motion Canvas manifest is missing")
    if target_reel_id:
        require_reel_id(target_reel_id)
    commands: list[dict[str, Any]] = []
    compile_repairs: list[dict[str, Any]] = []
    try:
        motion_pipeline.assemble(run_path, manifest)
        for attempt in range(max_compile_repairs + 1):
            motion_pipeline._sync_runtime(run_path)
            result = npm(run_path, manifest, "typecheck", 600)
            commands.append(result)
            if result["returncode"] == 0:
                break
            output = f"{result.get('stdout', '')}\n{result.get('stderr', '')}"
            grouped = _compiler_errors_by_reel(output)
            compile_repairs.append({
                "attempt": attempt + 1,
                "errors": grouped or {"runtime": [output[-12_000:]]},
            })
            if attempt >= max_compile_repairs:
                raise RuntimeError(
                    f"npm run typecheck still failed after {max_compile_repairs} Codex repair passes: "
                    f"{output[-12_000:]}"
                )
            if not allow_model_call:
                raise RuntimeError(
                    f"npm run typecheck failed and model repair is not authorized: {output[-12_000:]}"
                )
            if not grouped:
                raise RuntimeError(
                    f"npm run typecheck failed without a Reel-specific source location: {output[-12_000:]}"
                )
            for scene_id, errors in grouped.items():
                print(
                    f"TypeScript repair pass {attempt + 1}: repairing {scene_id} with motion_canvas_repair",
                    flush=True,
                )
                repair = motion_pipeline._repair_chapter_with_model(
                    run_path,
                    scene_id,
                    errors,
                    model_call=model_call,
                )
                compile_repairs[-1].setdefault("repairs", []).append(repair)
            motion_pipeline.assemble(run_path, manifest)
        else:  # pragma: no cover - the bounded loop always breaks or raises
            raise RuntimeError("TypeScript repair loop exhausted")

        motion_pipeline._sync_runtime(run_path)
        preview_result = npm(run_path, manifest, "reel-pack-preview", 900)
        commands.append(preview_result)
        if preview_result["returncode"] != 0:
            raise RuntimeError(
                "npm run reel-pack-preview failed: "
                f"{(preview_result['stderr'] or preview_result['stdout'])[-12_000:]}"
            )
        portrait_validation = read_json(run_path / "motion_canvas" / "validation.json", {}) or {}
        if portrait_validation.get("status") != "passed":
            raise RuntimeError(f"Portrait Reel validation failed: {portrait_validation}")
        validation = {
            "version": "2.0",
            "status": "passed",
            "canvas": portrait_validation.get("canvas"),
            "portrait_validation": portrait_validation,
            "commands": commands,
            "compile_repairs": compile_repairs,
        }
    except Exception as exc:
        selected = [
            record for record in pack["reels"]
            if not target_reel_id or record["reel_id"] == target_reel_id
        ]
        for record in selected:
            record["status"] = "failed"
            record["error"] = str(exc)
        pack["status"] = "partial"
        write_json_file(run_path / "validation-report.json", {
            "version": "2.0",
            "status": "failed",
            "error": str(exc),
            "commands": commands,
            "compile_repairs": compile_repairs,
        })
        write_json_file(run_path / "motion_canvas" / "robot-report.json", {
            "version": "2.0",
            "status": "failed",
            "error": str(exc),
            "commands": commands,
            "compile_repairs": compile_repairs,
        })
        save_pack(run_path, pack)
        raise
    for record in active_reels(pack):
        if not target_reel_id or record["reel_id"] == target_reel_id:
            record["status"] = "visual_ready"
            record.pop("error", None)
    pack["status"] = "visuals_ready"
    pack["current_step"] = max(int(pack.get("current_step", 5)), 6)
    write_json_file(run_path / "validation-report.json", validation)
    write_json_file(run_path / "motion_canvas" / "robot-report.json", validation)
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
    manifest = read_json(run_path / "motion_canvas" / "manifest.json", {}) or {}
    unit = _unit_for(manifest, parent_id)
    scene_id = str(unit["scene_id"])
    source_path = motion_pipeline._unit_path(run_path / "motion_canvas", scene_id, ".tsx", manifest)
    previous = source_path.read_text(encoding="utf-8")
    response = model_call(
        task="motion_canvas_repair",
        system=(PROMPT_ROOT / "reel_repair.system.txt").read_text(encoding="utf-8"),
        user=visual_user_prompt(
            run_path,
            record,
            manifest,
            current_source=previous,
            repair_findings=findings,
        ),
        max_tokens=64_000,
    )
    if not response:
        raise RuntimeError("Standalone Reel repair model returned no response")
    write_text(run_path / "motion_canvas" / "responses" / f"{parent_id}-repair-{time.time_ns()}.txt", response)
    source = extract_marked_source(response, scene_id)
    source = motion_pipeline._normalize_chapter_source(source)
    source = motion_pipeline._enforce_manifest_duration(source, unit)
    validation_warnings = motion_pipeline._validate_chapter_source(source, scene_id)
    motion_pipeline._validate_cue_references(run_path / "motion_canvas", source, scene_id)
    contract, warnings = extract_visual_contract(source, scene_id)
    if warnings or not contract:
        raise RuntimeError("; ".join(warnings) or "Repaired Reel omitted MAV_VISUAL_CONTRACT")
    write_text(source_path, source)
    stored_warnings = record.setdefault("validation_warnings", [])
    for warning in validation_warnings:
        if warning not in stored_warnings:
            stored_warnings.append(warning)
    try:
        validate_visuals(run_path, target_reel_id=parent_id)
    except Exception:
        write_text(source_path, previous)
        motion_pipeline.assemble(run_path, manifest)
        raise


def render_pack(run_path: Path, *, target_reel_id: str | None = None, render_all: bool = False) -> dict[str, Any]:
    pack = load_pack(run_path)
    errors = []
    eligible_statuses = {"visual_ready", "approved"}
    requested_target = require_reel_id(target_reel_id) if target_reel_id else None
    selected = [
        record for record in pack["reels"]
        if not requested_target or record["reel_id"] == requested_target
    ]
    if requested_target and not selected:
        raise ValueError(f"Unknown Reel: {requested_target}")
    if requested_target and selected[0].get("status") not in eligible_statuses:
        raise ValueError(
            f"{requested_target} must complete compile & preview before rendering; "
            f"current status is {selected[0].get('status')}"
        )
    attempted = 0
    for record in pack["reels"]:
        parent_id = record["reel_id"]
        if requested_target and parent_id != requested_target:
            continue
        if record.get("status") not in eligible_statuses:
            continue
        attempted += 1
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
    if not attempted and not errors:
        raise RuntimeError("No compile-ready Reels are available to render")
    rendered = sum(item.get("status") == "rendered" for item in pack["reels"])
    active_count = sum(item.get("status") != "rejected" for item in pack["reels"])
    pack["status"] = "complete" if rendered == active_count else "partial" if errors else "visuals_ready"
    pack["current_step"] = max(int(pack.get("current_step", 6)), 8)
    save_pack(run_path, pack)
    if errors:
        raise RuntimeError("; ".join(errors))
    return pack
