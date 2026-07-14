# Physics Template Lab

This is the repo-local Physics V3 production pipeline. It accepts grounded educational fact packets and creates student-friendly IGCSE lesson videos using the approved physics visual identity.

Pipeline stages:

1. validate grounded topic facts;
2. generate a duration-aware teaching sequence and narration;
3. create voiceover audio;
4. align narration with local Whisper;
5. select a grounded typed recipe locally from the narration beat's objective IDs
   and compile it into reusable DOM/SVG/GSAP workbenches; uncovered objectives fail
   clearly unless the legacy model fallback is explicitly enabled;
6. validate and repair scene artifacts;
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

## Why prompts remain

Prompts still support story structure, narration, and the explicitly optional legacy
fallback. Covered objectives do not use scene shortlisting, routing,
parameterization, direction, or coding models. Their diagrams and timing come from
validated local recipes in `assets/objective_visual_recipes.json`. See
`prompts/README.md` for the remaining model tasks.
