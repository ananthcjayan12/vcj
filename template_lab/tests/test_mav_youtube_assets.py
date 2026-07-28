from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import mav_youtube_assets


class MavYoutubeAssetsTest(unittest.TestCase):
    def test_only_cinematic_reference_pair_is_used_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            reference_root = Path(temporary_directory)
            for name in ("reference-01.png", "reference-04.png", "reference-05.png"):
                (reference_root / name).write_bytes(b"reference")

            with (
                patch.object(mav_youtube_assets, "THUMBNAIL_REFERENCE_ROOT", reference_root),
                patch.dict(os.environ, {}, clear=True),
            ):
                references = mav_youtube_assets._thumbnail_references()

        self.assertEqual(
            [path.name for path in references],
            ["reference-04.png", "reference-05.png"],
        )

    def test_reference_override_requires_exactly_two_images(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            reference_root = Path(temporary_directory)
            (reference_root / "reference-04.png").write_bytes(b"reference")

            with (
                patch.object(mav_youtube_assets, "THUMBNAIL_REFERENCE_ROOT", reference_root),
                patch.dict(
                    os.environ,
                    {"MAV_YOUTUBE_THUMBNAIL_REFERENCES": "reference-04.png"},
                    clear=True,
                ),
                self.assertRaisesRegex(RuntimeError, "exactly two"),
            ):
                mav_youtube_assets._thumbnail_references()

    def test_prompt_demands_reference_style_and_exact_ai_typography(self) -> None:
        prompt = mav_youtube_assets._thumbnail_prompt(
            "A pendulum swings from its highest point into a fast central pass.",
            "WHERE DID IT GO?",
            "GPE TO KE",
        )

        self.assertIn("Image 1 and Image 2 are the only approved visual references", prompt)
        self.assertIn('Primary headline: "WHERE DID IT GO?"', prompt)
        self.assertIn('Supporting line: "GPE TO KE"', prompt)
        self.assertIn('Small subject label: "IGCSE PHYSICS"', prompt)
        self.assertIn("Render those three text elements exactly, letter-for-letter", prompt)
        self.assertIn("Avoid a flat classroom slide", prompt)
        self.assertNotIn("white and electric-cyan word blocks", prompt)

    def test_clean_model_text_repairs_mojibake_and_invisible_characters(self) -> None:
        broken = (
            "Energy â€” transfer â€¢ Ek = Â½mvÂ²; Î”Ep = mgÎ”h; "
            "ðŸ§  challenge; 1ï¸\x8fâƒ£ question\u200b; ðŸ§ truncated"
        )

        cleaned = mav_youtube_assets._clean_model_text(broken)

        self.assertEqual(
            cleaned,
            "Energy — transfer • Ek = ½mv²; ΔEp = mgΔh; 🧠 challenge; 1️⃣ question; 🧠 truncated",
        )

    def test_clean_model_text_preserves_valid_unicode(self) -> None:
        valid = "Energy — transfer • Ek = ½mv²; ΔEp = mgΔh; 🧠 challenge"
        self.assertEqual(mav_youtube_assets._clean_model_text(valid), valid)

    def test_copy_pack_is_utf8_marked_and_includes_ascii_fallback(self) -> None:
        metadata = {
            "video_title": "Energy — Explained",
            "alternative_titles": {"search_led": "Energy • Search", "curiosity_led": "Where’s it going?"},
            "description": "Use Ek = ½mv² and ΔEp = mgΔh. 🧠",
            "tags": ["energy transfer"],
            "hashtags": ["#IGCSEPhysics"],
            "pinned_comment": "⚡ Try it 1️⃣",
            "chapters": [{"timestamp": "00:00", "title": "Energy — opening"}],
            "filename": "energy.mp4",
            "playlist_placement": ["Physics — Course"],
            "upload_settings": ["Audience: it’s not made for kids"],
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_root = Path(temporary_directory)
            mav_youtube_assets._write_copy_pack(output_root, metadata)

            unicode_bytes = (output_root / "copy-paste.txt").read_bytes()
            ascii_text = (output_root / "copy-paste-ascii.txt").read_text(encoding="utf-8-sig")

        self.assertTrue(unicode_bytes.startswith(b"\xef\xbb\xbf"))
        self.assertIn("Energy — Explained", unicode_bytes.decode("utf-8-sig"))
        self.assertTrue(ascii_text.isascii())
        self.assertIn("Energy - Explained", ascii_text)
        self.assertIn("Ek = 1/2mv^2", ascii_text)


if __name__ == "__main__":
    unittest.main()
