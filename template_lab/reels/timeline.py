from __future__ import annotations

import hashlib
import json
import math
from typing import Any


def _timeline_id(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def _split_points(words: list[dict[str, Any]], start: float, end: float, *, maximum: float = 9.0) -> list[float]:
    boundaries = [start]
    cursor = start
    while end - cursor > maximum:
        midpoint = min(end, cursor + maximum * .72)
        candidates = []
        for left, right in zip(words, words[1:]):
            at = float(right["start"])
            if cursor + 2.5 <= at <= min(end - 2.5, cursor + maximum):
                gap = max(0.0, at - float(left["end"]))
                candidates.append((abs(at - midpoint) - min(.7, gap) * 2, at))
        if not candidates:
            break
        chosen = min(candidates)[1]
        boundaries.append(chosen)
        cursor = chosen
    boundaries.append(end)
    return boundaries


def build_immutable_shot_timeline(
    words_payload: dict[str, Any], audio_timing: dict[str, Any], *, fps: int = 30,
    width: int = 1080, height: int = 1920,
) -> dict[str, Any]:
    words = list(words_payload.get("words") or [])
    if not words:
        raise RuntimeError("Reel immutable timeline requires local word timestamps")
    by_paragraph: dict[str, list[dict[str, Any]]] = {}
    for word in words:
        by_paragraph.setdefault(str(word.get("paragraph_id")), []).append(word)
    ranges = list(audio_timing.get("paragraphs") or [])
    if not ranges:
        raise RuntimeError("Reel immutable timeline requires paragraph timing")
    total_duration = float(audio_timing.get("audio_duration_seconds") or ranges[-1]["end"])
    shots: list[dict[str, Any]] = []
    previous_frame = 0
    for paragraph in ranges:
        paragraph_id = str(paragraph["id"])
        start, end = float(paragraph["start"]), float(paragraph["end"])
        paragraph_words = by_paragraph.get(paragraph_id, [])
        boundaries = _split_points(paragraph_words, start, end)
        for segment_index, (segment_start, segment_end) in enumerate(zip(boundaries, boundaries[1:])):
            local_words = [word for word in paragraph_words if float(word["start"]) < segment_end and float(word["end"]) > segment_start]
            is_final = paragraph is ranges[-1] and segment_index == len(boundaries) - 2
            end_frame = math.ceil(total_duration * fps) if is_final else round(segment_end * fps)
            end_frame = max(previous_frame + 1, end_frame)
            shot_id = f"shot_{len(shots) + 1:03d}"
            shots.append({
                "id": shot_id, "scene_id": shot_id, "source_paragraph_ids": [paragraph_id],
                "absolute_start": previous_frame / fps, "absolute_end": end_frame / fps,
                "duration": (end_frame - previous_frame) / fps,
                "render_start_frame": previous_frame, "render_end_frame": end_frame,
                "render_absolute_start": previous_frame / fps, "render_absolute_end": end_frame / fps,
                "render_duration": (end_frame - previous_frame) / fps,
                "narration": " ".join(str(word["word"]) for word in local_words),
                "words": [{"word": str(word["word"]), "start": round(max(0.0, float(word["start"]) - segment_start), 3),
                           "end": round(max(0.0, float(word["end"]) - segment_start), 3)} for word in local_words],
            })
            previous_frame = end_frame
    payload = {
        "version": "1.0", "mode": "immutable_shots", "profile": "reel_portrait", "fps": fps,
        "width": width, "height": height, "voiceover_sha256": str(words_payload.get("voiceover_sha256") or ""),
        "total_frames": previous_frame, "shots": shots,
    }
    payload["timeline_id"] = _timeline_id(payload)
    return payload


def validate_immutable_shot_timeline(payload: dict[str, Any]) -> None:
    previous = 0
    for shot in payload.get("shots") or []:
        if int(shot["render_start_frame"]) != previous or int(shot["render_end_frame"]) <= previous:
            raise RuntimeError(f"Non-contiguous immutable Reel timeline at {shot.get('scene_id')}")
        previous = int(shot["render_end_frame"])
    if previous != int(payload.get("total_frames") or -1):
        raise RuntimeError("Immutable Reel total_frames does not match its final boundary")
