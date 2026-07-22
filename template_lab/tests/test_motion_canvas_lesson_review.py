from __future__ import annotations

import json

from motion_canvas.generation_contract import CONTRACT_END, CONTRACT_START, contract_instructions
from motion_canvas.lesson_review import extract_visual_contract, parse_screening_response, _repair_instruction


def _evidence() -> dict:
    return {
        "reels": [
            {
                "reel_id": "reel_001",
                "frames": [
                    {"frame_id": "reel_001-A"},
                    {"frame_id": "reel_001-B"},
                ],
            },
            {
                "reel_id": "reel_002",
                "frames": [{"frame_id": "reel_002-A"}],
            },
        ]
    }


def test_extract_visual_contract() -> None:
    contract = {
        "version": "1.0",
        "scene_claim": "An arrow and trajectory agree.",
        "review_checkpoints": [{"local_time": 2.0, "purpose": "completed state"}],
    }
    source = f"{CONTRACT_START}\n{json.dumps(contract)}\n{CONTRACT_END}\nexport default null;"
    parsed, warnings = extract_visual_contract(source, "reel_001")
    assert parsed == contract
    assert warnings == []


def test_screening_filters_speculation_and_caps_findings() -> None:
    findings = []
    for index in range(8):
        findings.append(
            {
                "rank": index + 1,
                "chapter_number": 1,
                "reel_id": "reel_001",
                "frame_id": "reel_001-A" if index % 2 == 0 else "reel_001-B",
                "category": f"issue_{index}",
                "severity": "critical" if index == 0 else "major",
                "confidence": 0.99 - index * 0.01,
                "visible_evidence": "visible",
                "expected_behaviour": "expected",
                "repair_instruction": "repair",
            }
        )
    findings.extend(
        [
            {
                "rank": 9,
                "reel_id": "reel_002",
                "frame_id": "reel_002-A",
                "category": "low_confidence",
                "severity": "major",
                "confidence": 0.5,
            },
            {
                "rank": 10,
                "reel_id": "reel_999",
                "frame_id": "unknown",
                "category": "invented",
                "severity": "critical",
                "confidence": 1.0,
            },
            {
                "rank": 11,
                "reel_id": "reel_002",
                "frame_id": "reel_002-A",
                "category": "minor_style",
                "severity": "minor",
                "confidence": 1.0,
            },
        ]
    )
    parsed = parse_screening_response(
        json.dumps({"status": "ISSUES_FOUND", "findings": findings}),
        evidence=_evidence(),
    )
    assert parsed["status"] == "ISSUES_FOUND"
    assert len(parsed["findings"]) == 5
    assert all(item["confidence"] >= 0.85 for item in parsed["findings"])
    assert all(item["severity"] in {"critical", "major"} for item in parsed["findings"])


def test_zero_findings_is_valid_pass() -> None:
    parsed = parse_screening_response(
        '{"status":"PASS","findings":[]}',
        evidence=_evidence(),
    )
    assert parsed == {"status": "PASS", "findings": [], "raw_status": "PASS"}


def test_generation_contract_is_generic_and_reviewable() -> None:
    text = contract_instructions()
    assert "direction" in text
    assert "trajectory" in text
    assert "reference frame" in text
    assert "one to three review checkpoints" in text
    assert "centre of gravity" not in text.lower()


def test_repair_instruction_preserves_semantic_timing() -> None:
    instruction = _repair_instruction(
        "reel_001",
        [{"visible_evidence": "Arrow and motion disagree."}],
        {"cue_events": [{"cue": "push", "expected_visual": "motion begins"}]},
    )
    assert "preserve CHAPTER_DURATION" in instruction
    assert "cue-to-visual event mapping" in instruction
    assert "do not move a semantic event" in instruction
