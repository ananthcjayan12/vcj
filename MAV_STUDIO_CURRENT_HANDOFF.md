# MAV Physics Studio — Current-State Handoff

Last updated: 2026-07-17

Repository:

```text
/Users/ananthu/Downloads/papacambridge_physics_0625_downloader
```

This document is the current handoff for the local MAV Physics Studio (sometimes
referred to conversationally as WAV Studio). It describes what is implemented
now, how the active Motion Canvas production route works, which files control
each feature, recent fixes, operational warnings, and useful starting points for
the next feature.

The older historical handoff remains at:

```text
MOTION_CANVAS_CODEX_HANDOFF.md
```

Use this document as the newer source of truth.

---

## 1. Product purpose

MAV Physics Studio is a local production control room for creating narrated
Cambridge IGCSE Physics lesson videos.

The current Studio UI deliberately uses one production route:

```text
grounded topic packet
  → lesson structure
  → complete narration
  → chapter-based voice generation
  → local word alignment
  → immutable audio reels with continuous visuals and editable beat markers
  → TypeScript/browser validation
  → live preview
  → final MP4 render with voiceover
```

The important design principle is:

> Narration and measured audio timing are authoritative. Animation follows the
> voiceover; it does not invent a separate timeline.

### Immutable continuous-reel timeline

New Motion Canvas step-5 preparations write `motion_canvas/timeline.json` and
use `timeline_mode: immutable_reels`. Each TTS paragraph chunk becomes one
continuous 30–60 second visual reel with one reel-owned clock. Smaller windows
near measured word gaps are stored as editable beat metadata, not independent
Motion Canvas scenes. Generated TSX can consume its assigned reel duration but
cannot resize it.

Targeted beat regeneration revises only the parent
`motion_canvas/reels/reel_NNN.tsx`, with an explicit fixed beat window and
instructions to preserve incoming/outgoing visual state. Beats never add scene
cuts. Before generation and assembly, the pipeline verifies the timeline hash,
master-audio hash, reel membership, beat membership, and every sample/frame
boundary. The renderer also compares measured playback duration with the
master timeline and fails if drift exceeds approximately one frame.

Legacy chapter and short-shot manifests remain readable. To migrate an existing
run, rebuild step 5 without selecting an individual unit; this explicitly
creates and generates the continuous reel set instead of silently expanding one
paid edit request.

### Resumable MP4 rendering and queue

Motion Canvas video renders preserve completed PNG frames in
`motion_canvas/frames/` and record `motion_canvas/render-checkpoint.json`.
Frames are written atomically. A retry fingerprints the accepted visual source,
scans the contiguous valid PNG sequence, and resumes at the first missing frame.
If the visual source, FPS, duration, or frame count changed, cached frames are
discarded instead of being mixed into a different render. Older interrupted
runs without a checkpoint can be adopted when their frame files are newer than
the underlying visual TSX/runtime sources.

Studio stores its sequential MP4 queue in `template_lab/render_queue.json`.
The Runs view can select several step-7/8 runs and enqueue them together. Only
one renderer runs at a time. Failed runs remain selectable; re-queuing them uses
their valid frame checkpoint. Queue state is restored when Studio restarts.

The repository still contains Direct HTML and legacy recipe code, but
`studio/server.py` currently forces newly created and resumed Studio runs to
`motion-canvas`.

---

## 2. Starting the Studio

From the repository root:

```bash
source .venv/bin/activate
python3 -m studio.server
```

Default URL:

```text
http://127.0.0.1:8765
```

Alternative port:

```bash
python3 -m studio.server --port 8877
```

The macOS launcher may also be used:

```text
run_on_mac.command
```

The Studio must remain local. It can launch paid provider calls, delete run
artifacts, and start long render processes.

Required local tools include:

- Python virtual environment at `.venv`
- Node.js and npm
- Chrome, Chromium, or Microsoft Edge
- FFmpeg
- ffprobe for optional media inspection
- installed dependencies in `template_lab/` and `motion_canvas_runtime/`

---

## 3. Main application files

### Studio server

```text
studio/server.py
```

Responsibilities:

- serves the Studio UI and JSON API;
- reads curriculum, topic, run, and artifact state;
- creates and resumes runs;
- stores per-run model selections;
- starts generation and render subprocesses;
- streams subprocess output into `studio.log`;
- starts the local Motion Canvas preview server;
- handles run stop, reset, and deletion;
- exposes run artifacts safely.

### Studio browser application

```text
studio/static/index.html
studio/static/app.js
studio/static/styles.css
```

`app.js` owns:

- dashboard loading;
- topic selection;
- run creation;
- pipeline controls;
- model-map controls;
- usage/cost display;
- log polling;
- preview launching;
- MP4 render controls;
- destructive reset/delete confirmations.

### Main pipeline orchestrator

```text
template_lab/scripts/mav_generate.py
```

This is the step-based generation CLI launched by Studio.

### Final render orchestrator

```text
template_lab/scripts/mav_render.py
```

This launches the Motion Canvas renderer, records render metadata, and performs
non-fatal media inspection.

### Motion Canvas production pipeline

```text
template_lab/motion_canvas/pipeline.py
```

This prepares chapter manifests, generates/caches chapter TSX, validates cue
references, assembles scenes, performs aggregate compilation repair, syncs the
fixed runtime, creates deterministic previews, and starts video rendering.

### Fixed Motion Canvas runtime

```text
motion_canvas_runtime/
```

Important files:

```text
motion_canvas_runtime/src/presentation.tsx
motion_canvas_runtime/scripts/render.mjs
motion_canvas_runtime/src/generated/
motion_canvas_runtime/public/voiceover.mp3
```

The generated runtime files are replaced when an accepted run is installed for
preview or rendering.

---

## 4. The eight Studio steps

The UI presents these Motion Canvas stages:

| Step | UI label | Main artifacts | Paid/external? |
|---:|---|---|---|
| 1 | Inputs | `input.json` | Local |
| 2 | Narration | `story_skeleton.json`, `narration.json` | Model call |
| 3 | Voiceover | `voiceover.mp3`, `audio_chunks/`, `audio_generation.json` | TTS provider |
| 4 | Word timing | `audio_timing.json`, `audio_word_timestamps.json` | Local alignment |
| 5 | Chapters | `motion_canvas/manifest.json`, generated TSX, generation report | Model call |
| 6 | Compile & QA | TypeScript check, deterministic frames, robot report | Local, except model repairs when needed |
| 7 | Review | live Motion Canvas preview and human review | Local |
| 8 | Approval | Studio completion state and final render availability | Local |

CLI step labels in `mav_generate.py` still use some older internal wording:

```text
1 inputs
2 script
3 audio
4 timing
5 scene_plan
6 validate_repair
7 build_preview
8 qa_handoff
```

For Motion Canvas, steps 7 and 8 are primarily Studio workflow states. There is
not yet a substantial independent automated “approval” operation at step 8.
This is a known area that a future feature may improve.

---

## 5. Run metadata and state

Every Studio-managed run stores:

```text
template_lab/runs/<run-id>/studio_run.json
template_lab/runs/<run-id>/studio.log
```

`studio_run.json` includes:

- run ID;
- topic and topic reference;
- objective IDs;
- current status;
- current step;
- timestamps;
- duration;
- audio provider;
- per-task model map;
- chapter concurrency;
- paid-API confirmation;
- animation mode.

Run statuses include:

```text
created
paused
running
partial
failed
stopped
completed
rendering
rendered
```

`run_detail()` combines stored metadata with inferred artifact state. Older runs
without complete Studio metadata are normalized automatically.

---

## 6. Step execution and resume behavior

Studio builds commands through:

```python
studio.server.build_generation_command()
```

Typical command:

```bash
.venv/bin/python3 template_lab/scripts/mav_generate.py \
  --run-id <run-id> \
  --facts <facts.json> \
  --duration 480 \
  --model-provider configured \
  --audio-provider gemini \
  --animation-mode motion-canvas \
  --from-step <N> \
  --stop-after-step <N> \
  --use-model \
  --confirm-paid-api
```

The pipeline is designed to resume from cached artifacts:

- `--from-step 2` loads `input.json`;
- `--from-step 3` loads `narration.json`;
- `--from-step 4` loads `audio_generation.json`;
- `--from-step 5` loads timing artifacts;
- `--from-step 6` requires complete accepted Motion Canvas chapters;
- successful chapter generation responses and TSX files are retained.

Paid cache protection exists in `mav_generate.py`:

- `--clean` cannot be used with `--from-step > 1`;
- deleting an existing paid run cache requires `--force-paid-api`;
- existing valid narration can be reused rather than regenerated;
- existing Motion Canvas batch responses are reused unless forced.

### Important reset warning

Studio’s **Regenerate from step** action is destructive by design.

`reset_run_from_step()` removes the chosen step and all downstream artifacts.
In particular:

- reset from step 2 deletes narration and everything downstream;
- reset from step 3 deletes `voiceover.mp3`, `voiceover.wav`,
  `audio_generation.json`, and the entire `audio_chunks/` cache;
- reset from step 5 deletes the entire `motion_canvas/` directory;
- reset from step 6 deletes validation, previews, frames, and rendered MP4.

For a transient provider failure, prefer rerunning the failed step without using
the destructive reset whenever its partial cache is useful.

---

## 7. Script structure and narration pipeline

Implementation:

```text
template_lab/scripts/mav_script.py
template_lab/scripts/mav_schema.py
template_lab/prompts/script_structure.system.txt
template_lab/prompts/script_structure.user.txt
template_lab/prompts/script_writing.system.txt
template_lab/prompts/script_writing.user.txt
```

Step 2 uses two independent model tasks.

### 7.1 `script_structure`

Inputs include:

- topic;
- tone;
- narrative mode;
- target duration;
- duration-derived word and paragraph limits;
- grounded fact IDs and text;
- optional grounded research/raw values.

It creates:

```text
story_skeleton.json
```

Each beat contains:

- `beat_id`;
- `beat_type`;
- one-sentence summary;
- key number or claim;
- emotional register;
- non-empty grounded `claim_ids`.

### 7.2 `script_writing`

It receives:

- the complete structure JSON;
- the same grounded facts;
- target duration and bounds;
- teacher tone;
- any explicit regeneration instruction.

It creates:

```text
narration.json
narration.txt
narration_elevenlabs.txt
```

Debug artifacts:

```text
debug/narration_model_raw.json
debug/narration_normalized.json
debug/narration_validation.json
debug/script_generation_debug.json
debug/step_02_script.json
```

### 7.3 Narration schema hardening

Recent failures exposed two Anthropic structured-output restrictions:

1. every object schema must explicitly set `additionalProperties: false`;
2. Anthropic’s strict schema subset does not support arbitrary high
   `minItems` values or several other validation keywords.

The current provider adapter addresses this in:

```text
template_lab/scripts/mav_models.py
```

Important functions:

```python
_strict_object_schema()
_anthropic_compatible_json_schema()
```

The Anthropic-normalized schema:

- recursively closes every object;
- removes unsupported `minimum`, `maximum`, `minLength`, `maxLength`, and
  `maxItems` constraints;
- reduces array `minItems > 1` to `1`.

The complete educational constraints are still enforced locally after the model
returns.

The writing schema also explicitly requires:

```json
{
  "text": {
    "type": "string",
    "minLength": 1
  }
}
```

Local validation then checks for:

- empty narration paragraphs;
- paragraph count matching structure beats;
- exact sequential paragraph IDs;
- grounded claim IDs;
- word-count/duration limits;
- forbidden date-relative wording;
- damaged spoken text;
- ElevenLabs/plain narration consistency.

The normalizer can repair common harmless model drift, such as paragraph strings
instead of paragraph objects, but it does not silently accept an empty required
paragraph.

---

## 8. Supported model routing

Configuration:

```text
template_lab/prompts/prompt_model_mapping.json
template_lab/scripts/mav_models.py
template_lab/scripts/mav_codex.py
studio/server.py
studio/static/app.js
```

The active Studio model map exposes these tasks:

- `script_structure`
- `script_writing`
- `audio_generation`
- `motion_canvas_batch`
- `motion_canvas_repair`

### Script providers and models

Configured Gemini options:

```text
gemini-3.1-pro-preview
gemini-3.5-flash
gemini-3.1-flash-lite
gemini-2.5-pro
gemini-2.5-flash
gemini-2.5-flash-lite
```

Configured Anthropic options:

```text
claude-fable-5
claude-opus-4-8
claude-sonnet-5
claude-haiku-4-5
```

Codex CLI options added by Studio:

```text
gpt-5.6-sol
gpt-5.6-terra
gpt-5.6-luna
gpt-5.5
gpt-5.4
gpt-5.4-mini
```

Codex reasoning options:

```text
low
medium
high
xhigh
max
ultra
```

### Other provider support in the lower-level adapter

`mav_models.py` also supports:

```text
gemini
anthropic
zai
moonshot
codex
```

The Studio currently presents only the provider/model combinations included in
its retained Motion Canvas task catalog.

### Per-run model map

The active-run panel allows each task to use a different provider and model.
Selections are saved into:

```text
studio_run.json → settings.task_models
```

They become task-specific environment variables, such as:

```text
MAV_SCRIPT_STRUCTURE_PROVIDER
MAV_SCRIPT_STRUCTURE_MODEL
MAV_SCRIPT_STRUCTURE_REASONING_EFFORT

MAV_SCRIPT_WRITING_PROVIDER
MAV_SCRIPT_WRITING_MODEL
MAV_SCRIPT_WRITING_REASONING_EFFORT

MAV_MOTION_CANVAS_BATCH_PROVIDER
MAV_MOTION_CANVAS_BATCH_MODEL
MAV_MOTION_CANVAS_BATCH_REASONING_EFFORT

MAV_MOTION_CANVAS_REPAIR_PROVIDER
MAV_MOTION_CANVAS_REPAIR_MODEL
MAV_MOTION_CANVAS_REPAIR_REASONING_EFFORT
```

Model changes affect the next execution only. Existing artifacts and usage
records retain the provider/model that produced them.

### Codex provider

Codex uses the authenticated local Codex CLI, not an OpenAI API key.

```text
template_lab/scripts/mav_codex.py
```

It:

- discovers the CLI binary;
- checks login status;
- invokes `codex exec`;
- applies the selected reasoning effort;
- supports strict JSON output;
- records token usage;
- uses temporary response files.

---

## 9. Audio generation and current free-tier behavior

Implementation:

```text
template_lab/scripts/mav_audio.py
```

Supported Studio providers:

```text
Gemini TTS
ElevenLabs
```

Current default Gemini model:

```text
gemini-3.1-flash-tts-preview
```

### Chapter-based generation

Audio is generated one narration paragraph/chapter at a time.

Artifacts:

```text
audio_chunks/
  paragraph_01/
    narration.txt
    audio.wav
    cache_key.txt
    quality.json
  paragraph_02/
    ...
  manifest.json

voiceover.wav
voiceover.mp3
audio_generation.json
```

Each chapter cache key includes the text and provider configuration. On a normal
step-3 rerun:

- completed matching chapter WAV files are reused;
- generation continues at the first missing or changed chapter;
- cached chapters are not sent to Gemini again;
- the final WAV/MP3 is reassembled from all chapter files.

Therefore a Gemini `503 UNAVAILABLE` does not inherently require starting all
TTS calls from the beginning.

### Current limitation: no automatic retry/backoff

`_call_gemini_tts()` currently makes one provider request for the active chapter.
It does not yet implement:

- exponential backoff;
- retry-after handling;
- randomized jitter;
- a bounded retry count;
- per-chapter failure state in the manifest.

If Gemini returns a temporary 503, the current process exits. Rerunning step 3
without deleting `audio_chunks/` resumes from the incomplete chapter.

An effective next feature would add bounded retry/backoff around each Gemini TTS
chapter call while retaining the existing chapter cache.

Do not use **Regenerate from Audio** merely to retry a 503, because reset step 3
deletes `audio_chunks/`.

---

## 10. Word timing

Implementation:

```text
template_lab/scripts/mav_timing.py
```

Inputs:

- `narration.json`
- `voiceover.mp3`
- audio chapter manifest when available

Outputs:

```text
audio_timing.json
audio_word_timestamps.json
```

The word timestamps become the authoritative source for Motion Canvas cue
generation. Scenes should not use guessed equal subdivisions when a real word
cue exists.

---

## 11. Motion Canvas chapter generation

Implementation:

```text
template_lab/motion_canvas/pipeline.py
template_lab/motion_canvas/prompts/batch.system.txt
template_lab/motion_canvas/prompts/repair.system.txt
template_lab/motion_canvas/prompts/approved-api.md
```

### Preparation

`prepare()` validates and consumes:

- `voiceover.mp3`;
- `audio_word_timestamps.json`;
- narration paragraphs;
- chapter audio manifest when available.

It creates:

```text
motion_canvas/manifest.json
motion_canvas/voiceover.mp3
motion_canvas/chapters/chapter_NN.cues.ts
motion_canvas/prompts/batch_NN.txt
```

Each chapter contains:

- scene/chapter ID;
- narration text;
- absolute start/end;
- local duration;
- chapter-local word timestamps;
- generated cue names.

### Batch generation

The standard model batch contains two chapters. Successful outputs are cached:

```text
motion_canvas/responses/batch_NN.txt
motion_canvas/chapters/chapter_NN.tsx
```

Studio caps Motion Canvas workers at two. Codex-backed chapter generation is
also deliberately capped at two concurrent workers.

If some batches fail:

- accepted chapters remain on disk;
- `generation-report.json` becomes `partial`;
- Studio keeps the run before step 5 completion;
- resuming step 5 retries only missing/failed work unless forced.

### Generated chapter architecture

Every chapter is an independent deterministic Motion Canvas scene with:

- fixed 1920×1080 output;
- centered coordinates;
- one normalized time/progress signal;
- exact chapter duration;
- reveal timing derived from generated `CUES`;
- no remote assets;
- no random animation;
- no browser timers;
- no variable-delta physics integration.

The fixed presentation layer is:

```text
motion_canvas_runtime/src/presentation.tsx
```

Available components include:

- `SceneTitle`
- `TextCard`
- `EquationCard`
- `StatReadout`
- `TwoColumnComparison`
- `ComparisonTable`

---

## 12. Layout-overlap prevention

The root cause of many earlier box overlaps was prompt-level spatial reasoning
based only on component center points. The model often forgot:

- the actual width and height of each card;
- persistent earlier reveals;
- the densest final frame;
- required space around diagrams and labels.

The current prompt uses a simple rectangle-reservation rule rather than a new
layout engine.

Important instructions now present in:

```text
template_lab/motion_canvas/prompts/batch.system.txt
template_lab/motion_canvas/prompts/repair.system.txt
template_lab/motion_canvas/prompts/approved-api.md
```

Current rules include:

- safe area: `x=-860..860`, `y=-440..440`;
- treat every component as its complete rectangle;
- reserve `x ± width/2` and `y ± height/2`;
- keep unrelated regions at least 32 px apart;
- use prescribed 20 px gaps for intentional card stacks;
- horizontal card centers must be at least `card width + 32` apart;
- do not place card groups over diagrams, graphs, titles, or readouts;
- include all persistent earlier reveals when checking later frames;
- inspect the densest frame before returning source;
- prefer cue-windowing earlier content or simplifying the composition over
  shrinking typography.

This is intentionally a prompt-scale solution. It avoids a separate automatic
layout engine while substantially improving generated composition quality.

---

## 13. Validation and automatic chapter repair

After generation, the pipeline performs:

1. source normalization;
2. static contract checks;
3. cue key/index checks;
4. installation of accepted chapters;
5. aggregate TypeScript compilation;
6. grouping compiler errors by chapter;
7. targeted model repair;
8. recompilation, up to three aggregate repair passes;
9. deterministic browser preview.

Important generated reports:

```text
motion_canvas/generation-report.json
motion_canvas/robot-report.json
motion_canvas/validation.json
motion_canvas/preview/contact-sheet.png
motion_canvas/scenes.ts
```

The source normalizer also fixes some safe mechanical issues, including:

- numeric cue access such as `CUES.148` to `CUES["148"]`;
- duplicated mapped node keys by assigning group-prefixed keys.

Step 6 cannot start unless:

- the manifest lists chapters;
- every chapter TSX exists;
- `generation-report.json` has status `generated`.

---

## 14. Live preview

Studio starts the preview through:

```python
studio.server.start_motion_preview()
```

Requirements:

- step 6 robot report must have status `passed`;
- accepted run files are synced into the fixed runtime;
- an unused localhost port is allocated;
- `npm run serve` starts in `motion_canvas_runtime`.

The preview URL is stored only in server memory. Restarting the Studio server
stops/forgets the preview and requires starting it again.

Preview server logs:

```text
template_lab/runs/<run-id>/motion_canvas/preview-server.log
```

---

## 15. Render progress logging

Renderer:

```text
motion_canvas_runtime/scripts/render.mjs
```

Pipeline wrapper:

```text
template_lab/motion_canvas/pipeline.py
template_lab/scripts/mav_render.py
```

Rendering now writes detailed live logs to Studio:

- local render-host startup;
- headless browser launch;
- initialized scene duration;
- total frame count;
- FPS;
- completed frames;
- percentage complete;
- elapsed time;
- measured frames per second;
- estimated remaining time;
- H.264 video encoding start;
- voiceover attachment start/result;
- final duration/size summary.

The progress interval is limited to roughly one percent or five seconds of
timeline frames, preventing the log from being flooded.

The long renderer inherits stdout/stderr through `_npm_live()`, allowing Studio’s
existing subprocess log pipe to display progress in `studio.log`.

---

## 16. Final MP4 audio behavior

Recent root cause:

The original Motion Canvas FFmpeg command encoded only PNG frames into H.264.
Although `voiceover.mp3` existed, it was never supplied to FFmpeg, so
`final.mp4` had no audio stream.

Current corrected behavior:

1. render every PNG frame;
2. encode and preserve a complete video-only `final.mp4`;
3. if `voiceover.mp3` exists, mux it into a temporary MP4;
4. copy the existing H.264 stream without re-encoding it;
5. encode voiceover as AAC at 192 kbps;
6. replace `final.mp4` only after successful muxing;
7. if audio muxing fails, delete only the temporary audio output and preserve
   the usable video-only MP4;
8. report a warning rather than failing the completed render.

Relevant FFmpeg mapping:

```text
-map 0:v:0
-map 1:a:0
-c:v copy
-c:a aac
-b:a 192k
-shortest
-movflags +faststart
```

Media inspection in `mav_render.py` is also warning-only for Motion Canvas:

- missing `ffprobe` does not fail the render;
- inability to inspect does not fail the render;
- missing audio produces a warning;
- the only essential media requirement is a usable video output.

This behavior is deliberate:

> A successful, expensive frame render must never be discarded or marked failed
> merely because audio attachment failed. Audio can be repaired manually later.

Current verified output:

```text
template_lab/runs/physics-1-1-recipe-smoke/motion_canvas/final.mp4
```

At handoff time it contains:

- H.264 video;
- AAC audio;
- duration approximately 598.8 seconds.

---

## 17. Cost and usage tracking

Implementation:

```text
template_lab/scripts/mav_costs.py
template_lab/model_pricing.json
```

Per-run artifacts:

```text
costs/model_usage.json
costs/summary.json
```

The Studio displays:

- total estimated USD;
- call count;
- input tokens;
- output tokens;
- cached input tokens;
- total tokens;
- estimated cost by task;
- priced and unpriced record counts.

Model/provider combinations absent from `model_pricing.json` remain explicitly
unpriced. They must not be reported as zero-cost.

Pricing changes over time. Update `model_pricing.json` from current official
provider pricing before relying on estimates for a future production batch.

---

## 18. Current run inventory

Useful Studio-managed runs at handoff:

### `physics-1-1-recipe-smoke`

```text
status: rendered
current_step: 8
script structure: claude-sonnet-5
script writing: claude-sonnet-5
audio: Gemini TTS
chapter generation: Codex gpt-5.6-sol, low
chapter repair: Codex gpt-5.6-sol, low
```

This is the latest verified rendered run and contains the repaired audio/video
MP4.

### `physics-1-4-v01`

```text
status: completed
current_step: 7
script structure: Codex gpt-5.6-sol, low
script writing: Codex gpt-5.6-sol, medium
audio: Gemini TTS
chapter generation: Codex gpt-5.6-sol, low
chapter repair: Codex gpt-5.6-sol, low
```

This was the earlier Motion Canvas acceptance run described in the historical
handoff.

### `physics-1-5-1-v01`

```text
status: completed
current_step: 6
script structure: Gemini 3.1 Flash Lite
script writing: Codex gpt-5.6-sol, low
audio: Gemini TTS
chapter generation: Codex gpt-5.6-sol, low
chapter repair: Codex gpt-5.6-sol, medium
```

Other earlier runs remain under `template_lab/runs/`. Generated run artifacts
are intentionally not intended for normal Git commits.

---

## 19. Studio HTTP API

The local server exposes these important endpoints.

Read:

```text
GET /api/dashboard
GET /api/assets
GET /api/runs
GET /api/model-map
GET /api/topics/<topic-ref>
GET /api/runs/<run-id>
GET /api/runs/<run-id>/logs
```

Write/action:

```text
POST /api/topics/<topic-ref>/prepare
POST /api/topics/<topic-ref>/status
POST /api/runs
POST /api/runs/<run-id>/execute
POST /api/runs/<run-id>/reset
POST /api/runs/<run-id>/models
POST /api/runs/<run-id>/render
POST /api/runs/<run-id>/preview
POST /api/runs/<run-id>/stop
DELETE /api/runs/<run-id>
```

Older scene/chapter regeneration endpoints remain in the server, but some are
tied to legacy/direct-HTML assumptions and should be reviewed before exposing
them as Motion Canvas chapter-repair controls.

---

## 20. Important environment variables

Provider credentials:

```text
GEMINI_API_KEY
GOOGLE_API_KEY
ANTHROPIC_API_KEY
MOONSHOT_API_KEY
ZAI_API_KEY
ZHIPU_API_KEY
BIGMODEL_API_KEY
ELEVENLABS_API_KEY
```

General model routing:

```text
MAV_MODEL_PROVIDER
MAV_MODEL_MAX_TOKENS
MAV_MODEL_TIMEOUT_SECONDS
```

Task-specific routing follows:

```text
MAV_<TASK>_PROVIDER
MAV_<TASK>_MODEL
MAV_<TASK>_REASONING_EFFORT
MAV_<TASK>_MAX_TOKENS
MAV_<TASK>_TIMEOUT_SECONDS
```

Motion Canvas:

```text
MAV_MOTION_CANVAS_WORKERS
MAV_MOTION_RUN_ROOT
```

Audio:

```text
GEMINI_TTS_MODEL
ELEVENLABS_MODEL_ID
MAV_CHAPTER_PAUSE_SECONDS
```

Regeneration:

```text
MAV_STEP_REGEN_INSTRUCTION
MAV_SCENE_REGEN_INSTRUCTION
```

Node/renderer:

```text
MAV_NODE_BIN_DIR
NODE_BIN_DIR
MAV_NODE_HOME
NODE_HOME
CHROME_PATH
```

---

## 21. Known limitations and cautions

### 21.1 Gemini TTS has chapter caching but no automatic retry

Completed chapters survive a normal rerun, but the active chapter gets only one
request attempt. Add bounded retry/backoff as a future feature.

### 21.2 Destructive reset can remove useful caches

Use reset only when the user explicitly wants to regenerate a stage and all
downstream work. Do not use it as the default response to temporary provider
errors.

### 21.3 Frame rendering itself is not resumable

`render.mjs` clears `motion_canvas/frames/` at the beginning of a video render.
If frame capture fails halfway through, a new render starts frame capture again.
The recent audio fix protects completed video encoding, but it does not provide
frame-level resume.

### 21.4 Render timeout is currently one hour

`motion_canvas.pipeline.render_video()` calls:

```python
_npm_live("render-video", run_path, 3600)
```

Long lessons or slower machines could exceed this. A future feature could make
the timeout configurable or estimate it from measured frames per second.

### 21.5 Render quality/FPS UI arguments are not fully authoritative for Motion Canvas

Studio passes quality, FPS, and workers into `mav_render.py`, but the Motion
Canvas renderer currently reads FPS from the runtime scene and does not apply
all HyperFrames-style quality/worker settings. Avoid promising that these
controls materially change Motion Canvas output until they are wired through.

### 21.6 Step 8 is more workflow state than independent QA

The Studio can mark completion through step 8, but Motion Canvas does not yet
have a distinct final automated educational/visual approval suite beyond step 6
validation and human review.

### 21.7 Preview state is process-local

Only one Motion Canvas preview process is tracked globally. Starting another
run’s preview stops the previous preview.

### 21.8 Existing run `render_report.json` may predate the latest schema

New renders include:

```json
{
  "audio_source": ".../voiceover.mp3",
  "audio_attached": true,
  "ffprobe": {}
}
```

An older or manually repaired run may have a simpler report even when its MP4
actually contains audio. Probe the media itself when accuracy matters.

### 21.9 Historical documentation contains legacy route descriptions

`studio/README.md`, `template_lab/README.md`, and some server functions still
describe Direct HTML or legacy recipes. Current Studio run creation forces
Motion Canvas. Do not infer current UI behavior solely from older README
sections.

---

## 22. Recent files changed for the current feature set

The most relevant recently changed files are:

```text
template_lab/prompts/prompt_model_mapping.json
template_lab/scripts/mav_models.py
template_lab/scripts/mav_script.py
template_lab/scripts/mav_generate.py
template_lab/scripts/mav_audio.py
template_lab/scripts/mav_render.py
template_lab/motion_canvas/pipeline.py
template_lab/motion_canvas/prompts/batch.system.txt
template_lab/motion_canvas/prompts/repair.system.txt
template_lab/motion_canvas/prompts/approved-api.md
motion_canvas_runtime/scripts/render.mjs
studio/server.py
studio/static/app.js
studio/static/styles.css
```

Before editing, inspect the current versions rather than relying on the older
handoff or README snippets.

---

## 23. Verification performed for the latest render/audio fix

No full project rerender or full automated test suite was run for the latest
audio behavior change.

Lightweight checks performed:

```bash
node --check motion_canvas_runtime/scripts/render.mjs
.venv/bin/python3 -m py_compile template_lab/scripts/mav_render.py
```

The existing repaired MP4 was inspected with ffprobe and showed:

```text
h264 video
aac audio
duration 598.8 seconds
```

The next agent should preserve the user’s preference not to launch expensive or
time-consuming generation/render tests unless explicitly requested.

---

## 24. Recommended next-feature workflow

When beginning the next feature:

1. Read this handoff completely.
2. Inspect `studio/server.py`, `studio/static/app.js`, and the task-specific
   pipeline file before changing behavior.
3. Identify whether the requested operation is destructive or paid.
4. Preserve existing run caches and accepted chapters.
5. Prefer warning/fallback behavior when an optional finishing operation fails.
6. Never make a completed expensive render unusable because an optional
   post-processing or diagnostic check failed.
7. Keep model/provider choices per task and per run.
8. Record new provider usage in the existing cost ledger.
9. Keep prompts simple and enforceable; use local validation for strict
   correctness.
10. Use syntax/static checks first. Do not run a full render unless the user asks
    for it.

Good candidate next features include:

- Gemini TTS bounded retry/backoff with jitter and visible retry logs;
- a non-destructive “Retry failed audio chapter” Studio control;
- resumable frame rendering;
- configurable render timeout;
- a separate “Attach/re-attach audio” button for an existing MP4;
- final step-8 educational/visual approval evidence;
- Motion Canvas chapter-specific regeneration from Studio;
- clearer render settings that affect the actual Motion Canvas encoder;
- update old Studio documentation to describe the Motion Canvas-only UI.

---

## 25. Fast orientation checklist

For a new coding agent:

```text
[ ] Open MAV_STUDIO_CURRENT_HANDOFF.md
[ ] Inspect studio/server.py
[ ] Inspect studio/static/app.js
[ ] Inspect template_lab/scripts/mav_generate.py
[ ] Inspect the pipeline file for the requested step
[ ] Inspect the active run's studio_run.json and studio.log
[ ] Preserve run caches
[ ] Distinguish rerun from destructive reset
[ ] Avoid paid calls unless authorized
[ ] Avoid full renders unless requested
[ ] Keep video output even if optional audio/inspection fails
```
