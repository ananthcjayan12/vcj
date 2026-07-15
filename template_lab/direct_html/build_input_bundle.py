from __future__ import annotations

import json
from typing import Any

from .constants import (
    CONTRACT_VERSION,
    DESIGN_SYSTEM_VERSION,
    MAX_ACTIVE_OBJECTS,
    MIN_IMPORTANT_TEXT_PX,
    MIN_SECONDARY_TEXT_PX,
    SAFE_MARGIN_PX,
    VIEWPORT_HEIGHT,
    VIEWPORT_WIDTH,
)
from .io_utils import canonical_hash, write_json, write_text


def build_input_bundle(
    run_path,
    input_payload: dict[str, Any],
    narration: dict[str, Any],
    timing: dict[str, Any],
    word_timing: dict[str, Any],
    asset_manifest: dict[str, Any],
    physics_context: dict[str, Any],
) -> dict[str, Any]:
    timing_by_id = {item.get("id"): item for item in timing.get("paragraphs", [])}
    paragraphs = []
    for paragraph in narration.get("paragraphs", []):
        paragraph_timing = timing_by_id.get(paragraph.get("id"), {})
        paragraphs.append(
            {
                "id": paragraph.get("id"),
                "text": paragraph.get("text", ""),
                "beat_label": paragraph.get("beat_label", ""),
                "claim_ids": paragraph.get("claim_ids", []),
                "start": paragraph_timing.get("start"),
                "end": paragraph_timing.get("end"),
                "duration": paragraph_timing.get("duration"),
            }
        )

    bundle = {
        "schema_version": CONTRACT_VERSION,
        "video": {
            "run_id": input_payload.get("run_id"),
            "video_id": input_payload.get("video_id") or input_payload.get("run_id"),
            "title": narration.get("title") or input_payload.get("topic"),
            "topic": input_payload.get("topic"),
            "duration_seconds": timing.get("audio_duration_seconds"),
            "resolution": [VIEWPORT_WIDTH, VIEWPORT_HEIGHT],
            "fps": 30,
        },
        "narration": {"paragraphs": paragraphs, "words": word_timing.get("words", [])},
        "grounding": {
            "facts": input_payload.get("facts", []),
            "objective_ids": input_payload.get("objective_ids", []),
            "physics": physics_context,
        },
        "assets": asset_manifest,
        "visual_direction": {
            "identity": "hybrid modern science-lab teaching platform",
            "design_system_version": DESIGN_SYSTEM_VERSION,
            "safe_margin_px": SAFE_MARGIN_PX,
            "minimum_important_text_px": MIN_IMPORTANT_TEXT_PX,
            "minimum_secondary_text_px": MIN_SECONDARY_TEXT_PX,
            "max_active_objects": MAX_ACTIVE_OBJECTS,
            "target_chapters": [6, 8],
            "target_composition_states": [12, 16],
            "meaningful_change_seconds": [5, 12],
        },
        "runtime_contract": {
            "styles": ["./runtime/motion-core.css"],
            "scripts": [
                "./runtime/gsap.min.js",
                "./runtime/phrase-timing.js",
                "./runtime/physics-helpers.js",
                "./runtime/asset-loader.js",
                "./lesson-data.js",
                "./runtime/motion-core.js",
                "./runtime/browser-probe.js",
            ],
            "timeline_id": "direct_html_master",
            "chapter_markers": "<!-- BEGIN CHAPTER chapter_NN --> ... <!-- END CHAPTER chapter_NN -->",
        },
    }
    bundle["input_hash"] = canonical_hash(bundle)
    write_json(run_path / "direct_html" / "lesson_input_bundle.json", bundle)
    lesson_data = (
        "window.lessonTiming = "
        + json.dumps(bundle["narration"], ensure_ascii=False, separators=(",", ":"))
        + ";\nwindow.lessonPhysics = "
        + json.dumps(physics_context, ensure_ascii=False, separators=(",", ":"))
        + ";\nwindow.lessonAssets = "
        + json.dumps(asset_manifest, ensure_ascii=False, separators=(",", ":"))
        + ";\n"
    )
    write_text(run_path / "direct_html" / "lesson-data.js", lesson_data)
    return bundle
