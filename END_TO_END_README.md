# IGCSE Physics Video Engine — End-to-End Runbook

This repository now contains the reusable source needed to prepare, generate, preview, and render one syllabus topic at a time. It has no runtime dependency on the two original external source repositories.

## 1. Components

```text
pilot/output/syllabus_topics.json        58 topics and 328 objectives
pilot/index_output/question_index.sqlite3
                                          private aggregate assessment patterns
video_engine/                             curriculum, coverage, and topic preparation
physics_animation_engine/                 35 reusable deterministic physics scenes
template_lab/                              narration, TTS, timing, V3 scenes, preview, QA, MP4
```

The private past-paper index is used only to count patterns such as command words, question types, difficulty, and use of visuals. Raw question text and screenshots are never inserted into a generation packet.

## 2. Install once

```bash
cd /Users/ananthu/Downloads/papacambridge_physics_0625_downloader

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-video-engine.txt

cd physics_animation_engine
npm install
cd ../template_lab
npm install
cd ..

python3 -m video_engine.cli init
python3 -m video_engine.cli doctor
```

Required system tools for final render are Node 22.12+, npm, FFmpeg, and ffprobe. `template_lab/package-lock.json` pins HyperFrames. Python model/audio dependencies are separate from the downloader requirements because Whisper installs a large local ML stack.

## 3. Configure only the providers you use

```bash
cp .env.example .env
```

At minimum, the recommended V3 route needs:

```text
GEMINI_API_KEY      script and Gemini TTS
ZAI_API_KEY         V3 visual scene design
```

Anthropic, Moonshot, and ElevenLabs are optional alternatives. `.env` is ignored by Git. Every paid generation command must include `--confirm-paid-api`.

## 4. Prepare one topic

```bash
python3 -m video_engine.cli status
python3 -m video_engine.cli next-topic
python3 -m video_engine.cli prepare-topic 1.1
```

The final command creates:

```text
video_engine/topics/1.1/facts.json
```

It contains stable syllabus objective IDs, Core/Supplement labels, private aggregate assessment patterns, and a strict originality boundary. Existing packets are not overwritten unless `--force` is supplied.

Before generation, add trusted teacher-authored facts to the packet when the syllabus objective alone is not enough to ground an explanation, worked example, practical method, or misconception correction. Each added fact needs a unique `id`, exact `text`, and a `source` note.

## 5. Generate the lesson manually

```bash
RUN_ID=physics-1-1-v01

python3 template_lab/scripts/mav_generate.py \
  --run-id "$RUN_ID" \
  --facts video_engine/topics/1.1/facts.json \
  --duration 480 \
  --v3 \
  --use-gemini \
  --use-gemini-tts \
  --confirm-paid-api
```

The default 480-second target produces duration-aware word and paragraph bounds. The physics prompts require concept-first teaching, prediction/retrieval pauses, correct units and diagram geometry, original examples, and strict claim IDs. Generated narration fails the run instead of silently continuing when it violates the bounds or grounding checks.

Important output files:

```text
template_lab/runs/<run-id>/input.json
template_lab/runs/<run-id>/story_skeleton.json
template_lab/runs/<run-id>/narration.json
template_lab/runs/<run-id>/voiceover.mp3
template_lab/runs/<run-id>/audio_timing.json
template_lab/runs/<run-id>/audio_word_timestamps.json
template_lab/runs/<run-id>/scene_plan_v3.json
template_lab/runs/<run-id>/v3_scenes/
template_lab/runs/<run-id>/compositions/master_v3.html
template_lab/runs/<run-id>/validation/
```

## 6. Review and repair without repeating paid work

```bash
python3 template_lab/scripts/mav_preview.py --run-id "$RUN_ID" --port 8766
```

Review physics accuracy, objective coverage, pacing, visual clarity, and originality. Cached artifacts let you restart from a later stage:

```bash
# Rebuild/validate from cached scene artifacts without regenerating script or audio.
python3 template_lab/scripts/mav_generate.py \
  --run-id "$RUN_ID" \
  --facts video_engine/topics/1.1/facts.json \
  --duration 480 \
  --v3 \
  --use-gemini \
  --confirm-paid-api \
  --from-step 6
```

Regenerating a model-driven step is a paid action; the guard remains in force. Never use `--clean` casually on a paid run because it removes cached artifacts.

## 7. Render the approved MP4

```bash
python3 template_lab/scripts/mav_render.py \
  --run-id "$RUN_ID" \
  --quality high \
  --fps 30
```

The renderer builds the current V3 composition, renders its visual stream with the pinned local HyperFrames package, muxes `voiceover.mp3` with FFmpeg, and checks that the result contains video and audio streams. The default output is:

```text
template_lab/runs/<run-id>/renders/master_v3.mp4
```

## 8. Update coverage only after human review

```bash
python3 -m video_engine.cli set-status --topic 1.1 --status reviewed
python3 -m video_engine.cli set-status --topic 1.1 --status covered
python3 -m video_engine.cli status
```

Use explicit objective IDs when a video covers only part of a topic:

```bash
python3 -m video_engine.cli set-status \
  --objective-ids 1.2-C01 1.2-C02 1.2-C03 \
  --status covered
```

Uploading remains manual. The engine has no scheduler, platform credentials, or automatic publishing path.

## 9. Preview the reusable 35-scene library

```bash
cd physics_animation_engine
npm run preview
```

Open `http://127.0.0.1:8765/` or select a pilot composition:

```text
http://127.0.0.1:8765/?spec=specs/pilot/04-speed-time-graph.json
```

These deterministic scenes are reusable references and building blocks. Template Lab V3 is the final custom-scene and MP4 path.
