"""Centralized prompt registry for the MAV video pipeline.

Every LLM prompt used in the pipeline lives here as a plain-text file.
This module provides a single `load(name)` function that reads and returns
the prompt content, with optional variable substitution.

Usage:
    from prompts import load
    system_prompt = load("script_structure")
    user_prompt = load("script_writing", topic="AAPL", facts="...")
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

DEFAULT_PROMPTS_DIR = Path(__file__).resolve().parent


def _prompt_dir() -> Path:
    override = os.environ.get("MAV_PROMPT_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return DEFAULT_PROMPTS_DIR


def load(name: str, **variables: Any) -> str:
    """Load a prompt template by name and substitute variables.

    Args:
        name: Filename without extension (e.g., "script_structure").
        **variables: Key-value pairs to substitute into the template.
            Only exact `{key}` placeholders are replaced, so example JSON
            braces inside prompt files remain untouched.

    Returns:
        The prompt text with variables substituted.
    """
    prompt_dir = _prompt_dir()
    path = prompt_dir / f"{name}.txt"
    if not path.exists() and prompt_dir != DEFAULT_PROMPTS_DIR:
        path = DEFAULT_PROMPTS_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    text = path.read_text(encoding="utf-8")
    for key, value in variables.items():
        text = text.replace("{" + key + "}", str(value))
    return text


def list_prompts() -> list[str]:
    """List all available prompt template names."""
    names = {p.stem for p in DEFAULT_PROMPTS_DIR.glob("*.txt")}
    prompt_dir = _prompt_dir()
    if prompt_dir != DEFAULT_PROMPTS_DIR and prompt_dir.exists():
        names.update(p.stem for p in prompt_dir.glob("*.txt"))
    return sorted(names)


def prompt_path(name: str) -> Path:
    """Return the filesystem path for a prompt template."""
    prompt_dir = _prompt_dir()
    path = prompt_dir / f"{name}.txt"
    if not path.exists() and prompt_dir != DEFAULT_PROMPTS_DIR:
        return DEFAULT_PROMPTS_DIR / f"{name}.txt"
    return path
