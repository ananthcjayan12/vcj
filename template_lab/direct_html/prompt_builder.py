from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .constants import PROMPTS_ROOT


def _read(name: str) -> str:
    return (PROMPTS_ROOT / f"{name}.txt").read_text(encoding="utf-8")


def design_system_prompt() -> str:
    return _read("direct_html_design_system")


def composer_system_prompt() -> str:
    return _read("direct_html_composer.system").replace("{design_system}", design_system_prompt())


def repair_system_prompt() -> str:
    return _read("direct_html_repair.system").replace("{design_system}", design_system_prompt())


def review_system_prompt() -> str:
    return _read("direct_html_review.system").replace("{design_system}", design_system_prompt())


def composer_user_prompt(bundle: dict[str, Any]) -> str:
    return (
        "Create the final lesson application from this complete input bundle. "
        "Use the runtime paths exactly as supplied. lesson-data.js already exposes lessonTiming, lessonPhysics, and lessonAssets; "
        "do not copy the input bundle, narration, facts, or word-timing arrays into the HTML. "
        "call DirectHTML.boot once after all chapter registrations, and return only the complete HTML.\n\n"
        + json.dumps(bundle, indent=2, ensure_ascii=False)
    )


def write_prompt(path: Path, system: str, user: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"SYSTEM\n======\n{system}\n\nUSER\n====\n{user}\n", encoding="utf-8")
