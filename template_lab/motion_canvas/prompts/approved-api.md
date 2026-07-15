# Approved Motion Canvas API for the MVP

Use only these imports unless the starter scene already demonstrates another one:

```ts
import {Circle, Grid, Layout, Line, Node, Rect, Txt, makeScene2D} from '@motion-canvas/2d';
import {Vector2, all, chain, createRef, createSignal, linear, waitFor} from '@motion-canvas/core';
```

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
- JSX `key` values must be strings, for example `key={String(index)}`; never pass a number.
- Do not use the global `JSX.Element` type. When storing constructed scene nodes, import `Node` and use `Node[]`.
- Motion Canvas does not accept the CSS color name `transparent`; use the explicit alpha color `#00000000`.

The robot controls `project.ts`, the renderer, build configuration, screenshots, and video export. Never reproduce or modify that infrastructure.
