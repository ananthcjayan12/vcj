from __future__ import annotations

import json
import re
import subprocess
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .constants import (
    FORBIDDEN_SOURCE_PATTERNS,
    LEGACY_STYLE_TERMS,
    MAX_ACTIVE_OBJECTS,
    MAX_HTML_BYTES,
    MIN_IMPORTANT_TEXT_PX,
    SCIENCE_TOKENS,
)
from .html_contract import extract_chapter_blocks, missing_root_ids, parse_document
from .io_utils import write_json


@dataclass(frozen=True)
class DirectHTMLViolation:
    code: str
    message: str
    severity: str = "error"
    chapter_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {"code": self.code, "message": self.message, "severity": self.severity}
        if self.chapter_id:
            payload["chapter_id"] = self.chapter_id
        return payload


def _javascript_violations(parser) -> list[DirectHTMLViolation]:
    violations: list[DirectHTMLViolation] = []
    for index, (attrs, source) in enumerate(parser.scripts, 1):
        if attrs.get("src") or attrs.get("type") in {"application/json", "application/ld+json"} or not source.strip():
            continue
        with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8", delete=False) as handle:
            handle.write(source)
            path = Path(handle.name)
        try:
            result = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True, timeout=15)
            if result.returncode:
                detail = (result.stderr or result.stdout).strip().splitlines()[-1]
                violations.append(DirectHTMLViolation("JAVASCRIPT_SYNTAX", f"Inline script {index} failed node --check: {detail}"))
        except (OSError, subprocess.TimeoutExpired) as exc:
            violations.append(DirectHTMLViolation("JAVASCRIPT_CHECK_UNAVAILABLE", str(exc), "warning"))
        finally:
            path.unlink(missing_ok=True)
    return violations


def validate_html(
    html: str,
    *,
    expected_duration: float | None = None,
    physics_context: dict[str, Any] | None = None,
    full_lesson: bool | None = None,
) -> list[DirectHTMLViolation]:
    violations: list[DirectHTMLViolation] = []
    if not re.match(r"\s*<!doctype html>", html, flags=re.IGNORECASE):
        violations.append(DirectHTMLViolation("DOCTYPE_REQUIRED", "A complete HTML document beginning with <!doctype html> is required."))
    if len(html.encode("utf-8")) > MAX_HTML_BYTES:
        violations.append(DirectHTMLViolation("HTML_TOO_LARGE", f"HTML exceeds {MAX_HTML_BYTES} bytes."))
    parser = parse_document(html)
    missing = missing_root_ids(parser)
    if missing:
        violations.append(DirectHTMLViolation("MISSING_ROOT_IDS", f"Missing required root IDs: {', '.join(missing)}"))
    duplicates = sorted(item for item, count in Counter(parser.ids).items() if count > 1)
    if duplicates:
        violations.append(DirectHTMLViolation("DUPLICATE_IDS", f"Duplicate element IDs: {', '.join(duplicates[:12])}"))

    for required in ("DirectHTML.boot", "DirectHTML.registerChapter"):
        if required not in html:
            violations.append(DirectHTMLViolation("RUNTIME_CONTRACT", f"Generated HTML must call {required}."))
    if re.search(r"\bbuild\s*:\s*(?:async\s*)?\(\s*\{", html):
        violations.append(
            DirectHTMLViolation(
                "HYPERFRAMES_BUILD_PARAMETER",
                "Chapter builders must use build: function (chapter) with local variables; destructured parameters break HyperFrames scoping.",
            )
        )
    if "direct_html_master" not in html:
        violations.append(DirectHTMLViolation("TIMELINE_ID", "Generated HTML must declare the direct_html_master timeline ID."))

    chapters = extract_chapter_blocks(html)
    if not chapters:
        violations.append(DirectHTMLViolation("CHAPTERS_REQUIRED", "No exact BEGIN/END CHAPTER blocks were found."))
    chapter_ids = [chapter.chapter_id for chapter in chapters]
    if len(chapter_ids) != len(set(chapter_ids)):
        violations.append(DirectHTMLViolation("DUPLICATE_CHAPTER", "Chapter IDs must be unique."))
    inferred_full = bool(expected_duration and expected_duration >= 180) if full_lesson is None else full_lesson
    if inferred_full and not 6 <= len(chapters) <= 8:
        violations.append(DirectHTMLViolation("CHAPTER_COUNT", f"A full lesson requires 6–8 chapters; found {len(chapters)}."))
    ordered = sorted(chapters, key=lambda chapter: chapter.start)
    for index, chapter in enumerate(ordered):
        if chapter.start < 0 or chapter.end <= chapter.start:
            violations.append(DirectHTMLViolation("CHAPTER_TIMING", "Chapter has invalid data-start/data-end.", chapter_id=chapter.chapter_id))
        if f'id: "{chapter.chapter_id}"' not in chapter.source and f"id: '{chapter.chapter_id}'" not in chapter.source:
            violations.append(DirectHTMLViolation("CHAPTER_REGISTRATION", "Chapter registration must preserve its exact ID.", chapter_id=chapter.chapter_id))
        if index and abs(chapter.start - ordered[index - 1].end) > 0.11:
            violations.append(DirectHTMLViolation("CHAPTER_COVERAGE", f"Gap or overlap between {ordered[index - 1].chapter_id} and {chapter.chapter_id}."))
    if ordered and expected_duration is not None:
        if abs(ordered[0].start) > 0.1 or abs(ordered[-1].end - expected_duration) > 0.11:
            violations.append(DirectHTMLViolation("DURATION_MISMATCH", f"Chapter range must cover 0–{expected_duration:.3f}s."))

    for pattern in FORBIDDEN_SOURCE_PATTERNS:
        if pattern.lower() in html.lower():
            violations.append(DirectHTMLViolation("FORBIDDEN_API", f"Forbidden generated source pattern: {pattern}"))
    remote = re.findall(r"(?:src|href)=[\"']((?:https?:)?//[^\"']+)[\"']", html, flags=re.IGNORECASE)
    if remote:
        violations.append(DirectHTMLViolation("REMOTE_ASSET", f"Remote resources are forbidden: {remote[0]}"))
    for term in LEGACY_STYLE_TERMS:
        if term.lower() in html.lower():
            violations.append(DirectHTMLViolation("LEGACY_VISUAL_STYLE", f"Legacy visual term is forbidden in direct HTML: {term}"))

    allowed_colors = {value.lower() for value in SCIENCE_TOKENS.values()}
    raw_colors = {match.lower() for match in re.findall(r"(?<!url\()#[0-9a-fA-F]{6}\b", html)}
    unexpected_colors = sorted(raw_colors - allowed_colors)
    if unexpected_colors:
        violations.append(DirectHTMLViolation("RAW_COLOR", f"Use semantic science tokens instead of raw colors: {', '.join(unexpected_colors[:8])}", "warning"))

    visual_objects = len(re.findall(r"\bdata-visual-object(?:=|\s|>)", html))
    if chapters and visual_objects == 0:
        violations.append(DirectHTMLViolation("QA_ANNOTATIONS", "At least one data-visual-object annotation is required."))
    card_count = len(re.findall(r"(?:class|id)=[\"'][^\"']*\bcard\b", html, flags=re.IGNORECASE))
    if card_count >= 3:
        violations.append(DirectHTMLViolation("REPEATED_CARD_LAYOUT", f"Found {card_count} card-like elements; direct scientific composition is required.", "warning"))

    physics_context = physics_context or {}
    values = physics_context.get("values", {}) if isinstance(physics_context.get("values"), dict) else {}
    units = physics_context.get("units", {}) if isinstance(physics_context.get("units"), dict) else {}
    for _tag, attrs in parser.tags:
        key = attrs.get("data-physics-key")
        if not key:
            continue
        if key not in values:
            violations.append(DirectHTMLViolation("UNKNOWN_PHYSICS_KEY", f"Unknown data-physics-key {key}."))
            continue
        try:
            actual = float(attrs.get("data-value", ""))
            expected = float(values[key])
        except (TypeError, ValueError):
            violations.append(DirectHTMLViolation("PHYSICS_VALUE", f"Physics value for {key} must be numeric."))
        else:
            if abs(actual - expected) > max(1e-6, abs(expected) * 1e-6):
                violations.append(DirectHTMLViolation("PHYSICS_VALUE", f"Physics value mismatch for {key}: {actual} != {expected}."))
        if key in units and attrs.get("data-unit") != str(units[key]):
            violations.append(DirectHTMLViolation("PHYSICS_UNIT", f"Physics unit mismatch for {key}."))

    violations.extend(_javascript_violations(parser))
    return violations


def validation_report(violations: list[DirectHTMLViolation]) -> dict[str, Any]:
    errors = [item for item in violations if item.severity == "error"]
    return {
        "status": "passed" if not errors else "failed",
        "error_count": len(errors),
        "warning_count": len(violations) - len(errors),
        "violations": [item.to_dict() for item in violations],
        "thresholds": {"minimum_important_text_px": MIN_IMPORTANT_TEXT_PX, "max_active_objects": MAX_ACTIVE_OBJECTS},
    }


def validate_file(path: Path, *, expected_duration: float | None = None, physics_context: dict[str, Any] | None = None, output: Path | None = None) -> dict[str, Any]:
    report = validation_report(validate_html(path.read_text(encoding="utf-8"), expected_duration=expected_duration, physics_context=physics_context))
    if output:
        write_json(output, report)
    return report
