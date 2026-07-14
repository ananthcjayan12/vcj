from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from mav_audio import resolve_audio_provider


class MavAudioProviderTest(unittest.TestCase):
    def test_audio_provider_defaults_to_gemini(self) -> None:
        self.assertEqual(resolve_audio_provider(), "gemini")

    def test_audio_provider_shortcuts(self) -> None:
        self.assertEqual(resolve_audio_provider(use_gemini_tts=True), "gemini")
        self.assertEqual(resolve_audio_provider(use_elevenlabs=True), "elevenlabs")

    def test_audio_provider_conflicts_fail(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "Choose only one live audio shortcut"):
            resolve_audio_provider(use_gemini_tts=True, use_elevenlabs=True)
        with self.assertRaisesRegex(RuntimeError, "conflicts"):
            resolve_audio_provider(audio_provider="elevenlabs", use_gemini_tts=True)
        with self.assertRaisesRegex(RuntimeError, "Unsupported audio provider"):
            resolve_audio_provider(audio_provider="silent")


if __name__ == "__main__":
    unittest.main()
