from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mav_codex import _binary, _strict_output_schema
from motion_canvas.pipeline import _normalize_chapter_source, _validate_chapter_source, _validate_cue_references


class CodexDiscoveryTest(unittest.TestCase):
    def test_explicit_executable_is_preferred_without_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "codex"
            executable.write_text("#!/bin/sh\n")
            executable.chmod(0o755)
            with patch.dict(os.environ, {"MAV_CODEX_BIN": str(executable), "PATH": ""}, clear=False):
                self.assertEqual(_binary(), str(executable))

    def test_numeric_cue_property_is_normalized_to_valid_typescript(self) -> None:
        source = "const x = CUES.148[0];"
        normalized = _normalize_chapter_source(source)
        self.assertEqual(normalized, 'const x = CUES["148"][0];')

    def test_bare_mapped_keys_receive_scene_unique_prefixes(self) -> None:
        normalized = _normalize_chapter_source("<Rect key={String(index)} /><Circle key={String(index)} />")
        self.assertIn('key={`mapped-0-${String(index)}`}', normalized)
        self.assertIn('key={`mapped-1-${String(index)}`}', normalized)

    def test_numeric_cue_property_is_rejected_if_not_normalized(self) -> None:
        source = "import x from '../../presentation'; import './chapter_11.cues'; makeScene2D(); const x = CUES.148[0];"
        with self.assertRaisesRegex(RuntimeError, "invalid numeric cue access"):
            _validate_chapter_source(source, "chapter_11")

    def test_missing_and_out_of_range_cues_are_rejected_before_compile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cue = root / "chapters" / "chapter_01.cues.ts"
            cue.parent.mkdir()
            cue.write_text('export const CUES = {"word":[1.0]} as const;')
            with self.assertRaisesRegex(RuntimeError, "missing cue"):
                _validate_cue_references(root, "CUES.absent[0]", "chapter_01")
            with self.assertRaisesRegex(RuntimeError, "only 1 occurrence"):
                _validate_cue_references(root, "CUES.word[1]", "chapter_01")

    def test_old_two_column_comparison_contract_is_rejected(self) -> None:
        source = "import x from '../../presentation'; import './chapter_01.cues'; makeScene2D(); <TwoColumnComparison leftTitle={'Mass'} rightTitle={'Weight'} />"
        with self.assertRaisesRegex(RuntimeError, "left/right TextItem"):
            _validate_chapter_source(source, "chapter_01")

    def test_codex_schema_is_strict_at_every_object_level(self) -> None:
        schema = {"type": "object", "properties": {"items": {"type": "array", "items": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}}}, "required": ["items"]}
        strict = _strict_output_schema(schema)
        self.assertFalse(strict["additionalProperties"])
        self.assertFalse(strict["properties"]["items"]["items"]["additionalProperties"])


if __name__ == "__main__":
    unittest.main()
