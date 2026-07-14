from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import mav_models
from mav_models import ResolvedModelConfig, _call_gemini_json, _gemini_compatible_json_schema
from mav_plan_v3 import _parameter_output_schema, _route_output_schema


class GeminiSchemaCompatibilityTest(unittest.TestCase):
    def test_router_schema_drops_large_repeated_enums_but_keeps_small_classifications(self) -> None:
        modules = [f"Scene_{index:02d}" for index in range(35)]
        schema = _gemini_compatible_json_schema(_route_output_schema(["scene_01"], modules))
        route = schema["properties"]["routes"]["items"]["properties"]

        self.assertEqual(route["route"]["enum"], ["module", "custom"])
        self.assertNotIn("enum", route["module"])
        self.assertNotIn("enum", route["alternatives"]["items"])

    def test_parameter_schema_removes_keywords_not_supported_by_gemini(self) -> None:
        source = _parameter_output_schema(
            {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "maxLength": 60, "default": "Physics"},
                },
                "required": ["title"],
                "additionalProperties": False,
            }
        )
        schema = _gemini_compatible_json_schema(source)
        title = schema["properties"]["params"]["properties"]["title"]

        self.assertEqual(title, {"type": "string"})
        self.assertFalse(schema["properties"]["params"]["additionalProperties"])

    def test_invalid_schema_retries_once_without_provider_schema(self) -> None:
        class FakeModels:
            def __init__(self) -> None:
                self.configs = []

            def generate_content(self, *, model, contents, config):  # noqa: ANN001
                self.configs.append(config)
                if len(self.configs) == 1:
                    raise RuntimeError("400 INVALID_ARGUMENT")
                return SimpleNamespace(text='{"routes": []}', candidates=[], usage_metadata=None)

        fake_models = FakeModels()
        fake_client = SimpleNamespace(models=fake_models)
        resolved = ResolvedModelConfig(
            task="scene_asset_router",
            provider="gemini",
            model="gemini-3.1-flash-lite",
            max_tokens=12000,
        )
        schema = {"type": "object", "properties": {"routes": {"type": "array"}}, "required": ["routes"]}

        with (
            patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}),
            patch("google.genai.Client", return_value=fake_client),
            patch.object(mav_models, "record_model_usage"),
        ):
            result = _call_gemini_json(resolved, system="system", user="user", output_schema=schema)

        self.assertEqual(result, {"routes": []})
        self.assertEqual(len(fake_models.configs), 2)
        self.assertIsNotNone(fake_models.configs[0].response_json_schema)
        self.assertIsNone(fake_models.configs[1].response_json_schema)


if __name__ == "__main__":
    unittest.main()
