from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from mav_assets import (
    build_compact_catalog,
    build_grouped_scene_index,
    validate_module_params,
    validate_route_plan,
    validate_shortlist,
)


class MavAssetsTest(unittest.TestCase):
    def test_compact_catalog_contains_all_registered_modules_without_full_examples(self) -> None:
        payload = build_compact_catalog(write=False)
        self.assertEqual(payload["scene_count"], 41)
        self.assertEqual(len(payload["scenes"]), 41)
        self.assertNotIn("example_specs", payload["scenes"][0])
        self.assertIn("required_parameters", payload["scenes"][0])
        self.assertIn("duration_profile", payload["scenes"][0])
        self.assertIn("motion_cues", payload["scenes"][0])

    def test_route_plan_requires_every_expected_scene(self) -> None:
        valid = {"routes": [{"scene_id": "scene_01", "route": "module", "module": "Scene_TitleCard", "reason": "Opening", "confidence": .9}]}
        self.assertEqual(validate_route_plan(valid, ["scene_01"]), [])
        self.assertTrue(validate_route_plan(valid, ["scene_01", "scene_02"]))

    def test_simple_index_groups_names_without_parameter_schemas(self) -> None:
        payload = build_grouped_scene_index(write=False)
        self.assertEqual(payload["scene_count"], 41)
        self.assertGreater(len(payload["groups"]), 10)
        mechanics = next(group for group in payload["groups"] if group["module"] == "mechanics")
        self.assertIn("Scene_ForceDiagram", mechanics["scenes"])
        self.assertIsInstance(mechanics["scenes"][0], str)

    def test_shortlist_and_routes_are_restricted_to_selected_modules(self) -> None:
        available = ["Scene_TitleCard", "Scene_ForceDiagram"]
        self.assertEqual(validate_shortlist({"selected_modules": ["Scene_ForceDiagram"]}, available), [])
        self.assertTrue(validate_shortlist({"selected_modules": ["Scene_Unknown"]}, available))
        route = {
            "routes": [
                {
                    "scene_id": "scene_01",
                    "route": "module",
                    "module": "Scene_TitleCard",
                    "reason": "Opening",
                    "confidence": 0.9,
                }
            ]
        }
        self.assertTrue(
            validate_route_plan(route, ["scene_01"], allowed_modules=["Scene_ForceDiagram"])
        )

    def test_module_params_follow_registry_schema(self) -> None:
        self.assertEqual(validate_module_params("Scene_TitleCard", {"title": "Measurement"}), [])
        errors = validate_module_params("Scene_TitleCard", {"unknown": "value"})
        self.assertTrue(any("title is required" in error for error in errors))
        self.assertTrue(any("unknown is not allowed" in error for error in errors))

    def test_topic_1_1_modules_are_registered_and_schema_validated(self) -> None:
        self.assertEqual(
            validate_module_params(
                "Scene_VectorAdditionTriangle",
                {"firstLabel": "3 N east", "secondLabel": "4 N north", "resultantLabel": "5 N resultant"},
            ),
            [],
        )
        self.assertEqual(
            validate_module_params(
                "Scene_PendulumTiming", {"oscillations": 10, "totalTime": 12.4, "unit": "s"}
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
