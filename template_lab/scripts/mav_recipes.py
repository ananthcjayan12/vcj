"""Deterministic syllabus-grounded visual recipe selection.

Recipes are deliberately data-only.  The browser compiler may translate the
validated node and action vocabulary into DOM/SVG/GSAP, but a recipe cannot
carry executable code or arbitrary markup itself.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any


LAB_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST_PATH = LAB_ROOT / "assets" / "objective_visual_recipes.json"

WORKBENCHES = (
    "Measurement and apparatus",
    "Mechanics, forces and vectors",
    "Materials and fluids",
    "Energy and system flow",
    "Matter and thermal physics",
    "Waves, optics and signals",
    "Fields, charge and magnetism",
    "Circuits and electrical systems",
    "Electromagnetic devices",
    "Atomic and nuclear physics",
    "Space, scale and timelines",
)

LAYOUT_TYPES = {
    "canvas",
    "cause_effect",
    "classification",
    "comparison",
    "evidence_zoom",
    "experiment",
    "experiment_bench",
    "instrument_demo",
    "prediction_reveal",
    "scale_drawing",
    "simulation_graph",
    "system_flow",
    "timeline",
    "worked_example",
}

NODE_TYPES = {
    "answer_cover",
    "apparatus",
    "axis",
    "bar",
    "callout",
    "clock",
    "counter",
    "digital_timer",
    "divider",
    "equation",
    "error_bar",
    "eye",
    "graph",
    "label",
    "line",
    "liquid",
    "measurement",
    "measuring_cylinder",
    "meniscus",
    "object",
    "particles",
    "pendulum",
    "quantity_card",
    "ray",
    "region",
    "ruler",
    "scale_key",
    "sight_line",
    "stopwatch",
    "text",
    "timeline",
    "vector",
}

ACTION_TYPES = {
    "classify",
    "compare",
    "count",
    "draw",
    "fill",
    "hide",
    "highlight",
    "measure",
    "move",
    "oscillate",
    "persist",
    "reveal",
    "reveal_answer",
    "rotate",
    "scale",
    "trace",
    "update",
}

RECIPE_FIELDS = {"id", "workbench", "layout", "title", "subtitle", "nodes", "actions"}
RECIPE_REQUIRED_FIELDS = {"id", "workbench", "layout", "nodes", "actions"}
NODE_FIELDS = {
    "id",
    "type",
    "x",
    "y",
    "width",
    "height",
    "label",
    "text",
    "value",
    "unit",
    "color",
    "hidden",
    "answer",
    "percent",
    "role",
    "orientation",
    "kind",
    "items",
    "points",
    "minimum",
    "maximum",
    "min",
    "max",
    "reading",
    "scale",
    "magnitude",
    "direction",
    "count",
    "decimals",
    "state",
    "x2",
    "y2",
    "xLabel",
    "yLabel",
}
NODE_REQUIRED_FIELDS = {"id", "type", "x", "y", "width", "height"}
ACTION_FIELDS = {
    "type",
    "target",
    "at",
    "duration",
    "to",
    "value",
    "label",
    "count",
    "amplitude",
    "direction",
    "ease",
}
ACTION_REQUIRED_FIELDS = {"type", "target", "at", "duration"}
FORBIDDEN_DATA_KEYS = {
    "html",
    "raw_html",
    "css",
    "raw_css",
    "javascript",
    "js",
    "script",
    "svg",
    "svg_markup",
    "svg_path",
    "path",
    "path_data",
    "d",
}

_ID_RE = re.compile(r"^[a-z][a-z0-9_]*(?:-[a-z0-9]+)*$")
_OBJECTIVE_RE = re.compile(r"^\d+(?:\.\d+)*-[CS]\d{2,}$")
_CLAIM_OBJECTIVE_RE = re.compile(
    r"^(?P<topic>\d+(?:[._]\d+)*)[._-](?P<route>[CS])(?P<number>\d+)(?:[._].*)?$",
    re.IGNORECASE,
)


class RecipeManifestError(ValueError):
    """Raised when the on-disk recipe manifest violates its data contract."""

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _unknown_fields(value: dict[str, Any], allowed: set[str], path: str) -> list[str]:
    return [f"{path}.{key} is not allowed" for key in value if key not in allowed]


def _forbidden_key_errors(value: Any, path: str = "recipe") -> list[str]:
    errors: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in FORBIDDEN_DATA_KEYS:
                errors.append(f"{path}.{key} is an unsafe executable or markup field")
            errors.extend(_forbidden_key_errors(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            errors.extend(_forbidden_key_errors(child, f"{path}[{index}]"))
    return errors


def _validate_text(value: Any, path: str, errors: list[str], *, required: bool = False) -> None:
    if value is None and not required:
        return
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{path} must be a non-empty string")
    elif len(value) > 240:
        errors.append(f"{path} must be at most 240 characters")


def _validate_normalized_number(value: Any, path: str, errors: list[str]) -> None:
    if not _is_number(value) or not 0 <= float(value) <= 1:
        errors.append(f"{path} must be a normalized number from 0 to 1")


def validate_recipe(recipe: Any) -> list[str]:
    """Return contract violations for one browser recipe."""
    if not isinstance(recipe, dict):
        return ["recipe must be an object"]

    errors = _forbidden_key_errors(recipe)
    errors.extend(_unknown_fields(recipe, RECIPE_FIELDS, "recipe"))
    for field in sorted(RECIPE_REQUIRED_FIELDS - set(recipe)):
        errors.append(f"recipe.{field} is required")

    recipe_id = recipe.get("id")
    if not isinstance(recipe_id, str) or not _ID_RE.fullmatch(recipe_id):
        errors.append("recipe.id must be a lowercase stable identifier")
    if recipe.get("workbench") not in WORKBENCHES:
        errors.append("recipe.workbench is not a registered workbench")
    if recipe.get("layout") not in LAYOUT_TYPES:
        errors.append("recipe.layout is not a registered layout")
    _validate_text(recipe.get("title"), "recipe.title", errors)
    _validate_text(recipe.get("subtitle"), "recipe.subtitle", errors)

    nodes = recipe.get("nodes")
    node_ids: set[str] = set()
    if not isinstance(nodes, list) or not nodes:
        errors.append("recipe.nodes must be a non-empty list")
        nodes = []
    for index, node in enumerate(nodes):
        path = f"recipe.nodes[{index}]"
        if not isinstance(node, dict):
            errors.append(f"{path} must be an object")
            continue
        errors.extend(_unknown_fields(node, NODE_FIELDS, path))
        for field in sorted(NODE_REQUIRED_FIELDS - set(node)):
            errors.append(f"{path}.{field} is required")
        node_id = node.get("id")
        if not isinstance(node_id, str) or not _ID_RE.fullmatch(node_id):
            errors.append(f"{path}.id must be a lowercase stable identifier")
        elif node_id in node_ids:
            errors.append(f"{path}.id duplicates {node_id}")
        else:
            node_ids.add(node_id)
        if node.get("type") not in NODE_TYPES:
            errors.append(f"{path}.type is not a registered node type")
        for field in ("x", "y", "width", "height"):
            _validate_normalized_number(node.get(field), f"{path}.{field}", errors)
        x, y, width, height = (node.get(field) for field in ("x", "y", "width", "height"))
        if all(_is_number(value) for value in (x, y, width, height)):
            if float(width) <= 0 or float(height) <= 0:
                errors.append(f"{path} width and height must be positive")
            if float(x) + float(width) > 1.000001 or float(y) + float(height) > 1.000001:
                errors.append(f"{path} geometry must remain inside the normalized canvas")
        for field in (
            "label",
            "text",
            "unit",
            "color",
            "role",
            "orientation",
            "kind",
            "state",
            "xLabel",
            "yLabel",
        ):
            _validate_text(node.get(field), f"{path}.{field}", errors)
        if "direction" in node and not isinstance(node["direction"], (str, int, float)):
            errors.append(f"{path}.direction must be a string or number")
        for field in ("hidden", "answer"):
            if field in node and not isinstance(node[field], bool):
                errors.append(f"{path}.{field} must be a boolean")
        if "items" in node and (
            not isinstance(node["items"], list)
            or not node["items"]
            or not all(isinstance(item, str) and item.strip() for item in node["items"])
        ):
            errors.append(f"{path}.items must be a non-empty list of strings")
        if "points" in node:
            points = node["points"]
            if not isinstance(points, list) or len(points) < 2:
                errors.append(f"{path}.points must contain at least two normalized points")
            else:
                for point_index, point in enumerate(points):
                    point_path = f"{path}.points[{point_index}]"
                    if not isinstance(point, dict) or set(point) - {"x", "y", "label"}:
                        errors.append(f"{point_path} must contain only x, y, and optional label")
                        continue
                    _validate_normalized_number(point.get("x"), f"{point_path}.x", errors)
                    _validate_normalized_number(point.get("y"), f"{point_path}.y", errors)
                    _validate_text(point.get("label"), f"{point_path}.label", errors)
        for field in (
            "minimum",
            "maximum",
            "min",
            "max",
            "reading",
            "scale",
            "magnitude",
            "count",
            "decimals",
            "percent",
        ):
            if field in node and not _is_number(node[field]):
                errors.append(f"{path}.{field} must be numeric")
        for field in ("x2", "y2"):
            if field in node:
                _validate_normalized_number(node[field], f"{path}.{field}", errors)
        if "percent" in node and _is_number(node["percent"]) and not 0 <= float(node["percent"]) <= 100:
            errors.append(f"{path}.percent must be between 0 and 100")
        if "value" in node and not isinstance(node["value"], (str, int, float)):
            errors.append(f"{path}.value must be a string or number")
        if node.get("type") == "graph" and not node.get("points"):
            errors.append(f"{path}.points is required for graph nodes")
        if node.get("type") == "apparatus" and not isinstance(node.get("kind"), str):
            errors.append(f"{path}.kind is required for apparatus nodes")
        if node.get("type") == "measurement" and "value" not in node:
            errors.append(f"{path}.value is required for measurement nodes")

    actions = recipe.get("actions")
    if not isinstance(actions, list) or not actions:
        errors.append("recipe.actions must be a non-empty list")
        actions = []
    for index, action in enumerate(actions):
        path = f"recipe.actions[{index}]"
        if not isinstance(action, dict):
            errors.append(f"{path} must be an object")
            continue
        errors.extend(_unknown_fields(action, ACTION_FIELDS, path))
        for field in sorted(ACTION_REQUIRED_FIELDS - set(action)):
            errors.append(f"{path}.{field} is required")
        if action.get("type") not in ACTION_TYPES:
            errors.append(f"{path}.type is not a registered action type")
        target = action.get("target")
        if not isinstance(target, str) or target not in node_ids:
            errors.append(f"{path}.target must reference a node in this recipe")
        at = action.get("at")
        duration = action.get("duration")
        _validate_normalized_number(at, f"{path}.at", errors)
        _validate_normalized_number(duration, f"{path}.duration", errors)
        if _is_number(duration) and float(duration) <= 0:
            errors.append(f"{path}.duration must be positive")
        if _is_number(at) and _is_number(duration) and float(at) + float(duration) > 1.000001:
            errors.append(f"{path} must finish within the normalized timeline")
        if "to" in action:
            destination = action["to"]
            allowed_destination_fields = {"x", "y", "rotation", "scale", "opacity", "value", "percent", "color"}
            if not isinstance(destination, dict) or not destination:
                errors.append(f"{path}.to must be a non-empty destination object")
            elif set(destination) - allowed_destination_fields:
                errors.append(f"{path}.to contains unsupported destination fields")
            else:
                for field in ("x", "y", "opacity"):
                    if field in destination:
                        _validate_normalized_number(destination[field], f"{path}.to.{field}", errors)
                for field in ("rotation", "scale", "value"):
                    if field in destination and not _is_number(destination[field]):
                        errors.append(f"{path}.to.{field} must be numeric")
                if "percent" in destination and (
                    not _is_number(destination["percent"]) or not 0 <= float(destination["percent"]) <= 100
                ):
                    errors.append(f"{path}.to.percent must be between 0 and 100")
                if "color" in destination:
                    _validate_text(destination["color"], f"{path}.to.color", errors)
        destination = action.get("to") if isinstance(action.get("to"), dict) else {}
        if action.get("type") == "rotate" and "rotation" not in destination:
            errors.append(f"{path}.to.rotation is required for rotate")
        if action.get("type") == "scale" and "scale" not in destination:
            errors.append(f"{path}.to.scale is required for scale")
        if action.get("type") == "fill" and "percent" not in destination:
            errors.append(f"{path}.to.percent is required for fill")
        for field in ("count",):
            if field in action and (not isinstance(action[field], int) or isinstance(action[field], bool) or action[field] < 1):
                errors.append(f"{path}.{field} must be a positive integer")
        if "amplitude" in action:
            _validate_normalized_number(action["amplitude"], f"{path}.amplitude", errors)
        for field in ("label", "direction", "ease"):
            _validate_text(action.get(field), f"{path}.{field}", errors)
        if "value" in action and not isinstance(action["value"], (str, int, float)):
            errors.append(f"{path}.value must be a string or number")
    return errors


def validate_manifest(manifest: Any) -> list[str]:
    """Return violations for the registry envelope and all contained recipes."""
    if not isinstance(manifest, dict):
        return ["manifest must be an object"]
    errors = _unknown_fields(manifest, {"version", "syllabus", "workbenches", "recipes"}, "manifest")
    if not isinstance(manifest.get("version"), int) or manifest.get("version", 0) < 1:
        errors.append("manifest.version must be a positive integer")
    _validate_text(manifest.get("syllabus"), "manifest.syllabus", errors, required=True)
    workbenches = manifest.get("workbenches")
    if workbenches != list(WORKBENCHES):
        errors.append("manifest.workbenches must declare the complete canonical workbench list")
    recipes = manifest.get("recipes")
    if not isinstance(recipes, list) or not recipes:
        errors.append("manifest.recipes must be a non-empty list")
        return errors

    recipe_ids: set[str] = set()
    for index, entry in enumerate(recipes):
        path = f"manifest.recipes[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{path} must be an object")
            continue
        errors.extend(_unknown_fields(entry, {"objective_id", "beat_labels", "cue_terms", "recipe"}, path))
        objective_id = entry.get("objective_id")
        if not isinstance(objective_id, str) or not _OBJECTIVE_RE.fullmatch(objective_id):
            errors.append(f"{path}.objective_id must be a canonical syllabus objective ID")
        for field in ("beat_labels", "cue_terms"):
            values = entry.get(field)
            if not isinstance(values, list) or not all(isinstance(value, str) and value.strip() for value in values):
                errors.append(f"{path}.{field} must be a list of non-empty strings")
        recipe = entry.get("recipe")
        recipe_errors = validate_recipe(recipe)
        errors.extend(f"{path}: {error}" for error in recipe_errors)
        if isinstance(recipe, dict) and isinstance(recipe.get("id"), str):
            if recipe["id"] in recipe_ids:
                errors.append(f"{path}.recipe.id duplicates {recipe['id']}")
            recipe_ids.add(recipe["id"])
            declared_workbenches = workbenches if isinstance(workbenches, list) else []
            if recipe.get("workbench") not in declared_workbenches:
                errors.append(f"{path}.recipe.workbench is not declared by the manifest")
    return errors


def load_recipe_manifest(path: str | Path | None = None) -> dict[str, Any]:
    """Load and validate the deterministic recipe manifest."""
    manifest_path = Path(path) if path is not None else DEFAULT_MANIFEST_PATH
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors = validate_manifest(manifest)
    if errors:
        raise RecipeManifestError(errors)
    return manifest


def claim_id_to_objective_id(claim_id: Any) -> str | None:
    """Map canonical or fact-handle-style claim IDs to a syllabus objective."""
    if not isinstance(claim_id, str):
        return None
    match = _CLAIM_OBJECTIVE_RE.fullmatch(claim_id.strip())
    if not match:
        return None
    topic = match.group("topic").replace("_", ".")
    route = match.group("route").upper()
    number = int(match.group("number"))
    return f"{topic}-{route}{number:02d}"


def _normalized_words(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", value.lower())


def _normalized_phrase(value: str) -> str:
    return " ".join(_normalized_words(value))


def select_recipe(
    objective_ids: list[str] | tuple[str, ...] | None,
    beat_label: str,
    narration_text: str,
    occurrence_by_objective: dict[str, int] | None = None,
) -> dict[str, Any] | None:
    """Select a recipe using syllabus grounding before any textual signal.

    Text and beat labels only score recipes already attached to one of the
    supplied objective IDs.  They can therefore never route a beat to an
    unrelated syllabus concept.
    """
    ordered_objectives: list[str] = []
    for raw_id in objective_ids or []:
        objective_id = claim_id_to_objective_id(raw_id)
        if objective_id and objective_id not in ordered_objectives:
            ordered_objectives.append(objective_id)
    if not ordered_objectives:
        return None

    manifest = load_recipe_manifest()
    objective_positions = {objective_id: index for index, objective_id in enumerate(ordered_objectives)}
    beat_phrase = _normalized_phrase(beat_label)
    narration_phrase = _normalized_phrase(narration_text)
    scored: list[dict[str, Any]] = []
    for manifest_index, entry in enumerate(manifest["recipes"]):
        objective_id = entry["objective_id"]
        if objective_id not in objective_positions:
            continue
        normalized_labels = [_normalized_phrase(label) for label in entry["beat_labels"]]
        exact_beat_matches = [label for label in normalized_labels if label and label == beat_phrase]
        beat_word_matches = [
            label for label in normalized_labels
            if label and label != beat_phrase and set(label.split()) & set(beat_phrase.split())
        ]
        cue_matches = [
            term for term in entry["cue_terms"]
            if _normalized_phrase(term) and _normalized_phrase(term) in narration_phrase
        ]
        score = (6 * len(exact_beat_matches)) + (2 * len(beat_word_matches)) + sum(
            1 + min(len(_normalized_words(term)), 3) for term in cue_matches
        )
        scored.append(
            {
                "entry": entry,
                "manifest_index": manifest_index,
                "score": score,
                "beat_matches": exact_beat_matches or beat_word_matches,
                "cue_matches": cue_matches,
            }
        )
    if not scored:
        return None

    best_score = max(item["score"] for item in scored)
    tied = [item for item in scored if item["score"] == best_score]
    occurrence_by_objective = occurrence_by_objective or {}
    selected: dict[str, Any] | None = None
    for objective_id in ordered_objectives:
        objective_ties = sorted(
            (item for item in tied if item["entry"]["objective_id"] == objective_id),
            key=lambda item: (item["entry"]["recipe"]["id"], item["manifest_index"]),
        )
        if not objective_ties:
            continue
        raw_occurrence = occurrence_by_objective.get(objective_id, 0)
        occurrence = raw_occurrence if isinstance(raw_occurrence, int) and raw_occurrence >= 0 else 0
        selected = objective_ties[occurrence % len(objective_ties)]
        break
    if selected is None:
        return None

    entry = selected["entry"]
    objective_id = entry["objective_id"]
    occurrence = occurrence_by_objective.get(objective_id, 0)
    occurrence = occurrence if isinstance(occurrence, int) and occurrence >= 0 else 0
    return {
        "recipe": copy.deepcopy(entry["recipe"]),
        "selection": {
            "objective_id": objective_id,
            "recipe_id": entry["recipe"]["id"],
            "score": selected["score"],
            "beat_matches": copy.deepcopy(selected["beat_matches"]),
            "cue_matches": copy.deepcopy(selected["cue_matches"]),
            "occurrence": occurrence,
            "candidate_count": len(scored),
            "strategy": "objective_constrained_beat_and_cue_score",
        },
    }
