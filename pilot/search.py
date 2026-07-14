#!/usr/bin/env python3
"""Search the private question index from the terminal."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


PILOT_DIR = Path(__file__).resolve().parent
DB_PATH = PILOT_DIR / "index_output" / "question_index.sqlite3"
LEGACY_DB_PATH = PILOT_DIR / "output" / "pilot_index.sqlite3"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", help="Keyword or FTS5 query, for example: momentum OR impulse")
    parser.add_argument("--topic", help="Optional syllabus reference, for example 1.6")
    parser.add_argument("--year", type=int, help="Optional paper year")
    parser.add_argument("--paper", type=int, choices=range(1, 7), help="Optional paper component, 1-6")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--json", action="store_true", help="Return machine-readable JSON results")
    parser.add_argument("--original", action="store_true", help="Search newly authored questions instead of private past-paper text")
    args = parser.parse_args()
    database_path = LEGACY_DB_PATH if args.original else DB_PATH
    if not database_path.exists():
        command = "pilot/build_pilot.py" if args.original else "pilot/build_question_index.py"
        raise SystemExit(f"Database does not exist. Run ./.venv/bin/python {command} --clean first.")

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    if args.original:
        rows = connection.execute(
            """
            SELECT o.id, o.title, o.question, o.answer, o.syllabus_refs_json
            FROM original_questions_fts f
            JOIN original_questions o ON o.id = f.question_id
            WHERE original_questions_fts MATCH ?
            LIMIT ?
            """,
            (args.query, args.limit),
        ).fetchall()
        if args.json:
            print(json.dumps([dict(row) for row in rows], indent=2, ensure_ascii=False))
        else:
            for row in rows:
                print(f"{row['id']} | {row['title']} | syllabus {row['syllabus_refs_json']}")
                print(f"  {row['question']}")
                print(f"  Answer: {row['answer']}\n")
    else:
        filters = ["questions_fts MATCH ?"]
        values: list[object] = [args.query]
        if args.topic:
            filters.append("q.topic_ref = ?")
            values.append(args.topic)
        if args.year:
            filters.append("q.year = ?")
            values.append(args.year)
        if args.paper:
            filters.append("q.component = ?")
            values.append(args.paper)
        values.append(args.limit)
        rows = connection.execute(
            f"""
            SELECT q.id, q.year, q.season, q.component, p.paper_code, p.paper_name,
                   q.question_number, q.marks, q.page_start,
                   q.topic_ref, s.title AS topic_title, q.confidence, q.image_path,
                   snippet(questions_fts, 1, '[', ']', ' … ', 24) AS excerpt
            FROM questions_fts
            JOIN questions q ON q.id = questions_fts.question_id
            JOIN papers p ON p.id = q.paper_id
            JOIN syllabus_topics s ON s.ref = q.topic_ref
            WHERE {' AND '.join(filters)}
            ORDER BY bm25(questions_fts), q.year DESC
            LIMIT ?
            """,
            values,
        ).fetchall()
        if args.json:
            payload = []
            for row in rows:
                item = dict(row)
                item["image_url"] = (database_path.parent / row["image_path"]).resolve().as_uri()
                payload.append(item)
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            for row in rows:
                image_url = (database_path.parent / row["image_path"]).resolve().as_uri()
                print(f"{row['id']} | {row['topic_ref']} {row['topic_title']} | confidence {row['confidence']:.2f}")
                marks = f" · {row['marks']} marks" if row["marks"] else ""
                print(
                    f"  {row['year']} {row['season']} · Paper {row['paper_code']} "
                    f"{row['paper_name']} · Q{row['question_number']}{marks} · page {row['page_start']}"
                )
                print(f"  {row['excerpt']}")
                print(f"  Image: {image_url}\n")
    connection.close()
    if not args.json:
        print(f"{len(rows)} result(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
