from __future__ import annotations

import difflib
import hashlib
import os
import re
from pathlib import Path
from typing import Any

from mav_audio import ffprobe_duration
from mav_schema import normalize_text, validate_timing, write_json, read_json

DEFAULT_WHISPER_MODEL = "base.en"
DEFAULT_WHISPER_LANGUAGE = "en"
MIN_WHISPER_PARAGRAPH_MATCH = 0.42
_WORD_RE = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)?")


def _word_tokens(text: str) -> list[str]:
    normalized = normalize_text(text).lower().replace("\u2019", "'")
    return _WORD_RE.findall(normalized)


def _timing_from_alignment(run_path: Path, narration: dict[str, Any], audio_duration: float) -> list[dict[str, Any]] | None:
    alignment_path = run_path / "audio_alignment.json"
    if not alignment_path.exists():
        return None
    payload = read_json(alignment_path)
    alignment = payload.get("normalized_alignment") or payload.get("alignment")
    if not alignment:
        return None
    chars = alignment.get("characters") or []
    starts = alignment.get("character_start_times_seconds") or []
    ends = alignment.get("character_end_times_seconds") or []
    if not chars or not starts or not ends or len(chars) != len(starts) or len(chars) != len(ends):
        return None
    full = "".join(chars)
    search_from = 0
    timed = []
    for index, paragraph in enumerate(narration["paragraphs"]):
        needle = normalize_text(paragraph["text"])
        found = full.find(needle, search_from)
        if found < 0:
            return None
        end_index = min(len(ends) - 1, found + len(needle) - 1)
        start = starts[found] if index else 0.0
        end = ends[end_index]
        timed.append({"id": paragraph["id"], "start": round(start, 3), "end": round(end, 3), "duration": round(end - start, 3)})
        search_from = end_index + 1
    if timed:
        timed[0]["start"] = 0.0
        timed[-1]["end"] = round(audio_duration, 3)
        timed[-1]["duration"] = round(timed[-1]["end"] - timed[-1]["start"], 3)
        for i in range(1, len(timed)):
            timed[i]["start"] = timed[i - 1]["end"]
            timed[i]["duration"] = round(timed[i]["end"] - timed[i]["start"], 3)
    return timed


def _extract_whisper_words(transcription: dict[str, Any]) -> list[dict[str, Any]]:
    words: list[dict[str, Any]] = []
    for segment in transcription.get("segments", []) or []:
        for item in segment.get("words", []) or []:
            raw = str(item.get("word") or "")
            start = item.get("start")
            end = item.get("end")
            if start is None or end is None:
                continue
            tokens = _word_tokens(raw)
            if not tokens:
                continue
            for token in tokens:
                words.append({"word": token, "start": float(start), "end": float(end)})
    return words


def _word_payload(word: dict[str, Any], *, index: int, paragraph_id: str) -> dict[str, Any]:
    start = round(float(word["start"]), 3)
    end = round(float(word["end"]), 3)
    return {
        "index": index,
        "paragraph_id": paragraph_id,
        "word": str(word["word"]),
        "start": start,
        "end": end,
        "duration": round(max(0.0, end - start), 3),
    }


def _best_transcript_window(
    target_words: list[str],
    transcript_words: list[dict[str, Any]],
    cursor: int,
    *,
    is_last: bool,
) -> tuple[int, int, float] | None:
    if not target_words or cursor >= len(transcript_words):
        return None
    if is_last:
        candidate_words = [item["word"] for item in transcript_words[cursor:]]
        score = difflib.SequenceMatcher(None, target_words, candidate_words).ratio()
        return cursor, len(transcript_words) - 1, score

    target_len = len(target_words)
    min_len = max(1, int(target_len * 0.6))
    max_len = max(min_len, int(target_len * 1.55) + 4)
    max_start = min(len(transcript_words), cursor + max(12, int(target_len * 0.35) + 6))
    best: tuple[int, int, float] | None = None
    for start in range(cursor, max_start):
        max_end = min(len(transcript_words), start + max_len)
        for end_exclusive in range(start + min_len, max_end + 1):
            candidate_words = [item["word"] for item in transcript_words[start:end_exclusive]]
            score = difflib.SequenceMatcher(None, target_words, candidate_words).ratio()
            if best is None or score > best[2]:
                best = (start, end_exclusive - 1, score)
    return best


def _timing_from_whisper_words(
    narration: dict[str, Any],
    transcript_words: list[dict[str, Any]],
    audio_duration: float,
) -> list[dict[str, Any]]:
    return _align_whisper_words_to_paragraphs(narration, transcript_words, audio_duration)["paragraphs"]


def _align_whisper_words_to_paragraphs(
    narration: dict[str, Any],
    transcript_words: list[dict[str, Any]],
    audio_duration: float,
) -> dict[str, Any]:
    if not transcript_words:
        raise RuntimeError("Whisper produced no word timestamps; cannot derive live-audio timing.")

    paragraphs = narration["paragraphs"]
    raw_ranges: list[dict[str, Any]] = []
    cursor = 0
    min_score = float(os.getenv("MAV_WHISPER_MIN_PARAGRAPH_MATCH", str(MIN_WHISPER_PARAGRAPH_MATCH)))
    for index, paragraph in enumerate(paragraphs):
        target_words = _word_tokens(paragraph["text"])
        if not target_words:
            raise RuntimeError(f"{paragraph['id']} has no spoken words to align with Whisper.")
        match = _best_transcript_window(target_words, transcript_words, cursor, is_last=index == len(paragraphs) - 1)
        if match is None:
            raise RuntimeError(f"Whisper could not align {paragraph['id']} to the transcript.")
        start_index, end_index, score = match
        if score < min_score:
            raise RuntimeError(
                f"Whisper paragraph alignment for {paragraph['id']} was too weak "
                f"({score:.2f} < {min_score:.2f}). Regenerate audio or lower MAV_WHISPER_MIN_PARAGRAPH_MATCH."
            )
        start = max(0.0, float(transcript_words[start_index]["start"]))
        end = min(audio_duration, max(start, float(transcript_words[end_index]["end"])))
        raw_ranges.append(
            {
                "id": paragraph["id"],
                "start": start,
                "end": end,
                "start_index": start_index,
                "end_index": end_index,
                "match_score": round(score, 3),
            }
        )
        cursor = end_index + 1

    timed: list[dict[str, Any]] = []
    tagged_words: list[dict[str, Any]] = []
    cursor_time = 0.0
    min_paragraph_duration = 0.05
    for index, paragraph_range in enumerate(raw_ranges):
        if index == len(raw_ranges) - 1:
            end = audio_duration
        else:
            next_start = raw_ranges[index + 1]["start"]
            remaining = len(raw_ranges) - index - 1
            latest_end = max(cursor_time + min_paragraph_duration, audio_duration - remaining * min_paragraph_duration)
            end = min(max(next_start, cursor_time + min_paragraph_duration), latest_end)
        timed.append(
            {
                "id": paragraph_range["id"],
                "start": round(cursor_time, 3),
                "end": round(end, 3),
                "duration": round(end - cursor_time, 3),
                "whisper_match_score": paragraph_range["match_score"],
            }
        )
        cursor_time = end
        for word in transcript_words[paragraph_range["start_index"] : paragraph_range["end_index"] + 1]:
            tagged_words.append(_word_payload(word, index=len(tagged_words), paragraph_id=paragraph_range["id"]))
    return {"paragraphs": timed, "words": tagged_words}


def _transcribe_audio_with_whisper(audio_path: Path) -> list[dict[str, Any]]:
    if not audio_path.exists() or audio_path.stat().st_size == 0:
        raise RuntimeError(f"Cannot run Whisper timing because {audio_path} is missing or empty.")
    try:
        import whisper
    except ImportError as exc:
        raise RuntimeError("OpenAI Whisper is required for live-audio timing. Install openai-whisper in the venv.") from exc

    model_name = os.getenv("MAV_WHISPER_MODEL", DEFAULT_WHISPER_MODEL)
    language = os.getenv("MAV_WHISPER_LANGUAGE", DEFAULT_WHISPER_LANGUAGE).strip() or None
    download_root = os.getenv("MAV_WHISPER_DOWNLOAD_ROOT") or None
    try:
        model = whisper.load_model(model_name, download_root=download_root)
        options: dict[str, Any] = {
            "word_timestamps": True,
            "fp16": False,
            "verbose": False,
        }
        if language:
            options["language"] = language
        transcription = model.transcribe(str(audio_path), **options)
    except Exception as exc:
        raise RuntimeError(f"Whisper transcription failed with model {model_name!r}: {exc}") from exc
    return _extract_whisper_words(transcription)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _derive_chapter_timing(run_path: Path, narration: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    paragraphs = {str(item["id"]): item for item in narration["paragraphs"]}
    global_words: list[dict[str, Any]] = []
    timed_paragraphs: list[dict[str, Any]] = []
    voiceover = run_path / "voiceover.mp3"
    voiceover_hash = _sha256(voiceover)
    cached_words_path = run_path / "audio_word_timestamps.json"
    cached_timing_path = run_path / "audio_timing.json"
    cached_words = read_json(cached_words_path) if cached_words_path.exists() else {}
    cached_timing = read_json(cached_timing_path) if cached_timing_path.exists() else {}
    reuse_alignment = cached_words.get("source") == "chapter_whisper_word_timestamps" and cached_words.get("voiceover_sha256") == voiceover_hash
    cached_by_chapter: dict[str, list[dict[str, Any]]] = {}
    if reuse_alignment:
        for word in cached_words.get("words") or []:
            cached_by_chapter.setdefault(str(word.get("paragraph_id")), []).append(word)
    cached_paragraphs = {str(item.get("id")): item for item in cached_timing.get("paragraphs") or []}
    for chapter in manifest.get("chapters") or []:
        chapter_id = str(chapter["id"])
        paragraph = paragraphs.get(chapter_id)
        if paragraph is None:
            raise RuntimeError(f"Audio chapter {chapter_id} does not match narration")
        audio_path = run_path / str(chapter["path"])
        speech_duration = float(chapter["speech_duration"])
        absolute_start = float(chapter["absolute_start"])
        absolute_end = float(chapter["absolute_end"])
        if reuse_alignment and cached_by_chapter.get(chapter_id):
            chapter_words = cached_by_chapter[chapter_id]
            match_score = float(cached_paragraphs.get(chapter_id, {}).get("whisper_match_score", 1))
            for item in chapter_words:
                global_words.append({**item, "index": len(global_words)})
        else:
            transcript_words = _transcribe_audio_with_whisper(audio_path)
            aligned = _align_whisper_words_to_paragraphs({"paragraphs": [paragraph]}, transcript_words, speech_duration)
            match_score = aligned["paragraphs"][0]["whisper_match_score"]
            for item in aligned["words"]:
                start = round(absolute_start + float(item["start"]), 3)
                end = round(absolute_start + float(item["end"]), 3)
                global_words.append({**item, "index": len(global_words), "start": start, "end": end, "duration": round(max(0, end - start), 3)})
        timed_paragraphs.append({
            "id": chapter_id, "start": round(absolute_start, 3), "end": round(absolute_end, 3),
            "duration": round(absolute_end - absolute_start, 3),
            "speech_duration": round(speech_duration, 3), "trailing_pause": round(float(chapter.get("trailing_pause", 0)), 3),
            "whisper_match_score": match_score,
        })
    timeline_duration = float((manifest.get("chapters") or [{}])[-1].get("absolute_end", 0))
    if timeline_duration <= 0:
        raise RuntimeError("Chapter audio manifest has no valid timeline duration")
    return {
        "audio_duration_seconds": round(timeline_duration, 3),
        "mp3_container_duration_seconds": round(ffprobe_duration(voiceover) or timeline_duration, 3),
        "source": "chapter_whisper_word_timestamps", "voiceover_sha256": voiceover_hash,
        "paragraphs": timed_paragraphs, "words": global_words,
    }


def derive_timing(run_path: Path, narration: dict[str, Any], *, fallback_duration: float) -> dict[str, Any]:
    duration = ffprobe_duration(run_path / "voiceover.mp3") or fallback_duration
    chapter_manifest_path = run_path / "audio_chunks" / "manifest.json"
    if chapter_manifest_path.exists():
        chapter_timing = _derive_chapter_timing(run_path, narration, read_json(chapter_manifest_path))
        word_payload = {
            "audio_duration_seconds": chapter_timing["audio_duration_seconds"], "source": chapter_timing["source"],
            "voiceover_sha256": chapter_timing["voiceover_sha256"], "words": chapter_timing["words"],
        }
        write_json(run_path / "audio_word_timestamps.json", word_payload)
        payload = {key: value for key, value in chapter_timing.items() if key != "words"}
        payload["word_timestamps"] = "audio_word_timestamps.json"
        write_json(run_path / "audio_timing.json", payload)
        violations = validate_timing(payload, narration)
        if violations:
            raise ValueError("; ".join(v.message for v in violations))
        return payload
    aligned = _timing_from_alignment(run_path, narration, duration)
    if aligned:
        payload = {"audio_duration_seconds": round(duration, 3), "source": "elevenlabs_character_alignment", "paragraphs": aligned}
        write_json(run_path / "audio_timing.json", payload)
        violations = validate_timing(payload, narration)
        if violations:
            raise ValueError("; ".join(v.message for v in violations))
        return payload

    transcript_words = _transcribe_audio_with_whisper(run_path / "voiceover.mp3")
    aligned = _align_whisper_words_to_paragraphs(narration, transcript_words, duration)
    word_payload = {
        "audio_duration_seconds": round(duration, 3),
        "source": "openai_whisper_word_timestamps",
        "words": aligned["words"],
    }
    write_json(run_path / "audio_word_timestamps.json", word_payload)
    payload = {
        "audio_duration_seconds": round(duration, 3),
        "source": "openai_whisper_word_timestamps",
        "word_timestamps": "audio_word_timestamps.json",
        "paragraphs": aligned["paragraphs"],
    }
    write_json(run_path / "audio_timing.json", payload)
    violations = validate_timing(payload, narration)
    if violations:
        raise ValueError("; ".join(v.message for v in violations))
    return payload
