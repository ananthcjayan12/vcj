"""ChatGPT-authenticated Codex CLI adapter for Motion Canvas batch generation."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import json
from pathlib import Path

from mav_costs import record_model_usage


def _binary() -> str:
    configured = os.getenv("MAV_CODEX_BIN", "").strip()
    candidates = [Path(configured)] if configured else []
    discovered = shutil.which("codex")
    if discovered:
        candidates.append(Path(discovered))
    # The VS Code extension bundles Codex but does not add it to PATH for
    # applications launched from Finder/the macOS dock.
    candidates.extend(sorted(
        (Path.home() / ".vscode" / "extensions").glob("openai.chatgpt-*/bin/*/codex"),
        key=lambda path: path.stat().st_mtime if path.exists() else 0,
        reverse=True,
    ))
    candidates.extend(sorted(
        (Path.home() / ".vscode-insiders" / "extensions").glob("openai.chatgpt-*/bin/*/codex"),
        key=lambda path: path.stat().st_mtime if path.exists() else 0,
        reverse=True,
    ))
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    raise RuntimeError("Codex CLI was not found. Open/install the Codex VS Code extension, install the CLI, or set MAV_CODEX_BIN.")


def _login_status(codex: str) -> None:
    result = subprocess.run([codex, "login", "status"], capture_output=True, text=True, timeout=15)
    detail = (result.stdout + result.stderr).strip()
    if result.returncode != 0 or "logged in" not in detail.lower():
        raise RuntimeError(f"Codex CLI is not authenticated with ChatGPT. Run `codex login`. Details: {detail}")


def _tokens(stderr: str) -> int:
    match = re.search(r"tokens used\s*\n\s*([0-9,]+)", stderr, flags=re.IGNORECASE)
    return int(match.group(1).replace(",", "")) if match else 0


def _strict_output_schema(schema: dict) -> dict:
    """Return the strict object schema required by Codex structured output."""
    def normalize(node):
        if isinstance(node, list):
            return [normalize(item) for item in node]
        if not isinstance(node, dict):
            return node
        result = {key: normalize(value) for key, value in node.items()}
        if result.get("type") == "object" or "properties" in result:
            result["additionalProperties"] = False
        return result
    return normalize(schema)


def _failure_detail(stderr: str, stdout: str) -> str:
    messages = re.findall(r'"message"\s*:\s*"([^"]+)"', stderr)
    if messages:
        return messages[-1]
    return (stderr or stdout)[-2000:]


def call_codex_text(*, task: str, system: str, user: str, max_tokens: int | None = None, output_schema: dict | None = None) -> str:
    """Match ``call_model_text`` so the existing cache/retry pipeline can use Codex."""
    del max_tokens  # Codex CLI manages its own output/context budget.
    codex = _binary()
    _login_status(codex)
    prefix = f"MAV_{task.upper()}"
    model = os.getenv(f"{prefix}_MODEL", "").strip()
    reasoning = os.getenv(f"{prefix}_REASONING_EFFORT", os.getenv("MAV_CODEX_REASONING_EFFORT", "low")).strip().lower()
    if reasoning not in {"low", "medium", "high", "xhigh", "max", "ultra"}:
        raise RuntimeError(f"Unsupported Codex reasoning effort: {reasoning}")
    prompt = (
        "You are a bounded code-generation worker. Do not edit files or run commands. "
        "Return only the exact file-marker response requested below.\n\n"
        f"SYSTEM INSTRUCTIONS\n{system}\n\nUSER REQUEST\n{user}"
    )
    with tempfile.TemporaryDirectory(prefix="mav-codex-") as directory:
        output = Path(directory) / "response.txt"
        isolated_cwd = directory if task.startswith("reel_") else str(Path(__file__).resolve().parents[2])
        command = [
            codex, "exec", "-", "--ephemeral", "--sandbox", "read-only", "--color", "never",
            "--output-last-message", str(output), "--cd", isolated_cwd,
        ]
        if task.startswith("reel_"):
            command.append("--skip-git-repo-check")
        if model:
            command.extend(["--model", model])
        command.extend(["--config", f'model_reasoning_effort="{reasoning}"'])
        if output_schema is not None:
            schema_path = Path(directory) / "schema.json"
            schema_path.write_text(json.dumps(_strict_output_schema(output_schema)), encoding="utf-8")
            command.extend(["--output-schema", str(schema_path)])
        result = subprocess.run(
            command,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=int(os.getenv("MAV_CODEX_TIMEOUT_SECONDS", "2400")),
        )
        if result.returncode != 0:
            detail = _failure_detail(result.stderr, result.stdout)
            raise RuntimeError(f"Codex CLI exited with code {result.returncode}: {detail}")
        if not output.exists():
            raise RuntimeError("Codex CLI completed without producing a final response")
        response = output.read_text(encoding="utf-8")
    actual_model = model
    match = re.search(r"^model:\s*(.+)$", result.stderr, flags=re.MULTILINE)
    if match:
        actual_model = match.group(1).strip()
    total = _tokens(result.stderr)
    record_model_usage(
        task=task,
        provider="codex",
        model=actual_model or "authenticated-default",
        usage={"total_tokens": total},
    )
    print(f"Codex {task} usage: model={actual_model or 'authenticated-default'} reasoning={reasoning} total={total or '?'}")
    print("Codex subscription remaining: not exposed by the CLI; check the Codex/ChatGPT usage UI.")
    return response


def call_codex_json(*, task: str, system: str, user: str, max_tokens: int | None = None, output_schema: dict | None = None) -> dict:
    response = call_codex_text(task=task, system=system, user=user, max_tokens=max_tokens, output_schema=output_schema)
    try:
        return json.loads(response)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Codex {task} did not return valid JSON: {exc}") from exc
