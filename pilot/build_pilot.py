#!/usr/bin/env python3
"""Build the private 0625 searchable-index and content-planning pilot."""

from __future__ import annotations

import argparse
import ast
import csv
import json
import math
import re
import shutil
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from topics import DOMAINS, TOPICS, TOPIC_TITLE, classify_question_metadata, classify_topic


PILOT_DIR = Path(__file__).resolve().parent
REPO_DIR = PILOT_DIR.parent
CONFIG_DIR = PILOT_DIR / "config"
OUTPUT_DIR = PILOT_DIR / "output"
DB_PATH = OUTPUT_DIR / "pilot_index.sqlite3"
SYLLABUS_PATH = REPO_DIR / "697209-2026-2028-syllabus.pdf"


SEASONS = {"m": "March", "s": "May/June", "w": "October/November"}
PAPER_RE = re.compile(r"0625_([msw])(\d{2})_qp_(\d{2})\.pdf$", re.IGNORECASE)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def clean_line(line: str) -> str:
    return " ".join(line.replace("\u00a0", " ").replace("\uf062", "β").split())


def topic_heading_ref(line: str) -> str | None:
    lower = line.lower().replace("–", "-")
    for ref, title in sorted(TOPICS, key=lambda item: len(item[0]), reverse=True):
        if lower.startswith(f"{ref} {title.lower()}"):
            return ref
    return None


def objective_records(lines: list[str]) -> tuple[list[dict], list[dict]]:
    records = {"Core": [], "Supplement": []}
    mode: str | None = None
    current: dict | None = None

    def finish() -> None:
        nonlocal current
        if current and mode:
            current["text"] = " ".join(current["parts"]).strip()
            current.pop("parts", None)
            if len(current["text"]) >= 8:
                records[mode].append(current)
        current = None

    for line in lines:
        if line in {"Core", "Supplement"}:
            finish()
            mode = line
            continue
        if line == "Core Supplement":
            finish()
            mode = "Core"
            continue
        if not mode or line.endswith("continued") or line.startswith("Cambridge IGCSE"):
            continue
        match = re.match(r"^(\d+)\s+(.+)$", line)
        if match and int(match.group(1)) <= 20 and len(re.findall(r"[A-Za-z]{2,}", match.group(2))) >= 2:
            finish()
            current = {"number": int(match.group(1)), "parts": [match.group(2)]}
        elif current:
            current["parts"].append(line)
    finish()

    for level in records:
        unique = []
        seen = set()
        for item in records[level]:
            key = (item["number"], item["text"])
            if key not in seen:
                unique.append(item)
                seen.add(key)
        records[level] = unique
    return records["Core"], records["Supplement"]


def extract_syllabus() -> list[dict]:
    reader = PdfReader(str(SYLLABUS_PATH))
    collected: dict[str, list[str]] = defaultdict(list)
    pages_by_ref: dict[str, set[int]] = defaultdict(set)
    current_ref: str | None = None

    for page_index in range(11, 41):
        text = reader.pages[page_index].extract_text() or ""
        for raw in text.splitlines():
            line = clean_line(raw)
            if not line:
                continue
            if line.startswith("Cambridge IGCSE Physics") or line.startswith("www.cambridgeinternational"):
                continue
            if line in {"Back to contents page", str(page_index + 1)}:
                continue
            heading = topic_heading_ref(line)
            if heading:
                current_ref = heading
                pages_by_ref[current_ref].add(page_index + 1)
                continue
            if current_ref:
                collected[current_ref].append(line)
                pages_by_ref[current_ref].add(page_index + 1)

    topics = []
    for ref, title in TOPICS:
        core, supplement = objective_records(collected.get(ref, []))
        topics.append(
            {
                "ref": ref,
                "title": title,
                "domain_ref": ref.split(".")[0],
                "domain_title": DOMAINS[ref.split(".")[0]],
                "core_objectives": core,
                "supplement_objectives": supplement,
                "source_pages": sorted(pages_by_ref.get(ref, [])),
                "extraction_review_required": not core and not supplement,
            }
        )
    return topics


def paper_metadata(path: Path) -> dict:
    match = PAPER_RE.match(path.name)
    if not match:
        raise ValueError(f"Unsupported paper filename: {path.name}")
    season_code, year_2, paper_code = match.groups()
    return {
        "id": path.stem,
        "year": 2000 + int(year_2),
        "season": SEASONS[season_code.lower()],
        "component": int(paper_code[0]),
        "variant": int(paper_code[1]),
        "paper_code": paper_code,
        "path": str(path.relative_to(REPO_DIR)),
    }


def extract_paper_questions(path: Path) -> list[dict]:
    reader = PdfReader(str(path))
    lines: list[tuple[int, str]] = []
    for page_number, page in enumerate(reader.pages[1:], start=2):
        for raw in (page.extract_text() or "").splitlines():
            line = clean_line(raw)
            if not line or line == str(page_number) or line == "[Turn over":
                continue
            if line.startswith("© UCLES") or line.startswith("Permission to reproduce"):
                continue
            if line.startswith("Cambridge Assessment International Education"):
                continue
            if line in {"BLANK PAGE", "DO NOT WRITE IN THIS MARGIN"}:
                continue
            lines.append((page_number, line))

    starts = []
    expected = 1
    for index, (page_number, line) in enumerate(lines):
        match = re.match(rf"^{expected}\s+(.+)$", line)
        if not match:
            continue
        if len(re.findall(r"[A-Za-z]{2,}", match.group(1))) < 2:
            continue
        starts.append((expected, page_number, index))
        expected += 1
        if expected == 41:
            break

    if len(starts) != 40:
        raise RuntimeError(f"Expected 40 questions in {path.name}; extracted {len(starts)}")

    results = []
    for position, (number, page_start, start_index) in enumerate(starts):
        end_index = starts[position + 1][2] if position + 1 < len(starts) else len(lines)
        block = lines[start_index:end_index]
        page_end = max(page for page, _line in block)
        first_line = re.sub(rf"^{number}\s+", "", block[0][1], count=1)
        block_lines = [first_line, *[line for _page, line in block[1:]]]
        raw_text = "\n".join(block_lines).strip()
        normalized = " ".join(raw_text.split())
        topic = classify_topic(normalized, number)
        extra = classify_question_metadata(normalized)
        review_required = topic["confidence"] < 0.6 or topic["classification_method"] == "position-only"
        if extra["has_visual"] and topic["confidence"] < 0.72:
            review_required = True
        results.append(
            {
                "question_number": number,
                "page_start": page_start,
                "page_end": page_end,
                "raw_text": raw_text,
                "normalized_text": normalized,
                **topic,
                **extra,
                "marks": 1,
                "component_level": "Extended",
                "objective_level": "unverified",
                "review_required": review_required,
            }
        )
    return results


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE syllabus_topics (
  ref TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  domain_ref TEXT NOT NULL,
  domain_title TEXT NOT NULL,
  core_objectives_json TEXT NOT NULL,
  supplement_objectives_json TEXT NOT NULL,
  source_pages_json TEXT NOT NULL,
  extraction_review_required INTEGER NOT NULL
);
CREATE TABLE papers (
  id TEXT PRIMARY KEY,
  year INTEGER NOT NULL,
  season TEXT NOT NULL,
  component INTEGER NOT NULL,
  variant INTEGER NOT NULL,
  paper_code TEXT NOT NULL,
  path TEXT NOT NULL,
  question_count INTEGER NOT NULL
);
CREATE TABLE questions (
  id TEXT PRIMARY KEY,
  paper_id TEXT NOT NULL REFERENCES papers(id),
  year INTEGER NOT NULL,
  season TEXT NOT NULL,
  component INTEGER NOT NULL,
  variant INTEGER NOT NULL,
  question_number INTEGER NOT NULL,
  page_start INTEGER NOT NULL,
  page_end INTEGER NOT NULL,
  raw_text TEXT NOT NULL,
  normalized_text TEXT NOT NULL,
  topic_ref TEXT NOT NULL REFERENCES syllabus_topics(ref),
  domain_ref TEXT NOT NULL,
  component_level TEXT NOT NULL,
  objective_level TEXT NOT NULL,
  ao TEXT NOT NULL,
  command_word TEXT NOT NULL,
  marks INTEGER NOT NULL,
  difficulty TEXT NOT NULL,
  question_type TEXT NOT NULL,
  has_visual INTEGER NOT NULL,
  confidence REAL NOT NULL,
  review_required INTEGER NOT NULL,
  classification_method TEXT NOT NULL,
  matched_patterns_json TEXT NOT NULL,
  UNIQUE(paper_id, question_number)
);
CREATE VIRTUAL TABLE questions_fts USING fts5(
  question_id UNINDEXED, raw_text, topic_ref, topic_title, domain_title,
  tokenize='porter unicode61'
);
CREATE TABLE original_questions (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  syllabus_refs_json TEXT NOT NULL,
  level TEXT NOT NULL,
  ao TEXT NOT NULL,
  command_word TEXT NOT NULL,
  question_type TEXT NOT NULL,
  question TEXT NOT NULL,
  options_json TEXT,
  answer TEXT NOT NULL,
  solution TEXT NOT NULL,
  verification_json TEXT NOT NULL,
  originality_notes TEXT NOT NULL,
  review_status TEXT NOT NULL,
  mav_spec TEXT NOT NULL
);
CREATE VIRTUAL TABLE original_questions_fts USING fts5(
  question_id UNINDEXED, title, question, solution, syllabus_refs,
  tokenize='porter unicode61'
);
CREATE INDEX questions_topic_idx ON questions(topic_ref);
CREATE INDEX questions_paper_idx ON questions(paper_id);
CREATE INDEX questions_review_idx ON questions(review_required);
"""


ALLOWED_BINOPS = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b, ast.Div: lambda a, b: a / b, ast.Pow: lambda a, b: a**b}
ALLOWED_UNARY = {ast.UAdd: lambda a: a, ast.USub: lambda a: -a}


def safe_eval(expression: str) -> float:
    def visit(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in ALLOWED_BINOPS:
            return ALLOWED_BINOPS[type(node.op)](visit(node.left), visit(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in ALLOWED_UNARY:
            return ALLOWED_UNARY[type(node.op)](visit(node.operand))
        raise ValueError(f"Unsafe numeric expression: {expression}")

    return visit(ast.parse(expression, mode="eval"))


def verify_original_question(item: dict) -> list[str]:
    verification = item["verification"]
    failures = []
    tolerance = verification.get("tolerance", 1e-9)
    if verification["type"] == "numeric":
        actual = safe_eval(verification["expression"])
        if not math.isclose(actual, verification["expected"], abs_tol=tolerance, rel_tol=tolerance):
            failures.append(f"{item['id']}: numeric result {actual} != {verification['expected']}")
    elif verification["type"] == "multi_numeric":
        for check in verification["checks"]:
            actual = safe_eval(check["expression"])
            if not math.isclose(actual, check["expected"], abs_tol=tolerance, rel_tol=tolerance):
                failures.append(f"{item['id']}: numeric result {actual} != {check['expected']}")
    elif verification["type"] == "exact" and str(item["answer"]) != str(verification["expected"]):
        failures.append(f"{item['id']}: exact answer mismatch")
    elif verification["type"] == "required_concepts":
        answer = item["answer"].lower()
        missing = [concept for concept in verification["concepts"] if concept.lower() not in answer]
        if missing:
            failures.append(f"{item['id']}: answer is missing required concepts: {missing}")
    return failures


def title_slide(title: str, subtitle: str, narration: str) -> dict:
    return {
        "scene": "Scene_TitleCard",
        "label": "Introduction",
        "duration": 5,
        "narration": narration,
        "params": {"title": title, "subtitle": subtitle, "badge": "IGCSE Physics 0625"},
    }


def summary_slide(points: list[str], narration: str) -> dict:
    return {
        "scene": "Scene_SummaryCard",
        "label": "Retrieval summary",
        "duration": 6,
        "narration": narration,
        "params": {"heading": "Pause and recall", "points": points},
    }


def make_mav_specs() -> dict[str, dict]:
    specs: dict[str, dict] = {}
    specs["01-scalars-vectors.json"] = {
        "$schema": "mav-physics-video-spec-v1",
        "title": "Scalars and vectors",
        "totalDuration": "auto",
        "slides": [
            title_slide("Scalars and vectors", "Magnitude alone, or magnitude with direction?", "A drone can report how fast it moves, but navigation also needs a direction."),
            {"scene": "Scene_ComparisonTable", "label": "Compare", "duration": 7, "narration": "Scalars have magnitude only. Vectors have both magnitude and direction.", "params": {"heading1": "Scalar", "heading2": "Vector", "rows": [{"col1": "time", "col2": "displacement"}, {"col1": "energy", "col2": "velocity"}, {"col1": "speed", "col2": "force"}]}},
            {"scene": "Scene_DefinitionCard", "label": "Exam idea", "duration": 6, "narration": "Direction is the deciding feature. Displacement and velocity are both vectors.", "params": {"term": "Vector", "definition": "A quantity with both magnitude and direction.", "example": "The drone moves at 6 metres per second north."}},
            summary_slide(["A scalar has magnitude only", "A vector also has direction", "Displacement and velocity are vectors"], "Which two quantities in the drone problem require a direction?"),
        ],
    }
    specs["02-density-worked-example.json"] = {
        "$schema": "mav-physics-video-spec-v1",
        "title": "Density worked example",
        "totalDuration": "auto",
        "slides": [
            title_slide("Density without guesswork", "Mass divided by volume", "Let us calculate the density of a ceramic sample and keep every unit consistent."),
            {"scene": "Scene_MathEquation", "label": "Equation", "duration": 6, "narration": "Density equals mass divided by volume.", "params": {"equation": "\\rho = \\frac{m}{V}", "highlight": "\\rho", "caption": "Use kilograms and cubic metres for kilograms per cubic metre."}},
            {"scene": "Scene_NumericalExample", "label": "Worked solution", "duration": 8, "narration": "Substitute zero point three six zero kilograms and one point five times ten to the minus four cubic metres.", "params": {"title": "Ceramic sample", "steps": [{"label": "Write", "content": "density = mass / volume"}, {"label": "Substitute", "content": "0.360 / (1.50 x 10^-4)"}, {"label": "Calculate", "content": "density = 2400 kg/m^3"}]}},
            summary_slide(["Write the equation first", "Keep the units consistent", "Give the unit with the answer"], "The sample density is two thousand four hundred kilograms per cubic metre."),
        ],
    }
    specs["03-convection-explanation.json"] = {
        "$schema": "mav-physics-video-spec-v1",
        "title": "Convection in a greenhouse",
        "totalDuration": "auto",
        "slides": [
            title_slide("Why warm air rises", "Convection in a greenhouse", "A heater near the floor creates a continuous circulation of air."),
            {"scene": "Scene_ParticleModel", "label": "Particle model", "duration": 8, "narration": "Air near the heater gains energy. Its particles move faster and spread out, reducing the density.", "params": {"state": "gas", "temperature": "high", "containerType": "box", "particleCount": 42, "showEnergyLabel": True}},
            {"scene": "Scene_DefinitionCard", "label": "Convection current", "duration": 7, "narration": "Warmer, less dense air rises while cooler, denser air moves down to replace it.", "params": {"term": "Convection current", "definition": "A circulation caused by density differences in a fluid.", "example": "Warm air rises above the heater and cooler air returns near the floor."}},
            summary_slide(["Heating makes the air expand", "Expanded air is less dense and rises", "Cooler air replaces it and circulation continues"], "Explain the movement using energy, density and circulation."),
        ],
    }
    specs["04-speed-time-graph.json"] = {
        "$schema": "mav-physics-video-spec-v1",
        "title": "Speed-time graph challenge",
        "totalDuration": "auto",
        "slides": [
            title_slide("Read the whole journey", "Acceleration and area from one graph", "The gradient gives acceleration, while the area under the graph gives distance."),
            {"scene": "Scene_GraphPlotter", "label": "Journey graph", "duration": 9, "narration": "The bicycle reaches eight metres per second in four seconds, travels steadily, and then stops.", "params": {"title": "Electric bicycle journey", "xAxis": {"label": "time", "min": 0, "max": 12, "unit": "s"}, "yAxis": {"label": "speed", "min": 0, "max": 10, "unit": "m/s"}, "curves": [{"label": "speed", "color": "velocity", "style": "solid", "dataPoints": [[0, 0], [4, 8], [10, 8], [12, 0]]}], "annotations": [{"x": 4, "y": 8, "text": "8 m/s after 4 s"}]}},
            {"scene": "Scene_NumericalExample", "label": "Calculate", "duration": 9, "narration": "Acceleration is eight divided by four. Distance is the sum of two triangles and one rectangle.", "params": {"title": "Gradient and area", "steps": [{"label": "Acceleration", "content": "8 / 4 = 2.0 m/s^2"}, {"label": "First triangle", "content": "0.5 x 4 x 8 = 16 m"}, {"label": "Rectangle", "content": "6 x 8 = 48 m"}, {"label": "Final triangle", "content": "0.5 x 2 x 8 = 8 m"}, {"label": "Total", "content": "16 + 48 + 8 = 72 m"}]}},
            summary_slide(["Gradient gives acceleration", "Area gives distance", "Split a complex area into simple shapes"], "Pause and calculate the two answers again without looking."),
        ],
    }
    specs["05-pendulum-practical.json"] = {
        "$schema": "mav-physics-video-spec-v1",
        "title": "Pendulum period practical",
        "totalDuration": "auto",
        "slides": [
            title_slide("Measure a short period", "Time many oscillations, then divide", "A single swing is too short for reliable manual timing, so we measure many oscillations."),
            {"scene": "Scene_GraphPlotter", "label": "Repeated readings", "duration": 8, "narration": "Three repeated timings for fifteen oscillations are close together, with a mean of eighteen point five seconds.", "params": {"title": "Time for 15 oscillations", "xAxis": {"label": "trial", "min": 1, "max": 3, "unit": ""}, "yAxis": {"label": "time", "min": 18, "max": 19, "unit": "s"}, "curves": [{"label": "reading", "color": "label", "style": "solid", "dataPoints": [[1, 18.6], [2, 18.4], [3, 18.5]]}], "annotations": [{"x": 3, "y": 18.5, "text": "mean = 18.5 s"}]}},
            {"scene": "Scene_NumericalExample", "label": "Mean period", "duration": 9, "narration": "Average the repeated timings, then divide by fifteen to find the period of one oscillation.", "params": {"title": "Calculate the period", "steps": [{"label": "Mean time", "content": "(18.6 + 18.4 + 18.5) / 3"}, {"label": "Mean", "content": "time for 15 = 18.5 s"}, {"label": "One oscillation", "content": "period = 18.5 / 15"}, {"label": "Answer", "content": "period = 1.23 s"}]}},
            summary_slide(["Repeat the timing", "Time many oscillations", "Divide the mean time by the number of oscillations"], "Timing many oscillations reduces the percentage effect of reaction time."),
        ],
    }
    return specs


def build_database(syllabus_topics: list[dict], paper_rows: list[tuple[dict, list[dict]]], originals: list[dict]) -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()
    connection = sqlite3.connect(DB_PATH)
    connection.executescript(SCHEMA)
    now = datetime.now(timezone.utc).isoformat()
    metadata = {
        "built_at": now,
        "syllabus": SYLLABUS_PATH.name,
        "privacy": "Past-paper text is private research data and must not be published.",
        "classification": "Deterministic pilot labels; low-confidence rows require teacher review.",
    }
    connection.executemany("INSERT INTO metadata(key, value) VALUES (?, ?)", metadata.items())

    for topic in syllabus_topics:
        connection.execute(
            "INSERT INTO syllabus_topics VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                topic["ref"], topic["title"], topic["domain_ref"], topic["domain_title"],
                json.dumps(topic["core_objectives"], ensure_ascii=False),
                json.dumps(topic["supplement_objectives"], ensure_ascii=False),
                json.dumps(topic["source_pages"]), int(topic["extraction_review_required"]),
            ),
        )

    for paper, questions in paper_rows:
        connection.execute(
            "INSERT INTO papers VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (paper["id"], paper["year"], paper["season"], paper["component"], paper["variant"], paper["paper_code"], paper["path"], len(questions)),
        )
        for question in questions:
            question_id = f"{paper['id']}-q{question['question_number']:02d}"
            connection.execute(
                """INSERT INTO questions (
                    id, paper_id, year, season, component, variant, question_number,
                    page_start, page_end, raw_text, normalized_text, topic_ref, domain_ref,
                    component_level, objective_level, ao, command_word, marks, difficulty,
                    question_type, has_visual, confidence, review_required,
                    classification_method, matched_patterns_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    question_id, paper["id"], paper["year"], paper["season"], paper["component"], paper["variant"],
                    question["question_number"], question["page_start"], question["page_end"], question["raw_text"], question["normalized_text"],
                    question["topic_ref"], question["domain_ref"], question["component_level"], question["objective_level"], question["ao"],
                    question["command_word"], question["marks"], question["difficulty"], question["question_type"], int(question["has_visual"]),
                    question["confidence"], int(question["review_required"]), question["classification_method"], json.dumps(question["matched_patterns"]),
                ),
            )
            connection.execute(
                "INSERT INTO questions_fts VALUES (?, ?, ?, ?, ?)",
                (question_id, question["raw_text"], question["topic_ref"], TOPIC_TITLE[question["topic_ref"]], DOMAINS[question["domain_ref"]]),
            )

    for item in originals:
        connection.execute(
            "INSERT INTO original_questions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                item["id"], item["title"], json.dumps(item["syllabus_refs"]), item["level"], item["ao"], item["command_word"], item["question_type"],
                item["question"], json.dumps(item.get("options"), ensure_ascii=False) if item.get("options") else None, str(item["answer"]), item["solution"],
                json.dumps(item["verification"], ensure_ascii=False), item["originality_notes"], item["review_status"], item["mav_spec"],
            ),
        )
        connection.execute(
            "INSERT INTO original_questions_fts VALUES (?, ?, ?, ?, ?)",
            (item["id"], item["title"], item["question"], item["solution"], " ".join(item["syllabus_refs"])),
        )
    connection.commit()
    connection.close()


def generate_outputs(syllabus_topics: list[dict], paper_rows: list[tuple[dict, list[dict]]], originals: list[dict]) -> None:
    all_questions = [dict(question, paper=paper) for paper, questions in paper_rows for question in questions]
    counts = Counter(question["topic_ref"] for question in all_questions)
    domain_counts = Counter(question["domain_ref"] for question in all_questions)
    review_count = sum(question["review_required"] for question in all_questions)
    visual_count = sum(question["has_visual"] for question in all_questions)
    manual_count = sum(question["classification_method"] == "manual-pilot-review" for question in all_questions)

    analysis = {
        "scope": "Four recent Extended Paper 2 variants; this is a parser and workflow pilot, not a prediction model.",
        "question_count": len(all_questions),
        "paper_count": len(paper_rows),
        "visual_question_count": visual_count,
        "teacher_review_queue_count": review_count,
        "manual_pilot_review_count": manual_count,
        "domain_counts": [{"domain_ref": ref, "domain_title": DOMAINS[ref], "questions": domain_counts[ref]} for ref in DOMAINS],
        "topic_counts": [
            {"topic_ref": ref, "topic_title": title, "questions": counts[ref]}
            for ref, title in sorted(TOPICS, key=lambda item: (-counts[item[0]], [x[0] for x in TOPICS].index(item[0])))
        ],
        "limitations": [
            "MCQ questions carry one mark each, so this pilot measures occurrence rather than full qualification mark share.",
            "Automatic text extraction cannot reconstruct every diagram.",
            "Question-to-objective level and Core/Supplement mapping remain unverified.",
            "Regional variants can test similar archetypes and must later be clustered before trend analysis.",
            "All syllabus objectives remain mandatory regardless of pilot frequency.",
        ],
    }
    write_json(OUTPUT_DIR / "analysis.json", analysis)
    write_json(OUTPUT_DIR / "syllabus_topics.json", {"syllabus": SYLLABUS_PATH.name, "topics": syllabus_topics})
    write_json(OUTPUT_DIR / "original_questions.json", originals)

    content_topics = []
    for topic in syllabus_topics:
        count = counts[topic["ref"]]
        formats = ["concept lesson"]
        if count >= 1:
            formats.append("original worked question")
        if count >= 3:
            formats.append("misconception short")
        if topic["domain_ref"] == "1" and topic["ref"] in {"1.1", "1.2", "1.4"}:
            formats.append("practical or graph skill")
        content_topics.append(
            {
                "topic_ref": topic["ref"],
                "topic_title": topic["title"],
                "domain_title": topic["domain_title"],
                "pilot_question_occurrences": count,
                "coverage_rule": "mandatory",
                "reinforcement_band": "high in pilot" if count >= 4 else "seen in pilot" if count else "not sampled; still mandatory",
                "recommended_formats": formats,
            }
        )
    content_plan = {
        "principle": "Syllabus coverage decides what is taught; past-paper analysis decides how much reinforcement it receives.",
        "assessment_balance": {"AO1": 50, "AO2": 30, "AO3": 20},
        "pilot_original_lessons": [{"question_id": item["id"], "title": item["title"], "mav_spec": item["mav_spec"]} for item in originals],
        "topics": content_topics,
    }
    write_json(OUTPUT_DIR / "content_plan.json", content_plan)

    with (OUTPUT_DIR / "review_queue.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["question_id", "paper", "question", "page", "proposed_topic", "confidence", "method", "excerpt"])
        for question in all_questions:
            if question["review_required"]:
                paper = question["paper"]
                qid = f"{paper['id']}-q{question['question_number']:02d}"
                writer.writerow([qid, paper["path"], question["question_number"], question["page_start"], question["topic_ref"], question["confidence"], question["classification_method"], question["normalized_text"][:180]])

    top_rows = sorted(((count, ref, TOPIC_TITLE[ref]) for ref, count in counts.items()), reverse=True)[:12]
    report_lines = [
        "# Pilot build report",
        "",
        f"Built {len(all_questions)} private question records from {len(paper_rows)} recent Extended Paper 2 PDFs.",
        "",
        "## What is ready",
        "",
        f"- {len(syllabus_topics)} current syllabus subtopics.",
        f"- {len(all_questions)} searchable past-paper question records.",
        f"- {visual_count} questions flagged as containing a visual, graph, table or diagram reference.",
        f"- {review_count} automatic classifications placed in the teacher-review queue.",
        f"- {manual_count} question tags corrected through the documented pilot review overrides.",
        f"- {len(originals)} newly authored pilot questions with verification metadata.",
        f"- {len(make_mav_specs())} MAV composition specifications.",
        "",
        "## Highest occurrence counts in this four-paper pilot",
        "",
        "| Topic | Proposed tag | Questions |",
        "|---|---:|---:|",
    ]
    report_lines.extend(f"| {title} | {ref} | {count} |" for count, ref, title in top_rows)
    report_lines.extend(
        [
            "",
            "These counts are parser-pilot observations, not examination predictions. All syllabus objectives remain mandatory.",
            "",
            "## Privacy and review",
            "",
            "Past-paper text in the SQLite database is private research data. Do not display or publish it. Only the newly authored questions and teacher-approved explanations are intended for public content.",
            "",
            "Automatic labels are starting points. Review every row in `review_queue.csv` and sample high-confidence rows before using aggregate results.",
            "",
        ]
    )
    (OUTPUT_DIR / "pilot_report.md").write_text("\n".join(report_lines), encoding="utf-8")

    specs_dir = OUTPUT_DIR / "mav_specs"
    specs_dir.mkdir(parents=True, exist_ok=True)
    for filename, spec in make_mav_specs().items():
        write_json(specs_dir / filename, spec)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clean", action="store_true", help="Remove the existing pilot output before rebuilding.")
    args = parser.parse_args()
    if args.clean and OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not SYLLABUS_PATH.exists():
        raise SystemExit(f"Missing syllabus: {SYLLABUS_PATH}")
    syllabus_topics = extract_syllabus()
    paper_paths = [REPO_DIR / relative for relative in read_json(CONFIG_DIR / "pilot_papers.json")]
    missing = [str(path) for path in paper_paths if not path.exists()]
    if missing:
        raise SystemExit(f"Missing pilot papers: {missing}")

    paper_rows = []
    overrides = read_json(CONFIG_DIR / "manual_overrides.json")
    for path in paper_paths:
        paper = paper_metadata(path)
        questions = extract_paper_questions(path)
        for question in questions:
            question_id = f"{paper['id']}-q{question['question_number']:02d}"
            if question_id in overrides:
                override = overrides[question_id]
                question["topic_ref"] = override["topic_ref"]
                question["domain_ref"] = override["topic_ref"].split(".")[0]
                question["confidence"] = 1.0
                question["classification_method"] = "manual-pilot-review"
                question["matched_patterns"] = [override["reason"]]
                question["review_required"] = False
        paper_rows.append((paper, questions))
    originals = read_json(CONFIG_DIR / "original_questions.json")
    failures = [failure for item in originals for failure in verify_original_question(item)]
    if failures:
        raise SystemExit("Original-question verification failed:\n" + "\n".join(failures))

    build_database(syllabus_topics, paper_rows, originals)
    generate_outputs(syllabus_topics, paper_rows, originals)
    print(f"Built {DB_PATH.relative_to(REPO_DIR)}")
    print(f"Indexed {sum(len(questions) for _paper, questions in paper_rows)} questions from {len(paper_rows)} papers")
    print(f"Generated {len(syllabus_topics)} syllabus topics and {len(originals)} original questions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
