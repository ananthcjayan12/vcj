#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB_ROOT))

from shorts.pipeline import ShortsPipeline  # noqa: E402
from shorts.rendering import render  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Create derivative portrait Shorts without mutating parent lessons")
    sub = parser.add_subparsers(dest="command", required=True)
    def parent(command: str, *, paid: bool = False):
        p = sub.add_parser(command); p.add_argument("--parent-run-id", required=True)
        if paid: p.add_argument("--confirm-paid-api", action="store_true")
        return p
    analyze = parent("analyze", paid=True)
    create = parent("create", paid=True); create.add_argument("--candidate-id", required=True); create.add_argument("--short-id", required=True)
    generate = parent("generate", paid=True); generate.add_argument("--short-id", required=True); generate.add_argument("--from-step", type=int, default=1); generate.add_argument("--stop-after-step", type=int, default=7)
    for flag in ("script", "audio", "visual", "captions", "render"): generate.add_argument(f"--force-{flag}", action="store_true")
    preview = parent("preview"); preview.add_argument("--short-id", required=True)
    render_parser = parent("render"); render_parser.add_argument("--short-id", required=True)
    args = parser.parse_args(); pipeline = ShortsPipeline(LAB_ROOT/"runs", args.parent_run_id)
    if args.command in {"analyze", "create", "generate"} and not args.confirm_paid_api:
        parser.error(f"{args.command} may invoke paid services; pass --confirm-paid-api")
    if args.command == "analyze": result = pipeline.analyze(use_model=True)
    elif args.command == "create": result = pipeline.create(args.candidate_id, args.short_id, use_model=True)
    elif args.command == "generate":
        force = {name for name in ("script", "audio", "visual", "captions", "render") if getattr(args, f"force_{name}")}
        result = pipeline.generate(args.short_id, from_step=args.from_step, stop_after_step=args.stop_after_step, force=force, use_model=True)
    elif args.command == "preview": return render(pipeline.shorts/args.short_id, preview=True)
    else: return render(pipeline.shorts/args.short_id)
    print(json.dumps(result, indent=2)); return 0


if __name__ == "__main__": raise SystemExit(main())
