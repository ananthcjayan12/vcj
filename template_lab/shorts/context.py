from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .constants import MAX_SHORT_DURATION, MAX_SOURCE_REELS, MIN_SHORT_DURATION
from .schemas import claim_ids, words


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\[[^\]]+\]", " ", text or "")).strip()


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _split_clauses(text: str) -> list[str]:
    cleaned = _clean(text)
    if not cleaned:
        return []
    parts = re.split(r"(?<=[.!?;:])\s+|\s+[—–-]\s+", cleaned)
    clauses: list[str] = []
    for part in parts:
        piece = part.strip(" ,;")
        if not piece:
            continue
        if len(words(piece)) < 4 and clauses:
            clauses[-1] = f"{clauses[-1]} {piece}".strip()
        else:
            clauses.append(piece)
    return [c for c in clauses if 4 <= len(words(c)) <= 28]


def _tsx_summary(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {"objects": [], "equations": [], "activity": [], "portrait_suitability": 40}
    text = path.read_text(encoding="utf-8")
    objects = sorted({m.group(1) for m in re.finditer(r"""(?:id|name|label|text)\s*[:=]\s*['"]([A-Za-z][A-Za-z0-9 _-]{1,40})['"]""", text)})[:12]
    equations = sorted({m.group(0) for m in re.finditer(r"\b[A-Za-z]\s*=\s*[A-Za-z0-9/²³^\s.+-]{1,24}", text)})[:8]
    activity = []
    lowered = text.lower()
    for token, label in (
        ("tween", "motion"), ("yield", "sequenced reveal"), ("opacity", "fade"),
        ("scale", "scale"), ("arrow", "arrow"), ("compare", "comparison"),
        ("chart", "chart"), ("graph", "graph"), ("force", "force diagram"),
    ):
        if token in lowered:
            activity.append(label)
    density = min(100, 35 + 8 * len(objects) + 6 * len(equations) + 5 * len(activity))
    return {
        "objects": objects[:8],
        "equations": equations[:6],
        "activity": activity[:6] or (["static labels"] if objects else ["limited visual signal"]),
        "portrait_suitability": density,
        "has_motion": any(x in lowered for x in ("tween", "yield*", "loop")),
    }


def _reel_tsx(parent: Path, reel_id: str) -> Path | None:
    for directory in ("reels", "shots", "chapters"):
        path = parent / "motion_canvas" / directory / f"{reel_id}.tsx"
        if path.is_file():
            return path
    return None


def _paragraph_duration(paragraph_id: str, audio_manifest: dict[str, Any], timestamps: dict[str, Any]) -> float | None:
    for item in audio_manifest.get("chapters") or []:
        if str(item.get("id")) == paragraph_id:
            for key in ("duration_seconds", "duration", "length_seconds"):
                if item.get(key) is not None:
                    return float(item[key])
            start, end = item.get("absolute_start"), item.get("absolute_end")
            if start is not None and end is not None:
                return max(0.0, float(end) - float(start))
    words_list = [w for w in timestamps.get("words") or [] if str(w.get("paragraph_id")) == paragraph_id]
    if words_list:
        return max(0.0, float(words_list[-1].get("end", 0)) - float(words_list[0].get("start", 0)))
    return None


def load_parent_artifacts(parent: Path) -> dict[str, Any]:
    narration = _read(parent / "narration.json")
    story = _read(parent / "story_skeleton.json")
    manifest = _read(parent / "motion_canvas" / "manifest.json")
    timeline = _read(parent / "motion_canvas" / "timeline.json")
    audio_manifest = _read(parent / "audio_chunks" / "manifest.json")
    timestamps = _read(parent / "audio_word_timestamps.json")
    input_payload = _read(parent / "input.json")
    return {
        "parent": parent,
        "narration": narration,
        "story": story,
        "manifest": manifest,
        "timeline": timeline,
        "audio_manifest": audio_manifest,
        "timestamps": timestamps,
        "input": input_payload,
        "known_claims": claim_ids(narration) | claim_ids(story),
    }


def build_discovery_context(artifacts: dict[str, Any], *, parent_run_id: str) -> dict[str, Any]:
    narration = artifacts["narration"]
    story = artifacts["story"]
    manifest = artifacts["manifest"]
    parent: Path = artifacts["parent"]
    audio_manifest = artifacts["audio_manifest"]
    timestamps = artifacts["timestamps"]
    input_payload = artifacts["input"]

    claim_text: dict[str, str] = {}
    for collection_key in ("claims", "key_claims", "learning_objectives"):
        for item in narration.get(collection_key) or story.get(collection_key) or []:
            if isinstance(item, dict):
                cid = str(item.get("claim_id") or item.get("id") or "")
                if cid:
                    claim_text[cid] = _clean(str(item.get("text") or item.get("claim") or item.get("statement") or ""))
    for paragraph in narration.get("paragraphs") or []:
        text = _clean(str(paragraph.get("text", "")))
        for cid in paragraph.get("claim_ids") or []:
            claim_text.setdefault(str(cid), text[:180])

    claims = [{"claim_id": cid, "text": text or cid} for cid, text in sorted(claim_text.items()) if cid in artifacts["known_claims"] or True]
    if not claims:
        claims = [{"claim_id": cid, "text": cid} for cid in sorted(artifacts["known_claims"])]

    paragraphs = []
    for index, paragraph in enumerate(narration.get("paragraphs") or []):
        pid = str(paragraph.get("id") or f"paragraph_{index+1:02d}")
        text = _clean(str(paragraph.get("text", "")))
        if not text:
            continue
        duration = _paragraph_duration(pid, audio_manifest, timestamps)
        paragraphs.append({
            "paragraph_id": pid,
            "text": text,
            "claim_ids": [str(x) for x in paragraph.get("claim_ids") or []],
            "word_count": len(words(text)),
            "audio_duration_seconds": round(duration, 2) if duration is not None else None,
        })

    reels_raw = manifest.get("reels") or manifest.get("shots") or manifest.get("chapters") or []
    reel_meta: dict[str, dict[str, Any]] = {}
    for index, reel in enumerate(reels_raw):
        rid = str(reel.get("scene_id") or reel.get("reel_id") or reel.get("id") or f"reel_{index+1:03d}")
        reel_meta[rid] = {
            "reel_id": rid,
            "start": float(reel.get("start", reel.get("absolute_start", 0)) or 0),
            "end": float(reel.get("end", reel.get("absolute_end", 0)) or 0),
            "title": str(reel.get("title") or reel.get("label") or rid),
            "claim_ids": [str(x) for x in reel.get("claim_ids") or []],
            "index": index,
        }

    beats_raw = manifest.get("beats") or story.get("beats") or []
    beats = []
    for index, beat in enumerate(beats_raw):
        bid = str(beat.get("beat_id") or beat.get("id") or f"beat_{index+1:03d}")
        reel_id = str(beat.get("reel_id") or beat.get("scene_id") or "")
        if not reel_id and reel_meta:
            reel_id = list(reel_meta.keys())[min(index, len(reel_meta) - 1)]
        tsx = _reel_tsx(parent, reel_id) if reel_id else None
        visual = _tsx_summary(tsx)
        start = float(beat.get("start", beat.get("absolute_start", reel_meta.get(reel_id, {}).get("start", 0))) or 0)
        end = float(beat.get("end", beat.get("absolute_end", reel_meta.get(reel_id, {}).get("end", start + 8))) or (start + 8))
        summary = _clean(str(beat.get("summary") or beat.get("title") or beat.get("intent") or beat.get("description") or bid))
        beats.append({
            "beat_id": bid,
            "reel_id": reel_id,
            "summary": summary,
            "claim_ids": [str(x) for x in beat.get("claim_ids") or reel_meta.get(reel_id, {}).get("claim_ids") or []],
            "start": start,
            "end": end,
            "visual_evidence": visual,
        })

    if not beats and reel_meta:
        for rid, meta in reel_meta.items():
            visual = _tsx_summary(_reel_tsx(parent, rid))
            beats.append({
                "beat_id": f"beat_for_{rid}",
                "reel_id": rid,
                "summary": meta["title"],
                "claim_ids": meta["claim_ids"],
                "start": meta["start"],
                "end": meta["end"] or meta["start"] + 10,
                "visual_evidence": visual,
            })

    topic = str(
        input_payload.get("title")
        or input_payload.get("topic")
        or story.get("title")
        or narration.get("title")
        or parent_run_id
    )
    return {
        "lesson": {
            "parent_run_id": parent_run_id,
            "topic": topic,
            "target_audience": "Cambridge IGCSE Physics students",
        },
        "claims": claims,
        "paragraphs": paragraphs,
        "beats": beats,
        "reels": [
            {
                "reel_id": rid,
                "title": meta["title"],
                "start": meta["start"],
                "end": meta["end"],
                "claim_ids": meta["claim_ids"],
                "adjacent_reel_ids": [
                    other for other, other_meta in reel_meta.items()
                    if abs(other_meta["index"] - meta["index"]) == 1
                ],
            }
            for rid, meta in reel_meta.items()
        ],
        "constraints": {
            "raw_candidate_count_requested": 8,
            "final_candidate_count": "3-5",
            "maximum_source_reels": MAX_SOURCE_REELS,
            "duration_seconds": [MIN_SHORT_DURATION, MAX_SHORT_DURATION],
            "maximum_spoken_words": 170,
        },
        "_index": {
            "paragraphs": {p["paragraph_id"]: p for p in paragraphs},
            "beats": {b["beat_id"]: b for b in beats},
            "reels": reel_meta,
            "known_claims": set(artifacts["known_claims"]),
        },
    }


def public_discovery_context(context: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in context.items() if not key.startswith("_")}


def build_reusable_clauses(artifacts: dict[str, Any], paragraph_ids: list[str]) -> list[dict[str, Any]]:
    wanted = set(map(str, paragraph_ids))
    narration = artifacts["narration"]
    timestamps = artifacts["timestamps"]
    clauses: list[dict[str, Any]] = []
    counter = 1
    for paragraph in narration.get("paragraphs") or []:
        pid = str(paragraph.get("id") or "")
        if pid not in wanted:
            continue
        text = _clean(str(paragraph.get("text", "")))
        source_words = words(text)
        cursor = 0
        for clause in _split_clauses(text):
            clause_words = words(clause)
            if not clause_words:
                continue
            start = None
            for index in range(cursor, max(cursor, len(source_words) - len(clause_words) + 1)):
                if source_words[index:index + len(clause_words)] == clause_words:
                    start = index
                    break
            if start is None:
                continue
            end = start + len(clause_words) - 1
            duration = None
            para_words = [w for w in timestamps.get("words") or [] if str(w.get("paragraph_id")) == pid]
            if para_words and end < len(para_words):
                duration = round(float(para_words[end].get("end", 0)) - float(para_words[start].get("start", 0)), 2)
            clauses.append({
                "clause_id": f"clause_{counter:03d}",
                "paragraph_id": pid,
                "text": " ".join(text.split()[start:end + 1]) if text.split() else clause,
                "source_word_start": start,
                "source_word_end": end,
                "duration_seconds": duration,
                "claim_ids": [str(x) for x in paragraph.get("claim_ids") or []],
            })
            # Prefer exact slice from cleaned word list joined simply
            joined = " ".join(source_words[start:end + 1])
            # Restore a readable form from original clause when close
            clauses[-1]["text"] = clause if words(clause) == clause_words else joined
            counter += 1
            cursor = end + 1
    return clauses


def build_script_context(
    artifacts: dict[str, Any],
    candidate: dict[str, Any],
    discovery_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    paragraph_ids = [str(x) for x in candidate.get("source_paragraph_ids") or []]
    paragraphs = artifacts["narration"].get("paragraphs") or []
    by_id = {str(p.get("id")): p for p in paragraphs}
    ordered_ids = [str(p.get("id")) for p in paragraphs]
    expanded: list[str] = []
    for pid in paragraph_ids:
        if pid not in ordered_ids:
            expanded.append(pid)
            continue
        index = ordered_ids.index(pid)
        for neighbor in ordered_ids[max(0, index - 1): min(len(ordered_ids), index + 2)]:
            if neighbor not in expanded:
                expanded.append(neighbor)

    source_paragraphs = []
    for pid in expanded:
        paragraph = by_id.get(pid)
        if not paragraph:
            continue
        source_paragraphs.append({
            "paragraph_id": pid,
            "text": _clean(str(paragraph.get("text", ""))),
            "claim_ids": [str(x) for x in paragraph.get("claim_ids") or []],
        })

    claim_set = set(map(str, candidate.get("claim_ids") or []))
    if candidate.get("primary_claim_id"):
        claim_set.add(str(candidate["primary_claim_id"]))
    claim_set.update(map(str, candidate.get("supporting_claim_ids") or []))

    claims = []
    if discovery_context:
        for item in discovery_context.get("claims") or []:
            if str(item.get("claim_id")) in claim_set or not claim_set:
                claims.append(item)
    if not claims:
        claims = [{"claim_id": cid, "text": cid} for cid in sorted(claim_set)]

    beat_ids = set(map(str, candidate.get("source_beat_ids") or []))
    for segment in candidate.get("source_segments") or []:
        beat_ids.update(map(str, segment.get("beat_ids") or []))
    visual_evidence = []
    if discovery_context:
        for beat in discovery_context.get("beats") or []:
            if str(beat.get("beat_id")) in beat_ids or str(beat.get("reel_id")) in {
                str(s.get("reel_id")) for s in candidate.get("source_segments") or []
            } or str(beat.get("reel_id")) in set(map(str, candidate.get("source_reel_ids") or [])):
                visual_evidence.append(beat)

    public_candidate = {
        key: value for key, value in candidate.items()
        if key not in {"scores"} or True
    }
    return {
        "candidate": public_candidate,
        "claims": claims,
        "source_paragraphs": source_paragraphs,
        "reusable_clauses": build_reusable_clauses(artifacts, expanded or paragraph_ids),
        "visual_evidence": visual_evidence,
        "voice_profile": {
            "audience": "IGCSE student",
            "energy": "curious challenger",
            "speech_style": "natural, concise, conversational",
        },
        "platform": {
            "aspect_ratio": "9:16",
            "captions_enabled": True,
            "first_line_must_work_as_on_screen_text": True,
            "duration_seconds": [MIN_SHORT_DURATION, MAX_SHORT_DURATION],
            "max_spoken_words": 170,
            "preferred_spoken_words": [80, 140],
        },
    }
