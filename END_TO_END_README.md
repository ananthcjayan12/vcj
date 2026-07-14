# Template Lab End-to-End Runbook

This file explains how to run the MAV Template Lab pipeline from raw inputs to a browser preview.

For agent-to-agent development transfer, see:

```text
template_lab/DEVELOPMENT_HANDOFF.md
```

Run all commands from the repo root:

```bash
cd /Users/ananthu/Desktop/new_repos/stock-select
```

## Engine Choice

The lab currently has two scene engines:

```text
--v3              new generative scene engine; GLM 5.2 designs each scene as custom HTML/CSS/GSAP
--choreography-v2 legacy fixed editorial-SVG choreography engine
```

Use `--v3` when you want to test the new implementation. V3 reuses the same inputs, script, audio, and timing steps as V2; only steps 5-7 change.

## 1. Prepare Inputs

The generator reads these files from the repo root by default:

```text
current_target.txt       # ticker or current target name
raw_numbers.json         # structured finance/fundamentals JSON
grounded_research.txt    # research/catalyst text
```

`grounded_research.txt` can end with `Bullish` or `Bearish`; that final line is used as a hint for narrative mode. If no clear hint exists, the code classifies the research into a mode such as `sector_wave`, `bull_breakout`, `bear_pressure`, or `turnaround`.

You can override the topic with `--topic`, or pass a custom facts file with `--facts path/to/facts.json`.

### Selector, Harvester, And Cooldown DB

Run the stock selector first when you want the system to pick a ticker from social attention:

```bash
.venv/bin/python selector.py
```

`selector.py` writes only the chosen ticker to:

```text
current_target.txt
```

It does not automatically insert the selected ticker into `channel_history.db`. That is intentional: the DB is a cooldown/published-history list, so a failed or rejected run should not block the ticker.

After `current_target.txt` exists, run the harvester:

```bash
.venv/bin/python harvester.py
```

`harvester.py` reads `current_target.txt`, writes `raw_numbers.json`, then calls Gemini grounding and writes `grounded_research.txt`. It needs `GEMINI_API_KEY` in `.env`.

If you previously saw:

```text
zsh: bus error  python harvester.py
```

that was a native crash inside the old yfinance/pandas fundamentals path. The harvester now uses plain HTTP JSON endpoints instead of `yf.Ticker(...).get_info()`.

View the cooldown DB:

```bash
sqlite3 channel_history.db \
  "SELECT ticker, published_date, narrative_mode FROM video_history ORDER BY published_date DESC;"
```

Mark a ticker as used/published after you approve or publish the video:

```bash
sqlite3 channel_history.db \
  "INSERT OR REPLACE INTO video_history (ticker, published_date, narrative_mode) VALUES ('WEN', date('now'), 'manual');"
```

Use an explicit date or mode when needed:

```bash
sqlite3 channel_history.db \
  "INSERT OR REPLACE INTO video_history (ticker, published_date, narrative_mode) VALUES ('WEN', '2026-07-06', 'sector_wave');"
```

Remove one ticker from the cooldown DB:

```bash
sqlite3 channel_history.db \
  "DELETE FROM video_history WHERE ticker = 'WEN';"
```

Clear the whole cooldown DB only when you intentionally want every ticker eligible again:

```bash
sqlite3 channel_history.db "DELETE FROM video_history;"
```

## 2. Configure APIs

Live full generation needs paid/external APIs:

- Gemini for narration and V2 scene planning
- Z.AI GLM 5.2 for V3 scene design
- Gemini TTS for voiceover audio
- local OpenAI Whisper for paragraph timing

Put keys in `.env` at the repo root or inside `template_lab/.env`.

Common variables:

```bash
GEMINI_API_KEY=...
ZAI_API_KEY=...                  # required for V3 scene design with GLM 5.2
GEMINI_TTS_MODEL=gemini-3.1-flash-tts-preview
GEMINI_TTS_VOICE=Kore
MAV_WHISPER_MODEL=base.en
MAV_V3_SCENE_CONCURRENCY=4       # optional: full V3 scene batches default to 4 concurrent GLM calls
```

The pipeline refuses paid paths unless `--confirm-paid-api` is present.
Gemini TTS timing is derived by local OpenAI Whisper speech-to-text, so no Whisper API key is needed. `openai-whisper` must be installed in the venv.

Gemini is the default low-cost provider for script and V2 scene-planning tasks. V3 scene design defaults to Z.AI GLM 5.2. Claude/Anthropic remains available as an advanced fallback. To force Claude for a run, set `ANTHROPIC_API_KEY`, then add either `--model-provider anthropic` or set:

```bash
MAV_MODEL_PROVIDER=anthropic
```

V3 uses GLM 5.2 for the scene-designer calls while leaving the rest of the pipeline on Gemini:

```bash
ZAI_API_KEY=... \
python3 template_lab/scripts/mav_generate.py \
  --run-id "$RUN_ID" \
  --v3 \
  --use-gemini \
  --confirm-paid-api \
  --from-step 5
```

The Z.AI model id is `glm-5.2`. Its context cache is automatic, so the V3 design system stays in the stable system prompt and is not duplicated in each per-scene user prompt. Full V3 scene batches run concurrently; set `MAV_V3_SCENE_CONCURRENCY` to tune the worker count. Z.AI usage logs include `cached=` token counts when the API reports cache hits.

## 3. Run A Full Live Generation

Use a fresh run id. This is the recommended command for testing V3 end to end:

```bash
RUN_ID=memory-chip-v3-live-001

python3 template_lab/scripts/mav_generate.py \
  --run-id "$RUN_ID" \
  --v3 \
  --use-gemini \
  --use-gemini-tts \
  --confirm-paid-api
```

You can also reuse an existing run that already has script, audio, and timing artifacts from steps 1-4. This only regenerates the V3 scene plan, validation report, and preview:

```bash
RUN_ID=memory-chip-live-001

python3 template_lab/scripts/mav_generate.py \
  --run-id "$RUN_ID" \
  --v3 \
  --use-gemini \
  --confirm-paid-api \
  --from-step 5
```

For the existing V2 preview run in this repo, use:

```bash
RUN_ID=gemini-1

python3 template_lab/scripts/mav_generate.py \
  --run-id "$RUN_ID" \
  --v3 \
  --use-gemini \
  --confirm-paid-api \
  --from-step 5
```

The terminal prints timestamped progress while V3 is running. If it appears to pause, check the latest `scene_XX` lines; several GLM 5.2 scene calls may be waiting concurrently.

This reuses:

```text
template_lab/runs/gemini-1/input.json
template_lab/runs/gemini-1/narration.json
template_lab/runs/gemini-1/voiceover.mp3
template_lab/runs/gemini-1/audio_timing.json
template_lab/runs/gemini-1/audio_word_timestamps.json
```

It does not regenerate the script or audio. It creates:

```text
template_lab/runs/gemini-1/scene_plan_v3.json
template_lab/runs/gemini-1/v3_scenes/
template_lab/runs/gemini-1/validation/plan_validation_v3.json
template_lab/runs/gemini-1/preview_manifest_v3.json
template_lab/runs/gemini-1/compositions/master_v3.html
template_lab/runs/gemini-1/compositions/scenes_v3/
```

Legacy V2 full generation still works:

```bash
RUN_ID=memory-chip-live-001

python3 template_lab/scripts/mav_generate.py \
  --run-id "$RUN_ID" \
  --choreography-v2 \
  --use-gemini \
  --use-gemini-tts \
  --confirm-paid-api \
  --model-plan-repair
```

Gemini TTS is also the default audio provider, so `--use-gemini-tts` is optional. Keep it in commands when you want the provider choice to be obvious:

```bash
RUN_ID=memory-chip-live-002

python3 template_lab/scripts/mav_generate.py \
  --run-id "$RUN_ID" \
  --choreography-v2 \
  --use-gemini \
  --confirm-paid-api \
  --model-plan-repair
```

## 4. Generated Artifacts

Outputs are written to:

```text
template_lab/runs/<run-id>/
```

Important files:

```text
input.json                         # normalized run input
story_skeleton.json                # script phase 1 output
narration.json                     # final narration JSON
narration.txt                      # plain paragraph text
voiceover.mp3                      # live audio used by the preview
voiceover.wav                      # Gemini TTS source WAV sidecar, if generated
audio_generation.json              # audio report/cache info
audio_timing.json                  # paragraph timing from local Whisper
audio_word_timestamps.json         # word-by-word Whisper timing used for action sync
scene_plan_v3.json                 # V3 generated HTML/CSS/GSAP scene plan
v3_scenes/                         # per-scene V3 debug JSON
preview_manifest_v3.json           # V3 preview build manifest
compositions/master_v3.html        # V3 browser preview
scene_outline.json                 # scene planning phase 1 output
scene_choreography.json            # scene planning phase 2 output
scene_plan_v2.candidate.json       # scene planning phase 3 candidate
scene_plan_v2.repair_candidate.json # optional model repair output
scene_plan_v2.json                 # validated final plan
preview_manifest_v2.json           # preview build manifest
compositions/master_v2.html        # browser preview
renders/master_v3.mp4              # final V3 MP4 with voiceover, when V3 exists
renders/master_v2.mp4              # final V2 MP4 fallback
render_report.json                 # render settings and ffprobe validation
validation/                        # plan/layout/risk/visual QA reports
generation_summary.json            # final summary
```

## 5. Preview In Browser

The run-specific preview helper prints the exact URL and starts a local server:

```bash
python3 template_lab/scripts/mav_preview.py --run-id "$RUN_ID" --port 8766
```

Open the printed URL. The helper prefers `preview_manifest_v3.json` when present, otherwise it falls back to V2. A V3 URL will look like:

```text
http://127.0.0.1:8766/runs/<run-id>/compositions/master_v3.html
```

A V2 URL will look like:

```text
http://127.0.0.1:8766/runs/<run-id>/compositions/master_v2.html
```

For the reused `gemini-1` run, preview V3 with:

```bash
python3 template_lab/scripts/mav_preview.py --run-id gemini-1 --port 8766
```

Then open:

```text
http://127.0.0.1:8766/runs/gemini-1/compositions/master_v3.html
```

Compare against the existing V2 preview:

```text
http://127.0.0.1:8766/runs/gemini-1/compositions/master_v2.html
```

Open a single V3 scene directly:

```text
http://127.0.0.1:8766/runs/gemini-1/compositions/scenes_v3/scene_02.html
```

You can also serve the whole lab:

```bash
python3 template_lab/scripts/serve_lab.py --port 8766
```

### Render MP4

`mav_render.py` prefers V3 when `scene_plan_v3.json` exists, otherwise it renders V2. It rebuilds the selected preview, renders the GSAP timeline with HyperFrames, hides browser controls, muxes `voiceover.mp3` with FFmpeg, and verifies that the final MP4 contains both video and audio.

Verify the local tools once:

```bash
node --version
npx --yes hyperframes --version
ffmpeg -version
ffprobe -version
```

Render a 1920x1080 MP4 at 30 fps:

```bash
python3 template_lab/scripts/mav_render.py \
  --run-id "$RUN_ID"
```

For a faster review render:

```bash
python3 template_lab/scripts/mav_render.py \
  --run-id "$RUN_ID" \
  --quality draft
```

For final delivery:

```bash
python3 template_lab/scripts/mav_render.py \
  --run-id "$RUN_ID" \
  --quality high
```

Default output:

```text
template_lab/runs/<run-id>/renders/master_v3.mp4
```

For a V2-only run, the default output is `renders/master_v2.mp4`. Codec, duration, and stream validation are written to `render_report.json`.

## 6. Resume From A Step

`mav_generate.py` supports `--from-step`:

```text
1 = inputs
2 = script
3 = audio
4 = timing
5 = plan
6 = validate/repair
7 = build
8 = QA only
```

Examples:

Re-run V3 scene generation from cached script/audio/timing. This calls GLM 5.2 once per scene, with full batches dispatched concurrently:

```bash
python3 template_lab/scripts/mav_generate.py \
  --run-id "$RUN_ID" \
  --v3 \
  --from-step 5 \
  --use-gemini \
  --confirm-paid-api
```

Re-run V3 validation and local build from existing `scene_plan_v3.json` without paid APIs:

```bash
python3 template_lab/scripts/mav_generate.py \
  --run-id "$RUN_ID" \
  --v3 \
  --from-step 6
```

Rebuild V3 HTML from an existing validated `scene_plan_v3.json`:

```bash
python3 template_lab/scripts/mav_generate.py \
  --run-id "$RUN_ID" \
  --v3 \
  --from-step 7
```

Run V3 QA only from existing preview artifacts:

```bash
python3 template_lab/scripts/mav_generate.py \
  --run-id "$RUN_ID" \
  --v3 \
  --from-step 8
```

Legacy V2 examples:

Re-run V2 scene planning from cached script/audio/timing:

```bash
python3 template_lab/scripts/mav_generate.py \
  --run-id "$RUN_ID" \
  --choreography-v2 \
  --from-step 5 \
  --use-gemini \
  --confirm-paid-api \
  --model-plan-repair
```

Re-run validation and local build from existing JSON without paid APIs:

```bash
python3 template_lab/scripts/mav_generate.py \
  --run-id "$RUN_ID" \
  --choreography-v2 \
  --from-step 6
```

Rebuild HTML from an existing validated `scene_plan_v2.json`:

```bash
python3 template_lab/scripts/mav_generate.py \
  --run-id "$RUN_ID" \
  --choreography-v2 \
  --from-step 7
```

Run QA only from existing preview artifacts:

```bash
python3 template_lab/scripts/mav_generate.py \
  --run-id "$RUN_ID" \
  --choreography-v2 \
  --from-step 8
```

Do not use `--clean` with `--from-step > 1`; resume mode needs cached artifacts.

## 7. Restart After Failures

When a run fails, keep the same `RUN_ID` and restart from the failed step. The command will continue through later steps unless you also add `--stop-after-step`.

The error usually names the internal task or script that failed. Use this map:

| Step | What It Does | Main Scripts | Common Failed Task | Restart From |
|---|---|---|---|---|
| 1 | Read `current_target.txt`, `raw_numbers.json`, `grounded_research.txt` and write `input.json` | `mav_generate.py`, `mav_inputs.py`, `mav_schema.py` | input validation | `--from-step 1` or new `RUN_ID` |
| 2 | Generate story skeleton and narration | `mav_script.py`, `mav_models.py`, prompts in `template_lab/prompts/` | `script_structure`, `script_writing` | `--from-step 2` |
| 3 | Generate voiceover audio | `mav_audio.py` | Gemini TTS / audio cache | `--from-step 3` |
| 4 | Derive paragraph timing | `mav_timing.py` | Whisper transcription / timing validation | `--from-step 4` |
| 5 | Generate V3 scene HTML/CSS/GSAP or V2 scene outline/choreography/asset plan | V3: `mav_plan_v3.py`; V2: `mav_plan.py`; shared: `mav_models.py`, prompts in `template_lab/prompts/` | V3: `v3_scene_designer`; V2: `scene_architect`, `motion_director`, `asset_placer` | `--from-step 5` |
| 6 | Validate the scene plan | V3: `mav_validate_v3.py`; V2: `mav_schema.py`, `mav_plan.py`, `mav_presentation_risk.py` | V3 validation; V2 plan validation, `plan_repair` | `--from-step 6` |
| 7 | Build browser preview HTML | V3: `mav_build_preview_v3.py`; V2: `mav_build_preview.py` | preview build | `--from-step 7` |
| 8 | Run layout/risk/visual QA | `mav_layout_qa.py`, `mav_presentation_risk.py`, `mav_visual_qa.py` | QA report failure | `--from-step 8` |

Example: if V3 fails with:

```text
V3 scene designer did not return valid HTML
```

or:

```text
V3 validation failed
```

that is a step 5 or step 6 V3 failure. Check:

```text
template_lab/runs/<run-id>/scene_plan_v3.json
template_lab/runs/<run-id>/v3_scenes/
template_lab/runs/<run-id>/validation/plan_validation_v3.json
```

If the model output was malformed, rerun V3 scene generation from cached script/audio/timing:

```bash
python3 template_lab/scripts/mav_generate.py \
  --run-id "$RUN_ID" \
  --v3 \
  --from-step 5 \
  --use-gemini \
  --confirm-paid-api
```

If you edited `scene_plan_v3.json` manually and only want to validate/build locally:

```bash
python3 template_lab/scripts/mav_generate.py \
  --run-id "$RUN_ID" \
  --v3 \
  --from-step 6
```

Example: if V2 fails with:

```text
Gemini motion_director call stopped with max_tokens
```

that is a step 5 scene-planning failure. Resume from cached script/audio/timing like this:

```bash
python3 template_lab/scripts/mav_generate.py \
  --run-id "$RUN_ID" \
  --choreography-v2 \
  --from-step 5 \
  --use-gemini \
  --confirm-paid-api \
  --model-plan-repair
```

If the pipeline fails with:

```text
Gemini script_writing call stopped with max_tokens
```

that is a step 2 script failure. Resume from step 2:

```bash
python3 template_lab/scripts/mav_generate.py \
  --run-id "$RUN_ID" \
  --v3 \
  --from-step 2 \
  --use-gemini \
  --confirm-paid-api
```

If `narration.json` already exists and you intentionally want to refresh it with another paid call, add `--force-paid-api`.

For audio failures, rerun step 3:

```bash
python3 template_lab/scripts/mav_generate.py \
  --run-id "$RUN_ID" \
  --v3 \
  --from-step 3 \
  --use-gemini \
  --use-gemini-tts \
  --confirm-paid-api
```

If the existing audio cache is bad and must be regenerated, remove only the audio artifacts first:

```bash
rm -rf template_lab/runs/$RUN_ID/audio_chunks \
       template_lab/runs/$RUN_ID/voiceover.mp3 \
       template_lab/runs/$RUN_ID/voiceover.wav \
       template_lab/runs/$RUN_ID/audio_generation.json \
       template_lab/runs/$RUN_ID/audio_timing.json \
       template_lab/runs/$RUN_ID/audio_word_timestamps.json
```

Then rerun from step 3.

For validation/repair failures, rerun step 6:

```bash
python3 template_lab/scripts/mav_generate.py \
  --run-id "$RUN_ID" \
  --choreography-v2 \
  --from-step 6 \
  --model-plan-repair \
  --confirm-paid-api
```

If `scene_plan_v2.repair_candidate.json` already exists and you want a fresh model repair attempt, add `--force-model-plan-repair`.

Model output budgets are configured in:

```text
template_lab/prompts/prompt_model_mapping.json
```

Each model task has a `max_tokens` value. You can override all tasks for one shell command with:

```bash
MAV_MODEL_MAX_TOKENS=64000 \
python3 template_lab/scripts/mav_generate.py \
  --run-id "$RUN_ID" \
  --v3 \
  --from-step 5 \
  --use-gemini \
  --confirm-paid-api
```

Or override one V3 task:

```bash
MAV_V3_SCENE_DESIGNER_MAX_TOKENS=64000 \
python3 template_lab/scripts/mav_generate.py \
  --run-id "$RUN_ID" \
  --v3 \
  --from-step 5 \
  --use-gemini \
  --confirm-paid-api
```

Legacy V2 task override example:

```bash
MAV_MOTION_DIRECTOR_MAX_TOKENS=64000 \
python3 template_lab/scripts/mav_generate.py \
  --run-id "$RUN_ID" \
  --choreography-v2 \
  --from-step 5 \
  --use-gemini \
  --confirm-paid-api \
  --model-plan-repair
```

## 8. Run Each Stage Separately

For debugging, combine `--from-step` with `--stop-after-step`. Each command writes its artifacts and exits. Use the same `RUN_ID` for the whole sequence.

Set a run id once:

```bash
RUN_ID=memory-chip-debug-001
```

Pre-stage A, select the ticker:

```bash
.venv/bin/python selector.py
```

Check:

```text
current_target.txt
```

Pre-stage B, harvest numbers and grounded research:

```bash
.venv/bin/python harvester.py
```

Check:

```text
raw_numbers.json
grounded_research.txt
```

Step 1, normalize inputs only:

```bash
python3 template_lab/scripts/mav_generate.py \
  --run-id "$RUN_ID" \
  --v3 \
  --stop-after-step 1
```

Check:

```text
template_lab/runs/<run-id>/input.json
template_lab/runs/<run-id>/generation_summary.json
```

Step 2, script only:

```bash
python3 template_lab/scripts/mav_generate.py \
  --run-id "$RUN_ID" \
  --v3 \
  --from-step 2 \
  --use-gemini \
  --confirm-paid-api \
  --stop-after-step 2
```

Check:

```text
template_lab/runs/<run-id>/story_skeleton.json
template_lab/runs/<run-id>/narration.json
template_lab/runs/<run-id>/narration.txt
```

Step 3, audio only. Gemini TTS is the default and expected provider:

```bash
python3 template_lab/scripts/mav_generate.py \
  --run-id "$RUN_ID" \
  --v3 \
  --from-step 3 \
  --use-gemini-tts \
  --confirm-paid-api \
  --stop-after-step 3
```

Check:

```text
template_lab/runs/<run-id>/voiceover.mp3
template_lab/runs/<run-id>/audio_generation.json
```

Step 4, timing only. This runs local Whisper against `voiceover.mp3`:

```bash
MAV_WHISPER_MODEL=base.en \
python3 template_lab/scripts/mav_generate.py \
  --run-id "$RUN_ID" \
  --v3 \
  --from-step 4 \
  --stop-after-step 4
```

Check:

```text
template_lab/runs/<run-id>/audio_timing.json
template_lab/runs/<run-id>/audio_word_timestamps.json
```

From this point, choose V3 or V2.

### V3 Steps 5-8

Step 5, V3 scene generation only. This calls GLM 5.2 once per narration paragraph and writes generated HTML/CSS/GSAP:

```bash
python3 template_lab/scripts/mav_generate.py \
  --run-id "$RUN_ID" \
  --v3 \
  --from-step 5 \
  --stop-after-step 5 \
  --use-gemini \
  --confirm-paid-api
```

Check:

```text
template_lab/runs/<run-id>/scene_plan_v3.json
template_lab/runs/<run-id>/v3_scenes/
```

Regenerate only one V3 scene. This keeps the other scenes from the existing `scene_plan_v3.json` and makes only one paid model call:

```bash
python3 template_lab/scripts/mav_generate.py \
  --run-id "$RUN_ID" \
  --v3 \
  --v3-scene-id scene_02 \
  --from-step 5 \
  --stop-after-step 7 \
  --use-gemini \
  --confirm-paid-api
```

Check:

```text
template_lab/runs/<run-id>/v3_scenes/scene_02.json
template_lab/runs/<run-id>/scene_plan_v3.json
template_lab/runs/<run-id>/compositions/scenes_v3/scene_02.html
template_lab/runs/<run-id>/compositions/master_v3.html
```

Step 6, validate V3 only. This does not call paid APIs:

```bash
python3 template_lab/scripts/mav_generate.py \
  --run-id "$RUN_ID" \
  --v3 \
  --from-step 6 \
  --stop-after-step 6
```

Check:

```text
template_lab/runs/<run-id>/validation/plan_validation_v3.json
template_lab/runs/<run-id>/scene_plan_v3.json
```

Step 7, build V3 preview HTML only. This does not call paid APIs:

```bash
python3 template_lab/scripts/mav_generate.py \
  --run-id "$RUN_ID" \
  --v3 \
  --from-step 7 \
  --stop-after-step 7
```

Check:

```text
template_lab/runs/<run-id>/preview_manifest_v3.json
template_lab/runs/<run-id>/compositions/master_v3.html
```

Step 8, V3 QA only:

```bash
python3 template_lab/scripts/mav_generate.py \
  --run-id "$RUN_ID" \
  --v3 \
  --from-step 8
```

Check:

```text
template_lab/runs/<run-id>/validation/visual_qa.json
template_lab/runs/<run-id>/generation_summary.json
```

Preview:

```bash
python3 template_lab/scripts/mav_preview.py --run-id "$RUN_ID" --port 8766
```

### Edit One V3 Scene Locally

Each scene is also saved as editable JSON:

```text
template_lab/runs/<run-id>/v3_scenes/scene_02.json
```

To manually fix one scene, edit only that file. The important fields are:

```text
scene_html     # HTML and CSS for the scene
scene_gsap     # function initScene(tl, start, dur) { ... }
```

Then validate and rebuild without paid APIs:

```bash
python3 template_lab/scripts/mav_generate.py \
  --run-id "$RUN_ID" \
  --v3 \
  --from-step 6 \
  --stop-after-step 7
```

The pipeline merges `v3_scenes/*.json` back into `scene_plan_v3.json`, applies deterministic repairs, validates, and rebuilds the preview.

Open the isolated scene:

```text
http://127.0.0.1:8766/runs/<run-id>/compositions/scenes_v3/scene_02.html
```

Then compare in the full master:

```text
http://127.0.0.1:8766/runs/<run-id>/compositions/master_v3.html
```

Known automatic V3 repairs:

```text
- recovers misplaced <style> blocks from the raw model response
- converts rgb/rgba/hsl/hsla colors to token-based color-mix(...)
- converts known hardcoded token hex colors to CSS variables
- strips real inline event-handler attributes
```

### Legacy V2 Steps 5-8

Step 5, V2 scene planning only:

```bash
python3 template_lab/scripts/mav_generate.py \
  --run-id "$RUN_ID" \
  --choreography-v2 \
  --from-step 5 \
  --stop-after-step 5 \
  --use-gemini \
  --confirm-paid-api
```

Check:

```text
template_lab/runs/<run-id>/scene_outline.json
template_lab/runs/<run-id>/scene_choreography.json
template_lab/runs/<run-id>/scene_plan_v2.candidate.json
```

Step 6, validate and repair only:

```bash
python3 template_lab/scripts/mav_generate.py \
  --run-id "$RUN_ID" \
  --choreography-v2 \
  --from-step 6 \
  --stop-after-step 6
```

If you want model repair for remaining non-local violations, add:

```bash
--model-plan-repair --confirm-paid-api
```

Check:

```text
template_lab/runs/<run-id>/validation/plan_validation_v2.json
template_lab/runs/<run-id>/scene_plan_v2.json
```

Step 7, build preview HTML only:

```bash
python3 template_lab/scripts/mav_generate.py \
  --run-id "$RUN_ID" \
  --choreography-v2 \
  --from-step 7 \
  --stop-after-step 7
```

Check:

```text
template_lab/runs/<run-id>/preview_manifest_v2.json
template_lab/runs/<run-id>/compositions/master_v2.html
```

Step 8, QA only:

```bash
python3 template_lab/scripts/mav_generate.py \
  --run-id "$RUN_ID" \
  --choreography-v2 \
  --from-step 8
```

Check:

```text
template_lab/runs/<run-id>/validation/layout_qa_v2.json
template_lab/runs/<run-id>/validation/presentation_risk.json
template_lab/runs/<run-id>/validation/visual_qa.json
```

Then preview:

```bash
python3 template_lab/scripts/mav_preview.py --run-id "$RUN_ID" --port 8766
```

## 9. Edit Prompts And Re-run

All prompts live in:

```text
template_lab/prompts/
```

Use the prompt map here:

```text
template_lab/prompts/PROMPT_MAPPING.md
```

Use the model map here:

```text
template_lab/prompts/prompt_model_mapping.json
template_lab/prompts/PROMPT_MODEL_MAPPING.md
```

V3 scene-design prompts are:

```text
template_lab/prompts/v3_design_system.txt
template_lab/prompts/v3_scene_designer.system.txt
template_lab/prompts/v3_scene_designer.user.txt
```

After changing script prompts, re-run from step 2. Use `--force-paid-api` if you want to refresh an existing cached narration:

```bash
python3 template_lab/scripts/mav_generate.py \
  --run-id "$RUN_ID" \
  --v3 \
  --from-step 2 \
  --use-gemini \
  --confirm-paid-api \
  --force-paid-api
```

After changing V3 scene-design prompts, re-run from step 5:

```bash
python3 template_lab/scripts/mav_generate.py \
  --run-id "$RUN_ID" \
  --v3 \
  --from-step 5 \
  --use-gemini \
  --confirm-paid-api
```

After changing legacy V2 scene planning prompts, re-run from step 5:

```bash
python3 template_lab/scripts/mav_generate.py \
  --run-id "$RUN_ID" \
  --choreography-v2 \
  --from-step 5 \
  --use-gemini \
  --confirm-paid-api \
  --model-plan-repair
```

After changing repair prompts, re-run from step 6:

```bash
python3 template_lab/scripts/mav_generate.py \
  --run-id "$RUN_ID" \
  --choreography-v2 \
  --from-step 6 \
  --model-plan-repair \
  --force-model-plan-repair \
  --confirm-paid-api
```

## 10. Local Checks

Compile the V3 implementation:

```bash
python3 -m py_compile \
  template_lab/scripts/mav_plan_v3.py \
  template_lab/scripts/mav_build_preview_v3.py \
  template_lab/scripts/mav_validate_v3.py \
  template_lab/scripts/mav_models.py \
  template_lab/scripts/mav_generate.py
```

Validate the model map JSON:

```bash
python3 -m json.tool template_lab/prompts/prompt_model_mapping.json >/tmp/prompt_model_mapping.validated.json
```

Run tests:

```bash
python3 -m unittest discover -s template_lab/tests
```

List available prompts:

```bash
PYTHONPATH=template_lab python3 -c "from prompts import list_prompts; print(list_prompts())"
```

Build an existing V3 run without paid APIs:

```bash
python3 template_lab/scripts/mav_generate.py \
  --run-id "$RUN_ID" \
  --v3 \
  --from-step 7 \
  --stop-after-step 7
```

Then preview:

```bash
python3 template_lab/scripts/mav_preview.py --run-id "$RUN_ID" --port 8766
```

Build and QA an existing V2 run without paid APIs:

```bash
python3 template_lab/scripts/mav_build_preview.py --run-id "$RUN_ID" --v2
python3 template_lab/scripts/mav_layout_qa.py --run-id "$RUN_ID"
python3 template_lab/scripts/mav_presentation_risk.py --run-id "$RUN_ID"
```

## 11. Common Failures

Missing cached artifact:

```text
Cannot resume: missing cached ...
```

Run from an earlier step, or use a run id that already has the needed artifact.

Paid API refusal:

```text
Paid/API generation requires --confirm-paid-api
```

Add `--confirm-paid-api` only when you intentionally want to call paid/external services.

Plan validation failure:

```text
MAV generation failed: ...
```

For V3, check:

```text
template_lab/runs/<run-id>/validation/plan_validation_v3.json
template_lab/runs/<run-id>/scene_plan_v3.json
template_lab/runs/<run-id>/v3_scenes/
```

Then either edit `scene_plan_v3.json` locally and rerun from step 6, or rerun paid V3 scene generation from step 5.

For V2, check:

```text
template_lab/runs/<run-id>/validation/plan_validation_v2.json
```

Then either edit `scene_plan_v2.candidate.json` locally and rerun from step 6, or allow model repair with `--model-plan-repair --confirm-paid-api`.
