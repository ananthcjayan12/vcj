# Active Physics V3 prompts

These prompts are still required. The reusable scene assets provide a visual language; these prompts decide the teaching sequence, narration, scene-specific layout, and timed GSAP choreography for each syllabus topic.

Seven model tasks are active:

- `script_structure.*`: turns grounded syllabus facts into teaching beats.
- `script_writing.*`: writes the final student-friendly narration.
- `scene_asset_shortlister.system.txt`: sees only a simple list grouped by physics module and selects the few assets relevant to the lesson.
- `scene_asset_router.system.txt`: sees detailed cards only for shortlisted assets and chooses module or custom routes.
- `module_parameterizer.system.txt`: fills only the selected module's full JSON Schema from grounded narration and facts.
- `v3_creative_director.system.txt` + `v3_design_system.txt`: chooses a Physics V3 layout using the approved visual identity.
- `v3_scene_coder.system.txt`: converts that layout into validated HTML/CSS/GSAP.

Provider and model defaults live in `prompt_model_mapping.json`.
