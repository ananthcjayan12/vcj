from __future__ import annotations

import json
from pathlib import Path

import pytest

from reel_pack.pipeline import CONTENT_PRODUCT, create_pack, load_pack, reject_reel, restore_reel
from reel_pack.common import active_narration
from reel_pack.schema import validate_plan, validate_script


def _brief(index: int) -> dict:
    return {
        "reel_id": f"reel_{index:03d}",
        "working_title": f"Reel {index}",
        "hook": f"Distinct hook {index}",
        "learning_payoff": f"Distinct payoff {index}",
        "objective_ids": [f"objective_{index}"],
        "fact_ids": [f"fact_{index}"],
        "angle": "curiosity",
        "visual_concept": f"Portrait concept {index}",
        "required_scientific_relationships": [
            "The displayed vector and object response must remain directionally consistent."
        ],
        "target_duration_seconds": 45,
    }


def test_plan_requires_exact_requested_reel_count():
    payload = {"reels": [_brief(index) for index in range(1, 13)]}
    assert len(validate_plan(payload, reel_count=12)) == 12
    with pytest.raises(ValueError, match="exactly 12"):
        validate_plan({"reels": payload["reels"][:-1]}, reel_count=12)


def test_plan_rejects_duplicate_hook_and_payoff():
    records = [_brief(index) for index in range(1, 13)]
    records[1]["hook"] = records[0]["hook"]
    records[1]["learning_payoff"] = records[0]["learning_payoff"]
    with pytest.raises(ValueError, match="duplicate"):
        validate_plan({"reels": records}, reel_count=12)


def test_script_must_be_standalone():
    brief = _brief(1)
    valid = {
        "reel_id": "reel_001",
        "title": "A standalone Reel",
        "narration": " ".join(["physics"] * 70),
        "visual_direction": "One portrait mechanism",
        "target_duration_seconds": 45,
    }
    assert validate_script(valid, brief=brief)["status"] == "scripted"
    long_narration = dict(valid)
    long_narration["narration"] = " ".join(["physics"] * 216)
    assert validate_script(long_narration, brief=brief)["narration_word_count"] == 216
    invalid = dict(valid)
    invalid["narration"] = "In the previous Reel " + " ".join(["physics"] * 70)
    with pytest.raises(ValueError, match="not standalone"):
        validate_script(invalid, brief=brief)


def test_create_pack_is_shared_root_run_and_defaults_to_five(tmp_path, monkeypatch):
    from reel_pack import common

    monkeypatch.setattr(common, "RUNS_ROOT", tmp_path)
    pack = create_pack(
        run_id="physics-1-5-3-reels-v01",
        topic="Centre of gravity",
        topic_ref="1.5.3",
        objective_ids=["1_5_3_O01"],
        facts=[{"id": "fact_1", "text": "Grounded fact"}],
        physics_context={},
        tone="precise",
    )
    assert pack["content_product"] == CONTENT_PRODUCT
    assert pack["render_profile"] == "portrait-short-v1"
    assert pack["canvas"] == {"width": 1080, "height": 1920, "fps": 30}
    assert len(pack["reels"]) == 5
    assert [item["reel_id"] for item in pack["reels"]] == [
        f"reel_{index:03d}" for index in range(1, 6)
    ]
    assert not (tmp_path / "physics-1-5-3-reels-v01" / "motion_canvas").exists()
    assert load_pack(tmp_path / "physics-1-5-3-reels-v01")["status"] == "created"


def test_pack_manifest_uses_one_shared_root(tmp_path, monkeypatch):
    from reel_pack import common

    monkeypatch.setattr(common, "RUNS_ROOT", tmp_path)
    pack = create_pack(
        run_id="pack-v01",
        topic="Density",
        topic_ref="1.4.2",
        objective_ids=[],
        facts=[],
        physics_context={},
        tone="precise",
        reel_count=3,
    )
    paths = [item["path"] for item in pack["reels"]]
    assert paths == [".", ".", "."]


def test_reel_can_be_rejected_after_script_review_and_restored(tmp_path, monkeypatch):
    from reel_pack import common

    monkeypatch.setattr(common, "RUNS_ROOT", tmp_path)
    create_pack(
        run_id="reject-v01",
        topic="Motion",
        topic_ref="1.2",
        objective_ids=[],
        facts=[],
        physics_context={},
        tone="precise",
        reel_count=2,
    )
    run_path = tmp_path / "reject-v01"
    pack = load_pack(run_path)
    pack["reels"][0].update({"status": "scripted", "narration": "A standalone explanation."})
    common.save_pack(run_path, pack)
    rejected = reject_reel(run_path, "reel_001", "Not catchy enough")
    assert rejected["reels"][0]["status"] == "rejected"
    assert rejected["reels"][0]["rejection_reason"] == "Not catchy enough"
    assert [item["id"] for item in active_narration({"paragraphs": [{"id": "reel_001"}, {"id": "reel_002"}]}, rejected)["paragraphs"]] == ["reel_002"]
    restored = restore_reel(run_path, "reel_001")
    assert restored["reels"][0]["status"] == "scripted"


def test_runtime_package_keeps_long_form_commands():
    package_path = Path(__file__).resolve().parents[2] / "motion_canvas_runtime" / "package.json"
    package = json.loads(package_path.read_text(encoding="utf-8"))
    scripts = package["scripts"]
    assert scripts["preview-frames"] == "node scripts/render.mjs --preview"
    assert scripts["render-video"] == "node scripts/render.mjs --video"
    assert scripts["reel-pack-preview"] == "node scripts/reel-pack-render.mjs --preview"
    assert scripts["reel-pack-render"] == "node scripts/reel-pack-render.mjs --video"
