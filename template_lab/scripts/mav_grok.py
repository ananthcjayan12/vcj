"""Official xAI Grok Build CLI adapter for bounded MAV model tasks."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from mav_costs import record_model_usage


def _binary() -> str:
    configured = os.getenv("MAV_GROK_BIN", "").strip()
    candidates = [configured] if configured else []
    discovered = shutil.which("grok")
    if discovered:
        candidates.append(discovered)
    candidates.extend([str(Path.home() / ".local" / "bin" / "grok"), str(Path.home() / ".grok" / "bin" / "grok")])
    for candidate in candidates:
        path = Path(candidate).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    raise RuntimeError("Official Grok Build CLI was not found. Install it from https://x.ai/cli/install.sh or set MAV_GROK_BIN.")


def _login_status(binary: str) -> None:
    if os.getenv("XAI_API_KEY"):
        return
    result = subprocess.run([binary, "--no-auto-update", "models"], capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[-1500:]
        raise RuntimeError(f"Grok CLI is not authenticated. Run `grok login` or set XAI_API_KEY. Details: {detail}")


def _extract_json(text: str) -> dict:
    text = text.strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise RuntimeError("Grok CLI did not return a JSON object") from None
        value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise RuntimeError("Grok CLI structured response must be a JSON object")
    return value


def call_grok_text(*, task: str, system: str, user: str, max_tokens: int | None = None, output_schema: dict | None = None) -> str:
    del max_tokens
    binary = _binary()
    _login_status(binary)
    prefix = f"MAV_{task.upper()}"
    model = os.getenv(f"{prefix}_MODEL", os.getenv("MAV_GROK_MODEL", "grok-4.5")).strip()
    effort = os.getenv(f"{prefix}_REASONING_EFFORT", os.getenv("MAV_GROK_REASONING_EFFORT", "high")).strip().lower()
    if effort not in {"low", "medium", "high"}:
        raise RuntimeError(f"Unsupported Grok reasoning effort: {effort}. Use low, medium, or high.")
    schema_instruction = f"\n\nSTRICT OUTPUT JSON SCHEMA\n{json.dumps(output_schema, ensure_ascii=False)}" if output_schema else ""
    prompt = (
        "You are a bounded generation worker. Do not inspect or modify files and do not run tools. "
        "Return only the exact response requested.\n\n"
        f"SYSTEM INSTRUCTIONS\n{system}\n\nUSER REQUEST\n{user}{schema_instruction}"
    )
    with tempfile.TemporaryDirectory(prefix="mav-grok-") as isolated_cwd:
        command = [
            binary, "--no-auto-update", "-p", prompt, "--output-format", "plain", "--cwd", isolated_cwd,
            "--model", model, "--effort", effort, "--max-turns", "1", "--no-plan", "--no-subagents", "--no-memory",
            "--disable-web-search", "--sandbox", "read-only", "--permission-mode", "dontAsk",
            "--disallowed-tools", "Bash,Edit,Read,Grep,WebFetch",
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=int(os.getenv("MAV_GROK_TIMEOUT_SECONDS", "2400")))
    if result.returncode != 0:
        raise RuntimeError(f"Grok CLI exited with code {result.returncode}: {(result.stderr or result.stdout)[-2000:]}")
    response = result.stdout.strip()
    if not response:
        raise RuntimeError("Grok CLI completed without a response")
    record_model_usage(task=task, provider="grok", model=model, usage={})
    return response


def call_grok_json(*, task: str, system: str, user: str, max_tokens: int | None = None, output_schema: dict | None = None) -> dict:
    return _extract_json(call_grok_text(task=task, system=system, user=user, max_tokens=max_tokens, output_schema=output_schema))
