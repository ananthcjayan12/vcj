# Active physics production prompts

These prompts are still required. The reusable scene assets provide a visual language; these prompts decide the teaching sequence, narration, scene-specific layout, and timed GSAP choreography for each syllabus topic.

The shared script tasks, frozen legacy visual tasks, and direct-HTML visual tasks are:

- `script_structure.*`: turns grounded syllabus facts into teaching beats.
- `script_writing.*`: writes the final student-friendly narration.
- `scene_asset_shortlister.system.txt`: sees only a simple list grouped by physics module and selects the few assets relevant to the lesson.
- `scene_asset_router.system.txt`: sees detailed cards only for shortlisted assets and chooses module or custom routes.
- `module_parameterizer.system.txt`: fills only the selected module's full JSON Schema from grounded narration and facts.
- `v3_creative_director.system.txt` + `v3_design_system.txt`: chooses a Physics V3 layout using the approved visual identity.
- `v3_scene_coder.system.txt`: converts that layout into validated HTML/CSS/GSAP.
- `direct_html_composer.system.txt` + `direct_html_design_system.txt`: composes one complete modern science-platform HTML lesson from the full timed bundle.
- `direct_html_repair.system.txt`: returns one exact chapter replacement without changing timing, claims, or physics values.
- `direct_html_review.system.txt`: optionally scores a browser contact sheet when a paid multimodal review is explicitly approved.

Provider and model defaults live in `prompt_model_mapping.json`.
