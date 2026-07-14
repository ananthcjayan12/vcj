#!/usr/bin/env python3
"""Verify the generated 10-year Papers 1-6 question index and screenshots."""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from PIL import Image


PILOT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = PILOT_DIR / "index_output"
DB_PATH = OUTPUT_DIR / "question_index.sqlite3"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    require(DB_PATH.exists(), f"Missing {DB_PATH}")
    connection = sqlite3.connect(DB_PATH)
    metadata = dict(connection.execute("SELECT key, value FROM metadata"))
    paper_count = connection.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
    question_count = connection.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    fts_count = connection.execute("SELECT COUNT(*) FROM questions_fts").fetchone()[0]
    bad_papers = connection.execute(
        """SELECT id, component, question_count FROM papers WHERE
           (component IN (1, 2) AND question_count != 40) OR
           (component = 3 AND question_count NOT BETWEEN 10 AND 12) OR
           (component = 4 AND question_count NOT BETWEEN 9 AND 12) OR
           (component = 5 AND question_count != 4) OR
           (component = 6 AND question_count NOT BETWEEN 4 AND 5)"""
    ).fetchall()
    unknown_topics = connection.execute(
        "SELECT COUNT(*) FROM questions q LEFT JOIN syllabus_topics s ON s.ref=q.topic_ref WHERE s.ref IS NULL"
    ).fetchone()[0]
    missing_paths = connection.execute("SELECT id, image_path FROM questions ORDER BY id").fetchall()
    momentum_hits = connection.execute(
        "SELECT COUNT(*) FROM questions_fts WHERE questions_fts MATCH 'momentum'"
    ).fetchone()[0]
    years = connection.execute("SELECT MIN(year), MAX(year), COUNT(DISTINCT year) FROM papers").fetchone()
    components = connection.execute(
        """SELECT p.component, p.paper_name, COUNT(DISTINCT p.id), COUNT(q.id)
           FROM papers p JOIN questions q ON q.paper_id=p.id
           GROUP BY p.component, p.paper_name ORDER BY p.component"""
    ).fetchall()
    connection.close()

    require(paper_count == int(metadata["paper_count"]), "Paper count does not match metadata")
    require(question_count == int(metadata["question_count"]), "Question count does not match metadata")
    require(fts_count == question_count, "FTS row count does not match questions")
    require(not bad_papers, f"Papers with an unexpected top-level question count: {bad_papers}")
    require([row[0] for row in components] == [1, 2, 3, 4, 5, 6], f"Missing components: {components}")
    require(unknown_topics == 0, f"Questions with unknown topic refs: {unknown_topics}")
    require(momentum_hits > 0, "FTS search found no momentum questions")
    require(years == (int(metadata["start_year"]), int(metadata["end_year"]), int(metadata["end_year"]) - int(metadata["start_year"]) + 1), f"Unexpected year coverage: {years}")

    missing_images = []
    bad_images = []
    for question_id, relative in missing_paths:
        path = OUTPUT_DIR / relative
        if not path.exists():
            missing_images.append(question_id)
            continue
        try:
            with Image.open(path) as image:
                width, height = image.size
                image.verify()
            # A withdrawn question can legitimately be a single 57 px notice.
            if width < 800 or height < 40:
                bad_images.append((question_id, width, height))
        except Exception as exc:
            bad_images.append((question_id, str(exc)))
    require(not missing_images, f"Missing question screenshots: {missing_images[:10]}")
    require(not bad_images, f"Unreadable or undersized screenshots: {bad_images[:10]}")

    csv_path = OUTPUT_DIR / "question_index.csv"
    require(csv_path.exists(), "Missing question_index.csv")
    with csv_path.open(newline="", encoding="utf-8") as handle:
        csv_count = sum(1 for _row in csv.reader(handle)) - 1
    require(csv_count == question_count, f"CSV has {csv_count} rows, expected {question_count}")
    search_path = OUTPUT_DIR / "search.html"
    require(search_path.exists(), "Missing search.html")
    search_html = search_path.read_text(encoding="utf-8")
    require('class="question-text' in search_html, "Search results do not render extracted question text")
    require("Show full text" in search_html, "Search results are missing the full-text expander")
    require((OUTPUT_DIR / "index_summary.json").exists(), "Missing index_summary.json")

    print("Question-index verification passed")
    print(f"  years: {years[0]}-{years[1]}")
    print(f"  papers: {paper_count}")
    print(f"  questions: {question_count}")
    print(f"  screenshots: {question_count}")
    print(f"  momentum search hits: {momentum_hits}")
    for component, paper_name, papers, questions in components:
        print(f"  Paper {component} {paper_name}: {papers} papers, {questions} questions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
