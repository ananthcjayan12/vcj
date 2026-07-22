"""Generation-time scientific context and visual-behaviour contract support."""
from __future__ import annotations

import json
from pathlib import Path
from types import ModuleType
from typing import Any

CONTRACT_START = "/* MAV_VISUAL_CONTRACT"
CONTRACT_END = "MAV_VISUAL_CONTRACT */"


def _load(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _compact(value: Any, limit: int = 32_000) -> Any:
    rendered = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if len(rendered) <= limit:
        return value
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for key, item in value.items():
            candidate = {**output, key: item}
            if len(json.dumps(candidate, ensure_ascii=False, separators=(",", ":"))) > limit:
                break
            output[key] = item
        output["_truncated"] = True
        return output
    if isinstance(value, list):
        output = []
        for item in value:
            candidate = [*output, item]
            if len(json.dumps(candidate, ensure_ascii=False, separators=(",", ":"))) > limit:
                break
            output.append(item)
        return [*output, {"_truncated": True}]
    return str(value)[:limit]


def build_generation_context(root: Path, manifest: dict[str, Any], chapter_ids: list[str]) -> dict[str, Any]:
    run_path = root.parent
    input_payload = _load(run_path / "input.json", {}) or {}
    narration = _load(run_path / "narration.json", {}) or {}
    skeleton = _load(run_path / "story_skeleton.json", {}) or {}
    units = {
        str(unit.get("scene_id")): unit
        for unit in (manifest.get("reels") or manifest.get("shots") or manifest.get("chapters") or [])
    }
    paragraph_ids = {
        str(units[chapter_id].get("source_paragraph_id") or units[chapter_id].get("source_id") or "")
        for chapter_id in chapter_ids
        if chapter_id in units
    }
    paragraphs = [
        paragraph
        for paragraph in narration.get("paragraphs", [])
        if str(paragraph.get("id") or paragraph.get("paragraph_id") or "") in paragraph_ids
    ]
    directory = "reels" if manifest.get("timeline_mode") == "immutable_reels" else "shots" if manifest.get("timeline_mode") == "immutable_shots" else "chapters"
    cues: dict[str, Any] = {}
    for chapter_id in chapter_ids:
        cue_path = root / directory / f"{chapter_id}.cues.ts"
        if not cue_path.exists():
            continue
        import re
        match = re.search(r"export const CUES = (\{.*\}) as const;", cue_path.read_text(encoding="utf-8"), re.S)
        if match:
            try:
                cues[chapter_id] = json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
    return {
        "topic": input_payload.get("topic"),
        "topic_ref": input_payload.get("topic_ref"),
        "objective_ids": input_payload.get("objective_ids", []),
        "relevant_narration_paragraphs": paragraphs,
        "exact_reel_cues": cues,
        "grounded_facts": _compact(input_payload.get("facts", [])),
        "physics_context": _compact(input_payload.get("physics_context", {})),
        "story_context": _compact(skeleton, 16_000),
    }


def contract_instructions() -> str:
    return f"""

SCIENTIFIC AND VISUAL BEHAVIOUR CONTRACT
Before writing each reel, derive the expected behaviour from the grounded facts and narration. Do not rely on topic-specific memorised templates. For every displayed scientific relationship, determine and keep consistent:
- the direction and reference frame of arrows, vectors, fields, forces, velocity and acceleration;
- the expected path, trajectory, rotation or deformation of moving objects;
- which points, objects or labels remain attached, coincident or aligned;
- which quantities remain fixed in world space and which transform with an object;
- the causal relationship between a displayed action and the resulting motion;
- the exact narration cue at which each important visual event begins or becomes assessable.

Use one source of truth for each relationship. A displayed arrow and the motion it causes must derive from the same direction/state. Connected objects must derive from shared or transformed attachment points. Never invent a derived scientific value merely because it looks convenient.

Before returning TSX, silently audit scientific correctness, cue synchronisation, contrast, readable type, safe-area containment, label association, clipping, overlap at the densest state, and the final teaching meaning. Fix the source before returning it.

At the top of each TSX file, include exactly one valid JSON contract inside this TypeScript block comment:
{CONTRACT_START}
{{
  "version": "1.0",
  "scene_claim": "one sentence describing what the reel must demonstrate",
  "behaviour": [
    {{
      "subject": "semantic object id",
      "property": "direction | trajectory | rotation | alignment | value | state",
      "expected": "fact-grounded observable behaviour",
      "evidence_fact": "short supporting fact or narration phrase"
    }}
  ],
  "attachments": [
    {{"a": "object.point", "b": "other.point", "relationship": "attached | coincident | aligned | follows"}}
  ],
  "cue_events": [
    {{"cue": "existing CUES key", "occurrence": 0, "expected_visual": "observable event tied to that cue"}}
  ],
  "review_checkpoints": [
    {{"cue": "existing CUES key", "occurrence": 0, "offset_seconds": 0.35, "purpose": "why this completed state is useful for review"}}
  ]
}}
{CONTRACT_END}

Contract rules:
- Use only cue keys that exist in the supplied reel CUES data.
- Supply one to three review checkpoints where the important objects and relationships are simultaneously visible and entrance motion has settled.
- Checkpoints are evidence locations, not new animation timings.
- Keep the contract generic and observable. Describe the arrow direction, object trajectory, attachment, state or causal response required by the supplied facts.
- The comment must contain strict JSON: double quotes, no trailing commas, no Markdown fences.
""".strip()


def install(pipeline: ModuleType) -> None:
    """Wrap the existing batch prompt once without changing generation control flow."""
    if getattr(pipeline, "_visual_contract_prompt_installed", False):
        return
    original = pipeline._batch_prompt

    def wrapped(root: Path, manifest: dict[str, Any], batch: dict[str, Any], *, instruction: str = ""):
        system, user = original(root, manifest, batch, instruction=instruction)
        context = build_generation_context(root, manifest, list(batch.get("chapter_ids") or []))
        user += (
            "\n\nGROUNDED SCIENTIFIC SOURCE CONTEXT\n"
            + json.dumps(context, ensure_ascii=False, separators=(",", ":"))
            + "\n\n"
            + contract_instructions()
        )
        return system, user

    pipeline._batch_prompt = wrapped
    pipeline._visual_contract_prompt_installed = True
