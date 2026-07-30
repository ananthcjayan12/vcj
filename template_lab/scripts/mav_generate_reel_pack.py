from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

TEMPLATE_LAB_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = Path(__file__).resolve().parent
for candidate in (str(TEMPLATE_LAB_ROOT), str(SCRIPTS_ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from mav_env import load_repo_env  # noqa: E402
from mav_inputs import read_facts_payload, read_pipeline_inputs  # noqa: E402
from reel_pack.pipeline import (  # noqa: E402
    CONTENT_PRODUCT,
    create_pack,
    load_pack,
    pack_path,
    run_pack_step,
)

load_repo_env()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a standalone portrait Reel pack beside the long-form lesson pipeline."
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--topic")
    parser.add_argument("--topic-ref")
    parser.add_argument("--facts", type=Path)
    parser.add_argument("--tone", default="warm, precise IGCSE Physics teacher")
    parser.add_argument("--reel-count", type=int, default=5)
    parser.add_argument("--duration", type=float, default=35.0)
    parser.add_argument("--audio-provider", choices=("gemini", "elevenlabs"), default="gemini")
    parser.add_argument("--from-step", type=int, choices=range(1, 9), default=1)
    parser.add_argument("--stop-after-step", type=int, choices=range(1, 9), default=7)
    parser.add_argument("--reel-id", help="Run child stages only for one parent Reel ID, e.g. reel_004")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--use-model", action="store_true")
    parser.add_argument("--confirm-paid-api", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--screen-only", action="store_true")
    parser.add_argument("--render-all", action="store_true")
    return parser.parse_args()


def _input_from_args(args: argparse.Namespace) -> dict:
    payload = read_facts_payload(args.facts) if args.facts else read_pipeline_inputs()
    topic = str(args.topic or payload.get("topic") or "").strip()
    if not topic:
        raise RuntimeError("A topic is required through --topic or the facts payload")
    topic_ref = str(args.topic_ref or payload.get("topic_ref") or "").strip()
    return {
        "topic": topic,
        "topic_ref": topic_ref,
        "objective_ids": payload.get("objective_ids", []),
        "facts": payload.get("facts", []),
        "physics_context": payload.get("physics_context", {}),
    }


def main() -> int:
    args = parse_args()
    os.environ["MAV_RUN_ID"] = args.run_id
    if args.stop_after_step < args.from_step:
        print("--stop-after-step must be >= --from-step", file=sys.stderr)
        return 2
    paid_step = any(step in {2, 3, 5, 6, 7} for step in range(args.from_step, args.stop_after_step + 1))
    if paid_step and not args.confirm_paid_api:
        print("Paid/API Reel-pack stages require --confirm-paid-api", file=sys.stderr)
        return 2
    run_path = pack_path(args.run_id)
    try:
        if args.from_step == 1 and not (run_path / "reel_pack.json").exists():
            source = _input_from_args(args)
            create_pack(
                run_id=args.run_id,
                topic=source["topic"],
                topic_ref=source["topic_ref"],
                objective_ids=source["objective_ids"],
                facts=source["facts"],
                physics_context=source["physics_context"],
                tone=args.tone,
                reel_count=args.reel_count,
                target_duration_seconds=args.duration,
                audio_provider=args.audio_provider,
            )
        else:
            load_pack(run_path)
        for step in range(args.from_step, args.stop_after_step + 1):
            run_pack_step(
                run_path,
                step=step,
                allow_model_call=args.use_model,
                force=args.force,
                target_reel_id=args.reel_id,
                audio_provider=args.audio_provider,
                workers=args.workers,
                auto_repair=not args.screen_only,
                render_all=args.render_all,
            )
            print(f"Reel-pack step {step} completed.", flush=True)
        pack = load_pack(run_path)
        print(
            json.dumps(
                {
                    "run_id": pack["run_id"],
                    "content_product": CONTENT_PRODUCT,
                    "status": pack["status"],
                    "current_step": pack["current_step"],
                    "summary": pack.get("summary", {}),
                    "run_path": str(run_path),
                },
                indent=2,
            )
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"Standalone Reel-pack generation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
