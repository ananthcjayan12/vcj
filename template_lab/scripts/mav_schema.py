from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

LAB_ROOT = Path(__file__).resolve().parents[1]
PROJECT_DIR = LAB_ROOT / "project"
RUNS_DIR = LAB_ROOT / "runs"

TARGET_DURATION_SECONDS = 50.0
MIN_WORDS = 115
MAX_WORDS = 155
MIN_PARAGRAPHS = 6
MAX_PARAGRAPHS = 8
TIMING_TOLERANCE_SECONDS = 0.10
DATE_RELATIVE_LANGUAGE_PATTERNS = (
    (re.compile(r"\btoday\b", re.IGNORECASE), "today"),
    (re.compile(r"\bright\s+now\b", re.IGNORECASE), "right now"),
    (re.compile(r"\bcurrently\b", re.IGNORECASE), "currently"),
    (re.compile(r"\bat\s+the\s+moment\b", re.IGNORECASE), "at the moment"),
    (re.compile(r"\bat\s+present\b", re.IGNORECASE), "at present"),
    (re.compile(r"\bthese\s+days\b", re.IGNORECASE), "these days"),
    (re.compile(r"\bthis\s+(week|month|year|season)\b", re.IGNORECASE), "this week/month/year/season"),
    (re.compile(r"\brecent(?:ly)?\b", re.IGNORECASE), "recent/recently"),
    (re.compile(r"\blatest\b", re.IGNORECASE), "latest"),
    (re.compile(r"\bas\s+of\b", re.IGNORECASE), "as of"),
)
DAMAGED_WORD_PATTERN = re.compile(r"\b[A-Za-z]+%[A-Za-z]+\b")

FORBIDDEN_PLANNER_KEYS = {
    "svg",
    "svg_markup",
    "path",
    "path_data",
    "raw_html",
    "raw_css",
    "javascript",
    "script",
}

@dataclass
class Violation:
    code: str
    message: str
    scene_id: str | None = None
    field: str | None = None
    allowed_repairs: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {"code": self.code, "message": self.message}
        if self.scene_id:
            payload["scene_id"] = self.scene_id
        if self.field:
            payload["field"] = self.field
        if self.allowed_repairs:
            payload["allowed_repairs"] = self.allowed_repairs
        return payload


class MavValidationError(ValueError):
    def __init__(self, violations: list[Violation]):
        super().__init__("; ".join(v.message for v in violations))
        self.violations = violations


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "mav-run"


def run_dir(run_id: str) -> Path:
    return RUNS_DIR / slugify(run_id)


def strip_performance_tags(text: str) -> str:
    return re.sub(r"\[[^\]]+\]", " ", text)


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", strip_performance_tags(text)).strip()


def spoken_word_count(text: str) -> int:
    return len(re.findall(r"\b[\w']+\b", strip_performance_tags(text)))


def narration_bounds(target_duration_seconds: float) -> dict[str, int]:
    """Return duration-aware script bounds suitable for shorts and lessons.

    The original 50-second bounds remain unchanged for compatibility. Longer
    lessons target roughly 111-153 spoken words per minute and use enough
    paragraphs to give the visual planner distinct teaching beats.
    """
    duration = max(float(target_duration_seconds or TARGET_DURATION_SECONDS), 1.0)
    if duration <= 75:
        return {
            "min_words": MIN_WORDS,
            "max_words": MAX_WORDS,
            "min_paragraphs": MIN_PARAGRAPHS,
            "max_paragraphs": MAX_PARAGRAPHS,
        }
    # A patient educational delivery can naturally sit near 108 words/minute.
    # Keep the strict upper bound, but allow deliberate pauses in long lessons.
    min_words = max(MIN_WORDS, math.floor(duration * 1.80))
    max_words = max(min_words + 20, math.ceil(duration * 2.55))
    min_paragraphs = max(MIN_PARAGRAPHS, math.ceil(duration / 35.0))
    max_paragraphs = max(min_paragraphs + 2, math.ceil(duration / 18.0))
    return {
        "min_words": min_words,
        "max_words": max_words,
        "min_paragraphs": min_paragraphs,
        "max_paragraphs": max_paragraphs,
    }


def date_relative_phrases(text: str) -> list[str]:
    found: list[str] = []
    plain = normalize_text(text)
    for pattern, label in DATE_RELATIVE_LANGUAGE_PATTERNS:
        if pattern.search(plain):
            found.append(label)
    return found


def damaged_words(text: str) -> list[str]:
    return sorted(set(DAMAGED_WORD_PATTERN.findall(text)))


def check_forbidden_keys(value: Any, path: str = "$") -> list[Violation]:
    violations: list[Violation] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in FORBIDDEN_PLANNER_KEYS:
                violations.append(Violation("FORBIDDEN_KEY", f"Forbidden planner key {key} at {path}", field=path))
            violations.extend(check_forbidden_keys(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            violations.extend(check_forbidden_keys(child, f"{path}[{index}]"))
    return violations


def facts_by_id(input_payload: dict[str, Any]) -> dict[str, str]:
    facts = {}
    for item in input_payload.get("facts", []):
        fact_id = str(item.get("id", "")).strip()
        text = str(item.get("text", "")).strip()
        if fact_id and text:
            facts[fact_id] = text
    return facts


def validate_run_input(payload: dict[str, Any]) -> list[Violation]:
    violations: list[Violation] = []
    if not str(payload.get("run_id", "")).strip():
        violations.append(Violation("INPUT_RUN_ID", "run_id is required", field="run_id"))
    if not str(payload.get("topic", "")).strip():
        violations.append(Violation("INPUT_TOPIC", "topic is required", field="topic"))
    duration = float(payload.get("target_duration_seconds", TARGET_DURATION_SECONDS) or 0)
    if duration <= 0:
        violations.append(Violation("INPUT_DURATION", "target_duration_seconds must be positive", field="target_duration_seconds"))
    facts = payload.get("facts")
    if not isinstance(facts, list) or not facts:
        violations.append(Violation("INPUT_FACTS", "facts must contain at least one supplied fact", field="facts"))
    else:
        seen = set()
        for index, item in enumerate(facts):
            fact_id = str(item.get("id", "")).strip() if isinstance(item, dict) else ""
            text = str(item.get("text", "")).strip() if isinstance(item, dict) else ""
            if not fact_id or not text:
                violations.append(Violation("INPUT_FACT", f"facts[{index}] must include id and text", field=f"facts[{index}]"))
            if fact_id in seen:
                violations.append(Violation("INPUT_FACT_DUPLICATE", f"Duplicate fact id {fact_id}", field=f"facts[{index}].id"))
            seen.add(fact_id)
    return violations


def validate_narration(narration: dict[str, Any], input_payload: dict[str, Any]) -> list[Violation]:
    violations = check_forbidden_keys(narration)
    paragraphs = narration.get("paragraphs")
    if not isinstance(paragraphs, list) or not paragraphs:
        violations.append(Violation("NARRATION_PARAGRAPHS", "Narration must contain at least one paragraph", field="paragraphs"))
        paragraphs = paragraphs if isinstance(paragraphs, list) else []
    ids: set[str] = set()
    allowed_facts = facts_by_id(input_payload)
    plain_parts: list[str] = []
    for item in paragraphs:
        paragraph_id = str(item.get("id", "")).strip()
        text = str(item.get("text", "")).strip()
        if not paragraph_id or paragraph_id in ids:
            violations.append(Violation("NARRATION_PARAGRAPH_ID", "Paragraph IDs must be present and unique", field="paragraphs.id"))
        ids.add(paragraph_id)
        if not text:
            violations.append(Violation("NARRATION_EMPTY_PARAGRAPH", f"{paragraph_id} has empty text", field=paragraph_id))
        plain_parts.append(text)
        for claim_id in item.get("claim_ids", []):
            fact_root = str(claim_id).split(".", 1)[0]
            if claim_id not in allowed_facts and fact_root not in allowed_facts:
                violations.append(Violation("UNKNOWN_CLAIM_ID", f"{paragraph_id} references unknown fact {claim_id}", field=paragraph_id))
    # Word and paragraph targets guide the writing prompt but never reject a
    # usable script. The generated chapter audio establishes actual duration.
    relative_phrases = date_relative_phrases(" ".join([str(narration.get("title", "")), *plain_parts]))
    if relative_phrases:
        phrases = ", ".join(relative_phrases)
        violations.append(
            Violation(
                "NARRATION_DATE_RELATIVE_LANGUAGE",
                f"Narration must stay evergreen; replace date-relative phrasing: {phrases}",
                field="paragraphs.text",
            )
        )
    damaged = damaged_words(" ".join(plain_parts))
    if damaged:
        violations.append(
            Violation(
                "NARRATION_DAMAGED_WORD",
                f"Narration contains symbol-damaged words; replace them with clean ASCII or Unicode text: {', '.join(damaged)}",
                field="paragraphs.text",
            )
        )
    eleven = normalize_text(str(narration.get("elevenlabs_narration", ""))).lower()
    plain = normalize_text(" ".join(plain_parts)).lower()
    if plain and eleven and plain != eleven:
        violations.append(Violation("NARRATION_ELEVENLABS_MISMATCH", "ElevenLabs narration must match paragraphs after tag removal", field="elevenlabs_narration"))
    return violations


def validate_timing(timing: dict[str, Any], narration: dict[str, Any]) -> list[Violation]:
    violations: list[Violation] = []
    paragraphs = timing.get("paragraphs", [])
    narration_ids = [p["id"] for p in narration.get("paragraphs", [])]
    if [p.get("id") for p in paragraphs] != narration_ids:
        violations.append(Violation("TIMING_PARAGRAPH_IDS", "Timing paragraph IDs must match narration order", field="paragraphs"))
    duration = float(timing.get("audio_duration_seconds", 0) or 0)
    if duration <= 0:
        violations.append(Violation("TIMING_DURATION", "Audio duration must be positive", field="audio_duration_seconds"))
    cursor = 0.0
    for item in paragraphs:
        start = float(item.get("start", -1))
        end = float(item.get("end", -1))
        if abs(start - cursor) > TIMING_TOLERANCE_SECONDS:
            violations.append(Violation("TIMING_GAP", f"{item.get('id')} starts at {start}, expected {cursor}", field=item.get("id")))
        if end <= start:
            violations.append(Violation("TIMING_NEGATIVE", f"{item.get('id')} has non-positive duration", field=item.get("id")))
        cursor = end
    if duration and abs(cursor - duration) > TIMING_TOLERANCE_SECONDS:
        violations.append(Violation("TIMING_END", f"Timing ends at {cursor}, audio duration is {duration}", field="audio_duration_seconds"))
    return violations


def validation_payload(violations: list[Violation]) -> dict[str, Any]:
    return {
        "status": "passed" if not violations else "failed",
        "violations": [violation.to_dict() for violation in violations],
    }


def raise_if_invalid(violations: list[Violation]) -> None:
    if violations:
        raise MavValidationError(violations)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def dependency_hashes() -> dict[str, str]:
    files = [
        PROJECT_DIR / "css" / "tokens.css",
        PROJECT_DIR / "css" / "common.css",
        PROJECT_DIR / "css" / "v3_base.css",
        PROJECT_DIR / "js" / "composition_runtime.js",
        PROJECT_DIR / "vendor" / "gsap.min.js",
    ]
    return {str(path.relative_to(LAB_ROOT)): sha256_file(path) for path in files if path.exists()}
