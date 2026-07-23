# Standalone Topic Reel Pack

This feature is additive. The existing long-form Motion Canvas lesson pipeline remains the default and is not replaced.

## Products

- **Full lesson:** existing `mav_generate.py --animation-mode motion-canvas` route, one master audio timeline, landscape 1920×1080 output.
- **Topic Reel pack:** new `mav_generate_reel_pack.py` route, twelve independent child productions, portrait 1080×1920 output.

The two products may use the same grounded topic facts and model configuration, but they have independent scripts, audio, timing, visual sources, review states, caches, and MP4 files.

## Generate a pack

```bash
python3 template_lab/scripts/mav_generate_reel_pack.py \
  --run-id physics-1-5-3-reels-v01 \
  --topic "Centre of gravity" \
  --topic-ref 1.5.3 \
  --reel-count 12 \
  --duration 45 \
  --from-step 1 \
  --stop-after-step 7 \
  --use-model \
  --confirm-paid-api
```

The default facts source is the same repository-local facts input used by lesson generation. Pass `--facts <path>` to override it.

## Stages

1. Create the additive Reel-pack manifest.
2. Plan twelve distinct standalone briefs and write scripts in batches of four.
3. Generate an independent audio file for every Reel.
4. Derive independent word timestamps and cue data.
5. Generate one portrait Motion Canvas source per Reel.
6. Compile and render an independent portrait preview for each Reel.
7. Capture one to three dense stable frames per Reel, send all contact sheets in one multimodal screening call, and optionally repair only flagged Reels once.
8. Render approved Reels as separate portrait MP4 files.

## Target one Reel

```bash
python3 template_lab/scripts/mav_generate_reel_pack.py \
  --run-id physics-1-5-3-reels-v01 \
  --reel-id reel_004 \
  --from-step 5 \
  --stop-after-step 6 \
  --use-model \
  --confirm-paid-api \
  --force
```

Targeting one child does not rewrite the other eleven child directories.

## Review policy

The pack-level screening:

- makes one multimodal call;
- accepts zero findings;
- accepts at most five critical or major findings;
- rejects findings below 0.85 confidence;
- does not send complete TSX source to the reviewer;
- sends only flagged Reels through one targeted visual-repair call;
- does not automatically screen the pack a second time.

A repaired Reel is marked `repaired_pending_review` and must be manually approved before the default render stage includes it.

## Output

```text
template_lab/runs/<pack-run-id>/
├── input.json
├── reel_pack.json
├── pack_plan.json
├── pack-review.json
├── publishing_manifest.json
├── review/
└── reels/
    ├── reel_001/
    │   ├── brief.json
    │   ├── script.json
    │   ├── narration.json
    │   ├── voiceover.mp3
    │   ├── audio_word_timestamps.json
    │   └── motion_canvas/
    │       ├── reels/reel_001.tsx
    │       ├── preview/contact-sheet.png
    │       └── final.mp4
    └── ...
```

The internal Motion Canvas scene ID is local to each child. The parent `reel_001`–`reel_012` identity is stored in every child manifest and used on evidence sheets and publishing output.

## Long-form regression contract

The Reel-pack route does not call or alter long-form script generation, master audio assembly, immutable lesson timeline creation, lesson screening, or landscape rendering. Existing commands remain:

```bash
python3 template_lab/scripts/mav_generate.py \
  --run-id <lesson-run-id> \
  --animation-mode motion-canvas
```

The Motion Canvas render host now reads optional canvas dimensions from the Reel-pack environment. Without those environment variables it remains 1920×1080 and follows the existing long-form behaviour.
