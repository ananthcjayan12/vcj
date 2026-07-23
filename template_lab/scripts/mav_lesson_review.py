from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

TEMPLATE_LAB_ROOT = Path(__file__).resolve().parents[1]
if str(TEMPLATE_LAB_ROOT) not in sys.path:
    sys.path.insert(0, str(TEMPLATE_LAB_ROOT))

from mav_schema import run_dir
from mav_env import load_repo_env
from motion_canvas import pipeline
from motion_canvas.lesson_review import screen_and_repair

load_repo_env()


def log(message: str) -> None:
    print(f"[optional-ai-review] {message}", flush=True)


def archive_previous_review(path: Path) -> Path | None:
    report = path / "motion_canvas" / "lesson-review.json"
    artifacts = path / "motion_canvas" / "lesson-review"
    if not report.exists() and not artifacts.exists():
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive = path / "motion_canvas" / "lesson-review-history" / stamp
    suffix = 1
    while archive.exists():
        archive = archive.with_name(f"{stamp}-{suffix}")
        suffix += 1
    archive.mkdir(parents=True)
    if report.exists():
        shutil.copy2(report, archive / "lesson-review.json")
    if artifacts.exists():
        shutil.copytree(artifacts, archive / "artifacts")
    return archive


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one lesson-level Motion Canvas visual screen.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--screen-only", action="store_true", help="Diagnose but do not regenerate flagged reels.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    os.environ["MAV_RUN_ID"] = args.run_id
    path = run_dir(args.run_id)
    manifest_path = path / "motion_canvas" / "manifest.json"
    if not manifest_path.exists():
        raise RuntimeError(f"Missing Motion Canvas manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    directory = "reels" if manifest.get("timeline_mode") == "immutable_reels" else "shots" if manifest.get("timeline_mode") == "immutable_shots" else "chapters"
    units = list(manifest.get(directory) or manifest.get("reels") or manifest.get("shots") or manifest.get("chapters") or [])
    source_paths = {
        str(unit["scene_id"]): path / "motion_canvas" / directory / f"{unit['scene_id']}.tsx"
        for unit in units
    }
    backups = {unit_id: source.read_text(encoding="utf-8") for unit_id, source in source_paths.items() if source.exists()}
    archived = archive_previous_review(path)
    log(f"run={args.run_id} mode={'screen-only' if args.screen_only else 'screen-and-repair'} reels={len(units)}")
    if archived:
        log(f"previous report and evidence archived at {archived.relative_to(path)}")
    original_validate = getattr(pipeline, "validate_and_assemble_original", pipeline.validate_and_assemble)
    log("phase 1/4: technical preflight validation")
    original_validate(path, manifest, allow_model_repair=False, max_model_repairs=0)
    log("technical preflight passed")
    log("phase 2/4: rendered evidence capture and multimodal screening")
    report = screen_and_repair(
        path,
        manifest,
        pipeline,
        allow_repairs=not args.screen_only,
    )
    if report.get("repaired_reels"):
        log(f"phase 3/4: validating {len(report['repaired_reels'])} regenerated reel(s)")
        try:
            technical = original_validate(path, manifest, allow_model_repair=False, max_model_repairs=0)
        except Exception as exc:
            log(f"post-repair validation failed; restoring all original reel sources: {exc}")
            for unit_id, source in backups.items():
                source_paths[unit_id].write_text(source.rstrip() + "\n", encoding="utf-8")
            pipeline.assemble(path, manifest)
            pipeline._sync_runtime(path)
            original_validate(path, manifest, allow_model_repair=False, max_model_repairs=0)
            report.update({
                "status": "needs_review",
                "post_repair_validation_error": str(exc),
                "restored_reels": list(report.get("repaired_reels") or []),
                "repaired_reels": [],
            })
            (path / "motion_canvas" / "lesson-review.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        else:
            log(f"post-repair technical validation passed: status={technical.get('status')}")
    else:
        log("phase 3/4: no regenerated reels require post-repair validation")
    log(f"phase 4/4: report finalized status={report.get('status')} findings={len(report.get('findings') or [])} repaired={len(report.get('repaired_reels') or [])}")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Lesson visual review failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
