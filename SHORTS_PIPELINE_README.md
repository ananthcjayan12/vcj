# Shorts Derivative Pipeline

The Shorts pipeline creates independent portrait child runs beneath an approved Motion Canvas lesson. It never writes into the parent `motion_canvas/reels` directory and validates the immutable parent before analysis.

## Commands

```bash
python3 template_lab/scripts/mav_shorts.py analyze --parent-run-id RUN --confirm-paid-api
python3 template_lab/scripts/mav_shorts.py create --parent-run-id RUN --candidate-id candidate_001 --short-id short_001 --confirm-paid-api
python3 template_lab/scripts/mav_shorts.py preview --parent-run-id RUN --short-id short_001
python3 template_lab/scripts/mav_shorts.py render --parent-run-id RUN --short-id short_001
```

Candidate analysis and creation invoke their registered structured-output models and require explicit paid-API confirmation. Generation calls the configured TTS provider only for generated lines and the portrait adapter only for the child scene. Local extraction, assembly, alignment, captions, validation, preview, and rendering do not require confirmation by themselves.

## Artifacts and resume safety

Artifacts live at `template_lab/runs/<parent>/shorts/<short>/`. Scripts, the audio EDL, generated lines, extracted source clauses, captions, portrait source, frames, reports, costs, and provenance are isolated per Short. Provenance hashes the parent timeline, voiceover, selected reel TSX, and reused paragraph WAVs. A mismatch must be treated as `source_stale`; the parent is never rewritten.

The renderer reads a manifest profile. Old manifests without a profile remain `lesson_landscape` (1920×1080); Short manifests use `short_portrait` (1080×1920). Frame checkpoints remain within the Short directory.

## Studio API

The Studio exposes `/api/runs/<run>/shorts`, `/candidates`, and child detail/log resources plus separate analyze, create, execute, preview, render, stop, model, regeneration, and delete actions. Paid actions require `confirm_paid_api`. Short processes use `<parent>:short:<short>` keys.

The Derivative portrait productions panel has its own saved model map for candidate analysis, script writing, portrait adaptation, and repair. Provider choices include configured Gemini, Anthropic, Moonshot/Kimi, Z.AI, and Codex models. Analysis and per-Short logs are displayed in the panel, and Short-task token usage plus estimated cost is filtered from the parent run ledger.

## Portrait rules

Use `motion_canvas_runtime/src/short-presentation.tsx`, Short-local cues, minimum 34 px labels, and the reserved caption band. Full landscape scale-down, center-cropped lesson scenes, remote assets, random timing, and parent cues are rejected.

## Troubleshooting

- “Parent run is not Short-ready”: complete Motion Canvas generation and validation first.
- “source_stale”: regenerate the child from the now-current approved parent; do not overwrite provenance.
- Missing generated line: resume from step 4; only the missing independently cached line is synthesized.
- Interrupted render: rerun `render`; the existing fingerprinted frame checkpoint is reused.
