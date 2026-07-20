"""SuperGrok-authenticated Grok Build CLI adapter for MAV model tasks."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from mav_costs import record_model_usage


def _binary() -> str:
    configured = os.getenv("MAV_GROK_BIN", "").strip()
    candidates = [Path(configured)] if configured else []
    discovered = shutil.which("grok")
    if discovered:
        candidates.append(Path(discovered))
    candidates.extend((Path.home() / ".local" / "bin" / "grok", Path.home() / ".grok" / "bin" / "grok"))
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    raise RuntimeError(
        "Grok Build CLI was not found. Install it from https://x.ai/cli or set MAV_GROK_BIN."
    )


def _model_catalog(grok: str) -> tuple[str, tuple[str, ...]]:
    result = subprocess.run(
        [grok, "models"], capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[-2000:]
        raise RuntimeError(
            f"Grok CLI is not authenticated. Run `grok login` and sign in with SuperGrok. Details: {detail}"
        )
    output = result.stdout + result.stderr
    default_match = re.search(r"^Default model:\s*(\S+)", output, flags=re.MULTILINE)
    models = tuple(re.findall(r"^\s*\*\s+(\S+?)(?:\s+\(default\))?\s*$", output, flags=re.MULTILINE))
    default = default_match.group(1) if default_match else (models[0] if models else "")
    if not default or not models:
        raise RuntimeError(f"Could not parse available models from `grok models`: {output.strip()[-2000:]}")
    return default, models


def _login_status(grok: str) -> None:
    _model_catalog(grok)


def _resolve_model(requested: str, default: str, available: tuple[str, ...]) -> str:
    # Older Studio builds exposed these documentation/config aliases even when
    # the installed subscription CLI did not. Preserve saved runs by resolving
    # them to the authenticated CLI's current default.
    if requested in {"grok-build", "grok-build-latest", "authenticated-default", "default"}:
        return default
    if requested not in available:
        raise RuntimeError(
            f"Grok model {requested!r} is not available for this account/CLI. "
            f"Available models: {', '.join(available)}"
        )
    return requested


def call_grok_text(
    *, task: str, system: str, user: str, max_tokens: int | None = None,
    output_schema: dict | None = None,
) -> str:
    """Run one isolated, non-interactive Grok Build request."""
    del max_tokens  # Grok Build controls the subscription model's context/output budget.
    grok = _binary()
    default_model, available_models = _model_catalog(grok)
    prefix = f"MAV_{task.upper()}"
    requested_model = os.getenv(f"{prefix}_MODEL", default_model).strip() or default_model
    model = _resolve_model(requested_model, default_model, available_models)
    effort = os.getenv(f"{prefix}_REASONING_EFFORT", os.getenv("MAV_GROK_REASONING_EFFORT", "high")).strip().lower()
    if effort not in {"low", "medium", "high"}:
        raise RuntimeError(f"Unsupported Grok reasoning effort: {effort}")
    response_rule = "Return only the requested response, with no Markdown fence or commentary."
    if output_schema is not None:
        response_rule += " Return one JSON object conforming to this schema:\n" + json.dumps(output_schema)
    prompt = f"{response_rule}\n\nSYSTEM INSTRUCTIONS\n{system}\n\nUSER REQUEST\n{user}"
    command = [
        grok, "--no-auto-update", "--verbatim", "-p", prompt,
        "--system-prompt-override",
        "You are a bounded text and code generation worker. Do not announce a plan. Do not edit files or explain your work. All required task context is in the supplied prompt. Start generating immediately and return only the requested final output.",
        "--tools", "read_file,list_dir,grep", "--output-format", "plain",
        "--cwd", str(Path(__file__).resolve().parents[2]), "--model", model,
        "--effort", effort, "--sandbox", "read-only", "--permission-mode", "dontAsk",
        "--max-turns", os.getenv("MAV_GROK_MAX_TURNS", "16"),
        "--no-plan", "--no-subagents", "--no-memory", "--disable-web-search",
    ]
    result = subprocess.run(
        command, capture_output=True, text=True,
        timeout=int(os.getenv("MAV_GROK_TIMEOUT_SECONDS", "2400")),
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[-2000:]
        raise RuntimeError(f"Grok CLI exited with code {result.returncode}: {detail}")
    response = result.stdout.strip()
    if not response:
        raise RuntimeError("Grok CLI completed without producing a response")
    record_model_usage(task=task, provider="grok", model=model, usage={})
    print(f"Grok {task} usage: model={model} reasoning={effort} (subscription usage is not exposed by the CLI)")
    return response


def call_grok_json(
    *, task: str, system: str, user: str, max_tokens: int | None = None,
    output_schema: dict | None = None,
) -> dict:
    response = call_grok_text(
        task=task, system=system, user=user, max_tokens=max_tokens, output_schema=output_schema,
    )
    try:
        return json.loads(response)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Grok {task} did not return valid JSON: {exc}") from exc
