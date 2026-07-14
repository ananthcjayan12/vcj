# Physics Animation Scene Library

This directory is the repo-local copy of the reusable JSON-driven physics animation engine. It contains 35 registered scenes, three showcase compositions, and five pilot lesson compositions. It has no runtime dependency on the original `animations` repository.

## Install and preview

```bash
cd physics_animation_engine
npm install
npm run preview
```

Open `http://127.0.0.1:8765/`. Select another composition with the `spec` query parameter:

```text
http://127.0.0.1:8765/?spec=specs/phase-one-showcase.json
http://127.0.0.1:8765/?spec=specs/pilot/04-speed-time-graph.json
```

The browser uses the local GSAP and KaTeX packages. Google Fonts are optional network resources; the CSS fallbacks keep the preview usable when they are unavailable.

## Library layout

```text
engine/                 composition loader, validation, playback and export hooks
modules/                15 Phase 1/2 scene modules
modules/phase3/         20 additional scene modules
styles/                 app and scene CSS
specs/                  reusable example compositions
specs/pilot/            five IGCSE lesson examples
```

`modules/_registry.js` is the authoritative scene list. A composition is JSON with a `slides` array; each slide names a registered scene and supplies `duration`, optional `narration`, and `params`.

Print the machine-readable parameter schema for every scene with `npm run catalog`. The curriculum CLI includes these schemas and example-spec references in `video_engine/registry/animation_assets.json`.

This package is the deterministic reusable-scene library. Final narrated HTML and MP4 production is handled by the repo-local `template_lab/` pipeline.
