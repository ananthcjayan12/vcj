from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parents[1]
if str(LAB_ROOT) not in sys.path:
    sys.path.insert(0, str(LAB_ROOT))

from reels.pipeline import analyze_parent, create_reel, generate_reel, render_reel


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Create native portrait MAV Physics Reels from approved lesson narration.")
    commands = root.add_subparsers(dest="command", required=True)
    analyze = commands.add_parser("analyze")
    analyze.add_argument("--parent-run-id", required=True); analyze.add_argument("--candidate-count", type=int, default=4); analyze.add_argument("--confirm-paid-api", action="store_true")
    create = commands.add_parser("create")
    create.add_argument("--parent-run-id", required=True); create.add_argument("--candidate-id", required=True); create.add_argument("--reel-run-id", required=True)
    generate = commands.add_parser("generate")
    generate.add_argument("--reel-run-id", required=True); generate.add_argument("--from-step", type=int, default=1); generate.add_argument("--stop-after-step", type=int, default=8)
    generate.add_argument("--use-model", action="store_true"); generate.add_argument("--confirm-paid-api", action="store_true"); generate.add_argument("--force-paid-api", action="store_true")
    generate.add_argument("--audio-provider", choices=("gemini", "elevenlabs"), default="gemini"); generate.add_argument("--instruction", default="")
    regenerate = commands.add_parser("regenerate-shot")
    regenerate.add_argument("--reel-run-id", required=True); regenerate.add_argument("--shot-id", required=True); regenerate.add_argument("--instruction", default=""); regenerate.add_argument("--confirm-paid-api", action="store_true")
    preview = commands.add_parser("preview"); preview.add_argument("--reel-run-id", required=True)
    render = commands.add_parser("render"); render.add_argument("--reel-run-id", required=True)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "analyze":
            if not args.confirm_paid_api: raise RuntimeError("Candidate analysis requires --confirm-paid-api")
            result = analyze_parent(args.parent_run_id, candidate_count=args.candidate_count)
        elif args.command == "create": result = create_reel(args.parent_run_id, args.candidate_id, args.reel_run_id)
        elif args.command == "generate":
            paid = args.from_step <= 7 and args.stop_after_step >= 1
            if paid and (not args.use_model or not args.confirm_paid_api): raise RuntimeError("Creative/TTS generation requires --use-model --confirm-paid-api")
            result = generate_reel(args.reel_run_id, from_step=args.from_step, stop_after_step=args.stop_after_step, allow_model_call=args.use_model,
                                   force=args.force_paid_api, instruction=args.instruction, audio_provider=args.audio_provider)
        elif args.command == "regenerate-shot":
            if not args.confirm_paid_api: raise RuntimeError("Shot regeneration requires --confirm-paid-api")
            result = generate_reel(args.reel_run_id, from_step=7, stop_after_step=8, target_shot_id=args.shot_id,
                                   force=True, instruction=args.instruction, allow_model_call=True)
        elif args.command == "preview":
            from motion_canvas.pipeline import prepare_runtime_preview
            from mav_schema import run_dir
            prepare_runtime_preview(run_dir(args.reel_run_id))
            result = {"status": "ready", "command": "cd motion_canvas_runtime && npm run serve", "profile": "1080x1920"}
        else: result = render_reel(args.reel_run_id)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(f"MAV Reel failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
