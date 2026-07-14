from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from mav_validate_v3 import repair_v3_plan, validate_scene_gsap, validate_v3_plan


class MavValidateV3Test(unittest.TestCase):
    def test_repair_normalizes_token_compatible_colors_and_handlers(self) -> None:
        plan = {
            "scenes": [
                {
                    "id": "scene_01",
                    "start": 0,
                    "duration": 4,
                    "scene_html": """
                    <div class="v3-scene-content" onclick="alert(1)">
                      <div style="box-shadow: 0 10px 20px rgba(23, 23, 20, 0.15); background: #f2efe4; fill: rgba(66,184,139,0.25);"></div>
                    </div>
                    """,
                    "scene_gsap": "function initScene(tl, start, dur) { tl.to({}, {}, start); }",
                }
            ]
        }

        repaired, repairs = repair_v3_plan(plan)
        self.assertTrue(repairs)
        html = repaired["scenes"][0]["scene_html"]
        self.assertNotIn("onclick", html)
        self.assertNotIn("rgba(", html)
        self.assertNotIn("#f2efe4", html)
        self.assertIn("color-mix(in srgb, var(--ink) 15%, transparent)", html)
        self.assertIn("color-mix(in srgb, var(--teal) 25%, transparent)", html)
        self.assertEqual(validate_v3_plan(repaired), [])

    def test_gsap_allows_callbacks_and_on_named_variables(self) -> None:
        gsap = """
        function initScene(tl, start, dur) {
          const shakeContainer = {};
          const tensionZone = {};
          tl.to({}, { onUpdate: function() { shakeContainer.x = tensionZone.y || 0; } }, start);
        }
        """
        self.assertEqual(validate_scene_gsap(gsap, "scene_01", 0, 4), [])

    def test_gsap_rejects_function_constructor(self) -> None:
        gsap = """
        function initScene(tl, start, dur) {
          const makeIt = new Function("return 1");
          tl.call(makeIt, null, start);
        }
        """
        violations = validate_scene_gsap(gsap, "scene_01", 0, 4)
        self.assertTrue(any(violation.code == "FUNCTION_CONSTRUCTOR" for violation in violations))

    def test_repair_recovers_style_block_outside_scene_html_markers(self) -> None:
        plan = {
            "scenes": [
                {
                    "id": "scene_02",
                    "start": 0,
                    "duration": 4,
                    "scene_html": '<div class="v3-scene-content"><div class="card">BROKEN WITHOUT CSS</div></div>',
                    "scene_gsap": "function initScene(tl, start, dur) { tl.to({}, {}, start); }",
                    "raw_response": """
                    <!--SCENE_HTML_START-->
                    <div class="v3-scene-content"><div class="card">BROKEN WITHOUT CSS</div></div>
                    <!--SCENE_HTML_END-->
                    <!--SCENE_GSAP_START-->
                    function initScene(tl, start, dur) { tl.to({}, {}, start); }
                    <!--SCENE_GSAP_END-->
                    <style>.card { position:absolute; left:200px; top:200px; color:var(--ink); }</style>
                    """,
                }
            ]
        }

        repaired, repairs = repair_v3_plan(plan)

        self.assertTrue(repairs)
        self.assertIn("<style>", repaired["scenes"][0]["scene_html"])
        self.assertEqual(validate_v3_plan(repaired), [])

    def test_repair_collapses_duplicate_scene_scope(self) -> None:
        plan = {
            "scenes": [
                {
                    "id": "scene_01",
                    "start": 0,
                    "duration": 4,
                    "scene_html": """
                    <div id="b01_pitch_diagram">
                      <svg><rect class="pitch-line" x="0" y="0" width="100" height="100"></rect></svg>
                    </div>
                    <style>
                      [data-scene-id="scene_01"] #b01_pitch_diagram {
                        position:absolute;
                        background:var(--paper-deep);
                      }
                      .mav-v3-scene[data-scene-id="scene_01"] [data-scene-id="scene_01"] .pitch-line {
                        fill:none;
                        stroke:var(--teal);
                      }
                    </style>
                    """,
                    "scene_gsap": "function initScene(tl, start, dur) { tl.to({}, {}, start); }",
                }
            ]
        }

        repaired, repairs = repair_v3_plan(plan)

        self.assertTrue(repairs)
        html = repaired["scenes"][0]["scene_html"]
        self.assertNotIn('.mav-v3-scene[data-scene-id="scene_01"] [data-scene-id="scene_01"]', html)
        self.assertIn('.mav-v3-scene[data-scene-id="scene_01"] #b01_pitch_diagram', html)
        self.assertIn('.mav-v3-scene[data-scene-id="scene_01"] .pitch-line', html)
        self.assertEqual(validate_v3_plan(repaired), [])

    def test_typed_recipe_scene_does_not_require_generated_html(self) -> None:
        plan = {
            "scenes": [{
                "id": "scene_04",
                "renderer": "recipe",
                "start": 0,
                "duration": 6,
                "recipe": {
                    "id": "measurement_ruler",
                    "workbench": "Measurement and apparatus",
                    "layout": "instrument_demo",
                    "nodes": [{"id": "ruler", "type": "ruler", "x": .2, "y": .3, "width": .6, "height": .2}],
                    "actions": [{"target": "ruler", "type": "reveal", "at": .1, "duration": .1}],
                },
            }]
        }

        self.assertEqual(validate_v3_plan(plan), [])


if __name__ == "__main__":
    unittest.main()
