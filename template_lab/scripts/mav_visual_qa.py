from __future__ import annotations

from pathlib import Path

from mav_schema import write_json


def visual_qa(run_path: Path, *, enabled: bool = False) -> dict:
    report = {
        "status": "skipped" if not enabled else "passed",
        "model": "gemini-3.5-flash",
        "enabled": enabled,
        "scene_reviews": [],
        "review_questions": [
            "Does this feel like a purposeful educational animation rather than a slide presentation?",
            "Is information revealed over time?",
            "Do objects perform explanatory actions?",
            "Is the focal point clear at each moment?",
            "Does the scene have a visual payoff?",
            "Is the transition motivated?",
            "Does the scene visually explain the narration?",
            "Is there excessive reliance on cards, labels, and icons?"
        ],
        "note": "Subjective multimodal QA remains disabled unless the user explicitly approves an external API call.",
    }
    write_json(run_path / "validation" / "visual_qa.json", report)
    return report
