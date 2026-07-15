# Run one topic video with the Motion Canvas flow

This is the acceptance run for MAV Studio's narration-authoritative Motion Canvas pipeline. Run commands from the repository root. The example uses syllabus topic `1.1`; replace it with the topic you want to test.

## 1. Install and verify local tools

Required local programs are Python, Node 18 or newer, FFmpeg, FFprobe, Chrome/Chromium, and Whisper dependencies from the Python requirements.

```bash
python3 -m pip install -r requirements.txt -r requirements-video-engine.txt
npm --prefix motion_canvas_runtime install
PATH="$HOME/.nvm/versions/node/v22.12.0/bin:$PATH" npm --prefix motion_canvas_runtime run check
ffmpeg -version
```

Set the paid providers in `.env`. The current route uses Gemini for narration/TTS and Moonshot for Motion Canvas chapter coding:

```dotenv
GEMINI_API_KEY=...
MOONSHOT_API_KEY=...
MAV_MOTION_CANVAS_WORKERS=2
```

Never commit `.env`.

## 2. Prepare grounded topic facts

```bash
python3 -m video_engine.cli init
python3 -m video_engine.cli prepare-topic 1.1
```

Review `video_engine/topics/1.1/facts.json`. The video must not be generated until its claims, equations, units, examples, and objective IDs are correct.

## 3. Run one stage at a time

Choose a unique run ID:

```bash
export MAV_RUN_ID="motion-canvas-1-1-acceptance"
```

Steps 1–2 — inputs and final narration:

```bash
python3 template_lab/scripts/mav_generate.py \
  --run-id "$MAV_RUN_ID" \
  --facts video_engine/topics/1.1/facts.json \
  --topic "1.1 Physical quantities and measurement techniques" \
  --duration 120 \
  --animation-mode motion-canvas \
  --use-model --confirm-paid-api \
  --stop-after-step 2
```

Read `template_lab/runs/$MAV_RUN_ID/narration.json` before continuing. This narration becomes authoritative.

Step 3 — final voiceover:

```bash
python3 template_lab/scripts/mav_generate.py \
  --run-id "$MAV_RUN_ID" --facts video_engine/topics/1.1/facts.json \
  --topic "1.1 Physical quantities and measurement techniques" --duration 120 \
  --animation-mode motion-canvas --use-model --confirm-paid-api \
  --from-step 3 --stop-after-step 3
```

Step 4 — word timestamps from that exact audio:

```bash
python3 template_lab/scripts/mav_generate.py \
  --run-id "$MAV_RUN_ID" --facts video_engine/topics/1.1/facts.json \
  --topic "1.1 Physical quantities and measurement techniques" --duration 120 \
  --animation-mode motion-canvas --use-model \
  --from-step 4 --stop-after-step 4
```

Confirm that both `voiceover.mp3` and `audio_word_timestamps.json` exist. Do not replace the audio after this point.

Step 5 — prepare chapters and generate cached batches:

```bash
python3 template_lab/scripts/mav_generate.py \
  --run-id "$MAV_RUN_ID" --facts video_engine/topics/1.1/facts.json \
  --topic "1.1 Physical quantities and measurement techniques" --duration 120 \
  --animation-mode motion-canvas --use-model --confirm-paid-api \
  --from-step 5 --stop-after-step 5
```

Inspect:

- `motion_canvas/manifest.json`: contiguous chapter boundaries and local timestamps.
- `motion_canvas/prompts/`: exact paid prompts.
- `motion_canvas/responses/`: raw responses.
- `motion_canvas/chapters/`: installed TSX chapters.
- `motion_canvas/generation-report.json`: generated, cached, and failed batches.

If a batch failed, rerun the same command without `--force-paid-api`. Successful batches remain cached and only missing batches are called again.

Step 6 — compile and deterministic browser validation:

```bash
python3 template_lab/scripts/mav_generate.py \
  --run-id "$MAV_RUN_ID" --facts video_engine/topics/1.1/facts.json \
  --topic "1.1 Physical quantities and measurement techniques" --duration 120 \
  --animation-mode motion-canvas --use-model \
  --from-step 6 --stop-after-step 6
```

Approval requires `motion_canvas/robot-report.json` and `motion_canvas/validation.json` to say `passed`. Review `motion_canvas/preview/contact-sheet.png` manually for cropping, overlap, physics consistency, readable text, and narration timing.

## 4. Render the approved video

```bash
python3 template_lab/scripts/mav_render.py \
  --run-id "$MAV_RUN_ID" \
  --animation-mode motion-canvas
```

Expected output:

```text
template_lab/runs/<run-id>/motion_canvas/final.mp4
```

The renderer validates again, seeks every frame deterministically at 30 fps, encodes H.264 through FFmpeg, and retains the original voiceover attached by the fixed Motion Canvas project.

## Acceptance checklist

- Narration was approved before audio generation.
- Timestamps came from the final unchanged audio.
- Chapter durations sum to the selected audio duration.
- Rerunning step 5 reports cached successful batches.
- TypeScript and Vite build pass.
- Repeated midpoint renders are byte-identical.
- Browser console and page errors are empty.
- Contact sheet contains meaningful, safe-bounded visuals.
- Final MP4 duration and narration alignment are correct.
- Model cost records exist under `template_lab/runs/<run-id>/costs/`.
