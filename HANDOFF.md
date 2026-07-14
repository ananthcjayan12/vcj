# MAV Physics Animation Engine — Agent Handoff

Last updated: 14 July 2026

## 1. Read this first

This repository now contains a reusable, JSON-driven physics animation engine built with vanilla JavaScript, DOM/SVG, and GSAP. Phases 1–3 of the scene-module library are implemented and visually checked. There are 35 registered scene modules and three showcase compositions.

The next planned feature is the video export pipeline. Its browser-side foundation has been added, but the recorder itself does **not** exist yet. `npm run export` therefore does not work at this handoff point. See [Section 11](#11-video-export-phase-currently-incomplete) before continuing that work.

All repository files are currently untracked in Git. There is no clean committed baseline, so preserve existing files and review `git status` before editing.

## 2. Product goal

The engine turns a composition JSON file into a timed 1920×1080 educational animation. A composition chooses reusable scene modules and supplies parameters, duration, labels, and narration. The same module changes its content and animation behavior from those parameters; it is not tied to one fixed lesson.

The source plans are:

- [`plan.md`](plan.md): architecture, Phase 1 modules, and the planned video export pipeline.
- [`plan_2.md`](plan_2.md): Phase 2 and Phase 3 module specifications.

The implemented engine—not any temporary phase scaffold—is the source of truth when the plans and code differ.

## 3. Completed implementation

| Library group | Scenes | Showcase duration | Status |
|---|---:|---:|---|
| Phase 1 | 8 | 53.0 s | Implemented and previewed |
| Phase 2 | 7 | 51.5 s | Implemented and previewed |
| Phase 3 | 20 | 125.2 s | Implemented and previewed |
| **Total** | **35** | — | Registered and reusable |

### Phase 1 modules

`Scene_TitleCard`, `Scene_SummaryCard`, `Scene_MathEquation`, `Scene_ForceDiagram`, `Scene_GraphPlotter`, `Scene_WaveForm`, `Scene_CircuitDiagram`, and `Scene_ParticleModel`.

### Phase 2 modules

`Scene_CollisionBlocks`, `Scene_SankeyDiagram`, `Scene_EnergyBars`, `Scene_MagneticField`, `Scene_AtomicModel`, `Scene_NuclearDecay`, and `Scene_WaveBehavior`.

### Phase 3 modules

`Scene_DefinitionCard`, `Scene_ComparisonTable`, `Scene_NumericalExample`, `Scene_ProjectileMotion`, `Scene_CircularMotion`, `Scene_SpringMass`, `Scene_InclinedPlane`, `Scene_ThermalHeating`, `Scene_EMSpectrum`, `Scene_StandingWave`, `Scene_ElectronFlow`, `Scene_MotorEffect`, `Scene_EMInduction`, `Scene_Transformer`, `Scene_GasParticles`, `Scene_NuclearReaction`, `Scene_RayDiagram`, `Scene_OrbitalMotion`, `Scene_StarLifeCycle`, and `Scene_RadiationPenetration`.

The `modules/phase3/` directory is an active part of the implementation, not an obsolete generated scaffold. Its modules use `_shared.js` to keep common Phase 3 drawing and timeline behavior consistent. Reuse is driven by scene registration and JSON parameters, not by the folder name.

## 4. Repository map

```text
index.html                         Main modular-engine preview UI
engine/
  core.js                         Loads specs, builds master timeline, playback/export API
  validator.js                    Validates and normalizes scene parameters
  renderer.js                     DOM/SVG helpers, colors, duration and timeline finish helpers
  transitions.js                  Reusable transition helpers
  narrator.js                     Subtitles and optional browser speech synthesis
modules/
  _registry.js                    Authoritative map of all 35 scene classes
  Scene_*.js                      Phase 1 and Phase 2 scene implementations
  phase3/
    _shared.js                    Shared Phase 3 helpers and schema fragments
    Scene_*.js                    20 Phase 3 implementations
specs/
  phase-one-showcase.json         8-scene example composition
  phase-two-showcase.json         7-scene example composition
  phase-three-showcase.json       20-scene example composition; current default
styles/
  tokens.css                      Design tokens
  engine.css                      App shell, preview stage, controls, export mode
  modules/phase1.css              Phase 1 scene styling
  modules/phase2.css              Phase 2 scene styling
  modules/phase3.css              Phase 3 scene styling
output/playwright/                Visual verification screenshots
plan.md / plan_2.md               Original requirements and module specifications
package.json                      Preview/export commands; export command is not complete yet
```

`composition.html`, `script.js`, and `style.css` are the older standalone inertia-studio prototype. They are not imported by the modular engine in `index.html`. Do not mix their global `masterTimeline` implementation into the current engine unless the user explicitly asks to merge the prototype.

## 5. How the engine works

The runtime sequence is:

1. `index.html` loads GSAP and KaTeX from CDNs, then imports `engine/core.js`.
2. `core.js` chooses a spec from the `spec` URL query parameter or the body's `data-spec-url`.
3. `validateSpec()` verifies every scene name against `modules/_registry.js`, validates its parameters with the module schema, and normalizes its duration.
4. For each slide, the engine creates the registered module, calls `setup(stage, params)`, obtains its paused GSAP timeline from `buildTimeline(params)`, and inserts it into one master timeline.
5. Playback, seeking, scene navigation, subtitles, and the active-module list are synchronized from the master timeline.
6. Module cleanup is performed through `teardown()` when a composition is rebuilt.

Useful browser globals and events:

- `window.MAVEngine`: live `SceneEngine` instance.
- `window.MAVEngine.timeline`: master GSAP timeline.
- `mav:ready`: document event fired after all scenes are built. Its detail includes `duration` and `scenes`.
- `window.MAVExport.getMetadata()`: returns readiness, title, duration, and scene count.
- `window.MAVExport.seek(seconds)`: deterministically seeks and prepares one export frame.

The actual runtime length comes from the combined scene timelines. The top-level `totalDuration` property in a spec is descriptive and is currently not used to override the timeline.

## 6. Run and use the preview

The project must be served over HTTP because it uses ES modules and fetches JSON.

```bash
cd /Users/ananthu/Desktop/new_repos/animations
python3 -m http.server 8765 --bind 127.0.0.1
```

The equivalent package command is:

```bash
npm run preview
```

Then open:

```text
http://127.0.0.1:8765/
```

The default page loads the Phase 3 showcase. Any composition can be selected without editing `index.html`:

```text
http://127.0.0.1:8765/?spec=specs/phase-one-showcase.json
http://127.0.0.1:8765/?spec=specs/phase-two-showcase.json
http://127.0.0.1:8765/?spec=specs/phase-three-showcase.json
```

Available preview controls include play/pause, restart, timeline scrubbing, playback speed, narration toggle, scene-list navigation, keyboard Space for play/pause, and Left/Right arrows for scene navigation.

Speech narration is disabled by default. The narration button enables browser `speechSynthesis`; subtitles update regardless of whether speech is enabled.

## 7. Build a new composition from existing modules

Copy one of the files in `specs/` and modify the `slides` array. A minimal composition looks like this:

```json
{
  "$schema": "mav-physics-video-spec-v1",
  "title": "Forces lesson",
  "totalDuration": "auto",
  "slides": [
    {
      "scene": "Scene_TitleCard",
      "label": "Introduction",
      "duration": 5,
      "narration": "Let us explore balanced and unbalanced forces.",
      "params": {
        "title": "Forces",
        "subtitle": "Balanced and unbalanced motion"
      }
    },
    {
      "scene": "Scene_ForceDiagram",
      "label": "Force diagram",
      "duration": 7,
      "params": {
        "objectLabel": "Crate",
        "forces": [
          { "label": "Weight", "magnitude": 50, "direction": "down", "color": "force" },
          { "label": "Normal", "magnitude": 50, "direction": "up", "color": "velocity" }
        ]
      }
    }
  ]
}
```

Use a scene name exactly as exported in `modules/_registry.js`. Each module's `getParamSchema()` is the authoritative list of accepted parameters and defaults. The showcase specs are the quickest source of valid examples for all 35 scenes.

Validation behavior to remember:

- An unknown scene name stops loading with an error.
- Missing or invalid parameters are replaced with schema defaults and produce warnings.
- Slide duration is clamped to a minimum of two seconds.
- Schemas with `additionalProperties: false` discard unsupported parameter keys.

## 8. Add or change a reusable scene module

Every module follows the same contract:

```js
export class Scene_Example {
  setup(container, params) {
    // Create and append this.root. Do not start an independent timeline here.
  }

  buildTimeline(params) {
    const timeline = gsap.timeline({ paused: true });
    // Build all scene animation into this timeline.
    return timeline;
  }

  teardown() {
    this.root?.remove();
  }

  static getParamSchema() {
    return { type: "object", properties: {} };
  }
}
```

Implementation checklist:

1. Prefer helpers from `engine/renderer.js`; Phase 3-style scenes can also use `modules/phase3/_shared.js`.
2. Keep the returned timeline paused. The engine makes it a child of the master timeline.
3. Use the validated `params.duration`, normally through `duration()`, `finishTimeline()`, or `finishPhase3()`.
4. Put every animation affecting the scene into the returned timeline. Independent timers or infinite global tweens make deterministic seeking and video export unreliable.
5. Store the root node on `this.root` and remove it in `teardown()`.
6. Export the class and register it in `modules/_registry.js`.
7. Add scene-specific CSS to the appropriate module stylesheet.
8. Add a showcase slide, seek through its complete duration, and check both its first and final transition frames.

Do not create duplicate per-phase wrapper modules. One well-parameterized module should cover related visual situations wherever possible.

## 9. Visual system and dependencies

The stage is authored at exactly 1920×1080 and scaled down only for the interactive preview. Core colors and typography live in `styles/tokens.css`; shared scene colors are also exposed by `engine/renderer.js`.

The current page uses network-hosted dependencies:

- GSAP 3.12.5 from cdnjs.
- KaTeX 0.16.11 from jsDelivr.
- Google Fonts: Fira Code, Outfit, and Plus Jakarta Sans.

An internet connection is therefore required for a fresh preview/export unless these assets are vendored locally. If exports must be fully reproducible or run in CI, vendoring and pinning these assets is a sensible follow-up.

## 10. Verification performed

The implementation was visually exercised through real-browser previews. There are 33 PNG artifacts in `output/playwright/`, including overview/preview screenshots for all phases and one screenshot for each of the 20 Phase 3 scenes.

Useful samples:

- [`output/playwright/phase1-preview.png`](output/playwright/phase1-preview.png)
- [`output/playwright/phase2-preview.png`](output/playwright/phase2-preview.png)
- [`output/playwright/phase3-preview.png`](output/playwright/phase3-preview.png)
- [`output/playwright/phase3-scenes/`](output/playwright/phase3-scenes/)

At this handoff, all files in `engine/`, `modules/`, and `modules/phase3/` pass `node --check`; all three specs and `package.json` parse successfully. There is not yet an automated unit/integration test suite.

## 11. Video export phase: currently incomplete

The next phase specified in `plan.md` is a headless-browser and FFmpeg pipeline that produces a 1920×1080 H.264 MP4 at 30 fps, with fade-in/out and an optional narration track.

The following export foundation **is already implemented**:

- `?spec=...` selects a composition dynamically.
- `?export=1` activates a clean, UI-free 1920×1080 stage through `styles/engine.css`.
- `window.MAVExport.getMetadata()` exposes render metadata.
- `window.MAVExport.seek(time)` prepares an exact frame from the master timeline.
- `package.json` defines intended `export` and `export:sample` commands.
- `.gitignore` excludes `node_modules/` and generated `output/video/` files.

The following work **has not been implemented**:

- There is no `export/recorder.js` file yet.
- `puppeteer-core` has not been installed and there is no `package-lock.json`.
- No PNG-frame sequence or MP4 has been generated.
- TTS generation/audio merging has not been implemented.
- The new export-mode hook has not yet received a visual browser regression check.

Consequently, do not report the export phase as complete and do not run `npm run export` expecting success.

### Recommended continuation

Use deterministic frame capture rather than real-time screencasting:

1. Install the pinned `puppeteer-core` dependency with `npm install`.
2. Implement `export/recorder.js` as a reusable CLI accepting at least `--spec`, `--output`, `--fps`, `--start`, `--duration`, and optional `--audio`/`--tts` flags.
3. Auto-start a local static server when the caller does not supply a URL.
4. Launch local Chrome at 1920×1080. On this machine it is available at `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`.
5. Load `index.html?export=1&spec=...`, wait until `window.MAVExport.getMetadata().ready` is true, and obtain the actual master duration.
6. For frame `n`, call `window.MAVExport.seek(start + n / fps)` and capture only after layout has settled.
7. Encode frames with the installed FFmpeg using `libx264`, `yuv420p`, 30 fps, `+faststart`, and short video fades.
8. If audio is supplied or generated, align it to the master-timeline timestamps, pad/trim to the exact render length, apply audio fades, and encode AAC.
9. First verify a two-second sample, then one full short showcase, and only then render the 125.2-second Phase 3 showcase.

Local tooling already confirmed:

- Node.js 22.9.0 and npm 10.8.3.
- Google Chrome is installed.
- FFmpeg/ffprobe 7.1.1 are installed with `libx264` support.
- macOS `/usr/bin/say` is available if automatic TTS is desired.

`puppeteer-core` is pinned to `24.43.1` in `package.json`. If changing that version, verify its Node engine requirement before installation.

## 12. Known caveats and safe next steps

- The Git worktree has no tracked baseline. Create a deliberate initial commit only with user approval; do not discard or reset files.
- The preview header text and module-count badge are currently Phase 3-specific even when another spec is selected via the query string. The animation content changes correctly, but the surrounding UI label does not. This can be made data-driven later.
- External CDN assets are a reproducibility risk for offline or CI export.
- The legacy standalone prototype and modular engine coexist; confirm which surface the user means before changing legacy files.
- Preserve deterministic timelines: avoid animation state based on wall-clock time, random values without seeding, or unmanaged `requestAnimationFrame` loops.
- After any engine change, test seeking backward as well as forward; export capture and interactive scrubbing both depend on correct timeline reversibility.

## 13. Suggested first commands for the next agent

```bash
cd /Users/ananthu/Desktop/new_repos/animations
git status --short
sed -n '1,240p' HANDOFF.md
npm run preview
```

For export work, inspect `engine/core.js`, the export-mode rules near the top of `styles/engine.css`, Section 6 of `plan.md`, and Section 11 of this handoff before writing the recorder.
