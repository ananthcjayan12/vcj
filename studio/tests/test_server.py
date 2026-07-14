from __future__ import annotations

import json
import threading
import unittest
import urllib.request

from studio.server import _require_run_id, build_generation_command, build_server, dashboard_payload, topic_detail


class StudioPayloadTest(unittest.TestCase):
    def test_dashboard_exposes_complete_curriculum_and_scene_catalog(self) -> None:
        payload = dashboard_payload()
        self.assertEqual(payload["summary"]["topic_count"], 58)
        self.assertEqual(payload["summary"]["objective_count"], 328)
        self.assertEqual(payload["summary"]["scene_count"], 35)
        self.assertEqual(payload["next_topic"]["ref"], "1.1")

    def test_topic_detail_uses_aggregate_assessment_evidence(self) -> None:
        payload = topic_detail("1.1")
        self.assertEqual(len(payload["objectives"]), 7)
        self.assertGreater(payload["assessment"]["question_count"], 0)
        self.assertIn("command_words", payload["assessment"])
        self.assertNotIn("question_text", json.dumps(payload["assessment"]))

    def test_run_ids_reject_path_traversal_and_uppercase_drift(self) -> None:
        self.assertEqual(_require_run_id("physics-1-1-v01"), "physics-1-1-v01")
        for unsafe in ("../run", "Physics-Run", "/tmp/run", "run id"):
            with self.subTest(unsafe=unsafe), self.assertRaises(ValueError):
                _require_run_id(unsafe)

    def test_generation_command_enforces_paid_boundary(self) -> None:
        meta = {
            "id": "physics-1-1-command-test",
            "facts_path": "video_engine/topics/1.1/facts.json",
            "settings": {"duration": 480, "model_provider": "gemini", "audio_provider": "gemini"},
        }
        with self.assertRaises(PermissionError):
            build_generation_command(meta, {"from_step": 2, "stop_after_step": 2})
        command, _env = build_generation_command(meta, {"from_step": 6, "stop_after_step": 8})
        self.assertNotIn("--confirm-paid-api", command)
        command, _env = build_generation_command(meta, {"from_step": 2, "stop_after_step": 2, "confirm_paid_api": True})
        self.assertIn("--confirm-paid-api", command)


class StudioHttpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = build_server("127.0.0.1", 0, quiet=True)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def test_dashboard_api(self) -> None:
        with urllib.request.urlopen(f"{self.base}/api/dashboard", timeout=5) as response:
            payload = json.load(response)
        self.assertEqual(payload["summary"]["topic_count"], 58)

    def test_static_application(self) -> None:
        with urllib.request.urlopen(f"{self.base}/", timeout=5) as response:
            html = response.read().decode("utf-8")
        self.assertIn("MAV Physics Studio", html)
        self.assertIn("Production workspace", html)

    def test_scene_library_is_served_from_repo(self) -> None:
        with urllib.request.urlopen(f"{self.base}/scene-library/", timeout=5) as response:
            html = response.read().decode("utf-8")
        self.assertIn("MAV Physics — Scene Engine", html)


if __name__ == "__main__":
    unittest.main()
