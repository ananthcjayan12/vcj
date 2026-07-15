from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

LAB_ROOT = Path(__file__).resolve().parents[1]
if str(LAB_ROOT) not in sys.path:
    sys.path.insert(0, str(LAB_ROOT))

from prompts import load as load_prompt

from mav_schema import narration_bounds, normalize_text, run_dir, spoken_word_count, validate_narration, write_json


def _script_structure_schema(target_duration: float = 50.0) -> dict[str, Any]:
    del target_duration
    beat = {
        "type": "object",
        "properties": {
            "beat_id": {"type": "string"},
            "beat_type": {"type": "string"},
            "one_sentence_summary": {"type": "string"},
            "key_number_or_claim": {"type": "string"},
            "emotional_register": {"type": "string"},
            "claim_ids": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "beat_id",
            "beat_type",
            "one_sentence_summary",
            "key_number_or_claim",
            "emotional_register",
            "claim_ids",
        ],
    }
    return {
        "type": "object",
        "properties": {
            "beats": {
                "type": "array",
                "items": beat,
            }
        },
        "required": ["beats"],
    }


def _script_writing_schema(target_duration: float = 50.0) -> dict[str, Any]:
    del target_duration
    paragraph = {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "beat_label": {"type": "string"},
            "text": {"type": "string"},
            "claim_ids": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["id", "beat_label", "text", "claim_ids"],
    }
    return {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "target_duration_seconds": {"type": "number"},
            "spoken_word_count": {"type": "number"},
            "paragraphs": {
                "type": "array",
                "items": paragraph,
            },
            "elevenlabs_narration": {"type": "string"},
        },
        "required": [
            "title",
            "target_duration_seconds",
            "spoken_word_count",
            "paragraphs",
            "elevenlabs_narration",
        ],
    }


def _step_regen_instruction() -> str:
    return os.getenv("MAV_STEP_REGEN_INSTRUCTION", "").strip()


def _with_director_override(prompt: str, instruction: str) -> str:
    if not instruction:
        return prompt
    return (
        f"{prompt}\n\n"
        "=== DIRECTOR OVERRIDE FOR THIS REGENERATION ===\n"
        f"{instruction}\n"
        "Honor this direction while preserving factual grounding, duration, JSON shape, and all schema constraints."
    )


def _raise_script_failure(run_path: Path, message: str, debug_events: list[dict[str, Any]], **extra: Any) -> None:
    payload = {"event": "script_generation_failed", "message": message, **extra}
    debug_events.append(payload)
    debug_path = run_path / "debug" / "script_generation_debug.json"
    write_json(debug_path, debug_events)
    detail = f"{message}. See {debug_path}"
    if extra:
        detail += f" Details: {json.dumps(extra, ensure_ascii=False)}"
    raise RuntimeError(detail)


def _normalize_narration_shape(narration: dict[str, Any], skeleton: dict[str, Any], input_payload: dict[str, Any]) -> dict[str, Any]:
    """Repair common model output drift before schema validation.

    Some models occasionally return paragraph strings even when the prompt asks
    for paragraph objects. The rest of the pipeline only needs stable paragraph
    ids, text, and claim handles, so convert that shape locally.
    """
    if not isinstance(narration, dict):
        return narration

    paragraphs = narration.get("paragraphs")
    if not isinstance(paragraphs, list):
        return narration

    beats = skeleton.get("beats", []) if isinstance(skeleton, dict) else []
    fallback_claim_ids = [
        str(item.get("id"))
        for item in input_payload.get("facts", [])
        if isinstance(item, dict) and item.get("id")
    ] or ["syllabus_topic"]

    normalized_paragraphs: list[dict[str, Any]] = []
    changed = False
    for index, item in enumerate(paragraphs):
        paragraph_id = f"paragraph_{index + 1:02d}"
        beat = beats[index] if index < len(beats) and isinstance(beats[index], dict) else {}
        if isinstance(item, str):
            normalized_paragraphs.append(
                {
                    "id": paragraph_id,
                    "beat_label": str(beat.get("beat_type") or beat.get("emotional_register") or ""),
                    "text": item.strip(),
                    "claim_ids": beat.get("claim_ids") if isinstance(beat.get("claim_ids"), list) else fallback_claim_ids,
                }
            )
            changed = True
            continue
        if isinstance(item, dict):
            repaired = dict(item)
            if not repaired.get("id"):
                repaired["id"] = paragraph_id
                changed = True
            if "beat_label" not in repaired and beat.get("beat_type"):
                repaired["beat_label"] = beat["beat_type"]
                changed = True
            if not isinstance(repaired.get("claim_ids"), list) or not repaired.get("claim_ids"):
                repaired["claim_ids"] = beat.get("claim_ids") if isinstance(beat.get("claim_ids"), list) else fallback_claim_ids
                changed = True
            normalized_paragraphs.append(repaired)
            continue
        normalized_paragraphs.append({"id": paragraph_id, "text": str(item), "claim_ids": fallback_claim_ids})
        changed = True

    if changed:
        narration = dict(narration)
        narration["paragraphs"] = normalized_paragraphs

    joined_text = " ".join(normalize_text(str(item.get("text", ""))) for item in normalized_paragraphs)
    narration["elevenlabs_narration"] = joined_text
    narration["spoken_word_count"] = spoken_word_count(joined_text)
    narration.setdefault("target_duration_seconds", input_payload.get("target_duration_seconds", 50))
    return narration


def generate_narration(input_payload: dict[str, Any], *, use_model: bool = False) -> dict[str, Any]:
    if not use_model:
        raise RuntimeError("Narration generation requires --use-model, --use-gemini, or --use-claude. No local fallback script is available.")

    from mav_models import call_model_json

    run_path = run_dir(input_payload["run_id"])
    debug_events: list[dict[str, Any]] = [{"event": "script_generation_started", "use_model": True}]
    fact_lines = "\n".join(f"- {item.get('id')}: {item.get('text')}" for item in input_payload.get("facts", []))
    target_duration = float(input_payload.get("target_duration_seconds", 50))
    bounds = narration_bounds(target_duration)
    regen_instruction = _step_regen_instruction()
    if regen_instruction:
        debug_events.append({"event": "script_regeneration_instruction_received"})

    structure_user_prompt = _with_director_override(
        load_prompt(
            "script_structure.user",
            topic=input_payload["topic"],
            tone=input_payload.get("tone", "patient, precise IGCSE Physics teacher"),
            narrative_mode=input_payload.get("narrative_mode") or "concept_mastery",
            target_duration=target_duration,
            min_words=bounds["min_words"],
            max_words=bounds["max_words"],
            min_paragraphs=bounds["min_paragraphs"],
            max_paragraphs=bounds["max_paragraphs"],
            raw_numbers=input_payload.get("raw_numbers", ""),
            grounded_research=input_payload.get("grounded_research", ""),
            fact_lines=fact_lines,
        ),
        regen_instruction,
    )
    skeleton = call_model_json(
        task="script_structure",
        system=load_prompt("script_structure.system"),
        user=structure_user_prompt,
        output_schema=_script_structure_schema(target_duration),
    )
    if skeleton is None:
        _raise_script_failure(run_path, "Script Structure phase returned no JSON", debug_events)

    write_json(run_path / "story_skeleton.json", skeleton)
    debug_events.append({"event": "story_skeleton_saved", "artifact": "story_skeleton.json", "beats": len(skeleton.get("beats", []))})

    writing_user_prompt = _with_director_override(
        load_prompt(
            "script_writing.user",
            story_skeleton=json.dumps(skeleton, indent=2),
            topic=input_payload["topic"],
            tone=input_payload.get("tone", "patient, precise IGCSE Physics teacher"),
            target_duration=target_duration,
            min_words=bounds["min_words"],
            max_words=bounds["max_words"],
            min_paragraphs=bounds["min_paragraphs"],
            max_paragraphs=bounds["max_paragraphs"],
            fact_lines=fact_lines,
            raw_numbers=input_payload.get("raw_numbers", ""),
            grounded_research=input_payload.get("grounded_research", ""),
        ),
        regen_instruction,
    )
    narration = call_model_json(
        task="script_writing",
        system=load_prompt("script_writing.system"),
        user=writing_user_prompt,
        max_tokens=10000,
        output_schema=_script_writing_schema(target_duration),
    )
    if narration is None:
        _raise_script_failure(run_path, "Script Writing phase returned no JSON", debug_events)

    write_json(run_path / "debug" / "narration_model_raw.json", narration)
    debug_events.append({"event": "script_writing_raw_saved", "artifact": "debug/narration_model_raw.json"})
    narration = _normalize_narration_shape(narration, skeleton, input_payload)
    write_json(run_path / "debug" / "narration_normalized.json", narration)
    debug_events.append({"event": "script_writing_normalized", "artifact": "debug/narration_normalized.json"})

    violations = validate_narration(narration, input_payload)
    if violations:
        violation_payload = [violation.to_dict() for violation in violations]
        strict = os.getenv("MAV_STRICT_NARRATION", "1").strip().lower() not in {"0", "false", "no"}
        write_json(
            run_path / "debug" / "narration_validation_warnings.json",
            {"status": "failed" if strict else "warning", "violations": violation_payload},
        )
        if strict:
            _raise_script_failure(
                run_path,
                "Generated narration failed strict educational script validation",
                debug_events,
                violations=violation_payload,
            )
        debug_events.append(
            {
                "event": "script_writing_validation_warning",
                "message": "Strict validation was disabled; continuing with generated script.",
                "violations": violation_payload,
            }
        )
    else:
        debug_events.append({"event": "script_writing_passed_advisory_validation", "fallback": None})
    write_json(run_path / "debug" / "script_generation_debug.json", debug_events)
    return narration
