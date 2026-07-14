# Migration Plan: Legacy Physics V3/MAV Pipeline → Single-Agent Direct-HTML Composer

## 1. Purpose

Replace the current recipe/MAV scene-generation layer with a new animation-generation system in which one coding agent reads the full timed lesson and directly creates the final HTML, CSS, SVG, and JavaScript animation.

The migration must preserve the reliable parts of the existing system:

- curriculum registry and syllabus-objective coverage;
- trusted facts and claim IDs;
- narration generation;
- TTS generation;
- Whisper paragraph and word timings;
- physics, mathematics, unit, and originality verification;
- browser preview;
- FFmpeg/HyperFrames rendering;
- final video QA;
- publishing-package generation;
- resumable runs and cached artifacts.

The migration should replace only the rigid visual-production section:

```text
objective IDs
    ↓
recipe selection / MAV routing
    ↓
typed recipe compilation
    ↓
many isolated scene files
```

with:

```text
full narration + timings + physics facts + asset manifest
    ↓
one direct-HTML coding-agent run
    ↓
one integrated lesson HTML application
    ↓
browser inspection and targeted self-repair
```

---

## 2. Core product decision

The new system must not use:

- objective-to-recipe selection as the primary visual generator;
- a JSON scene plan that a separate renderer interprets creatively;
- one model call per beat;
- one isolated HTML file per narration beat;
- a giant hand-written deterministic layout system;
- full regeneration when only one visual chapter fails.

The new system must use:

- one visual coding agent for the complete lesson;
- one shared 1920×1080 HTML/SVG stage;
- approximately 6–8 visual chapters per 6–8 minute lesson;
- approximately 12–16 major composition states;
- continuous reuse and transformation of visual objects;
- a tiny motion micro-core for repetitive technical work;
- direct HTML/CSS/SVG/JavaScript output;
- real browser rendering before approval;
- targeted chapter-level repair;
- deterministic physics data, but generative visual composition.

The guiding principle is:

> Deterministic truth, generative presentation.

---

## 3. Existing pipeline and target pipeline

### Existing production flow

```text
facts.json
    ↓
narration.json
    ↓
voiceover.mp3
    ↓
audio_timing.json + audio_word_timestamps.json
    ↓
split narration into beats
    ↓
claim IDs → objective IDs
    ↓
select objective-linked recipe or MAV module
    ↓
create scene plan and separate scene artifacts
    ↓
compile typed recipes into DOM/SVG/GSAP
    ↓
build master preview
    ↓
manual/automated QA
    ↓
render MP4
```

### Target production flow

```text
facts.json
    ↓
narration.json
    ↓
voiceover.mp3
    ↓
audio_timing.json + audio_word_timestamps.json
    ↓
build direct-HTML lesson input bundle
    ↓
single coding agent reads the full lesson
    ↓
agent directly writes lesson.html
    ↓
open lesson.html in Chromium
    ↓
capture chapter keyframes + console + layout metrics
    ↓
same agent patches failed chapters in the same HTML
    ↓
approved master HTML
    ↓
existing render and final-video QA pipeline
```

---

## 4. What remains unchanged

The following legacy components should remain operational.

### Curriculum and coverage

Keep:

```text
video_engine/curriculum/objectives.json
video_engine/curriculum/topic_order.json
video_engine/curriculum/prerequisites.json
video_engine/curriculum/coverage_registry.json
video_engine/registry/videos.json
video_engine/registry/original_questions.json
video_engine/registry/content_fingerprints.json
```

These remain the source of truth for what must be taught and what has already been covered.

### Script and fact grounding

Keep:

- trusted topic fact preparation;
- claim IDs attached to narration paragraphs;
- objective IDs;
- verified examples and calculations;
- physics critic;
- learning critic;
- duplication checks.

### Audio

Keep:

- TTS generation;
- audio caching;
- paragraph timing;
- Whisper word timestamps;
- narration/audio consistency checks.

### Rendering and packaging

Keep:

- Chromium preview;
- HyperFrames or the current pinned-frame renderer;
- FFmpeg export;
- captions;
- transcript;
- thumbnails;
- final MP4 checks;
- publishing package.

---

## 5. What must be replaced

Deprecate the following as the default visual route:

```text
template_lab/scripts/mav_plan_v3.py
template_lab/scripts/mav_recipes.py
template_lab/assets/objective_visual_recipes.json
physics_animation_engine/engine/scene_recipe.js
template_lab/scripts/mav_build_preview_v3.py
```

Do not delete them immediately. Move them behind a compatibility flag:

```bash
--animation-mode legacy-recipes
```

The new default becomes:

```bash
--animation-mode direct-html
```

The old route remains available until the new route passes the first two complete topic packages.

---

## 6. New architecture

Add a new package:

```text
template_lab/direct_html/
  __init__.py
  build_input_bundle.py
  composer.py
  prompt_builder.py
  html_contract.py
  browser_inspector.py
  repair_loop.py
  chapter_index.py
  asset_manifest.py
  physics_context.py
  direct_html_validator.py
  render_adapter.py

physics_animation_engine/direct_html/
  motion-core.js
  motion-core.css
  asset-loader.js
  phrase-timing.js
  physics-helpers.js
  browser-probe.js

template_lab/prompts/
  direct_html_composer.system.txt
  direct_html_repair.system.txt
  direct_html_review.system.txt
```

### Main responsibility of each component

#### `build_input_bundle.py`

Combines:

- approved narration;
- paragraph timings;
- word timings;
- trusted facts;
- objective IDs;
- physics invariants;
- approved on-screen copy;
- asset manifest;
- visual style guide;
- lesson duration;
- output dimensions.

#### `composer.py`

Calls one coding model for the full lesson and expects one complete HTML document.

#### `html_contract.py`

Defines the minimum required HTML structure, IDs, metadata, and chapter markers.

#### `browser_inspector.py`

Runs the generated HTML in Chromium and gathers:

- JavaScript errors;
- missing assets;
- key screenshots;
- active SVG/DOM element bounds;
- text sizes;
- safe-area violations;
- blank frames;
- frozen frames;
- chapter start/end states.

#### `repair_loop.py`

Sends only the failed chapter context, screenshots, browser findings, and current HTML section back to the same model.

#### `chapter_index.py`

Maintains chapter boundaries so individual sections can be repaired without rewriting the complete lesson.

#### `render_adapter.py`

Allows the existing rendering pipeline to render the new HTML exactly as it renders the current master preview.

---

## 7. New run artifacts

For every run, write:

```text
template_lab/runs/<run-id>/
  input.json
  narration.json
  voiceover.mp3
  audio_timing.json
  audio_word_timestamps.json

  direct_html/
    lesson_input_bundle.json
    asset_manifest.json
    physics_context.json
    composer_prompt.txt
    composer_response.html
    master.html
    chapter_index.json
    generation_manifest.json

    inspection/
      initial_report.json
      chapter_01/
        start.png
        peak.png
        end.png
        metrics.json
      chapter_02/
        start.png
        peak.png
        end.png
        metrics.json

    repairs/
      repair_01_request.json
      repair_01_response.html
      repair_02_request.json
      repair_02_response.html

    validation/
      html_validation.json
      physics_validation.json
      layout_validation.json
      timeline_validation.json
      final_direct_html_report.json

  renders/
    master.mp4
```

The canonical final source becomes:

```text
direct_html/master.html
```

---

## 8. Input supplied to the coding agent

The agent should receive one complete lesson bundle, not 42 isolated beat prompts.

Example structure:

```json
{
  "video": {
    "video_id": "P0625-1.1-01",
    "title": "Mastering Physical Quantities and Measurement",
    "duration_seconds": 348.744,
    "resolution": [1920, 1080],
    "fps": 30
  },
  "narration": {
    "paragraphs": [...],
    "word_timestamps": [...]
  },
  "grounding": {
    "facts": [...],
    "claim_to_objective_map": {...},
    "physics_invariants": [...]
  },
  "assets": {
    "icons": [...],
    "physics_svg_assets": [...],
    "allowed_fonts": [...],
    "local_paths": {...}
  },
  "visual_direction": {
    "style": "clean modern educational motion graphics",
    "max_active_objects": 8,
    "safe_margin_px": 100,
    "minimum_text_px": 30,
    "target_chapters": [6, 8],
    "target_compositions": [12, 16]
  }
}
```

This JSON is only an input package for the model. It is not a scene plan and is not translated into the layout.

---

## 9. Required model output

The coding model must return one directly executable HTML document.

It must include:

```html
<!doctype html>
<html>
<head>
  <!-- local CSS and motion-core references -->
</head>
<body>
  <div id="viewport">
    <svg id="stage" viewBox="0 0 1920 1080">
      <g id="camera">
        <g id="background-layer"></g>
        <g id="world-layer"></g>
        <g id="diagram-layer"></g>
        <g id="annotation-layer"></g>
        <g id="overlay-layer"></g>
      </g>
    </svg>
    <div id="html-overlay-layer"></div>
  </div>

  <script src="motion-core.js"></script>
  <script>
    // direct model-generated composition and animation
  </script>
</body>
</html>
```

The LLM itself must decide:

- exact composition;
- exact coordinates;
- relative sizes;
- SVG structure;
- visual hierarchy;
- chapter transitions;
- camera movement;
- appearance/disappearance of objects;
- how one concept transforms into another;
- how paragraph meaning maps to motion;
- which local assets are reused;
- which simple SVGs are created inline.

No downstream renderer may reinterpret those decisions.

---

## 10. HTML contract

Although the model has creative freedom, the output must follow a small technical contract.

### Required root IDs

```text
viewport
stage
camera
background-layer
world-layer
diagram-layer
annotation-layer
overlay-layer
html-overlay-layer
```

### Required chapter markers

Each visual chapter must be wrapped in:

```html
<g
  data-chapter-id="chapter_01"
  data-start="0.0"
  data-end="46.5">
</g>
```

or for HTML overlays:

```html
<section
  data-chapter-id="chapter_01"
  data-start="0.0"
  data-end="46.5">
</section>
```

### Required timeline API

The lesson must expose:

```javascript
window.lessonPlayer = {
  duration,
  seek(seconds),
  play(),
  pause(),
  getCurrentTime(),
  getChapterAt(seconds)
};
```

This allows preview, screenshot QA, deterministic seeking, and final rendering.

### Required metadata

The HTML must expose:

```javascript
window.lessonManifest = {
  videoId,
  duration,
  chapters,
  objectiveIds,
  generatedBy,
  version
};
```

This is not a layout plan. It is only runtime metadata.

---

## 11. Motion micro-core

Create one small reusable runtime, preferably under 10–20 KB minified.

It should provide only generic technical helpers:

```javascript
show(element, options)
hide(element, options)
drawPath(element, options)
move(element, options)
scale(element, options)
morphPath(from, to, options)
focusCamera(targets, options)
fitCamera(targets, padding)
atPhrase(phrase, callback)
betweenPhrases(startPhrase, endPhrase, callback)
clearChapter(chapterId)
measureSafeArea(chapterId)
```

It should not provide:

- objective-specific recipes;
- fixed scene templates;
- hard-coded lesson layouts;
- automatic visual metaphors;
- automatic scene selection;
- topic-specific choreography.

The agent remains the animator. The micro-core only removes repetitive code.

---

## 12. Asset strategy

The agent may use three asset sources.

### Inline SVG created by the agent

Use for:

- arrows;
- graphs;
- axes;
- force diagrams;
- simple apparatus;
- geometric shapes;
- motion trails;
- equations;
- labels;
- simple vehicles and robots.

### Local general icon library

Use approved local icons for:

- eye;
- stopwatch;
- thermometer;
- warning;
- question;
- battery;
- light;
- sound;
- timer.

Do not allow runtime internet requests.

### Local reusable physics SVG assets

Use for detailed apparatus that would be wasteful to redraw repeatedly:

```text
measuring-cylinder.svg
pendulum.svg
trolley.svg
convex-lens.svg
ray-box.svg
ripple-tank.svg
battery.svg
resistor.svg
motor.svg
transformer.svg
geiger-counter.svg
```

These are static, well-structured drawings, not pre-animated recipes.

Every reusable SVG asset should expose named parts through IDs or `data-part` attributes.

---

## 13. Full-lesson generation strategy

The coding agent should read the complete lesson and internally group it into approximately 6–8 chapters.

Example:

```text
Chapter 1 — Hook and why measurement matters
Chapter 2 — Scalars and vectors
Chapter 3 — Measuring length and volume
Chapter 4 — Meniscus and parallax
Chapter 5 — Timing and averaging
Chapter 6 — Vector addition worked example
Chapter 7 — Transfer question and synthesis
```

Each chapter should use one persistent visual world for 30–70 seconds.

The model should not generate 42 disconnected scenes.

Instead:

```text
42 semantic beats
    ↓
6–8 visual chapters
    ↓
12–16 major composition states
    ↓
40–60 small visual actions
```

---

## 14. Browser inspection

After generation, launch Chromium and inspect the actual result.

For each chapter capture:

```text
chapter start
most visually complex moment
chapter end
```

Also capture additional frames when:

- the camera moves;
- a graph or equation becomes primary;
- a major object transformation occurs;
- the active-object count is highest.

Collect:

```json
{
  "chapter_id": "chapter_06",
  "console_errors": [],
  "missing_assets": [],
  "overflow_elements": [],
  "overlap_pairs": [],
  "minimum_text_px": 34,
  "active_object_peak": 7,
  "blank_frames": [],
  "frozen_intervals": [],
  "safe_area_pass": true
}
```

---

## 15. Repair loop

The first generation is not assumed to be perfect.

When a chapter fails:

1. isolate the chapter;
2. provide the current HTML section;
3. provide start/peak/end screenshots;
4. provide exact browser measurements;
5. provide narration and timings only for that chapter;
6. ask the same model to patch that chapter;
7. merge the patch into `master.html`;
8. rerender only that chapter;
9. repeat until passing or until the configured repair limit is reached.

Example repair request:

```text
Chapter 4 fails.

Problems:
- measuring-cylinder label extends 72 px outside the safe area;
- eye-level guide overlaps the 50 mL label;
- text becomes 24 px after scaling;
- composition holds static for 5.8 seconds.

Do not rewrite other chapters.
Return a replacement for:
<!-- BEGIN CHAPTER chapter_04 -->
...
<!-- END CHAPTER chapter_04 -->
```

Default maximum:

```text
2 automatic repairs per chapter
1 final full-lesson review repair
```

If still failing, mark for manual review.

---

## 16. Physics accuracy

The model controls visual presentation, not scientific truth.

Before the model call, produce:

```text
direct_html/physics_context.json
```

This contains verified values and invariants.

Example:

```json
{
  "worked_example_id": "vector_3_4_5",
  "inputs": {
    "north_force_n": 3,
    "east_force_n": 4
  },
  "derived": {
    "resultant_force_n": 5,
    "angle_deg": 53.13
  },
  "invariants": [
    "north and east vectors are perpendicular",
    "resultant connects the common origin to the final point",
    "triangle side proportions are 3:4:5",
    "magnitude label must be 5 N"
  ]
}
```

The HTML validator should extract or inspect declared values where practical.

The existing physics critic and final vision QA remain mandatory.

---

## 17. Direct-HTML validation

Add checks for:

### Technical validity

- HTML parses;
- JavaScript syntax passes;
- required runtime interface exists;
- local assets resolve;
- no external network requests;
- no forbidden APIs;
- deterministic seeking works;
- no console errors.

### Timeline validity

- lesson duration matches audio;
- chapter ranges do not overlap incorrectly;
- all chapters are reachable;
- seeking backward restores correct visual state;
- no action extends beyond lesson duration.

### Layout validity

- no important object outside safe area;
- minimum text size;
- no severe label collision;
- no composition requiring excessive shrink;
- no chapter with excessive active-object count.

### Physics validity

- values match `physics_context.json`;
- graph labels and units are correct;
- directions are correct;
- diagrams satisfy objective invariants.

### Performance validity

- DOM/SVG element count remains below threshold;
- no excessive per-frame DOM creation;
- no runaway requestAnimationFrame loops;
- acceptable browser memory usage;
- acceptable render time per frame.

---

## 18. CLI changes

Add:

```bash
python3 -m video_engine.cli generate-video P0625-1.1-01 \
  --animation-mode direct-html
```

Additional commands:

```bash
python3 -m video_engine.cli compose-html P0625-1.1-01
python3 -m video_engine.cli inspect-html P0625-1.1-01
python3 -m video_engine.cli repair-html P0625-1.1-01 --chapter chapter_04
python3 -m video_engine.cli preview-html P0625-1.1-01
python3 -m video_engine.cli render-html P0625-1.1-01
```

Resume controls:

```bash
--from-step direct-html-input
--from-step direct-html-compose
--from-step direct-html-inspect
--from-step direct-html-repair
--from-step render
```

---

## 19. Updated generation stages

The revised `generate-video` workflow becomes:

```text
1. load approved video brief
2. retrieve approved archetypes
3. generate original questions and solutions
4. verify physics, maths, units, route, and originality
5. generate narration and on-screen copy
6. run script critics and repair
7. generate TTS
8. derive paragraph and word timings
9. build direct-HTML input bundle
10. call one coding agent for the complete lesson
11. validate HTML and JavaScript
12. run browser inspection
13. repair only failed chapters
14. create approved master.html
15. render with existing frame/video pipeline
16. run final video QA
17. build publishing package
```

---

## 20. Prompt design

Create `direct_html_composer.system.txt`.

It should tell the model:

- you are the sole motion designer and frontend animator;
- directly create final executable HTML;
- there is no downstream layout translator;
- use the full narration and timing context;
- group beats into chapters;
- keep one evolving composition for related ideas;
- use inline SVG for simple scientific visuals;
- use approved local assets for detailed apparatus;
- use the small motion core only for generic animation utilities;
- maintain one clear focal point;
- avoid presentation-card layouts;
- preserve negative space;
- keep active objects limited;
- never rely on remote assets;
- use verified physics values exactly;
- expose `lessonPlayer`;
- include chapter markers;
- ensure deterministic seeking;
- return only complete HTML.

The repair prompt should tell the model:

- modify only the named chapter;
- preserve all external IDs and runtime contracts;
- use the supplied screenshots and measurements;
- do not alter narration timing;
- do not change verified physics facts;
- return only the replacement chapter block.

---

## 21. Model-call strategy

Use:

```text
1 main full-lesson composition call
0–N chapter repair calls
1 optional full-lesson visual-review call
```

Do not call the model once per beat.

Cache:

- model input hash;
- prompt version;
- asset-manifest version;
- motion-core version;
- generated HTML;
- chapter repairs.

A rerun should skip composition when all relevant hashes match.

---

## 22. Migration phases

### Phase 0 — Freeze the legacy baseline

Before changing code:

- run the current Topic 1.1 smoke lesson;
- save current preview and MP4;
- save QA reports;
- record generation time;
- record API cost;
- record scene count;
- record manual repair count.

This becomes the comparison baseline.

### Phase 1 — Build the micro-core and HTML contract

Implement:

- `motion-core.js`;
- fixed 1920×1080 stage;
- `lessonPlayer` interface;
- deterministic seek;
- chapter markers;
- local asset loading;
- basic browser probe.

Do not integrate the LLM yet.

Create two manually written HTML fixtures and render them.

### Phase 2 — Build input bundling and one-segment composer

Use paragraphs 9–10 of Topic 1.1 as the first test:

```text
3 N north
4 N east
right triangle
5 N resultant
```

Generate one 30–50 second HTML composition.

Acceptance:

- direct output opens without transformation;
- deterministic seek works;
- physics values are correct;
- layout fits;
- final render works.

### Phase 3 — Add browser inspection and repair

Implement:

- screenshots;
- safe-area metrics;
- console capture;
- text-size check;
- blank/frozen-frame checks;
- targeted chapter replacement.

Test deliberate failures:

- overflow;
- missing asset;
- duplicate ID;
- broken JavaScript;
- tiny text;
- static chapter;
- incorrect physics label.

### Phase 4 — Generate one complete Topic 1.1 video

Use the full narration and audio.

Target:

```text
6–8 chapters
12–16 major states
one master HTML
no beat-by-beat scene generation
```

Compare against the legacy output.

### Phase 5 — Parallel production mode

Run both:

```text
legacy-recipes
direct-html
```

for the first two complete topics:

```text
1.1 Physical quantities and measurement techniques
1.2 Motion
```

Do not remove the legacy route until both topics pass.

### Phase 6 — Make direct HTML the default

When acceptance criteria are satisfied:

```text
default: direct-html
fallback: legacy-recipes
```

Keep the legacy route for emergency production for at least one release cycle.

### Phase 7 — Retire unused recipe infrastructure

Only after stable production:

- stop expanding objective recipe coverage;
- archive unused recipe registries;
- retain reusable SVG assets and physics modules;
- remove dead routing code gradually;
- keep migration notes and rollback tag.

---

## 23. Acceptance criteria

The direct-HTML route is ready when:

### Reliability

- at least 9 of 10 full-lesson generations produce syntactically valid HTML;
- all generated lessons expose the required runtime API;
- deterministic seek passes;
- failed chapters can be repaired independently;
- no full lesson needs regeneration for a single layout issue.

### Visual quality

- no presentation-like repeated card sequence;
- one clear visual focus per state;
- important change every 5–12 seconds;
- no severe overflow;
- no unreadably small text;
- no more than 6–8 major visual chapters in a normal lesson;
- transitions feel continuous within each chapter.

### Scientific quality

- all calculations and units remain correct;
- diagrams satisfy physics invariants;
- graph values agree with narration;
- objective coverage is unchanged;
- no factual drift introduced by the coding model.

### Efficiency

- one main coding-model call per lesson;
- lesson-specific output preferably below 30K tokens;
- generated HTML preferably below 150 KB before assets;
- initial generation cost and total repair cost are recorded;
- total generation time improves over beat-by-beat custom generation.

### Rendering

- existing MP4 rendering pipeline works without manual conversion;
- final resolution, frame rate, codec, duration, audio, and captions remain valid.

---

## 24. Rollback and safety

Every run stores:

```text
animation_mode
composer_model
prompt_version
motion_core_version
asset_manifest_version
input_hash
html_hash
repair_count
```

If direct HTML fails:

```bash
python3 -m video_engine.cli generate-video P0625-1.1-01 \
  --animation-mode legacy-recipes \
  --from-step scenes
```

The migration must never remove the ability to finish a production run using the legacy route during the evaluation period.

---

## 25. Recommended implementation order

Build in this exact order:

```text
1. add --animation-mode flag
2. preserve legacy path unchanged
3. create direct_html package
4. implement motion-core.js
5. implement lessonPlayer contract
6. implement input bundle builder
7. implement full-lesson composer prompt
8. save direct model output as master.html
9. integrate Chromium preview
10. add JavaScript and HTML validation
11. add keyframe screenshots
12. add layout metrics
13. add chapter-level repair
14. connect existing renderer
15. test 46-second vector segment
16. test one complete Topic 1.1 video
17. test full Topic 1.1 package
18. test Topic 1.2 package
19. compare cost, speed, QA, and visual quality
20. switch default only after acceptance criteria pass
```

---

## 26. First implementation ticket

### Ticket: Direct HTML proof of concept for vector addition

Input:

```text
paragraph_09: 208.78–234.78
paragraph_10: 234.78–255.42
objective: 1_1_S07
```

Required output:

```text
direct_html/master.html
```

The HTML must:

- use one 1920×1080 SVG stage;
- show a robot;
- draw 3 N north;
- draw 4 N east;
- construct a right triangle;
- derive a 5 N resultant;
- move the robot along the resultant;
- expose deterministic seek;
- use no remote assets;
- pass browser console checks;
- fit within the safe area;
- render through the existing MP4 pipeline.

This proof of concept should be completed before any full-pipeline rewrite.

---

## 27. Final target architecture

```text
CURRICULUM + COVERAGE CONTROL
                ↓
VERIFIED FACTS + SCRIPT + AUDIO + TIMINGS
                ↓
DIRECT-HTML INPUT BUNDLE
                ↓
ONE CODING AGENT
designs + codes full lesson HTML
                ↓
CHROMIUM PREVIEW
                ↓
MEASURE + SCREENSHOT + VALIDATE
                ↓
TARGETED CHAPTER REPAIR
                ↓
APPROVED MASTER.HTML
                ↓
EXISTING VIDEO RENDER + FINAL QA
                ↓
PUBLISHING PACKAGE
```

The new system is not “LLM plan plus deterministic renderer.”

It is:

> one LLM-generated final animation application, supported by a tiny runtime, verified by the browser, and protected by the existing physics and production QA pipeline.
