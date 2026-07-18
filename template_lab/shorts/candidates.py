from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import re

from .constants import ARCHETYPES
from .quality import deduplicate_candidates, normalize_model_candidate
from .schemas import validate_candidate, words


def analyze(parent_run_id: str, narration: dict[str, Any], story: dict[str, Any], manifest: dict[str, Any], timeline_id: str) -> dict[str, Any]:
    """Backward-compatible offline entry point used by tests and local fallback."""
    from .context import build_discovery_context

    artifacts = {
        "parent": __import__("pathlib").Path("."),
        "narration": narration,
        "story": story,
        "manifest": manifest,
        "timeline": {},
        "audio_manifest": {},
        "timestamps": {},
        "input": {},
        "known_claims": {
            str(c)
            for paragraph in narration.get("paragraphs") or []
            for c in paragraph.get("claim_ids") or []
        } | {
            str(c)
            for beat in story.get("beats") or []
            for c in beat.get("claim_ids") or []
        },
    }
    context = build_discovery_context(artifacts, parent_run_id=parent_run_id)
    payload = deterministic_fallback_candidates(context, timeline_id=timeline_id)
    payload["parent_run_id"] = parent_run_id
    return payload


def deterministic_fallback_candidates(context: dict[str, Any], *, timeline_id: str = "") -> dict[str, Any]:
    """Local-only ideas for tests, offline mode, or explicit Studio fallback. Never feed these to the model."""
    paragraphs = context.get("paragraphs") or []
    beats = context.get("beats") or []
    reels = context.get("reels") or []
    known = set((context.get("_index") or {}).get("known_claims") or [])
    candidates = []
    for index, paragraph in enumerate(paragraphs[:8]):
        text = str(paragraph.get("text") or "").strip()
        if not text:
            continue
        p_claims = [str(x) for x in paragraph.get("claim_ids") or [] if (not known or str(x) in known)]
        reel = reels[min(index, len(reels) - 1)] if reels else {}
        beat = beats[min(index, len(beats) - 1)] if beats else {}
        sentence = text.split(".")[0].strip(" []")
        questions = re.findall(r"(?:^|[.!]\s+)([^.!?]{8,120}\?)", text)
        hook = questions[0].strip() if questions else f"What changes here: {sentence[:72].rstrip(',.')}?"
        payoff = sentence + ("." if not sentence.endswith(".") else "")
        item = {
            "concept_key": f"fallback-{paragraph.get('paragraph_id')}",
            "primary_claim_id": p_claims[0] if p_claims else "",
            "supporting_claim_ids": p_claims[1:],
            "archetype": ARCHETYPES[index % len(ARCHETYPES)],
            "hook_mechanism": "question" if questions else "curiosity_gap",
            "working_title": " ".join(words(sentence)[:8]).title() or f"Physics Idea {index + 1}",
            "hook": hook,
            "promise": "See the key physics idea fast.",
            "payoff": payoff,
            "target_duration_seconds": min(50, max(25, round(len(words(text)) / 2.5))),
            "claim_ids": p_claims,
            "source_paragraph_ids": [str(paragraph.get("paragraph_id"))],
            "source_beat_ids": [str(beat.get("beat_id"))] if beat else [],
            "source_reel_ids": [str(reel.get("reel_id"))] if reel else [],
            "creative_rationale": "Deterministic offline fallback.",
            "warnings": ["deterministic_fallback"],
            "self_scores": {
                "standalone_score": 75,
                "hook_score": 70,
                "payoff_score": 72,
                "exam_relevance_score": 70,
            },
        }
        try:
            candidates.append(normalize_model_candidate(item, context, index=index))
        except Exception:
            # Keep tests resilient when evidence is sparse.
            legacy = {
                "candidate_id": f"candidate_{index + 1:03d}",
                "archetype": item["archetype"],
                "working_title": item["working_title"],
                "hook": item["hook"],
                "promise": item["promise"],
                "payoff": item["payoff"],
                "target_duration_seconds": item["target_duration_seconds"],
                "claim_ids": p_claims,
                "source_paragraph_ids": item["source_paragraph_ids"],
                "source_segments": [{
                    "reel_id": str(reel.get("reel_id") or f"reel_{index + 1:03d}"),
                    "beat_ids": [str(beat.get("beat_id") or f"beat_{index + 1:03d}")],
                    "absolute_start": float(reel.get("start", 0) or 0),
                    "absolute_end": float(reel.get("end", 30) or 30),
                    "visual_reuse_mode": "adapt",
                    "audio_reuse_mode": "partial",
                }],
                "scores": {
                    "standalone_score": 75, "hook_score": 70, "payoff_score": 72,
                    "visual_reuse_score": 60, "audio_reuse_score": 60,
                    "exam_relevance_score": 70, "portrait_suitability_score": 65,
                },
                "warnings": ["deterministic_fallback"],
            }
            candidates.append(validate_candidate(legacy, known or set(p_claims)))
    ranked, _ = deduplicate_candidates(candidates, final_count=5)
    if not ranked:
        ranked = candidates[:5]
    return {
        "version": "1.0",
        "parent_run_id": (context.get("lesson") or {}).get("parent_run_id", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_timeline_id": timeline_id,
        "analysis_mode": "deterministic_fallback",
        "candidates": ranked[:5],
    }


def process_model_candidates(raw_candidates: list[dict[str, Any]], context: dict[str, Any], *, timeline_id: str = "") -> dict[str, Any]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_candidates):
        try:
            accepted.append(normalize_model_candidate(raw, context, index=index))
        except Exception as exc:
            rejected.append({"raw": raw, "reasons": [str(exc)]})
    final, dupes = deduplicate_candidates(accepted, final_count=5)
    rejected.extend(dupes)
    if not 3 <= len(final) <= 5:
        raise ValueError(f"After grounding/diversity gates, expected 3–5 candidates, got {len(final)}")
    return {
        "version": "1.0",
        "parent_run_id": (context.get("lesson") or {}).get("parent_run_id", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_timeline_id": timeline_id,
        "analysis_mode": "model_discovery",
        "candidates": final,
        "rejected_candidates": rejected,
        "raw_candidate_count": len(raw_candidates),
    }
