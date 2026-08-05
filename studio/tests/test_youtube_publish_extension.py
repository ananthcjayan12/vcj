from __future__ import annotations

import json
from pathlib import Path

import pytest


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _workspace(tmp_path: Path) -> tuple[Path, Path]:
    runs = tmp_path / "template_lab" / "runs"
    youtube = tmp_path / ".youtube"
    youtube.mkdir(parents=True)
    (youtube / "token.json").write_text("{}", encoding="utf-8")
    _write_json(
        youtube / "channel.json",
        {
            "channel_id": "UC_TEST_CHANNEL",
            "channel_title": "Physics Channel",
        },
    )

    lesson = runs / "lesson-run"
    (lesson / "motion_canvas").mkdir(parents=True)
    (lesson / "motion_canvas" / "final.mp4").write_bytes(b"long-form")
    _write_json(lesson / "youtube" / "metadata.json", {"video_title": "Long-form lesson"})
    (lesson / "youtube" / "thumbnail.jpg").write_bytes(b"thumbnail")

    pack = runs / "reel-run"
    _write_json(
        pack / "reel_pack.json",
        {"reels": [{"reel_id": "reel_001", "working_title": "Short lesson"}]},
    )
    _write_json(
        pack / "youtube" / "reel-assets.json",
        {
            "reels": [
                {
                    "reel_id": "reel_001",
                    "metadata": "youtube/reels/reel_001/metadata.json",
                    "thumbnail": "youtube/reels/reel_001/thumbnail.jpg",
                    "youtube_video": "youtube/reels/reel_001/youtube-short.mp4",
                }
            ]
        },
    )
    _write_json(pack / "youtube" / "reels" / "reel_001" / "metadata.json", {"video_title": "Short lesson"})
    (pack / "youtube" / "reels" / "reel_001" / "youtube-short.mp4").write_bytes(b"short")
    (pack / "youtube" / "reels" / "reel_001" / "thumbnail.jpg").write_bytes(b"cover")
    return runs, youtube


def test_dashboard_discovers_channels_longform_and_reels(tmp_path, monkeypatch):
    import studio.server as server
    import studio.youtube_publish_extension as extension

    runs, _youtube = _workspace(tmp_path)
    monkeypatch.setattr(server, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(server, "RUNS_ROOT", runs)
    extension._JOBS.clear()

    payload = extension.youtube_dashboard_payload(server)

    assert payload["selected_channel"]["channel_id"] == "UC_TEST_CHANNEL"
    assert payload["profiles"][0]["channel_title"] == "Physics Channel"
    assert payload["candidates"]["longform"][0]["ready"] is True
    assert payload["candidates"]["longform"][0]["thumbnail_ready"] is True
    assert payload["candidates"]["reels"][0]["ready"] is True
    assert payload["candidates"]["reels"][0]["thumbnail_mode"] == "embedded_final_frame"
    assert payload["defaults"]["auto_organize_course"] is True
    assert "IGCSE Physics (0625)" in payload["defaults"]["course_playlist_title"]


def test_profile_selection_is_persisted(tmp_path, monkeypatch):
    import studio.server as server
    import studio.youtube_publish_extension as extension

    runs, _youtube = _workspace(tmp_path)
    monkeypatch.setattr(server, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(server, "RUNS_ROOT", runs)
    first = extension.youtube_dashboard_payload(server)["profiles"][0]

    selected = extension.select_profile(server, first["id"])

    assert selected["selected_profile_id"] == first["id"]
    stored = json.loads((tmp_path / ".youtube" / "profiles.json").read_text(encoding="utf-8"))
    assert stored["selected_profile_id"] == first["id"]


def test_publish_requires_explicit_confirmation(tmp_path, monkeypatch):
    import studio.server as server
    import studio.youtube_publish_extension as extension

    runs, _youtube = _workspace(tmp_path)
    monkeypatch.setattr(server, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(server, "RUNS_ROOT", runs)
    profile = extension.youtube_dashboard_payload(server)["profiles"][0]

    with pytest.raises(PermissionError, match="Confirm"):
        extension.start_publish_job(
            server,
            {
                "profile_id": profile["id"],
                "item_keys": ["longform:lesson-run"],
                "confirm_publish": False,
            },
        )


def test_publish_refuses_existing_upload_receipt(tmp_path, monkeypatch):
    import studio.server as server
    import studio.youtube_publish_extension as extension

    runs, _youtube = _workspace(tmp_path)
    monkeypatch.setattr(server, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(server, "RUNS_ROOT", runs)
    _write_json(
        runs / "lesson-run" / "youtube" / "upload-result.json",
        {"status": "uploaded", "url": "https://youtu.be/already"},
    )
    profile = extension.youtube_dashboard_payload(server)["profiles"][0]

    with pytest.raises(FileExistsError, match="already uploaded"):
        extension.start_publish_job(
            server,
            {
                "profile_id": profile["id"],
                "item_keys": ["longform:lesson-run"],
                "confirm_publish": True,
            },
        )


def test_last_json_ignores_oauth_progress_lines():
    import studio.youtube_publish_extension as extension

    payload = extension._last_json(
        "Open this URL first\n{\n  \"status\": \"authorized\", \"channel_id\": \"UC123\"\n}\n"
    )

    assert payload == {"status": "authorized", "channel_id": "UC123"}
