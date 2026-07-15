from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.request
from unittest.mock import patch

from pathlib import Path

from studio.server import _infer_step, _normalized_meta, _require_run_id, build_generation_command, build_server, dashboard_payload, delete_run, model_map_payload, reset_run_from_step, topic_detail, update_run_models


class StudioPayloadTest(unittest.TestCase):
    def test_dashboard_exposes_complete_curriculum_and_scene_catalog(self) -> None:
        payload = dashboard_payload()
        self.assertEqual(payload["summary"]["topic_count"], 58)
        self.assertEqual(payload["summary"]["objective_count"], 324)
        self.assertEqual(payload["summary"]["scene_count"], 41)
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

    def test_task_model_overrides_are_injected_per_prompt(self) -> None:
        meta = {"id": "physics-1-1-command-test", "facts_path": "video_engine/topics/1.1/facts.json", "settings": {"duration": 480, "model_provider": "gemini", "audio_provider": "gemini", "task_models": {"script_writing": {"provider": "anthropic", "model": "claude-opus-4-8"}}}}
        _command, env = build_generation_command(meta, {"from_step": 2, "stop_after_step": 2, "confirm_paid_api": True})
        self.assertEqual(env["MAV_SCRIPT_WRITING_PROVIDER"], "anthropic")
        self.assertEqual(env["MAV_SCRIPT_WRITING_MODEL"], "claude-opus-4-8")

    def test_script_provider_does_not_override_direct_composer(self) -> None:
        meta = {
            "id": "physics-1-1-command-test",
            "facts_path": "video_engine/topics/1.1/facts.json",
            "settings": {"duration": 480, "model_provider": "anthropic", "audio_provider": "gemini"},
        }
        with patch.dict("os.environ", {}, clear=True):
            command, env = build_generation_command(
                meta,
                {"from_step": 2, "stop_after_step": 5, "confirm_paid_api": True},
            )
        provider_index = command.index("--model-provider")
        self.assertEqual(command[provider_index + 1], "configured")
        self.assertEqual(env["MAV_SCRIPT_STRUCTURE_PROVIDER"], "anthropic")
        self.assertEqual(env["MAV_SCRIPT_WRITING_PROVIDER"], "anthropic")
        self.assertNotIn("MAV_DIRECT_HTML_COMPOSER_PROVIDER", env)

    def test_model_map_covers_all_paid_pipeline_tasks(self) -> None:
        tasks = {item["task"] for item in model_map_payload()["tasks"]}
        self.assertEqual(tasks, {"script_structure", "script_writing", "audio_generation", "motion_canvas_batch"})

    def test_codex_cli_model_can_be_selected_for_motion_canvas_only(self) -> None:
        meta = {"id": "physics-1-1-command-test", "facts_path": "video_engine/topics/1.1/facts.json", "settings": {"duration": 480, "model_provider": "gemini", "audio_provider": "gemini", "scene_concurrency": 4, "task_models": {"motion_canvas_batch": {"provider": "codex", "model": "gpt-5.6-sol"}}}}
        _command, env = build_generation_command(meta, {"from_step": 5, "stop_after_step": 5, "confirm_paid_api": True})
        self.assertEqual(env["MAV_MOTION_CANVAS_BATCH_PROVIDER"], "codex")
        self.assertEqual(env["MAV_MOTION_CANVAS_BATCH_MODEL"], "gpt-5.6-sol")
        self.assertEqual(env["MAV_MOTION_CANVAS_WORKERS"], "2")

    def test_mid_run_model_change_is_persisted_for_next_execution(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch("studio.server.RUNS_ROOT", Path(directory)):
            run_path = Path(directory) / "model-change-test"
            run_path.mkdir()
            (run_path / "studio_run.json").write_text(json.dumps({"id": "model-change-test", "facts_path": "video_engine/topics/1.1/facts.json", "status": "paused", "current_step": 4, "settings": {"task_models": {"motion_canvas_batch": {"provider": "moonshot", "model": "kimi-k2.7-code"}}}}))
            result = update_run_models("model-change-test", {"task_models": {"motion_canvas_batch": {"provider": "codex", "model": "gpt-5.6-sol"}}})
            self.assertEqual(result["settings"]["task_models"]["motion_canvas_batch"], {"provider": "codex", "model": "gpt-5.6-sol"})

    def test_generation_summary_uses_actual_stopped_step(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_path = Path(directory)
            (run_path / "input.json").write_text("{}")
            (run_path / "generation_summary.json").write_text(json.dumps({"stopped_after_step": 2}))
            self.assertEqual(_infer_step(run_path), 2)

    def test_completed_generation_summary_infers_qa_step(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_path = Path(directory)
            (run_path / "motion_canvas").mkdir()
            (run_path / "motion_canvas" / "final.mp4").write_bytes(b"video")
            self.assertEqual(_infer_step(run_path), 8)

    def test_existing_run_metadata_backfills_facts_and_paid_settings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_path = Path(directory)
            (run_path / "input.json").write_text(
                json.dumps(
                    {
                        "topic_ref": "1.1",
                        "topic": "1.1 Physical quantities and measurement techniques",
                        "target_duration_seconds": 300,
                        "animation_mode": "direct-html",
                    }
                )
            )
            normalized = _normalized_meta(run_path, {"id": "old-run", "settings": {}})
            self.assertEqual(normalized["facts_path"], "video_engine/topics/1.1/facts.json")
            self.assertEqual(normalized["settings"]["duration"], 300)
            self.assertEqual(normalized["settings"]["animation_mode"], "motion-canvas")
            self.assertTrue(normalized["settings"]["confirm_paid_api"])

    def test_reset_removes_selected_and_downstream_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch("studio.server.RUNS_ROOT", Path(directory)):
            run_path = Path(directory) / "reset-test"
            (run_path / "motion_canvas" / "preview").mkdir(parents=True)
            (run_path / "input.json").write_text("{}")
            (run_path / "narration.json").write_text("{}")
            (run_path / "voiceover.mp3").write_bytes(b"audio")
            (run_path / "audio_generation.json").write_text("{}")
            (run_path / "audio_timing.json").write_text("{}")
            (run_path / "audio_word_timestamps.json").write_text("{}")
            (run_path / "motion_canvas" / "manifest.json").write_text('{"chapters": [], "batches": []}')
            (run_path / "studio_run.json").write_text(json.dumps({"id": "reset-test", "facts_path": "video_engine/topics/1.1/facts.json", "status": "completed", "current_step": 8, "settings": {}}))
            result = reset_run_from_step("reset-test", 5)
            self.assertFalse((run_path / "motion_canvas").exists())
            self.assertTrue((run_path / "audio_word_timestamps.json").exists())
            self.assertEqual(result["current_step"], 4)
            self.assertTrue(result["settings"]["confirm_paid_api"])

    def test_delete_removes_complete_run_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch("studio.server.RUNS_ROOT", Path(directory)):
            run_path = Path(directory) / "delete-test"
            run_path.mkdir()
            (run_path / "studio_run.json").write_text("{}")
            self.assertEqual(delete_run("delete-test")["status"], "deleted")
            self.assertFalse(run_path.exists())


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

    def test_model_map_api(self) -> None:
        with urllib.request.urlopen(f"{self.base}/api/model-map", timeout=5) as response:
            payload = json.load(response)
        self.assertEqual(len(payload["tasks"]), 4)

    def test_static_application(self) -> None:
        with urllib.request.urlopen(f"{self.base}/", timeout=5) as response:
            html = response.read().decode("utf-8")
        self.assertIn("MAV Physics Studio", html)
        self.assertIn("Production workspace", html)
        self.assertNotIn("Scene library", html)
        self.assertIn("Motion Canvas", html)

    def test_scene_library_is_served_from_repo(self) -> None:
        with urllib.request.urlopen(f"{self.base}/scene-library/", timeout=5) as response:
            html = response.read().decode("utf-8")
        self.assertIn("MAV Physics — Scene Engine", html)


if __name__ == "__main__":
    unittest.main()
