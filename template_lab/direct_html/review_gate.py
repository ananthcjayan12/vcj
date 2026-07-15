from __future__ import annotations

from pathlib import Path
from typing import Any

from .io_utils import write_json

REVIEW_CATEGORIES = (
    "scientific_focal_clarity",
    "visual_hierarchy_legibility",
    "modern_platform_polish",
    "meaningful_motion_continuity",
    "semantic_color_discipline",
    "teaching_value",
    "scientific_accuracy",
)


def evaluate_visual_review(payload: dict[str, Any]) -> dict[str, Any]:
    chapters = payload.get("chapters") if isinstance(payload.get("chapters"), list) else []
    failures: list[dict[str, Any]] = []
    totals = {category: 0.0 for category in REVIEW_CATEGORIES}
    valid_chapters = 0
    for chapter in chapters:
        scores = chapter.get("scores") if isinstance(chapter.get("scores"), dict) else {}
        chapter_scores: dict[str, float] = {}
        for category in REVIEW_CATEGORIES:
            try:
                value = float(scores[category])
            except (KeyError, TypeError, ValueError):
                value = 0.0
            chapter_scores[category] = value
            totals[category] += value
            if value < 1 or value > 5:
                failures.append(
                    {
                        "code": "INVALID_SCORE",
                        "chapter_id": chapter.get("chapter_id"),
                        "category": category,
                        "score": value,
                    }
                )
            if value < 3:
                failures.append(
                    {
                        "code": "CHAPTER_SCORE_BELOW_3",
                        "chapter_id": chapter.get("chapter_id"),
                        "category": category,
                        "score": value,
                    }
                )
        if chapter_scores:
            valid_chapters += 1
    averages = {
        category: round(total / valid_chapters, 3) if valid_chapters else 0.0
        for category, total in totals.items()
    }
    for category, average in averages.items():
        if average < 4:
            failures.append({"code": "CATEGORY_AVERAGE_BELOW_4", "category": category, "average": average})
    if not chapters:
        failures.append({"code": "NO_REVIEW_CHAPTERS"})
    recommendation = payload.get("overall_recommendation")
    if recommendation and recommendation != "pass":
        failures.append({"code": "REVIEW_RECOMMENDS_ACTION", "recommendation": recommendation})
    return {
        "status": "passed" if not failures else "failed",
        "chapter_count": len(chapters),
        "category_averages": averages,
        "failures": failures,
    }


def save_visual_review(run_path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    result = {**payload, "quality_gate": evaluate_visual_review(payload)}
    write_json(run_path / "direct_html" / "validation" / "visual_review.json", result)
    return result
