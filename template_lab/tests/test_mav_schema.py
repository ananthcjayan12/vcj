from __future__ import annotations

import json
import os
import shutil
from argparse import Namespace
import unittest
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from mav_schema import narration_bounds, validate_narration, validate_run_input
from mav_script import generate_narration


class MavSchemaTest(unittest.TestCase):
    def sample_input(self) -> dict:
        return {
            "run_id": "schema-test",
            "topic": "Why AI is creating a memory-chip bottleneck",
            "tone": "investigative",
            "target_duration_seconds": 50,
            "facts": [
                {"id": "fact_01", "text": "AI servers require large amounts of advanced memory."},
                {"id": "fact_02", "text": "Advanced memory supply depends on specialized chip manufacturing capacity."},
                {"id": "fact_03", "text": "Demand can grow faster than supply."},
            ],
        }

    def test_run_input_validates(self) -> None:
        self.assertEqual(validate_run_input(self.sample_input()), [])

    def test_long_lesson_uses_duration_aware_narration_bounds(self) -> None:
        short = narration_bounds(50)
        lesson = narration_bounds(480)
        self.assertEqual(short, {"min_words": 115, "max_words": 155, "min_paragraphs": 6, "max_paragraphs": 8})
        self.assertEqual(lesson, {"min_words": 864, "max_words": 1224, "min_paragraphs": 14, "max_paragraphs": 27})

    def sample_narration(self) -> dict:
        paragraphs = [
            {
                "id": f"paragraph_{index:02d}",
                "beat_label": "beat",
                "text": "Memory demand is no longer a background detail because AI servers turn capacity into pricing power.",
                "claim_ids": [],
            }
            for index in range(1, 7)
        ]
        plain = " ".join(item["text"] for item in paragraphs)
        return {
            "title": "Memory Bottleneck",
            "target_duration_seconds": 50,
            "spoken_word_count": 126,
            "paragraphs": paragraphs,
            "elevenlabs_narration": plain,
        }

    def test_narration_requires_model(self) -> None:
        payload = self.sample_input()
        with self.assertRaisesRegex(RuntimeError, "requires --use-model"):
            generate_narration(payload)

    def test_unknown_claim_id_fails(self) -> None:
        payload = self.sample_input()
        narration = self.sample_narration()
        narration["paragraphs"][0]["claim_ids"] = ["missing_fact"]
        violations = validate_narration(narration, payload)
        self.assertTrue(any(v.code == "UNKNOWN_CLAIM_ID" for v in violations))

    def test_dotted_claim_id_uses_known_root(self) -> None:
        payload = self.sample_input()
        payload["facts"].append({"id": "raw_numbers", "text": "Structured numbers."})
        narration = self.sample_narration()
        narration["paragraphs"][0]["claim_ids"] = ["raw_numbers.currentPrice"]
        violations = validate_narration(narration, payload)
        self.assertFalse(any(v.code == "UNKNOWN_CLAIM_ID" for v in violations))

    def test_narration_rejects_date_relative_language(self) -> None:
        payload = self.sample_input()
        narration = self.sample_narration()
        narration["paragraphs"][0]["text"] = "Today, memory demand turns server capacity into a source of market power and pricing pressure."
        narration["elevenlabs_narration"] = " ".join(item["text"] for item in narration["paragraphs"])
        violations = validate_narration(narration, payload)
        self.assertTrue(any(v.code == "NARRATION_DATE_RELATIVE_LANGUAGE" for v in violations))

    def test_narration_allows_instructional_now(self) -> None:
        payload = self.sample_input()
        narration = self.sample_narration()
        narration["paragraphs"][0]["text"] = "Now consider how memory demand turns server capacity into pricing power and market pressure."
        narration["elevenlabs_narration"] = " ".join(item["text"] for item in narration["paragraphs"])
        violations = validate_narration(narration, payload)
        self.assertFalse(any(v.code == "NARRATION_DATE_RELATIVE_LANGUAGE" for v in violations))

    def test_narration_still_rejects_right_now(self) -> None:
        payload = self.sample_input()
        narration = self.sample_narration()
        narration["paragraphs"][0]["text"] = "Right now, memory demand turns server capacity into pricing power and market pressure."
        narration["elevenlabs_narration"] = " ".join(item["text"] for item in narration["paragraphs"])
        violations = validate_narration(narration, payload)
        self.assertTrue(any(v.code == "NARRATION_DATE_RELATIVE_LANGUAGE" for v in violations))

    def test_narration_rejects_symbol_damaged_words(self) -> None:
        payload = self.sample_input()
        narration = self.sample_narration()
        narration["paragraphs"][0]["text"] = "A key player named Hern%ndez becomes impossible to pronounce cleanly in narration."
        narration["elevenlabs_narration"] = " ".join(item["text"] for item in narration["paragraphs"])
        violations = validate_narration(narration, payload)
        self.assertTrue(any(v.code == "NARRATION_DAMAGED_WORD" for v in violations))

    def test_prompt_loading(self) -> None:
        sys.path.insert(0, str(ROOT))
        from prompts import list_prompts, load

        names = list_prompts()
        self.assertIn("script_structure.system", names)
        self.assertIn("script_writing.system", names)
        self.assertIn("v3_creative_director.system", names)
        self.assertIn("v3_scene_coder.system", names)
        self.assertIn("v3_design_system", names)

        text = load("script_structure.user", topic="TEST_TOPIC")
        self.assertIn("TEST_TOPIC", text)
        self.assertNotIn("{topic}", text)

        text = load("script_structure.user")
        self.assertIn("{topic}", text)

    def test_prompt_model_mapping(self) -> None:
        from mav_models import configured_models, model_config_for_task

        models = configured_models()
        expected = {
            "script_structure": ("gemini", "gemini-3.1-flash-lite", "claude-sonnet-5", "MAV_SCRIPT_STRUCTURE_MODEL", 64000),
            "script_writing": ("gemini", "gemini-3.1-flash-lite", "claude-opus-4-8", "MAV_SCRIPT_WRITING_MODEL", 64000),
            "scene_asset_shortlister": ("gemini", "gemini-3.1-flash-lite", "claude-sonnet-5", "MAV_SCENE_ASSET_SHORTLISTER_MODEL", 4000),
            "scene_asset_router": ("gemini", "gemini-3.5-flash", "claude-sonnet-5", "MAV_SCENE_ASSET_ROUTER_MODEL", 12000),
            "module_parameterizer": ("gemini", "gemini-3.1-flash-lite", "claude-sonnet-5", "MAV_MODULE_PARAMETERIZER_MODEL", 12000),
            "v3_creative_director": ("zai", "glm-5.2", "claude-opus-4-8", "MAV_V3_CREATIVE_DIRECTOR_MODEL", 16000),
            "v3_scene_coder": ("moonshot", "kimi-k2.7-code", "claude-sonnet-5", "MAV_V3_SCENE_CODER_MODEL", 32000),
        }
        for task, (provider, model, anthropic_model, env_var, max_tokens) in expected.items():
            self.assertIn(task, models)
            self.assertEqual(models[task]["provider"], provider)
            self.assertEqual(models[task]["model"], model)
            self.assertEqual(models[task]["provider_models"]["anthropic"], anthropic_model)
            self.assertEqual(models[task]["env_var"], env_var)
            self.assertEqual(models[task]["max_tokens"], max_tokens)
            self.assertTrue(models[task]["prompt_files"])
        self.assertTrue(set(expected).issubset(models))
        self.assertTrue({"reel_candidate_analysis", "reel_story_structure", "reel_script_writing", "reel_shot_planning", "reel_motion_canvas_batch", "reel_motion_canvas_repair"}.issubset(models))

        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(model_config_for_task("script_structure").provider, "gemini")
        with patch.dict("os.environ", {"MAV_MODEL_PROVIDER": "anthropic"}, clear=True):
            resolved = model_config_for_task("script_writing")
            self.assertEqual(resolved.provider, "anthropic")
            self.assertEqual(resolved.model, "claude-opus-4-8")
        with patch.dict("os.environ", {}, clear=True):
            resolved = model_config_for_task("v3_creative_director")
            self.assertEqual(resolved.provider, "zai")
            self.assertEqual(resolved.model, "glm-5.2")

    def test_use_gemini_keeps_v3_task_specific_providers(self) -> None:
        from mav_generate import _configure_model_provider

        args = Namespace(
            model_provider="configured",
            use_gemini=True,
            use_claude=False,
        )
        with patch.dict("os.environ", {}, clear=True):
            provider = _configure_model_provider(args)
            self.assertEqual(provider, "gemini")
            self.assertEqual(os.environ["MAV_MODEL_PROVIDER"], "gemini")
            self.assertEqual(os.environ["MAV_V3_CREATIVE_DIRECTOR_PROVIDER"], "zai")
            self.assertEqual(os.environ["MAV_V3_SCENE_CODER_PROVIDER"], "moonshot")

    def test_v3_html_repair_scopes_css_and_removes_shell_wrappers(self) -> None:
        from mav_validate_v3 import normalize_scene_html_for_shell

        html, actions = normalize_scene_html_for_shell(
            """
            <div class="v3-scene-content">
              <div id="b01_card" class="card">Text</div>
            </div>
            <style>
              .camera { transform: scale(2); }
              #b01_card, .card { color: var(--paper); }
            </style>
            """,
            "scene_09",
        )
        self.assertIn("removed redundant v3-scene-content wrapper", actions)
        self.assertIn('data-scene-id="scene_09"] #b01_card', html)
        self.assertIn('data-scene-id="scene_09"] .card', html)
        self.assertNotIn(".camera", html)

    def test_v3_validation_rejects_undefined_css_variables(self) -> None:
        from mav_validate_v3 import validate_scene_html

        violations = validate_scene_html("<div></div><style>#x { color: var(--font-headline); }</style>", "scene_01")
        self.assertTrue(any(violation.code == "UNDEFINED_CSS_VARIABLE" for violation in violations))

    def test_cost_ledger_summarizes_priced_model_usage(self) -> None:
        from mav_costs import cost_summary_for_run, record_audio_usage, record_model_usage
        from mav_schema import run_dir

        run_id = "cost-ledger-test"
        path = run_dir(run_id)
        if path.exists():
            shutil.rmtree(path)
        pricing = {
            "models": {
                "gemini:gemini-test": {
                    "input_usd_per_million": 1.0,
                    "cached_input_usd_per_million": 0.25,
                    "output_usd_per_million": 2.0,
                }
            }
        }
        try:
            with patch.dict(
                os.environ,
                {
                    "MAV_RUN_ID": run_id,
                    "MAV_MODEL_PRICING_JSON": json.dumps(pricing),
                },
                clear=True,
            ):
                record_model_usage(
                    task="script_writing",
                    provider="gemini",
                    model="gemini-test",
                    usage={
                        "prompt_token_count": 1000,
                        "cached_content_token_count": 200,
                        "candidates_token_count": 500,
                    },
                    response_id="test-response",
                )
                record_audio_usage(
                    provider="gemini",
                    model="gemini-tts-test",
                    voice_id="Kore",
                    text="cached narration",
                    cache_reused=True,
                )
            summary = cost_summary_for_run(path)
            self.assertIsNotNone(summary)
            assert summary is not None
            self.assertEqual(summary["priced_records"], 2)
            self.assertEqual(summary["unpriced_records"], 0)
            self.assertAlmostEqual(summary["estimated_cost_usd"], 0.00185)
            self.assertEqual(summary["by_task"]["script_writing"]["calls"], 1)
            self.assertEqual(summary["by_task"]["audio_generation"]["estimated_cost_usd"], 0.0)
        finally:
            if path.exists():
                shutil.rmtree(path)

if __name__ == "__main__":
    unittest.main()
