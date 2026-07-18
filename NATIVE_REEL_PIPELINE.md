# Native Reel / YouTube Shorts Pipeline

The Reel workflow is a separate, portrait-native production path. It reads only an approved parent lesson's narration, story skeleton, and grounded facts. It does not reuse parent Motion Canvas TSX, scene plans, screenshots, or visual assets.

## Studio workflow

Start Studio from the repository root:

```bash
PYTHONPATH=.:template_lab/scripts:template_lab .venv/bin/python3 studio/server.py
```

Open `http://127.0.0.1:8765`, select **Reels**, then:

1. Choose a completed lesson and generate 3–5 concepts.
2. Select one concept to create a linked Reel run.
3. Review or edit the treatment and short script before audio generation.
4. Generate the fast, enthusiastic portrait voiceover and local alignment.
5. Review the immutable shot timeline and shot descriptions.
6. Generate or selectively regenerate portrait Motion Canvas shots.
7. Run preview/QA, then render the 1080×1920 MP4.

Every model-driven Reel task has its own independent provider, model, and reasoning selection. The shared catalog makes all configured Gemini, Claude, Z.AI/GLM, Moonshot/Kimi, Codex CLI, and Grok models available to every task; tasks are not divided into creative-versus-coding model categories. Audio remains separate because it requires a speech provider. The default Gemini Reel voice is `Puck`; ElevenLabs can use a dedicated `ELEVENLABS_REEL_VOICE_ID`.

## CLI workflow

```bash
.venv/bin/python3 template_lab/scripts/mav_reel.py analyze \
  --parent-run-id PARENT_RUN --candidate-count 4 --confirm-paid-api

.venv/bin/python3 template_lab/scripts/mav_reel.py create \
  --parent-run-id PARENT_RUN --candidate-id candidate_01 --reel-run-id REEL_RUN

.venv/bin/python3 template_lab/scripts/mav_reel.py generate \
  --reel-run-id REEL_RUN --from-step 1 --stop-after-step 8 \
  --use-model --confirm-paid-api --audio-provider gemini

.venv/bin/python3 template_lab/scripts/mav_reel.py preview --reel-run-id REEL_RUN
.venv/bin/python3 template_lab/scripts/mav_reel.py render --reel-run-id REEL_RUN
```

Set a task's provider/model through the same environment convention as the lesson pipeline. For example:

```bash
MAV_REEL_MOTION_CANVAS_BATCH_PROVIDER=grok \
MAV_REEL_MOTION_CANVAS_BATCH_MODEL=grok-4.5 \
MAV_REEL_MOTION_CANVAS_BATCH_REASONING_EFFORT=high \
.venv/bin/python3 template_lab/scripts/mav_reel.py generate \
  --reel-run-id REEL_RUN --from-step 7 --stop-after-step 8 \
  --use-model --confirm-paid-api
```

Grok uses the authenticated official `grok` CLI in headless, plain-output, read-only mode. Run `grok login` first if it is not already authenticated.

## Reel stages

1. Narrative treatment
2. Short narration
3. Fast, energetic voiceover
4. Local word/paragraph alignment
5. Immutable frame-aligned portrait shot timeline
6. Portrait shot descriptions
7. Motion Canvas TSX generation
8. Compile, preview, and robot QA

Changing narration invalidates audio and everything downstream. Changing audio invalidates alignment and everything downstream. Editing one shot description or regenerating one shot invalidates only that shot's TSX and downstream preview/render artifacts; sibling shots stay intact.
