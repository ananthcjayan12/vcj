from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from mav_build_preview_v3 import _audio_src_for_run, _module_init_calls, _recipe_init_calls, _scene_section


class MavBuildPreviewTest(unittest.TestCase):
    def test_audio_source_is_relative_to_composition(self) -> None:
        run_path = ROOT / "runs" / "audio-path-test"
        self.assertEqual(_audio_src_for_run(run_path), "../voiceover.mp3")

    def test_scene_section_injects_content_inside_shell_wrapper(self) -> None:
        html = _scene_section(
            {
                "id": "scene_01",
                "start": 0,
                "duration": 4,
                "scene_html": '<div id="b01_card">Text</div><style>#b01_card{color:var(--ink);}</style>',
            }
        )

        self.assertIn('<div class="camera">', html)
        self.assertIn('<div class="v3-scene-content">', html)
        self.assertLess(html.index('<div class="camera">'), html.index('<div class="v3-scene-content">'))
        self.assertLess(html.index('<div class="v3-scene-content">'), html.index('id="b01_card"'))

    def test_module_scene_uses_registered_runtime_host(self) -> None:
        scene = {
            "id": "scene_02", "start": 4, "duration": 6, "renderer": "module",
            "module": {"scene": "Scene_DefinitionCard", "params": {"term": "Vector", "definition": "Magnitude and direction."}},
            "timing": {"cue_points": [0.8, 2.1, 4.2], "final_hold_seconds": 1.1},
        }
        html = _scene_section(scene)
        init = _module_init_calls([scene])
        self.assertIn("mav-module-scene", html)
        self.assertIn("module-scene-content", html)
        self.assertIn("Scene_DefinitionCard", init)
        self.assertIn('"cuePoints": [0.8, 2.1, 4.2]', init)
        self.assertIn('"finalHoldSeconds": 1.1', init)
        self.assertIn("tl.add(moduleTimeline.paused(false), 4.0)", init)

    def test_recipe_scene_uses_local_compiler_host(self) -> None:
        scene = {
            "id": "scene_03",
            "start": 10,
            "duration": 7,
            "renderer": "recipe",
            "recipe": {
                "id": "measurement_ruler",
                "workbench": "Measurement and apparatus",
                "layout": "instrument_demo",
                "nodes": [{"id": "ruler", "type": "ruler", "x": .2, "y": .3, "width": .6, "height": .2}],
                "actions": [{"target": "ruler", "type": "reveal", "at": .1, "duration": .1}],
            },
            "timing": {"cue_points": [1.2], "final_hold_seconds": 1.0},
        }

        html = _scene_section(scene)
        init = _recipe_init_calls([scene])

        self.assertIn("mav-recipe-scene", html)
        self.assertIn("recipe-scene-content", html)
        self.assertIn("new RecipeScene()", init)
        self.assertIn('"cuePoints": [1.2]', init)
        self.assertIn("tl.add(recipeTimeline.paused(false), 10.0)", init)


if __name__ == "__main__":
    unittest.main()
