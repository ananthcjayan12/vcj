# Independent Reels Through the Existing Long-Form Batch Pipeline

## 1. Final product definition

Build a topic Reel pack as the existing long-form Motion Canvas production with
one important semantic change:

> Each long-form “chapter” is an independently written, independently
> publishable 30–40 second Reel.

Do not create a second visual pipeline. Do not create one child project per
Reel. Do not make one model call per Reel.

A topic should normally produce **4–5 independent Reels**, not 12.

Use the existing long-form infrastructure to:

- generate/cache independent audio chapters;
- concatenate those chapters into the production master audio;
- derive word timing;
- create one immutable timeline unit per Reel;
- batch **2–3 complete Reels in one visual-coder prompt**;
- parse multiple marked TSX files from the response;
- compile and repair them together;
- preview each Reel using its fixed timeline range;
- screen and approve each Reel;
- render/download each Reel independently.

## 2. Correct terminology

- **Topic Reel pack**: one production run containing 4–5 independent Reels.
- **Reel**: one independent 30–40 second story and one Motion Canvas timeline
  unit/source file.
- **Beat**: an internal 5–15 second edit/preview window inside a Reel, generated
  by the existing immutable timeline logic. Beats are not separate model calls,
  source files, or MP4s.
- **Batch**: one model request containing two or three complete Reel
  specifications and expecting two or three complete marked TSX files.

The coding agent must not confuse a Reel batch with narrative continuity. Reels
in the same model request are still completely independent stories.

## 3. Target architecture

Use one standard run directory, matching the current long-form layout:

```text
template_lab/runs/<run-id>/
  input.json
  story_skeleton.json
  narration.json
  narration.txt
  narration_elevenlabs.txt
  voiceover.mp3
  audio_generation.json
  audio_timing.json
  audio_word_timestamps.json
  audio_chunks/
    manifest.json
    reel_001/
    reel_002/
    reel_003/
    reel_004/
    reel_005/
  motion_canvas/
    timeline.json
    manifest.json
    prompts/
      batch_01.txt
      batch_02.txt
    responses/
      batch_01.txt
      batch_02.txt
    reels/
      reel_001.cues.ts
      reel_001.tsx
      reel_002.cues.ts
      reel_002.tsx
      ...
    scenes.ts
    generation-report.json
    robot-report.json
    validation.json
    preview/
    renders/
      reel_001.mp4
      reel_002.mp4
      ...
  publishing_manifest.json
  studio_run.json
```

This is the same architecture already used when
`motion_canvas.pipeline.prepare()` sees an audio-chunk manifest and builds an
`immutable_reels` timeline.

The existing Pack implementation’s nested
`reels/reel_001/motion_canvas/...` child projects should not be the target
architecture.

## 4. Reel count and duration

Change defaults and validation:

- default Reel count: **5**;
- allowed Reel count: **4–5** for the normal product;
- target duration per Reel: **35 seconds**;
- allowed measured duration per Reel: **30–40 seconds**;
- visual batch size: **2** by default, configurable to **3**;
- visual workers: retain existing safe range of 1–3.

For five Reels with batch size two, visual generation should produce exactly
three requests:

```text
batch_01 → reel_001 + reel_002
batch_02 → reel_003 + reel_004
batch_03 → reel_005
```

For four Reels with batch size two:

```text
batch_01 → reel_001 + reel_002
batch_02 → reel_003 + reel_004
```

For five Reels with batch size three:

```text
batch_01 → reel_001 + reel_002 + reel_003
batch_02 → reel_004 + reel_005
```

This batching must use the existing `manifest["batches"]`,
`ThreadPoolExecutor`, response cache, marker parser, per-source validation,
compile grouping, and repair flow in `motion_canvas.pipeline.generate()`.

## 5. Independent story contract

Every narration paragraph becomes one independently publishable Reel.

Each Reel must:

1. Make sense when watched without any other Reel.
2. Open with a catchy, concrete hook in the first 1–2 seconds.
3. Create retention through a question, prediction, contradiction, surprising
   observation, or visible problem.
4. Teach one focused syllabus-grounded idea.
5. Progress toward an answer instead of immediately stating the conclusion.
6. Close its own open loop.
7. End with a clear learning payoff.
8. Avoid references such as:
   - “as we saw earlier”;
   - “in the previous Reel”;
   - “in the next Reel”;
   - “part two”;
   - “continuing from”;
   - unexplained objects, variables, or diagrams introduced elsewhere.
9. Use only its assigned grounded facts and objective IDs.
10. Measure 30–40 seconds after actual TTS generation.

Reels may share:

- the same visual theme;
- the same presentation components;
- the same motion language;
- a similar diagram style;
- a reusable layout or animation recipe.

They may not share:

- story context;
- required prior knowledge introduced only by another Reel;
- runtime state;
- audio;
- approval state;
- render output.

## 6. Planning and narration schema

Keep the useful independent planning/script work, but write the result into the
normal long-form narration shape so the rest of the pipeline stays unchanged.

Recommended Pack plan:

```json
{
  "version": "2.0",
  "content_product": "topic-reel-pack",
  "topic": "1.1 Physical quantities and measurement techniques",
  "reel_count": 5,
  "reels": [
    {
      "reel_id": "reel_001",
      "title": "The Parallax Trap",
      "hook": "Why can one ruler show two different readings?",
      "retention_device": "Compare three eye positions before revealing the correct one.",
      "open_loop": "Which eye position gives the true measurement?",
      "learning_payoff": "Read a scale with the line of sight perpendicular.",
      "fact_ids": ["fact_..."],
      "objective_ids": ["0625-..."],
      "visual_concept": "One persistent ruler rig changes eye position.",
      "target_duration_seconds": 35
    }
  ]
}
```

Write the generated scripts to the existing long-form `narration.json`:

```json
{
  "version": "2.0",
  "title": "Independent Reels: Physical quantities and measurement",
  "content_product": "topic-reel-pack",
  "paragraphs": [
    {
      "id": "reel_001",
      "reel_id": "reel_001",
      "title": "The Parallax Trap",
      "text": "Complete independent spoken story...",
      "claim_ids": ["fact_..."],
      "objective_ids": ["0625-..."],
      "hook": "...",
      "retention_device": "...",
      "open_loop": "...",
      "learning_payoff": "...",
      "visual_concept": "...",
      "target_duration_seconds": 35
    }
  ],
  "elevenlabs_narration": "All paragraphs joined exactly as required by the existing audio contract."
}
```

Each paragraph is a complete Reel, not one part of a continuous lesson.

The Reel narration validator should enforce:

- exactly 4–5 paragraphs/Reels;
- stable `reel_001`... IDs;
- unique hook/open-loop/payoff combinations;
- no cross-Reel dependency language;
- non-empty hook, retention device, open loop, and payoff;
- valid grounded fact/objective references;
- one clear teaching payoff per Reel;
- no repeated introductions or conclusions added merely to fill time.

Keep narration and audio validation product-aware so ordinary long-form runs are
unchanged.

## 7. Audio generation

Use the existing long-form chapter-aware audio generator.

Each Reel paragraph should become one independent audio chunk:

```text
audio_chunks/reel_001/audio.wav
audio_chunks/reel_002/audio.wav
...
```

The audio manifest should list one record per Reel with:

- `id` / `reel_id`;
- relative chunk path;
- cache key;
- speech duration;
- optional trailing pause;
- absolute start/end in the production master;
- measured duration.

The production may concatenate these chunks into `voiceover.mp3` because the
existing Motion Canvas preview and compile infrastructure expects a master
timeline. This concatenation is a production convenience only; it must not make
the Reel stories dependent.

When rendering a single Reel, use its own chunk or its exact master-audio sample
range. Do not include the inter-Reel pause or neighboring Reel speech.

Duration handling:

1. Generate the Reel’s audio.
2. Measure its real duration.
3. Accept 30–40 seconds.
4. If outside the range, mark only that Reel as `duration_out_of_range`.
5. Permit rewriting/regenerating only that Reel’s narration/audio before visual
   timing becomes immutable.

Do not use word count as the final duration authority.

## 8. Immutable Reel timeline

Reuse `motion_canvas.pipeline.build_immutable_timeline()` directly.

The existing flow already maps each audio-manifest chapter to:

- `reel_001`, `reel_002`, etc.;
- an absolute master-audio range;
- a local word-timing array;
- fixed sample boundaries;
- fixed render-frame boundaries;
- internal 5–15 second beats;
- one timeline hash.

Only ensure the source paragraph IDs are `reel_001`, `reel_002`, etc., and that
product metadata declares these units independently publishable.

Do not introduce a new standalone timeline builder unless a measured gap in the
existing function requires it.

Preserve:

- `_shot_boundaries`;
- `SHOT_TARGET_SECONDS`;
- `SHOT_MIN_SECONDS`;
- `SHOT_MAX_SECONDS`;
- `_assert_immutable_timeline`;
- `_apply_frame_aligned_timing`;
- `_write_chapter_cues`;
- the master-audio hash lock.

Internal beats remain useful for:

- synchronized preview navigation;
- bounded editing of one time window;
- review checkpoints;
- describing visual progression inside a 30–40 second Reel.

They are not separate initial generation prompts.

## 9. Visual generation: batch 2–3 independent Reels per prompt

Use the existing `motion_canvas.pipeline.generate()` without replacing its
batch architecture.

Call `prepare()` with `batch_size=2` or `batch_size=3`. The manifest then drives
the existing code:

```python
work_batches = manifest["batches"]

with ThreadPoolExecutor(max_workers=workers) as executor:
    future_map = {
        executor.submit(generate_batch, batch): batch
        for batch in work_batches
    }
```

The existing prompt marker format is exactly what is needed:

```text
=== reel_001.tsx ===
...complete independent Reel source...

=== reel_002.tsx ===
...complete independent Reel source...
```

The visual coder receives two or three Reel specifications in one request and
returns two or three complete source files.

### Prompt changes

Keep `template_lab/motion_canvas/prompts/batch.system.txt` and
`_batch_prompt()` as the foundation. Add product-specific context stating:

- every supplied Reel is a separate publishable video;
- do not create narrative or visual dependencies between them;
- every Reel starts from a valid standalone initial frame;
- every Reel reaches a complete payoff/final state;
- each source owns its full 30–40 second local clock;
- reuse presentation components and motion grammar where helpful;
- 2–3 Reels in the request may deliberately use a related visual style;
- do not import generated source/state from a sibling Reel;
- keep portrait content within the supplied safe area;
- use only cue keys supplied for that Reel.

The batch request may include a shared `batch_visual_direction` so two or three
Reels can efficiently use the same visual family. That direction is stylistic,
not narrative:

```json
{
  "batch_visual_direction": {
    "shared_palette": true,
    "shared_motion_grammar": "persistent apparatus with signal-driven changes",
    "allowed_shared_components": ["SceneTitle", "TextCard", "KineticActor"],
    "forbid_cross_reel_state": true
  }
}
```

### Installation and repair

Keep the existing behavior:

1. Cache the raw batch response.
2. Parse every expected marker.
3. Enforce each Reel’s immutable duration independently.
4. Validate each TSX and cue set independently.
5. Repair only the failing Reel source when possible.
6. Write successful Reel sources even if a sibling in the same batch needs
   repair.
7. Compile the assembled production.
8. Group TypeScript errors by `reel_###.tsx`.
9. Repair only measured compile failures.
10. Preserve cached successful batches on resume.

Do not use `reel_pack.visuals.generate_visual_sources()`, which currently loops
over child projects and makes one 64k-token call per Reel.

## 10. Visual continuity

Within one 30–40 second Reel:

- use its existing internal beats to evolve one persistent composition;
- avoid clearing/rebuilding the canvas at every beat;
- keep the main apparatus, diagram, or actors visible when that improves
  comprehension;
- use signal-driven changes and deliberate transitions;
- close with a stable payoff frame.

Across separate Reels in the same batch:

- related palette, typography, components, and motion grammar are encouraged;
- a similar canvas layout may be reused for two or three Reels where suitable;
- every source must still initialize and render independently;
- never rely on a previous Reel’s ending state.

This satisfies both goals: efficient batch generation and independently
publishable stories.

## 11. Compile and preview

Reuse the existing long-form compile/preview path:

- `motion_canvas.pipeline.assemble`;
- `_sync_runtime`;
- TypeScript typecheck;
- browser build;
- deterministic frame validation;
- `robot-report.json`;
- `validation.json`;
- contact sheet generation;
- live Motion Canvas preview server;
- `chapter-player.html` with start/end and visual frame range.

The current long-form UI already supports:

- selecting a `reel_###` timeline unit;
- playing only its synchronized range;
- navigating its internal beats;
- showing its narration;
- regenerating a bounded beat in context.

For the Reel product, relabel the workspace but do not rebuild it:

- “Continuous reels” → “Independent Reels”;
- “chapter” → “Reel” where visible;
- show hook and payoff metadata;
- show measured Reel duration;
- use portrait preview dimensions.

## 12. Independent rendering and download

This is the main capability that must be added to the shared infrastructure.

Add a renderer that accepts a timeline unit:

```bash
python template_lab/scripts/mav_render.py \
  --run-id <run-id> \
  --motion-reel-id reel_003 \
  --output template_lab/runs/<run-id>/motion_canvas/renders/reel_003.mp4
```

The renderer must:

1. Load the immutable manifest.
2. Resolve `render_start_frame` and `render_end_frame`.
3. Render only that visual frame range.
4. Start the output video at local time zero.
5. Mux only the matching Reel audio chunk or exact audio sample range.
6. Produce 1080×1920 H.264 MP4.
7. Probe duration, dimensions, video stream, and audio stream.
8. Write a per-Reel render report.
9. Support resuming cached frames using a fingerprint that includes:
   - timeline ID;
   - Reel ID;
   - source hash;
   - audio hash;
   - FPS;
   - dimensions;
   - start/end frames.

Recommended outputs:

```text
motion_canvas/renders/reel_001.mp4
motion_canvas/renders/reel_001.report.json
```

Do not copy the whole production to a temporary child project merely to render
one Reel. Range rendering belongs in the shared renderer.

## 13. Review and approval

Technical QA may compile the whole production because that is efficient, but
review and approval must be recorded per Reel:

```json
{
  "reel_001": {
    "technical_status": "passed",
    "visual_review": "passed",
    "approval": "approved",
    "render": "rendered"
  }
}
```

Reuse the existing lesson evidence tool’s `--reels` filtering and per-Reel
frame metadata.

Allow:

- preview one Reel while another is missing;
- screen all technically ready Reels in one multimodal request;
- approve one Reel;
- regenerate one Reel or one internal beat;
- render one approved Reel;
- queue all approved Reels as separate range-render jobs.

A failing Reel must not block rendering a different approved Reel.

## 14. Studio UI

Use the existing long-form production workspace as the primary Reel-pack UI.

Required changes:

1. Creation form:
   - content product: `Independent Reels`;
   - count default: `5`;
   - count options/range: `4–5`;
   - duration default: `35`;
   - duration range: `30–40`;
   - visual batch size: `2` or `3`.
2. Stepper:
   - keep the same long-form stages and controls;
   - do not create a second stage engine.
3. Reel workspace:
   - reuse the existing timeline-unit selector;
   - show one card/tab per independent Reel;
   - retain internal beat selection;
   - add hook/payoff;
   - add per-Reel approve, render, and download controls.
4. Pack actions:
   - `Generate visuals` uses existing batches;
   - `Screen ready Reels`;
   - `Render approved`;
   - `Download` beside each completed MP4.
5. Logs:
   - `Batch 1/3 started: reel_001, reel_002`;
   - provider/model;
   - response received;
   - each Reel parse/validation status;
   - compile repair status;
   - batch terminal status.

Retire the duplicated pipeline rendering and status inference in
`studio/static/reel-pack-ui.js`. Keep product-specific presentation as a thin
layer around the shared workspace.

## 15. File-level implementation

### `template_lab/reel_pack/planning.py`

- Keep independent Pack planning and script writing.
- Change default count from 12 to 5.
- Emit 4–5 independent Reel records.
- Combine validated Reel scripts into the normal `narration.json` paragraph
  array at the Pack root.
- Stop creating a full child production directory for each Reel.

### `template_lab/reel_pack/schema.py`

- Restrict normal Reel count to 4–5.
- Restrict target/measured duration to 30–40 seconds.
- Require hook, retention device, open loop, payoff, facts, and objectives.
- Reject cross-Reel dependency language.
- Validate stable `reel_###` IDs.

### `template_lab/reel_pack/pipeline.py`

- Retain Pack-specific planning and publishing metadata.
- Delegate audio, timing, visual generation, compile/preview, and render to the
  shared long-form services.
- Remove child-loop orchestration.

### `template_lab/reel_pack/visuals.py`

- Retire the one-call-per-child `generate_visual_sources`.
- Retire child-only compile/render behavior after shared range rendering works.
- Keep only small compatibility adapters for legacy runs if required.

### `template_lab/motion_canvas/pipeline.py`

- Reuse `prepare(..., batch_size=2|3)`.
- Add product metadata to `_batch_prompt()` without forking the generator.
- Ensure portrait canvas settings are supplied through the manifest rather than
  hard-coded landscape prompt text.
- Keep existing batching, caching, parse, validation, repair, assembly, and
  compile flow.

Important correction: `_batch_prompt()` currently contains a fixed
`Canvas 1920x1080` theme string. Replace that with manifest-driven dimensions
and safe bounds so portrait Reel packs receive 1080×1920 instructions while
full-length defaults stay unchanged.

### `template_lab/scripts/mav_generate_reel_pack.py`

- Make it an input/planning adapter to the shared generation runner.
- Pass count, duration, portrait canvas, batch size, and product context.
- Do not call a separate visual generator.

### `template_lab/scripts/mav_render.py`

- Add `--motion-reel-id`.
- Add fixed frame-range rendering and matching audio extraction/muxing.
- Add per-Reel report/fingerprint/resume support.
- Keep current whole-production rendering unchanged when the flag is absent.

### `studio/server.py`

- Use shared run detail/artifact snapshot for Reel packs.
- Add per-Reel approval and range-render endpoints.
- Extend render queue entries with optional `motion_reel_id`.
- Keep shared preview and bounded-beat regeneration endpoints.

### `studio/reel_pack_extension.py`

- Keep product creation and product-specific metadata.
- Remove replacement implementations of the shared stage runner.
- Delegate to shared server commands.

### `studio/static/app.js`

- Reuse the existing chapter/Reel workspace.
- Add product-aware labels and per-Reel render/download controls.

### `studio/static/reel-pack-ui.js`

- Reduce to creation-form additions and small product-specific decorations.
- Remove duplicated stepper, model map, process polling, and stage calculations
  once the shared UI covers the product.

## 16. Status model

Keep run-level stage progress and add per-Reel status:

```text
planned
scripted
audio_ready
timed
visual_pending
visual_ready
qa_failed
preview_ready
flagged
approved
rendering
rendered
```

Batch status must be terminal only when every expected marker has been handled:

```json
{
  "batch_01": {
    "reel_ids": ["reel_001", "reel_002"],
    "status": "partial",
    "results": {
      "reel_001": "visual_ready",
      "reel_002": "repairing"
    }
  }
}
```

A model usage log means “response received”, not “batch complete” or
“generation complete”.

## 17. Migration

1. Treat existing nested-child Reel packs as `legacy_reel_pack_v1`.
2. Do not silently mix their artifacts with the new shared layout.
3. Preserve old runs as readable.
4. Switch only newly created Reel packs to `reel_pack_v2`.
5. Optionally reuse validated planning/script text from an old run.
6. Regenerate audio/timeline/visual artifacts into the v2 root layout.
7. Remove legacy execution code only after v2 passes end-to-end tests.

## 18. Tests

### Planning/script tests

- default count is 5;
- count outside 4–5 is rejected for the normal product;
- each Reel has a unique hook/open-loop/payoff;
- every Reel is standalone;
- cross-Reel dependency language is rejected;
- all facts/objectives are grounded.

### Audio/timeline tests

- each narration paragraph creates one audio chunk;
- each chunk becomes one immutable Reel;
- each Reel measures 30–40 seconds;
- timeline units and frames are contiguous;
- internal beats remain within their parent Reel;
- audio/timeline hashes prevent accidental retiming.

### Batch generation tests

- four Reels with batch size two create two requests;
- five Reels with batch size two create three requests;
- five Reels with batch size three create two requests;
- each response contains all expected markers;
- a valid sibling source is preserved when another source needs repair;
- cached successful batches are not repurchased on resume;
- portrait dimensions appear in prompts;
- compile errors are grouped and repaired by Reel ID.

### Preview/edit tests

- select and play only `reel_003`;
- audio and visual ranges begin at local zero;
- internal beat navigation remains synchronized;
- regenerating one Reel preserves all other Reel sources;
- regenerating a beat preserves the immutable timeline.

### Render tests

- render only one Reel from a five-Reel production;
- output is 1080×1920 with audio;
- output duration matches the Reel range;
- neighboring Reel audio is absent;
- rendering one approved Reel works when siblings are incomplete;
- range-render resume fingerprint invalidates only when relevant inputs change.

### Regression tests

- normal long-form script/audio generation is unchanged;
- normal long-form batching is unchanged;
- normal long-form preview is unchanged;
- whole-production rendering is unchanged;
- bounded beat regeneration is unchanged.

## 19. Acceptance criteria

The implementation is complete when:

1. One topic produces 4–5 independently understandable Reel scripts.
2. Each measured Reel lasts 30–40 seconds.
3. Each Reel has a catchy opening, retention mechanism, and closed payoff.
4. The Motion Canvas manifest batches 2–3 complete Reels per request.
5. Five Reels require only two or three initial visual-coder requests.
6. Every response is parsed into independent `reel_###.tsx` sources.
7. Related Reels may share a visual style without sharing story/runtime state.
8. The shared long-form compile, repair, preview, review, and rendering
   infrastructure is used.
9. Any Reel can be previewed, approved, rendered, and downloaded independently.
10. Existing full-length productions continue to behave exactly as before.

## 20. Recommended implementation sequence

1. **Schema/defaults**: 4–5 independent 30–40 second Reel paragraphs.
2. **Root run layout**: stop creating one child Motion Canvas project per Reel.
3. **Shared audio/timeline**: feed Reel paragraphs through the normal long-form
   audio and immutable Reel builder.
4. **Shared visual batching**: call `prepare(batch_size=2|3)` and existing
   `generate()`.
5. **Portrait contract**: make batch prompt/runtime canvas dimensions
   manifest-driven.
6. **Range renderer**: independently render/mux one Reel.
7. **Shared UI**: use the existing production/Reel workspace and add per-Reel
   render/download.
8. **Review/status**: per-Reel approval with Pack-level aggregation.
9. **Migration and cleanup**: legacy read support, then retire duplicate paths.

First prove four cached/fake Reels through shared batching, preview, and one
independent range render. Only then switch live paid generation to v2.
