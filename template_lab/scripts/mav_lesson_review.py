from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

TEMPLATE_LAB_ROOT = Path(__file__).resolve().parents[1]
if str(TEMPLATE_LAB_ROOT) not in sys.path:
    sys.path.insert(0, str(TEMPLATE_LAB_ROOT))

from mav_schema import run_dir
from motion_canvas import pipeline
from motion_canvas.lesson_review import screen_and_repair


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
    original_validate = getattr(pipeline, "validate_and_assemble_original", pipeline.validate_and_assemble)
    original_validate(path, manifest, allow_model_repair=False, max_model_repairs=0)
    report = screen_and_repair(
        path,
        manifest,
        pipeline,
        allow_repairs=not args.screen_only,
    )
    if report.get("repaired_reels"):
        original_validate(path, manifest, allow_model_repair=False, max_model_repairs=0)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Lesson visual review failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
