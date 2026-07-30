from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.request
from unittest.mock import patch

from pathlib import Path

from studio.server import _artifact_snapshot, _finish_external_render, _infer_step, _normalized_meta, _parse_byte_range, _require_run_id, approve_motion_lesson_review, build_generation_command, build_server, dashboard_payload, delete_run, enqueue_render_runs, model_map_payload, regenerate_motion_chapter, reset_run_from_step, start_motion_lesson_review, topic_detail, update_run_models
from studio.server import ANTIGRAVITY_MODELS


class StudioPayloadTest(unittest.TestCase):
    def test_corrected_lesson_review_can_be_manually_approved(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch("studio.server.RUNS_ROOT", Path(directory)):
            run_path = Path(directory) / "approval-test"
            corrected = run_path / "motion_canvas" / "lesson-review" / "corrected-evidence" / "contact-sheet-01.png"
            corrected.parent.mkdir(parents=True)
            corrected.write_bytes(b"png")
            report_path = run_path / "motion_canvas" / "lesson-review.json"
            report_path.write_text(json.dumps({
                "status": "repaired_pending_review",
                "corrected_contact_sheets": ["motion_canvas/lesson-review/corrected-evidence/contact-sheet-01.png"],
            }))
            (run_path / "motion_canvas" / "robot-report.json").write_text('{"status":"passed"}')
            (run_path / "studio.log").write_text("")
            report = approve_motion_lesson_review("approval-test")
            self.assertEqual(report["status"], "approved")
            robot = json.loads((run_path / "motion_canvas" / "robot-report.json").read_text())
            self.assertEqual(robot["lesson_review_status"], "approved")

    def test_multiple_ready_runs_are_added_to_render_queue_in_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch(
            "studio.server.RENDER_QUEUE_PATH", Path(directory) / "render_queue.json"
        ), patch(
            "studio.server._load_meta",
            side_effect=lambda run_id: {"id": run_id, "topic": f"Topic {run_id}", "current_step": 7},
        ), patch("studio.server._ensure_render_queue_worker"):
            queue = enqueue_render_runs(
                ["physics-1-1-v01", "physics-1-2-v01", "physics-1-1-v01"],
                {"quality": "high", "fps": 30, "workers": 1},
            )
        self.assertEqual([item["run_id"] for item in queue["entries"]], ["physics-1-1-v01", "physics-1-2-v01"])
        self.assertTrue(all(item["status"] == "queued" for item in queue["entries"]))
        self.assertTrue(all(item["settings"]["force"] is False for item in queue["entries"]))

    def test_force_render_setting_is_saved_for_selected_runs(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch(
            "studio.server.RENDER_QUEUE_PATH", Path(directory) / "render_queue.json"
        ), patch(
            "studio.server._load_meta",
            return_value={"id": "physics-1-7-1-v01", "topic": "Energy", "current_step": 7},
        ), patch("studio.server._ensure_render_queue_worker"):
            queue = enqueue_render_runs(
                ["physics-1-7-1-v01"],
                {"quality": "high", "fps": 30, "workers": 1, "force": True},
            )
        self.assertTrue(queue["entries"][0]["settings"]["force"])

    def test_stopped_external_render_is_paused_instead_of_requeued(self) -> None:
        updates = {}
        with tempfile.TemporaryDirectory() as directory, patch(
            "studio.server.RUNS_ROOT", Path(directory)
        ), patch(
            "studio.server._pid_is_alive", return_value=False
        ), patch(
            "studio.server._load_meta", return_value={"id": "physics-1-7-2-v01", "status": "stopped"}
        ), patch(
            "studio.server._read_render_queue",
            return_value={"version": 1, "entries": [{"id": "entry", "report_mtime_before": 0}]},
        ), patch(
            "studio.server._set_queue_entry",
            side_effect=lambda _entry_id, **values: updates.update(values),
        ), patch("studio.server._ensure_render_queue_worker"):
            run_path = Path(directory) / "physics-1-7-2-v01"
            run_path.mkdir()
            _finish_external_render("entry", "physics-1-7-2-v01", 12345)
        self.assertEqual(updates["status"], "paused")
        self.assertEqual(updates["error"], "Stopped by user; requeue to resume")

    def test_byte_ranges_support_open_ended_and_suffix_requests(self) -> None:
        self.assertEqual(_parse_byte_range("bytes=10-19", 100), (10, 19))
        self.assertEqual(_parse_byte_range("bytes=90-", 100), (90, 99))
        self.assertEqual(_parse_byte_range("bytes=-10", 100), (90, 99))
        with self.assertRaises(ValueError):
            _parse_byte_range("bytes=100-", 100)

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
        with self.assertRaises(PermissionError):
            build_generation_command(meta, {"from_step": 6, "stop_after_step": 8})
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
        self.assertEqual(tasks, {"script_structure", "script_writing", "audio_generation", "motion_canvas_batch", "motion_canvas_repair", "motion_canvas_lesson_screen"})

    def test_subscription_clis_are_available_for_both_script_phases(self) -> None:
        catalog = {item["task"]: item for item in model_map_payload()["tasks"]}
        for task in ("script_structure", "script_writing"):
            self.assertEqual(catalog[task]["provider_models"]["antigravity"], "authenticated-default")
            self.assertEqual(
                catalog[task]["provider_model_options"]["antigravity"],
                list(ANTIGRAVITY_MODELS),
            )
            self.assertEqual(
                catalog[task]["provider_model_options"]["copilot"],
                [
                    "claude-sonnet-4.6", "claude-haiku-4.5",
                    "claude-sonnet-5", "claude-opus-5",
                ],
            )

    def test_antigravity_and_copilot_script_overrides_reach_generation_environment(self) -> None:
        meta = {
            "id": "physics-1-1-cli-script-test",
            "facts_path": "video_engine/topics/1.1/facts.json",
            "settings": {
                "duration": 480,
                "model_provider": "configured",
                "audio_provider": "gemini",
                "task_models": {
                    "script_structure": {
                        "provider": "antigravity",
                        "model": "claude-opus-4-6-thinking",
                    },
                    "script_writing": {
                        "provider": "copilot",
                        "model": "claude-sonnet-4.6",
                    },
                },
            },
        }
        _command, env = build_generation_command(
            meta, {"from_step": 2, "stop_after_step": 2, "confirm_paid_api": True},
        )
        self.assertEqual(env["MAV_SCRIPT_STRUCTURE_PROVIDER"], "antigravity")
        self.assertEqual(env["MAV_SCRIPT_STRUCTURE_MODEL"], "claude-opus-4-6-thinking")
        self.assertNotIn("MAV_SCRIPT_STRUCTURE_REASONING_EFFORT", env)
        self.assertEqual(env["MAV_SCRIPT_WRITING_PROVIDER"], "copilot")
        self.assertEqual(env["MAV_SCRIPT_WRITING_MODEL"], "claude-sonnet-4.6")

    def test_kimi_visual_review_uses_latest_multimodal_model(self) -> None:
        task = next(item for item in model_map_payload()["tasks"] if item["task"] == "motion_canvas_lesson_screen")
        self.assertEqual(task["provider_models"]["moonshot"], "kimi-k3")
        self.assertEqual(task["provider_model_options"]["moonshot"], ["kimi-k3", "kimi-k2.7-code", "kimi-k2.7-code-highspeed", "kimi-k2.6"])

    def test_compile_qa_disables_optional_multimodal_review(self) -> None:
        meta = {"id": "physics-1-1-command-test", "facts_path": "video_engine/topics/1.1/facts.json", "settings": {"duration": 480, "model_provider": "gemini", "audio_provider": "gemini"}}
        _command, env = build_generation_command(meta, {"from_step": 1, "stop_after_step": 1, "confirm_paid_api": True})
        self.assertEqual(env["MAV_MOTION_CANVAS_LESSON_REVIEW"], "0")

    def test_optional_visual_review_uses_selected_screening_model(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch("studio.server.RUNS_ROOT", Path(directory)):
            run_path = Path(directory) / "review-run"
            (run_path / "motion_canvas").mkdir(parents=True)
            (run_path / "motion_canvas" / "robot-report.json").write_text('{"status":"passed"}')
            (run_path / "studio_run.json").write_text(json.dumps({"id": "review-run", "current_step": 6, "settings": {}}))
            (run_path / "studio.log").write_text("")
            with patch("studio.server._start_process", return_value={"status": "running"}) as start:
                start_motion_lesson_review("review-run", {
                    "confirm_paid_api": True,
                    "auto_repair": False,
                    "task_models": {"motion_canvas_lesson_screen": {"provider": "gemini", "model": "gemini-2.5-pro"}},
                })
            command, env = start.call_args.args[1:3]
            self.assertIn("--screen-only", command)
            self.assertEqual(env["MAV_MOTION_CANVAS_LESSON_SCREEN_MODEL"], "gemini-2.5-pro")

    def test_codex_cli_model_can_be_selected_for_motion_canvas_only(self) -> None:
        meta = {"id": "physics-1-1-command-test", "facts_path": "video_engine/topics/1.1/facts.json", "settings": {"duration": 480, "model_provider": "gemini", "audio_provider": "gemini", "scene_concurrency": 4, "task_models": {"motion_canvas_batch": {"provider": "codex", "model": "gpt-5.6-sol", "reasoning_effort": "high"}}}}
        _command, env = build_generation_command(meta, {"from_step": 5, "stop_after_step": 5, "confirm_paid_api": True})
        self.assertEqual(env["MAV_MOTION_CANVAS_BATCH_PROVIDER"], "codex")
        self.assertEqual(env["MAV_MOTION_CANVAS_BATCH_MODEL"], "gpt-5.6-sol")
        self.assertEqual(env["MAV_MOTION_CANVAS_BATCH_REASONING_EFFORT"], "high")
        self.assertEqual(env["MAV_MOTION_CANVAS_WORKERS"], "2")

    def test_supergrok_cli_model_can_be_selected_for_motion_canvas(self) -> None:
        meta = {"id": "physics-1-1-grok-test", "facts_path": "video_engine/topics/1.1/facts.json", "settings": {"duration": 480, "model_provider": "gemini", "audio_provider": "gemini", "scene_concurrency": 4, "task_models": {"motion_canvas_batch": {"provider": "grok", "model": "grok-4.5", "reasoning_effort": "high"}, "motion_canvas_repair": {"provider": "grok", "model": "grok-4.5", "reasoning_effort": "high"}}}}
        _command, env = build_generation_command(meta, {"from_step": 5, "stop_after_step": 5, "confirm_paid_api": True})
        self.assertEqual(env["MAV_MOTION_CANVAS_BATCH_PROVIDER"], "grok")
        self.assertEqual(env["MAV_MOTION_CANVAS_BATCH_MODEL"], "grok-4.5")
        self.assertEqual(env["MAV_MOTION_CANVAS_BATCH_REASONING_EFFORT"], "high")
        self.assertEqual(env["MAV_MOTION_CANVAS_WORKERS"], "1")

    def test_targeted_motion_chapter_command_preserves_the_rest_of_the_run(self) -> None:
        meta = {
            "id": "physics-1-1-command-test",
            "facts_path": "video_engine/topics/1.1/facts.json",
            "settings": {
                "duration": 480,
                "model_provider": "configured",
                "audio_provider": "gemini",
                "scene_concurrency": 2,
                "task_models": {
                    "motion_canvas_batch": {
                        "provider": "codex",
                        "model": "gpt-5.6-sol",
                        "reasoning_effort": "medium",
                    }
                },
            },
        }
        command, env = build_generation_command(
            meta,
            {
                "from_step": 5,
                "stop_after_step": 6,
                "confirm_paid_api": True,
                "force_paid_api": True,
                "target_motion_chapter_id": "chapter_03",
                "custom_instruction": "Use a clearer force diagram.",
            },
        )
        self.assertIn("--motion-chapter-id", command)
        self.assertEqual(command[command.index("--motion-chapter-id") + 1], "chapter_03")
        self.assertIn("--force-paid-api", command)
        self.assertEqual(env["MAV_MOTION_CHAPTER_REGEN_INSTRUCTION"], "Use a clearer force diagram.")

    def test_motion_chapter_snapshot_exposes_cached_audio_and_source_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch("studio.server.RUNS_ROOT", Path(directory)):
            run_path = Path(directory) / "chapter-preview-test"
            (run_path / "motion_canvas" / "chapters").mkdir(parents=True)
            (run_path / "audio_chunks" / "paragraph_01").mkdir(parents=True)
            (run_path / "motion_canvas" / "manifest.json").write_text(
                json.dumps(
                    {
                        "chapters": [
                            {
                                "id": "paragraph_01",
                                "scene_id": "chapter_01",
                                "absolute_start": 0,
                                "absolute_end": 12.5,
                                "duration": 12.5,
                            }
                        ],
                        "batches": [{"id": "batch_01", "chapter_ids": ["chapter_01"], "status": "generated"}],
                    }
                )
            )
            (run_path / "motion_canvas" / "chapters" / "chapter_01.tsx").write_text("// chapter")
            (run_path / "audio_chunks" / "paragraph_01" / "audio.wav").write_bytes(b"audio")
            (run_path / "audio_chunks" / "manifest.json").write_text(
                json.dumps(
                    {
                        "chapters": [
                            {
                                "id": "paragraph_01",
                                "path": "audio_chunks/paragraph_01/audio.wav",
                                "quality": {"status": "passed"},
                            }
                        ]
                    }
                )
            )
            chapter = _artifact_snapshot("chapter-preview-test")["chapters"][0]
            self.assertTrue(chapter["source_ready"])
            self.assertEqual(chapter["audio_quality"]["status"], "passed")
            self.assertEqual(
                chapter["audio_url"],
                "/artifacts/runs/chapter-preview-test/audio_chunks/paragraph_01/audio.wav",
            )

    def test_beat_regeneration_targets_parent_reel_with_fixed_context(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch("studio.server.RUNS_ROOT", Path(directory)):
            run_path = Path(directory) / "beat-edit-test"
            (run_path / "motion_canvas").mkdir(parents=True)
            (run_path / "motion_canvas" / "manifest.json").write_text(json.dumps({
                "timeline_mode": "immutable_reels",
                "reels": [{"scene_id": "reel_002"}],
                "beats": [{
                    "beat_id": "beat_006", "reel_id": "reel_002",
                    "local_start": 8.25, "local_end": 17.5,
                    "narration": "The force now increases.",
                }],
            }))
            captured = {}

            def fake_command(_meta, request):
                captured.update(request)
                return ["python", "fake"], {}

            with patch("studio.server._load_meta", return_value={"id": "beat-edit-test"}), patch(
                "studio.server.build_generation_command", side_effect=fake_command
            ), patch("studio.server._start_process", return_value={"status": "running"}), patch("studio.server._append_log"):
                regenerate_motion_chapter(
                    "beat-edit-test", "beat_006",
                    {"confirm_paid_api": True, "custom_instruction": "Clarify the arrow."},
                )
            self.assertEqual(captured["target_motion_chapter_id"], "reel_002")
            self.assertIn("8.250s to 17.500s", captured["custom_instruction"])
            self.assertIn("Preserve the visual state", captured["custom_instruction"])

    def test_mid_run_model_change_is_persisted_for_next_execution(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch("studio.server.RUNS_ROOT", Path(directory)):
            run_path = Path(directory) / "model-change-test"
            run_path.mkdir()
            (run_path / "studio_run.json").write_text(json.dumps({"id": "model-change-test", "facts_path": "video_engine/topics/1.1/facts.json", "status": "paused", "current_step": 4, "settings": {"task_models": {"motion_canvas_batch": {"provider": "moonshot", "model": "kimi-k2.7-code"}}}}))
            result = update_run_models("model-change-test", {"task_models": {"motion_canvas_batch": {"provider": "codex", "model": "gpt-5.6-sol"}}})
            self.assertEqual(result["settings"]["task_models"]["motion_canvas_batch"], {"provider": "codex", "model": "gpt-5.6-sol", "reasoning_effort": "low"})

    def test_codex_can_drive_both_script_phases_with_reasoning(self) -> None:
        meta = {"id": "physics-1-1-command-test", "facts_path": "video_engine/topics/1.1/facts.json", "settings": {"duration": 480, "model_provider": "codex", "audio_provider": "gemini", "task_models": {"script_structure": {"provider": "codex", "model": "gpt-5.6-sol", "reasoning_effort": "medium"}, "script_writing": {"provider": "codex", "model": "gpt-5.6-sol", "reasoning_effort": "high"}}}}
        _command, env = build_generation_command(meta, {"from_step": 2, "stop_after_step": 2, "confirm_paid_api": True})
        self.assertEqual(env["MAV_SCRIPT_STRUCTURE_PROVIDER"], "codex")
        self.assertEqual(env["MAV_SCRIPT_STRUCTURE_REASONING_EFFORT"], "medium")
        self.assertEqual(env["MAV_SCRIPT_WRITING_REASONING_EFFORT"], "high")

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

    def test_validation_contact_sheet_stays_at_step_six(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_path = Path(directory)
            preview = run_path / "motion_canvas" / "preview"
            preview.mkdir(parents=True)
            (run_path / "motion_canvas" / "robot-report.json").write_text("{}")
            (preview / "contact-sheet.png").write_bytes(b"image")
            self.assertEqual(_infer_step(run_path), 6)

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
            self.assertEqual(normalized["content_product"], "full-lesson")
            self.assertEqual(normalized["settings"]["content_product"], "full-lesson")
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
        self.assertEqual(len(payload["tasks"]), 6)

    def test_static_application(self) -> None:
        with urllib.request.urlopen(f"{self.base}/", timeout=5) as response:
            html = response.read().decode("utf-8")
        self.assertIn("MAV Physics Studio", html)
        self.assertIn("Production workspace", html)
        self.assertNotIn("Scene library", html)
        self.assertIn("Motion Canvas", html)

    def test_static_files_support_http_byte_ranges(self) -> None:
        request = urllib.request.Request(f"{self.base}/", headers={"Range": "bytes=0-15"})
        with urllib.request.urlopen(request, timeout=5) as response:
            data = response.read()
            self.assertEqual(response.status, 206)
            self.assertEqual(response.headers["Accept-Ranges"], "bytes")
            self.assertTrue(response.headers["Content-Range"].startswith("bytes 0-15/"))
        self.assertEqual(len(data), 16)

    def test_scene_library_is_served_from_repo(self) -> None:
        with urllib.request.urlopen(f"{self.base}/scene-library/", timeout=5) as response:
            html = response.read().decode("utf-8")
        self.assertIn("MAV Physics — Scene Engine", html)


if __name__ == "__main__":
    unittest.main()
