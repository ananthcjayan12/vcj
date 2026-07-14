# Active Physics V3 prompts

These prompts are still required. The reusable scene assets provide a visual language; these prompts decide the teaching sequence, narration, scene-specific layout, and timed GSAP choreography for each syllabus topic.

Only four model tasks remain:

- `script_structure.*`: turns grounded syllabus facts into teaching beats.
- `script_writing.*`: writes the final student-friendly narration.
- `v3_creative_director.system.txt` + `v3_design_system.txt`: chooses a Physics V3 layout using the approved visual identity.
- `v3_scene_coder.system.txt`: converts that layout into validated HTML/CSS/GSAP.

Provider and model defaults live in `prompt_model_mapping.json`.
