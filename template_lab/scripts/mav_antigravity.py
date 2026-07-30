"""Google Antigravity CLI adapter for bounded MAV text-generation tasks."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from mav_costs import record_model_usage


def _binary() -> str:
    configured = os.getenv("MAV_ANTIGRAVITY_BIN", "").strip()
    candidates = [Path(configured)] if configured else []
    candidates.append(Path.home() / ".local" / "bin" / "agy")
    discovered = shutil.which("agy")
    if discovered:
        candidates.append(Path(discovered))
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    raise RuntimeError(
        "Antigravity CLI was not found. Install the official `agy` CLI from "
        "https://antigravity.google/docs/cli/overview or set MAV_ANTIGRAVITY_BIN."
    )


def _model_catalog(agy: str) -> tuple[str, ...]:
    help_result = subprocess.run([agy, "--help"], capture_output=True, text=True, timeout=15)
    help_text = (help_result.stdout + help_result.stderr).lower()
    if (
        help_result.returncode != 0
        or "--print" not in help_text
    ):
        raise RuntimeError(
            "The discovered `agy` executable is not the headless Antigravity CLI "
            "(the older Antigravity desktop launcher is not supported). Install the "
            "official CLI or set MAV_ANTIGRAVITY_BIN to it."
        )
    result = subprocess.run([agy, "models"], capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[-2000:]
        raise RuntimeError(
            "Antigravity CLI is not authenticated or could not list models. "
            f"Run `agy` and sign in with Google. Details: {detail}"
        )
    models = tuple(
        line.strip()
        for line in (result.stdout + result.stderr).splitlines()
        if line.strip() and not line.lstrip().startswith(("Error:", "Warning:"))
    )
    if not models:
        raise RuntimeError("Antigravity CLI returned an empty authenticated model catalog")
    return models


def _login_status(agy: str) -> None:
    _model_catalog(agy)


def call_antigravity_text(
    *, task: str, system: str, user: str, max_tokens: int | None = None,
    output_schema: dict | None = None,
) -> str:
    """Run one isolated Antigravity headless request."""
    del max_tokens  # The subscription CLI controls its context/output budget.
    agy = _binary()
    available_models = _model_catalog(agy)
    prefix = f"MAV_{task.upper()}"
    model = os.getenv(f"{prefix}_MODEL", "authenticated-default").strip() or "authenticated-default"
    response_rule = "Return only the requested response, with no Markdown fence or commentary."
    if output_schema is not None:
        response_rule += " Return one JSON object conforming to this schema:\n" + json.dumps(output_schema)
    prompt = (
        "You are a bounded script-planning and script-writing worker. Do not use tools, "
        "edit files, browse, or run commands. All task context is supplied below.\n\n"
        f"{response_rule}\n\nSYSTEM INSTRUCTIONS\n{system}\n\nUSER REQUEST\n{user}"
    )
    command = [agy, "--print", prompt, "--sandbox"]
    if model not in {"authenticated-default", "default", "auto"}:
        if model not in available_models:
            raise RuntimeError(
                f"Antigravity model {model!r} is not available for this account/CLI. "
                f"Available models: {', '.join(available_models)}"
            )
        command.extend(["--model", model])
    with tempfile.TemporaryDirectory(prefix="mav-antigravity-") as directory:
        result = subprocess.run(
            command,
            cwd=directory,
            capture_output=True,
            text=True,
            timeout=int(os.getenv("MAV_ANTIGRAVITY_TIMEOUT_SECONDS", "2400")),
        )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[-2000:]
        raise RuntimeError(f"Antigravity CLI exited with code {result.returncode}: {detail}")
    response = result.stdout.strip()
    if not response:
        raise RuntimeError("Antigravity CLI completed without producing a response")
    record_model_usage(task=task, provider="antigravity", model=model, usage={})
    print(
        f"Antigravity {task} usage: model={model} "
        "(subscription usage is not exposed by the CLI)"
    )
    return response


def call_antigravity_json(
    *, task: str, system: str, user: str, max_tokens: int | None = None,
    output_schema: dict | None = None,
) -> dict:
    response = call_antigravity_text(
        task=task, system=system, user=user, max_tokens=max_tokens, output_schema=output_schema,
    )
    try:
        return json.loads(response)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Antigravity {task} did not return valid JSON: {exc}") from exc
