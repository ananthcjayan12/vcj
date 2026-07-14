# IGCSE Physics 10-year question index

This builds a private searchable index of every top-level CAIE IGCSE Physics 0625 question from Papers 1-6 across the ten complete years 2016-2025.

The complete local index contains 417 papers and 7,643 questions. Search uses extracted PDF text, but every result links to a tightly cropped JPEG of the original question, including all subparts, diagrams, tables and answer choices. You do not need to follow a review path back into the source PDF.

## Build

From the repository root:

```bash
./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/python pilot/build_question_index.py --clean
./.venv/bin/python pilot/verify_question_index.py
```

The default range is 2016-2025. To build another complete range:

```bash
./.venv/bin/python pilot/build_question_index.py --start-year 2019 --end-year 2025 --clean
```

The builder discovers Paper 1-6 PDFs in `CAIE_IGCSE_Physics_0625_Question_Papers/`. It validates the expected historical question-count range for each component and stops rather than creating a partial index.

## Paper coverage

| Component | Purpose | Candidate route |
|---|---|---|
| Paper 1 | Multiple Choice (Core) | Core |
| Paper 2 | Multiple Choice (Extended) | Extended |
| Paper 3 | Theory (Core) | Core |
| Paper 4 | Theory (Extended) | Extended |
| Paper 5 | Practical Test | Core and Extended |
| Paper 6 | Alternative to Practical | Core and Extended |

The second digit is the administrative variant. For example, Papers 21, 22 and 23 are parallel variants of component 2.

## Search in a browser

On macOS:

```bash
open pilot/index_output/search.html
```

The page works locally without a server. Search by question wording, physics term, topic or domain; optionally filter by year, paper type and syllabus topic. Results show metadata and a **View question image** link instead of a PDF/review path.

If your browser restricts local files, serve the directory:

```bash
./.venv/bin/python -m http.server 8000 --directory pilot/index_output
```

Then open `http://127.0.0.1:8000/search.html`.

## Search in the terminal

The SQLite database uses FTS5:

```bash
./.venv/bin/python pilot/search.py momentum
./.venv/bin/python pilot/search.py 'speed AND graph' --topic 1.2
./.venv/bin/python pilot/search.py transformer --year 2025 --paper 4
./.venv/bin/python pilot/search.py experiment --paper 6
./.venv/bin/python pilot/search.py density --json
```

Each terminal result includes an absolute `file://` URL for its screenshot. `--json` adds the same link as `image_url` for other tools.

## Outputs

| Output | Purpose |
|---|---|
| `index_output/search.html` | Self-contained local search page with image links |
| `index_output/question_index.sqlite3` | Private SQLite/FTS5 index |
| `index_output/question_images/` | One cropped JPEG per question |
| `index_output/question_index.csv` | Question metadata and relative image links |
| `index_output/index_summary.json` | Coverage and topic-count summary |

## Scope and boundaries

- “Last 10 years” means the ten latest complete local exam years, 2016 through 2025. Partial 2026 material is not mixed into the range.
- The index covers Core, Extended, Practical Test and Alternative-to-Practical papers. Candidates normally take either the Core route (1, 3 and 5/6) or Extended route (2, 4 and 5/6).
- Automatic topic labels use the current 2026-2028 syllabus taxonomy and remain provisional, especially for older papers.
- The screenshot is the source-of-truth view when PDF text extraction loses a symbol or diagram.
- Past-paper text and screenshots are private research material. Check Cambridge and source-site terms before sharing or publishing them.

The earlier four-paper content-planning prototype remains available through `build_pilot.py`, including its original-question and MAV outputs. It is separate from this complete historical question index.
