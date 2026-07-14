from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from mav_recipes import (  # noqa: E402
    WORKBENCHES,
    claim_id_to_objective_id,
    load_recipe_manifest,
    select_recipe,
    validate_manifest,
    validate_recipe,
)


TOPIC_1_1_OBJECTIVES = {
    "1.1-C01",
    "1.1-C02",
    "1.1-C03",
    "1.1-S04",
    "1.1-S05",
    "1.1-S06",
    "1.1-S07",
}


class MavRecipesTest(unittest.TestCase):
    def test_manifest_is_valid_and_declares_all_workbenches(self) -> None:
        manifest = load_recipe_manifest()
        self.assertEqual(validate_manifest(manifest), [])
        self.assertEqual(manifest["version"], 1)
        self.assertEqual(manifest["workbenches"], list(WORKBENCHES))

    def test_all_topic_1_1_objectives_have_multiple_valid_variants(self) -> None:
        manifest = load_recipe_manifest()
        by_objective: dict[str, list[dict]] = {}
        for entry in manifest["recipes"]:
            by_objective.setdefault(entry["objective_id"], []).append(entry["recipe"])
        self.assertTrue(TOPIC_1_1_OBJECTIVES.issubset(by_objective))
        for objective_id in TOPIC_1_1_OBJECTIVES:
            self.assertGreaterEqual(len(by_objective[objective_id]), 2, objective_id)
            for recipe in by_objective[objective_id]:
                self.assertEqual(validate_recipe(recipe), [], recipe["id"])

    def test_claim_handles_map_to_canonical_objective_ids(self) -> None:
        self.assertEqual(claim_id_to_objective_id("1.1-C01"), "1.1-C01")
        self.assertEqual(claim_id_to_objective_id("1_1_C01"), "1.1-C01")
        self.assertEqual(claim_id_to_objective_id("1_1_S07.detail"), "1.1-S07")
        self.assertEqual(claim_id_to_objective_id("2_1_1_C2"), "2.1.1-C02")
        self.assertIsNone(claim_id_to_objective_id("syllabus_topic"))

    def test_selection_is_deterministic_and_returns_a_deep_copy(self) -> None:
        arguments = (
            ["1.1-C01"],
            "diagram_reading",
            "Read the meniscus at eye level to avoid parallax error.",
            {"1.1-C01": 2},
        )
        first = select_recipe(*arguments)
        second = select_recipe(*arguments)
        self.assertEqual(first, second)
        self.assertEqual(first["recipe"]["id"], "measurement_meniscus_parallax")
        self.assertEqual(first["selection"]["objective_id"], "1.1-C01")
        first["recipe"]["nodes"][0]["x"] = 0.99
        third = select_recipe(*arguments)
        self.assertNotEqual(first["recipe"], third["recipe"])

    def test_occurrence_breaks_an_unscored_tie_without_changing_objective(self) -> None:
        first = select_recipe(["1.1-C01"], "unknown", "no matching cues", {"1.1-C01": 0})
        second = select_recipe(["1.1-C01"], "unknown", "no matching cues", {"1.1-C01": 1})
        self.assertNotEqual(first["recipe"]["id"], second["recipe"]["id"])
        self.assertEqual(first["selection"]["objective_id"], "1.1-C01")
        self.assertEqual(second["selection"]["objective_id"], "1.1-C01")

    def test_keywords_cannot_route_across_unrelated_objectives(self) -> None:
        result = select_recipe(
            ["1.1-C02"],
            "mechanism",
            "Use a ruler and measuring cylinder, then read the meniscus.",
            {},
        )
        self.assertEqual(result["selection"]["objective_id"], "1.1-C02")
        self.assertTrue(result["recipe"]["id"].startswith("timing_"))

    def test_unsafe_and_unknown_recipe_fields_are_rejected(self) -> None:
        base = copy.deepcopy(load_recipe_manifest()["recipes"][0]["recipe"])
        base["html"] = "<script>alert(1)</script>"
        base["nodes"][0]["svg_path"] = "M0 0"
        errors = validate_recipe(base)
        self.assertTrue(any("unsafe" in error for error in errors))
        self.assertTrue(any("html is not allowed" in error for error in errors))
        self.assertTrue(any("svg_path is not allowed" in error for error in errors))

        unknown_types = copy.deepcopy(load_recipe_manifest()["recipes"][0]["recipe"])
        unknown_types["nodes"][0]["type"] = "custom_html_widget"
        unknown_types["actions"][0]["type"] = "execute_javascript"
        errors = validate_recipe(unknown_types)
        self.assertTrue(any("registered node type" in error for error in errors))
        self.assertTrue(any("registered action type" in error for error in errors))

    def test_geometry_targets_and_durations_are_validated(self) -> None:
        recipe = copy.deepcopy(load_recipe_manifest()["recipes"][0]["recipe"])
        recipe["nodes"][0]["x"] = 0.9
        recipe["nodes"][0]["width"] = 0.4
        recipe["actions"][0]["target"] = "missing"
        recipe["actions"][0]["at"] = 0.9
        recipe["actions"][0]["duration"] = 0.4
        errors = validate_recipe(recipe)
        self.assertTrue(any("inside the normalized canvas" in error for error in errors))
        self.assertTrue(any("reference a node" in error for error in errors))
        self.assertTrue(any("normalized timeline" in error for error in errors))

    def test_unknown_or_uncovered_objective_has_no_recipe(self) -> None:
        self.assertIsNone(select_recipe(["not-an-objective"], "mechanism", "ruler", {}))
        self.assertIsNone(select_recipe(["1.2-C01"], "mechanism", "speed", {}))

    def test_syllabus_wide_graph_and_region_vocabulary_is_available(self) -> None:
        recipe = {
            "id": "generic_graph_evidence",
            "workbench": "Waves, optics and signals",
            "layout": "simulation_graph",
            "title": "Read the changing signal",
            "nodes": [
                {
                    "id": "plot",
                    "type": "graph",
                    "x": 0.08,
                    "y": 0.2,
                    "width": 0.56,
                    "height": 0.58,
                    "xLabel": "time / s",
                    "yLabel": "displacement / cm",
                    "points": [{"x": 0, "y": 0.5}, {"x": 0.5, "y": 0.9}, {"x": 1, "y": 0.5}],
                },
                {
                    "id": "evidence",
                    "type": "region",
                    "x": 0.7,
                    "y": 0.3,
                    "width": 0.22,
                    "height": 0.26,
                    "label": "evidence",
                    "text": "Compare amplitude and period.",
                },
            ],
            "actions": [
                {"type": "draw", "target": "plot", "at": 0.04, "duration": 0.5},
                {"type": "reveal", "target": "evidence", "at": 0.62, "duration": 0.22},
            ],
        }
        self.assertEqual(validate_recipe(recipe), [])


if __name__ == "__main__":
    unittest.main()
