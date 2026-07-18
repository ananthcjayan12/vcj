# Approved portrait API

Canvas is always **1080×1920** (`short_portrait`). Origin is the center. Safe content width ≈ 940px. Keep important labels inside y ≈ -860 … +860.

Use Motion Canvas `@motion-canvas/2d` / `@motion-canvas/core` plus `../short-presentation`:

## Components and props

- `ShortHook` — `text` (or `title`), optional `fontSize`, `y`, `opacity`
- `ShortTitle` — `title` or `text`
- `ShortSubtitle` — `subtitle` or `text`
- `PortraitTextCard` — `title?`, `text`/`body`, or `children`
- `PortraitEquationCard` — `title?`, `equation`, `caption?`, or `children`
- `PortraitStatReadout` — `label`, `value`
- `CaptionSafeArea` — `text` **or** `children` (preferred for multi-line captions). Default y ≈ 745–810
- `DiagramStage` — container for free-positioned diagram nodes; `y`, `width`, `height`, `children`
- `VerticalComparison` / `VerticalCardStack` — column stacks of cards
- `ExamTrapBadge` — `text`
- `PredictionPrompt` / `AnswerReveal` — card wrappers with `text`
- `ProgressBar` — `progress` (0–1 signal), `width`, `y`, `accent`

## Rules

1. Return only executable TSX. No markdown fences. No `<<<START OF FILE>>>` banners.
2. Every `fontSize` integer **≥ 34**. Prefer 40–52 body, 64–96 hooks.
3. No remote URLs, no `Math.random`, no landscape 1920×1080 root scaled into portrait.
4. Import cues from `./{short_id}.cues` and drive duration with `SHORT_DURATION`.
5. Prefer one clear diagram + caption over dense essay text on screen.
6. Layout for phone: large type, high contrast, few simultaneous labels.
