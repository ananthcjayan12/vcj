# MAV Physics Studio — Short-Form Reel Generation Implementation Plan

## 1. Objective

Extend MAV Physics Studio so that every completed long-form physics lesson can produce multiple self-contained vertical Shorts/Reels while reusing as much of the existing work as possible.

The Shorts must not be simple extracts or crops of long-form chapters. Each Short must:

* Work without requiring the viewer to watch the long-form video.
* Begin with a strong standalone hook.
* Explain one clear concept.
* Reach a satisfying payoff.
* Use a native 9:16 composition.
* Reuse existing narration, audio, diagrams, Motion Canvas code and physics logic wherever practical.
* Generate only the missing hook, bridge, payoff, captions or portrait layout.
* Never modify or damage the approved long-form run.

The implementation should create **child Short runs** underneath an existing long-form production run.

---

# 2. Current system constraints

The current production route is:

```text
grounded topic packet
→ lesson structure
→ complete narration
→ chapter-based voice generation
→ local word alignment
→ immutable audio reels
→ TypeScript/browser validation
→ live preview
→ final MP4 render
```

Narration and measured audio timing are already authoritative. Visual animation follows the audio timeline.

The Motion Canvas system currently creates:

* Continuous visual reels.
* Fixed reel durations.
* Semantic beat windows inside each reel.
* Reel-level TSX files.
* Reel-local cues.
* Timeline hashes.
* Audio sample boundaries.
* Render frame boundaries.

Beat regeneration already modifies the parent reel while preserving its timing and surrounding visual state.

Audio is already generated and cached paragraph by paragraph. Each paragraph keeps its own WAV file, text, cache key, quality report, timing and provider configuration.

The current Motion Canvas runtime is landscape-only:

```ts
const SIZE = new Vector2(1920, 1080);
```

The current presentation components are also designed around a landscape safe region.

Therefore, the implementation must not simply render the current TSX at 1080×1920. A separate portrait composition layer is required.

---

# 3. Core design decision

Implement a new subsystem named:

```text
Shorts Derivative Pipeline
```

Do not add Shorts as “Step 9” of the existing long-form pipeline.

A long-form run may create several Shorts. Each Short may have its own:

* Script.
* Audio edits.
* Generated hook audio.
* Portrait TSX.
* Captions.
* Preview.
* Validation.
* Final render.
* Status.
* Model usage.
* Cost.

The relationship should be:

```text
Long-form parent run
    ├── Short 001
    ├── Short 002
    └── Short 003
```

The parent run remains immutable.

---

# 4. High-level architecture

```text
Approved long-form run
        │
        ├── input.json
        ├── story_skeleton.json
        ├── narration.json
        ├── audio_chunks/
        ├── audio_word_timestamps.json
        ├── motion_canvas/timeline.json
        ├── motion_canvas/manifest.json
        └── motion_canvas/reels/*.tsx
                │
                ▼
      1. Short Candidate Analyzer
                │
                ▼
         shorts/candidates.json
                │
          Human selection
                │
                ▼
       2. Short Script Compiler
                │
                ▼
       shorts/<id>/script.json
                │
          ┌─────┴─────┐
          ▼           ▼
  3. Audio Editor   4. Portrait Visual Adapter
          │           │
          ▼           ▼
 short voiceover   portrait Motion Canvas TSX
          │           │
          └─────┬─────┘
                ▼
       5. Local word alignment
                │
                ▼
        6. Caption generation
                │
                ▼
        7. Compile and validation
                │
                ▼
           8. Live preview
                │
                ▼
           9. MP4 rendering
```

---

# 5. Directory structure

Create the following structure inside each parent run:

```text
template_lab/runs/<parent-run-id>/
  shorts/
    candidates.json
    shorts_registry.json

    short_001/
      short_run.json
      plan.json
      script.json
      source_provenance.json

      audio/
        audio_edl.json
        reused_segments/
        generated_lines/
        voiceover.wav
        voiceover.mp3
        audio_generation.json
        audio_timing.json
        audio_word_timestamps.json

      motion_canvas/
        manifest.json
        short_001.cues.ts
        short_001.tsx
        scenes.ts
        validation.json
        robot-report.json
        preview/
        frames/
        render-checkpoint.json
        final.mp4
        render-report.json

      captions/
        captions.json
        captions.srt
        captions.ass

      debug/
        candidate_source.json
        script_model_raw.json
        script_validation.json
        visual_adapter_prompt.txt
        visual_adapter_response.txt

      costs/
        model_usage.json
        summary.json
```

Do not store Short artifacts inside:

```text
motion_canvas/reels/
```

That folder belongs to the parent lesson timeline.

---

# 6. New Python package

Create:

```text
template_lab/shorts/
```

Recommended files:

```text
template_lab/shorts/
  __init__.py
  constants.py
  schemas.py
  candidates.py
  script.py
  audio.py
  provenance.py
  portrait.py
  captions.py
  pipeline.py
  validation.py
  rendering.py
```

## Responsibilities

### `constants.py`

Define:

```python
DEFAULT_SHORT_DURATION = 40.0
MIN_SHORT_DURATION = 20.0
MAX_SHORT_DURATION = 60.0

PORTRAIT_WIDTH = 1080
PORTRAIT_HEIGHT = 1920
SHORT_FPS = 30
```

Also define:

* Maximum source reels per Short: 2.
* Maximum concepts per Short: 1.
* Minimum hook duration.
* Maximum caption length.
* Safe-area margins.
* Minimum text sizes.
* Supported Short archetypes.

### `schemas.py`

Contain all local validation models and schema helpers.

### `candidates.py`

Analyze the long-form artifacts and generate Short candidate concepts.

### `script.py`

Create the final standalone Short script and map each spoken line to reused or generated audio.

### `audio.py`

Create the Short audio edit decision list, extract reusable source audio, generate missing TTS lines and assemble final audio.

### `provenance.py`

Record hashes and source relationships.

### `portrait.py`

Generate or adapt portrait Motion Canvas TSX.

### `captions.py`

Generate word- or phrase-level captions from the final aligned Short audio.

### `validation.py`

Perform local schema, timing, source, portrait-layout and render validation.

### `rendering.py`

Prepare the runtime and render the Short MP4.

### `pipeline.py`

Orchestrate all Short stages and support resume behavior.

---

# 7. Short candidate analysis

## 7.1 Inputs

The analyzer must consume:

```text
input.json
story_skeleton.json
narration.json
audio_chunks/manifest.json
audio_word_timestamps.json
motion_canvas/timeline.json
motion_canvas/manifest.json
motion_canvas/reels/*.tsx
```

The analyzer must fail with a clear message when the parent run does not have:

* Valid narration.
* Valid timing.
* An immutable Motion Canvas timeline.
* Generated source reels.
* Passed Motion Canvas validation.

## 7.2 Candidate archetypes

Support these initial values:

```json
[
  "misconception",
  "surprising_fact",
  "prediction_challenge",
  "exam_trap",
  "visual_explanation",
  "worked_example",
  "practical_tip",
  "quick_comparison"
]
```

## 7.3 Candidate rules

Each candidate must:

* Cover one primary claim or concept.
* Be understandable without the previous chapter.
* Have an explicit hook.
* Have a clear payoff.
* Use no more than two adjacent source reels.
* Prefer source beats with strong visual activity.
* Avoid phrases such as:

  * “As we saw earlier”
  * “In the previous section”
  * “Now that we know”
  * “Continuing from”
* Prefer durations between 25 and 50 seconds.
* Include exact claim IDs.
* Identify all source paragraphs, reels and beats.

## 7.4 Candidate scoring

Calculate:

```json
{
  "standalone_score": 0,
  "hook_score": 0,
  "payoff_score": 0,
  "visual_reuse_score": 0,
  "audio_reuse_score": 0,
  "exam_relevance_score": 0,
  "portrait_suitability_score": 0,
  "overall_score": 0
}
```

Recommended weights:

```text
standalone               25%
hook                     20%
payoff                    15%
visual reuse              15%
audio reuse               10%
exam relevance            10%
portrait suitability       5%
```

## 7.5 Output schema

Create:

```text
shorts/candidates.json
```

Example:

```json
{
  "version": "1.0",
  "parent_run_id": "physics-1-1-v01",
  "created_at": "ISO-8601",
  "source_timeline_id": "sha256",
  "candidates": [
    {
      "candidate_id": "candidate_001",
      "archetype": "misconception",
      "working_title": "You Weigh Less on the Moon",
      "hook": "An astronaut weighs less on the Moon. Did she lose any matter?",
      "promise": "Understand mass and weight in under 40 seconds.",
      "payoff": "Mass stays constant while weight changes with gravity.",
      "target_duration_seconds": 38,
      "claim_ids": ["1.1-C04"],
      "source_paragraph_ids": ["paragraph_01", "paragraph_02"],
      "source_segments": [
        {
          "reel_id": "reel_001",
          "beat_ids": ["beat_001", "beat_002"],
          "absolute_start": 0.0,
          "absolute_end": 24.8,
          "visual_reuse_mode": "adapt",
          "audio_reuse_mode": "partial"
        }
      ],
      "scores": {
        "standalone_score": 95,
        "hook_score": 91,
        "payoff_score": 89,
        "visual_reuse_score": 90,
        "audio_reuse_score": 72,
        "exam_relevance_score": 84,
        "portrait_suitability_score": 88,
        "overall_score": 89
      },
      "warnings": []
    }
  ]
}
```

Generate between three and five candidates per parent lesson.

---

# 8. Model task registration

Add two model tasks:

```text
short_candidate_analysis
short_script_writing
```

Add a third model task for portrait adaptation:

```text
short_motion_canvas_adapter
```

Optionally add:

```text
short_motion_canvas_repair
```

Update:

```text
template_lab/prompts/prompt_model_mapping.json
studio/server.py
studio/static/app.js
```

The current Studio exposes separate model selections for script, audio and Motion Canvas generation. Follow the same task-specific model-routing approach.

Add prompt files:

```text
template_lab/prompts/short_candidate_analysis.system.txt
template_lab/prompts/short_candidate_analysis.user.txt

template_lab/prompts/short_script_writing.system.txt
template_lab/prompts/short_script_writing.user.txt

template_lab/shorts/prompts/portrait_adapter.system.txt
template_lab/shorts/prompts/portrait_repair.system.txt
template_lab/shorts/prompts/portrait-approved-api.md
```

All model usage must be recorded in the existing cost ledger.

---

# 9. Short script generation

## 9.1 Script structure

The generated Short must follow:

```text
Hook
→ Context
→ Tension or prediction
→ Explanation
→ Payoff
→ Optional loop or soft CTA
```

Do not require every Short to have an explicit CTA.

A final insight or visual loop is preferable to:

```text
Follow for more.
```

## 9.2 Script line schema

Create:

```text
shorts/<short-id>/script.json
```

Example:

```json
{
  "version": "1.0",
  "short_id": "short_001",
  "candidate_id": "candidate_001",
  "title": "You Weigh Less on the Moon",
  "target_duration_seconds": 38,
  "claim_ids": ["1.1-C04"],
  "lines": [
    {
      "line_id": "line_001",
      "role": "hook",
      "text": "An astronaut weighs less on the Moon. Did she lose any matter?",
      "claim_ids": ["1.1-C04"],
      "audio_source": "generate",
      "visual_intent": "astronaut jump and question reveal"
    },
    {
      "line_id": "line_002",
      "role": "evidence",
      "text": "She has not lost any atoms.",
      "claim_ids": ["1.1-C04"],
      "audio_source": "reuse",
      "source_paragraph_id": "paragraph_01",
      "source_word_start": 12,
      "source_word_end": 18,
      "visual_intent": "retain astronaut and highlight body mass"
    }
  ],
  "closing_loop": {
    "enabled": true,
    "instruction": "End on a frame composition compatible with the opening astronaut pose."
  }
}
```

## 9.3 Script validation

Reject scripts that:

* Reference unknown claim IDs.
* Depend on unstated previous knowledge.
* Have multiple unrelated concepts.
* Exceed 60 seconds.
* Contain more than 170 spoken words.
* Contain relative references to earlier content.
* Have no hook.
* Have no payoff.
* Mark audio as reusable without a source range.
* Use source narration that does not match the declared text closely enough.

---

# 10. Audio Edit Decision List

## 10.1 Do not extract from final MP4

Use:

```text
audio_chunks/<paragraph-id>/audio.wav
```

or:

```text
voiceover.wav
```

Do not use:

```text
motion_canvas/final.mp4
```

as the source audio.

The paragraph WAV sources are cleaner and already cached.

## 10.2 Audio EDL schema

Create:

```text
shorts/<short-id>/audio/audio_edl.json
```

Example:

```json
{
  "version": "1.0",
  "sample_rate": 24000,
  "segments": [
    {
      "segment_id": "segment_001",
      "type": "generated",
      "line_id": "line_001",
      "target_path": "generated_lines/line_001.wav"
    },
    {
      "segment_id": "segment_002",
      "type": "source",
      "line_id": "line_002",
      "source_path": "../../../audio_chunks/paragraph_01/audio.wav",
      "source_start_seconds": 5.41,
      "source_end_seconds": 7.92,
      "fade_in_ms": 20,
      "fade_out_ms": 25
    }
  ]
}
```

## 10.3 Reuse algorithm

For each script line marked `reuse`:

1. Normalize the script text.
2. Search the relevant source paragraph words.
3. Find the best contiguous word range.
4. Require a high confidence threshold.
5. Snap cuts to word boundaries.
6. Include a small surrounding silence allowance when available.
7. Extract WAV using FFmpeg.
8. Add short fades.
9. Reject reuse when the cut sounds unnatural.

Do not stitch individual words from many places.

Reuse should operate on:

* Complete clauses.
* Complete sentences.
* Natural phrase groups.

## 10.4 Generated audio

Generate only lines marked:

```json
"audio_source": "generate"
```

Use the same:

* Provider.
* Model.
* Voice.
* Language configuration.
* Prompt style.

Store each generated line separately so it can be regenerated without rebuilding the complete Short.

## 10.5 Final assembly

Assemble:

```text
audio/voiceover.wav
audio/voiceover.mp3
```

After assembly:

* Run the existing local word alignment process.
* Treat the aligned final Short audio as authoritative.
* Do not derive the final Short cue timing only by offsetting source timestamps.

---

# 11. Source provenance

Create:

```text
source_provenance.json
```

Required fields:

```json
{
  "version": "1.0",
  "parent_run_id": "physics-1-1-v01",
  "parent_timeline_id": "sha256",
  "parent_voiceover_sha256": "sha256",
  "source_reels": [
    {
      "reel_id": "reel_001",
      "source_sha256": "sha256",
      "beat_ids": ["beat_001", "beat_002"]
    }
  ],
  "reused_audio": [
    {
      "paragraph_id": "paragraph_01",
      "audio_sha256": "sha256",
      "source_start_seconds": 5.41,
      "source_end_seconds": 7.92
    }
  ],
  "generated_audio_lines": ["line_001"],
  "created_at": "ISO-8601"
}
```

Before resuming or rendering a Short, validate that its source hashes still match.

If the parent source changed, mark the Short:

```text
source_stale
```

Do not silently continue.

---

# 12. Portrait Motion Canvas runtime

## 12.1 Make the renderer profile-driven

Create a render profile type:

```ts
export interface RenderProfile {
  id: 'lesson_landscape' | 'short_portrait' | 'square_social';
  width: number;
  height: number;
  fps: number;
  background: string;
}
```

Profiles:

```ts
lesson_landscape = {
  width: 1920,
  height: 1080,
  fps: 30
}

short_portrait = {
  width: 1080,
  height: 1920,
  fps: 30
}

square_social = {
  width: 1080,
  height: 1080,
  fps: 30
}
```

Update:

```text
motion_canvas_runtime/src/render-host.ts
motion_canvas_runtime/scripts/render.mjs
```

The runtime must read the selected profile from the active manifest.

Do not hardcode portrait dimensions into generated TSX.

## 12.2 Avoid breaking landscape rendering

The default profile must remain:

```text
lesson_landscape
```

Existing parent runs must render exactly as before.

Add backward-compatible behavior:

```text
Missing profile in manifest → lesson_landscape
```

---

# 13. Portrait presentation library

Create:

```text
motion_canvas_runtime/src/short-presentation.tsx
```

Do not change the existing landscape presentation components in a way that alters approved lessons.

Recommended components:

```text
ShortHook
ShortTitle
ShortSubtitle
PortraitTextCard
PortraitEquationCard
PortraitStatReadout
VerticalComparison
VerticalCardStack
DiagramStage
CaptionSafeArea
ExamTrapBadge
PredictionPrompt
AnswerReveal
ProgressBar
```

## Suggested portrait safe areas

For a 1080×1920 canvas:

```text
Full visible:
x = -540..540
y = -960..960

Primary content safe area:
x = -470..470
y = -790..720

Reserved top region:
y = -900..-760

Reserved caption region:
y = 650..840

Avoid critical content near:
bottom 240 px
right 100 px
```

Exact safe areas may be refined after preview testing.

## Typography minimums

Recommended starting values:

```text
Hook:                  72 px
Title:                 60 px
Equation:              58 px
Primary labels:        42 px
Body text:             40 px
Captions:              46–56 px
Small labels:          minimum 34 px
```

---

# 14. Portrait visual adaptation

## 14.1 Inputs to the adapter

The adapter must receive:

* Final Short script.
* Final Short word timestamps.
* Source reel TSX.
* Source reel cues.
* Selected beat records.
* Source claim IDs.
* Portrait component API.
* Render profile.
* Instructions about reusable physics functions and diagrams.

## 14.2 Required behavior

The adapter should:

* Reuse physics calculations and analytic motion logic.
* Reuse diagram concepts.
* Reuse equation content.
* Reuse color identity.
* Reuse object names and educational relationships.
* Re-layout everything for portrait.
* Remove unrelated long-form content.
* Add a strong hook composition.
* Use the final Short audio cues.
* End exactly at the Short duration.
* Keep one continuous scene when possible.
* Avoid landscape scaling as the primary solution.

## 14.3 Forbidden shortcuts

Reject generated Short TSX that:

* Imports the parent Reel scene and scales the whole scene down.
* Uses a 1920×1080 container inside portrait as the main composition.
* Center-crops critical diagrams.
* Uses screenshot captures of the landscape video.
* Uses remote assets.
* Uses random timing.
* Invents claim text not found in the Short script.
* uses the parent timeline cues instead of Short-local cues.

## 14.4 Limited landscape reuse

Allow a landscape source to appear only as:

* A temporary inset.
* A background layer.
* A decorative framed window.
* A blurred visual reference.

It must not be the main teaching composition for the full Short.

---

# 15. Short Motion Canvas manifest

Create:

```text
shorts/<short-id>/motion_canvas/manifest.json
```

Example:

```json
{
  "version": "1.0",
  "content_type": "short",
  "short_id": "short_001",
  "parent_run_id": "physics-1-1-v01",
  "profile": {
    "id": "short_portrait",
    "width": 1080,
    "height": 1920,
    "fps": 30
  },
  "duration": 38.267,
  "render_frames": 1148,
  "audio_path": "../audio/voiceover.mp3",
  "scene_file": "short_001.tsx",
  "cues_file": "short_001.cues.ts",
  "source_provenance": "../source_provenance.json"
}
```

---

# 16. Captions

## 16.1 Caption generation

Use final Short word timestamps.

Create caption groups based on:

* Natural phrases.
* Punctuation.
* Maximum word count.
* Maximum display duration.
* Reading speed.

Suggested defaults:

```text
2–5 words per emphasized phrase
Maximum two lines
Maximum 22 characters per line when practical
Minimum display time 0.65 seconds
Maximum display time 2.2 seconds
```

## 16.2 Caption formats

Generate:

```text
captions.json
captions.srt
captions.ass
```

The JSON should support emphasis:

```json
{
  "start": 1.20,
  "end": 2.45,
  "words": [
    {"text": "weighs", "emphasis": false},
    {"text": "less", "emphasis": true},
    {"text": "on", "emphasis": false},
    {"text": "the Moon", "emphasis": true}
  ]
}
```

## 16.3 Burned-in captions

For the first implementation, captions should be rendered inside Motion Canvas.

Keep caption text inside the reserved caption region and ensure it does not cover equations, diagrams or labels.

---

# 17. Short pipeline stages

Use a separate Short stage system:

```text
1. Candidate selected
2. Script ready
3. Audio EDL ready
4. Audio assembled
5. Word timing ready
6. Portrait scene ready
7. Compile and validation passed
8. Preview approved
9. Rendered
```

Store status in:

```text
short_run.json
```

Example:

```json
{
  "short_id": "short_001",
  "parent_run_id": "physics-1-1-v01",
  "candidate_id": "candidate_001",
  "status": "preview_ready",
  "current_step": 7,
  "created_at": "ISO-8601",
  "updated_at": "ISO-8601",
  "error": null
}
```

---

# 18. CLI commands

Add a new CLI:

```text
template_lab/scripts/mav_shorts.py
```

Recommended commands:

```bash
# Analyze a completed parent run
python3 template_lab/scripts/mav_shorts.py analyze \
  --parent-run-id physics-1-1-v01 \
  --confirm-paid-api

# Create a Short from a candidate
python3 template_lab/scripts/mav_shorts.py create \
  --parent-run-id physics-1-1-v01 \
  --candidate-id candidate_001 \
  --short-id short_001 \
  --confirm-paid-api

# Resume from a particular Short stage
python3 template_lab/scripts/mav_shorts.py generate \
  --parent-run-id physics-1-1-v01 \
  --short-id short_001 \
  --from-step 3 \
  --stop-after-step 7 \
  --confirm-paid-api

# Preview
python3 template_lab/scripts/mav_shorts.py preview \
  --parent-run-id physics-1-1-v01 \
  --short-id short_001

# Render
python3 template_lab/scripts/mav_shorts.py render \
  --parent-run-id physics-1-1-v01 \
  --short-id short_001
```

## Paid API boundary

Require `--confirm-paid-api` for:

* Candidate model generation.
* Short script generation.
* New TTS lines.
* Portrait TSX generation.
* Model-based repair.

Do not require paid confirmation for:

* Audio extraction.
* Audio assembly.
* Local alignment.
* Validation.
* Preview.
* Rendering existing source.
* Caption generation.
* Source-hash validation.

---

# 19. Studio server API

Update:

```text
studio/server.py
```

Add read endpoints:

```text
GET /api/runs/<run-id>/shorts
GET /api/runs/<run-id>/shorts/candidates
GET /api/runs/<run-id>/shorts/<short-id>
GET /api/runs/<run-id>/shorts/<short-id>/logs
```

Add action endpoints:

```text
POST /api/runs/<run-id>/shorts/analyze
POST /api/runs/<run-id>/shorts
POST /api/runs/<run-id>/shorts/<short-id>/execute
POST /api/runs/<run-id>/shorts/<short-id>/preview
POST /api/runs/<run-id>/shorts/<short-id>/render
POST /api/runs/<run-id>/shorts/<short-id>/stop
POST /api/runs/<run-id>/shorts/<short-id>/models
POST /api/runs/<run-id>/shorts/<short-id>/regenerate-audio-line
POST /api/runs/<run-id>/shorts/<short-id>/regenerate-visual
DELETE /api/runs/<run-id>/shorts/<short-id>
```

Do not overload existing long-form execution endpoints.

Use separate process keys:

```python
_processes[f"{parent_run_id}:short:{short_id}"]
```

This prevents a Short process from being confused with the parent lesson process.

---

# 20. Studio UI

Update:

```text
studio/static/index.html
studio/static/app.js
studio/static/styles.css
```

The current UI already supports selecting reels and beats and opening synchronized previews. Reuse this interaction pattern for source selection and provenance display.

## 20.1 Add a Shorts tab

Inside each completed run, add:

```text
Lesson
Visual Reels
Shorts
Costs
Artifacts
```

## 20.2 Shorts landing state

Show:

```text
Generate Short ideas from this lesson
```

Button:

```text
Analyze for Shorts
```

## 20.3 Candidate cards

Each candidate card must show:

* Working title.
* Hook.
* Archetype.
* Target duration.
* Overall score.
* Audio reuse percentage.
* Source reels.
* Source beats.
* Warnings.
* “Create Short” button.

## 20.4 Short workspace

For each created Short, show:

### Script panel

* Editable hook.
* Full Short script.
* Source/generated badge per line.
* Claim IDs.
* Regenerate script button.

### Audio panel

* Source reuse percentage.
* Reused segments.
* Generated TTS lines.
* Play final audio.
* Regenerate individual generated line.
* Rebuild audio button.

### Visual panel

* Source reel references.
* Portrait preview.
* Regenerate portrait scene.
* Repair instruction field.
* Source provenance state.

### Caption panel

* Caption preview.
* Caption style controls.
* Enable/disable keyword emphasis.

### Render panel

* Preview.
* Render status.
* Final MP4 link.
* Add to render queue.

---

# 21. Render queue integration

Extend the existing render queue so entries can represent:

```json
{
  "type": "lesson",
  "run_id": "physics-1-1-v01"
}
```

or:

```json
{
  "type": "short",
  "run_id": "physics-1-1-v01",
  "short_id": "short_001"
}
```

The queue worker must select the correct render command based on `type`.

Do not create a second competing render queue.

Use the current resumable frame rendering behavior for Shorts as well.

Short frame caches must be isolated under:

```text
shorts/<short-id>/motion_canvas/frames/
```

---

# 22. Validation

## 22.1 Parent source validation

Before starting:

* Parent run exists.
* Parent timeline is immutable.
* Timeline hash is valid.
* Source audio hash matches.
* Source reel files exist.
* Parent validation passed.
* Selected beat IDs belong to selected reels.

## 22.2 Script validation

* All claim IDs are grounded.
* One core concept.
* Standalone wording.
* Valid duration.
* Hook present.
* Payoff present.
* Audio-source mappings are complete.

## 22.3 Audio validation

* All segments exist.
* WAV format is consistent.
* No negative ranges.
* No overlaps in source ranges.
* No cuts inside words.
* Final duration is positive.
* Final MP3 contains audio.
* Loudness and clipping checks pass.

## 22.4 Portrait TSX validation

* Uses portrait presentation components.
* Uses Short-local cues.
* Defines duration exactly once.
* Uses approved Motion Canvas API.
* No remote imports.
* No random behavior.
* No landscape root scaling.
* No critical coordinates outside safe area.
* Caption region does not overlap primary content.
* Minimum type sizes are respected.

## 22.5 Browser validation

Capture frames at:

```text
0%
10%
25%
50%
75%
90%
100%
```

Also capture:

* Hook frame.
* Densest frame.
* Equation reveal.
* Final payoff frame.

Create:

```text
motion_canvas/preview/contact-sheet.png
```

## 22.6 Final media validation

Check:

* Video stream exists.
* Audio stream exists.
* Resolution is 1080×1920.
* Duration matches manifest within one frame.
* FPS matches profile.
* Audio/video drift is within tolerance.
* MP4 uses fast-start metadata.

---

# 23. Resume and cache behavior

Each Short stage must be independently resumable.

Examples:

* Script exists: do not regenerate it unless forced.
* Source audio extracts exist and hashes match: reuse them.
* Generated hook WAV exists and cache key matches: reuse it.
* Final Short audio exists: skip audio generation.
* Word timing exists and matches audio hash: reuse it.
* Portrait TSX exists and validates: reuse it.
* Render frames exist and fingerprint matches: resume rendering.

Add Short-specific force flags:

```text
--force-script
--force-audio
--force-visual
--force-captions
--force-render
```

Avoid one broad destructive `--clean` action in the UI.

---

# 24. Testing plan

Create:

```text
template_lab/tests/test_shorts_candidates.py
template_lab/tests/test_shorts_script.py
template_lab/tests/test_shorts_audio.py
template_lab/tests/test_shorts_provenance.py
template_lab/tests/test_shorts_portrait.py
template_lab/tests/test_shorts_pipeline.py
studio/tests/test_shorts_api.py
```

## 24.1 Candidate tests

Test:

* Reject dependent chapter language.
* Maximum two source reels.
* Candidate scores remain within 0–100.
* Unknown claim IDs are rejected.
* Candidates are sorted by overall score.
* Empty source visuals produce a warning.

## 24.2 Audio tests

Test:

* Correct extraction from paragraph WAV.
* Word-boundary snapping.
* Fade insertion.
* Mixed reuse and generated segments.
* Cache reuse.
* Source hash mismatch detection.
* No source MP4 extraction.
* Final WAV duration.

## 24.3 Portrait tests

Test:

* Manifest profile selection.
* Landscape fallback for old runs.
* 1080×1920 stage creation.
* Rejection of full-scene scale-down.
* Short-local cue imports.
* Safe-area checks.
* Minimum text-size checks.

## 24.4 API tests

Test:

* Candidate list.
* Short creation.
* Duplicate Short ID rejection.
* Execute/resume.
* Preview.
* Render queue insertion.
* Short deletion without deleting parent.
* Paid-action confirmation.

## 24.5 Regression tests

Run existing:

```bash
python3 -m unittest discover -s template_lab/tests
```

Ensure:

* Existing landscape lessons compile.
* Existing landscape previews work.
* Existing lesson render queue works.
* Existing parent beat regeneration works.
* Old manifests without profiles default to 1920×1080.

---

# 25. Implementation phases

## Phase 1 — schemas and local scaffolding

Implement:

* `template_lab/shorts/`
* Directory creation.
* Short registry.
* Status handling.
* Provenance.
* Render profiles.
* Backward-compatible landscape profile.

No model calls yet.

### Acceptance criteria

* Existing lessons still render.
* A manual Short directory can be created.
* Short manifest can select 1080×1920.
* Renderer produces a blank portrait test scene.

---

## Phase 2 — candidate analyzer

Implement:

* Candidate model task.
* Candidate schema.
* Candidate validation.
* Candidate Studio cards.

### Acceptance criteria

* Completed lesson returns 3–5 candidates.
* Every candidate includes exact source reels and beats.
* Invalid claim IDs fail validation.
* Candidates are persisted and reload after Studio restart.

---

## Phase 3 — Short script and audio

Implement:

* Script compiler.
* Audio reuse matching.
* Audio EDL.
* TTS generation for missing lines.
* Final audio assembly.
* Local word alignment.

### Acceptance criteria

* One Short can mix reused and generated audio.
* Reused source audio is extracted from WAV.
* Regenerating one hook line does not regenerate other lines.
* Final aligned timestamps match the assembled audio.

---

## Phase 4 — portrait visual adapter

Implement:

* Portrait presentation library.
* Portrait adapter prompt.
* Short-local cues.
* TSX validation.
* Portrait browser preview.

### Acceptance criteria

* Adapter generates one 1080×1920 scene.
* It reuses source reel logic without scaling down the complete landscape scene.
* Hook, explanation and payoff are visually distinct.
* Captions do not overlap core diagrams.

---

## Phase 5 — Studio workflow

Implement:

* Shorts tab.
* Candidate selection.
* Short script/audio/visual panels.
* Preview controls.
* Render controls.
* Cost display.
* Source-stale warnings.

### Acceptance criteria

A user can:

1. Open a completed lesson.
2. Click Analyze for Shorts.
3. Select a candidate.
4. Generate the Short.
5. Listen to audio.
6. Preview portrait animation.
7. Regenerate one line or visual.
8. Render final MP4.

---

## Phase 6 — render queue and production hardening

Implement:

* Short render queue entries.
* Resumable Short frames.
* Final media inspection.
* Error recovery.
* Full tests.
* Documentation.

---

# 26. Initial MVP restrictions

For the first release:

* Maximum three generated Shorts per parent run at one time.
* Maximum two adjacent parent reels per Short.
* One Motion Canvas scene per Short.
* Duration between 20 and 60 seconds.
* English captions only.
* One portrait design theme.
* No automatic publishing.
* No performance analytics.
* No automatic background music.
* No multi-language dubbing.
* No automatic clipping from rendered MP4.

These restrictions should simplify the first production-quality implementation.

---

# 27. Non-goals

Do not:

* Replace the existing long-form pipeline.
* Change the parent immutable timeline.
* Regenerate the parent narration.
* Delete parent audio caches.
* Convert the parent lesson into portrait automatically.
* Add automatic YouTube or Instagram upload in this feature.
* Guarantee that a Short will become viral.
* Build a generic video editor.
* Add external stock media in the first version.

---

# 28. Failure-handling rules

Follow these principles:

1. Never modify the approved parent run.
2. Never delete reusable parent caches.
3. A failed Short must not change parent status.
4. A failed audio mux must preserve the rendered video stream.
5. A failed optional caption export must not delete the Short MP4.
6. A stale source hash must pause the Short instead of silently adapting to changed sources.
7. Paid calls require explicit confirmation.
8. Local validation should catch strict constraints before requesting model repair.
9. Retry only the failed Short stage.
10. Regenerating one Short must not affect other Shorts.

---

# 29. Documentation

Create:

```text
SHORTS_PIPELINE_README.md
```

Include:

* Architecture.
* CLI usage.
* Studio workflow.
* File structure.
* Model tasks.
* Paid API boundaries.
* Resume behavior.
* Source provenance.
* Portrait layout rules.
* Troubleshooting.
* Render queue behavior.

Update:

```text
MAV_STUDIO_CURRENT_HANDOFF.md
```

Add a new section describing the Shorts subsystem, but keep the long-form pipeline documentation unchanged.

---

# 30. Definition of done

The feature is complete when the following is demonstrated with one real parent lesson:

1. The parent lesson remains unchanged.
2. Candidate analysis produces at least three sensible standalone ideas.
3. One candidate is converted into a complete Short.
4. At least one source audio clause is reused.
5. At least one new hook or bridge line is generated.
6. Source reel code or physics logic is supplied to the portrait adapter.
7. The resulting visual is natively composed in 1080×1920.
8. Captions are synchronized to final Short audio.
9. TypeScript and browser validation pass.
10. Final output contains H.264 video and AAC audio.
11. Final duration matches the Short manifest within one frame.
12. The Short can be resumed after interruption.
13. Model and TTS usage appears in the cost ledger.
14. The Studio can preview and render the Short.
15. Existing long-form tests and rendering remain functional.

---

# 31. Recommended first production test

Use the mass-versus-weight lesson.

Create a Short with:

```text
Hook:
An astronaut weighs less on the Moon. Did she lose any matter?

Explanation:
Her mass remains constant because the amount of matter has not changed.

Payoff:
Weight is a force caused by gravity, so weight changes when gravitational field strength changes.

Equation:
W = mg
```

Reuse:

* Astronaut/Moon animation logic.
* Mass-versus-weight comparison.
* Any existing `W = mg` equation content.
* Suitable source narration clauses.

Generate:

* Standalone hook.
* Necessary bridge.
* Portrait layout.
* Captions.
* Final payoff or loop.

This test covers candidate planning, partial audio reuse, generated TTS, source visual adaptation, equations, portrait composition and final rendering.
