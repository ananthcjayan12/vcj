from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from mav_timing import _extract_whisper_words, _timing_from_whisper_words


class MavTimingWhisperTest(unittest.TestCase):
    def test_extract_whisper_words_normalizes_tokens(self) -> None:
        words = _extract_whisper_words(
            {
                "segments": [
                    {
                        "words": [
                            {"word": "Fuel,", "start": 0.0, "end": 0.2},
                            {"word": "isn't", "start": 0.2, "end": 0.4},
                            {"word": " filler.", "start": 0.4, "end": 0.7},
                        ]
                    }
                ]
            }
        )
        self.assertEqual([item["word"] for item in words], ["fuel", "isn't", "filler"])

    def test_paragraph_timing_uses_whisper_word_boundaries(self) -> None:
        narration = {
            "paragraphs": [
                {"id": "paragraph_01", "text": "Fuel is not filler for AI."},
                {"id": "paragraph_02", "text": "The lawsuit changes the question."},
            ]
        }
        transcript_words = [
            {"word": "fuel", "start": 0.0, "end": 0.2},
            {"word": "is", "start": 0.2, "end": 0.3},
            {"word": "not", "start": 0.3, "end": 0.4},
            {"word": "filler", "start": 0.4, "end": 0.6},
            {"word": "for", "start": 0.6, "end": 0.7},
            {"word": "ai", "start": 0.7, "end": 0.9},
            {"word": "the", "start": 1.2, "end": 1.3},
            {"word": "lawsuit", "start": 1.3, "end": 1.6},
            {"word": "changes", "start": 1.6, "end": 1.9},
            {"word": "the", "start": 1.9, "end": 2.0},
            {"word": "question", "start": 2.0, "end": 2.3},
        ]
        timing = _timing_from_whisper_words(narration, transcript_words, 3.0)
        self.assertEqual([item["id"] for item in timing], ["paragraph_01", "paragraph_02"])
        self.assertEqual(timing[0]["start"], 0.0)
        self.assertEqual(timing[0]["end"], 1.2)
        self.assertEqual(timing[1]["start"], 1.2)
        self.assertEqual(timing[1]["end"], 3.0)
        self.assertGreaterEqual(timing[0]["whisper_match_score"], 0.9)

    def test_empty_whisper_words_fail(self) -> None:
        narration = {"paragraphs": [{"id": "paragraph_01", "text": "Real narration text."}]}
        with self.assertRaisesRegex(RuntimeError, "Whisper produced no word timestamps"):
            _timing_from_whisper_words(narration, [], 2.0)


if __name__ == "__main__":
    unittest.main()
