from __future__ import annotations

import json


def test_studio_extension_creates_additive_reel_pack(tmp_path, monkeypatch):
    import studio.server as server
    import studio.reel_pack_extension as extension
    import template_lab.reel_pack.common as reel_common

    runs_root = tmp_path / "template_lab" / "runs"
    topics_root = tmp_path / "video_engine" / "topics"
    topic_ref = server.TOPIC_ORDER[0]
    facts_path = topics_root / topic_ref / "facts.json"
    facts_path.parent.mkdir(parents=True)
    facts_path.write_text(
        json.dumps(
            {
                "topic": "Test topic",
                "topic_ref": topic_ref,
                "objective_ids": ["O1"],
                "facts": [{"id": "F1", "text": "A grounded test fact."}],
                "physics_context": {"units": "SI"},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(server, "RUNS_ROOT", runs_root)
    monkeypatch.setattr(server, "TOPICS_ROOT", topics_root)
    monkeypatch.setattr(server, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(reel_common, "RUNS_ROOT", runs_root)
    monkeypatch.setattr(
        server,
        "topic_detail",
        lambda value: {
            "topic": {"title": "Test topic"},
            "objectives": [{"objective_id": "O1", "status": "uncovered"}],
        },
    )
    extension._INSTALLED = False
    extension.install(server)

    run = server.create_run(
        {
            "content_product": "topic-reel-pack",
            "topic_ref": topic_ref,
            "run_id": "test-reel-pack",
            "reel_count": 3,
            "duration": 30,
            "audio_provider": "gemini",
            "confirm_paid_api": True,
        }
    )

    assert run["content_product"] == "topic-reel-pack"
    assert run["current_step"] == 1
    assert len(run["artifacts"]["reels"]) == 3
    assert (runs_root / "test-reel-pack" / "reel_pack.json").exists()

    command, environment = server.build_generation_command(
        run,
        {"from_step": 2, "stop_after_step": 2, "confirm_paid_api": True},
    )
    assert any(str(item).endswith("mav_generate_reel_pack.py") for item in command)
    assert "--reel-count" in command
    assert environment["MAV_RUN_ID"] == "test-reel-pack"

    run_path = runs_root / "test-reel-pack"
    (run_path / "pack_plan.json").write_text("{}", encoding="utf-8")
    (run_path / "narration.json").write_text("{}", encoding="utf-8")
    (run_path / "audio_generation.json").write_text("{}", encoding="utf-8")
    (run_path / "audio_chunks").mkdir()
    (run_path / "audio_timing.json").write_text("{}", encoding="utf-8")
    reset = server.reset_run_from_step("test-reel-pack", 3)

    assert reset["current_step"] == 2
    assert (run_path / "pack_plan.json").exists()
    assert (run_path / "narration.json").exists()
    assert not (run_path / "audio_generation.json").exists()
    assert not (run_path / "audio_chunks").exists()
    assert not (run_path / "audio_timing.json").exists()
    reset_pack = json.loads((run_path / "reel_pack.json").read_text(encoding="utf-8"))
    assert reset_pack["status"] == "scripts_ready"
    assert {item["status"] for item in reset_pack["reels"]} == {"scripted"}

    resized = server._resize_reel_pack("test-reel-pack", 6)
    assert resized["settings"]["reel_count"] == 6
    assert resized["current_step"] == 1
    assert len(resized["artifacts"]["reels"]) == 6
    assert json.loads((run_path / "input.json").read_text(encoding="utf-8"))["reel_count"] == 6


def test_full_lesson_remains_default_contract():
    import studio.reel_pack_extension as extension

    assert extension.FULL_LESSON_PRODUCT == "full-lesson"
    assert extension.CONTENT_PRODUCT == "topic-reel-pack"


def test_reel_pack_artifacts_expose_live_preview_timeline(tmp_path, monkeypatch):
    import studio.server as server
    import studio.reel_pack_extension as extension
    import template_lab.reel_pack.common as reel_common

    runs_root = tmp_path / "template_lab" / "runs"
    run_path = runs_root / "preview-pack"
    (run_path / "motion_canvas" / "reels").mkdir(parents=True)
    (run_path / "audio_chunks" / "reel_001").mkdir(parents=True)
    (run_path / "motion_canvas" / "reels" / "reel_001.tsx").write_text("// reel", encoding="utf-8")
    (run_path / "audio_chunks" / "reel_001" / "audio.wav").write_bytes(b"audio")
    (run_path / "motion_canvas" / "preview").mkdir()
    (run_path / "motion_canvas" / "preview" / "contact-sheet.png").write_bytes(b"png")
    (run_path / "reel_pack.json").write_text(json.dumps({
        "run_id": "preview-pack",
        "content_product": "topic-reel-pack",
        "reels": [{"reel_id": "reel_001", "working_title": "Preview reel"}],
    }), encoding="utf-8")
    (run_path / "motion_canvas" / "manifest.json").write_text(json.dumps({
        "reels": [{
            "scene_id": "reel_001",
            "absolute_start": 12.5,
            "absolute_end": 42.5,
            "render_absolute_start": 12.5,
            "render_absolute_end": 42.5,
            "render_start_frame": 375,
            "render_end_frame": 1275,
        }],
    }), encoding="utf-8")

    monkeypatch.setattr(server, "RUNS_ROOT", runs_root)
    monkeypatch.setattr(reel_common, "RUNS_ROOT", runs_root)
    extension._INSTALLED = False
    extension.install(server)
    monkeypatch.setattr(server, "_preview_run_id", "preview-pack")
    monkeypatch.setattr(server, "_preview_url", "http://127.0.0.1:9010/")

    class RunningProcess:
        def poll(self):
            return None

    monkeypatch.setattr(server, "_preview_process", RunningProcess())
    artifacts = server._artifact_snapshot("preview-pack")

    assert artifacts["preview_url"] == "http://127.0.0.1:9010/"
    assert artifacts["validation_preview_url"].endswith("contact-sheet.png")
    assert artifacts["reels"][0]["absolute_start"] == 12.5
    assert artifacts["reels"][0]["render_end_frame"] == 1275
