# Manual Topic Video Engine

This package is the curriculum-control layer around the two repo-local video systems:

- `physics_animation_engine/`: 35 reusable deterministic physics scenes and example JSON compositions.
- `template_lab/`: script, voice, Whisper timing, V3 custom scenes, validation, preview, HyperFrames render, and FFmpeg audio muxing.

It does not schedule daily jobs or upload to a platform. You choose a topic, run generation, review the result, render it, publish it manually, and then update coverage.

## First setup

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-video-engine.txt

cd physics_animation_engine
npm install
cd ..

cd template_lab
npm install
cd ..

python3 -m video_engine.cli init
python3 -m video_engine.cli doctor
```

Full MP4 rendering also requires Node 22.12+, npm, FFmpeg, and ffprobe. The renderer is installed from `template_lab/package-lock.json`; it does not fetch an unspecified HyperFrames release at render time. Copy `.env.example` to `.env` and add only the provider keys you intend to use. Paid calls are refused unless the generation command includes `--confirm-paid-api`.

## One-topic workflow

```bash
# 1. Inspect coverage and choose the next incomplete topic.
python3 -m video_engine.cli status
python3 -m video_engine.cli next-topic

# 2. Create a local grounded facts packet from the syllabus and private index aggregates.
python3 -m video_engine.cli prepare-topic 1.1

# 3. Generate an editable V3 lesson. This is the explicit paid/API step.
python3 template_lab/scripts/mav_generate.py \
  --run-id physics-1-1-v01 \
  --facts video_engine/topics/1.1/facts.json \
  --duration 480 \
  --v3 \
  --use-gemini \
  --use-gemini-tts \
  --confirm-paid-api

# 4. Preview and iterate locally.
python3 template_lab/scripts/mav_preview.py --run-id physics-1-1-v01

# 5. Render the approved composition to MP4.
python3 template_lab/scripts/mav_render.py --run-id physics-1-1-v01 --quality high

# 6. After human review, update progress deliberately.
python3 -m video_engine.cli set-status --topic 1.1 --status reviewed
python3 -m video_engine.cli set-status --topic 1.1 --status covered
```

`prepare-topic` never includes the raw past-paper text. It writes syllabus objectives plus aggregate command-word, question-type, difficulty, and visual-frequency patterns. The facts packet explicitly requires original questions, numbers, diagrams, and wording.

Generated topic packets and run outputs are ignored by Git. Curriculum, animation, video, original-question, and content-fingerprint registries are versioned so coverage and duplication control stay in this repository.
