# Native Reel Pipeline Implementation Plan

## Current architecture findings

- Studio currently creates only Motion Canvas lesson runs and treats narration/audio timing as authoritative.
- `mav_audio.generate_audio()` already provides paragraph-level TTS caching, WAV/MP3 assembly, Gemini and ElevenLabs support.
- `mav_timing.derive_timing()` already produces local word timestamps and protects them with the voiceover SHA-256.
- `template_lab.motion_canvas.pipeline` already validates immutable timelines and supports legacy `immutable_shots`, but its active preparation path creates long-form `immutable_reels` and uses landscape prompts/components.
- The Motion Canvas runtime, Puppeteer viewport, preview sheet geometry, and render fingerprint are coupled to 1920×1080.
- Studio has reusable run metadata, background-process, model-map, preview, render, and targeted-unit regeneration machinery.
- Codex CLI is a provider adapter. The official xAI Grok Build CLI exposes equivalent headless operation (`grok -p`, model selection, output formats, cwd, sandbox/tool controls), so it can be added as another provider without changing creative schemas.

## Chosen architecture

- Add linked top-level child runs with `content_format: reel`, `animation_mode: motion-canvas`, `render_profile: reel_portrait`, and `parent_run_id`.
- Keep Reel creative source loading in a dedicated package. It will read only parent `input.json`, `narration.json`, optional `story_skeleton.json`, and grounded fact/claim data; parent Motion Canvas files are never enumerated or serialized.
- Add a thin `mav_reel.py` orchestrator for analyze, create, generate/resume, preview, targeted-shot regeneration, and render.
- Reuse shared model, audio, alignment, Motion Canvas validation/repair, preview, and final-render functions.
- Add a local immutable-shot timeline builder driven by aligned words and paragraph/audio boundaries. Models describe shots but never control exact timestamps.
- Add centralized render profiles and a portrait-only presentation library. Existing missing-profile manifests default to landscape.
- Add a separate Studio Reels tab that groups linked child runs under eligible parent lessons and exposes candidate, script, shot-plan, preview, regeneration, and render actions.
- Add the official Grok Build CLI as provider `grok`, defaulting to model `grok-4.5`, alongside Codex.

## Migration and compatibility

- Existing lesson inputs and manifests without `content_format` or `render_profile` retain lesson/landscape behavior.
- Existing `immutable_reels`, chapter, and legacy `immutable_shots` manifests remain readable.
- Portrait profile data participates in the render fingerprint, so landscape frame checkpoints cannot be reused for portrait output.
- Reel invalidation is dependency-based and confined to the child run. Parent artifacts are read-only sources.

## Main files

Add:

- `template_lab/reels/` source, schemas, validation, timeline, and pipeline modules
- `template_lab/scripts/mav_reel.py` and `template_lab/scripts/mav_grok.py`
- four Reel creative prompt pairs
- Reel Motion Canvas batch/repair/API prompts
- `motion_canvas_runtime/src/render-profile.ts` and `reel-presentation.tsx`
- focused Reel/profile/Grok tests

Modify:

- Motion Canvas pipeline/runtime renderer for profiles and Reel prompts
- model mapping/adapter for Reel tasks and Grok CLI
- audio configuration for energetic Reel-specific voice direction
- Studio server/client/styles for the separate Reels workflow

## Risks and controls

- Portrait runtime regression: resolve profile centrally, default to landscape, and test both dimensions.
- Creative contamination from parent visuals: use an allowlisted source loader and prompt-payload tests.
- Audio/timeline drift: reuse local alignment and immutable voiceover/timeline hashes.
- Paid regeneration/data loss: preserve existing cache guards and invalidate only dependent child artifacts.
- CLI output variability: use strict prompts plus local JSON extraction/schema validation; never allow CLI filesystem tools.

## Verification strategy

- Unit tests for source isolation, schemas, sequential paragraph IDs, profile resolution/fingerprints, contiguous frame timelines, voiceover hashes, cue/import rules, and selective invalidation.
- Existing Motion Canvas, audio, timing, server, and render regression tests.
- TypeScript compilation and Node syntax checks.
- A locally authored portrait smoke scene was previewed and rendered with silent audio; `ffprobe` confirmed a 1080×1920 H.264 video stream plus audio. No paid model or TTS call was used.
