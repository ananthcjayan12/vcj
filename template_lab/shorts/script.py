from __future__ import annotations

from typing import Any
import re

from .quality import script_quality_warnings
from .schemas import claim_ids, validate_script, words


def compile_script(candidate: dict[str, Any], narration: dict[str, Any]) -> dict[str, Any]:
    """Offline/local fallback script only. Never pass this object to the script model as an example."""
    paragraph_by_id = {str(p.get("id")): p for p in narration.get("paragraphs") or []}
    source_id = str((candidate.get("source_paragraph_ids") or [""])[0])
    source_text = re.sub(r"\[[^\]]+\]", "", str(paragraph_by_id.get(source_id, {}).get("text", ""))).strip()
    source_words = words(source_text)
    excerpt = " ".join(source_words[: min(28, len(source_words))])
    lines = [{
        "line_id": "line_001",
        "role": "hook",
        "text": candidate["hook"],
        "claim_ids": candidate.get("claim_ids", []),
        "audio_source": "generate",
        "visual_intent": "native portrait hook reveal",
    }]
    if excerpt:
        lines.append({
            "line_id": "line_002",
            "role": "setup",
            "text": excerpt if len(words(excerpt)) <= 18 else " ".join(words(excerpt)[:18]),
            "claim_ids": candidate.get("claim_ids", []),
            "audio_source": "generate",
            "visual_intent": "establish the concrete situation",
        })
        if len(source_words) > 8:
            mid = " ".join(source_words[: min(20, len(source_words))])
            lines.append({
                "line_id": "line_003",
                "role": "explanation",
                "text": mid,
                "claim_ids": candidate.get("claim_ids", []),
                "audio_source": "reuse",
                "source_paragraph_id": source_id,
                "source_word_start": 0,
                "source_word_end": len(words(mid)) - 1,
                "visual_intent": "adapt source diagram and physics relationship",
            })
    lines.append({
        "line_id": f"line_{len(lines)+1:03d}",
        "role": "payoff",
        "text": candidate["payoff"],
        "claim_ids": candidate.get("claim_ids", []),
        "audio_source": "generate",
        "visual_intent": "answer reveal and visual loop",
    })
    result = {
        "version": "1.0",
        "short_id": "",
        "candidate_id": candidate["candidate_id"],
        "title": candidate["working_title"],
        "target_duration_seconds": float(candidate["target_duration_seconds"]),
        "claim_ids": candidate.get("claim_ids", []),
        "lines": lines,
        "closing_loop": {"enabled": True, "instruction": "Return to the opening composition."},
        "quality_warnings": [],
    }
    validated = validate_script(result, claim_ids(narration), candidate_claims=set(map(str, candidate.get("claim_ids") or [])))
    validated["quality_warnings"] = script_quality_warnings(validated)
    return validated


def resolve_clause_references(script: dict[str, Any], clauses: list[dict[str, Any]]) -> dict[str, Any]:
    """Bind reuse lines to catalogue clauses.

    A valid clause_id is authoritative: spoken text is always overwritten from the
    catalogue so model paraphrase cannot break exact audio reuse.
    """
    by_id = {str(item.get("clause_id")): item for item in clauses}
    warnings = list(script.get("quality_warnings") or [])
    for line in script.get("lines") or []:
        clause_id = str(line.get("clause_id") or "").strip()
        if line.get("audio_source") != "reuse" and not clause_id:
            line.pop("clause_id", None)
            continue
        if line.get("audio_source") != "reuse":
            line.pop("clause_id", None)
            continue
        if not clause_id:
            has_range = (
                line.get("source_paragraph_id") is not None
                and line.get("source_word_start") is not None
                and line.get("source_word_end") is not None
            )
            if not has_range:
                line["audio_source"] = "generate"
                warnings.append(f"{line.get('line_id')}:reuse_missing_clause_demoted")
            continue
        clause = by_id.get(clause_id)
        if not clause:
            raise ValueError(f"Unknown clause_id: {clause_id}")
        expected = str(clause.get("text") or "").strip()
        actual = str(line.get("text") or "").strip()
        if actual and words(expected) != words(actual):
            warnings.append(f"{line.get('line_id')}:clause_{clause_id}_text_forced_from_catalogue")
        line["text"] = expected
        line["audio_source"] = "reuse"
        line["clause_id"] = clause_id
        line["source_paragraph_id"] = clause["paragraph_id"]
        line["source_word_start"] = int(clause["source_word_start"])
        line["source_word_end"] = int(clause["source_word_end"])
        if clause.get("claim_ids") and not line.get("claim_ids"):
            line["claim_ids"] = list(clause["claim_ids"])
    if warnings:
        script["quality_warnings"] = list(dict.fromkeys(warnings))
    return script


def finalize_model_script(
    modeled: dict[str, Any],
    *,
    short_id: str,
    candidate: dict[str, Any],
    narration: dict[str, Any],
    clauses: list[dict[str, Any]],
) -> dict[str, Any]:
    modeled = dict(modeled)
    modeled["short_id"] = short_id
    modeled["candidate_id"] = candidate["candidate_id"]
    modeled.setdefault("version", "1.0")
    modeled.setdefault("title", candidate.get("working_title"))
    modeled.setdefault("target_duration_seconds", candidate.get("target_duration_seconds", 40))
    modeled.setdefault("claim_ids", candidate.get("claim_ids", []))
    modeled.setdefault("closing_loop", {"enabled": True, "instruction": "Return to the opening composition."})
    for index, line in enumerate(modeled.get("lines") or [], 1):
        line.setdefault("line_id", f"line_{index:03d}")
        line.setdefault("claim_ids", modeled.get("claim_ids") or candidate.get("claim_ids") or [])
        line.setdefault("visual_intent", "portrait-friendly physics visual")
        if line.get("audio_source") == "reuse" and line.get("clause_id"):
            pass
        elif line.get("audio_source") not in {"reuse", "generate"}:
            line["audio_source"] = "generate"
    resolve_clause_references(modeled, clauses)
    known = claim_ids(narration)
    candidate_claims = set(map(str, candidate.get("claim_ids") or []))
    validated = validate_script(modeled, known, candidate_claims=candidate_claims)
    prior = list(modeled.get("quality_warnings") or [])
    validated["quality_warnings"] = list(dict.fromkeys(prior + script_quality_warnings(validated)))
    return validated
