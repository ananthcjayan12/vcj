from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .chapter_index import build_chapter_index
from .constants import MAX_CHAPTER_REPAIRS
from .direct_html_validator import validate_html, validation_report
from .html_contract import extract_chapter_blocks
from .io_utils import read_json, sha256_text, sync_direct_cost_records, write_json, write_text
from .prompt_builder import repair_system_prompt, write_prompt

ModelCall = Callable[..., str | None]


def _default_model_call(**kwargs: Any) -> str | None:
    from mav_models import call_model_text

    return call_model_text(**kwargs)


def replace_chapter(html: str, chapter_id: str, replacement: str, *, expected_hash: str | None = None) -> str:
    current = next((item for item in extract_chapter_blocks(html) if item.chapter_id == chapter_id), None)
    if current is None:
        raise RuntimeError(f"Cannot repair missing chapter {chapter_id}")
    if expected_hash and current.sha256 != expected_hash:
        raise RuntimeError(f"Refusing stale repair for {chapter_id}; source hash changed")
    replacement_blocks = extract_chapter_blocks(replacement)
    if len(replacement_blocks) != 1 or replacement_blocks[0].chapter_id != chapter_id:
        raise RuntimeError(f"Repair response must contain exactly one complete {chapter_id} block")
    return html[: current.source_start] + replacement_blocks[0].full_source + html[current.source_end :]


def repair_chapter(
    run_path: Path,
    chapter_id: str,
    findings: list[dict[str, Any]],
    bundle: dict[str, Any],
    physics_context: dict[str, Any],
    *,
    instruction: str = "",
    model_call: ModelCall | None = None,
) -> dict[str, Any]:
    direct_root = run_path / "direct_html"
    master_path = direct_root / "master.html"
    html = master_path.read_text(encoding="utf-8")
    chapter = next((item for item in extract_chapter_blocks(html) if item.chapter_id == chapter_id), None)
    if chapter is None:
        raise RuntimeError(f"Unknown direct-HTML chapter: {chapter_id}")
    manifest_path = direct_root / "generation_manifest.json"
    manifest = read_json(manifest_path, {}) or {}
    counts = dict(manifest.get("repair_counts") or {})
    repair_count = int(counts.get(chapter_id, 0))
    if repair_count >= MAX_CHAPTER_REPAIRS:
        raise RuntimeError(f"Automatic repair limit reached for {chapter_id}")

    chapter_paragraphs = [
        item
        for item in bundle.get("narration", {}).get("paragraphs", [])
        if item.get("start") is not None and float(item["end"]) > chapter.start and float(item["start"]) < chapter.end
    ]
    request = {
        "chapter_id": chapter_id,
        "source_hash": chapter.sha256,
        "timing": {"start": chapter.start, "end": chapter.end},
        "narration": chapter_paragraphs,
        "physics_context": physics_context,
        "findings": findings,
        "instruction": instruction,
        "current_chapter": chapter.full_source,
    }
    next_count = repair_count + 1
    system = repair_system_prompt()
    user = json.dumps(request, indent=2, ensure_ascii=False)
    write_json(direct_root / "repairs" / f"repair_{chapter_id}_{next_count:02d}_request.json", request)
    write_prompt(direct_root / "repairs" / f"repair_{chapter_id}_{next_count:02d}_prompt.txt", system, user)
    response = (model_call or _default_model_call)(task="direct_html_repair", system=system, user=user, max_tokens=24_000)
    sync_direct_cost_records(run_path)
    if not response:
        raise RuntimeError(f"Repair model returned no response for {chapter_id}")
    response = response.strip()
    if response.startswith("```"):
        raise RuntimeError("Chapter repair returned Markdown fences")
    write_text(direct_root / "repairs" / f"repair_{chapter_id}_{next_count:02d}_response.html", response + "\n")
    candidate = replace_chapter(html, chapter_id, response, expected_hash=chapter.sha256)
    report = validation_report(
        validate_html(
            candidate,
            expected_duration=float(bundle["video"]["duration_seconds"]),
            physics_context=physics_context,
        )
    )
    write_json(direct_root / "repairs" / f"repair_{chapter_id}_{next_count:02d}_validation.json", report)
    if report["status"] != "passed":
        raise RuntimeError(f"Repair for {chapter_id} failed contract validation")

    versions = direct_root / "versions"
    versions.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    write_text(versions / f"master_before_{chapter_id}_{next_count:02d}_{stamp}.html", html)
    write_text(master_path, candidate)
    counts[chapter_id] = next_count
    manifest.update({"repair_counts": counts, "html_hash": sha256_text(candidate), "status": "repaired", "validation": "passed"})
    write_json(manifest_path, manifest)
    index = build_chapter_index(master_path, repair_state={chapter_id: {"repair_count": next_count, "status": "repaired"}})
    return {"status": "repaired", "chapter_id": chapter_id, "repair_count": next_count, "master": master_path, "chapter_index": index}
