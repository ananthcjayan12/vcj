# PapaCambridge CAIE IGCSE Physics 0625 downloader

## Physics Production Studio

The repo now includes a local dashboard for syllabus coverage, lesson preparation, video generation, scene review, and rendering:

```bash
python3 -m studio.server
```

Open `http://127.0.0.1:8765`. Keep the Terminal window open while the server runs, and press `Ctrl+C` in that same Terminal to stop it.

If you get `OSError: [Errno 48] Address already in use`, another Studio process is already using port `8765`. Stop the old process or launch on a different port with `python3 -m studio.server --port 8877`.

### Stop the Studio server later

If the Terminal that started the server is still available, press `Ctrl+C`. Otherwise, find and stop the process using port `8765`:

```bash
lsof -tiTCP:8765 -sTCP:LISTEN | xargs kill
```

To confirm that the port is free:

```bash
lsof -nP -iTCP:8765 -sTCP:LISTEN
```

See [`studio/README.md`](studio/README.md) and [`UI_IMPLEMENTATION_PLAN.md`](UI_IMPLEMENTATION_PLAN.md).

This utility recursively crawls:

`https://pastpapers.papacambridge.com/papers/caie/igcse-physics-0625`

It follows only Physics 0625 subfolders, downloads only official **question-paper PDFs**, preserves session folders, resumes safely, writes a CSV manifest, and creates a final ZIP.

## macOS — easiest method

1. Extract this toolkit ZIP.
2. Double-click `run_on_mac.command`.
3. If macOS blocks it, right-click the file, choose **Open**, then confirm.
4. Leave the Terminal window open until it reports completion.

Output:

- `CAIE_IGCSE_Physics_0625_Question_Papers/`
- `CAIE_IGCSE_Physics_0625_Question_Papers.zip`
- `download_manifest.csv`

## Terminal method

```bash
cd papacambridge_physics_0625_downloader
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python download_physics_0625.py --workers 3
```

## Resume after interruption

Run it again. Valid PDFs already downloaded are skipped automatically.

## Useful options

```bash
# Change the output location
python download_physics_0625.py --output ~/Downloads/Physics_0625

# Re-download existing files
python download_physics_0625.py --overwrite

# Download without creating a ZIP
python download_physics_0625.py --no-zip
```

Use the papers in accordance with Cambridge International and PapaCambridge terms, especially when republishing or using them commercially.

## Search the last 10 years of questions

The [`pilot/`](pilot/) directory builds a private searchable index of 7,643 top-level questions from all 417 local Paper 1-6 PDFs for 2016-2025. Every result links directly to a cropped screenshot containing the complete question, including subparts, diagrams, tables and answer choices.

```bash
./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/python pilot/build_question_index.py --clean
./.venv/bin/python pilot/verify_question_index.py
open pilot/index_output/search.html
./.venv/bin/python pilot/search.py momentum
```

Past-paper text and screenshots in the index are private research data and are not intended for publication. The earlier four-paper content-planning prototype is still available as `pilot/build_pilot.py`.

## Build IGCSE Physics videos topic by topic

The repository also contains a manual, curriculum-controlled video engine. It combines a 58-topic/328-row raw syllabus extraction (324 teachable objectives after removing section headings), private aggregate question-pattern research, 41 reusable physics animation scenes, and a complete narration-to-MP4 Template Lab pipeline.

```bash
python3 -m video_engine.cli init
python3 -m video_engine.cli doctor
python3 -m video_engine.cli next-topic
python3 -m video_engine.cli prepare-topic 1.1
```

Read [`END_TO_END_README.md`](END_TO_END_README.md) for installation and the complete generation, preview, render, review, and coverage workflow. For a stage-by-stage account of scene selection, recipe compilation, slowdown diagnosis, and low-engagement repair, see [`SCENE_GENERATION_PIPELINE_README.md`](SCENE_GENERATION_PIPELINE_README.md). Publication remains manual.

The video pipeline also includes a comparison-gated `direct-html` animation mode. It composes one continuous modern science-platform lesson, inspects chapter frames in Chromium, supports atomic chapter repair, and renders through the existing HyperFrames/FFmpeg path. See [`template_lab/README.md`](template_lab/README.md) for commands. The legacy route remains the default until the documented rollout gates pass.
