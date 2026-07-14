from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import mav_models
import mav_generate
import mav_plan_v3


class HybridAssetRoutingTest(unittest.TestCase):
    def test_grounded_objective_recipe_avoids_all_scene_model_calls(self) -> None:
        narration = {
            "title": "Measurement",
            "paragraphs": [{
                "id": "paragraph_01",
                "text": "Align the ruler zero with the object before reading the scale.",
                "beat_label": "mechanism",
                "claim_ids": ["1_1_C01"],
            }],
        }
        timing = {
            "audio_duration_seconds": 8.0,
            "paragraphs": [{"id": "paragraph_01", "start": 0.0, "end": 8.0, "duration": 8.0}],
        }
        input_payload = {
            "run_id": "recipe-routing-test",
            "topic": "1.1 Measurement",
            "topic_ref": "1.1",
            "template_id": "physics",
            "objective_ids": ["1.1-C01"],
            "facts": [],
        }

        with tempfile.TemporaryDirectory() as directory:
            run_path = Path(directory)
            with (
                patch.object(mav_plan_v3, "run_dir", return_value=run_path),
                patch.object(mav_models, "call_model_json") as model_json,
                patch.object(mav_models, "call_model_text") as model_text,
            ):
                plan = mav_plan_v3.generate_v3_scenes(
                    input_payload,
                    narration,
                    timing,
                    allow_model_fallback=False,
                )

            model_json.assert_not_called()
            model_text.assert_not_called()
            self.assertEqual(plan["planner_mode"], "objective_recipe_first")
            self.assertEqual(plan["routing_summary"]["recipe"], 1)
            self.assertEqual(plan["routing_summary"]["custom"], 0)
            self.assertEqual(plan["scenes"][0]["renderer"], "recipe")
            self.assertEqual(plan["scenes"][0]["objective_ids"], ["1.1-C01"])

    def test_router_receives_details_only_for_shortlisted_modules(self) -> None:
        calls: list[tuple[str, dict]] = []

        def fake_json(*, task, user, **kwargs):  # noqa: ANN001
            payload = json.loads(user)
            calls.append((task, payload))
            if task == "scene_asset_shortlister":
                return {
                    "selected_modules": ["Scene_TitleCard"],
                    "reason": "A concise opening card fits this one-beat lesson.",
                }
            if task == "scene_asset_router":
                return {
                    "routes": [
                        {
                            "scene_id": "scene_01",
                            "route": "module",
                            "module": "Scene_TitleCard",
                            "alternatives": [],
                            "reason": "The selected title card fits.",
                            "confidence": 0.95,
                            "parameter_guidance": "Show the lesson title.",
                        }
                    ]
                }
            if task == "module_parameterizer":
                return {"params": {"title": "Measurement"}}
            self.fail(f"Unexpected task {task}")

        narration = {
            "title": "Measurement",
            "paragraphs": [
                {
                    "id": "paragraph_01",
                    "text": "Measurement makes observations comparable.",
                    "beat_label": "hook",
                    "claim_ids": ["1_1_C01", "private_assessment_pattern_01", "1_1_C01"],
                }
            ],
        }
        timing = {
            "audio_duration_seconds": 8.0,
            "paragraphs": [{"id": "paragraph_01", "start": 0.0, "end": 8.0, "duration": 8.0}],
        }
        input_payload = {
            "run_id": "routing-test",
            "topic": "1.1 Measurement",
            "template_id": "physics",
            "objective_ids": ["1.1-C01"],
            "facts": [],
        }

        with tempfile.TemporaryDirectory() as directory:
            run_path = Path(directory)
            with (
                patch.object(mav_plan_v3, "run_dir", return_value=run_path),
                patch.object(mav_plan_v3, "select_recipe", return_value=None),
                patch.object(mav_models, "call_model_json", side_effect=fake_json),
                patch.object(mav_models, "call_model_text"),
            ):
                plan = mav_plan_v3.generate_v3_scenes(input_payload, narration, timing)

            router_request = next(payload for task, payload in calls if task == "scene_asset_router")
            self.assertEqual(
                [card["scene"] for card in router_request["shortlisted_modules"]],
                ["Scene_TitleCard"],
            )
            self.assertEqual(plan["routing_summary"]["shortlisted_scene_count"], 1)
            self.assertEqual(plan["scenes"][0]["renderer"], "module")
            self.assertEqual(plan["scenes"][0]["claim_ids"], ["1_1_C01", "private_assessment_pattern_01"])
            self.assertEqual(plan["scenes"][0]["objective_ids"], ["1.1-C01"])
            self.assertEqual(json.loads((run_path / "asset_index_used.json").read_text())["scene_count"], 41)

    def test_long_paragraph_is_split_into_short_visual_beats(self) -> None:
        paragraphs = [{
            "id": "paragraph_01",
            "text": "First we choose the instrument. Then we align the zero carefully. Finally we take the reading and include its unit.",
            "beat_label": "explain",
            "claim_ids": ["1_1_C01"],
            "start": 0.0,
            "end": 30.0,
            "duration": 30.0,
        }]
        beats = mav_plan_v3._split_visual_beats(paragraphs, [], target_seconds=11, max_seconds=15, min_seconds=5)
        self.assertGreaterEqual(len(beats), 3)
        self.assertTrue(all(beat["duration"] <= 15.01 for beat in beats))
        self.assertTrue(all(beat["source_paragraph_id"] == "paragraph_01" for beat in beats))
        self.assertTrue(all(beat["claim_ids"] == ["1_1_C01"] for beat in beats))
        self.assertEqual([beat["id"] for beat in beats], [f"paragraph_01_v0{i}" for i in range(1, len(beats) + 1)])

    def test_merge_timing_preserves_claim_ids_and_fact_id_mapping_is_strict(self) -> None:
        paragraphs = mav_plan_v3._merge_narration_timing(
            {
                "paragraphs": [
                    {
                        "id": "paragraph_01",
                        "text": "Measure length.",
                        "beat_label": "explain",
                        "claim_ids": ["1_1_C01", "4_5_6_s05", "not_an_objective"],
                    }
                ]
            },
            {"paragraphs": [{"id": "paragraph_01", "start": 1, "end": 3, "duration": 2}]},
        )
        self.assertEqual(paragraphs[0]["claim_ids"], ["1_1_C01", "4_5_6_s05", "not_an_objective"])
        self.assertEqual(mav_plan_v3._objective_id_from_claim_id("1_1_C01"), "1.1-C01")
        self.assertEqual(mav_plan_v3._objective_id_from_claim_id("4_5_6_s05"), "4.5.6-S05")
        self.assertEqual(mav_plan_v3._objective_id_from_claim_id("1.1-C01"), "1.1-C01")
        self.assertIsNone(mav_plan_v3._objective_id_from_claim_id("private_assessment_pattern_01"))
        self.assertIsNone(mav_plan_v3._objective_id_from_claim_id("1_1_X01"))

    def test_build_input_preserves_facts_packet_grounding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            facts_path = Path(directory) / "facts.json"
            facts_path.write_text(
                json.dumps(
                    {
                        "topic": "1.1 Measurement",
                        "topic_ref": "1.1",
                        "objective_ids": ["1.1-C01", "1.1-C01", "1.1-S04"],
                        "facts": [{"id": "1_1_C01", "text": "Measure length."}],
                    }
                ),
                encoding="utf-8",
            )
            args = type(
                "Args",
                (),
                {
                    "facts": facts_path,
                    "topic": None,
                    "run_id": "grounding-test",
                    "template_id": None,
                    "tone": None,
                    "duration": 60,
                },
            )()
            input_payload = mav_generate.build_input(args)
        self.assertEqual(input_payload["topic_ref"], "1.1")
        self.assertEqual(input_payload["objective_ids"], ["1.1-C01", "1.1-S04"])

    def test_module_cues_resolve_to_local_narration_times(self) -> None:
        words = [
            {"word": "align", "start": 12.0, "end": 12.3},
            {"word": "the", "start": 12.3, "end": 12.4},
            {"word": "zero", "start": 12.4, "end": 12.8},
            {"word": "read", "start": 16.0, "end": 16.3},
            {"word": "scale", "start": 16.3, "end": 16.7},
        ]
        points, resolved = mav_plan_v3._resolve_cue_points(
            ["align the zero", "read scale"], words, scene_start=10.0, scene_duration=9.0, fallback_count=4
        )
        self.assertEqual(resolved, ["align the zero", "read scale"])
        self.assertEqual(points, [1.72, 5.72])


if __name__ == "__main__":
    unittest.main()
