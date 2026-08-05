from __future__ import annotations

import argparse
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import mav_youtube_publish


class MavYouTubePublishTest(unittest.TestCase):
    def test_builds_body_with_generated_metadata(self) -> None:
        metadata = {
            "video_title": "Density in 8 Minutes",
            "description": "A complete density lesson.",
            "tags": ["IGCSE Physics", "density"],
            "hashtags": ["#IGCSEPhysics", "Density"],
            "chapters": [
                {"timestamp": "00:00", "title": "What density means"},
                {"timestamp": "02:10", "title": "Worked example"},
            ],
        }

        body = mav_youtube_publish.build_video_body(
            metadata,
            privacy="private",
            publish_at=None,
            made_for_kids=False,
            category_id="27",
        )

        self.assertEqual(body["snippet"]["title"], "Density in 8 Minutes")
        self.assertEqual(body["snippet"]["categoryId"], "27")
        self.assertIn("00:00 What density means", body["snippet"]["description"])
        self.assertIn("#IGCSEPhysics #Density", body["snippet"]["description"])
        self.assertFalse(body["status"]["selfDeclaredMadeForKids"])

    def test_schedule_requires_private_and_is_normalized_to_utc(self) -> None:
        future = datetime.now(timezone.utc) + timedelta(days=2)
        local_time = future.astimezone(timezone(timedelta(hours=5, minutes=30))).isoformat()
        metadata = {"video_title": "Scheduled physics lesson"}

        body = mav_youtube_publish.build_video_body(
            metadata,
            privacy="private",
            publish_at=local_time,
            made_for_kids=False,
            category_id="27",
        )
        self.assertTrue(body["status"]["publishAt"].endswith("Z"))

        with self.assertRaisesRegex(ValueError, "requires --privacy private"):
            mav_youtube_publish.build_video_body(
                metadata,
                privacy="public",
                publish_at=local_time,
                made_for_kids=False,
                category_id="27",
            )

    def test_preserves_tag_order_and_drops_only_overflow(self) -> None:
        tags = ["a" * 300, "b" * 250, "short"]

        with patch("sys.stderr"):
            fitted = mav_youtube_publish._fit_tags(tags)

        self.assertEqual(fitted, ["a" * 300, "short"])
        self.assertLessEqual(len(",".join(fitted)), 500)

    def test_resolves_standard_run_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "motion_canvas").mkdir()
            (root / "youtube").mkdir()
            (root / "motion_canvas" / "final.mp4").write_bytes(b"video")
            (root / "youtube" / "metadata.json").write_text("{}", encoding="utf-8")
            (root / "youtube" / "thumbnail.jpg").write_bytes(b"image")
            args = argparse.Namespace(
                run_id="lesson-1",
                video=None,
                metadata=None,
                thumbnail=None,
            )

            with patch.object(mav_youtube_publish, "run_dir", return_value=root):
                video, metadata, thumbnail = mav_youtube_publish.resolve_assets(args)

            self.assertEqual(video, (root / "motion_canvas" / "final.mp4").resolve())
            self.assertEqual(metadata, (root / "youtube" / "metadata.json").resolve())
            self.assertEqual(thumbnail, (root / "youtube" / "thumbnail.jpg").resolve())

    def test_missing_default_thumbnail_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            video = root / "lesson.mp4"
            metadata = root / "metadata.json"
            video.write_bytes(b"video")
            metadata.write_text("{}", encoding="utf-8")
            args = argparse.Namespace(run_id=None, video=str(video), metadata=str(metadata), thumbnail=None)

            _video, _metadata, thumbnail = mav_youtube_publish.resolve_assets(args)

            self.assertIsNone(thumbnail)

    def test_course_description_replaces_placeholders_with_real_navigation(self) -> None:
        description = (
            "Grounded lesson copy.\n\n"
            "[ADD PLAYLIST LINK]\n[ADD PREVIOUS VIDEO LINK]\n[ADD NEXT VIDEO LINK]\n\n"
            "00:00 Opening\n00:30 Worked example\n01:00 Summary"
        )

        result = mav_youtube_publish._course_description(
            description,
            playlist_url="https://www.youtube.com/playlist?list=PL123",
            previous={"video_id": "prev", "title": "Previous topic"},
            following={"video_id": "next", "title": "Next topic"},
            content_kind="longform",
        )

        self.assertNotIn("[ADD", result)
        self.assertIn("https://youtu.be/prev", result)
        self.assertIn("https://youtu.be/next", result)
        self.assertIn("00:30 Worked example", result)
        self.assertEqual(result.count(mav_youtube_publish.COURSE_LINKS_START), 1)

    def test_course_description_is_idempotent_and_supports_shorts(self) -> None:
        first = mav_youtube_publish._course_description(
            "Short description.\n\n00:00 Puzzle",
            playlist_url="https://www.youtube.com/playlist?list=PL123",
            previous=None,
            following=None,
            content_kind="short",
            full_lesson_video_id="lesson123",
        )
        second = mav_youtube_publish._course_description(
            first,
            playlist_url="https://www.youtube.com/playlist?list=PL123",
            previous={"video_id": "short0", "title": "Earlier Short"},
            following=None,
            content_kind="short",
            full_lesson_video_id="lesson123",
        )

        self.assertEqual(second.count(mav_youtube_publish.COURSE_LINKS_START), 1)
        self.assertIn("Full lesson: https://youtu.be/lesson123", second)
        self.assertEqual(
            mav_youtube_publish._full_lesson_id_from_description(second),
            "lesson123",
        )
        self.assertIn("Previous Short", second)
        self.assertIn("Next Short: coming soon", second)

    def test_infers_matching_full_lesson_for_short_from_topic_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            runs = Path(temporary_directory)
            reel = runs / "physics-2-1-reels-v01"
            lesson = runs / "physics-2-1-v01"
            (reel / "youtube" / "reels" / "reel_001").mkdir(parents=True)
            (lesson / "youtube").mkdir(parents=True)
            (reel / "reel_pack.json").write_text(
                json.dumps({"topic_ref": "2.1"}), encoding="utf-8"
            )
            (lesson / "studio_run.json").write_text(
                json.dumps({"topic_ref": "2.1"}), encoding="utf-8"
            )
            (lesson / "youtube" / "upload-result.json").write_text(
                json.dumps({"status": "uploaded", "video_id": "lesson-video"}),
                encoding="utf-8",
            )
            metadata = reel / "youtube" / "reels" / "reel_001" / "metadata.json"
            metadata.write_text("{}", encoding="utf-8")

            self.assertEqual(
                mav_youtube_publish.infer_full_lesson_video_id(metadata),
                "lesson-video",
            )


if __name__ == "__main__":
    unittest.main()
