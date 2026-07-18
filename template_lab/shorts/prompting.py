from __future__ import annotations

from pathlib import Path


def render_user_prompt(path: Path, replacements: dict[str, str]) -> str:
    text = path.read_text(encoding="utf-8")
    for key, value in replacements.items():
        token = "{{" + key + "}}"
        if token not in text:
            raise ValueError(f"Missing prompt token: {token}")
        text = text.replace(token, value)
    leftover = [part for part in text.split("{{")[1:] if "}}" in part]
    if leftover:
        names = ", ".join(part.split("}}", 1)[0] for part in leftover)
        raise ValueError(f"Unresolved prompt tokens: {names}")
    return text


def prompts_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "prompts"
