"""V3 generative scene planner: asks the model for HTML, CSS, and GSAP per scene."""
from __future__ import annotations

import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

LAB_ROOT = Path(__file__).resolve().parents[1]
if str(LAB_ROOT) not in sys.path:
    sys.path.insert(0, str(LAB_ROOT))

from prompts import load as load_prompt

from mav_assets import (
    MAX_SHORTLISTED_MODULES,
    asset_by_name,
    compact_catalog,
    grouped_scene_index,
    validate_module_params,
    validate_route_plan,
    validate_shortlist,
)
from mav_schema import read_json, run_dir, write_json
from mav_recipes import select_recipe


def _log(message: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] MAV V3: {message}", file=sys.stderr, flush=True)


def _load_word_timestamps(run_path: Path, narration_ids: list[str]) -> list[dict[str, Any]]:
    """Load word timestamps for specific narration paragraphs."""
    path = run_path / "audio_word_timestamps.json"
    if not path.exists():
        return []
    payload = read_json(path)
    id_set = set(narration_ids)
    return [word for word in payload.get("words", []) if word.get("paragraph_id") in id_set]


def _format_word_timestamps(words: list[dict[str, Any]]) -> str:
    """Format word timestamps as a compact list for the prompt."""
    if not words:
        return "(no word-level timestamps available; use narration timing)"
    lines = []
    for word in words:
        lines.append(f"  {float(word.get('start', 0)):.2f}s: \"{word.get('word', '')}\"")
    return "\n".join(lines)


_FACT_OBJECTIVE_ID = re.compile(r"^(?P<topic>\d+(?:_\d+)*)_(?P<route>[CS])(?P<number>\d{2})$", re.IGNORECASE)
_CANONICAL_OBJECTIVE_ID = re.compile(
    r"^(?P<topic>\d+(?:\.\d+)*)-(?P<route>[CS])(?P<number>\d{2})$",
    re.IGNORECASE,
)


def _objective_id_from_claim_id(claim_id: Any) -> str | None:
    """Convert a syllabus fact ID into its canonical objective ID when safe."""
    if not isinstance(claim_id, str):
        return None
    value = claim_id.strip()
    match = _FACT_OBJECTIVE_ID.fullmatch(value)
    if match:
        topic = match.group("topic").replace("_", ".")
    else:
        match = _CANONICAL_OBJECTIVE_ID.fullmatch(value)
        if not match:
            return None
        topic = match.group("topic")
    return f"{topic}-{match.group('route').upper()}{match.group('number')}"


def _merge_narration_timing(narration: dict[str, Any], timing: dict[str, Any]) -> list[dict[str, Any]]:
    """Merge narration paragraphs with timing info."""
    timing_by_id = {item["id"]: item for item in timing.get("paragraphs", [])}
    result = []
    for paragraph in narration.get("paragraphs", []):
        timing_item = timing_by_id.get(paragraph["id"], {})
        result.append(
            {
                "id": paragraph["id"],
                "text": paragraph["text"],
                "beat_label": paragraph.get("beat_label", ""),
                "claim_ids": list(paragraph.get("claim_ids", []))
                if isinstance(paragraph.get("claim_ids", []), list)
                else [],
                "start": float(timing_item.get("start", 0) or 0),
                "end": float(timing_item.get("end", 0) or 0),
                "duration": float(timing_item.get("duration", 0) or 0),
            }
        )
    return result


def _extract_scene_html(response_text: str) -> str | None:
    """Extract the HTML block between scene markers."""
    match = re.search(r"<!--SCENE_HTML_START-->(.*?)<!--SCENE_HTML_END-->", response_text, re.DOTALL)
    if not match:
        return None
    scene_html = match.group(1).strip()
    if "<style" not in scene_html.lower():
        orphan_styles = re.findall(r"<style\b[^>]*>.*?</style>", response_text, flags=re.DOTALL | re.IGNORECASE)
        if orphan_styles:
            scene_html = scene_html.rstrip() + "\n\n" + "\n".join(orphan_styles)
    return scene_html


def _extract_scene_gsap(response_text: str) -> str | None:
    """Extract the GSAP block between scene markers."""
    match = re.search(r"<!--SCENE_GSAP_START-->(.*?)<!--SCENE_GSAP_END-->", response_text, re.DOTALL)
    return match.group(1).strip() if match else None


def _positive_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if not raw_value:
        return default
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a positive integer") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be a positive integer")
    return value


def _positive_float_env(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if not raw_value:
        return default
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a positive number") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be a positive number")
    return value


def _default_visual_identity() -> dict[str, Any]:
    return {
        "persona": "experienced IGCSE Physics teacher and scientific animation director",
        "composition_style": "clean science-notebook explainer with precise diagrams, graphs, experiments, and equations",
        "motion_style": "prediction pauses, causal motion, progressive diagram construction, and restrained camera movement",
        "required_elements": ["physically_meaningful_diagram", "direct_labels_with_units"],
        "forbidden_elements": ["decorative_data", "unlabelled_axis", "text_wall"],
    }


def _load_template_visual_identity(template_id: str) -> dict[str, Any]:
    """Load the visual_identity block from the template's config.json."""
    config_path = LAB_ROOT / "templates" / template_id / "config.json"
    if not config_path.exists():
        _log(f"template config not found for '{template_id}', using default visual identity")
        return _default_visual_identity()
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        identity = config.get("visual_identity")
        if identity:
            return identity
        _log(f"no visual_identity in '{template_id}' config, using default")
    except Exception as exc:  # noqa: BLE001
        _log(f"failed to load template config for '{template_id}': {exc}")
    return _default_visual_identity()


def _text_chunks(text: str) -> list[str]:
    """Split prose at semantic punctuation while preserving the spoken wording."""
    chunks = [match.group(0).strip() for match in re.finditer(r"[^.!?;:]+(?:[.!?;:]+|$)", text)]
    return [chunk for chunk in chunks if chunk] or [text.strip()]


def _token_count(text: str) -> int:
    return max(1, len(re.findall(r"[\w']+", text, flags=re.UNICODE)))


def _split_visual_beats(
    paragraphs: list[dict[str, Any]],
    words: list[dict[str, Any]],
    *,
    target_seconds: float = 11.0,
    max_seconds: float = 15.0,
    min_seconds: float = 5.0,
) -> list[dict[str, Any]]:
    """Create narration-aligned visual beats suitable for one visual idea each."""
    words_by_paragraph: dict[str, list[dict[str, Any]]] = {}
    for word in words:
        words_by_paragraph.setdefault(str(word.get("paragraph_id", "")), []).append(word)

    raw_beats: list[dict[str, Any]] = []
    for paragraph in paragraphs:
        paragraph_words = words_by_paragraph.get(paragraph["id"], [])
        chunks = _text_chunks(paragraph["text"])
        source_tokens = sum(_token_count(chunk) for chunk in chunks)
        cursor = 0
        for chunk_index, chunk in enumerate(chunks):
            next_cursor = cursor + _token_count(chunk)
            if paragraph_words:
                start_index = min(len(paragraph_words) - 1, round(cursor / source_tokens * len(paragraph_words)))
                end_index = min(len(paragraph_words), round(next_cursor / source_tokens * len(paragraph_words)))
                if chunk_index == len(chunks) - 1:
                    end_index = len(paragraph_words)
                end_index = max(start_index + 1, end_index)
                start = float(paragraph_words[start_index].get("start", paragraph["start"]))
                if end_index < len(paragraph_words):
                    end = float(paragraph_words[end_index].get("start", paragraph["end"]))
                else:
                    end = float(paragraph["end"] or paragraph_words[-1].get("end", start))
            else:
                start = paragraph["start"] + paragraph["duration"] * cursor / source_tokens
                end = paragraph["start"] + paragraph["duration"] * next_cursor / source_tokens
            raw_beats.append(
                {
                    "source_paragraph_id": paragraph["id"],
                    "text": chunk,
                    "beat_label": paragraph["beat_label"],
                    "claim_ids": list(paragraph.get("claim_ids", [])),
                    "start": start,
                    "end": max(start + 0.05, end),
                }
            )
            cursor = next_cursor

    # Long clauses are divided near the target duration. This is a visual-shot
    # boundary only; paragraph lineage remains intact for regeneration and tracing.
    divided: list[dict[str, Any]] = []
    for beat in raw_beats:
        duration_seconds = beat["end"] - beat["start"]
        if duration_seconds <= max_seconds:
            divided.append(beat)
            continue
        parts = max(2, int((duration_seconds + target_seconds - 0.001) // target_seconds))
        tokens = beat["text"].split()
        for part in range(parts):
            token_start = round(part / parts * len(tokens))
            token_end = round((part + 1) / parts * len(tokens))
            part_start = beat["start"] + duration_seconds * part / parts
            part_end = beat["start"] + duration_seconds * (part + 1) / parts
            divided.append(
                {
                    **beat,
                    "text": " ".join(tokens[token_start:token_end]).strip(),
                    "start": part_start,
                    "end": part_end,
                }
            )

    # Merge only short adjacent clauses from the same narration paragraph. A beat
    # that already has enough screen time remains an independent visual thought.
    merged: list[dict[str, Any]] = []
    for beat in divided:
        if merged:
            previous = merged[-1]
            combined_duration = beat["end"] - previous["start"]
            same_paragraph = previous["source_paragraph_id"] == beat["source_paragraph_id"]
            previous_is_short = previous["end"] - previous["start"] < min_seconds
            current_is_short = beat["end"] - beat["start"] < min_seconds
            if same_paragraph and (
                (previous_is_short and combined_duration <= max_seconds)
                or (current_is_short and combined_duration <= max_seconds)
            ):
                previous["text"] = f"{previous['text']} {beat['text']}".strip()
                previous["end"] = beat["end"]
                continue
        merged.append(dict(beat))

    visual_beats: list[dict[str, Any]] = []
    paragraph_counts: dict[str, int] = {}
    for beat in merged:
        paragraph_id = beat["source_paragraph_id"]
        paragraph_counts[paragraph_id] = paragraph_counts.get(paragraph_id, 0) + 1
        beat_id = f"{paragraph_id}_v{paragraph_counts[paragraph_id]:02d}"
        visual_beats.append(
            {
                **beat,
                "id": beat_id,
                "duration": beat["end"] - beat["start"],
            }
        )
    return visual_beats


def _words_for_time_range(
    words: list[dict[str, Any]], start: float, end: float
) -> list[dict[str, Any]]:
    return [
        word
        for word in words
        if float(word.get("start", 0)) < end and float(word.get("end", word.get("start", 0))) > start
    ]


def _normalize_cue_tokens(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", value.lower())


def _resolve_cue_points(
    cue_words: list[str],
    words: list[dict[str, Any]],
    *,
    scene_start: float,
    scene_duration: float,
    fallback_count: int,
) -> tuple[list[float], list[str]]:
    """Resolve requested narration phrases to scene-local reveal times."""
    normalized_words = [_normalize_cue_tokens(str(word.get("word", ""))) for word in words]
    flat_words = [tokens[0] if tokens else "" for tokens in normalized_words]
    points: list[float] = []
    resolved_words: list[str] = []
    cursor = 0
    latest = max(0.35, scene_duration - 1.1)
    for cue in cue_words:
        tokens = _normalize_cue_tokens(cue)
        if not tokens:
            continue
        found = None
        for index in range(cursor, len(flat_words) - len(tokens) + 1):
            if flat_words[index : index + len(tokens)] == tokens:
                found = index
                break
        if found is None:
            continue
        raw_point = float(words[found].get("start", scene_start)) - scene_start - 0.28
        point = round(min(latest, max(0.35, raw_point)), 3)
        if not points or point > points[-1] + 0.08:
            points.append(point)
            resolved_words.append(cue)
        cursor = found + len(tokens)

    desired_count = max(1, fallback_count)
    if not points:
        span_start = min(0.7, scene_duration * 0.12)
        span_end = max(span_start, scene_duration - 1.25)
        points = [round(span_start + (span_end - span_start) * index / max(1, desired_count - 1), 3) for index in range(desired_count)]
    return points, resolved_words


def _validate_layout_json(layout: dict[str, Any], scene_id: str) -> None:
    """Validate that element IDs and GSAP target_ids match across all beats."""
    for beat in layout.get("beats", []):
        beat_id = beat.get("beat_id", "?")
        element_ids = {el["id"] for el in beat.get("layout", {}).get("elements", [])}
        gsap_targets = {entry["target_id"] for entry in beat.get("gsap_choreography", [])}
        # Warn on mismatches but do not hard-fail; the coder may still resolve them
        unmatched_targets = gsap_targets - element_ids
        if unmatched_targets:
            _log(
                f"WARNING {scene_id} beat {beat_id}: GSAP targets not in elements: "
                + ", ".join(sorted(unmatched_targets))
            )


def _route_output_schema(scene_ids: list[str], module_names: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "routes": {
                "type": "array",
                "minItems": len(scene_ids),
                "maxItems": len(scene_ids),
                "items": {
                    "type": "object",
                    "properties": {
                        "scene_id": {"type": "string", "enum": scene_ids},
                        "route": {"type": "string", "enum": ["module", "custom"]},
                        "module": {"type": "string"},
                        "alternatives": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
                        "reason": {"type": "string"},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "parameter_guidance": {"type": "string"},
                    },
                    "required": ["scene_id", "route", "reason", "confidence", "alternatives", "parameter_guidance"],
                },
            }
        },
        "required": ["routes"],
    }


def _shortlist_output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "selected_modules": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": MAX_SHORTLISTED_MODULES,
            },
            "reason": {"type": "string"},
        },
        "required": ["selected_modules", "reason"],
    }


def _parameter_output_schema(parameter_schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "params": parameter_schema,
            "cue_words": {
                "type": "array",
                "maxItems": 8,
                "items": {"type": "string", "maxLength": 60},
            },
        },
        "required": ["params"],
    }


def load_v3_plan_with_scene_files(run_path: Path) -> dict[str, Any]:
    """Load scene_plan_v3.json and apply editable per-scene JSON overrides."""
    plan = read_json(run_path / "scene_plan_v3.json")
    scene_dir = run_path / "v3_scenes"
    if not scene_dir.exists():
        return plan
    merged_scenes = []
    for scene in plan.get("scenes", []):
        scene_path = scene_dir / f"{scene['id']}.json"
        if scene_path.exists():
            override = read_json(scene_path)
            for key in ("id", "paragraph_id", "start", "duration", "beat_label", "narration_text"):
                override.setdefault(key, scene.get(key))
            merged_scenes.append(override)
        else:
            merged_scenes.append(scene)
    plan["scenes"] = merged_scenes
    plan["scene_count"] = len(merged_scenes)
    return plan


def generate_v3_scenes(
    input_payload: dict[str, Any],
    narration: dict[str, Any],
    timing: dict[str, Any],
    *,
    target_scene_id: str | None = None,
    allow_model_fallback: bool = True,
) -> dict[str, Any]:
    """Compile grounded recipes locally, with an explicit legacy model fallback."""
    from mav_models import call_model_json, call_model_text

    run_path = run_dir(input_payload["run_id"])
    paragraphs_with_timing = _merge_narration_timing(narration, timing)
    template_id = input_payload.get("template_id", "physics")
    visual_identity = _load_template_visual_identity(template_id)

    # Build system prompts with visual identity injected
    design_system = load_prompt("v3_design_system")
    creative_director_system = load_prompt(
        "v3_creative_director.system",
        design_system=design_system,
        template_persona=visual_identity["persona"],
        template_composition_style=visual_identity["composition_style"],
        template_required_elements=", ".join(visual_identity.get("required_elements", [])) or "(none specified)",
        template_forbidden_elements=", ".join(visual_identity.get("forbidden_elements", [])) or "(none specified)",
    )
    coder_system = load_prompt("v3_scene_coder.system")
    scene_regen_instruction = os.getenv("MAV_SCENE_REGEN_INSTRUCTION", "").strip()
    step_regen_instruction = os.getenv("MAV_STEP_REGEN_INSTRUCTION", "").strip()
    director_instruction = scene_regen_instruction or step_regen_instruction

    title = narration.get("title", input_payload.get("topic", ""))
    topic = input_payload.get("topic", "")

    all_word_ts = _load_word_timestamps(run_path, [paragraph["id"] for paragraph in paragraphs_with_timing])
    target_shot_seconds = _positive_float_env("MAV_V3_TARGET_SHOT_SECONDS", 11.0)
    max_shot_seconds = _positive_float_env("MAV_V3_MAX_SHOT_SECONDS", 15.0)
    min_shot_seconds = _positive_float_env("MAV_V3_MIN_SHOT_SECONDS", 5.0)
    if not min_shot_seconds <= target_shot_seconds <= max_shot_seconds:
        raise RuntimeError("Visual shot timing must satisfy MIN <= TARGET <= MAX")
    visual_beats = _split_visual_beats(
        paragraphs_with_timing,
        all_word_ts,
        target_seconds=target_shot_seconds,
        max_seconds=max_shot_seconds,
        min_seconds=min_shot_seconds,
    )
    # Each route now owns one visual thought. Custom scenes can still contain
    # internal reveals, but unrelated narration paragraphs are never bundled.
    scene_groups = [[beat] for beat in visual_beats]
    total_scenes = len(scene_groups)

    catalog = compact_catalog()
    all_module_names = [scene["scene"] for scene in catalog["scenes"]]
    simple_index = grouped_scene_index()
    write_json(run_path / "asset_index_used.json", simple_index)
    scene_ids = [f"scene_{index + 1:02d}" for index in range(total_scenes)]
    routes_path = run_path / "scene_routes.json"
    route_groups = [
        {
            "scene_id": scene_ids[index],
            "start": group[0]["start"],
            "duration": group[-1]["end"] - group[0]["start"],
            "beats": [{"id": beat["id"], "label": beat["beat_label"], "text": beat["text"]} for beat in group],
        }
        for index, group in enumerate(scene_groups)
    ]

    occurrence_by_objective: dict[str, int] = {}
    recipe_selections: dict[str, dict[str, Any]] = {}
    recipe_routes: dict[str, dict[str, Any]] = {}
    for index, group in enumerate(scene_groups):
        scene_id = scene_ids[index]
        claim_ids = [
            claim_id
            for beat in group
            for claim_id in beat.get("claim_ids", [])
            if isinstance(claim_id, str)
        ]
        objective_ids = list(
            dict.fromkeys(
                objective_id
                for claim_id in claim_ids
                if (objective_id := _objective_id_from_claim_id(claim_id)) is not None
            )
        )
        # Topic hooks have no objective claim of their own. Constrain their
        # recipe search to this lesson's declared objectives rather than prose.
        if not objective_ids and "syllabus_topic" in claim_ids:
            objective_ids = list(input_payload.get("objective_ids") or [])
        selection = select_recipe(
            objective_ids,
            group[0].get("beat_label", ""),
            " ".join(beat.get("text", "") for beat in group),
            occurrence_by_objective,
        )
        if not selection:
            continue
        selected_objective = selection["selection"]["objective_id"]
        occurrence_by_objective[selected_objective] = occurrence_by_objective.get(selected_objective, 0) + 1
        recipe_selections[scene_id] = selection
        recipe_routes[scene_id] = {
            "scene_id": scene_id,
            "route": "recipe",
            "recipe_id": selection["selection"]["recipe_id"],
            "objective_id": selected_objective,
            "reason": "Selected locally from the objective-constrained visual recipe registry.",
            "confidence": 1.0,
            "alternatives": [],
            "parameter_guidance": "Typed recipe parameters are already grounded and validated.",
        }

    uncovered_ids = [scene_id for scene_id in scene_ids if scene_id not in recipe_routes]
    write_json(
        run_path / "objective_recipe_coverage.json",
        {
            "version": "1.0",
            "scene_count": total_scenes,
            "covered_scene_count": len(recipe_routes),
            "uncovered_scene_count": len(uncovered_ids),
            "covered": [recipe_routes[scene_id] for scene_id in scene_ids if scene_id in recipe_routes],
            "uncovered_scene_ids": uncovered_ids,
        },
    )

    cached_routes: dict[str, dict[str, Any]] = {}
    if target_scene_id and routes_path.exists():
        cached_plan = read_json(routes_path)
        cached_routes = {route["scene_id"]: route for route in cached_plan.get("routes", [])}
        _log("loading cached lesson-level asset routes for surgical scene regeneration")

    legacy_routes: dict[str, dict[str, Any]] = {
        scene_id: route
        for scene_id, route in cached_routes.items()
        if scene_id in uncovered_ids
    }
    needs_live_routing = [scene_id for scene_id in uncovered_ids if scene_id not in legacy_routes]
    module_names: list[str] = []
    if needs_live_routing:
        if not allow_model_fallback:
            raise RuntimeError(
                "Deterministic scene coverage is incomplete for "
                + ", ".join(needs_live_routing)
                + ". Add objective recipes or rerun with an explicit model provider to use the legacy fallback."
            )
        uncovered_groups = [group for group in route_groups if group["scene_id"] in needs_live_routing]
        shortlist_request = {
            "topic": topic,
            "title": title,
            "scene_groups": uncovered_groups,
            "available_scene_index": simple_index["groups"],
        }
        write_json(run_path / "debug" / "scene_asset_shortlister_request.json", shortlist_request)
        write_json(run_path / "asset_index_used.json", simple_index)
        _log(
            f"asset shortlister: sending a simple {len(simple_index['groups'])}-group / "
            f"{len(all_module_names)}-scene index for {len(uncovered_groups)} uncovered narration groups"
        )
        shortlist = call_model_json(
            task="scene_asset_shortlister",
            system=load_prompt("scene_asset_shortlister.system"),
            user=json.dumps(shortlist_request, ensure_ascii=False, separators=(",", ":")),
            max_tokens=4000,
            output_schema=_shortlist_output_schema(),
        )
        if not shortlist:
            raise RuntimeError("Scene asset shortlister returned no result")
        shortlist_errors = validate_shortlist(shortlist, all_module_names)
        if shortlist_errors:
            write_json(
                run_path / "debug" / "scene_asset_shortlister_invalid.json",
                {"shortlist": shortlist, "errors": shortlist_errors},
            )
            raise RuntimeError(f"Scene asset shortlister returned an invalid shortlist: {shortlist_errors}")
        module_names = shortlist["selected_modules"]
        shortlist["registry_scene_count"] = len(all_module_names)
        write_json(run_path / "asset_shortlist.json", shortlist)
        selected_names = set(module_names)
        selected_catalog = {
            "version": catalog["version"],
            "scene_count": len(module_names),
            "scenes": [scene for scene in catalog["scenes"] if scene["scene"] in selected_names],
        }
        write_json(run_path / "asset_catalog_used.json", selected_catalog)
        _log(
            f"asset shortlister: selected {len(module_names)} of {len(all_module_names)} modules"
            + (f" → {', '.join(module_names)}" if module_names else "; router will consider custom scenes only")
        )
        router_request = {
            "topic": topic,
            "title": title,
            "grounded_objective_ids": input_payload.get("objective_ids", []),
            "scene_groups": uncovered_groups,
            "shortlisted_modules": selected_catalog["scenes"],
        }
        write_json(run_path / "debug" / "scene_asset_router_request.json", router_request)
        _log(
            f"asset router: sending detailed cards for only {len(module_names)} shortlisted modules "
            f"across {len(uncovered_groups)} uncovered scene groups"
        )
        route_plan = call_model_json(
            task="scene_asset_router",
            system=load_prompt("scene_asset_router.system"),
            user=json.dumps(router_request, ensure_ascii=False, separators=(",", ":")),
            max_tokens=12000,
            output_schema=_route_output_schema(needs_live_routing, module_names),
        )
        if not route_plan:
            raise RuntimeError("Scene asset router returned no routing plan")
        route_errors = validate_route_plan(route_plan, needs_live_routing, allowed_modules=module_names)
        if route_errors:
            write_json(run_path / "debug" / "scene_asset_router_invalid.json", {"routes": route_plan, "errors": route_errors})
            raise RuntimeError(f"Scene asset router returned an invalid plan: {route_errors}")
        legacy_routes.update({route["scene_id"]: route for route in route_plan["routes"]})
    elif cached_routes:
        module_names = list(read_json(routes_path).get("shortlisted_modules") or all_module_names)
    else:
        write_json(
            run_path / "asset_shortlist.json",
            {
                "selected_modules": [],
                "reason": "All visual beats were covered by deterministic objective recipes.",
                "registry_scene_count": len(all_module_names),
            },
        )
        write_json(
            run_path / "asset_catalog_used.json",
            {"version": catalog["version"], "scene_count": 0, "scenes": []},
        )

    combined_routes = {
        **legacy_routes,
        **recipe_routes,
    }
    route_plan = {
        "version": "2.0",
        "planner": "objective_recipe_first",
        "routes": [combined_routes[scene_id] for scene_id in scene_ids if scene_id in combined_routes],
        "shortlisted_modules": module_names,
        "shortlisted_scene_count": len(module_names),
        "registry_scene_count": len(all_module_names),
        "recipe_scene_count": len(recipe_routes),
    }
    write_json(routes_path, route_plan)
    route_errors = validate_route_plan(route_plan, scene_ids, allowed_modules=module_names)
    if route_errors:
        raise RuntimeError(f"Cached scene routing plan is invalid: {route_errors}")
    routes_by_id = {route["scene_id"]: route for route in route_plan["routes"]}

    existing_scenes: dict[str, dict[str, Any]] = {}
    if target_scene_id:
        existing_path = run_path / "scene_plan_v3.json"
        if not existing_path.exists():
            raise RuntimeError("--v3-scene-id requires an existing scene_plan_v3.json")
        existing_plan = load_v3_plan_with_scene_files(run_path)
        existing_scenes = {scene["id"]: scene for scene in existing_plan.get("scenes", [])}

    _log(
        f"starting scene generation: run={input_payload['run_id']} "
        f"paragraphs={len(paragraphs_with_timing)} visual_beats={len(visual_beats)} "
        f"scenes={total_scenes} template={template_id}"
        + (f" target_scene={target_scene_id}" if target_scene_id else "")
    )

    def generate_scene_group(group_index: int, beat_group: list[dict[str, Any]]) -> dict[str, Any]:
        scene_id = f"scene_{group_index + 1:02d}"
        route = routes_by_id[scene_id]
        scene_number = group_index + 1
        canvas_start = beat_group[0]["start"]
        canvas_end = beat_group[-1]["end"]
        canvas_duration = canvas_end - canvas_start

        # Collect word timestamps for all beats in this group
        word_ts = _words_for_time_range(all_word_ts, canvas_start, canvas_end)
        word_timestamps = _format_word_timestamps(word_ts)
        claim_ids = list(
            dict.fromkeys(
                claim_id.strip()
                for beat in beat_group
                for claim_id in beat.get("claim_ids", [])
                if isinstance(claim_id, str) and claim_id.strip()
            )
        )
        objective_ids = list(
            dict.fromkeys(
                objective_id
                for claim_id in claim_ids
                if (objective_id := _objective_id_from_claim_id(claim_id)) is not None
            )
        )

        common_scene = {
            "id": scene_id,
            "paragraph_id": beat_group[0]["source_paragraph_id"],
            "source_paragraph_ids": list(dict.fromkeys(p["source_paragraph_id"] for p in beat_group)),
            "beat_ids": [p["id"] for p in beat_group],
            "claim_ids": claim_ids,
            "objective_ids": objective_ids,
            "start": canvas_start,
            "duration": canvas_duration,
            "beat_label": beat_group[0]["beat_label"],
            "narration_text": " ".join(p["text"] for p in beat_group),
            "route": route["route"],
            "routing": route,
        }

        if route["route"] == "recipe":
            selection = recipe_selections.get(scene_id)
            if not selection:
                raise RuntimeError(f"Missing deterministic recipe selection for {scene_id}")
            recipe = selection["recipe"]
            matched_cues = [str(value) for value in selection["selection"].get("cue_matches", [])]
            cue_points, resolved_cue_words = _resolve_cue_points(
                matched_cues,
                word_ts,
                scene_start=canvas_start,
                scene_duration=canvas_duration,
                fallback_count=max(1, min(8, len(recipe.get("actions") or []))),
            )
            scene = {
                **common_scene,
                "renderer": "recipe",
                "recipe": recipe,
                "recipe_selection": selection["selection"],
                "timing": {
                    "cue_points": cue_points,
                    "cue_words": resolved_cue_words,
                    "final_hold_seconds": min(1.25, max(0.8, canvas_duration * 0.12)),
                },
                "scene_html": "",
                "scene_gsap": "",
            }
            write_json(run_path / "v3_scenes" / f"{scene_id}.json", scene)
            _log(f"{scene_id}: compiled local recipe {recipe['id']}")
            return scene

        if not allow_model_fallback:
            raise RuntimeError(
                f"{scene_id} uses legacy {route['route']} routing, but no model fallback was enabled"
            )

        if route["route"] == "module":
            module_name = route["module"]
            asset = asset_by_name(module_name)
            parameter_request = {
                "scene_id": scene_id,
                "selected_module": module_name,
                "module_description": asset.get("description", ""),
                "parameter_schema": asset.get("parameter_schema", {}),
                "router_reason": route.get("reason", ""),
                "parameter_guidance": route.get("parameter_guidance", ""),
                "duration": canvas_duration,
                "narration": [p["text"] for p in beat_group],
                "word_timestamps": word_ts,
                "available_motion_cues": asset.get("motion_cues", []),
                "duration_profile": asset.get("duration_profile", {}),
                "grounded_facts": input_payload.get("facts", []),
            }
            write_json(run_path / "debug" / "module_parameters" / f"{scene_id}_request.json", parameter_request)
            _log(f"{scene_id}: module route → {module_name}; generating schema-constrained parameters")
            parameter_output = call_model_json(
                task="module_parameterizer",
                system=load_prompt("module_parameterizer.system"),
                user=json.dumps(parameter_request, ensure_ascii=False),
                max_tokens=12000,
                output_schema=_parameter_output_schema(asset.get("parameter_schema", {})),
            )
            if not parameter_output or not isinstance(parameter_output.get("params"), dict):
                raise RuntimeError(f"Module parameterizer returned no params for {scene_id}")
            params = parameter_output["params"]
            requested_cues = [str(value) for value in parameter_output.get("cue_words", [])]
            motion_cues = asset.get("motion_cues") or []
            cue_points, resolved_cue_words = _resolve_cue_points(
                requested_cues,
                word_ts,
                scene_start=canvas_start,
                scene_duration=canvas_duration,
                fallback_count=len(motion_cues) or 3,
            )
            parameter_errors = validate_module_params(module_name, params)
            write_json(
                run_path / "debug" / "module_parameters" / f"{scene_id}_result.json",
                {
                    "module": module_name,
                    "params": params,
                    "cue_words": requested_cues,
                    "resolved_cue_words": resolved_cue_words,
                    "cue_points": cue_points,
                    "validation_errors": parameter_errors,
                },
            )
            if parameter_errors:
                raise RuntimeError(f"Invalid parameters for {scene_id} {module_name}: {parameter_errors}")
            scene = {
                **common_scene,
                "renderer": "module",
                "module": {"scene": module_name, "params": params},
                "timing": {
                    "cue_points": cue_points,
                    "cue_words": resolved_cue_words,
                    "final_hold_seconds": min(1.25, max(0.8, canvas_duration * 0.12)),
                },
                "scene_html": "",
                "scene_gsap": "",
            }
            write_json(run_path / "v3_scenes" / f"{scene_id}.json", scene)
            _log(f"{scene_id}: saved deterministic {module_name} scene")
            return scene

        # Build beats summary for creative director prompt
        beats_summary_lines = []
        for beat_index, paragraph in enumerate(beat_group):
            beat_num = f"b{beat_index + 1:02d}"
            beats_summary_lines.append(
                f"BEAT {beat_num} [{paragraph['beat_label']}] "
                f"time={paragraph['start']:.2f}s\u2013{paragraph['end']:.2f}s "
                f"({paragraph['duration']:.2f}s):\n{paragraph['text']}"
            )
        beats_summary = "\n\n".join(beats_summary_lines)

        creative_user_prompt = (
            f"SCENE: {scene_id}\n"
            f"SCENE GROUP: {scene_number} of {total_scenes}\n"
            f"CANVAS START: {canvas_start:.3f}s\n"
            f"CANVAS DURATION: {canvas_duration:.3f}s\n"
            f"BEATS IN THIS SCENE: {len(beat_group)}\n"
            f"VIDEO TITLE: {title}\n"
            f"TOPIC: {topic}\n\n"
            f"ASSET ROUTER DECISION: custom\n"
            f"CUSTOM JUSTIFICATION: {route.get('reason', '')}\n"
            f"REJECTED MODULE ALTERNATIVES: {', '.join(route.get('alternatives', [])) or '(none)'}\n\n"
            f"=== BEATS ===\n{beats_summary}\n\n"
            f"=== WORD TIMESTAMPS ===\n{word_timestamps}\n\n"
            "Design the layout JSON for this narration-aligned visual scene. "
            "Use beat IDs b01, b02, b03 etc. and prefix all element IDs with the beat number."
        )
        if director_instruction:
            creative_user_prompt += (
                "\n\n=== DIRECTOR OVERRIDE ===\n"
                f"{director_instruction}\n"
                "Honor this direction while preserving beat namespacing and the ID contract."
            )

        _log(
            f"{scene_id} ({scene_number}/{total_scenes}): step 1 \u2014 creative director "
            f"beats={len(beat_group)} canvas={canvas_duration:.1f}s"
        )

        # STEP 1: GLM-5.2 creative director → Layout JSON
        layout_json = call_model_json(
            task="v3_creative_director",
            system=creative_director_system,
            user=creative_user_prompt,
            max_tokens=16000,
        )
        if not layout_json:
            raise RuntimeError(f"Creative director returned no output for {scene_id}")

        _validate_layout_json(layout_json, scene_id)
        _log(f"{scene_id}: step 1 complete — layout JSON has {len(layout_json.get('beats', []))} beats")

        # STEP 2: Kimi K2 coder → HTML/CSS/GSAP
        coder_user_prompt = (
            f"Translate this Layout JSON into production HTML/CSS/GSAP code for scene {scene_id}:\n\n"
            f"{json.dumps(layout_json, indent=2)}"
        )
        _log(f"{scene_id}: step 2 \u2014 Kimi K2 code generation")
        code_response = call_model_text(
            task="v3_scene_coder",
            system=coder_system,
            user=coder_user_prompt,
            max_tokens=32000,
        )
        if not code_response:
            raise RuntimeError(f"Scene coder returned no output for {scene_id}")

        scene_html = _extract_scene_html(code_response)
        scene_gsap = _extract_scene_gsap(code_response)
        if not scene_html:
            raise RuntimeError(f"Scene coder did not return valid HTML for {scene_id}")
        if not scene_gsap:
            raise RuntimeError(f"Scene coder did not return valid GSAP for {scene_id}")

        _log(
            f"{scene_id}: step 2 complete "
            f"(html={len(scene_html):,} chars, gsap={len(scene_gsap):,} chars)"
        )

        scene = {
            **common_scene,
            "renderer": "v3_custom",
            "scene_html": scene_html,
            "scene_gsap": scene_gsap,
            "layout_json": layout_json,
            "raw_code_response": code_response,
        }
        write_json(run_path / "v3_scenes" / f"{scene_id}.json", scene)
        _log(f"{scene_id}: saved v3_scenes/{scene_id}.json")
        return scene

    scenes: list[dict[str, Any] | None] = [None] * total_scenes
    generation_jobs: list[tuple[int, list[dict[str, Any]]]] = []
    for group_index, beat_group in enumerate(scene_groups):
        scene_id = f"scene_{group_index + 1:02d}"
        if target_scene_id and scene_id != target_scene_id:
            if scene_id not in existing_scenes:
                raise RuntimeError(f"Cannot preserve {scene_id}: missing from existing V3 plan")
            scenes[group_index] = existing_scenes[scene_id]
            continue
        generation_jobs.append((group_index, beat_group))

    # Sequential execution to leverage Z.AI context caching on the creative director system prompt
    workers = _positive_int_env("MAV_V3_SCENE_CONCURRENCY", 1)
    _log(f"dispatching {len(generation_jobs)} scene group(s) with concurrency={workers}")
    if workers == 1:
        for group_index, beat_group in generation_jobs:
            scenes[group_index] = generate_scene_group(group_index, beat_group)
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_index = {
                executor.submit(generate_scene_group, gi, bg): gi for gi, bg in generation_jobs
            }
            try:
                for future in as_completed(future_to_index):
                    scenes[future_to_index[future]] = future.result()
            except Exception:
                for future in future_to_index:
                    future.cancel()
                raise

    ordered_scenes = [scene for scene in scenes if scene is not None]
    if len(ordered_scenes) != total_scenes:
        raise RuntimeError("V3 scene generation ended with missing scene outputs")

    plan = {
        "version": "4.0",
        "planner_mode": "objective_recipe_first",
        "run_id": input_payload["run_id"],
        "title": title,
        "template_id": template_id,
        "segmentation": {
            "mode": "narration_aligned_visual_beats",
            "target_seconds": target_shot_seconds,
            "max_seconds": max_shot_seconds,
            "min_seconds": min_shot_seconds,
            "source_paragraph_count": len(paragraphs_with_timing),
            "visual_beat_count": len(visual_beats),
        },
        "duration": timing["audio_duration_seconds"],
        "scene_count": len(ordered_scenes),
        "routing_summary": {
            "recipe": sum(scene.get("renderer") == "recipe" for scene in ordered_scenes),
            "module": sum(scene.get("renderer") == "module" for scene in ordered_scenes),
            "custom": sum(scene.get("renderer") not in {"recipe", "module"} for scene in ordered_scenes),
            "shortlisted_scene_count": len(module_names),
            "registry_scene_count": len(all_module_names),
        },
        "scenes": ordered_scenes,
    }
    write_json(run_path / "scene_plan_v3.json", plan)
    _log(f"wrote scene_plan_v3.json with {len(ordered_scenes)} narration-aligned visual scenes")
    return plan
