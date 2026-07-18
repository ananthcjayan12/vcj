# Approved native Reel Motion Canvas API

Use only these imports unless the supplied starter demonstrates another local deterministic helper:

```ts
import {Circle, Grid, Layout, Line, Node, Polygon, Rect, Txt, makeScene2D} from '@motion-canvas/2d';
import {Vector2, all, chain, createRef, createSignal, easeInOutCubic, easeOutCubic, linear, waitFor} from '@motion-canvas/core';
import {ReelBackground, ReelSafeStage, HookText, QuestionPrompt, PredictionChoice, ObjectLabel, EquationFlash, NumberCounter, PayoffBanner, BrandMark, ProgressPulse} from '../../reel-presentation';
import {CUES} from './shot_NNN.cues';
```

Every shot must use `ReelBackground` or an equivalent centered 1080×1920 background and use portrait presentation components for hooks, questions, equations, numeric readouts, labels, and payoff copy. Never import the landscape `../../presentation` module.

Motion Canvas coordinates are centered. Visible x is -540..540 and y is -960..960. Primary instructional bounds are x=-450..330 and y=-800..520. Keep caption space y=540..740 clear. Avoid right x=350..540 and bottom y=760..960 because platform controls may cover them. Reserve the complete size of every component, including labels and animated extrema.

`CUES` contains normalized shot-local word timestamps. Access numeric keys with brackets, for example `CUES["9"][0]`. Do not invent semantic time literals. A semantic reveal must use a supplied cue. Decorative easing may use fixed durations, but all state must remain deterministic and derive from `localTime()` or `progress()`.

Required ending:

```ts
const SHOT_DURATION = 4.2;
const progress = createSignal(0);
const localTime = () => progress() * SHOT_DURATION;
// deterministic reactive scene
yield* progress(1, SHOT_DURATION, linear);
```

Use JSX string keys, no global `JSX.Element`, no CSS color name `transparent` (use `#00000000`), no Math.random, timers, network assets, or variable-delta integration. Raw `Txt` is only for diagram labels of six words or fewer and must be 42 px or larger. Maintain at least 28 px between unrelated visible regions. Text assists the visual; it never transcribes narration.
