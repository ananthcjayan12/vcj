# Physics Production Studio — End-to-End Operator Guide

## Motion Canvas step-by-step UI

Start the Studio with `./run_on_mac.command` or `python3 -m studio.server`, then open the local URL printed in the terminal. The production UI now creates only narration-driven Motion Canvas runs.

1. Choose a syllabus topic and prepare its lesson packet.
2. Set the run ID, duration, script model, voice provider, and chapter workers.
3. Enable paid API confirmation and click **Create run**. Creation itself does not spend API credit.
4. Click a numbered stage card or use **Run selected step** to execute exactly one stage.
5. Open the generated artifacts and inspect the process log before continuing.
6. At step 6, review the deterministic contact sheet and require the compile/browser report to pass.
7. Use step 7 for human review and step 8 for approval, then click **Render MP4**.

Paid stages are narration (2), voiceover (3), and chapter generation (5). Inputs (1), word timing (4), compile/browser QA (6), review (7), approval (8), and rendering an accepted run are local. Rerunning chapter generation preserves successful cached batches.

Use **Regenerate from step** when an earlier artifact must be replaced. It removes the selected stage and all downstream artifacts, resets the recorded progress, and immediately starts that stage again. Use **Delete run** to remove an entire run directory—including audio, timestamps, prompts, responses, chapters, previews, validation evidence, and renders—before recreating the same run ID from step 1. Both destructive actions require an explicit UI confirmation and are disabled while a process is running.

The Physics Production Studio is the manual control room for producing one high-quality IGCSE Physics lesson at a time. It combines the syllabus map, curriculum coverage registry, aggregate past-paper patterns, reusable animation assets, AI-assisted lesson generation, preview, scene repair, and MP4 rendering in one local interface.

The Studio does **not** publish videos or run on a daily schedule. You choose a topic, supervise its production, approve the result, render it, upload it manually, and then update curriculum coverage.

---

## 1. What the Studio controls

The four areas in the left navigation are:

- **Production** — select a syllabus topic, prepare its lesson packet, create or generate a video, monitor the eight pipeline stages, preview the composition, repair individual scenes, and render the final MP4.
- **Curriculum** — see coverage across all 58 topics and 328 syllabus objectives and update a topic's production state.
- **Scene library** — search the 35 registered physics animation scenes that form the engine's reusable visual vocabulary.
- **Runs** — reopen previous productions and their artifacts, logs, previews, and renders.

The private question index contributes only aggregate teaching signals such as command-word frequency, question types, and use of diagrams. The generator does not copy raw past-paper questions into the lesson.

---

## 2. One-time installation

Open Terminal and move to the repository root:

```bash
cd /Users/ananthu/Downloads/papacambridge_physics_0625_downloader
```

Create and activate a Python virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-video-engine.txt
```

Install the Node dependencies used by the animation engine and final renderer:

```bash
cd physics_animation_engine
npm install

cd ../template_lab
npm install

cd ..
```

The machine must also have:

- Python 3.10 or newer
- Node.js 22.12 or newer and npm
- FFmpeg and ffprobe
- Enough disk space for audio, browser frames, and MP4 renders

On macOS, FFmpeg can be installed with Homebrew:

```bash
brew install ffmpeg
```

Initialize the curriculum registry and run the repository checks:

```bash
python -m video_engine.cli init
python -m video_engine.cli doctor
```

Do not start paid generation until `doctor` reports that the required local tools and data are available.

---

## 3. Configure AI and voice providers

Create the local environment file once:

```bash
cp .env.example .env
```

Open `.env` and add only the keys for providers you intend to use. The recommended default route is:

```dotenv
GEMINI_API_KEY=your_key_here
ZAI_API_KEY=your_key_here
```

These are used for:

- `GEMINI_API_KEY` — lesson scripting and Gemini text-to-speech
- `ZAI_API_KEY` — custom V3 scene design

Optional alternatives are:

```dotenv
ANTHROPIC_API_KEY=your_key_here
MOONSHOT_API_KEY=your_key_here
ELEVENLABS_API_KEY=your_key_here
```

`.env` is ignored by Git. Never commit, paste into a run note, or expose an API key in a screenshot.

Subscription-authenticated CLIs can also drive both Script Structure and Script
Writing for full lessons and Independent Reels:

- **Antigravity CLI** — install the official headless `agy` CLI from
  <https://antigravity.google/docs/cli/overview>, then run `agy` once and sign in.
  The Studio exposes every model reported by the authenticated `agy models`
  catalog. The older Antigravity desktop launcher also uses the name `agy`, but
  is detected and rejected because it has no headless `--print` mode.
- **GitHub Copilot CLI** — install and authenticate it using
  <https://docs.github.com/en/copilot/how-tos/set-up/install-copilot-cli>. The
  Studio exposes the documented `claude-sonnet-4.6` and `claude-haiku-4.5`
  model choices, plus forward-compatible `claude-sonnet-5` and
  `claude-opus-5` choices.

If either executable is outside `PATH`, set `MAV_ANTIGRAVITY_BIN` or
`MAV_COPILOT_BIN` to its absolute path. Optional request timeouts are controlled
with `MAV_ANTIGRAVITY_TIMEOUT_SECONDS` and `MAV_COPILOT_TIMEOUT_SECONDS`.
CLI requests run non-interactively in an isolated temporary directory and are
instructed to return only the script artifact without editing the repository.

### CLI authentication and catalog checks

The official installers place both executables in `~/.local/bin`. Open a fresh
Terminal, or run `source ~/.zshrc`, before completing these steps.

For Antigravity:

```bash
agy
# Choose Google OAuth and approve the browser login.
# Use /model to select the model for the authenticated account, then /exit.
agy models
```

For GitHub Copilot:

```bash
copilot login
# Approve the GitHub device login shown in the terminal.
copilot
# Use /models to inspect account-enabled model identifiers, then /exit.
```

The Antigravity choices mirror the authenticated `agy models` output:

```text
gemini-3.6-flash-high
gemini-3.6-flash-medium
gemini-3.6-flash-low
gemini-3.5-flash-high
gemini-3.5-flash-medium
gemini-3.5-flash-low
gemini-3.1-pro-high
gemini-3.1-pro-low
claude-sonnet-4-6
claude-opus-4-6-thinking
gpt-oss-120b-medium
```

Gemini reasoning effort is already encoded in these exact model slugs, so the
Studio does not apply a second Antigravity reasoning override.
`authenticated-default` uses the model selected inside `agy`. The adapter checks
the live authenticated catalog before every request and reports the available
models if a saved run references a model that is no longer offered.

Copilot's `claude-sonnet-5` and `claude-opus-5` remain forward-compatible
choices. Use Copilot's `/models` picker after login to confirm that the signed-in
account supports them.

### Load the keys before starting the Studio

The Studio reads keys from the environment of the server process. Export the contents of `.env` in the same Terminal before launch:

```bash
set -a
source .env
set +a
```

The provider indicators at the top-right of the Studio show a filled dot for detected providers. If the dots are empty even though `.env` contains keys, stop the server, run the three commands above, and restart it.

Every operation that may call a paid model or voice API still requires an explicit confirmation checkbox in the UI.

---

## 4. Start and stop the Studio

From the repository root, with the virtual environment active and `.env` loaded:

```bash
python3 -m studio.server
```

Open:

<http://127.0.0.1:8765>

To use another port:

```bash
python3 -m studio.server --port 8877
```

Keep the Terminal window open while using the Studio. Press `Ctrl+C` in that Terminal to stop the server.

The default host is `127.0.0.1`, so the interface is available only on the same computer. Do not expose it publicly: it can start paid jobs and write production state.

---

## 5. Recommended first test

For the first test, use one short, familiar topic, choose a five-minute duration, and keep scene workers at `1`. This makes the run easier to inspect and minimizes concurrent requests while verifying the setup.

Use a unique lowercase run ID such as:

```text
physics-1-1-test-v01
```

A run ID may contain lowercase letters, numbers, hyphens, and underscores. It cannot contain spaces or be reused after a run directory has been created.

---

## 6. Create a complete video

### Step 1 — Select the syllabus topic

Open **Production** and use the topic search on the left. Search by topic number, title, or domain, then select the topic.

Before generating, review:

- the Core and Supplement learning objectives;
- the current coverage state;
- classified-question and visual counts;
- common command words;
- common question types.

These assessment patterns tell you what students are commonly expected to do. They are planning evidence, not source material to reproduce.

### Step 2 — Prepare the lesson packet

Click **Prepare lesson packet**.

The Studio creates:

```text
video_engine/topics/<topic-ref>/facts.json
```

The packet contains the topic, stable objective IDs, syllabus statements, Core/Supplement routing, aggregate assessment patterns, and originality constraints.

If the button says **Rebuild packet**, a packet already exists. Clicking it rebuilds the file from current curriculum and index data. Avoid rebuilding after manually enriching `facts.json` unless you intend to replace those changes.

For a production lesson, inspect the packet before spending on generation. Add teacher-authored, trusted facts when the syllabus wording alone is insufficient for a worked example, practical method, misconception, or explanation. Preserve the existing JSON structure and give every added fact a unique `id`, accurate `text`, and clear `source` note.

### Step 3 — Configure the run

Set the production fields:

- **Run ID** — unique permanent identifier, for example `physics-1-1-v01`.
- **Duration** — target duration of 5, 8, 10, or 12 minutes. Eight minutes is a good default for a full concept lesson.
- **Script model** — Gemini is the recommended default; Claude API,
  Antigravity CLI, GitHub Copilot CLI, and Codex CLI are optional; Configured
  uses the pipeline's configured provider.
- **Voice** — Gemini TTS is the default; ElevenLabs is an optional alternative.
- **Scene workers** — number of custom scenes generated concurrently. Start with `1`; use `2` or `4` only when provider rate limits and the computer/network can support it.

Duration is a target, not an exact promise. Narration length, audio timing, and scene timing determine the final runtime.

For **Animation**, choose **Direct HTML · modern science** to compose one continuous simulation-style lesson. Direct runs expose Compose, Inspect/Repair, chapter screenshots, browser findings, optional review scores, and chapter-specific repair instructions. Choose **Legacy recipes** for the frozen comparison baseline. Both the Studio and command-line defaults remain legacy until the direct-HTML rollout gates pass, so select Direct HTML explicitly for a supervised trial.

### Step 4 — Choose Create run or Generate full lesson

There are two useful paths:

#### Safer supervised path

Click **Create run** without selecting the paid-API confirmation. This creates the run directory and metadata but does not call the generation providers. Use this path when testing the UI or when you want to execute the pipeline one stage at a time.

#### Full generation path

Select:

> I confirm this run may call paid model and voice APIs

Then click **Generate full lesson**. This creates the run and starts all eight stages. The browser may remain open, but the actual job is controlled by the local Studio server.

Do not click Generate twice. The Studio rejects duplicate run IDs and prevents two active processes for the same run.

---

## 7. Understand the eight pipeline stages

The production panel tracks:

1. **Inputs** — validates and snapshots the grounded topic packet and production settings.
2. **Script** — creates the concept-first lesson structure and narration. This is a paid model stage.
3. **Audio** — generates the voiceover using the selected provider. This is a paid voice stage.
4. **Timing** — aligns narration with word and scene timing using local processing.
5. **Compose** for Direct HTML, or **Scenes** for Legacy — generates the integrated HTML lesson or the V3 scene plan. This is a paid model stage.
6. **Inspect/Repair** for Direct HTML, or **Validate** for Legacy — runs contract/browser checks and may perform paid automatic chapter repairs for direct runs.
7. **Preview** — builds the browser-playable master composition.
8. **QA** — runs final automated quality checks and prepares the run for human review.

The log panel updates while a job is running. Use **Refresh** if the view looks stale.

### Pipeline controls

- **Run next** — executes only the next incomplete stage.
- **Run to QA** — resumes at the next stage and continues through stage 8.
- **Run selected step** — reruns only the stage selected in the dropdown.
- **Stop** — requests termination of the active subprocess.
- **Refresh** — reloads run state and artifacts.

Stages 2, 3, and 5 require the **Confirm paid APIs when required** checkbox. Direct-HTML stage 6 can also spend money when measured failures trigger automatic chapter repair. Local inspection itself does not call a model.

If a stage fails, read the final lines in the log, fix the reported issue, select that stage, and run it again. You normally do not need to recreate the whole run.

### Prompt/model map and usage ledger

The active-run panel shows every paid AI task, the pipeline step that uses it, its prompt files, provider, and exact model:

- Step 2: Script Structure and Script Writing
- Step 3: Voice Generation
- Step 5: Asset Shortlister, Asset Router, Module Parameterizer, Creative Director, and Scene Coder

The Asset Shortlister first receives only a simple scene list grouped under physics
modules such as mechanics, waves, electricity, and thermal physics. It selects the
few modules genuinely relevant to the lesson. The Asset Router then receives
detailed cards only for that shortlist, chooses `module` or `custom` for every
narration group, and records its reason, alternatives, and confidence. A module
choice is grounded against that selected module's full JSON Schema by the Module
Parameterizer. Only `custom` choices continue to the Creative Director and Scene
Coder.

You may change each provider/model pair while the run is paused, then click **Save model map**. The choices are stored in that run's `studio_run.json` and applied to its next execution. This allows, for example, Script Structure to use Antigravity while Script Writing uses a Claude model through GitHub Copilot. A model change is not retroactive: existing artifacts and usage records retain the model that actually produced them. Rerunning a paid task with a different model creates a new usage record and incurs a new provider charge or subscription allowance.

The **Model cost** panel displays estimated USD cost, calls, input tokens, output tokens, cached tokens, total tokens, and per-task cost. Detailed records remain available in `costs/model_usage.json`; aggregate totals are in `costs/summary.json`. Costs depend on `template_lab/model_pricing.json`. Calls whose provider pricing is absent are clearly counted as unpriced rather than incorrectly reported as free.

---

## 8. Review the generated lesson

After stage 7, the **V3 Composition Preview** appears inside the Studio. Use **OPEN ↗** to inspect it in a larger browser tab.

Watch the entire lesson before rendering. Review it like both a teacher and an editor.

The Studio shows the lesson shortlist before the per-scene routing list. The run
also stores `asset_index_used.json`, `asset_shortlist.json`,
`asset_catalog_used.json`, and `scene_routes.json`, so every narrowing decision is
inspectable and repeatable.

### Teaching review

- Every promised syllabus objective is actually taught.
- Explanations move from intuition to formal physics.
- Equations, substitutions, units, significant figures, vectors, and graph axes are correct.
- Diagrams use correct directions, labels, relative geometry, and conventions.
- The lesson anticipates likely misconceptions.
- Retrieval or prediction moments give the learner enough time to think.
- Worked examples are original and do not reproduce indexed paper content.
- Core and Supplement material are clearly appropriate for the selected scope.

### Video review

- Narration and visuals describe the same idea at the same moment.
- Important text remains readable on a phone-sized screen.
- No scene is visually empty, cluttered, cropped, or repetitive.
- Motion directs attention instead of decorating every moment.
- Scene changes feel intentional and pacing is not rushed.
- There are no long static holds, silent gaps, abrupt audio cuts, or overlapping labels.
- The introduction creates curiosity quickly and the ending consolidates learning.

Do not mark a topic covered based only on automated QA. Human review is required.

---

## 9. Repair one weak scene

After scenes have been generated, the **Scene surgery** section lists each scene, its duration, narration or beat label, a director-note field, and a **Regenerate** button.

To repair a scene:

1. Identify the exact visual problem and confirm the narration itself is correct.
2. Write a short, concrete director note.
3. Select **Confirm paid APIs when required** in the run controls.
4. Click **Regenerate** beside that scene.
5. Wait for the run to rebuild through scene generation, validation, preview, and QA.
6. Rewatch the repaired scene in context.

Good director notes are observable and specific:

```text
Keep the narration unchanged. Replace the generic arrows with a labelled free-body
diagram. Show weight vertically downward and normal contact force perpendicular to
the slope. Increase label size for mobile viewing and reveal one force at a time.
```

Avoid vague notes such as `make it better`, `more engaging`, or `fix animation`.

Scene regeneration is a paid operation and deliberately forces a fresh scene-generation call. It reuses the existing script and audio rather than regenerating the complete lesson.

If the problem is in narration, facts, or the overall teaching sequence, do not repair only the visual scene. Correct the appropriate upstream input and rerun from Script or the relevant stage.

---

## 10. Render the final MP4

The **Render MP4** button becomes available after the preview stage is complete. It starts a high-quality, 30 fps render with one worker.

Rendering is local and may take substantially longer than real time. Keep the Studio server running. The log shows progress, and the run status changes to `rendered` when complete.

The output appears at:

```text
template_lab/runs/<run-id>/renders/master_v3.mp4
```

The Studio also displays **Open rendered MP4 ↗** when it detects the file.

Watch the rendered MP4 from beginning to end. Browser preview success does not replace final-file review. Check:

- video and audio both exist;
- audio stays synchronized;
- the first and last frames are complete;
- fonts and equations render correctly;
- no browser-only overlays or loading states appear;
- playback works in a normal media player;
- final resolution, duration, and file size are suitable for upload.

The Studio intentionally does not upload the result. Publish the approved file manually to YouTube, Instagram, or another platform.

---

## 11. Update curriculum coverage

Open **Curriculum** after review and set the topic state deliberately:

- `planned` — topic selected and production intended.
- `scripted` — grounded script has been produced.
- `rendered` — an MP4 exists but has not passed the full human review.
- `reviewed` — a teacher/editor has reviewed the final output.
- `covered` — the reviewed video has been accepted as covering the topic objectives.
- `needs revision` — the output requires another production pass.

Changing a topic state updates all objectives in that topic. Therefore, mark `covered` only when the produced lesson genuinely covers all objectives shown for the topic.

If a video covers only part of a topic, use the curriculum CLI to update explicit objective IDs rather than marking the entire topic covered:

```bash
python3 -m video_engine.cli set-status \
  --objective-ids 1.2-C01 1.2-C02 1.2-C03 \
  --status covered
```

Use the next uncovered syllabus topic when starting the next lesson. This syllabus-first workflow and stable objective IDs prevent accidental repetition and expose real coverage gaps.

---

## 12. Reopen an existing run

Open **Runs**, locate the run, and click **Open**. The Studio returns to Production and loads:

- run status and completed stage;
- generation settings;
- latest logs;
- preview, if built;
- scene list, if generated;
- rendered MP4, if available.

Run data is stored under:

```text
template_lab/runs/<run-id>/
```

Important files include:

```text
studio_run.json                         Studio status and settings
studio.log                              Studio process output
input.json                              grounded generation input
story_skeleton.json                     lesson structure
narration.json                          final narration and beats
voiceover.mp3                           generated narration audio
voiceover.wav                           lossless assembled chapter master
audio_chunks/manifest.json              authoritative chapter audio boundaries
audio_chunks/<paragraph_id>/audio.wav   independently cached chapter TTS
audio_chunks/<paragraph_id>/quality.json deterministic PCM quality measurements
audio_timing.json                       timed narration segments
audio_word_timestamps.json              word-level alignment
motion_canvas/chapters/*.cues.ts         deterministic chapter-local timing constants
motion_canvas_runtime/src/presentation.tsx fixed typography/table/card components
scene_plan_v3.json                      planned V3 scenes
v3_scenes/                              generated scene code
compositions/master_v3.html             browser preview
validation/                             validation and QA reports
renders/master_v3.mp4                   final output
```

Do not rename a run directory or hand-edit `studio_run.json` while the server is running.

---

## 13. Cost-safe operating rules

Follow these rules for every production:

1. Prepare and inspect the topic packet before enabling paid APIs.
2. Start with one scene worker during setup and debugging.
3. Use **Create run** when testing the UI without generation.
4. Read logs before retrying a failed paid stage.
5. Never press a paid rerun button repeatedly because progress looks slow.
6. Repair one scene instead of regenerating the complete lesson when the script and audio are already correct.
7. Use local validation, preview, and rendering stages as often as needed.
8. Keep each run ID permanent so cached paid artifacts remain reusable.
9. Do not delete a run directory until its approved outputs have been archived.
10. Confirm provider dashboards and billing limits independently; the Studio confirmation is a safety gate, not a spending limit.

---

## 14. Troubleshooting

### Studio does not open

Confirm the server Terminal is still running and use the exact printed URL. If port 8765 is busy:

```bash
python3 -m studio.server --port 8877
```

Then open <http://127.0.0.1:8877>.

### `Address already in use`

That traceback means something is already listening on port `8765`. If you started the Studio in another Terminal, press `Ctrl+C` there to stop it.

If you cannot find the original Terminal, identify the process that owns the port and stop that PID:

```bash
lsof -nP -iTCP:8765 -sTCP:LISTEN
kill <PID>
```

Then restart the server, or choose a different port with:

```bash
python3 -m studio.server --port 8877
```

### Provider dot is empty

The key is not visible to the running server. Stop it and relaunch with:

```bash
source .venv/bin/activate
set -a
source .env
set +a
python3 -m studio.server
```

### `Run already exists`

Run IDs are immutable and unique. Open the existing run from **Runs**, or use a new version such as `physics-1-1-v02`.

### Paid-API confirmation error

Select the confirmation checkbox closest to the action:

- the checkbox in the topic form applies when starting full generation;
- the checkbox in the active-run panel applies when resuming paid stages or regenerating a scene.

### A run appears stuck

Wait for the current provider request or render operation, then click **Refresh**. Inspect the log before using **Stop**. A long render or scene-generation request can be normal; repeated clicks do not speed it up.

If a stopped process does not settle, stop the Studio with `Ctrl+C`, restart it, reopen the run, and resume from the appropriate stage.

### Script, audio, or scene stage fails

Check the bottom of `studio.log` in the run directory. Typical causes are an invalid/missing API key, provider quota or rate limit, network failure, invalid generated JSON, or a grounding/validation rejection. Correct the cause and rerun only the failed stage.

### Preview does not appear

Confirm stage 7 completed and this file exists:

```text
template_lab/runs/<run-id>/compositions/master_v3.html
```

Use **Run selected step → 7. Preview** to rebuild it from cached artifacts.

### Render button is disabled

The run must reach at least stage 7 and must not have another active process. Finish or rebuild Preview first.

### Render fails

Run these checks in Terminal:

```bash
ffmpeg -version
ffprobe -version
node --version
test -x template_lab/node_modules/.bin/hyperframes && echo "HyperFrames installed"
python -m video_engine.cli doctor
```

Install missing dependencies, then reopen the run and click **Render MP4** again.

### Audio timing is slow on the first run

Local Whisper may download a model on first use and then perform word alignment. This can take time and disk space. Later runs can reuse the downloaded model.

### The preview is good but MP4 looks wrong

Treat the MP4 as a separate approval artifact. Inspect `studio.log`, rerun Preview if generated scene code changed, and then render again. Do not mark the lesson reviewed until the actual MP4 passes inspection.

---

## 15. A repeatable production checklist

### Before generation

- [ ] Studio dependencies and `doctor` checks pass.
- [ ] Provider dots match the intended model and voice route.
- [ ] Correct syllabus topic is selected.
- [ ] Objectives and Core/Supplement scope are understood.
- [ ] Lesson packet has been prepared and teacher-reviewed.
- [ ] Facts, equations, definitions, units, and practical details are grounded.
- [ ] Run ID is unique and versioned.
- [ ] Duration and providers are appropriate.
- [ ] Paid API use is intentionally confirmed.

### During production

- [ ] Logs are monitored without repeatedly restarting stages.
- [ ] Failed stages are diagnosed before retrying.
- [ ] Preview is watched in full.
- [ ] Physics accuracy and objective coverage are checked.
- [ ] Visual clarity, pacing, mobile readability, and originality are checked.
- [ ] Weak scenes are repaired with precise director notes.

### Before publishing

- [ ] Final MP4 contains synchronized video and audio.
- [ ] Final MP4 is watched from start to finish.
- [ ] No rendering artifacts, clipped labels, or silent gaps remain.
- [ ] Title, description, thumbnail, subtitles, and platform format are prepared separately.
- [ ] Upload is performed manually.
- [ ] Curriculum state is updated to reviewed/covered only after approval.
- [ ] Run directory and final MP4 are retained as the production record.

---

## 16. Fast command reference

Start a normal Studio session:

```bash
cd /Users/ananthu/Downloads/papacambridge_physics_0625_downloader
source .venv/bin/activate
set -a
source .env
set +a
python3 -m studio.server
```

Check the engine:

```bash
python3 -m video_engine.cli doctor
python3 -m video_engine.cli status
python3 -m video_engine.cli next-topic
```

Run Studio tests after code changes:

```bash
python3 -m unittest discover -s studio/tests
```

The lower-level command-line workflow remains documented in [`END_TO_END_README.md`](../END_TO_END_README.md). The implementation architecture and planned future phases are in [`UI_IMPLEMENTATION_PLAN.md`](../UI_IMPLEMENTATION_PLAN.md).
