from __future__ import annotations

import sys
import tempfile
import unittest
import wave
import math
import struct
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from mav_audio import _assemble_wav, _chapter_texts, _write_silence, generate_audio


class ChapterAudioTest(unittest.TestCase):
    def test_narration_paragraphs_are_audio_chapters(self) -> None:
        chapters = _chapter_texts({"paragraphs": [
            {"id": "paragraph_01", "text": "[curious] Measure carefully."},
            {"id": "paragraph_02", "text": "Compare the results."},
        ]})
        self.assertEqual(chapters, [("paragraph_01", "Measure carefully."), ("paragraph_02", "Compare the results.")])

    def test_lossless_assembly_includes_boundary_pause(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first, pause, second, output = (root / name for name in ("first.wav", "pause.wav", "second.wav", "output.wav"))
            _write_silence(first, .1)
            _write_silence(pause, .35)
            _write_silence(second, .2)
            _assemble_wav([first, pause, second], output)
            with wave.open(str(output), "rb") as audio:
                self.assertAlmostEqual(audio.getnframes() / audio.getframerate(), .65, places=3)

    @mock.patch("mav_audio._call_gemini_tts")
    def test_generation_calls_tts_once_per_chapter(self, call_tts: mock.Mock) -> None:
        call_tts.return_value = b"".join(struct.pack("<h", round(6000 * math.sin(2 * math.pi * 220 * i / 24000))) for i in range(24000))
        narration = {
            "elevenlabs_narration": "First chapter. Second chapter.",
            "paragraphs": [
                {"id": "paragraph_01", "text": "First chapter."},
                {"id": "paragraph_02", "text": "Second chapter."},
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            report = generate_audio(Path(temporary), narration, target_duration=3, audio_provider="gemini")
            self.assertEqual(call_tts.call_count, 2)
            self.assertEqual(report["strategy"], "chapter_tts")
            self.assertEqual(len(report["chunks"]), 2)
            self.assertTrue((Path(temporary) / "voiceover.mp3").exists())


if __name__ == "__main__":
    unittest.main()
