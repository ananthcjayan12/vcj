# MAV Studio Physics Scene Producer — Reference File Index

This index is for a coding agent working in another MAV Studio checkout.

The reference implementation remains in:

```text
/Users/ananthu/Downloads/physics_scene_generation_lab
```

The agent does not need to copy this repository. It must have read access to the absolute paths below, study the implementation, and recreate the same responsibilities using MAV Studio’s native package structure and conventions.

## Read order

Read the files in Groups A–D first. Groups E–G are examples and evidence to consult only when needed.

## Group A — Production workflow implementation

These files explain how narration becomes timestamped, concurrently generated Motion Canvas chapters.

1. Timestamp splitting, manifest preparation, batching, prompt composition, parsing, caching, concurrency, and assembly:

   ```text
   /Users/ananthu/Downloads/physics_scene_generation_lab/motion_batch_robot.py
   ```

   Important locations:

   - Line 39: `_chapter_segments` — converts absolute word timestamps into chapter-local timing.
   - Line 83: `prepare_two_minute` — validates inputs, creates chapters/batches, copies audio, writes manifest.
   - Line 128: `_batch_prompt` — builds the compact system/user prompt.
   - Line 153: `_parse_batch_response` — enforces file markers and rejects unsafe output.
   - Line 173: `_generate_batch` — cache check, model call, response installation.
   - Line 193: `_assemble` — writes deterministic `scenes.ts` imports.
   - Line 214: `generate_two_minute` — concurrent execution and partial-failure preservation.

2. Single-scene prototype, prompt grounding, compile/preview checks, and bounded repair:

   ```text
   /Users/ananthu/Downloads/physics_scene_generation_lab/motion_robot.py
   ```

   Important locations:

   - Line 57: `_timing_context` — complete narration/timestamp prompt context.
   - Line 93: `build_prompt` — source-of-truth and neutral-reference prompt composition.
   - Line 137: `parse_generated_files` — strict two-file response parsing.
   - Line 161: `_run_npm` — controlled Node command execution.
   - Line 178: `check` — compile and deterministic preview orchestration.
   - Line 208: `generate` — generation plus one bounded repair.

3. CLI commands and model environment routing:

   ```text
   /Users/ananthu/Downloads/physics_scene_generation_lab/scene_lab.py
   ```

   Important locations:

   - Line 98: `_configure_model` — provider/model environment routing.
   - Line 201: Motion Canvas single-scene commands.
   - Line 254: `cmd_motion_prepare_two_minute`.
   - Line 273: `cmd_motion_generate_two_minute`.
   - Line 394: two-minute CLI argument definitions.

## Group B — Prompt contracts

These files are essential. They contain the prompting rules responsible for timing, deterministic physics, compact output, centered coordinates, and safe parsing.

1. Primary batch-generation system prompt:

   ```text
   /Users/ananthu/Downloads/physics_scene_generation_lab/motion_canvas_robot/prompts/batch.system.txt
   ```

2. Approved Motion Canvas APIs, physics state rules, safe area, and coordinate contract:

   ```text
   /Users/ananthu/Downloads/physics_scene_generation_lab/motion_canvas_robot/src/robot/approved-api.md
   ```

3. Neutral scene architecture reference:

   ```text
   /Users/ananthu/Downloads/physics_scene_generation_lab/motion_canvas_robot/src/robot/scene-template.txt
   ```

4. Neutral analytic-physics reference:

   ```text
   /Users/ananthu/Downloads/physics_scene_generation_lab/motion_canvas_robot/src/robot/physics-template.txt
   ```

5. Original single-scene generation contract:

   ```text
   /Users/ananthu/Downloads/physics_scene_generation_lab/motion_canvas_robot/prompts/generate.system.txt
   ```

6. Evidence-based chapter repair contract:

   ```text
   /Users/ananthu/Downloads/physics_scene_generation_lab/motion_canvas_robot/prompts/repair.system.txt
   ```

Prompt-loading guidance:

- Read `batch.system.txt` and `approved-api.md` completely.
- Use the neutral templates as architectural examples, not as lesson content.
- Do not use a generated projectile scene as the general few-shot example; that can bias unrelated lessons toward projectile visuals.
- Preserve the repeated centered-coordinate rules in both system and user prompts.

## Group C — Model dispatch, limits, and cost accounting

1. Task-to-provider/model/token/timeout mapping:

   ```text
   /Users/ananthu/Downloads/physics_scene_generation_lab/template_lab/prompts/prompt_model_mapping.json
   ```

   Relevant entries begin around:

   - Line 130: `motion_canvas_robot`.
   - Line 144: `motion_canvas_robot_repair`.
   - Line 158: `motion_canvas_batch`.

2. Provider-independent model client and Moonshot truncation protection:

   ```text
   /Users/ananthu/Downloads/physics_scene_generation_lab/template_lab/scripts/mav_models.py
   ```

   Important locations:

   - Line 150: token-limit resolution and environment overrides.
   - Line 176: timeout resolution.
   - Line 270: text-model dispatch.
   - Line 562: Moonshot request construction.
   - Line 638: reject `finish_reason=length` and incomplete output.

3. Thread-safe usage and cost ledger:

   ```text
   /Users/ananthu/Downloads/physics_scene_generation_lab/template_lab/scripts/mav_costs.py
   ```

   Important locations:

   - Line 12: shared lock protecting concurrent cost writes.
   - Line 117: aggregate cost summary.
   - Line 190: model usage recording.

4. Pricing used for estimates:

   ```text
   /Users/ananthu/Downloads/physics_scene_generation_lab/template_lab/model_pricing.json
   ```

## Group D — Fixed Motion Canvas runtime

These files show how generated scenes are hosted, previewed, sought deterministically, and rendered.

1. Project entry and original voiceover attachment:

   ```text
   /Users/ananthu/Downloads/physics_scene_generation_lab/motion_canvas_robot/src/project.ts
   ```

2. Deterministic generated chapter assembly:

   ```text
   /Users/ananthu/Downloads/physics_scene_generation_lab/motion_canvas_robot/src/generated/scenes.ts
   ```

3. Browser Motion Canvas initialization and frame seeking:

   ```text
   /Users/ananthu/Downloads/physics_scene_generation_lab/motion_canvas_robot/src/render-host.ts
   ```

   Important locations:

   - Line 36: scene initialization/recalculation.
   - Line 43: deterministic time-to-frame seek.
   - Line 63: public browser probe API.

4. Preview frames, deterministic comparison, contact sheet, and FFmpeg encoding:

   ```text
   /Users/ananthu/Downloads/physics_scene_generation_lab/motion_canvas_robot/scripts/render.mjs
   ```

   Important locations:

   - Line 13: preview/video modes.
   - Line 79: scene duration acquisition.
   - Line 83: seek and screenshot.
   - Line 90: five-frame preview.
   - Line 97: deterministic repeated-frame comparison.
   - Line 119: full-frame video render.
   - Line 128: FFmpeg H.264 encoding.

5. Browser renderer page:

   ```text
   /Users/ananthu/Downloads/physics_scene_generation_lab/motion_canvas_robot/render.html
   ```

6. Exact package versions and scripts:

   ```text
   /Users/ananthu/Downloads/physics_scene_generation_lab/motion_canvas_robot/package.json
   ```

7. Motion Canvas Vite integration:

   ```text
   /Users/ananthu/Downloads/physics_scene_generation_lab/motion_canvas_robot/vite.config.ts
   ```

8. Strict TypeScript/Motion Canvas JSX configuration:

   ```text
   /Users/ananthu/Downloads/physics_scene_generation_lab/motion_canvas_robot/tsconfig.json
   ```

9. Motion Canvas scene-query module typing:

   ```text
   /Users/ananthu/Downloads/physics_scene_generation_lab/motion_canvas_robot/src/vite-env.d.ts
   ```

## Group E — Current data contracts and run artifacts

Read these to understand real input/output shapes. Do not hard-code this specific lesson into MAV Studio.

1. Original voiceover:

   ```text
   /Users/ananthu/Downloads/physics_scene_generation_lab/reference/physics-1-2-v01/voiceover.mp3
   ```

2. Original word timestamps:

   ```text
   /Users/ananthu/Downloads/physics_scene_generation_lab/reference/physics-1-2-v01/audio_word_timestamps.json
   ```

3. Human-readable narration:

   ```text
   /Users/ananthu/Downloads/physics_scene_generation_lab/reference/physics-1-2-v01/narration.txt
   ```

4. Timestamp-derived chapter and batch manifest:

   ```text
   /Users/ananthu/Downloads/physics_scene_generation_lab/motion_canvas_robot/runs/two_minute/manifest.json
   ```

5. Generation status and partial-failure shape:

   ```text
   /Users/ananthu/Downloads/physics_scene_generation_lab/motion_canvas_robot/runs/two_minute/generation-report.json
   ```

6. Exact generated prompts:

   ```text
   /Users/ananthu/Downloads/physics_scene_generation_lab/motion_canvas_robot/runs/two_minute/prompts/batch_01.txt
   /Users/ananthu/Downloads/physics_scene_generation_lab/motion_canvas_robot/runs/two_minute/prompts/batch_02.txt
   /Users/ananthu/Downloads/physics_scene_generation_lab/motion_canvas_robot/runs/two_minute/prompts/batch_03.txt
   ```

7. Raw accepted model responses:

   ```text
   /Users/ananthu/Downloads/physics_scene_generation_lab/motion_canvas_robot/runs/two_minute/responses/batch_01.txt
   /Users/ananthu/Downloads/physics_scene_generation_lab/motion_canvas_robot/runs/two_minute/responses/batch_02.txt
   /Users/ananthu/Downloads/physics_scene_generation_lab/motion_canvas_robot/runs/two_minute/responses/batch_03.txt
   ```

## Group F — Generated chapter examples

These are examples of the output contract. They are not reusable runtime dependencies.

```text
/Users/ananthu/Downloads/physics_scene_generation_lab/motion_canvas_robot/src/generated/chapters/chapter_01.tsx
/Users/ananthu/Downloads/physics_scene_generation_lab/motion_canvas_robot/src/generated/chapters/chapter_02.tsx
/Users/ananthu/Downloads/physics_scene_generation_lab/motion_canvas_robot/src/generated/chapters/chapter_03.tsx
/Users/ananthu/Downloads/physics_scene_generation_lab/motion_canvas_robot/src/generated/chapters/chapter_04.tsx
/Users/ananthu/Downloads/physics_scene_generation_lab/motion_canvas_robot/src/generated/chapters/chapter_05.tsx
```

Recommended examples to study:

- `chapter_01.tsx`: one canonical time driving position and velocity direction.
- `chapter_02.tsx`: numerical average-speed example.
- `chapter_03.tsx`: graph, slope annotations, and corrected centered coordinates.
- `chapter_04.tsx`: acceleration motion plus velocity graph and safe animated bounds.
- `chapter_05.tsx`: short numerical-example chapter.

Do not copy editor swap files or Motion Canvas `.meta` files as implementation references.

## Group G — Validation examples and evidence

1. Analytic projectile physics test:

   ```text
   /Users/ananthu/Downloads/physics_scene_generation_lab/motion_canvas_robot/tests/physics.test.ts
   ```

2. Single-scene validation report:

   ```text
   /Users/ananthu/Downloads/physics_scene_generation_lab/motion_canvas_robot/runs/latest/robot-report.json
   ```

3. Deterministic browser validation summary:

   ```text
   /Users/ananthu/Downloads/physics_scene_generation_lab/motion_canvas_robot/runs/latest/validation.json
   ```

4. Contact-sheet example:

   ```text
   /Users/ananthu/Downloads/physics_scene_generation_lab/motion_canvas_robot/runs/latest/preview/contact-sheet.png
   ```

5. Model usage and cost evidence:

   ```text
   /Users/ananthu/Downloads/physics_scene_generation_lab/template_lab/runs/physics-1-2-v01/costs/model_usage.json
   /Users/ananthu/Downloads/physics_scene_generation_lab/template_lab/runs/physics-1-2-v01/costs/summary.json
   ```

## Existing module catalogue — optional design reference

The older scene modules are not part of the Motion Canvas runtime, but they contain useful physics-scene names, parameter ideas, and presentation patterns:

```text
/Users/ananthu/Downloads/physics_scene_generation_lab/modules/_registry.js
/Users/ananthu/Downloads/physics_scene_generation_lab/modules/
```

Use these only for taxonomy and design ideas. Do not assume their physics calculations or imports are production-correct.

## Files the agent should not copy

Do not copy:

- `node_modules/`
- `dist/`
- rendered frames or MP4 files
- editor `.swp`/`.swo` files
- generated `.meta` files unless MAV Studio explicitly needs Motion Canvas editor metadata
- immutable reference screenshots as runtime assets
- Direct HTML runtime files when implementing the Motion Canvas path

## Minimum loading set

If context is limited, load only these nine files first:

```text
/Users/ananthu/Downloads/physics_scene_generation_lab/MAV_STUDIO_MOTION_CANVAS_SCENE_PRODUCTION.md
/Users/ananthu/Downloads/physics_scene_generation_lab/motion_batch_robot.py
/Users/ananthu/Downloads/physics_scene_generation_lab/motion_canvas_robot/prompts/batch.system.txt
/Users/ananthu/Downloads/physics_scene_generation_lab/motion_canvas_robot/src/robot/approved-api.md
/Users/ananthu/Downloads/physics_scene_generation_lab/motion_canvas_robot/src/project.ts
/Users/ananthu/Downloads/physics_scene_generation_lab/motion_canvas_robot/src/render-host.ts
/Users/ananthu/Downloads/physics_scene_generation_lab/motion_canvas_robot/scripts/render.mjs
/Users/ananthu/Downloads/physics_scene_generation_lab/template_lab/scripts/mav_models.py
/Users/ananthu/Downloads/physics_scene_generation_lab/template_lab/scripts/mav_costs.py
```

After reading those, inspect one generated prompt, one raw response, the manifest, and chapters 1 and 3.

## Handoff instruction for the MAV Studio coding agent

Use this repository as a read-only reference. Reimplement the same responsibilities inside MAV Studio; do not introduce a runtime dependency on `/Users/ananthu/Downloads/physics_scene_generation_lab`.

Preserve these invariants:

1. Final narration and word timestamps are authoritative.
2. Chapter splitting is deterministic application code.
3. Each chapter owns one master time signal.
4. All related physics visuals read one canonical state.
5. Motion Canvas coordinates are centered and safe-bounded.
6. Model output is parsed through exact file markers.
7. Successful batches are cached and never regenerated unnecessarily.
8. Repairs operate on one failed chapter.
9. Assembly, validation, preview, and rendering are local deterministic stages.
10. Every paid call records provider, model, tokens, cache usage, response ID, and estimated cost.
