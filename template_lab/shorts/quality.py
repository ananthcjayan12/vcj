from __future__ import annotations

import re
from typing import Any

from .constants import ARCHETYPES, DEPENDENT_PHRASES, MAX_SHORT_DURATION, MAX_SOURCE_REELS, MIN_SHORT_DURATION, SCORE_WEIGHTS
from .schemas import ShortsValidationError, words


GENERIC_PHRASES = (
    "today we will",
    "in this video",
    "in this short",
    "let's learn",
    "understand this in one minute",
    "follow for more",
    "like and subscribe",
    "stay tuned",
    "as we saw earlier",
    "in the previous section",
    "now that we know",
    "continuing from",
)


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def hook_similarity(a: str, b: str) -> float:
    wa, wb = set(words(a)), set(words(b))
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def estimate_speech_seconds(text: str, *, wpm: float = 155.0) -> float:
    count = len(words(text))
    return round((count / wpm) * 60.0 + 0.35, 2)


def generic_language_hits(text: str) -> list[str]:
    lowered = text.lower()
    return [phrase for phrase in GENERIC_PHRASES + DEPENDENT_PHRASES if phrase in lowered]


def local_candidate_scores(item: dict[str, Any], context: dict[str, Any]) -> dict[str, float]:
    self_scores = item.get("self_scores") or item.get("scores") or {}
    hook = str(item.get("hook") or "")
    payoff = str(item.get("payoff") or "")
    promise = str(item.get("promise") or "")
    index = context.get("_index") or {}
    paragraphs = index.get("paragraphs") or {}
    beats = index.get("beats") or {}
    reels = index.get("reels") or {}

    hook_score = float(self_scores.get("hook_score", 70))
    if len(words(hook)) > 22:
        hook_score -= 15
    if hook.strip().endswith("?"):
        hook_score = min(100, hook_score + 5)
    if generic_language_hits(hook):
        hook_score = min(hook_score, 35)
    if hook_similarity(hook, payoff) > 0.75:
        hook_score = min(hook_score, 40)

    payoff_score = float(self_scores.get("payoff_score", 70))
    if len(words(payoff)) < 6:
        payoff_score -= 10
    if generic_language_hits(payoff):
        payoff_score = min(payoff_score, 35)

    standalone = float(self_scores.get("standalone_score", 80))
    if generic_language_hits(" ".join((hook, promise, payoff))):
        standalone = min(standalone, 30)

    visual = 45.0
    beat_ids = [str(x) for x in item.get("source_beat_ids") or []]
    if beat_ids:
        suits = [float((beats.get(bid) or {}).get("visual_evidence", {}).get("portrait_suitability", 40)) for bid in beat_ids]
        visual = sum(suits) / max(1, len(suits))
    elif item.get("source_reel_ids"):
        visual = 70.0 if all(str(r) in reels for r in item.get("source_reel_ids") or []) else 40.0

    audio = 55.0
    para_ids = [str(x) for x in item.get("source_paragraph_ids") or []]
    if para_ids and all(pid in paragraphs for pid in para_ids):
        durations = [paragraphs[pid].get("audio_duration_seconds") for pid in para_ids]
        if any(d is not None and d >= 4 for d in durations):
            audio = 78.0

    exam = float(self_scores.get("exam_relevance_score", 70))
    portrait = min(100.0, visual + 5)
    return {
        "standalone_score": max(0, min(100, standalone)),
        "hook_score": max(0, min(100, hook_score)),
        "payoff_score": max(0, min(100, payoff_score)),
        "visual_reuse_score": max(0, min(100, visual)),
        "audio_reuse_score": max(0, min(100, audio)),
        "exam_relevance_score": max(0, min(100, exam)),
        "portrait_suitability_score": max(0, min(100, portrait)),
    }


def derive_source_segments(item: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
    index = context.get("_index") or {}
    beats = index.get("beats") or {}
    reels = index.get("reels") or {}
    beat_ids = [str(x) for x in item.get("source_beat_ids") or []]
    reel_ids = [str(x) for x in item.get("source_reel_ids") or []]

    if not reel_ids and beat_ids:
        reel_ids = []
        for bid in beat_ids:
            rid = str((beats.get(bid) or {}).get("reel_id") or "")
            if rid and rid not in reel_ids:
                reel_ids.append(rid)
    if not reel_ids and reels:
        reel_ids = [next(iter(reels))]

    if len(set(reel_ids)) > MAX_SOURCE_REELS:
        raise ShortsValidationError("A Short may use at most two reels")

    if len(reel_ids) == 2:
        meta = [reels.get(rid) for rid in reel_ids]
        if all(meta) and abs(int(meta[0]["index"]) - int(meta[1]["index"])) > 1:
            raise ShortsValidationError("Source reels must be adjacent")

    segments = []
    for rid in reel_ids:
        related = [bid for bid in beat_ids if str((beats.get(bid) or {}).get("reel_id")) == rid]
        if not related:
            related = [bid for bid, beat in beats.items() if str(beat.get("reel_id")) == rid][:2]
        starts = [float((beats.get(bid) or {}).get("start", reels.get(rid, {}).get("start", 0))) for bid in related] or [float((reels.get(rid) or {}).get("start", 0))]
        ends = [float((beats.get(bid) or {}).get("end", reels.get(rid, {}).get("end", starts[0] + 8))) for bid in related] or [float((reels.get(rid) or {}).get("end", starts[0] + 8))]
        segments.append({
            "reel_id": rid,
            "beat_ids": related or [f"beat_for_{rid}"],
            "absolute_start": min(starts),
            "absolute_end": max(ends),
            "visual_reuse_mode": "adapt",
            "audio_reuse_mode": "partial",
        })
    return segments


def normalize_model_candidate(raw: dict[str, Any], context: dict[str, Any], *, index: int) -> dict[str, Any]:
    index_data = context.get("_index") or {}
    known = set(index_data.get("known_claims") or [])
    paragraphs = index_data.get("paragraphs") or {}
    beats = index_data.get("beats") or {}

    claim_ids_raw = [str(x) for x in raw.get("claim_ids") or []]
    primary = str(raw.get("primary_claim_id") or (claim_ids_raw[0] if claim_ids_raw else ""))
    if not primary and known:
        primary = next(iter(sorted(known)))
    supporting = [str(x) for x in raw.get("supporting_claim_ids") or [] if str(x) != primary]
    claim_list = [primary, *supporting] if primary else [str(x) for x in raw.get("claim_ids") or []]
    claim_list = [c for c in claim_list if c]
    unknown = set(claim_list) - known if known else set()
    if unknown:
        raise ShortsValidationError(f"Unknown claim IDs: {', '.join(sorted(unknown))}")

    paragraph_ids = [str(x) for x in raw.get("source_paragraph_ids") or []]
    if not paragraph_ids:
        paragraph_ids = [
            pid for pid, paragraph in paragraphs.items()
            if primary and primary in set(map(str, paragraph.get("claim_ids") or []))
        ][:2]
    if not paragraph_ids and paragraphs:
        paragraph_ids = [next(iter(paragraphs))]
    missing_p = [pid for pid in paragraph_ids if pid not in paragraphs]
    if missing_p and paragraphs:
        raise ShortsValidationError(f"Unknown source paragraphs: {', '.join(missing_p)}")

    beat_ids = [str(x) for x in raw.get("source_beat_ids") or []]
    missing_b = [bid for bid in beat_ids if bid not in beats]
    if missing_b and beats:
        raise ShortsValidationError(f"Unknown source beats: {', '.join(missing_b)}")

    archetype = str(raw.get("archetype") or ARCHETYPES[index % len(ARCHETYPES)])
    if archetype not in ARCHETYPES:
        raise ShortsValidationError("Unsupported Short archetype")

    item = {
        "candidate_id": f"candidate_{index + 1:03d}",
        "concept_key": _norm(str(raw.get("concept_key") or raw.get("working_title") or primary or f"concept-{index+1}")).replace(" ", "-")[:80],
        "primary_claim_id": primary,
        "supporting_claim_ids": supporting,
        "archetype": archetype,
        "hook_mechanism": str(raw.get("hook_mechanism") or "curiosity_gap"),
        "working_title": str(raw.get("working_title") or "Physics Short").strip(),
        "hook": str(raw.get("hook") or "").strip(),
        "promise": str(raw.get("promise") or "").strip(),
        "payoff": str(raw.get("payoff") or "").strip(),
        "target_duration_seconds": float(raw.get("target_duration_seconds") or 40),
        "claim_ids": claim_list,
        "source_paragraph_ids": paragraph_ids,
        "source_beat_ids": beat_ids,
        "source_reel_ids": [str(x) for x in raw.get("source_reel_ids") or []],
        "creative_rationale": str(raw.get("creative_rationale") or ""),
        "warnings": list(raw.get("warnings") or []),
        "self_scores": raw.get("self_scores") or raw.get("scores") or {},
    }
    if not MIN_SHORT_DURATION <= item["target_duration_seconds"] <= MAX_SHORT_DURATION:
        item["target_duration_seconds"] = max(MIN_SHORT_DURATION, min(MAX_SHORT_DURATION, item["target_duration_seconds"]))
    text_blob = " ".join(item[k] for k in ("hook", "promise", "payoff"))
    hits = generic_language_hits(text_blob)
    if hits:
        raise ShortsValidationError(f"Candidate uses banned phrasing: {hits[0]}")
    if not item["hook"] or not item["payoff"]:
        raise ShortsValidationError("Candidate requires hook and payoff")
    if hook_similarity(item["hook"], item["payoff"]) > 0.85:
        raise ShortsValidationError("Hook and payoff are near-duplicates")

    item["source_segments"] = derive_source_segments(item, context)
    item["source_reel_ids"] = [str(s["reel_id"]) for s in item["source_segments"]]
    item["scores"] = local_candidate_scores(item, context)
    item["scores"]["overall_score"] = round(sum(float(item["scores"][k]) * w for k, w in SCORE_WEIGHTS.items()))
    return item


def deduplicate_candidates(items: list[dict[str, Any]], *, final_count: int = 5) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    kept: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    claim_counts: dict[str, int] = {}
    sorted_items = sorted(items, key=lambda x: x.get("scores", {}).get("overall_score", 0), reverse=True)
    for item in sorted_items:
        reasons = []
        concept = str(item.get("concept_key") or "")
        if concept and any(concept == str(other.get("concept_key") or "") for other in kept):
            reasons.append("duplicate_concept_key")
        if any(hook_similarity(item.get("hook", ""), other.get("hook", "")) >= 0.82 for other in kept):
            reasons.append("duplicate_hook")
        primary = str(item.get("primary_claim_id") or (item.get("claim_ids") or [""])[0])
        if primary and claim_counts.get(primary, 0) >= 1:
            reasons.append("duplicate_primary_claim")
        source_key = tuple(sorted(map(str, item.get("source_paragraph_ids") or [])))
        if source_key and any(tuple(sorted(map(str, other.get("source_paragraph_ids") or []))) == source_key for other in kept):
            reasons.append("identical_source_paragraphs")
        if reasons:
            rejected.append({"candidate": item, "reasons": reasons})
            continue
        kept.append(item)
        if primary:
            claim_counts[primary] = claim_counts.get(primary, 0) + 1
        if len(kept) >= final_count:
            break

    def _can_add(item: dict[str, Any], reasons: list[str]) -> bool:
        concept = str(item.get("concept_key") or "")
        if concept and any(concept == str(other.get("concept_key") or "") for other in kept):
            return False
        if any(hook_similarity(item.get("hook", ""), other.get("hook", "")) >= 0.82 for other in kept):
            return False
        # Soft reasons are OK when we still need bodies.
        return True

    if len(kept) < min(3, final_count, len(sorted_items)):
        for entry in rejected:
            item = entry["candidate"]
            if item in kept:
                continue
            if not _can_add(item, entry.get("reasons") or []):
                continue
            kept.append(item)
            if len(kept) >= min(3, final_count):
                break
        rejected = [entry for entry in rejected if entry["candidate"] not in kept]

    # Last resort: fill remaining slots ignoring soft overlaps but never exact concept clones.
    if len(kept) < min(3, len(sorted_items)):
        for item in sorted_items:
            if item in kept:
                continue
            concept = str(item.get("concept_key") or "")
            if concept and any(concept == str(other.get("concept_key") or "") for other in kept):
                continue
            kept.append(item)
            if len(kept) >= min(3, final_count):
                break

    kept = sorted(kept, key=lambda x: x.get("scores", {}).get("overall_score", 0), reverse=True)[:final_count]
    for index, item in enumerate(kept, 1):
        item["candidate_id"] = f"candidate_{index:03d}"
    return kept, rejected


def script_quality_warnings(script: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    lines = script.get("lines") or []
    all_text = " ".join(str(line.get("text", "")) for line in lines)
    word_count = len(words(all_text))
    if word_count > 170:
        warnings.append("exceeds_170_words")
    elif word_count > 140:
        warnings.append("word_count_high")
    elif word_count < 60:
        warnings.append("word_count_low")
    if not 4 <= len(lines) <= 8:
        warnings.append(f"line_count_{len(lines)}")
    hook = next((line for line in lines if line.get("role") == "hook"), None)
    if hook and len(words(str(hook.get("text", "")))) > 18:
        warnings.append("hook_too_long")
    hits = generic_language_hits(all_text)
    warnings.extend(f"generic:{hit}" for hit in hits)
    roles = {str(line.get("role")) for line in lines}
    if not roles.intersection({"explanation", "evidence", "setup", "tension", "context"}):
        warnings.append("missing_explanatory_beat")
    duration = estimate_speech_seconds(all_text)
    target = float(script.get("target_duration_seconds") or 40)
    if duration > MAX_SHORT_DURATION:
        warnings.append("speech_longer_than_max_duration")
    if duration + 4 < MIN_SHORT_DURATION:
        warnings.append("speech_shorter_than_min_duration")
    if abs(duration - target) > 18:
        warnings.append("duration_mismatch")
    return warnings
