# Physics Template Lab

This is the repo-local physics production pipeline. It accepts grounded educational fact packets and creates student-friendly IGCSE lesson videos through the comparison-safe legacy route, integrated direct-HTML route, or narration-driven Motion Canvas route.

Motion Canvas production is selected with `--animation-mode motion-canvas`. It consumes the exact voiceover and word timestamps from steps 3–4, then writes deterministic manifests, cached two-chapter generation batches, strict TSX validation evidence, and locally assembled `scenes.ts` under `runs/<run-id>/motion_canvas/`. Paid calls require `--use-model --confirm-paid-api`; accepted caches are preserved. The pinned editor scaffold is in `motion_canvas_runtime/`.

Pipeline stages:

1. validate grounded topic facts;
2. generate a duration-aware teaching sequence and narration;
3. create voiceover audio;
4. align narration with local Whisper;
5. dispatch the visual route: compose one full-lesson modern-science HTML application, or run the frozen legacy recipe/V3 generator;
6. validate the runtime contract and inspect chapter frames in Chromium, with bounded chapter repair for direct HTML;
7. build a browser preview;
8. review the preview manually, then render an MP4 with pinned HyperFrames plus FFmpeg.

Run all commands from the repository root. See `END_TO_END_README.md` for the complete manual workflow and `video_engine/README.md` for curriculum/coverage commands.

## Paid API boundary

Script, scene, and voice generation can call external paid services. The generator refuses these steps unless `--confirm-paid-api` is present. Preview rebuilds, validators, tests, and rendering of an existing run remain local.

## Local checks

```bash
cd template_lab && npm install && cd ..
python3 -m unittest discover -s template_lab/tests
python3 -m video_engine.cli doctor
```

Generated artifacts go to `template_lab/runs/<run-id>/` and are intentionally ignored by Git.

## Direct-HTML route

The direct route keeps stages 1–4 shared, then stores its complete bundle, prompts, HTML versions, chapter index, screenshots, validation, and repair records under `runs/<run-id>/direct_html/`. Legacy output is never substituted after a direct-HTML failure.

```bash
python3 -m video_engine.cli generate-video RUN_ID --topic-ref 1.1 --animation-mode direct-html --confirm-paid-api
python3 -m video_engine.cli compose-html RUN_ID --confirm-paid-api
python3 -m video_engine.cli inspect-html RUN_ID
python3 -m video_engine.cli repair-html RUN_ID --chapter chapter_04 --instruction "Clarify the measurement" --confirm-paid-api
python3 -m video_engine.cli preview-html RUN_ID
python3 -m video_engine.cli render-html RUN_ID
```

`legacy-recipes` remains the CLI default until the two-topic comparison, scientific review, 9/10 first-pass reliability gate, and modern-platform score gate have been completed. Composition, repair, voice, and optional multimodal review calls require explicit paid-API confirmation; inspection, preview, validation, and rendering existing HTML are local.

## Why prompts remain

Prompts support story structure, narration, the integrated direct-HTML composer and repairer, and the explicitly optional legacy fallback. The direct route uses one coding-model call for the full visual lesson, with one bounded global contract repair only when needed. See `prompts/README.md` for model-task routing.
