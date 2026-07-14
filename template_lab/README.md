# Physics Template Lab

This is the repo-local Physics V3 production pipeline. It accepts grounded educational fact packets and creates student-friendly IGCSE lesson videos using the approved physics visual identity.

Pipeline stages:

1. validate grounded topic facts;
2. generate a duration-aware teaching sequence and narration;
3. create voiceover audio;
4. align narration with local Whisper;
5. generate V3 custom HTML/CSS/GSAP scenes in the approved physics style;
6. validate and repair scene artifacts;
7. build a browser preview;
8. run QA and render an MP4 with pinned HyperFrames plus FFmpeg.

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

Reusable scene assets establish the visual language, but they cannot decide the teaching sequence, narration, topic-specific diagram, or its timing. The pipeline therefore retains only seven active prompt files: two for lesson structure, two for narration, a visual design-system/creative-director pair, and one scene coder. See `prompts/README.md`.
