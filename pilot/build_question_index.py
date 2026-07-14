#!/usr/bin/env python3
"""Build a private, searchable 10-year index for Papers 1-6 with screenshots."""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pdfplumber
from PIL import Image

from build_pilot import extract_syllabus
from topics import DOMAINS, TOPICS, TOPIC_TITLE, classify_question_metadata, classify_topic


PILOT_DIR = Path(__file__).resolve().parent
REPO_DIR = PILOT_DIR.parent
PAPERS_DIR = REPO_DIR / "CAIE_IGCSE_Physics_0625_Question_Papers"
OUTPUT_DIR = PILOT_DIR / "index_output"
DB_PATH = OUTPUT_DIR / "question_index.sqlite3"
IMAGE_DIR = OUTPUT_DIR / "question_images"
CONFIG_DIR = PILOT_DIR / "config"

DEFAULT_START_YEAR = 2016
DEFAULT_END_YEAR = 2025
RENDER_DPI = 144

SEASONS = {"m": "March", "s": "May/June", "w": "October/November"}
PAPER_RE = re.compile(r"^0625_([msw])(\d{2})_qp_([1-6][1-3])\.pdf$", re.IGNORECASE)
CID_RE = re.compile(r"\(cid:\d+\)")
PAPER_DETAILS = {
    1: {"name": "Multiple Choice (Core)", "route": "Core"},
    2: {"name": "Multiple Choice (Extended)", "route": "Extended"},
    3: {"name": "Theory (Core)", "route": "Core"},
    4: {"name": "Theory (Extended)", "route": "Extended"},
    5: {"name": "Practical Test", "route": "Core and Extended"},
    6: {"name": "Alternative to Practical", "route": "Core and Extended"},
}
QUESTION_COUNT_RANGES = {
    1: (40, 40),
    2: (40, 40),
    3: (10, 12),
    4: (9, 12),
    5: (4, 4),
    6: (4, 5),
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def paper_metadata(path: Path) -> dict[str, Any]:
    match = PAPER_RE.match(path.name)
    if not match:
        raise ValueError(f"Unsupported question-paper filename: {path.name}")
    season_code, year_2, paper_code = match.groups()
    component = int(paper_code[0])
    return {
        "id": path.stem,
        "year": 2000 + int(year_2),
        "season": SEASONS[season_code.lower()],
        "component": component,
        "variant": int(paper_code[1]),
        "paper_code": paper_code,
        "paper_name": PAPER_DETAILS[component]["name"],
        "candidate_route": PAPER_DETAILS[component]["route"],
        "path": str(path.relative_to(REPO_DIR)),
    }


def discover_papers(start_year: int, end_year: int) -> list[Path]:
    papers: list[tuple[int, int, int, Path]] = []
    season_order = {"m": 0, "s": 1, "w": 2}
    for path in PAPERS_DIR.rglob("0625_*_qp_??.pdf"):
        match = PAPER_RE.match(path.name)
        if not match:
            continue
        season_code, year_2, paper_code = match.groups()
        year = 2000 + int(year_2)
        if start_year <= year <= end_year:
            papers.append((year, season_order[season_code.lower()], int(paper_code), path))
    return [item[-1] for item in sorted(papers)]


def clean_extracted_text(text: str) -> str:
    text = CID_RE.sub(" ", text)
    kept: list[str] = []
    for raw in text.splitlines():
        line = " ".join(raw.replace("\u00a0", " ").split())
        if not line:
            continue
        if line.startswith(("© UCLES", "Permission to reproduce", "Cambridge Assessment")):
            continue
        if line in {"[Turn over", "BLANK PAGE", "DO NOT WRITE IN THIS MARGIN"}:
            continue
        if set(line) <= {"*", " ", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9"} and "*" in line:
            continue
        if line in {"NIGRAM", "SIHT", "NI", "ETIRW", "TON", "OD"}:
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def find_question_starts(
    pdf: pdfplumber.PDF,
    page_words: list[list[dict[str, Any]]],
    path: Path,
    component: int,
) -> list[dict[str, Any]]:
    starts: list[dict[str, Any]] = []
    expected = 1
    maximum = QUESTION_COUNT_RANGES[component][1]
    for page_index, page in enumerate(pdf.pages[1:], start=1):
        words = page_words[page_index]
        candidates = sorted(words, key=lambda word: (float(word["top"]), float(word["x0"])))
        for word in candidates:
            if expected > maximum:
                break
            if word["text"] != str(expected):
                continue
            x0 = float(word["x0"])
            top = float(word["top"])
            if not (35 <= x0 <= 75 and 45 <= top <= page.height - 65):
                continue
            starts.append({"number": expected, "page_index": page_index, "top": top})
            expected += 1
        if expected > maximum:
            break
    minimum, maximum = QUESTION_COUNT_RANGES[component]
    if not minimum <= len(starts) <= maximum:
        found = [item["number"] for item in starts]
        raise RuntimeError(
            f"Expected {minimum}-{maximum} question starts in {path.name}; "
            f"found {len(starts)} ({found[-5:] if found else 'none'})"
        )
    return starts


def page_body_bottom(page: pdfplumber.page.Page, words: list[dict[str, Any]]) -> float:
    """Return the bottom of question content, above copyright/footer material."""
    bottom = page.height - 52.0
    for word in words:
        text = str(word["text"])
        top = float(word["top"])
        if top < page.height * 0.55:
            continue
        if text in {"©", "Permission"} or text.startswith("©"):
            bottom = min(bottom, top - 8.0)
    return bottom


def question_slices(
    pdf: pdfplumber.PDF,
    start: dict[str, Any],
    next_start: dict[str, Any] | None,
    body_bottoms: list[float],
) -> list[dict[str, float | int]]:
    left = 40.0
    page_index = int(start["page_index"])
    final_page_index = int(next_start["page_index"]) if next_start else page_index
    slices: list[dict[str, float | int]] = []
    for index in range(page_index, final_page_index + 1):
        page = pdf.pages[index]
        top = max(59.5, float(start["top"]) - 1.0) if index == page_index else 59.5
        bottom = body_bottoms[index]
        if next_start and index == int(next_start["page_index"]):
            bottom = min(bottom, float(next_start["top"]) - 8.0)
        if bottom - top >= 12:
            slices.append(
                {
                    "page_index": index,
                    "left": left,
                    "top": top,
                    "right": page.width - 40.0,
                    "bottom": bottom,
                }
            )
    return slices


def extract_questions(path: Path, paper: dict[str, Any]) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    with pdfplumber.open(path) as pdf:
        page_words = [
            page.extract_words(x_tolerance=2, y_tolerance=3, keep_blank_chars=False)
            for page in pdf.pages
        ]
        starts = find_question_starts(pdf, page_words, path, paper["component"])
        body_bottoms = [page_body_bottom(page, page_words[index]) for index, page in enumerate(pdf.pages)]
        for position, start in enumerate(starts):
            next_start = starts[position + 1] if position + 1 < len(starts) else None
            slices = question_slices(pdf, start, next_start, body_bottoms)
            text_parts = []
            for item in slices:
                page = pdf.pages[int(item["page_index"])]
                crop = page.crop((item["left"], item["top"], item["right"], item["bottom"]))
                text_parts.append(crop.extract_text(x_tolerance=2, y_tolerance=3) or "")
            raw_text = clean_extracted_text("\n".join(text_parts))
            normalized = " ".join(raw_text.split())
            if not normalized:
                raise RuntimeError(f"No text extracted for {paper['id']} question {start['number']}")
            topic = classify_topic(
                normalized,
                int(start["number"]),
                use_position_hint=paper["component"] in {1, 2},
            )
            extra = classify_question_metadata(normalized)
            total_match = re.search(r"\[\s*Total\s*:\s*(\d+)\s*\]", raw_text, flags=re.IGNORECASE)
            part_marks = [int(value) for value in re.findall(r"\[\s*(\d+)\s*\]", raw_text)]
            marks = (
                1
                if paper["component"] in {1, 2}
                else int(total_match.group(1))
                if total_match
                else sum(part_marks)
                if part_marks
                else None
            )
            image_path = f"question_images/{paper['id']}/q{int(start['number']):02d}.jpg"
            questions.append(
                {
                    "question_number": int(start["number"]),
                    "page_start": int(start["page_index"]) + 1,
                    "page_end": int(slices[-1]["page_index"]) + 1,
                    "raw_text": raw_text,
                    "normalized_text": normalized,
                    "image_path": image_path,
                    "marks": marks,
                    "slices": slices,
                    **topic,
                    **extra,
                }
            )
    return questions


def trim_question_image(image: Image.Image, stop_at_large_gap: bool = True) -> Image.Image:
    """Remove trailing page whitespace and isolated footer rules from a crop."""
    grayscale = image.convert("L")
    ink = grayscale.point(lambda value: 255 if value < 245 else 0)
    _horizontal, vertical = ink.getprojection()
    occupied = [index for index, value in enumerate(vertical) if value]
    if not occupied:
        return image
    first = occupied[0]
    last_kept = occupied[-1]
    if stop_at_large_gap:
        last_kept = first
        previous = first
        large_gap = max(160, round(image.height * 0.12))
        for row in occupied[1:]:
            if row - previous > large_gap:
                break
            last_kept = row
            previous = row
    top = max(0, first - 12)
    bottom = min(image.height, last_kept + 24)
    return image.crop((0, top, image.width, bottom))


def render_question_images(path: Path, paper: dict[str, Any], questions: list[dict[str, Any]]) -> None:
    destination = IMAGE_DIR / paper["id"]
    destination.mkdir(parents=True, exist_ok=True)
    scale = RENDER_DPI / 72.0
    with pdfplumber.open(path) as pdf:
        page_images: dict[int, Image.Image] = {}
        for question in questions:
            pieces: list[Image.Image] = []
            for item in question["slices"]:
                page_index = int(item["page_index"])
                if page_index not in page_images:
                    page_images[page_index] = pdf.pages[page_index].to_image(
                        resolution=RENDER_DPI,
                        antialias=True,
                    ).original.convert("RGB")
                source = page_images[page_index]
                box = (
                    round(float(item["left"]) * scale),
                    round(float(item["top"]) * scale),
                    round(float(item["right"]) * scale),
                    round(float(item["bottom"]) * scale),
                )
                pieces.append(
                    trim_question_image(
                        source.crop(box),
                        stop_at_large_gap=paper["component"] in {1, 2},
                    )
                )
            if not pieces:
                raise RuntimeError(f"No screenshot slices for {paper['id']} Q{question['question_number']}")
            width = max(piece.width for piece in pieces)
            separator = 8 if len(pieces) > 1 else 0
            height = sum(piece.height for piece in pieces) + separator * (len(pieces) - 1)
            combined = Image.new("RGB", (width, height), "white")
            y = 0
            for piece_index, piece in enumerate(pieces):
                combined.paste(piece, (0, y))
                y += piece.height
                if piece_index + 1 < len(pieces):
                    y += separator
            output_path = OUTPUT_DIR / question["image_path"]
            combined.save(output_path, "JPEG", quality=84, optimize=True, progressive=True)


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE syllabus_topics (
  ref TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  domain_ref TEXT NOT NULL,
  domain_title TEXT NOT NULL
);
CREATE TABLE papers (
  id TEXT PRIMARY KEY,
  year INTEGER NOT NULL,
  season TEXT NOT NULL,
  component INTEGER NOT NULL,
  variant INTEGER NOT NULL,
  paper_code TEXT NOT NULL,
  paper_name TEXT NOT NULL,
  candidate_route TEXT NOT NULL,
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
  marks INTEGER,
  page_start INTEGER NOT NULL,
  page_end INTEGER NOT NULL,
  raw_text TEXT NOT NULL,
  normalized_text TEXT NOT NULL,
  image_path TEXT NOT NULL,
  topic_ref TEXT NOT NULL REFERENCES syllabus_topics(ref),
  domain_ref TEXT NOT NULL,
  ao TEXT NOT NULL,
  command_word TEXT NOT NULL,
  difficulty TEXT NOT NULL,
  question_type TEXT NOT NULL,
  has_visual INTEGER NOT NULL,
  confidence REAL NOT NULL,
  classification_method TEXT NOT NULL,
  matched_patterns_json TEXT NOT NULL,
  UNIQUE(paper_id, question_number),
  UNIQUE(image_path)
);
CREATE VIRTUAL TABLE questions_fts USING fts5(
  question_id UNINDEXED, raw_text, topic_ref, topic_title, domain_title,
  tokenize='porter unicode61'
);
CREATE INDEX questions_topic_idx ON questions(topic_ref);
CREATE INDEX questions_year_idx ON questions(year);
CREATE INDEX questions_paper_idx ON questions(paper_id);
"""


def apply_manual_overrides(paper: dict[str, Any], questions: list[dict[str, Any]]) -> None:
    overrides = read_json(CONFIG_DIR / "manual_overrides.json")
    for question in questions:
        question_id = f"{paper['id']}-q{question['question_number']:02d}"
        override = overrides.get(question_id)
        if not override:
            continue
        question["topic_ref"] = override["topic_ref"]
        question["domain_ref"] = override["topic_ref"].split(".")[0]
        question["confidence"] = 1.0
        question["classification_method"] = "manual-pilot-review"
        question["matched_patterns"] = [override["reason"]]


def build_database(
    syllabus_topics: list[dict[str, Any]],
    paper_rows: list[tuple[dict[str, Any], list[dict[str, Any]]]],
    start_year: int,
    end_year: int,
) -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()
    connection = sqlite3.connect(DB_PATH)
    connection.executescript(SCHEMA)
    question_count = sum(len(questions) for _paper, questions in paper_rows)
    metadata = {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "start_year": str(start_year),
        "end_year": str(end_year),
        "paper_count": str(len(paper_rows)),
        "question_count": str(question_count),
        "scope": "CAIE IGCSE Physics 0625 Papers 1-6",
        "privacy": "Private local research index; source question text and screenshots are not publication assets.",
    }
    connection.executemany("INSERT INTO metadata(key, value) VALUES (?, ?)", metadata.items())
    connection.executemany(
        "INSERT INTO syllabus_topics VALUES (?, ?, ?, ?)",
        ((topic["ref"], topic["title"], topic["domain_ref"], topic["domain_title"]) for topic in syllabus_topics),
    )
    for paper, questions in paper_rows:
        connection.execute(
            "INSERT INTO papers VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                paper["id"], paper["year"], paper["season"], paper["component"], paper["variant"],
                paper["paper_code"], paper["paper_name"], paper["candidate_route"], paper["path"], len(questions),
            ),
        )
        for question in questions:
            question_id = f"{paper['id']}-q{question['question_number']:02d}"
            connection.execute(
                """INSERT INTO questions (
                    id, paper_id, year, season, component, variant, question_number, marks,
                    page_start, page_end, raw_text, normalized_text, image_path,
                    topic_ref, domain_ref, ao, command_word, difficulty, question_type,
                    has_visual, confidence, classification_method, matched_patterns_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    question_id, paper["id"], paper["year"], paper["season"], paper["component"],
                    paper["variant"], question["question_number"], question["marks"],
                    question["page_start"], question["page_end"],
                    question["raw_text"], question["normalized_text"], question["image_path"],
                    question["topic_ref"], question["domain_ref"], question["ao"], question["command_word"],
                    question["difficulty"], question["question_type"], int(question["has_visual"]),
                    question["confidence"], question["classification_method"],
                    json.dumps(question["matched_patterns"], ensure_ascii=False),
                ),
            )
            connection.execute(
                "INSERT INTO questions_fts VALUES (?, ?, ?, ?, ?)",
                (
                    question_id, question["raw_text"], question["topic_ref"],
                    TOPIC_TITLE[question["topic_ref"]], DOMAINS[question["domain_ref"]],
                ),
            )
    connection.commit()
    connection.close()


def public_index_rows(
    paper_rows: list[tuple[dict[str, Any], list[dict[str, Any]]]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for paper, questions in paper_rows:
        for question in questions:
            rows.append(
                {
                    "id": f"{paper['id']}-q{question['question_number']:02d}",
                    "year": paper["year"],
                    "season": paper["season"],
                    "component": paper["component"],
                    "paper": paper["paper_code"],
                    "paper_name": paper["paper_name"],
                    "candidate_route": paper["candidate_route"],
                    "question": question["question_number"],
                    "marks": question["marks"],
                    "topic_ref": question["topic_ref"],
                    "topic": TOPIC_TITLE[question["topic_ref"]],
                    "domain": DOMAINS[question["domain_ref"]],
                    "image": question["image_path"],
                    "search_text": question["normalized_text"],
                }
            )
    return rows


def write_csv(rows: list[dict[str, Any]]) -> None:
    with (OUTPUT_DIR / "question_index.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "question_id", "year", "season", "component", "paper", "paper_name", "candidate_route",
                "question", "marks", "topic_ref", "topic", "image_link",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row["id"], row["year"], row["season"], row["component"], row["paper"],
                    row["paper_name"], row["candidate_route"], row["question"], row["marks"],
                    row["topic_ref"], row["topic"], row["image"],
                ]
            )


def write_search_page(rows: list[dict[str, Any]], start_year: int, end_year: int) -> None:
    data = json.dumps(rows, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    topics = json.dumps([{"ref": ref, "title": title} for ref, title in TOPICS], ensure_ascii=False)
    components = json.dumps(
        [{"component": component, **details} for component, details in PAPER_DETAILS.items()],
        ensure_ascii=False,
    )
    paper_count = len({row["id"].rsplit("-q", 1)[0] for row in rows})
    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" href="data:,">
  <title>IGCSE Physics 0625 question index</title>
  <style>
    :root {{ color-scheme: light; --ink:#172033; --muted:#647087; --line:#dce2ea; --accent:#2457d6; --paper:#fff; --bg:#f5f7fb; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--bg); color:var(--ink); font:15px/1.5 system-ui,-apple-system,sans-serif; }}
    main {{ max-width:1080px; margin:0 auto; padding:40px 20px 72px; }}
    h1 {{ margin:0 0 6px; font-size:clamp(28px,4vw,42px); letter-spacing:-.03em; }}
    .lede {{ margin:0 0 26px; color:var(--muted); }}
    .search {{ display:grid; grid-template-columns:minmax(240px,1fr) 130px 230px 250px; gap:10px; padding:14px; background:var(--paper); border:1px solid var(--line); border-radius:14px; box-shadow:0 8px 30px #25375c10; }}
    input,select {{ width:100%; min-height:44px; border:1px solid var(--line); border-radius:9px; padding:9px 11px; color:var(--ink); background:#fff; font:inherit; }}
    input:focus,select:focus {{ outline:2px solid #2457d633; border-color:var(--accent); }}
    #status {{ margin:18px 2px 10px; color:var(--muted); }}
    #results {{ display:grid; gap:10px; }}
    article {{ display:grid; grid-template-columns:minmax(0,1fr) auto; align-items:start; gap:18px; padding:15px 17px; background:var(--paper); border:1px solid var(--line); border-radius:11px; }}
    .card-content {{ min-width:0; }}
    .meta {{ color:var(--muted); font-size:13px; }}
    .topic {{ margin-top:2px; font-weight:650; }}
    .question-text {{ margin-top:8px; color:#2d374c; line-height:1.55; overflow-wrap:anywhere; }}
    .question-text.clamped:not(.expanded) {{ display:-webkit-box; -webkit-box-orient:vertical; -webkit-line-clamp:3; overflow:hidden; }}
    .text-toggle {{ margin:5px 0 0; padding:0; border:0; color:var(--accent); background:transparent; font:inherit; font-size:13px; font-weight:650; cursor:pointer; }}
    .text-toggle:hover {{ text-decoration:underline; }}
    a {{ color:var(--accent); font-weight:650; text-decoration:none; white-space:nowrap; }}
    a:hover {{ text-decoration:underline; }}
    .image-link {{ align-self:center; }}
    .notice {{ margin-top:24px; padding:12px 14px; border-left:3px solid #d6a523; color:var(--muted); background:#fffaf0; }}
    @media (max-width:760px) {{ .search {{ grid-template-columns:1fr; }} article {{ grid-template-columns:1fr; gap:10px; }} .image-link {{ align-self:start; }} }}
  </style>
</head>
<body><main>
  <h1>Physics 0625 question index</h1>
  <p class="lede">{start_year}-{end_year} · Papers 1-6 · {paper_count:,} papers · {len(rows):,} questions · private local use</p>
  <section class="search" aria-label="Search filters">
    <input id="query" type="search" placeholder="Search, e.g. momentum or transformer" autofocus>
    <select id="year"><option value="">All years</option></select>
    <select id="component"><option value="">All paper types</option></select>
    <select id="topic"><option value="">All syllabus topics</option></select>
  </section>
  <p id="status"></p>
  <section id="results"></section>
  <p class="notice">Question screenshots and extracted text are for private analysis. Check Cambridge and source-site terms before sharing them.</p>
</main>
<script>
const QUESTIONS={data};
const TOPICS={topics};
const COMPONENTS={components};
const query=document.querySelector('#query'), year=document.querySelector('#year'), component=document.querySelector('#component'), topic=document.querySelector('#topic');
const status=document.querySelector('#status'), results=document.querySelector('#results');
[...new Set(QUESTIONS.map(q=>q.year))].sort((a,b)=>b-a).forEach(value=>year.add(new Option(value,value)));
COMPONENTS.forEach(item=>component.add(new Option(`Paper ${{item.component}} · ${{item.name}}`,item.component)));
TOPICS.forEach(item=>topic.add(new Option(`${{item.ref}} ${{item.title}}`,item.ref)));
function escapeHtml(value) {{ return String(value).replace(/[&<>"']/g,ch=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[ch])); }}
function render() {{
  const terms=query.value.toLocaleLowerCase().trim().split(/\s+/).filter(Boolean);
  const matches=QUESTIONS.filter(item => (!year.value || String(item.year)===year.value)
    && (!component.value || String(item.component)===component.value)
    && (!topic.value || item.topic_ref===topic.value)
    && terms.every(term => (`${{item.search_text}} ${{item.topic}} ${{item.domain}} ${{item.paper_name}}`).toLocaleLowerCase().includes(term)));
  const shown=matches.slice(0,100);
  status.textContent=`${{matches.length.toLocaleString()}} result${{matches.length===1?'':'s'}}${{matches.length>shown.length?' · showing first 100':''}}`;
  results.innerHTML=shown.map(item=>{{
    const extractedText=String(item.search_text || '').trim();
    const expandable=extractedText.length>260;
    return `<article><div class="card-content"><div class="meta">${{item.year}} · ${{escapeHtml(item.season)}} · Paper ${{item.paper}} · ${{escapeHtml(item.paper_name)}} · Question ${{item.question}}${{item.marks?' · '+item.marks+' '+(item.marks===1?'mark':'marks'):''}}</div><div class="topic">${{escapeHtml(item.topic_ref+' '+item.topic)}}</div><div class="question-text${{expandable?' clamped':''}}">${{escapeHtml(extractedText)}}</div>${{expandable?'<button class="text-toggle" type="button" aria-expanded="false">Show full text</button>':''}}</div><a class="image-link" href="${{encodeURI(item.image)}}" target="_blank" rel="noopener">View question image →</a></article>`;
  }}).join('');
}}
[query,year,component,topic].forEach(control=>control.addEventListener('input',render));
results.addEventListener('click',event=>{{
  const toggle=event.target.closest('.text-toggle');
  if (!toggle) return;
  const questionText=toggle.previousElementSibling;
  const expanded=toggle.getAttribute('aria-expanded')==='true';
  questionText.classList.toggle('expanded',!expanded);
  toggle.setAttribute('aria-expanded',String(!expanded));
  toggle.textContent=expanded?'Show full text':'Show less';
}});
render();
</script></body></html>
"""
    (OUTPUT_DIR / "search.html").write_text(document, encoding="utf-8")


def write_summary(
    paper_rows: list[tuple[dict[str, Any], list[dict[str, Any]]]],
    start_year: int,
    end_year: int,
) -> None:
    questions = [question for _paper, items in paper_rows for question in items]
    counts = Counter(question["topic_ref"] for question in questions)
    paper_counts = Counter(paper["component"] for paper, _items in paper_rows)
    question_counts = Counter(
        paper["component"]
        for paper, items in paper_rows
        for _question in items
    )
    summary = {
        "scope": f"CAIE IGCSE Physics 0625 Papers 1-6, {start_year}-{end_year}",
        "paper_count": len(paper_rows),
        "question_count": len(questions),
        "screenshot_count": len(questions),
        "component_counts": [
            {
                "component": component,
                "paper_name": PAPER_DETAILS[component]["name"],
                "candidate_route": PAPER_DETAILS[component]["route"],
                "papers": paper_counts[component],
                "questions": question_counts[component],
            }
            for component in PAPER_DETAILS
        ],
        "topic_counts": [
            {"topic_ref": ref, "topic_title": title, "questions": counts[ref]}
            for ref, title in TOPICS
        ],
        "limitations": [
            "Topic tags are deterministic suggestions against the current syllabus taxonomy.",
            "Historical papers predate parts of the current 2026-2028 syllabus taxonomy.",
            "Extracted text powers private search; the linked screenshot is the source-of-truth view.",
        ],
    }
    (OUTPUT_DIR / "index_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-year", type=int, default=DEFAULT_START_YEAR)
    parser.add_argument("--end-year", type=int, default=DEFAULT_END_YEAR)
    parser.add_argument("--clean", action="store_true", help="Remove the existing index output before rebuilding.")
    parser.add_argument("--no-screenshots", action="store_true", help="Build search data without rendering JPEGs.")
    args = parser.parse_args()
    if args.start_year > args.end_year:
        raise SystemExit("--start-year must be less than or equal to --end-year")
    if args.clean and OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)

    paths = discover_papers(args.start_year, args.end_year)
    if not paths:
        raise SystemExit(f"No Papers 1-6 PDFs found for {args.start_year}-{args.end_year} in {PAPERS_DIR}")
    syllabus_topics = extract_syllabus()
    paper_rows: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    for index, path in enumerate(paths, start=1):
        paper = paper_metadata(path)
        questions = extract_questions(path, paper)
        apply_manual_overrides(paper, questions)
        if not args.no_screenshots:
            render_question_images(path, paper, questions)
        paper_rows.append((paper, questions))
        print(f"[{index:03d}/{len(paths):03d}] {paper['id']}: {len(questions)} questions")

    build_database(syllabus_topics, paper_rows, args.start_year, args.end_year)
    rows = public_index_rows(paper_rows)
    write_csv(rows)
    write_search_page(rows, args.start_year, args.end_year)
    write_summary(paper_rows, args.start_year, args.end_year)
    print(f"Built {DB_PATH.relative_to(REPO_DIR)}")
    print(f"Indexed {len(rows)} questions from {len(paths)} papers")
    if not args.no_screenshots:
        print(f"Rendered {len(rows)} question screenshots in {IMAGE_DIR.relative_to(REPO_DIR)}")
    print(f"Open {(OUTPUT_DIR / 'search.html').relative_to(REPO_DIR)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
