from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from motion_canvas.pipeline import _split_from_audio_manifest, assemble, parse_response, prepare, split_chapters


class MotionCanvasPipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.words = {"audio_duration_seconds": 4.0, "words": [
            {"paragraph_id": "paragraph_01", "word": "move", "start": 0.5, "end": 1.0},
            {"paragraph_id": "paragraph_02", "word": "stop", "start": 2.5, "end": 3.0},
        ]}
        self.narration = {"paragraphs": [{"id": "paragraph_01", "text": "Move."}, {"id": "paragraph_02", "text": "Stop."}]}

    def test_split_is_contiguous_and_local(self) -> None:
        chapters = split_chapters(self.words, self.narration)
        self.assertEqual([item["duration"] for item in chapters], [2.5, 1.5])
        self.assertEqual(chapters[1]["words"][0]["start"], 0.0)
        self.assertEqual(sum(item["duration"] for item in chapters), 4.0)

    def test_strict_markers(self) -> None:
        parsed = parse_response("=== chapter_01.tsx ===\nsource", ["chapter_01"])
        self.assertEqual(parsed["chapter_01.tsx"], "source")
        with self.assertRaises(RuntimeError): parse_response("```tsx\nx\n```", ["chapter_01"])

    def test_prepare_and_assemble(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary); (run / "voiceover.mp3").write_bytes(b"audio")
            import json
            (run / "audio_word_timestamps.json").write_text(json.dumps(self.words))
            manifest = prepare(run, self.narration, batch_size=1)
            self.assertTrue((run / "motion_canvas" / "chapters" / "chapter_01.cues.ts").exists())
            for item in manifest["chapters"]:
                duration = item["duration"]
                source = f"""import {{makeScene2D}} from '@motion-canvas/2d';\nimport {{createSignal, linear}} from '@motion-canvas/core';\nconst CHAPTER_DURATION = {duration};\nexport default makeScene2D(function* () {{ const progress = createSignal(0); yield* progress(1, CHAPTER_DURATION, linear); }});\n"""
                path = run / "motion_canvas" / "chapters" / f"{item['scene_id']}.tsx"; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(source)
            self.assertTrue(assemble(run, manifest).exists())

    def test_parser_rejects_external_import(self) -> None:
        with self.assertRaises(RuntimeError):
            parse_response("=== chapter_01.tsx ===\nimport x from 'https://bad.test/x'", ["chapter_01"])

    def test_audio_manifest_boundaries_are_authoritative(self) -> None:
        words = {"words": [
            {"paragraph_id": "paragraph_01", "word": "move", "start": 0.2, "end": 0.7},
            {"paragraph_id": "paragraph_02", "word": "stop", "start": 2.3, "end": 2.8},
        ]}
        audio = {"chapters": [
            {"id": "paragraph_01", "absolute_start": 0, "absolute_end": 2.1, "speech_duration": 1.75, "trailing_pause": .35},
            {"id": "paragraph_02", "absolute_start": 2.1, "absolute_end": 3.0, "speech_duration": .9, "trailing_pause": 0},
        ]}
        chapters = _split_from_audio_manifest(words, audio)
        self.assertEqual([item["duration"] for item in chapters], [2.1, .9])
        self.assertEqual(chapters[1]["words"][0]["start"], .2)

    def test_generated_scene_requires_presentation_contract(self) -> None:
        source = "import {makeScene2D} from '@motion-canvas/2d'; export default makeScene2D(function*(){});"
        with self.assertRaisesRegex(RuntimeError, "presentation components"):
            parse_response(f"=== chapter_01.tsx ===\n{source}", ["chapter_01"])


if __name__ == "__main__": unittest.main()
