"""Compact scene catalogue, route validation, and module-parameter validation."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mav_schema import LAB_ROOT, read_json, write_json

ASSET_REGISTRY_PATH = LAB_ROOT.parent / "video_engine" / "registry" / "animation_assets.json"
COMPACT_CATALOG_PATH = LAB_ROOT / "assets" / "animation_assets.compact.json"
GROUPED_INDEX_PATH = LAB_ROOT / "assets" / "animation_assets.grouped.json"
ALLOWED_ROUTES = {"recipe", "module", "custom"}
MAX_SHORTLISTED_MODULES = 15


def _humanize(value: str) -> str:
    return value.replace("Scene_", "").replace("_", " ").strip()


def build_compact_catalog(*, write: bool = True) -> dict[str, Any]:
    registry = read_json(ASSET_REGISTRY_PATH)
    scenes = []
    for asset in registry.get("scenes", []):
        schema = asset.get("parameter_schema") or {}
        properties = schema.get("properties") or {}
        scenes.append(
            {
                "scene": asset["scene"],
                "category": asset.get("category", "general"),
                "purpose": asset.get("description", ""),
                "can_configure": list(properties),
                "required_parameters": list(schema.get("required") or []),
                "parameter_hints": {
                    key: {
                        field: value[field]
                        for field in ("type", "enum", "minimum", "maximum", "minItems", "maxItems", "maxLength")
                        if field in value
                    }
                    for key, value in properties.items()
                },
                "supports_overlay": True,
                "search_label": _humanize(asset["scene"]),
                "visual_form": asset.get("visual_form", "progressive scientific diagram"),
                "duration_profile": asset.get(
                    "duration_profile", {"min": 5, "ideal": 9, "max": 15}
                ),
                "motion_cues": asset.get(
                    "motion_cues", ["establish the visual", "develop the physics", "reveal the payoff"]
                ),
                "not_suitable_for": asset.get("not_suitable_for", []),
            }
        )
    payload = {"version": "1.0", "scene_count": len(scenes), "scenes": scenes}
    if write:
        write_json(COMPACT_CATALOG_PATH, payload)
    return payload


def compact_catalog() -> dict[str, Any]:
    current = build_compact_catalog(write=False)
    if not COMPACT_CATALOG_PATH.exists() or read_json(COMPACT_CATALOG_PATH) != current:
        write_json(COMPACT_CATALOG_PATH, current)
    return current


def build_grouped_scene_index(*, write: bool = True) -> dict[str, Any]:
    """Build the tiny lesson-level index shown to the shortlisting model."""
    registry = read_json(ASSET_REGISTRY_PATH)
    grouped: dict[str, list[str]] = {}
    for asset in registry.get("scenes", []):
        category = str(asset.get("category") or "general")
        grouped.setdefault(category, []).append(asset["scene"])
    payload = {
        "version": "1.0",
        "scene_count": sum(len(scenes) for scenes in grouped.values()),
        "groups": [{"module": category, "scenes": scenes} for category, scenes in grouped.items()],
    }
    if write:
        write_json(GROUPED_INDEX_PATH, payload)
    return payload


def grouped_scene_index() -> dict[str, Any]:
    current = build_grouped_scene_index(write=False)
    if not GROUPED_INDEX_PATH.exists() or read_json(GROUPED_INDEX_PATH) != current:
        write_json(GROUPED_INDEX_PATH, current)
    return current


def validate_shortlist(payload: dict[str, Any], available_modules: list[str]) -> list[str]:
    errors: list[str] = []
    selected = payload.get("selected_modules")
    if not isinstance(selected, list):
        return ["selected_modules must be an array"]
    if len(selected) > MAX_SHORTLISTED_MODULES:
        errors.append(f"selected_modules allows at most {MAX_SHORTLISTED_MODULES} scenes")
    normalized = [str(item) for item in selected]
    if len(normalized) != len(set(normalized)):
        errors.append("selected_modules must not contain duplicates")
    available = set(available_modules)
    unknown = [item for item in normalized if item not in available]
    if unknown:
        errors.append(f"unknown shortlisted modules: {', '.join(unknown)}")
    return errors


def asset_by_name(scene_name: str) -> dict[str, Any]:
    registry = read_json(ASSET_REGISTRY_PATH)
    for asset in registry.get("scenes", []):
        if asset.get("scene") == scene_name:
            return asset
    raise KeyError(f"Unknown registered module {scene_name}")


def validate_route_plan(
    route_plan: dict[str, Any],
    expected_scene_ids: list[str],
    *,
    allowed_modules: list[str] | None = None,
) -> list[str]:
    errors: list[str] = []
    routes = route_plan.get("routes")
    if not isinstance(routes, list):
        return ["routes must be an array"]
    available = set(allowed_modules) if allowed_modules is not None else {
        scene["scene"] for scene in compact_catalog()["scenes"]
    }
    by_id: dict[str, dict[str, Any]] = {}
    for route in routes:
        if not isinstance(route, dict):
            errors.append("every route must be an object")
            continue
        scene_id = str(route.get("scene_id", ""))
        if scene_id in by_id:
            errors.append(f"duplicate route for {scene_id}")
        by_id[scene_id] = route
        route_type = str(route.get("route", ""))
        if route_type not in ALLOWED_ROUTES:
            errors.append(f"{scene_id}: route must be recipe, module, or custom")
        module = route.get("module")
        if route_type == "module" and module not in available:
            errors.append(f"{scene_id}: unknown module {module!r}")
        if route_type == "recipe" and not str(route.get("recipe_id", "")).strip():
            errors.append(f"{scene_id}: recipe route requires recipe_id")
        if route_type == "custom" and not str(route.get("reason", "")).strip():
            errors.append(f"{scene_id}: custom route requires a reason")
    missing = [scene_id for scene_id in expected_scene_ids if scene_id not in by_id]
    extra = [scene_id for scene_id in by_id if scene_id not in expected_scene_ids]
    if missing:
        errors.append(f"missing routes: {', '.join(missing)}")
    if extra:
        errors.append(f"unexpected routes: {', '.join(extra)}")
    return errors


def _validate_value(value: Any, schema: dict[str, Any], path: str, errors: list[str]) -> None:
    kind = schema.get("type")
    matches = {
        "string": isinstance(value, str),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "array": isinstance(value, list),
        "object": isinstance(value, dict),
    }
    if kind in matches and not matches[kind]:
        errors.append(f"{path} must be {kind}")
        return
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path} must be one of {schema['enum']}")
    if isinstance(value, str) and schema.get("maxLength") is not None and len(value) > int(schema["maxLength"]):
        errors.append(f"{path} exceeds maxLength {schema['maxLength']}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if schema.get("minimum") is not None and value < schema["minimum"]:
            errors.append(f"{path} is below minimum {schema['minimum']}")
        if schema.get("maximum") is not None and value > schema["maximum"]:
            errors.append(f"{path} exceeds maximum {schema['maximum']}")
    if isinstance(value, list):
        if schema.get("minItems") is not None and len(value) < int(schema["minItems"]):
            errors.append(f"{path} requires at least {schema['minItems']} items")
        if schema.get("maxItems") is not None and len(value) > int(schema["maxItems"]):
            errors.append(f"{path} allows at most {schema['maxItems']} items")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                _validate_value(item, item_schema, f"{path}[{index}]", errors)
    if isinstance(value, dict):
        required = schema.get("required") or []
        for key in required:
            if key not in value:
                errors.append(f"{path}.{key} is required")
        properties = schema.get("properties") or {}
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in properties:
                    errors.append(f"{path}.{key} is not allowed")
        for key, child in value.items():
            if key in properties:
                _validate_value(child, properties[key], f"{path}.{key}", errors)


def validate_module_params(scene_name: str, params: dict[str, Any]) -> list[str]:
    asset = asset_by_name(scene_name)
    schema = asset.get("parameter_schema") or {}
    errors: list[str] = []
    _validate_value(params, schema, "params", errors)
    return errors


def router_catalog_text() -> str:
    return json.dumps(compact_catalog(), ensure_ascii=False, separators=(",", ":"))
