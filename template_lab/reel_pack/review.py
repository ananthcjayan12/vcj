from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from .common import (
    PROMPT_ROOT,
    facts_for_brief,
    load_pack,
    now,
    read_json,
    reel_path,
    save_pack,
    write_json_file,
    write_text,
)
from .schema import require_reel_id
from .visuals import repair_visual, runtime_env

from mav_models import model_config_for_task
from motion_canvas import pipeline as motion_pipeline
from motion_canvas.lesson_review import (
    _screen_with_model,
    extract_visual_contract,
    parse_screening_response,
)


def capture_pack_evidence(run_path: Path, pack: dict[str, Any]) -> tuple[dict[str, Any], list[Path]]:
    review_root = run_path / "review"
    evidence_root = review_root / "evidence"
    evidence_root.mkdir(parents=True, exist_ok=True)
    aggregate = {"version": "1.0", "reels": [], "contact_sheets": []}
    images: list[Path] = []
    for record in pack["reels"]:
        parent_id = record["reel_id"]
        if record.get("status") not in {"visual_ready", "approved", "repaired_pending_review", "flagged"}:
            continue
        child = reel_path(run_path, parent_id)
        manifest = read_json(child / "motion_canvas" / "manifest.json", {}) or {}
        motion_pipeline.assemble(child, manifest)
        motion_pipeline._sync_runtime(child)
        output = evidence_root / parent_id
        output.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["npm", "run", "reel-pack-evidence", "--", "--output", str(output)],
            cwd=motion_pipeline.RUNTIME_ROOT,
            env=runtime_env(child, manifest),
            capture_output=True,
            text=True,
            timeout=900,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Evidence capture failed for {parent_id}: {(result.stderr or result.stdout)[-12_000:]}"
            )
        evidence = read_json(output / "evidence.json", {}) or {}
        aggregate["reels"].extend(evidence.get("reels", []))
        for name in evidence.get("contact_sheets", []):
            image = output / name
            if image.exists():
                images.append(image)
                aggregate["contact_sheets"].append(str(image.relative_to(run_path)))
    write_json_file(review_root / "evidence.json", aggregate)
    if not images:
        raise RuntimeError("No completed Reel evidence was available for screening")
    return aggregate, images


def screening_context(run_path: Path, pack: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    input_payload = read_json(run_path / "input.json", {}) or {}
    record_by_id = {item["reel_id"]: item for item in pack["reels"]}
    reels = []
    for evidence_reel in evidence.get("reels", []):
        parent_id = str(evidence_reel.get("reel_id"))
        record = record_by_id.get(parent_id, {})
        child = reel_path(run_path, parent_id)
        source_path = child / "motion_canvas" / "reels" / "reel_001.tsx"
        if not source_path.exists():
            source_path = child / "motion_canvas" / "chapters" / "reel_001.tsx"
        source = source_path.read_text(encoding="utf-8") if source_path.exists() else ""
        contract, _ = extract_visual_contract(source, parent_id)
        reels.append({
            "reel_id": parent_id,
            "title": record.get("working_title"),
            "hook": record.get("hook"),
            "learning_payoff": record.get("learning_payoff"),
            "grounded_facts": facts_for_brief(input_payload, record),
            "required_scientific_relationships": record.get("required_scientific_relationships", []),
            "visual_contract": contract,
            "frames": evidence_reel.get("frames", []),
        })
    return {
        "version": "1.0",
        "content_product": "topic-reel-pack",
        "topic": input_payload.get("topic"),
        "topic_ref": input_payload.get("topic_ref"),
        "review_rules": {
            "maximum_findings": 5,
            "minimum_confidence": 0.85,
            "zero_findings_allowed": True,
            "ignore_minor_style_preferences": True,
        },
        "reels": reels,
    }


def screen_pack(
    run_path: Path,
    *,
    allow_repairs: bool = True,
    model_call: Any = None,
) -> dict[str, Any]:
    pack = load_pack(run_path)
    evidence, images = capture_pack_evidence(run_path, pack)
    context = screening_context(run_path, pack, evidence)
    system = (PROMPT_ROOT / "pack_screen.system.txt").read_text(encoding="utf-8")
    user = json.dumps(context, ensure_ascii=False)
    resolved = model_config_for_task("motion_canvas_lesson_screen", requested_max_tokens=8_000)
    response = (
        model_call(system=system, user=user, images=images)
        if model_call is not None
        else _screen_with_model(system=system, user=user, images=images, resolved=resolved)
    )
    write_text(run_path / "review" / "model-response.txt", response)
    parsed = parse_screening_response(
        response,
        evidence=evidence,
        max_findings=int(os.getenv("MAV_REEL_PACK_MAX_FINDINGS", "5")),
        min_confidence=float(os.getenv("MAV_REEL_PACK_MIN_CONFIDENCE", "0.85")),
    )
    findings = parsed["findings"]
    by_reel: dict[str, list[dict[str, Any]]] = {}
    for finding in findings:
        by_reel.setdefault(finding["reel_id"], []).append(finding)
    repairs = []
    for record in pack["reels"]:
        parent_id = record["reel_id"]
        if parent_id not in by_reel:
            if record.get("status") == "visual_ready":
                record["status"] = "approved"
            continue
        record["status"] = "flagged"
        if not allow_repairs:
            continue
        try:
            repair_visual(run_path, record, by_reel[parent_id])
            record["status"] = "repaired_pending_review"
            repairs.append({"reel_id": parent_id, "status": "repaired_pending_review"})
        except Exception as exc:
            record["status"] = "flagged"
            record["error"] = str(exc)
            repairs.append({"reel_id": parent_id, "status": "failed", "error": str(exc)})
    report_status = (
        "passed"
        if not findings
        else "repaired_pending_review"
        if repairs and all(item["status"] == "repaired_pending_review" for item in repairs)
        else "needs_review"
    )
    report = {
        "version": "1.0",
        "status": report_status,
        "screening_calls": 1,
        "screening_model": f"{resolved.provider}:{resolved.model}",
        "findings": findings,
        "repairs": repairs,
        "evidence": "review/evidence.json",
        "completed_at": now(),
    }
    write_json_file(run_path / "pack-review.json", report)
    pack["status"] = "approved" if report_status == "passed" else "needs_review"
    pack["current_step"] = max(int(pack.get("current_step", 6)), 7)
    save_pack(run_path, pack)
    return report


def approve_reel(run_path: Path, parent_reel_id: str) -> dict[str, Any]:
    pack = load_pack(run_path)
    target = require_reel_id(parent_reel_id)
    record = next((item for item in pack["reels"] if item["reel_id"] == target), None)
    if record is None:
        raise ValueError(f"Unknown Reel: {target}")
    if record.get("status") not in {"visual_ready", "repaired_pending_review", "flagged"}:
        raise ValueError(f"{target} cannot be approved from status {record.get('status')}")
    preview = reel_path(run_path, target) / "motion_canvas" / "preview" / "contact-sheet.png"
    if not preview.exists():
        raise ValueError(f"{target} preview evidence is missing")
    record["status"] = "approved"
    record["approved_at"] = now()
    pack["status"] = (
        "approved"
        if all(item.get("status") in {"approved", "rendered"} for item in pack["reels"])
        else "needs_review"
    )
    return save_pack(run_path, pack)
