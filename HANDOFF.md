# Local IGCSE Physics Video Engine Handoff

Last updated: 14 July 2026

## Current state

The reusable parts of the former animation and Template Lab repositories are now inside this repository. Generated runs, screenshots, node modules, caches, secrets, finance selectors/harvesters, and unrelated production apps were deliberately not copied.

The local system contains:

- 35 registered deterministic physics animation scenes and eight example compositions;
- the eight-stage Template Lab script/audio/timing/V3/validation/preview/render pipeline;
- vendored V3 runtime CSS, JavaScript, GSAP, and editorial SVG assets;
- physics-specific script, teaching, originality, visual, and TTS instructions;
- a pinned HyperFrames renderer plus FFmpeg integration;
- a curriculum CLI for 58 topics, 328 objective IDs, coverage, next-topic selection, and grounded facts packets.

There are no code or configuration references to the two source-repository absolute paths. Source repositories were not modified.

## Start here

1. Read `END_TO_END_README.md` for installation and one-topic commands.
2. Run `python3 -m video_engine.cli doctor`.
3. Run `python3 -m video_engine.cli status` and `next-topic`.
4. Prepare a topic with `python3 -m video_engine.cli prepare-topic <ref>`.
5. Add trusted teaching facts before a paid generation when syllabus wording alone is insufficient.
6. Generate, preview, and render through `template_lab/scripts/`.
7. Mark coverage only after manual physics and visual review.

## Important boundaries

- Raw past-paper content remains private and must not be republished or fed verbatim into generation.
- API keys belong only in ignored `.env` files.
- Paid steps require the explicit `--confirm-paid-api` flag.
- `template_lab/runs/` and `video_engine/topics/` are generated working data and are ignored.
- Publication is manual; no uploader or daily scheduler is present.
- The engine controls objective status but cannot decide that a lesson is pedagogically correct. A human reviewer must approve physics, calculations, diagrams, pacing, and originality.

## Source of truth

```text
pilot/output/syllabus_topics.json                 source syllabus extraction
video_engine/curriculum/objectives.json           stable immutable objective records
video_engine/curriculum/coverage_registry.json    mutable progress state
video_engine/registry/animation_assets.json       local scene availability
physics_animation_engine/modules/_registry.js     animation runtime registry
template_lab/templates/physics/config.json        physics visual identity
template_lab/prompts/                              model instructions
```
