# Approved Motion Canvas API for the MVP

Use only these imports unless the starter scene already demonstrates another one:

```ts
import {Circle, Grid, Layout, Line, Node, Rect, Txt, makeScene2D} from '@motion-canvas/2d';
import {Vector2, all, chain, createRef, createSignal, linear, waitFor} from '@motion-canvas/core';
import {ComparisonTable, EquationCard, KineticActor, SceneTitle, StatReadout, TextCard, TwoColumnComparison} from '../../presentation';
import {CUES} from './reel_NNN.cues';
```

Kinetic choreography contract:

- `KineticActor` wraps one independent visual group without imposing a layout. Example: `<KineticActor id={'force-rig'} role={'primary'} priority={900}>...</KineticActor>`. Keep freely authored coordinates and animation inside it.
- Group the complete apparatus, graph, force diagram, particle model, or other intentionally overlapping illustration as one actor. Never wrap every primitive separately.
- Recommended roles are `primary`, `diagram`, `supporting`, `equation`, `readout`, and `decorative`. Higher priority actors stay closer to the authored position; lower priority actors yield first.
- Optional capabilities are `canShift`, `canScale`, `canFade`, `maxShift`, and `minScale`. Keep the central scientific visual non-fading. Supporting and decorative groups may fade only as the runtime's final crowding fallback.
- Presentation components register automatically, so they do not need an additional actor wrapper unless several components should move as one cluster.
- The choreography runtime runs after every deterministic seek and before drawing. It minimally restages simultaneous actors and diagram labels; it does not fail the pipeline or replace the scene with a template.

Presentation contract:

- `TwoColumnComparison` accepts exactly `left={{title, body, accent?}}` and `right={{title, body, accent?}}`. Put positioning or opacity on a wrapping `Layout`; do not pass `x`, `y`, `opacity`, `leftTitle`, `leftBody`, `rightTitle`, or `rightBody` directly to it.

- Reserve these complete presentation-component footprints when planning layout:
  - `SceneTitle`: reserve a 1500×120 title band when it includes a subtitle.
  - default `TextCard`: 720×260; compact `TextCard`: 500×140.
  - default `EquationCard`: 900×220; compact `EquationCard`: 500×140.
  - default `StatReadout`: 440×210; compact `StatReadout`: 360×140.
  - `TwoColumnComparison`: 1720×620. It is nearly full-screen and must normally be centered in its own region, not placed beside another panel.
  - `ComparisonTable`: 1720 pixels wide; reserve its full row-dependent height.
- A wrapper's `x` and `y` identify the center of the complete child footprint. Bounds are `left=x-width/2`, `right=x+width/2`, `top=y-height/2`, and `bottom=y+height/2`.
- Simultaneously visible presentation footprints must not intersect. Keep unrelated regions at least 32 pixels apart; intentional grouped card stacks may use the prescribed 20-pixel gap. A component revealed with `localTime() >= cue` remains present in every later frame unless its opacity also has an end cue.
- When successive narration beats need the same space, window the earlier component and replace it in the same stable slot. Do not keep adding permanent cards around a diagram.

- Use the presentation components for every title, prose block, comparison, table, equation card, and numeric readout.
- `EquationCard` supports real LaTeX through its `equation` property. Use valid TeX for fractions, powers, subscripts, vectors, Greek symbols, and arrows, for example `equation={'v = \\dfrac{s}{t}'}` or `equation={'F_{\\text{drag}} = W'}`. In a TSX expression, escape each TeX backslash as `\\`. Never show LaTeX commands in a raw `Txt` node, and never use Unicode-art approximations when proper TeX is clearer.
- Raw `Txt` is reserved for short diagram labels of at most six words. It is not approved for paragraphs, tables, comparison prose, headings, or calculation steps.
- Do not set `fontFamily`, major `fontSize`, line height, table geometry, card padding, or prose coordinates yourself. The fixed presentation components own them.
- `ComparisonTable` accepts 2-3 columns and at most 4 visible rows. Split a larger comparison into successive cue-driven table pages; never shrink it.
- Keep display copy within the runtime-enforced limits: scene title <=64 characters, scene subtitle <=72, card title <=42, card body <=110, equation TeX source <=120, equation caption <=72, stat value <=32, stat unit <=12, stat label <=42, table title <=54, table heading <=28, row label <=32, and cell <=48.
- Narration is spoken explanation, not display copy. Prefer a short label, value, equation, or two-line takeaway instead of reproducing a narration sentence.
- `CUES` maps normalized spoken words to arrays of exact chapter-local start times, for example `CUES.scalar[0]`. All semantic reveals must derive from these constants. Only decorative motion durations may use literal values.
- Use only cue keys and occurrence indexes present in the supplied chapter data. Apostrophes are normalized to underscores (`let's` becomes `CUES.let_s`). If a cue has one timestamp, never access index `[1]`, even with a nullish fallback.

Required architecture:

- `physics.ts` contains pure deterministic physics functions and exports `stateAt(time)`-style functions.
- `scene.tsx` owns exactly one simulation-time signal.
- Object positions, vectors, numeric labels, and graph cursors derive from the same state returned for that time.
- Physical motion is linear in simulation time. Never use SVG/path-length progress as physical time.
- Do not use `Math.random`, network assets, browser timers, mutable global state, or variable delta-time integration.
- The scene must last at least three seconds and must finish naturally.
- Motion Canvas uses a centered Cartesian canvas. At 1920×1080, `(0,0)` is the center—not the top-left. Visible coordinates are `x=-960..960`, `y=-540..540`.
- Keep complete important elements inside `x=-860..860`, `y=-440..440`. Include element dimensions, labels, arrowheads, and the extrema of animated positions.
- Never use browser-style placement such as `x=1200`, `y=800`, or center `(960,540)`. Convert browser coordinates using `x-960` and `y-540`.
- Center full-canvas backgrounds at `(0,0)`.
- Use large readable text, restrained colors, and progressive explanation instead of decorative motion.
- JSX `key` values must be strings and unique across the entire scene, not merely inside one mapped array. Prefix every mapped group, for example `key={`particles-${String(index)}`}` and `key={`labels-${String(index)}`}`. Never use bare `key={String(index)}` and never pass a number.
- Do not use the global `JSX.Element` type. When storing constructed scene nodes, import `Node` and use `Node[]`.
- Motion Canvas does not accept the CSS color name `transparent`; use the explicit alpha color `#00000000`.

The robot controls `project.ts`, the renderer, build configuration, screenshots, and video export. Never reproduce or modify that infrastructure.
