"""GitHub Copilot CLI adapter for bounded MAV text-generation tasks."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from mav_costs import record_model_usage


def _binary() -> str:
    configured = os.getenv("MAV_COPILOT_BIN", "").strip()
    candidates = [Path(configured)] if configured else []
    discovered = shutil.which("copilot")
    if discovered:
        candidates.append(Path(discovered))
    candidates.append(Path.home() / ".local" / "bin" / "copilot")
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    raise RuntimeError(
        "GitHub Copilot CLI was not found. Install it from "
        "https://docs.github.com/en/copilot/how-tos/set-up/install-copilot-cli "
        "or set MAV_COPILOT_BIN."
    )


def _login_status(copilot: str) -> None:
    result = subprocess.run([copilot, "--help"], capture_output=True, text=True, timeout=15)
    detail = (result.stderr or result.stdout).strip()[-2000:]
    if result.returncode != 0:
        raise RuntimeError(f"GitHub Copilot CLI could not start: {detail}")
    help_text = (result.stdout + result.stderr).lower()
    if "--prompt" not in help_text and "-p" not in help_text:
        raise RuntimeError("The discovered `copilot` executable does not support programmatic prompt mode.")


def call_copilot_text(
    *, task: str, system: str, user: str, max_tokens: int | None = None,
    output_schema: dict | None = None,
) -> str:
    """Run one isolated, non-interactive Copilot request."""
    del max_tokens  # Copilot CLI controls the selected model's output budget.
    copilot = _binary()
    _login_status(copilot)
    prefix = f"MAV_{task.upper()}"
    model = os.getenv(f"{prefix}_MODEL", "claude-sonnet-4.6").strip() or "claude-sonnet-4.6"
    response_rule = "Return only the requested response, with no Markdown fence or commentary."
    if output_schema is not None:
        response_rule += " Return one JSON object conforming to this schema:\n" + json.dumps(output_schema)
    prompt = (
        "You are a bounded script-planning and script-writing worker. Do not use tools, "
        "edit files, browse, or run commands. All task context is supplied below.\n\n"
        f"{response_rule}\n\nSYSTEM INSTRUCTIONS\n{system}\n\nUSER REQUEST\n{user}"
    )
    command = [
        copilot, "-p", prompt, "-s", "--model", model, "--stream=off",
        "--no-ask-user", "--no-auto-update", "--no-color", "--no-custom-instructions",
    ]
    with tempfile.TemporaryDirectory(prefix="mav-copilot-") as directory:
        result = subprocess.run(
            command,
            cwd=directory,
            capture_output=True,
            text=True,
            timeout=int(os.getenv("MAV_COPILOT_TIMEOUT_SECONDS", "2400")),
        )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[-2000:]
        raise RuntimeError(
            f"GitHub Copilot CLI exited with code {result.returncode}. "
            f"Run `copilot` once to authenticate if needed. Details: {detail}"
        )
    response = result.stdout.strip()
    if not response:
        raise RuntimeError("GitHub Copilot CLI completed without producing a response")
    record_model_usage(task=task, provider="copilot", model=model, usage={})
    print(f"GitHub Copilot {task} usage: model={model} (subscription usage is not exposed by the CLI)")
    return response


def call_copilot_json(
    *, task: str, system: str, user: str, max_tokens: int | None = None,
    output_schema: dict | None = None,
) -> dict:
    response = call_copilot_text(
        task=task, system=system, user=user, max_tokens=max_tokens, output_schema=output_schema,
    )
    try:
        return json.loads(response)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"GitHub Copilot {task} did not return valid JSON: {exc}") from exc
