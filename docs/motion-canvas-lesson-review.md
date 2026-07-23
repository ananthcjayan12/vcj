# Motion Canvas lesson-level visual review

This feature replaces autonomous per-reel review loops with one lesson-level multimodal screening call.

## Workflow

1. The original reel-generation call receives grounded facts, exact cues, and a generic scientific/visual self-audit.
2. Every generated TSX includes a `MAV_VISUAL_CONTRACT` comment describing observable direction, trajectory, attachment, state, cue events, and one to three review checkpoints.
3. Compile & QA renders one to three dense, stable completed-state frames per reel.
4. The renderer produces multiple readable contact sheets and sends all of them to Gemini in one request.
5. Gemini may return zero to five high-confidence critical/major findings. It is explicitly told not to fill the quota or suggest optional polish.
6. Only flagged reels are sent back through the existing targeted reel generator, once per reel.
7. Reel duration, cue keys, cue order, cue-to-visual mapping, and audio windows remain immutable.
8. Corrected reel checkpoints are rendered for Studio review. There is no automatic second multimodal screening call.

## Frame selection

Candidate frames come from generator-declared review checkpoints and narration-beat endpoints. The local renderer samples those candidate states and ranks them using:

- visual density, so the important objects are present;
- stability between nearby frames, so entrance animation has settled;
- a semantic bonus for generator-declared checkpoints.

This scoring is used only to select screenshots. It does not judge or rewrite the scene.

Each reel contributes one to three frames. Panels are labelled with reel ID, chapter number, frame ID, local timestamp, cue, and purpose.

## Screening limits

- One Gemini request per unchanged lesson.
- Zero to five findings total.
- Minimum accepted confidence: `0.85` by default.
- Only `critical` and `major` findings are accepted locally.
- One targeted regeneration per flagged reel.
- No full TSX is sent to Gemini during screening.
- Gemini diagnoses; the configured Motion Canvas reel generator owns code changes.

## Environment controls

```bash
MAV_MOTION_CANVAS_LESSON_REVIEW=0
MAV_MOTION_CANVAS_AUTO_REPAIR_FINDINGS=0
MAV_MOTION_CANVAS_SCREEN_MAX_FINDINGS=5
MAV_MOTION_CANVAS_SCREEN_MIN_CONFIDENCE=0.85
```

`MAV_MOTION_CANVAS_AUTO_REPAIR_FINDINGS=0` keeps the one-call diagnosis but does not regenerate source.

## Artifacts

```text
motion_canvas/lesson-review.json
motion_canvas/lesson-review/screening-context.json
motion_canvas/lesson-review/screening-response.txt
motion_canvas/lesson-review/evidence/evidence.json
motion_canvas/lesson-review/evidence/contact-sheet-*.png
motion_canvas/lesson-review/corrected-evidence/contact-sheet-*.png
```

## Manual command

```bash
python3 template_lab/scripts/mav_lesson_review.py \
  --run-id physics-1-5-3-v01
```

Diagnosis only:

```bash
python3 template_lab/scripts/mav_lesson_review.py \
  --run-id physics-1-5-3-v01 \
  --screen-only
```

## Audio synchronisation

The targeted generator is instructed to preserve:

- `CHAPTER_DURATION`;
- absolute audio boundaries;
- cue keys and occurrences;
- cue order;
- the visual event associated with each cue.

The existing immutable timeline, duration enforcement, cue-reference validation, compile check, and browser-frame validation continue to run. The review feature adds no automatic timing rewrite.
