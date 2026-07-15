from __future__ import annotations

from typing import Any

from .constants import CONTRACT_VERSION


def build_physics_context(input_payload: dict[str, Any], narration: dict[str, Any]) -> dict[str, Any]:
    facts = [item for item in input_payload.get("facts", []) if isinstance(item, dict)]
    fact_map = {str(item.get("id")): item for item in facts if item.get("id")}
    claims: list[dict[str, Any]] = []
    for paragraph in narration.get("paragraphs", []):
        for claim_id in paragraph.get("claim_ids", []):
            root = str(claim_id).split(".", 1)[0]
            fact = fact_map.get(root)
            if fact:
                claims.append(
                    {
                        "paragraph_id": paragraph.get("id"),
                        "claim_id": claim_id,
                        "fact_id": root,
                        "text": fact.get("text", ""),
                        "source": fact.get("source", ""),
                    }
                )

    structured = input_payload.get("physics_context") if isinstance(input_payload.get("physics_context"), dict) else {}
    return {
        "schema_version": CONTRACT_VERSION,
        "claims": claims,
        "values": dict(structured.get("values") or {}),
        "units": dict(structured.get("units") or {}),
        "invariants": list(structured.get("invariants") or []),
        "worked_examples": list(structured.get("worked_examples") or []),
        "policy": [
            "Use supplied values and units exactly.",
            "Treat claim-linked fact text as authoritative.",
            "Do not infer an unstated numerical value.",
            "Preserve vector direction, geometry, graph axes, circuit connectivity, ray direction, and scale.",
        ],
    }
