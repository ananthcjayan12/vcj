from __future__ import annotations

from pathlib import Path
from typing import Any

from .asset_manifest import prepare_runtime_assets
from .browser_inspector import inspect_lesson
from .build_input_bundle import build_input_bundle
from .chapter_index import build_chapter_index
from .composer import compose_lesson
from .direct_html_validator import validate_file
from .io_utils import read_json, write_json, write_text
from .physics_context import build_physics_context
from .prompt_builder import composer_system_prompt, design_system_prompt, repair_system_prompt, review_system_prompt
from .repair_loop import repair_chapter


def prepare_input(run_path: Path, input_payload: dict[str, Any], narration: dict[str, Any], timing: dict[str, Any]) -> dict[str, Any]:
    word_timing_path = run_path / "audio_word_timestamps.json"
    if not word_timing_path.exists():
        raise RuntimeError(f"Direct HTML requires word timestamps: {word_timing_path}")
    word_timing = read_json(word_timing_path)
    asset_manifest = prepare_runtime_assets(run_path)
    prompt_root = run_path / "direct_html" / "prompts"
    write_text(prompt_root / "direct_html_design_system.txt", design_system_prompt())
    write_text(prompt_root / "direct_html_composer.system.txt", composer_system_prompt())
    write_text(prompt_root / "direct_html_repair.system.txt", repair_system_prompt())
    write_text(prompt_root / "direct_html_review.system.txt", review_system_prompt())
    physics_context = build_physics_context(input_payload, narration)
    write_json(run_path / "direct_html" / "physics_context.json", physics_context)
    bundle = build_input_bundle(run_path, input_payload, narration, timing, word_timing, asset_manifest, physics_context)
    return {"bundle": bundle, "asset_manifest": asset_manifest, "physics_context": physics_context}


def load_prepared(run_path: Path) -> dict[str, Any]:
    paths = {
        "bundle": run_path / "direct_html" / "lesson_input_bundle.json",
        "asset_manifest": run_path / "direct_html" / "asset_manifest.json",
        "physics_context": run_path / "direct_html" / "physics_context.json",
    }
    missing = [str(path) for path in paths.values() if not path.exists()]
    if missing:
        raise RuntimeError(f"Missing cached direct-HTML inputs: {missing}")
    return {name: read_json(path) for name, path in paths.items()}


def compose(
    run_path: Path,
    prepared: dict[str, Any],
    *,
    force: bool = False,
    allow_model_call: bool = True,
) -> dict[str, Any]:
    return compose_lesson(
        run_path,
        prepared["bundle"],
        prepared["physics_context"],
        prepared["asset_manifest"],
        force=force,
        allow_model_call=allow_model_call,
    )


def _chapter_findings(report: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    findings: dict[str, list[dict[str, Any]]] = {}
    browser = report.get("browser") or {}
    for chapter in browser.get("chapters", []):
        failed = (
            chapter.get("active_object_peak", 0) > 8
            or chapter.get("minimum_text_px") is not None and chapter["minimum_text_px"] < 30
            or bool(chapter.get("low_contrast_elements"))
            or bool(chapter.get("overflow_elements"))
            or bool(chapter.get("overlap_pairs"))
            or bool(chapter.get("blank_frames"))
            or bool(chapter.get("frozen_intervals"))
            or not chapter.get("deterministic_seek", False)
        )
        if failed:
            findings.setdefault(chapter["chapter_id"], []).append(chapter)
    for finding in (report.get("design_system") or {}).get("findings", []):
        chapter_id = finding.get("chapter_id")
        if chapter_id:
            findings.setdefault(chapter_id, []).append(finding)
    return findings


def validate_and_inspect(
    run_path: Path,
    prepared: dict[str, Any],
    *,
    browser: bool = True,
    auto_repair: bool = False,
) -> dict[str, Any]:
    master = run_path / "direct_html" / "master.html"
    build_chapter_index(master)
    static = validate_file(
        master,
        expected_duration=float(prepared["bundle"]["video"]["duration_seconds"]),
        physics_context=prepared["physics_context"],
        output=run_path / "direct_html" / "validation" / "html_validation.json",
    )
    if static["status"] != "passed":
        raise RuntimeError("Direct-HTML static validation failed")
    inspection = inspect_lesson(run_path) if browser else {"status": "skipped"}
    automatic_repairs = []
    if browser and auto_repair:
        for _round in range(2):
            failures = _chapter_findings(inspection)
            if not failures:
                break
            for chapter_id, findings in failures.items():
                automatic_repairs.append(
                    repair_chapter(
                        run_path,
                        chapter_id,
                        findings,
                        prepared["bundle"],
                        prepared["physics_context"],
                        instruction="Automatically repair the measured browser/design failures without changing lesson timing or scientific content.",
                    )
                )
            build_chapter_index(master)
            static = validate_file(
                master,
                expected_duration=float(prepared["bundle"]["video"]["duration_seconds"]),
                physics_context=prepared["physics_context"],
                output=run_path / "direct_html" / "validation" / "html_validation.json",
            )
            if static["status"] != "passed":
                raise RuntimeError("An automatic chapter repair broke the full direct-HTML contract")
            inspection = inspect_lesson(run_path)
    manifest_path = run_path / "direct_html" / "generation_manifest.json"
    manifest = read_json(manifest_path, {}) or {}
    manifest["status"] = "approved" if inspection.get("status") == "passed" else "validated"
    manifest["validation"] = inspection.get("status")
    write_json(manifest_path, manifest)
    return {"static": static, "inspection": inspection, "automatic_repairs": automatic_repairs}


def build_preview_manifest(run_path: Path) -> dict[str, Any]:
    master = run_path / "direct_html" / "master.html"
    if not master.exists():
        raise RuntimeError(f"Missing direct-HTML master: {master}")
    payload = {
        "version": "1.0",
        "run_id": run_path.name,
        "animation_mode": "direct-html",
        "master": "direct_html/master.html",
        "chapter_index": "direct_html/chapter_index.json",
        "validation": "direct_html/validation/final_direct_html_report.json",
    }
    write_json(run_path / "preview_manifest.json", payload)
    write_json(run_path / "preview_manifest_direct_html.json", payload)
    return payload
