#!/usr/bin/env python3
"""Run deterministic integrity checks against generated pilot artifacts."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path


PILOT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = PILOT_DIR / "output"
DB_PATH = OUTPUT_DIR / "pilot_index.sqlite3"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    require(DB_PATH.exists(), "Missing pilot database")
    connection = sqlite3.connect(DB_PATH)
    checks = {
        "syllabus_topics": connection.execute("SELECT COUNT(*) FROM syllabus_topics").fetchone()[0],
        "papers": connection.execute("SELECT COUNT(*) FROM papers").fetchone()[0],
        "questions": connection.execute("SELECT COUNT(*) FROM questions").fetchone()[0],
        "original_questions": connection.execute("SELECT COUNT(*) FROM original_questions").fetchone()[0],
        "fts_momentum": connection.execute("SELECT COUNT(*) FROM questions_fts WHERE questions_fts MATCH 'momentum'").fetchone()[0],
        "fts_original_density": connection.execute("SELECT COUNT(*) FROM original_questions_fts WHERE original_questions_fts MATCH 'density'").fetchone()[0],
        "unknown_topic_refs": connection.execute("SELECT COUNT(*) FROM questions q LEFT JOIN syllabus_topics s ON s.ref=q.topic_ref WHERE s.ref IS NULL").fetchone()[0],
        "bad_question_numbers": connection.execute("SELECT COUNT(*) FROM questions WHERE question_number NOT BETWEEN 1 AND 40").fetchone()[0],
    }
    per_paper = connection.execute("SELECT id, question_count FROM papers ORDER BY id").fetchall()
    connection.close()

    require(checks["syllabus_topics"] == 58, f"Expected 58 topics, got {checks['syllabus_topics']}")
    require(checks["papers"] == 4, f"Expected 4 papers, got {checks['papers']}")
    require(checks["questions"] == 160, f"Expected 160 questions, got {checks['questions']}")
    require(checks["original_questions"] == 5, f"Expected 5 originals, got {checks['original_questions']}")
    require(checks["fts_momentum"] > 0, "FTS search returned no momentum questions")
    require(checks["fts_original_density"] >= 1, "Original-question FTS density check failed")
    require(checks["unknown_topic_refs"] == 0, "Questions contain unknown topic references")
    require(checks["bad_question_numbers"] == 0, "Question numbers are outside 1-40")
    require(all(count == 40 for _paper, count in per_paper), f"A paper does not contain 40 questions: {per_paper}")

    specs = sorted((OUTPUT_DIR / "mav_specs").glob("*.json"))
    require(len(specs) == 5, f"Expected 5 MAV specs, got {len(specs)}")
    for path in specs:
        spec = json.loads(path.read_text(encoding="utf-8"))
        require(spec.get("$schema") == "mav-physics-video-spec-v1", f"Wrong schema in {path.name}")
        require(len(spec.get("slides", [])) >= 4, f"Too few slides in {path.name}")
        for slide in spec["slides"]:
            require(slide.get("scene", "").startswith("Scene_"), f"Invalid scene in {path.name}")
            require(slide.get("duration", 0) >= 2, f"Invalid duration in {path.name}")
            require(bool(slide.get("narration")), f"Missing narration in {path.name}")

    for required in ("analysis.json", "content_plan.json", "original_questions.json", "pilot_report.md", "review_queue.csv", "syllabus_topics.json"):
        require((OUTPUT_DIR / required).exists(), f"Missing output/{required}")

    print("Pilot verification passed")
    for key, value in checks.items():
        print(f"  {key}: {value}")
    for paper, count in per_paper:
        print(f"  {paper}: {count} questions")
    print(f"  mav_specs: {len(specs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
