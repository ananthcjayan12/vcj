"""Attach one-call lesson screening to Motion Canvas Compile & QA."""
from __future__ import annotations

import json
import os
from pathlib import Path
from types import ModuleType
from typing import Any

from mav_env import load_repo_env

load_repo_env()


def _enabled(allow_model_repair: bool) -> tuple[bool, str]:
    raw = os.getenv("MAV_MOTION_CANVAS_LESSON_REVIEW", "0").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return False, "lesson_review_disabled"
    if not allow_model_repair:
        return False, "paid_model_call_not_authorized"
    if not (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")):
        return False, "Gemini API key is not configured"
    return True, ""


def _source_paths(run_path: Path, manifest: dict[str, Any]) -> dict[str, Path]:
    if manifest.get("timeline_mode") == "immutable_reels":
        directory, units = "reels", manifest.get("reels") or []
    elif manifest.get("timeline_mode") == "immutable_shots":
        directory, units = "shots", manifest.get("shots") or []
    else:
        directory, units = "chapters", manifest.get("chapters") or []
    return {
        str(unit["scene_id"]): run_path / "motion_canvas" / directory / f"{unit['scene_id']}.tsx"
        for unit in units
    }


def _write_report(run_path: Path, report: dict[str, Any]) -> None:
    path = run_path / "motion_canvas" / "lesson-review.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _existing_screening_report(run_path: Path) -> dict[str, Any] | None:
    path = run_path / "motion_canvas" / "lesson-review.json"
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    return report if isinstance(report, dict) and report.get("status") not in {None, "skipped"} else None


def install(pipeline: ModuleType) -> None:
    if getattr(pipeline, "_lesson_review_installed", False):
        return
    original_validate = pipeline.validate_and_assemble

    def validated_with_lesson_review(
        run_path: Path,
        manifest: dict[str, Any],
        *,
        allow_model_repair: bool = False,
        max_model_repairs: int = 2,
        model_call: Any = None,
    ) -> dict[str, Any]:
        technical = original_validate(
            run_path,
            manifest,
            allow_model_repair=allow_model_repair,
            max_model_repairs=max_model_repairs,
            model_call=model_call,
        )
        enabled, reason = _enabled(allow_model_repair)
        if not enabled:
            if reason == "lesson_review_disabled":
                return technical
            report = _existing_screening_report(run_path)
            if report is None:
                report = {"version": "2.0", "status": "skipped", "reason": reason, "screening_calls": 0}
                _write_report(run_path, report)
            technical["lesson_review"] = report
            technical["lesson_review_status"] = report["status"]
            robot = run_path / "motion_canvas" / "robot-report.json"
            robot.write_text(json.dumps(technical, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            return technical

        from .lesson_review import screen_and_repair

        paths = _source_paths(run_path, manifest)
        backups = {reel_id: path.read_text(encoding="utf-8") for reel_id, path in paths.items() if path.exists()}
        allow_repairs = os.getenv("MAV_MOTION_CANVAS_AUTO_REPAIR_FINDINGS", "1").strip().lower() not in {"0", "false", "no", "off"}
        try:
            report = screen_and_repair(
                run_path,
                manifest,
                pipeline,
                allow_repairs=allow_repairs,
            )
            if report.get("repaired_reels"):
                try:
                    technical = original_validate(
                        run_path,
                        manifest,
                        allow_model_repair=False,
                        max_model_repairs=0,
                    )
                except Exception as exc:
                    for reel_id in report.get("repaired_reels", []):
                        path = paths.get(str(reel_id))
                        backup = backups.get(str(reel_id))
                        if path is not None and backup is not None:
                            path.write_text(backup.rstrip() + "\n", encoding="utf-8")
                    pipeline.assemble(run_path, manifest)
                    pipeline._sync_runtime(run_path)
                    technical = original_validate(
                        run_path,
                        manifest,
                        allow_model_repair=False,
                        max_model_repairs=0,
                    )
                    report["status"] = "needs_review"
                    report["post_repair_validation_error"] = str(exc)
                    report["restored_reels"] = list(report.get("repaired_reels", []))
                    report["repaired_reels"] = []
                    _write_report(run_path, report)
        except Exception as exc:
            for reel_id, backup in backups.items():
                path = paths.get(reel_id)
                if path is not None:
                    path.write_text(backup.rstrip() + "\n", encoding="utf-8")
            pipeline.assemble(run_path, manifest)
            pipeline._sync_runtime(run_path)
            report = {
                "version": "2.0",
                "status": "needs_review",
                "reason": "lesson_screening_error",
                "error": str(exc),
                "screening_calls": 0,
            }
            _write_report(run_path, report)

        technical["lesson_review"] = report
        technical["lesson_review_status"] = report.get("status", "unknown")
        robot = run_path / "motion_canvas" / "robot-report.json"
        robot.write_text(json.dumps(technical, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return technical

    pipeline.validate_and_assemble_original = original_validate
    pipeline.validate_and_assemble = validated_with_lesson_review
    pipeline._lesson_review_installed = True
