from __future__ import annotations

import json
from pathlib import Path

import pytest

from reel_pack.pipeline import CONTENT_PRODUCT, create_pack, load_pack, reject_reel, restore_reel
from reel_pack.common import active_narration
from reel_pack.planning import _paragraph_from_script, _validate_audio_durations, write_scripts
from reel_pack.schema import validate_plan, validate_script


def _beats() -> list[dict]:
    return [
        {
            "id": beat_id,
            "time_budget": duration,
            "narrative_job": f"Narrative job for {beat_id}",
            "visual_job": f"Visual job for {beat_id}",
            "energy": energy,
            "transition_intent": "continuous transformation",
        }
        for beat_id, duration, energy in (
            ("hook", 4, 5),
            ("prediction", 5, 4),
            ("reversal", 7, 5),
            ("proof", 11, 4),
            ("payoff", 8, 5),
        )
    ]


def _brief(index: int) -> dict:
    return {
        "reel_id": f"reel_{index:03d}",
        "working_title": f"Reel {index}",
        "hook": f"Distinct hook {index}",
        "learning_payoff": f"Distinct payoff {index}",
        "central_question": f"Central question {index}?",
        "misconception": f"Misconception {index}",
        "answer": f"Answer {index}",
        "continuity_entity": f"Continuity entity {index}",
        "visual_thesis": f"One evolving portrait mechanism {index}",
        "objective_ids": [f"objective_{index}"],
        "fact_ids": [f"fact_{index}"],
        "angle": "curiosity",
        "visual_concept": f"Portrait concept {index}",
        "required_scientific_relationships": [
            "The displayed vector and object response must remain directionally consistent."
        ],
        "target_duration_seconds": 35,
        "beats": _beats(),
    }


def _script(brief: dict, words_per_beat: int = 16) -> dict:
    beats = [
        {
            "id": beat["id"],
            "spoken_text": " ".join([beat["id"]] * words_per_beat),
            "delivery": "fast-curious" if beat["id"] == "hook" else "confident",
        }
        for beat in brief["beats"]
    ]
    return {
        "reel_id": brief["reel_id"],
        "title": "A standalone Reel",
        "narration": " ".join(item["spoken_text"] for item in beats),
        "beats": beats,
        "visual_direction": "One evolving portrait mechanism",
        "target_duration_seconds": 35,
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


def test_plan_requires_five_to_seven_story_beats():
    brief = _brief(1)
    brief["beats"] = brief["beats"][:4]
    with pytest.raises(ValueError, match="5-7 beats"):
        validate_plan({"reels": [brief]}, reel_count=1)


def test_plan_beat_budget_overrun_is_warning_only():
    brief = _brief(1)
    for beat in brief["beats"]:
        beat["time_budget"] = 10
    result = validate_plan({"reels": [brief]}, reel_count=1)[0]
    assert result["status"] == "planned"
    assert result["validation_warnings"] == [
        "reel_001 beat budgets total 50s, above the allowed target range"
    ]


def test_script_must_be_standalone_and_reel_length():
    brief = validate_plan({"reels": [_brief(1)]}, reel_count=1)[0]
    valid = _script(brief)
    result = validate_script(valid, brief=brief)
    assert result["status"] == "scripted"
    assert result["narration_word_count"] == 80
    assert result["validation_warnings"] == []

    long_narration = _script(brief, words_per_beat=22)
    long_result = validate_script(long_narration, brief=brief)
    assert long_result["status"] == "scripted"
    assert long_result["narration_word_count"] == 110
    assert long_result["validation_warnings"] == [
        "reel_001 has 110 words; expected 70-94 for a 35-second Reel"
    ]

    invalid = _script(brief)
    invalid["beats"][0]["spoken_text"] = "In the previous Reel " + invalid["beats"][0]["spoken_text"]
    invalid["narration"] = " ".join(item["spoken_text"] for item in invalid["beats"])
    with pytest.raises(ValueError, match="not standalone"):
        validate_script(invalid, brief=brief)


def test_script_beats_must_match_blueprint_order():
    brief = validate_plan({"reels": [_brief(1)]}, reel_count=1)[0]
    invalid = _script(brief)
    invalid["beats"][0], invalid["beats"][1] = invalid["beats"][1], invalid["beats"][0]
    invalid["narration"] = " ".join(item["spoken_text"] for item in invalid["beats"])
    with pytest.raises(ValueError, match="exactly match"):
        validate_script(invalid, brief=brief)


def test_script_narration_mismatch_is_normalized_with_warning():
    brief = validate_plan({"reels": [_brief(1)]}, reel_count=1)[0]
    script = _script(brief)
    canonical = script["narration"]
    script["narration"] = "Top-level narration accidentally omitted a beat."

    result = validate_script(script, brief=brief)

    assert result["narration"] == canonical
    assert result["narration_word_count"] == len(canonical.split())
    assert result["validation_warnings"] == [
        "reel_001 narration differed from its beat spoken_text values; "
        "the beat text was used as the canonical narration"
    ]


def test_audio_duration_range_is_warning_only(tmp_path, capsys):
    (tmp_path / "audio_chunks").mkdir()
    (tmp_path / "audio_chunks" / "manifest.json").write_text(json.dumps({
        "chapters": [{
            "id": "reel_001",
            "absolute_start": 0,
            "absolute_end": 44.9,
        }],
    }), encoding="utf-8")
    pack = {
        "reels": [{
            "reel_id": "reel_001",
            "status": "scripted",
            "target_duration_seconds": 35,
        }],
    }
    _validate_audio_durations(tmp_path, pack)
    record = pack["reels"][0]
    assert record["audio_duration_seconds"] == 44.9
    assert record["validation_warnings"] == [
        "reel_001 audio duration 44.9s is outside the allowed 28.0-42.0s range for a 35.0s Reel"
    ]
    assert "WARNING:" in capsys.readouterr().out


def test_cached_narration_restores_scripted_beats_after_plan_reload(tmp_path):
    brief = validate_plan({"reels": [_brief(1)]}, reel_count=1)[0]
    script = validate_script(_script(brief), brief=brief)
    paragraph = _paragraph_from_script(brief, script)
    (tmp_path / "input.json").write_text(json.dumps({
        "topic": "Density",
        "tone": "precise",
    }), encoding="utf-8")
    (tmp_path / "reel_pack.json").write_text(json.dumps({
        "run_id": "cached-pack",
        "content_product": "topic-reel-pack",
        "status": "planned",
        "current_step": 2,
        "reels": [brief],
    }), encoding="utf-8")
    (tmp_path / "narration.json").write_text(json.dumps({
        "paragraphs": [paragraph],
    }), encoding="utf-8")

    result = write_scripts(tmp_path, allow_model_call=False)

    record = result["reels"][0]
    assert record["status"] == "scripted"
    assert record["narration_word_count"] == 80
    assert [beat["spoken_text"] for beat in record["beats"]] == [
        beat["spoken_text"] for beat in script["beats"]
    ]


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


def test_create_pack_can_restart_after_step_one_reset_preserves_studio_files(tmp_path, monkeypatch):
    from reel_pack import common

    monkeypatch.setattr(common, "RUNS_ROOT", tmp_path)
    run_path = tmp_path / "restart-reels-v01"
    run_path.mkdir()
    (run_path / "studio_run.json").write_text('{"status":"paused"}', encoding="utf-8")
    (run_path / "studio.log").write_text("Reset from step 1\n", encoding="utf-8")

    pack = create_pack(
        run_id="restart-reels-v01",
        topic="Motion",
        topic_ref="1.2",
        objective_ids=["O1"],
        facts=[{"id": "F1", "text": "Motion fact"}],
        physics_context={},
        tone="precise",
        reel_count=2,
    )

    assert pack["status"] == "created"
    assert (run_path / "reel_pack.json").exists()
    assert (run_path / "studio_run.json").exists()
    assert (run_path / "studio.log").exists()


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

    from mav_render import MOTION_CANVAS_RUNTIME_ROOT
    assert MOTION_CANVAS_RUNTIME_ROOT == package_path.parent
