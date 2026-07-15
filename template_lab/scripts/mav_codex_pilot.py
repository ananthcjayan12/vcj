#!/usr/bin/env python3
"""Generate one isolated Motion Canvas chapter through a ChatGPT-authenticated Codex CLI."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

TEMPLATE_LAB_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = TEMPLATE_LAB_ROOT.parent
if str(TEMPLATE_LAB_ROOT) not in sys.path:
    sys.path.insert(0, str(TEMPLATE_LAB_ROOT))

from motion_canvas.pipeline import _batch_prompt, parse_response


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.rstrip() + "\n", encoding="utf-8")


def _codex_binary(explicit: str | None) -> str:
    configured = explicit or os.getenv("MAV_CODEX_BIN")
    candidates = [Path(configured)] if configured else []
    discovered = shutil.which("codex")
    if discovered:
        candidates.append(Path(discovered))
    candidates.extend(sorted(
        (Path.home() / ".vscode" / "extensions").glob("openai.chatgpt-*/bin/*/codex"),
        key=lambda path: path.stat().st_mtime if path.exists() else 0,
        reverse=True,
    ))
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    raise RuntimeError("Codex CLI was not found. Install/open the Codex VS Code extension or set MAV_CODEX_BIN.")


def _login_status(codex: str) -> str:
    result = subprocess.run([codex, "login", "status"], capture_output=True, text=True, timeout=15)
    status = (result.stdout + result.stderr).strip()
    if result.returncode != 0 or "logged in" not in status.lower():
        raise RuntimeError(f"Codex is not authenticated with ChatGPT. Run `codex login` first. Details: {status}")
    return status


def _parse_codex_usage(stderr: str) -> dict:
    usage: dict[str, object] = {
        "limit_remaining": None,
        "limit_remaining_note": "Codex CLI does not expose remaining ChatGPT/Codex subscription quota in this command output.",
    }
    for field in ("model", "provider", "reasoning effort", "session id"):
        match = re.search(rf"^{re.escape(field)}:\s*(.+)$", stderr, flags=re.MULTILINE)
        if match:
            usage[field.replace(" ", "_")] = match.group(1).strip()
    token_match = re.search(r"tokens used\s*\n\s*([0-9,]+)", stderr, flags=re.IGNORECASE)
    if token_match:
        usage["tokens_used"] = int(token_match.group(1).replace(",", ""))
    return usage


def run_pilot(args: argparse.Namespace) -> Path:
    run_path = args.run.resolve()
    source_root = run_path / "motion_canvas"
    manifest_path = source_root / "manifest.json"
    if not manifest_path.exists():
        raise RuntimeError(f"Missing Motion Canvas manifest: {manifest_path}")
    manifest = _load(manifest_path)
    chapter_ids = {item["scene_id"] for item in manifest.get("chapters", [])}
    if args.chapter not in chapter_ids:
        raise RuntimeError(f"Unknown chapter {args.chapter!r}; choose one of: {', '.join(sorted(chapter_ids))}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    pilot_root = run_path / "codex_pilot" / f"{args.chapter}-{stamp}"
    batch = {"id": "pilot_01", "chapter_ids": [args.chapter], "status": "pending"}
    system, user = _batch_prompt(pilot_root, manifest, batch)
    prompt = (
        "You are being called as an isolated code-generation worker. Do not edit files and do not run commands. "
        "Your final response is parsed by software, so obey the output markers exactly.\n\n"
        f"SYSTEM INSTRUCTIONS\n{system}\n\nUSER REQUEST\n{user}"
    )
    _write(pilot_root / "request.txt", prompt)

    codex = _codex_binary(args.codex_bin)
    status = _login_status(codex)
    _write(pilot_root / "auth-status.txt", status)
    if args.dry_run:
        _write(pilot_root / "result.json", json.dumps({"status": "ready", "chapter": args.chapter}, indent=2))
        return pilot_root

    response_path = pilot_root / "response.txt"
    command = [
        codex, "exec", "-", "--ephemeral", "--sandbox", "read-only",
        "--color", "never", "--output-last-message", str(response_path),
        "--cd", str(REPO_ROOT),
    ]
    if args.model:
        command.extend(["--model", args.model])
    result = subprocess.run(command, input=prompt, capture_output=True, text=True, timeout=args.timeout)
    _write(pilot_root / "codex-stdout.log", result.stdout)
    _write(pilot_root / "codex-stderr.log", result.stderr)
    if result.returncode != 0:
        raise RuntimeError(f"Codex exited with code {result.returncode}; inspect {pilot_root / 'codex-stderr.log'}")
    if not response_path.exists():
        raise RuntimeError("Codex completed without writing its final response")
    usage = _parse_codex_usage(result.stderr)

    response = response_path.read_text(encoding="utf-8")
    parsed = parse_response(response, [args.chapter])
    chapter_root = pilot_root / "chapters"
    _write(chapter_root / f"{args.chapter}.tsx", parsed[f"{args.chapter}.tsx"])
    cues = source_root / "chapters" / f"{args.chapter}.cues.ts"
    if not cues.exists():
        raise RuntimeError(f"Missing source cues: {cues}")
    shutil.copy2(cues, chapter_root / cues.name)
    _write(pilot_root / "result.json", json.dumps({
        "status": "generated",
        "backend": "codex-chatgpt-subscription",
        "source_run": str(run_path),
        "chapter": args.chapter,
        "tsx": str(chapter_root / f"{args.chapter}.tsx"),
        "codex_usage": usage,
        "production_files_changed": False,
    }, indent=2))
    return pilot_root


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True, help="Existing run directory containing motion_canvas/manifest.json")
    parser.add_argument("--chapter", default="chapter_01", help="One existing chapter id")
    parser.add_argument("--model", help="Optional Codex model override; otherwise use the authenticated CLI default")
    parser.add_argument("--codex-bin", help="Optional path to the Codex CLI")
    parser.add_argument("--timeout", type=int, default=900, help="Maximum Codex execution time in seconds")
    parser.add_argument("--dry-run", action="store_true", help="Check authentication and prepare the prompt without consuming usage")
    return parser.parse_args()


if __name__ == "__main__":
    try:
        output = run_pilot(parse_args())
        print(f"Codex pilot output: {output}")
        result_path = output / "result.json"
        if result_path.exists():
            result = _load(result_path)
            usage = result.get("codex_usage", {})
            if usage:
                model = usage.get("model") or "unknown"
                tokens = usage.get("tokens_used")
                remaining = usage.get("limit_remaining")
                token_text = f"{tokens:,}" if isinstance(tokens, int) else "unknown"
                remaining_text = remaining if remaining is not None else usage.get("limit_remaining_note", "unknown")
                print(f"Codex model: {model}")
                print(f"Codex tokens used: {token_text}")
                print(f"Codex limit remaining: {remaining_text}")
    except Exception as exc:
        print(f"Codex pilot failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
