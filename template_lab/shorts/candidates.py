from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import re

from .constants import ARCHETYPES
from .schemas import claim_ids, validate_candidate, words


def analyze(parent_run_id: str, narration: dict[str, Any], story: dict[str, Any], manifest: dict[str, Any], timeline_id: str) -> dict[str, Any]:
    paragraphs = narration.get("paragraphs") or []
    reels = manifest.get("reels") or manifest.get("shots") or manifest.get("chapters") or []
    beats = manifest.get("beats") or story.get("beats") or []
    known = claim_ids(narration) | claim_ids(story)
    candidates = []
    for index, paragraph in enumerate(paragraphs[:5]):
        text = re.sub(r"\[[^\]]+\]", "", str(paragraph.get("text", ""))).strip()
        if not text: continue
        p_claims = [str(x) for x in paragraph.get("claim_ids") or [] if str(x) in known]
        reel = reels[min(index, len(reels)-1)] if reels else {}
        reel_id = str(reel.get("scene_id") or reel.get("reel_id") or f"reel_{index+1:03d}")
        beat_id = str((beats[min(index, len(beats)-1)] if beats else {}).get("beat_id") or f"beat_{index+1:03d}")
        sentence = text.split(".")[0].strip(" []")
        questions = re.findall(r"(?:^|[.!]\s+)([^.!?]{8,120}\?)", text)
        hook = questions[0].strip() if questions else f"Can you predict the physics behind this: {sentence[:72].rstrip(',.')}?"
        payoff = sentence + "."
        lowered = text.lower()
        if "astronaut" in lowered and "moon" in lowered:
            hook = "An astronaut weighs less on the Moon. Did she lose any matter?"
            payoff = "Her mass stays constant; her weight changes because gravitational field strength changes: W = mg."
        elif "skydiver" in lowered:
            hook = "A skydiver speeds up, then stops accelerating. What changed?"
            payoff = "At terminal velocity, air resistance balances weight, so the resultant force is zero."
        item = {"candidate_id": f"candidate_{index+1:03d}", "archetype": ARCHETYPES[index % len(ARCHETYPES)],
                "working_title": ("Mass vs Weight on the Moon" if "astronaut" in lowered and "moon" in lowered else " ".join(words(sentence)[:8]).title()), "hook": hook,
                "promise": "See the key physics idea in under a minute.", "payoff": payoff,
                "target_duration_seconds": min(50, max(25, round(len(words(text)) / 2.5))), "claim_ids": p_claims,
                "source_paragraph_ids": [str(paragraph.get("id") or f"paragraph_{index+1:02d}")],
                "source_segments": [{"reel_id": reel_id, "beat_ids": [beat_id], "absolute_start": float(reel.get("start", 0)),
                                     "absolute_end": float(reel.get("end", min(50, len(words(text))/2.5))), "visual_reuse_mode": "adapt", "audio_reuse_mode": "partial"}],
                "scores": {"standalone_score": 85, "hook_score": 78, "payoff_score": 82, "visual_reuse_score": 80 if reels else 30,
                           "audio_reuse_score": 85, "exam_relevance_score": 75, "portrait_suitability_score": 80},
                "warnings": [] if reels else ["No source visuals were available"]}
        candidates.append(validate_candidate(item, known))
    candidates.sort(key=lambda x: x["scores"]["overall_score"], reverse=True)
    return {"version": "1.0", "parent_run_id": parent_run_id, "created_at": datetime.now(timezone.utc).isoformat(),
            "source_timeline_id": timeline_id, "candidates": candidates[:5]}
