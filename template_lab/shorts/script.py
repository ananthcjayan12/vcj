from __future__ import annotations

from typing import Any
import re

from .schemas import claim_ids, validate_script, words


def compile_script(candidate: dict[str, Any], narration: dict[str, Any]) -> dict[str, Any]:
    paragraph_by_id = {str(p.get("id")): p for p in narration.get("paragraphs") or []}
    source_id = str((candidate.get("source_paragraph_ids") or [""])[0])
    source_text = re.sub(r"\[[^\]]+\]", "", str(paragraph_by_id.get(source_id, {}).get("text", ""))).strip()
    source_words = words(source_text)
    excerpt = " ".join(source_words[: min(28, len(source_words))])
    lines = [{"line_id": "line_001", "role": "hook", "text": candidate["hook"], "claim_ids": candidate.get("claim_ids", []),
              "audio_source": "generate", "visual_intent": "native portrait hook reveal"}]
    if excerpt:
        lines.append({"line_id": "line_002", "role": "explanation", "text": excerpt, "claim_ids": candidate.get("claim_ids", []),
                      "audio_source": "reuse", "source_paragraph_id": source_id, "source_word_start": 0,
                      "source_word_end": len(words(excerpt))-1, "visual_intent": "adapt source diagram and physics relationship"})
    lines.append({"line_id": f"line_{len(lines)+1:03d}", "role": "payoff", "text": candidate["payoff"],
                  "claim_ids": candidate.get("claim_ids", []), "audio_source": "generate", "visual_intent": "answer reveal and visual loop"})
    result = {"version": "1.0", "short_id": "", "candidate_id": candidate["candidate_id"], "title": candidate["working_title"],
              "target_duration_seconds": float(candidate["target_duration_seconds"]), "claim_ids": candidate.get("claim_ids", []),
              "lines": lines, "closing_loop": {"enabled": True, "instruction": "Return to the opening composition."}}
    return validate_script(result, claim_ids(narration))
