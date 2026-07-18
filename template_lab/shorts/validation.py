from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .constants import MIN_TEXT_SIZE, PORTRAIT_HEIGHT, PORTRAIT_WIDTH
from .provenance import stale_reasons


def validate_parent(parent: Path) -> dict[str, Any]:
    required = ["input.json", "story_skeleton.json", "narration.json", "audio_chunks/manifest.json", "audio_word_timestamps.json", "voiceover.wav", "motion_canvas/manifest.json", "motion_canvas/final.mp4"]
    missing = [name for name in required if not (parent/name).is_file()]
    reels = [item for directory in ("reels", "shots", "chapters") for item in (parent/"motion_canvas"/directory).glob("*.tsx")]
    report_path = parent/"motion_canvas/robot-report.json"
    report = json.loads(report_path.read_text()) if report_path.is_file() else {}
    if not reels: missing.append("motion_canvas/{reels,shots,chapters}/*.tsx")
    if report.get("status") != "passed": missing.append("passed motion_canvas/robot-report.json")
    if missing: raise FileNotFoundError("Parent run is not Short-ready; missing: " + ", ".join(missing))
    return report


def extract_tsx_source(response: str) -> str:
    """Pull executable TSX out of model output (fences, file banners, prose wrappers)."""
    text = (response or "").strip()
    if not text:
        return text
    fenced = re.search(r"```(?:tsx|typescript|ts)?\s*(.*?)```", text, re.S | re.I)
    if fenced:
        text = fenced.group(1).strip()
    # Codex / tool wrappers occasionally emit path banners around the file body.
    text = re.sub(r"^\s*<<<\s*START OF FILE[^>\n]*>>>\s*", "", text, flags=re.I)
    text = re.sub(r"\s*<<<\s*END OF FILE[^>\n]*>>>\s*$", "", text, flags=re.I)
    text = re.sub(r"^\s*//\s*FILE:.*\n", "", text, flags=re.I)
    # Prefer the first import-driven module if prose still remains.
    import_match = re.search(r"(?m)^(import\s+.+)$", text)
    if import_match and import_match.start() > 0:
        text = text[import_match.start():]
    text = text.strip()
    if not text.endswith("\n"):
        text += "\n"
    return text


def sanitize_tsx(text: str, *, min_text_size: int = MIN_TEXT_SIZE) -> tuple[str, list[str]]:
    """Clamp common portrait rule violations so a near-valid adapter response can still ship."""
    notes: list[str] = []
    cleaned = extract_tsx_source(text)
    if cleaned != text and ("<<<" in text or "```" in text):
        notes.append("stripped non-tsx wrappers from model output")

    def clamp_font(match: re.Match[str]) -> str:
        prefix, raw, suffix = match.group(1), match.group(2), match.group(3)
        size = int(raw)
        if size < min_text_size:
            notes.append(f"fontSize {size}px raised to {min_text_size}px")
            return f"{prefix}{min_text_size}{suffix}"
        return match.group(0)

    # fontSize={31} | fontSize={ 31 } | fontSize={31 as const} style numerics
    sanitized = re.sub(r"(fontSize\s*=\s*\{?\s*)(\d+)(\s*\}?)", clamp_font, cleaned)
    return sanitized, notes


def validate_tsx(path: Path, short_id: str, *, sanitize: bool = True) -> list[str]:
    text = path.read_text(encoding="utf-8")
    notes: list[str] = []
    if sanitize:
        text, notes = sanitize_tsx(text)
        if notes:
            path.write_text(text, encoding="utf-8")
    errors = []
    if "short-presentation" not in text:
        errors.append("Portrait presentation components are not imported")
    if f"./{short_id}.cues" not in text and f"{short_id}.cues" not in text:
        errors.append("Short-local cues are not imported")
    if re.search(r"scale\s*=\s*\{?\s*0\.[0-9]", text) and ("1920" in text or "1080" in text):
        errors.append("Landscape root scale-down is forbidden")
    if re.search(r"https?://", text):
        errors.append("Remote assets/imports are forbidden")
    if re.search(r"Math\.random|random\(", text):
        errors.append("Random behavior is forbidden")
    for size in re.findall(r"fontSize\s*=\s*\{?([0-9]+)", text):
        if int(size) < MIN_TEXT_SIZE:
            errors.append(f"Text size {size}px is below {MIN_TEXT_SIZE}px")
    if errors:
        raise ValueError("Invalid portrait TSX: " + "; ".join(dict.fromkeys(errors)))
    return notes


def validate_manifest(manifest: dict[str, Any]) -> None:
    profile = manifest.get("profile") or {}
    if (profile.get("width"), profile.get("height")) != (PORTRAIT_WIDTH, PORTRAIT_HEIGHT): raise ValueError("Short profile must be 1080×1920")


def validate_sources(parent: Path, provenance: dict[str, Any]) -> None:
    stale = stale_reasons(parent, provenance)
    if stale: raise RuntimeError("source_stale: " + ", ".join(stale))
