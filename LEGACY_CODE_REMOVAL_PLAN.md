# Legacy code removal plan

## Goal

Make the narration-driven Motion Canvas path the only production video route while preserving curriculum preparation, grounded facts, narration, voice generation, word alignment, cost accounting, Studio run management, and final QA evidence.

This document is a removal plan only. No legacy production source is deleted in this change.

## Keep

- `video_engine/` curriculum, objective, facts, coverage, and run orchestration responsibilities.
- `template_lab/scripts/mav_inputs.py`, `mav_script.py`, `mav_audio.py`, `mav_timing.py`, `mav_models.py`, `mav_costs.py`, and shared schema utilities.
- `template_lab/motion_canvas/` generation, assembly, and validation pipeline.
- `motion_canvas_runtime/` fixed renderer.
- Studio dashboard, topic/run management, logs, model selection, validation evidence, and render controls.
- Tests and fixtures that cover retained responsibilities.

## Remove after migration

1. Legacy recipe/V3 generation:
   - `physics_animation_engine/modules/`
   - legacy registry and recipe specifications used only by `legacy-recipes`
   - `mav_plan_v3.py`, `mav_recipes.py`, `mav_validate_v3.py`, `mav_build_preview_v3.py`
   - V3 prompts and scene coder/parameterizer tasks after confirming they have no Motion Canvas consumer
2. Direct HTML production:
   - `template_lab/direct_html/`
   - `physics_animation_engine/direct_html/`
   - Direct HTML composer, repair, reviewer prompts and model-map tasks
   - HTML browser inspection and HyperFrames rendering adapters
3. Legacy preview/render dependencies:
   - GSAP composition runtime and old template project assets used only by HTML/V3
   - HyperFrames package and scripts once Motion Canvas rendering is the sole path
4. Obsolete UI controls, API branches, documentation, tests, and fixtures tied exclusively to removed modes.

## Migration phases

### Phase 1 — Prove Motion Canvas acceptance

- Complete at least two representative topic runs: one analytic-motion/graph lesson and one static/equation/measurement lesson.
- Confirm cached resume, provider truncation rejection, compile/build, deterministic frame seeking, contact sheets, MP4 render, narration sync, and cost records.
- Record known failure recovery procedures.

Exit gate: both lessons pass technical and human physics review without using Direct HTML or legacy fallback.

### Phase 2 — Make Motion Canvas the default

- Change CLI, Studio, and stored-run defaults to `motion-canvas`.
- Remove legacy/direct modes from new-run UI choices.
- Reject creation of new legacy runs while retaining read-only visibility for historical runs.
- Change model-map UI to show only narration, audio, and Motion Canvas tasks.

Exit gate: all newly created runs use Motion Canvas and render successfully through the standard Studio button.

### Phase 3 — Separate retained shared code

- Remove legacy constants from shared modules.
- Replace mode-based conditionals with one linear pipeline.
- Move retained generic utilities out of directories scheduled for deletion.
- Update `generation_summary.json` and Studio run-detail inference to use Motion Canvas artifacts exclusively.
- Add migration handling for historical metadata without executing historical renderers.

Exit gate: dependency/search audit shows retained production code has no imports from Direct HTML, V3, recipe, GSAP, or HyperFrames packages.

### Phase 4 — Delete legacy implementations

- Delete source groups listed under “Remove after migration” in small, reviewable commits.
- Delete their tests only after equivalent retained behavior is covered by Motion Canvas/shared tests.
- Remove obsolete npm dependencies and regenerate lockfiles.
- Remove environment variables and `.env.example` entries that no retained task reads.
- Remove old documentation or replace it with a short historical migration note.

Exit gate: fresh dependency installation, complete tests, one fixture acceptance run, and Studio startup all pass.

### Phase 5 — Repository and historical-run cleanup

- Archive historical legacy outputs outside the repository if they must be retained.
- Remove ignored local legacy render artifacts.
- Run dead-code and file-reference searches.
- Update the top-level README and architecture diagrams to describe only Motion Canvas.

Exit gate: no production command, UI control, model task, package dependency, or documentation instructs users to invoke a removed renderer.

## Safety rules for implementation

- Do not delete upstream narration/audio/timing code merely because legacy modules import it.
- Do not delete historical run data until its retention requirement is explicitly decided.
- Do not combine default switching and mass deletion in one commit.
- Use one removal commit per subsystem so regressions can be isolated.
- Run tests and a cached Motion Canvas fixture after every phase.
- Search for imports, CLI strings, environment variables, API routes, and UI mode values before deleting any file.

## Final verification commands

```bash
rg -n "legacy-recipes|direct-html|v3_generative|HyperFrames|GSAP" \
  studio template_lab video_engine README.md
python3 -m unittest discover -s template_lab/tests
python3 -m unittest discover -s studio/tests
npm --prefix motion_canvas_runtime ci
npm --prefix motion_canvas_runtime run check
```

The first search should return only intentional historical migration notes. Finish with one cached end-to-end Motion Canvas topic render.
