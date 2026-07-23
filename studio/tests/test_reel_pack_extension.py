from __future__ import annotations

import json
from pathlib import Path


def test_studio_extension_creates_additive_reel_pack(tmp_path, monkeypatch):
    import studio.server as server
    import studio.reel_pack_extension as extension

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


def test_full_lesson_remains_default_contract():
    import studio.reel_pack_extension as extension

    assert extension.FULL_LESSON_PRODUCT == "full-lesson"
    assert extension.CONTENT_PRODUCT == "topic-reel-pack"
