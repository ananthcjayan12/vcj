from __future__ import annotations

import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import mav_youtube_reel_assets


def _metadata() -> dict:
    return {
        "video_title": "Why Does the Arrow Change? #Shorts",
        "alternative_titles": {
            "search_led": "IGCSE Physics Vector Resultants",
            "curiosity_led": "Can Two Forces Become One?",
        },
        "description": "A compact grounded description.\n\n#IGCSEPhysics #Vectors #Shorts",
        "tags": ["IGCSE Physics", "vectors"],
        "hashtags": ["IGCSEPhysics", "Vectors", "Shorts"],
        "pinned_comment": "What direction is the resultant? Explain why.",
        "chapters": [{"timestamp": "00:00", "title": "Vector resultant"}],
        "filename": "vector-resultant-short.mp4",
        "playlist_placement": ["IGCSE Physics Shorts"],
        "upload_settings": ["Audience: Not made for kids"],
        "thumbnail": {
            "overlay_text": "ONE FORCE?",
            "supporting_text": "Vector Resultants",
            "visual_prompt": "Two force arrows combine into one clear resultant.",
            "alt_text": "Two force arrows and their resultant.",
        },
    }


class MavYoutubeReelAssetsTest(unittest.TestCase):
    def test_builds_valid_short_timeline_from_timed_beats(self) -> None:
        chapters = mav_youtube_reel_assets._reel_timeline(
            {
                "working_title": "Measure Tiny Distances",
                "audio_duration_seconds": 42,
                "timed_beats": [
                    {"id": "hook", "start": 0},
                    {"id": "prediction_prompt", "start": 6},
                    {"id": "method_intro", "start": 12},
                    {"id": "calculation", "start": 25},
                    {"id": "resolve", "start": 34},
                ],
            }
        )

        self.assertEqual(
            chapters,
            [
                {"timestamp": "00:00", "title": "Measure Tiny Distances"},
                {"timestamp": "00:12", "title": "The method"},
                {"timestamp": "00:25", "title": "Calculate the answer"},
            ],
        )
    def test_generates_independent_asset_pack_for_rendered_reel(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory) / "test-pack"
            (run / "motion_canvas" / "renders").mkdir(parents=True)
            (run / "motion_canvas" / "renders" / "reel_001.mp4").write_bytes(b"video")
            (run / "reel_pack.json").write_text(
                json.dumps({
                    "topic": "Vectors",
                    "reels": [{
                        "reel_id": "reel_001",
                        "status": "rendered",
                        "hook": "Can two forces become one?",
                        "learning_payoff": "Resolve a right-angle resultant.",
                    }],
                }),
                encoding="utf-8",
            )
            (run / "narration.json").write_text(
                json.dumps({"paragraphs": [{"id": "reel_001", "text": "Two forces combine."}]}),
                encoding="utf-8",
            )
            (run / "publishing_manifest.json").write_text(
                json.dumps({"reels": [{"reel_id": "reel_001"}]}),
                encoding="utf-8",
            )
            metadata_call = Mock(return_value=_metadata())
            thumbnail_call = Mock(return_value=(b"image", "image/png", "image-model", ["a.png", "b.png"]))
            embed_cover = Mock(
                side_effect=lambda _source, _cover, target: (
                    target.write_bytes(b"youtube-video"),
                    41.5,
                )[1]
            )

            with (
                patch.object(mav_youtube_reel_assets, "run_dir", return_value=run),
                patch.object(
                    mav_youtube_reel_assets,
                    "model_config_for_task",
                    return_value=SimpleNamespace(provider="gemini", model="gemini-test"),
                ),
                patch.object(
                    mav_youtube_reel_assets,
                    "_normalize_thumbnail",
                    side_effect=lambda _data, target, **_kwargs: (
                        target.parent.mkdir(parents=True, exist_ok=True),
                        target.write_bytes(b"jpg"),
                    ),
                ),
            ):
                output = mav_youtube_reel_assets.generate(
                    "test-pack",
                    metadata_call=metadata_call,
                    thumbnail_call=thumbnail_call,
                    embed_cover=embed_cover,
                )

            reel_root = output / "reel_001"
            self.assertTrue((reel_root / "thumbnail.jpg").is_file())
            self.assertTrue((reel_root / "copy-paste.txt").is_file())
            self.assertTrue((reel_root / "shorts-thumbnail-note.txt").is_file())
            self.assertTrue((reel_root / "youtube-short.mp4").is_file())
            report = json.loads((run / "youtube" / "reel-assets.json").read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "generated")
            self.assertEqual(report["reels"][0]["reel_id"], "reel_001")
            self.assertIn("final one-second frame", report["thumbnail_usage"])
            self.assertEqual(report["reels"][0]["thumbnail_frame_seconds"], 41.5)
            archive = run / report["download_zip"]
            self.assertTrue(archive.is_file())
            with zipfile.ZipFile(archive) as delivery:
                self.assertEqual(
                    sorted(delivery.namelist()),
                    [
                        "youtube-reel-upload-pack/README.txt",
                        "youtube-reel-upload-pack/reel-assets.json",
                        "youtube-reel-upload-pack/reel_001/copy-paste-ascii.txt",
                        "youtube-reel-upload-pack/reel_001/copy-paste.txt",
                        "youtube-reel-upload-pack/reel_001/metadata.json",
                        "youtube-reel-upload-pack/reel_001/shorts-thumbnail-note.txt",
                        "youtube-reel-upload-pack/reel_001/thumbnail.jpg",
                        "youtube-reel-upload-pack/reel_001/youtube-short.mp4",
                    ],
                )
            updated_pack = json.loads((run / "reel_pack.json").read_text(encoding="utf-8"))
            self.assertEqual(updated_pack["current_step"], 9)
            publishing = json.loads((run / "publishing_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(publishing["reels"][0]["youtube"]["status"], "generated")
            metadata_call.assert_called_once()
            thumbnail_call.assert_called_once()
            embed_cover.assert_called_once()

    def test_requires_rendered_mp4_before_paid_generation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory) / "test-pack"
            run.mkdir()
            (run / "reel_pack.json").write_text(
                json.dumps({"reels": [{"reel_id": "reel_001", "status": "approved"}]}),
                encoding="utf-8",
            )
            (run / "narration.json").write_text(
                json.dumps({"paragraphs": [{"id": "reel_001", "text": "Narration"}]}),
                encoding="utf-8",
            )
            metadata_call = Mock()
            with (
                patch.object(mav_youtube_reel_assets, "run_dir", return_value=run),
                self.assertRaisesRegex(RuntimeError, "No rendered Reels"),
            ):
                mav_youtube_reel_assets.generate("test-pack", metadata_call=metadata_call)
            metadata_call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
