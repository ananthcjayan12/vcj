# Topic-by-Topic IGCSE Physics Video Engine Plan

## 1. Exact goal

Build a reusable engine that is run manually for one syllabus topic at a time.

For each topic, the engine must:

1. read the exact Core and Supplement objectives;
2. check what has already been produced;
3. design the minimum set of videos needed for complete coverage;
4. retrieve private past-question patterns without copying questions;
5. create original scripts, examples, diagrams, and questions;
6. use existing physics animation modules or identify missing reusable modules;
7. generate voice, timing, animations, preview, captions, and final MP4 files;
8. run physics, duplication, visual, and technical QA;
9. export a complete publishing package;
10. stop before uploading so publication remains manual.

There is no daily scheduler and no automatic platform publishing.

The working model is:

```text
Choose next topic manually
        ↓
Plan complete topic package
        ↓
Build any missing reusable animations
        ↓
Generate one video at a time
        ↓
Preview and repair
        ↓
Render final package
        ↓
Mark objectives as covered
        ↓
Move to the next topic
```

---

## 2. Sources already available

| Source | Engine use |
|---|---|
| `pilot/output/syllabus_topics.json` | Source of truth for 58 topics and 328 objectives |
| `pilot/index_output/question_index.sqlite3` | Private question-pattern and misconception research |
| MAV 35-scene animation engine | Reusable, deterministic physics animations |
| Template Lab V3 pipeline | Script artifacts, TTS, Whisper timing, scene generation, browser preview, QA, HyperFrames, FFmpeg |

The new engine is an adapter and curriculum-control layer around these systems. It should not duplicate the existing rendering implementation.

---

## 3. Main engine architecture

```text
CURRICULUM REGISTRY
  58 topics / 328 objectives / Core-Supplement / prerequisites
                    │
                    ▼
TOPIC PLANNER ───── COVERAGE + DUPLICATION CHECKER
                    │
                    ▼
QUESTION-ARCHETYPE RETRIEVER
                    │
                    ▼
LESSON + ORIGINAL-QUESTION GENERATOR
                    │
                    ▼
PHYSICS / MATH / ORIGINALITY VERIFIER
                    │
                    ▼
MAV + V3 ANIMATION ROUTER
                    │
                    ▼
TEMPLATE LAB AUDIO / TIMING / BUILD / RENDER
                    │
                    ▼
VISUAL + TECHNICAL QA AND TARGETED REPAIR
                    │
                    ▼
LOCAL PUBLISHING PACKAGE
```

---

## 4. Repository structure

Add the following package:

```text
video_engine/
  config/
    engine.yaml
    model_providers.yaml
    brand.yaml
    qa_thresholds.yaml
  curriculum/
    objectives.json
    topic_order.json
    prerequisites.json
    coverage_registry.json
  registry/
    videos.json
    original_questions.json
    animation_assets.json
    content_fingerprints.json
  schemas/
    topic_plan.schema.json
    video_brief.schema.json
    verified_script.schema.json
    scene_plan.schema.json
    qa_report.schema.json
    publishing_package.schema.json
  prompts/
    topic_planner.system.txt
    video_writer.system.txt
    physics_critic.system.txt
    scene_director.system.txt
    metadata_writer.system.txt
  services/
    curriculum_importer.py
    topic_planner.py
    coverage_checker.py
    duplicate_checker.py
    question_retriever.py
    original_question_generator.py
    physics_verifier.py
    script_generator.py
    asset_router.py
    template_lab_adapter.py
    visual_qa.py
    final_video_qa.py
    publishing_package.py
  cli.py
  topics/
    1.1/
    1.2/
    ...
  output/
    publish_packages/
```

---

## 5. Curriculum registry

Convert the syllabus JSON into stable objective IDs:

```text
1.1-C01   Core objective 1 of topic 1.1
1.1-S04   Supplement objective 4 of topic 1.1
1.2-C01   Core objective 1 of topic 1.2
```

Each objective record contains:

```json
{
  "objective_id": "1.2-C04",
  "topic_ref": "1.2",
  "topic_title": "Motion",
  "route": "core",
  "objective_text": "...",
  "prerequisites": ["1.2-C01", "1.2-C02"],
  "primary_video_id": null,
  "reinforcement_video_ids": [],
  "status": "uncovered"
}
```

Valid objective states:

```text
uncovered
planned
scripted
rendered
reviewed
covered
needs_revision
```

This registry is what guarantees complete syllabus coverage.

---

## 6. Fixed topic order

Build topics in prerequisite order and complete one topic package before moving to the next.

### Stage 1 — Mechanics foundations

```text
1.1    Physical quantities and measurement techniques
1.2    Motion
1.3    Mass and weight
1.4    Density
1.5.1  Effects of forces
1.5.2  Turning effect of forces
1.5.3  Centre of gravity
1.6    Momentum
1.7.1  Energy
1.7.2  Work
1.7.4  Power
1.7.3  Energy resources
1.8    Pressure
```

### Stage 2 — Thermal physics

```text
2.1.1  States of matter
2.1.2  Particle model
2.1.3  Gases and the absolute scale of temperature
2.2.1  Thermal expansion
2.2.2  Specific heat capacity
2.2.3  Melting, boiling and evaporation
2.3.1  Conduction
2.3.2  Convection
2.3.3  Radiation
2.3.4  Consequences of thermal energy transfer
```

### Stage 3 — Waves

```text
3.1    General properties of waves
3.4    Sound
3.2.1  Reflection of light
3.2.2  Refraction of light
3.2.3  Thin lenses
3.2.4  Dispersion of light
3.3    Electromagnetic spectrum
```

### Stage 4 — Electricity and magnetism

```text
4.2.1  Electric charge
4.2.2  Electric current
4.2.3  Electromotive force and potential difference
4.2.4  Resistance
4.3.1  Circuit diagrams and circuit components
4.3.2  Series and parallel circuits
4.3.3  Action and use of circuit components
4.2.5  Electrical energy and electrical power
4.4    Electrical safety
4.1    Simple phenomena of magnetism
4.5.3  Magnetic effect of a current
4.5.4  Force on a current-carrying conductor
4.5.5  The d.c. motor
4.5.1  Electromagnetic induction
4.5.2  The a.c. generator
4.5.6  The transformer
```

### Stage 5 — Nuclear physics

```text
5.1.1  The atom
5.1.2  The nucleus
5.2.1  Detection of radioactivity
5.2.2  The three types of nuclear emission
5.2.3  Radioactive decay
5.2.4  Half-life
5.2.5  Safety precautions
```

### Stage 6 — Space physics

```text
6.1.1  The Earth
6.1.2  The Solar System
6.2.1  The Sun as a star
6.2.2  Stars
6.2.3  The Universe
```

`topic_order.json` controls this order, so it can be changed without changing engine code.

---

## 7. Definition of a complete topic package

The engine must not assume one topic equals one video. It first groups objectives into the smallest sensible set of videos.

A complete topic package can contain:

```text
1–3 concept videos
0–2 Extended-only videos
1 original worked-question video when calculations are required
1 practical/graph video when the syllabus requires experimental or graph skills
1 topic summary/retrieval asset
optional 9:16 derivatives from the finished videos
```

Only generate formats that the objectives require.

Example for topic `1.2 Motion`:

```text
V1  Speed, velocity, and average speed
V2  Distance-time and speed-time graphs
V3  Acceleration, free fall, and terminal velocity
V4  Original motion-graph worked problem
V5  Extended acceleration calculations, if kept separate
```

Example for topic `1.3 Mass and weight`:

```text
V1  Mass, weight, and gravitational field strength
V2  Original calculation and misconception video
```

The topic is complete only when every objective has one approved primary video and the topic-level QA report has no gap.

---

## 8. Topic planning workflow

Manual command:

```bash
python3 -m video_engine.cli plan-topic 1.1
```

The planner must:

1. load every Core and Supplement objective for the topic;
2. load prerequisites and already covered objectives;
3. load existing video, script, question, and animation registries;
4. retrieve representative private question archetypes;
5. group objectives into coherent videos;
6. assign route: Core, Both, or Extended;
7. define the original questions required;
8. select existing animation modules;
9. report missing reusable animation assets;
10. run coverage and duplication checks;
11. write `topic_plan.json`.

Example output:

```text
video_engine/topics/1.1/topic_plan.json
video_engine/topics/1.1/coverage_map.json
video_engine/topics/1.1/asset_gap_report.json
video_engine/topics/1.1/question_archetypes.json
video_engine/topics/1.1/plan_qa.json
```

Do not generate paid scripts, audio, or scenes until the topic plan passes.

---

## 9. Preventing repeated content

The engine needs both objective-level and semantic duplication protection.

### 9.1 Objective duplication

Before adding a proposed video, check:

- which objectives it teaches as primary objectives;
- which existing videos already teach those objectives;
- whether the new video adds a distinct assessment format or misconception;
- whether it should be reinforcement instead of a new concept video.

Reject a new concept video when all its primary objectives are already covered and it adds no approved new purpose.

### 9.2 Semantic duplication

Store for every finished video:

- title embedding;
- learning-outcome embedding;
- full-script embedding;
- question-archetype IDs;
- original-question fingerprint;
- scene sequence fingerprint;
- thumbnail concept;
- key misconception tags.

Compare each proposed video against the registry:

```text
title similarity
learning-outcome similarity
script similarity
question similarity
scene-order similarity
same hook + same misconception combination
```

If similarity exceeds the configured threshold, the planner must either:

- merge the videos;
- change the learning purpose;
- classify the new item as deliberate reinforcement;
- or reject it.

### 9.3 Original-question duplication

Compare every generated public question against:

- all prior public original questions;
- the private past-question index;
- diagrams using perceptual hashes;
- number/context patterns;
- long matching word sequences.

The public question must use original wording, context, values, and diagrams.

---

## 10. Animation asset workflow

Before generating a topic, run:

```bash
python3 -m video_engine.cli audit-assets 1.1
```

The asset router maps each required scientific representation to:

```text
existing MAV module
combination of existing MAV modules
new reusable MAV module required
custom V3 context scene
```

Use deterministic MAV modules for:

- equations and calculations;
- graphs;
- force/vector diagrams;
- energy and Sankey diagrams;
- particle models;
- waves and rays;
- circuits;
- magnetic fields and machines;
- nuclear processes;
- orbital and stellar models.

Use V3 custom HTML/CSS/GSAP for:

- hooks;
- real-world context scenes;
- transitions;
- comparisons;
- unique laboratory setups;
- recap visuals.

If a scientific visual will be reused in later topics, build it as a new MAV module before generating the topic videos.

Each new module needs:

```text
parameter schema
scientific invariants
example composition
first/middle/final frame tests
phone-legibility test
backward-seeking test
registry entry
```

This is how the animation library grows topic by topic without producing inconsistent one-off visuals.

---

## 11. Video generation workflow

Generate one planned video at a time:

```bash
python3 -m video_engine.cli generate-video P0625-1.1-01
```

Stages:

```text
1. load approved video brief
2. retrieve approved archetype summary
3. create original question and solution
4. verify physics, calculations, units, route, and originality
5. generate structured narration and on-screen copy
6. run script critics and targeted repairs
7. generate TTS paragraph chunks
8. derive paragraph and word timings with Whisper
9. route scenes to MAV or V3
10. generate scenes concurrently where possible
11. validate and repair scene plans
12. build isolated scenes and master browser preview
13. run screenshot/OCR/vision QA
14. repair only failed scenes
15. render with HyperFrames and FFmpeg
16. run final video QA
17. build local publishing package
```

The generation command must resume from the last successful artifact after interruption.

Optional controls:

```bash
python3 -m video_engine.cli generate-video P0625-1.1-01 --from-step script
python3 -m video_engine.cli generate-video P0625-1.1-01 --from-step scenes
python3 -m video_engine.cli generate-video P0625-1.1-01 --scene scene_04
python3 -m video_engine.cli generate-video P0625-1.1-01 --render-only
```

---

## 12. Structured video brief

Every video begins with an immutable approved brief:

```json
{
  "video_id": "P0625-1.2-02",
  "topic_ref": "1.2",
  "title_working": "Distance-Time and Speed-Time Graphs",
  "route": "both",
  "primary_objectives": ["1.2-C04", "1.2-C05", "1.2-C06", "1.2-C07"],
  "reinforcement_objectives": ["1.2-C01", "1.2-C03"],
  "learning_outcome": "Interpret motion graphs and calculate speed or distance.",
  "prerequisites": ["P0625-1.2-01"],
  "misconceptions": [
    "Graph height always means speed",
    "A falling speed-time line means the object moves backwards"
  ],
  "question_archetypes": [
    "distance_time_gradient",
    "speed_time_area"
  ],
  "required_visuals": [
    "motion_graph",
    "gradient_triangle",
    "area_under_graph"
  ],
  "asset_plan": [
    "Scene_GraphPlotter",
    "Scene_NumericalExample"
  ],
  "target_duration_seconds": 540
}
```

Scripts, scenes, metadata, and QA are generated from this brief. They must not silently change its objective scope.

---

## 13. Physics and content verification

### Deterministic checks

- equations parse correctly;
- numerical answers independently recalculate with SymPy;
- units and dimensions pass Pint checks;
- graph gradients and areas match source coordinates;
- significant figures and conversions are correct;
- conservation totals are consistent;
- every variable is defined;
- Core/Supplement classification matches the syllabus;
- every promised objective is explicitly present in the script;
- no unplanned objective creates unnecessary repetition.

### Model critics

Use two separate structured critics:

```text
Physics critic   correctness, causal reasoning, ambiguity, syllabus scope
Learning critic  clarity, missing steps, pacing, misconception handling
```

Critic results contain artifact location, severity, rule, and repair instruction. Critical errors block audio and animation generation.

---

## 14. Automated visual QA

For every scene, capture frames at:

```text
start
25%
50%
75%
end
```

Run:

- browser console/error checks;
- safe-area and overflow checks;
- text collision checks;
- minimum-font and contrast checks;
- OCR comparison with approved copy/equations;
- blank/frozen scene detection;
- deterministic seeking checks;
- vision-model review using the scene’s scientific invariants.

The vision check must inspect:

- circuit connectivity;
- graph axes, scales, and curves;
- vector direction and magnitude relationship;
- ray direction and geometry;
- field direction;
- particle arrangement and motion;
- label accuracy;
- equation accuracy;
- whether the visual state matches the narration time.

Repair only the failed scene. Do not regenerate the complete video.

---

## 15. Final render and package

Final master:

```text
1920×1080
30 fps
H.264
yuv420p
AAC audio
+faststart
```

Final video QA checks:

- expected resolution, frame rate, codec, and duration;
- video and audio streams present;
- no black or missing frames;
- no unintended long freeze;
- no clipping or unexpected silence;
- narration matches approved script;
- captions match narration;
- sampled frames pass OCR and visual checks;
- all critical findings equal zero.

Export locally:

```text
video_engine/output/publish_packages/P0625-1.2-02/
  master.mp4
  captions.srt
  transcript.txt
  thumbnail_01.png
  thumbnail_02.png
  thumbnail_03.png
  title_options.txt
  description.md
  chapters.txt
  syllabus_coverage.json
  qa_report.json
  generation_manifest.json
  shorts/
    short_01.mp4
    short_02.mp4
```

The engine stops here. The user previews the files and uploads manually.

---

## 16. Manual CLI workflow

### One-time setup

```bash
python3 -m video_engine.cli init
python3 -m video_engine.cli import-syllabus pilot/output/syllabus_topics.json
python3 -m video_engine.cli import-animation-registry /path/to/animations
```

### See curriculum progress

```bash
python3 -m video_engine.cli status
python3 -m video_engine.cli next-topic
python3 -m video_engine.cli status --topic 1.1
```

### Plan a topic

```bash
python3 -m video_engine.cli plan-topic 1.1
python3 -m video_engine.cli check-topic-plan 1.1
python3 -m video_engine.cli audit-assets 1.1
```

### Generate a video

```bash
python3 -m video_engine.cli generate-video P0625-1.1-01
python3 -m video_engine.cli preview-video P0625-1.1-01
python3 -m video_engine.cli render-video P0625-1.1-01
```

### Finalise coverage

```bash
python3 -m video_engine.cli approve-video P0625-1.1-01
python3 -m video_engine.cli check-topic-coverage 1.1
python3 -m video_engine.cli complete-topic 1.1
python3 -m video_engine.cli next-topic
```

`approve-video` and `complete-topic` are local registry operations. They do not publish anything online.

---

## 17. Topic and video states

Topic states:

```text
not_started
planning
asset_building
ready_to_generate
generating
reviewing
complete
needs_revision
```

Video states:

```text
planned
brief_verified
script_verified
audio_ready
scenes_ready
preview_ready
rendered
qa_passed
approved
packaged
```

The next topic cannot be marked active until the current topic is complete, unless an explicit override is used.

---

## 18. Build the engine in this order

### Phase 1 — Curriculum control

Build:

- syllabus importer;
- stable objective IDs;
- fixed topic order;
- prerequisite registry;
- topic/video/objective state tracking;
- `status`, `next-topic`, and coverage-check commands.

Result: the engine knows exactly what exists, what is missing, and what comes next.

### Phase 2 — Planning and non-repetition

Build:

- topic planner;
- objective grouping;
- private question retriever;
- archetype summariser;
- video/question/script fingerprint registry;
- duplicate checker;
- coverage-gap report.

Result: the engine creates a complete, non-repeating topic plan before generating content.

### Phase 3 — Connect the existing production pipeline

Build:

- physics input adapter for Template Lab;
- structured script schema;
- original-question generator;
- physics/math verifier;
- TTS and Whisper adapter;
- resumable step runner.

Result: one approved video brief becomes verified narration and timed audio.

### Phase 4 — Animation routing and quality

Build:

- animation asset registry;
- MAV parameter generator;
- MAV/V3 router;
- V3 scene generation adapter;
- isolated scene preview;
- OCR/layout/vision QA;
- targeted scene repair.

Result: scripts become reliable high-quality animated previews.

### Phase 5 — Render and export

Build:

- HyperFrames/FFmpeg wrapper;
- final MP4 validation;
- caption/transcript export;
- thumbnail templates;
- optional native vertical derivatives;
- publishing package builder.

Result: a local folder is ready for manual review and upload.

### Phase 6 — First two complete topics

Build topics in order:

```text
1.1 Physical quantities and measurement techniques
1.2 Motion
```

Topic 1.1 tests measurement, scalar/vector, original practical questions, and new apparatus assets. Topic 1.2 tests graphs, calculations, motion animation, misconception control, and multi-video coverage.

Do not continue to topic 1.3 until the engine can reproduce both topic packages from cached artifacts and all duplication/coverage reports pass.

---

## 19. Definition of engine completion

The engine is ready for full syllabus production when:

```text
the next topic is selected from a fixed curriculum order
all Core and Supplement objectives have stable IDs
a topic plan covers every objective without unnecessary repeated videos
past questions are used only as private archetype research
public questions and diagrams are original
existing scripts, questions, and videos are checked for duplication
missing reusable animation modules are identified before generation
each approved brief becomes a timed animated preview
physics, maths, layout, visuals, audio, and MP4 pass QA
failed scenes can be regenerated independently
runs resume from cached steps
the final local folder contains everything needed for manual upload
the coverage registry updates only after explicit local approval
```

---

## 20. Immediate implementation target

The first implementation slice should be:

```text
1. import all 328 objectives
2. create topic order and coverage registry
3. implement status/next-topic commands
4. generate the complete plan for topic 1.1
5. audit animation gaps for topic 1.1
6. adapt Template Lab to generate the first topic 1.1 video
7. render and export its local publishing package
8. mark its objectives covered
9. continue until topic 1.1 has no coverage gaps
10. repeat for topic 1.2 and validate non-repetition
```

After these two topics, the same engine can proceed through the remaining 56 topics in the defined order.
