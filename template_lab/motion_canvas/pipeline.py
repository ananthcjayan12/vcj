"""MAV-native adaptation of the isolated Motion Canvas batch robot."""
from __future__ import annotations

import json
import hashlib
import math
import os
import re
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

DEFAULT_BATCH_SIZE = 2
DEFAULT_WORKERS = 2
MOTION_CANVAS_MAX_TOKENS = 64_000
MOTION_CANVAS_FPS = 30
SHOT_TARGET_SECONDS = 10.0
SHOT_MIN_SECONDS = 5.0
SHOT_MAX_SECONDS = 15.0
RUNTIME_ROOT = Path(__file__).resolve().parents[2] / "motion_canvas_runtime"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.rstrip() + "\n", encoding="utf-8")


def _write_json(path: Path, value: Any) -> None:
    _write(path, json.dumps(value, indent=2, ensure_ascii=False))


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def split_chapters(words_payload: dict[str, Any], narration: dict[str, Any] | None = None, *, cutoff: float | None = None) -> list[dict[str, Any]]:
    """Reference `_chapter_segments`, generalized from two minutes to a MAV run."""
    words = list(words_payload.get("words") or [])
    if not words:
        raise RuntimeError("Timestamp file contains no words")
    available = float(words_payload.get("audio_duration_seconds") or words[-1]["end"])
    selected = min(float(cutoff if cutoff is not None else available), available)
    grouped: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    for word in words:
        paragraph_id = str(word.get("paragraph_id") or "paragraph")
        if paragraph_id not in grouped:
            grouped[paragraph_id] = []
            order.append(paragraph_id)
        grouped[paragraph_id].append(word)
    included = [paragraph_id for paragraph_id in order if float(grouped[paragraph_id][0]["start"]) < selected]
    chapters: list[dict[str, Any]] = []
    for index, paragraph_id in enumerate(included):
        start = 0.0 if index == 0 else float(grouped[paragraph_id][0]["start"])
        next_start = float(grouped[included[index + 1]][0]["start"]) if index + 1 < len(included) else selected
        end = min(selected, next_start)
        if end <= start:
            continue
        local_words = []
        for word in grouped[paragraph_id]:
            word_start = float(word["start"])
            if word_start >= end:
                break
            local_words.append({
                "word": str(word["word"]),
                "start": round(max(0.0, word_start - start), 3),
                "end": round(min(end, float(word["end"])) - start, 3),
            })
        chapters.append({
            "id": paragraph_id, "scene_id": f"chapter_{len(chapters)+1:02d}",
            "absolute_start": round(start, 3), "absolute_end": round(end, 3),
            "duration": round(end - start, 3),
            "narration": " ".join(item["word"] for item in local_words), "words": local_words,
        })
    return chapters


def _split_from_audio_manifest(words_payload: dict[str, Any], audio_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for word in words_payload.get("words") or []:
        grouped.setdefault(str(word.get("paragraph_id")), []).append(word)
    chapters = []
    for record in audio_manifest.get("chapters") or []:
        paragraph_id = str(record["id"])
        start, end = float(record["absolute_start"]), float(record["absolute_end"])
        local_words = [{"word": str(word["word"]), "start": round(float(word["start"]) - start, 3), "end": round(float(word["end"]) - start, 3)} for word in grouped.get(paragraph_id, [])]
        chapters.append({
            "id": paragraph_id, "scene_id": f"chapter_{len(chapters) + 1:02d}", "absolute_start": round(start, 3),
            "absolute_end": round(end, 3), "duration": round(end - start, 3),
            "speech_duration": round(float(record.get("speech_duration", end - start)), 3),
            "trailing_pause": round(float(record.get("trailing_pause", 0)), 3),
            "narration": " ".join(item["word"] for item in local_words), "words": local_words,
        })
    return chapters


def _timeline_units(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    if manifest.get("timeline_mode") == "immutable_reels":
        return list(manifest.get("reels") or [])
    return list(manifest.get("shots") or manifest.get("chapters") or [])


def _unit_directory(manifest: dict[str, Any]) -> str:
    if manifest.get("timeline_mode") == "immutable_reels":
        return "reels"
    return "shots" if manifest.get("timeline_mode") == "immutable_shots" else "chapters"


def _unit_path(root: Path, unit_id: str, suffix: str, manifest: dict[str, Any] | None = None) -> Path:
    if manifest is not None:
        return root / _unit_directory(manifest) / f"{unit_id}{suffix}"
    reel_path = root / "reels" / f"{unit_id}{suffix}"
    if reel_path.exists() or unit_id.startswith("reel_"):
        return reel_path
    shot_path = root / "shots" / f"{unit_id}{suffix}"
    return shot_path if shot_path.exists() or unit_id.startswith("shot_") else root / "chapters" / f"{unit_id}{suffix}"


def _shot_boundaries(
    words: list[dict[str, Any]],
    start: float,
    end: float,
    *,
    target: float = SHOT_TARGET_SECONDS,
    minimum: float = SHOT_MIN_SECONDS,
    maximum: float = SHOT_MAX_SECONDS,
) -> list[float]:
    """Choose stable edit points at word starts, preferring measured pauses near the target."""
    boundaries = [start]
    candidates: list[tuple[float, float]] = []
    ordered = sorted(words, key=lambda item: float(item["start"]))
    for previous, following in zip(ordered, ordered[1:]):
        boundary = float(following["start"])
        if start < boundary < end:
            gap = max(0.0, boundary - float(previous["end"]))
            candidates.append((boundary, gap))
    cursor = start
    while end - cursor > maximum:
        eligible = [(at, gap) for at, gap in candidates if cursor + minimum <= at <= cursor + maximum]
        if eligible:
            desired = cursor + target
            # A pause of 0.5 s can outweigh being about 1 s farther from the target.
            chosen = min(eligible, key=lambda item: (abs(item[0] - desired) - min(item[1], 0.5) * 2, item[0]))[0]
        else:
            chosen = min(cursor + maximum, end)
        if chosen <= cursor + 0.001:
            break
        boundaries.append(chosen)
        cursor = chosen
    if end - boundaries[-1] < minimum and len(boundaries) > 1:
        boundaries.pop()
    boundaries.append(end)
    return boundaries


def build_immutable_timeline(words_payload: dict[str, Any], audio_manifest: dict[str, Any]) -> dict[str, Any]:
    """Build continuous visual reels with immutable, non-scene beat edit windows."""
    sample_rate = int(audio_manifest.get("sample_rate") or 24_000)
    all_words = list(words_payload.get("words") or [])
    reels: list[dict[str, Any]] = []
    beats: list[dict[str, Any]] = []
    previous_frame = 0
    records = list(audio_manifest.get("chapters") or [])
    for reel_index, record in enumerate(records, start=1):
        reel_start = float(record["absolute_start"])
        reel_end = float(record["absolute_end"])
        reel_words = [
            word for word in all_words
            if float(word["start"]) < reel_end and float(word["end"]) > reel_start
        ]
        reel_id = f"reel_{reel_index:03d}"
        is_final_reel = reel_index == len(records)
        reel_end_frame = math.ceil(reel_end * MOTION_CANVAS_FPS) if is_final_reel else round(reel_end * MOTION_CANVAS_FPS)
        reel_end_frame = max(previous_frame + 1, reel_end_frame)
        reel_local_words = [{
            "word": str(word["word"]),
            "start": round(max(0.0, float(word["start"]) - reel_start), 3),
            "end": round(min(reel_end, float(word["end"])) - reel_start, 3),
        } for word in reel_words]
        reel_beats: list[dict[str, Any]] = []
        boundaries = _shot_boundaries(reel_words, reel_start, reel_end)
        boundary_pairs = list(zip(boundaries, boundaries[1:]))
        beat_frame_cursor = previous_frame
        for beat_index, (beat_start, beat_end) in enumerate(boundary_pairs):
            beat_end_frame = reel_end_frame if beat_index == len(boundary_pairs) - 1 else round(beat_end * MOTION_CANVAS_FPS)
            beat_end_frame = max(beat_frame_cursor + 1, beat_end_frame)
            local_words = []
            for word in reel_words:
                word_start, word_end = float(word["start"]), float(word["end"])
                if word_start >= beat_end or word_end <= beat_start:
                    continue
                local_words.append({
                    "word": str(word["word"]),
                    "start": round(max(0.0, word_start - reel_start), 3),
                    "end": round(min(beat_end, word_end) - reel_start, 3),
                })
            beat_id = f"beat_{len(beats) + 1:03d}"
            beat = {
                "id": beat_id,
                "beat_id": beat_id,
                "reel_id": reel_id,
                "source_paragraph_id": str(record["id"]),
                "absolute_start": round(beat_start, 6),
                "absolute_end": round(beat_end, 6),
                "duration": round(beat_end - beat_start, 6),
                "local_start": round(beat_start - reel_start, 6),
                "local_end": round(beat_end - reel_start, 6),
                "audio_start_sample": round(beat_start * sample_rate),
                "audio_end_sample": round(beat_end * sample_rate),
                "render_start_frame": beat_frame_cursor,
                "render_end_frame": beat_end_frame,
                "narration": " ".join(item["word"] for item in local_words),
            }
            beats.append(beat)
            reel_beats.append(beat)
            beat_frame_cursor = beat_end_frame
        reel = {
            "id": reel_id,
            "scene_id": reel_id,
            "reel_id": reel_id,
            "source_id": str(record["id"]),
            "source_paragraph_id": str(record["id"]),
            "audio_path": str(record.get("path") or ""),
            "audio_cache_key": str(record.get("cache_key") or ""),
            "absolute_start": reel_start,
            "absolute_end": reel_end,
            "duration": round(reel_end - reel_start, 6),
            "audio_start_sample": round(reel_start * sample_rate),
            "audio_end_sample": round(reel_end * sample_rate),
            "render_start_frame": previous_frame,
            "render_end_frame": reel_end_frame,
            "render_absolute_start": previous_frame / MOTION_CANVAS_FPS,
            "render_absolute_end": reel_end_frame / MOTION_CANVAS_FPS,
            "render_duration": (reel_end_frame - previous_frame) / MOTION_CANVAS_FPS,
            "narration": " ".join(item["word"] for item in reel_local_words),
            "words": reel_local_words,
            "beats": reel_beats,
            "beat_ids": [item["beat_id"] for item in reel_beats],
        }
        reels.append(reel)
        previous_frame = reel_end_frame
    immutable = {
        "version": "3.0",
        "mode": "immutable_reels",
        "fps": MOTION_CANVAS_FPS,
        "sample_rate": sample_rate,
        "voiceover_sha256": str(words_payload.get("voiceover_sha256") or ""),
        "total_frames": previous_frame,
        "total_samples": round(float((audio_manifest.get("chapters") or [{}])[-1].get("absolute_end", 0)) * sample_rate),
        "reels": reels,
        "beats": beats,
    }
    immutable["timeline_id"] = hashlib.sha256(
        json.dumps(immutable, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return immutable


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_chapter_cues(root: Path, chapters: list[dict[str, Any]], *, directory: str = "chapters") -> None:
    for chapter in chapters:
        cues: dict[str, list[float]] = {}
        for word in chapter.get("words") or []:
            key = re.sub(r"[^a-z0-9]+", "_", str(word["word"]).lower()).strip("_")
            if key:
                cues.setdefault(key, []).append(round(float(word["start"]), 3))
        source = "// Deterministic chapter-local word cues. Generated by MAV; do not edit.\nexport const CUES = " + json.dumps(cues, ensure_ascii=False, separators=(",", ":")) + " as const;"
        _write(root / directory / f"{chapter['scene_id']}.cues.ts", source)


def _apply_frame_aligned_timing(manifest: dict[str, Any]) -> dict[str, Any]:
    """Quantize cumulative chapter boundaries so frame rounding cannot accumulate."""
    chapters = _timeline_units(manifest)
    if manifest.get("timeline_mode") in {"immutable_shots", "immutable_reels"} and chapters:
        previous_end = 0
        for shot in chapters:
            start_frame = int(shot["render_start_frame"])
            end_frame = int(shot["render_end_frame"])
            if start_frame != previous_end or end_frame <= start_frame:
                raise RuntimeError(f"Immutable timeline is not contiguous at {shot.get('scene_id')}")
            expected_duration = (end_frame - start_frame) / MOTION_CANVAS_FPS
            if abs(float(shot["render_duration"]) - expected_duration) > 1e-9:
                raise RuntimeError(f"Immutable timeline duration changed for {shot.get('scene_id')}")
            previous_end = end_frame
        manifest["render_fps"] = MOTION_CANVAS_FPS
        manifest["render_duration"] = previous_end / MOTION_CANVAS_FPS
        return manifest
    previous_end_frame = 0
    fallback_absolute_end = 0.0
    for index, chapter in enumerate(chapters):
        fallback_absolute_end += float(chapter.get("duration") or 0)
        absolute_end = float(chapter.get("absolute_end", fallback_absolute_end))
        if index == len(chapters) - 1:
            end_frame = math.ceil(absolute_end * MOTION_CANVAS_FPS)
        else:
            end_frame = round(absolute_end * MOTION_CANVAS_FPS)
        end_frame = max(previous_end_frame + 1, end_frame)
        chapter["render_start_frame"] = previous_end_frame
        chapter["render_end_frame"] = end_frame
        chapter["render_absolute_start"] = previous_end_frame / MOTION_CANVAS_FPS
        chapter["render_absolute_end"] = end_frame / MOTION_CANVAS_FPS
        chapter["render_duration"] = (end_frame - previous_end_frame) / MOTION_CANVAS_FPS
        previous_end_frame = end_frame
    manifest["render_fps"] = MOTION_CANVAS_FPS
    manifest["render_duration"] = previous_end_frame / MOTION_CANVAS_FPS if chapters else 0
    return manifest


def _enforce_manifest_duration(source: str, chapter: dict[str, Any]) -> str:
    """Keep generated scene duration equal to its cumulative frame-aligned slot."""
    expected = float(chapter.get("render_duration", chapter.get("duration", 0)))
    pattern = r"(\bconst\s+CHAPTER_DURATION\s*=\s*)(\d+(?:\.\d+)?)(\s*;)"
    matches = list(re.finditer(pattern, source))
    if not matches:
        if str(chapter.get("scene_id", "")).startswith(("shot_", "reel_")):
            raise RuntimeError(f"{chapter['scene_id']} cannot own or omit timing; CHAPTER_DURATION is required")
        return source
    if len(matches) != 1:
        raise RuntimeError(f"{chapter.get('scene_id', 'chapter')} must define CHAPTER_DURATION exactly once")
    # Motion Canvas advances scenes on whole frames using an end-time comparison.
    # Repeating frame fractions rounded upward as decimal literals (for example,
    # 365 / 30 -> 12.166666666667) can therefore add a frame to every affected
    # scene. Keep frame-bounded slots infinitesimally inside their final frame;
    # the renderer still reaches progress=1 on the authoritative boundary.
    start_frame = chapter.get("render_start_frame")
    end_frame = chapter.get("render_end_frame")
    if start_frame is not None and end_frame is not None:
        frame_count = int(end_frame) - int(start_frame)
        if frame_count <= 0:
            raise RuntimeError(f"{chapter.get('scene_id', 'chapter')} has an invalid frame duration")
        expected = frame_count / MOTION_CANVAS_FPS
        # Apply the inward bias even to whole-second slots: adding an exact
        # duration to a fractional global start frame can still land a few
        # floating-point ulps beyond the intended cumulative boundary.
        expected -= 1e-7
    rendered = f"{expected:.12f}".rstrip("0").rstrip(".")
    aligned = re.sub(pattern, rf"\g<1>{rendered}\g<3>", source, count=1)
    if str(chapter.get("scene_id", "")).startswith(("shot_", "reel_")) and not re.search(
        r"yield\*\s+progress\(1,\s*CHAPTER_DURATION,\s*linear\)", aligned
    ):
        raise RuntimeError(f"{chapter['scene_id']} must end on the immutable master-clock duration")
    return aligned


IMMUTABLE_UNIT_FIELDS = (
    "scene_id", "reel_id", "absolute_start", "absolute_end",
    "audio_start_sample", "audio_end_sample", "render_start_frame", "render_end_frame",
    "beat_ids",
)
IMMUTABLE_BEAT_FIELDS = (
    "beat_id", "reel_id", "absolute_start", "absolute_end", "local_start", "local_end",
    "audio_start_sample", "audio_end_sample", "render_start_frame", "render_end_frame",
)


def _assert_immutable_timeline(run_path: Path, manifest: dict[str, Any]) -> None:
    timeline_mode = manifest.get("timeline_mode")
    if timeline_mode not in {"immutable_shots", "immutable_reels"}:
        return
    timeline_path = run_path / "motion_canvas" / "timeline.json"
    if not timeline_path.exists():
        raise RuntimeError("Immutable visual timeline is missing")
    timeline = _load(timeline_path)
    stored_id = timeline.get("timeline_id")
    hash_payload = {key: value for key, value in timeline.items() if key != "timeline_id"}
    measured_id = hashlib.sha256(
        json.dumps(hash_payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if stored_id != measured_id or stored_id != manifest.get("timeline_id"):
        raise RuntimeError("Timeline identity changed; visual regeneration is not allowed to retime audio")
    expected_audio_hash = str(timeline.get("voiceover_sha256") or "")
    voiceover = run_path / "voiceover.mp3"
    if expected_audio_hash and (not voiceover.exists() or _sha256(voiceover) != expected_audio_hash):
        raise RuntimeError("Master audio changed after the immutable timeline was created")
    timeline_units = timeline.get("reels") if timeline_mode == "immutable_reels" else timeline.get("shots")
    fixed_by_id = {str(item["scene_id"]): item for item in timeline_units or []}
    units = _timeline_units(manifest)
    if set(fixed_by_id) != {str(item["scene_id"]) for item in units}:
        raise RuntimeError("Visual reel membership changed after the immutable timeline was created")
    for shot in units:
        fixed = fixed_by_id[str(shot["scene_id"])]
        for field in IMMUTABLE_UNIT_FIELDS:
            if shot.get(field) != fixed.get(field):
                raise RuntimeError(f"Immutable timing field {field} changed for {shot['scene_id']}")
    if timeline_mode == "immutable_reels":
        fixed_beats = {str(item["beat_id"]): item for item in timeline.get("beats") or []}
        manifest_beats = {str(item["beat_id"]): item for item in manifest.get("beats") or []}
        if set(fixed_beats) != set(manifest_beats):
            raise RuntimeError("Beat membership changed after the immutable timeline was created")
        for beat_id, beat in manifest_beats.items():
            for field in IMMUTABLE_BEAT_FIELDS:
                if beat.get(field) != fixed_beats[beat_id].get(field):
                    raise RuntimeError(f"Immutable beat field {field} changed for {beat_id}")


def prepare(run_path: Path, narration: dict[str, Any] | None = None, *, batch_size: int = DEFAULT_BATCH_SIZE, duration: float | None = None) -> dict[str, Any]:
    if batch_size < 1 or batch_size > 3:
        raise RuntimeError("Batch size must be between 1 and 3")
    audio_path, timestamps_path = run_path / "voiceover.mp3", run_path / "audio_word_timestamps.json"
    if not audio_path.exists() or not timestamps_path.exists():
        raise RuntimeError("Motion Canvas requires voiceover.mp3 and audio_word_timestamps.json")
    timing = _load(timestamps_path)
    available = float(timing.get("audio_duration_seconds") or (timing.get("words") or [{}])[-1].get("end", 0))
    cutoff = min(float(duration if duration is not None else available), available)
    expected_audio_hash = timing.get("voiceover_sha256")
    if expected_audio_hash and expected_audio_hash != _sha256(audio_path):
        raise RuntimeError("Word timestamps are stale: voiceover.mp3 changed after alignment")
    audio_manifest_path = run_path / "audio_chunks" / "manifest.json"
    audio_manifest = _load(audio_manifest_path) if audio_manifest_path.exists() else None
    timeline = build_immutable_timeline(timing, audio_manifest) if audio_manifest else None
    chapters = timeline["reels"] if timeline else split_chapters(timing, narration, cutoff=cutoff)
    if audio_manifest and abs(float(timeline["total_samples"]) / float(timeline["sample_rate"]) - available) > 0.05:
        raise RuntimeError("Chapter audio, word timestamps, and lesson duration disagree")
    batches = []
    for offset in range(0, len(chapters), batch_size):
        members = chapters[offset:offset + batch_size]
        batches.append({"id": f"batch_{len(batches)+1:02d}", "chapter_ids": [item["scene_id"] for item in members], "status": "pending"})
    root = run_path / "motion_canvas"
    manifest = {
        "version": "2.0" if timeline else "1.0", "created_at": _now(), "source_audio": str(audio_path.resolve()),
        "source_timestamps": str(timestamps_path.resolve()), "preview_duration": cutoff,
        "batch_size": batch_size, "batches": batches,
    }
    if timeline:
        manifest.update({
            "timeline_mode": "immutable_reels",
            "timeline_id": timeline["timeline_id"],
            "sample_rate": timeline["sample_rate"],
            "total_samples": timeline["total_samples"],
            "reels": timeline["reels"],
            "beats": timeline["beats"],
        })
        _write_json(root / "timeline.json", timeline)
    else:
        manifest["chapters"] = chapters
    _apply_frame_aligned_timing(manifest)
    _write_json(root / "manifest.json", manifest)
    _write_chapter_cues(root, chapters, directory=_unit_directory(manifest))
    shutil.copy2(audio_path, root / "voiceover.mp3")
    return manifest


def _batch_prompt(
    root: Path,
    manifest: dict[str, Any],
    batch: dict[str, Any],
    *,
    instruction: str = "",
) -> tuple[str, str]:
    prompt_root = Path(__file__).with_name("prompts")
    system = (prompt_root / "batch.system.txt").read_text(encoding="utf-8")
    approved = (prompt_root / "approved-api.md").read_text(encoding="utf-8")
    chapter_by_id = {chapter["scene_id"]: chapter for chapter in _timeline_units(manifest)}
    chapters = [chapter_by_id[chapter_id] for chapter_id in batch["chapter_ids"]]
    markers = "\n".join(f"=== {chapter['scene_id']}.tsx ===" for chapter in chapters)
    user = (
        "OUTPUT MARKERS\nReturn these markers in this exact order, each followed by its complete TSX file:\n"
        f"{markers}\n\nFIXED VISUAL THEME\nCanvas 1920x1080; background #07111f; panel #0e1d31; text #eaf3ff; muted #91a8c5; "
        "cyan #46d9ff; amber #ffc857; coral #ff6b6b; minimum important text 30px. Motion Canvas origin is the CENTER at (0,0), "
        "visible x=-960..960 and y=-540..540; keep complete important content inside x=-860..860 and y=-440..440. Do not use browser/top-left coordinates.\n\n"
        f"APPROVED API\n{approved}\n\nFIXED CONTINUOUS REEL DATA\n{json.dumps(chapters, ensure_ascii=False, separators=(',', ':'))}\n\n"
        "Each reel is one continuous visual scene on the master audio timeline. Its beats are edit markers, not scene boundaries. "
        "Use the supplied reel-local word times and evolve a persistent composition across beats. "
        "Set CHAPTER_DURATION to render_duration exactly. The sum of frame-aligned render durations is assembled locally; "
        "do not add padding outside the supplied reel duration and never alter reel or beat boundaries."
        + (
            "\n\nBOUNDED REEL/BEAT EDIT REQUEST\n"
            "Apply this request inside the named reel/beat window while preserving the reel clock, surrounding visual state, narration timing, and factual meaning:\n"
            f"{instruction}"
            if instruction
            else ""
        )
    )
    _write(root / "prompts" / f"{batch['id']}.txt", f"SYSTEM\n{system}\n\nUSER\n{user}")
    return system, user


def _validate_chapter_source(content: str, chapter_id: str) -> None:
    if not content or "```" in content or "from 'http" in content or 'from "http' in content:
        raise RuntimeError(f"Unsafe or empty chapter: {chapter_id}")
    if "makeScene2D" in content:
        invalid_numeric_cue = re.search(r"\bCUES\.(\d[\w$]*)", content)
        if invalid_numeric_cue:
            raise RuntimeError(
                f"{chapter_id} uses invalid numeric cue access CUES.{invalid_numeric_cue.group(1)}; "
                "use bracket notation"
            )
        for comparison in re.findall(r"<TwoColumnComparison\b[\s\S]*?/>", content):
            if not re.search(r"\bleft=\{\{", comparison) or not re.search(r"\bright=\{\{", comparison):
                raise RuntimeError(
                    f"{chapter_id} must pass TwoColumnComparison left/right TextItem objects; "
                    "put placement and opacity on a wrapping Layout"
                )
        if "../../presentation" not in content:
            raise RuntimeError(f"{chapter_id} must use the fixed presentation components")
        if f"./{chapter_id}.cues" not in content:
            raise RuntimeError(f"{chapter_id} must import its deterministic CUES module")
        for raw_text in re.findall(r"<Txt\b[\s\S]*?\btext=[\"']([^\"']+)[\"'][\s\S]*?/?>", content):
            if len(raw_text.split()) > 6:
                raise RuntimeError(f"{chapter_id} uses raw Txt for prose: {raw_text!r}")
            if re.search(r"\\(?:text|frac|dfrac|sqrt|vec|mathbf|mathrm|quad|Rightarrow|uparrow|downarrow)\b", raw_text):
                raise RuntimeError(f"{chapter_id} exposes LaTeX through raw Txt; use EquationCard instead: {raw_text!r}")
        for size in re.findall(r"<Txt\b[\s\S]*?\bfontSize=\{(\d+)\}[\s\S]*?/?>", content):
            if int(size) < 26 or int(size) > 32:
                raise RuntimeError(f"{chapter_id} raw diagram-label fontSize must be 26-32")


def _normalize_chapter_source(content: str) -> str:
    """Repair syntax-safe mechanical drift without another model call."""
    content = re.sub(r"\bCUES\.(\d[\w$]*)", lambda match: f'CUES["{match.group(1)}"]', content)
    key_group = 0
    def unique_index_key(_match: re.Match[str]) -> str:
        nonlocal key_group
        replacement = f"key={{`mapped-{key_group}-${{String(index)}}`}}"
        key_group += 1
        return replacement
    return re.sub(r"key=\{String\(index\)\}", unique_index_key, content)


def _validate_cue_references(root: Path, content: str, chapter_id: str) -> None:
    cue_path = _unit_path(root, chapter_id, ".cues.ts")
    match = re.search(r"export const CUES = (\{.*\}) as const;", cue_path.read_text(encoding="utf-8"))
    if not match:
        raise RuntimeError(f"Cannot read deterministic cues for {chapter_id}")
    cues = json.loads(match.group(1))
    references = re.findall(r'CUES(?:\.([A-Za-z_$][\w$]*)|\["([^"]+)"\])\[(\d+)\]', content)
    for dotted, bracketed, raw_index in references:
        key = dotted or bracketed
        index = int(raw_index)
        if key not in cues:
            raise RuntimeError(f"{chapter_id} references missing cue {key!r}")
        if index >= len(cues[key]):
            raise RuntimeError(
                f"{chapter_id} references CUES[{key!r}][{index}], but that cue has only {len(cues[key])} occurrence(s)"
            )


def _extract_response(response: str, chapter_ids: list[str]) -> dict[str, str]:
    if "```" in response:
        raise RuntimeError("Response contains Markdown fences")
    pattern = "|".join(re.escape(f"=== {chapter_id}.tsx ===") for chapter_id in chapter_ids)
    matches = list(re.finditer(pattern, response))
    if len(matches) != len(chapter_ids):
        preview = response[:500].replace("\n", "\\n")
        raise RuntimeError(
            f"Expected {len(chapter_ids)} chapter markers, found {len(matches)}; response began: {preview!r}"
        )
    files = {}
    for index, match in enumerate(matches):
        expected = f"=== {chapter_ids[index]}.tsx ==="
        if match.group(0) != expected:
            raise RuntimeError("Chapter markers were returned out of order")
        end = matches[index + 1].start() if index + 1 < len(matches) else len(response)
        files[f"{chapter_ids[index]}.tsx"] = response[match.end():end].strip()
    return files


def parse_response(response: str, chapter_ids: list[str]) -> dict[str, str]:
    files = _extract_response(response, chapter_ids)
    for chapter_id in chapter_ids:
        name = f"{chapter_id}.tsx"
        files[name] = _normalize_chapter_source(files[name])
        _validate_chapter_source(files[name], chapter_id)
    return files


PRESENTATION_LITERAL_LIMITS = {
    "EquationCard": {"equation": 120, "caption": 72, "description": 72, "title": 72},
    "SceneTitle": {"text": 64, "title": 64, "subtitle": 72},
    "TextCard": {"title": 42, "body": 110},
    "StatReadout": {"value": 32, "unit": 12, "label": 42},
    "ComparisonTable": {"title": 54},
}


def presentation_contract_findings(run_path: Path) -> list[dict[str, Any]]:
    """Find literal presentation values that would throw during browser initialization."""
    findings: list[dict[str, Any]] = []
    root = run_path / "motion_canvas"
    manifest = _load(root / "manifest.json") if (root / "manifest.json").exists() else {}
    chapter_root = root / _unit_directory(manifest)
    for chapter_path in sorted(chapter_root.glob("*.tsx")):
        source = chapter_path.read_text(encoding="utf-8")
        for component, limits in PRESENTATION_LITERAL_LIMITS.items():
            for match in re.finditer(rf"<{component}\b[\s\S]*?/>", source):
                block = match.group(0)
                for prop, limit in limits.items():
                    literal = re.search(
                        rf"\b{prop}\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|\{{\s*\"([^\"]*)\"\s*\}}|\{{\s*'([^']*)'\s*\}})",
                        block,
                    )
                    if not literal:
                        continue
                    value = next(group for group in literal.groups() if group is not None)
                    if len(value) <= limit:
                        continue
                    line = source.count("\n", 0, match.start() + literal.start()) + 1
                    findings.append(
                        {
                            "chapter_id": chapter_path.stem,
                            "line": line,
                            "component": component,
                            "property": prop,
                            "limit": limit,
                            "length": len(value),
                            "value": value,
                            "error": f"{component} {prop} exceeds {limit} characters ({len(value)} supplied)",
                        }
                    )
    return findings


def _repair_chapter_with_model(
    run_path: Path,
    chapter_id: str,
    errors: list[str],
    *,
    model_call: Callable[..., str | None] | None = None,
) -> dict[str, Any]:
    root = run_path / "motion_canvas"
    manifest = _load(root / "manifest.json") if (root / "manifest.json").exists() else {}
    chapter_path = _unit_path(root, chapter_id, ".tsx", manifest)
    if not chapter_path.exists():
        raise RuntimeError(f"Cannot repair missing chapter source: {chapter_id}")
    if model_call is None:
        from mav_models import call_model_text
        model_call = call_model_text
    prompt_root = Path(__file__).with_name("prompts")
    system = (prompt_root / "repair.system.txt").read_text(encoding="utf-8")
    approved = (prompt_root / "approved-api.md").read_text(encoding="utf-8")
    source = chapter_path.read_text(encoding="utf-8")
    user = (
        f"Return exactly this marker and a complete corrected file:\n=== {chapter_id}.tsx ===\n\n"
        "MEASURED COMPILE/PREVIEW ERRORS\n"
        + "\n".join(f"- {error}" for error in errors)
        + "\n\nRepair only the measured errors. Preserve narration timing, cue usage, educational meaning, and the visual design.\n\n"
        f"APPROVED API\n{approved}\n\nCURRENT SOURCE\n{source}"
    )
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            response = model_call(task="motion_canvas_repair", system=system, user=user, max_tokens=MOTION_CANVAS_MAX_TOKENS)
            if not response:
                raise RuntimeError("Model returned no repair response")
            repaired = parse_response(response, [chapter_id])[f"{chapter_id}.tsx"]
            unit = next((item for item in _timeline_units(manifest) if item["scene_id"] == chapter_id), None)
            if unit is not None:
                repaired = _enforce_manifest_duration(repaired, unit)
            _validate_cue_references(root, repaired, chapter_id)
            _write(chapter_path, repaired)
            response_path = root / "responses" / f"qa-repair-{chapter_id}-{time.time_ns()}.txt"
            _write(response_path, response)
            return {"chapter_id": chapter_id, "errors": errors, "response": str(response_path)}
        except Exception as exc:
            last_error = exc
            rate_limited = "429" in str(exc) or "rate limit" in str(exc).lower() or "max organization concurrency" in str(exc).lower()
            if not rate_limited or attempt == 3:
                break
            time.sleep(2 ** attempt)
    raise RuntimeError(f"{chapter_id} QA repair failed: {last_error}")


def assemble(run_path: Path, manifest: dict[str, Any]) -> Path:
    root = run_path / "motion_canvas"
    _assert_immutable_timeline(run_path, manifest)
    _apply_frame_aligned_timing(manifest)
    units = _timeline_units(manifest)
    directory = _unit_directory(manifest)
    missing = [item["scene_id"] for item in units if not _unit_path(root, item["scene_id"], ".tsx", manifest).exists()]
    if missing:
        raise RuntimeError(f"Cannot assemble; missing chapters: {missing}")
    imports, names = [], []
    for chapter in units:
        scene_id = chapter["scene_id"]; variable = scene_id.replace("_", "")
        chapter_path = _unit_path(root, scene_id, ".tsx", manifest)
        source = chapter_path.read_text(encoding="utf-8")
        aligned = _enforce_manifest_duration(source, chapter)
        if aligned != source:
            _write(chapter_path, aligned)
        imports.append(f"import {variable} from './{directory}/{scene_id}?scene';"); names.append(variable)
    path = root / "scenes.ts"
    _write(path, "\n".join(imports) + f"\n\nexport const scenes = [{', '.join(names)}];")
    _write_json(root / "manifest.json", manifest)
    return path


def generate(
    run_path: Path,
    manifest: dict[str, Any],
    *,
    allow_model_call: bool,
    force: bool = False,
    workers: int = DEFAULT_WORKERS,
    model_call: Callable[..., str | None] | None = None,
    target_chapter_id: str | None = None,
    instruction: str = "",
) -> dict[str, Any]:
    if workers < 1 or workers > 3:
        raise RuntimeError("Workers must be between 1 and 3")
    root = run_path / "motion_canvas"
    _assert_immutable_timeline(run_path, manifest)
    _apply_frame_aligned_timing(manifest)
    chapter_by_id = {str(chapter["scene_id"]): chapter for chapter in _timeline_units(manifest)}
    if model_call is None:
        from mav_models import call_model_text
        model_call = call_model_text
    def call_with_backoff(*, task: str = "motion_canvas_batch", system: str, user: str, max_tokens: int) -> str:
        for attempt in range(4):
            try:
                response = model_call(task=task, system=system, user=user, max_tokens=max_tokens)
                if not response:
                    raise RuntimeError("Model returned no response")
                return response
            except Exception as exc:
                rate_limited = "429" in str(exc) or "rate limit" in str(exc).lower() or "max organization concurrency" in str(exc).lower()
                if not rate_limited or attempt == 3:
                    raise
                time.sleep(2 ** attempt)
        raise RuntimeError("Model retry loop exhausted")

    def repair_chapter(chapter_id: str, source: str, error: str) -> str:
        prompt_root = Path(__file__).with_name("prompts")
        system = (prompt_root / "repair.system.txt").read_text(encoding="utf-8")
        approved = (prompt_root / "approved-api.md").read_text(encoding="utf-8")
        user = (
            f"Return exactly this marker and a complete corrected file:\n=== {chapter_id}.tsx ===\n\n"
            f"VALIDATION ERROR\n{error}\n\nAPPROVED API\n{approved}\n\nCURRENT SOURCE\n{source}"
        )
        response = call_with_backoff(task="motion_canvas_repair", system=system, user=user, max_tokens=MOTION_CANVAS_MAX_TOKENS)
        repaired = parse_response(response, [chapter_id])[f"{chapter_id}.tsx"]
        repaired = _enforce_manifest_duration(repaired, chapter_by_id[chapter_id])
        _write(root / "responses" / f"repair-{chapter_id}.txt", response)
        return repaired

    def install_response(response: str, chapter_ids: list[str]) -> tuple[list[str], list[str]]:
        extracted = _extract_response(response, chapter_ids)
        installed, errors = [], []
        for chapter_id in chapter_ids:
            name = f"{chapter_id}.tsx"
            source = _enforce_manifest_duration(extracted[name], chapter_by_id[chapter_id])
            try:
                _validate_chapter_source(source, chapter_id)
                _validate_cue_references(root, source, chapter_id)
            except Exception as exc:
                try:
                    source = repair_chapter(chapter_id, source, str(exc))
                    _validate_cue_references(root, source, chapter_id)
                except Exception as repair_exc:
                    errors.append(f"{chapter_id}: {repair_exc}")
                    continue
            _write(_unit_path(root, chapter_id, ".tsx", manifest), source)
            installed.append(chapter_id)
        return installed, errors

    chapter_ids = {str(item["scene_id"]) for item in _timeline_units(manifest)}
    if target_chapter_id and target_chapter_id not in chapter_ids:
        raise RuntimeError(f"Unknown Motion Canvas chapter: {target_chapter_id}")
    work_batches = (
        [{"id": f"regenerate_{target_chapter_id}", "chapter_ids": [target_chapter_id], "status": "pending"}]
        if target_chapter_id
        else manifest["batches"]
    )

    def generate_batch(batch: dict[str, Any]) -> dict[str, Any]:
        response_name = f"{batch['id']}-{time.time_ns()}.txt" if target_chapter_id else f"{batch['id']}.txt"
        response_path = root / "responses" / response_name
        expected = [_unit_path(root, chapter_id, ".tsx", manifest) for chapter_id in batch["chapter_ids"]]
        if not force and all(path.exists() for path in expected):
            return {"id": batch["id"], "status": "cached", "chapter_ids": batch["chapter_ids"]}
        if not allow_model_call:
            raise RuntimeError(f"Cache miss for {batch['id']}; model call is not authorized")
        missing_ids = [chapter_id for chapter_id, path in zip(batch["chapter_ids"], expected) if force or not path.exists()]
        installed: list[str] = []
        if response_path.exists() and not force:
            try:
                cached_installed, cached_errors = install_response(response_path.read_text(encoding="utf-8"), missing_ids)
                installed.extend(cached_installed)
                missing_ids = [chapter_id for chapter_id in missing_ids if chapter_id not in installed]
                if cached_errors and not missing_ids:
                    missing_ids = []
            except Exception:
                pass
        if missing_ids:
            request_batch = {**batch, "chapter_ids": missing_ids}
            system, user = _batch_prompt(root, manifest, request_batch, instruction=instruction)
            response = call_with_backoff(system=system, user=user, max_tokens=MOTION_CANVAS_MAX_TOKENS)
            _write(response_path, response)
            new_installed, errors = install_response(response, missing_ids)
            installed.extend(new_installed)
            if errors:
                raise RuntimeError("; ".join(errors))
        still_missing = [chapter_id for chapter_id, path in zip(batch["chapter_ids"], expected) if not path.exists()]
        if still_missing:
            raise RuntimeError(f"Missing chapters after generation: {still_missing}")
        return {"id": batch["id"], "status": "generated", "chapter_ids": batch["chapter_ids"], "installed": installed}
    results, failures = [], []
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="motion-batch") as executor:
        future_map = {executor.submit(generate_batch, batch): batch for batch in work_batches}
        for future in as_completed(future_map):
            batch = future_map[future]
            try: results.append(future.result())
            except Exception as exc: failures.append({"id": batch["id"], "status": "failed", "error": str(exc)})
    by_id = {item["id"]: item for item in results + failures}
    chapter_status = dict(manifest.get("chapter_status") or {})
    if target_chapter_id:
        target_result = by_id.get(f"regenerate_{target_chapter_id}", {"status": "unknown"})
        chapter_status[target_chapter_id] = target_result.get("status", "unknown")
        for batch in manifest["batches"]:
            if target_chapter_id in batch.get("chapter_ids", []):
                batch["last_regenerated_chapter"] = target_chapter_id
                batch["last_regenerated_at"] = _now()
    else:
        for batch in manifest["batches"]:
            batch.update(by_id.get(batch["id"], {"status": "unknown"}))
            for chapter_id in batch.get("chapter_ids", []):
                chapter_status[chapter_id] = batch.get("status", "unknown")
    manifest["chapter_status"] = chapter_status
    manifest["updated_at"] = _now(); _write_json(root / "manifest.json", manifest)
    assembled = None
    compile_repairs: list[dict[str, Any]] = []
    if not failures:
        assembled = str(assemble(run_path, manifest))
        # Compile the complete generated lesson while the selected coding model
        # is still available. TypeScript reports are grouped by chapter so all
        # currently visible failures are repaired together, then rechecked.
        for attempt in range(4):
            _sync_runtime(run_path)
            compile_report = _npm("typecheck", run_path, 180)
            if compile_report["returncode"] == 0:
                break
            output = f"{compile_report.get('stdout', '')}\n{compile_report.get('stderr', '')}"
            grouped: dict[str, list[str]] = {}
            for line in output.splitlines():
                match = re.search(r"src/generated/(?:chapters|shots|reels)/((?:chapter|shot|reel)_\d+)\.tsx", line)
                if match:
                    grouped.setdefault(match.group(1), []).append(line)
            compile_repairs.append({"attempt": attempt + 1, "errors": grouped or {"runtime": output[-12000:]}})
            if attempt == 3:
                failures.append({"id": "typescript_compile", "status": "failed", "error": "TypeScript still failed after three aggregate repair passes\n" + output[-12000:]})
                break
            if not grouped or not allow_model_call:
                failures.append({"id": "typescript_compile", "status": "failed", "error": output[-12000:]})
                break
            repair_errors = []
            for chapter_id, errors in grouped.items():
                chapter_path = _unit_path(root, chapter_id, ".tsx", manifest)
                try:
                    repaired = repair_chapter(chapter_id, chapter_path.read_text(encoding="utf-8"), "\n".join(errors))
                    _validate_cue_references(root, repaired, chapter_id)
                    _write(chapter_path, repaired)
                except Exception as exc:
                    repair_errors.append(f"{chapter_id}: {exc}")
            if repair_errors:
                failures.append({"id": "typescript_repair", "status": "failed", "error": "; ".join(repair_errors)})
                break
        if not failures:
            _sync_runtime(run_path)
    report = {"status": "generated" if not failures else "partial", "workers": workers,
              "results": sorted(results, key=lambda item: item["id"]), "failures": sorted(failures, key=lambda item: item["id"]), "assembled_scenes": assembled,
              "compile_repairs": compile_repairs, "target_chapter_id": target_chapter_id}
    _write_json(root / "generation-report.json", report)
    return report


def _sync_runtime(run_path: Path) -> None:
    root, generated = run_path / "motion_canvas", RUNTIME_ROOT / "src" / "generated"
    manifest = _load(root / "manifest.json")
    directory = _unit_directory(manifest)
    source_chapters = root / directory
    target_chapters = generated / directory
    for inactive_directory in {"chapters", "shots", "reels"} - {directory}:
        inactive_root = generated / inactive_directory
        if inactive_root.exists():
            for stale in inactive_root.iterdir():
                if stale.is_file() and (stale.name.endswith(".tsx") or stale.name.endswith(".cues.ts")):
                    stale.unlink(missing_ok=True)
    target_chapters.mkdir(parents=True, exist_ok=True)
    source_files = {
        path.name: path
        for path in source_chapters.iterdir()
        if path.is_file() and (path.name.endswith(".tsx") or path.name.endswith(".cues.ts"))
    }
    for target in target_chapters.iterdir():
        if target.is_file() and (target.name.endswith(".tsx") or target.name.endswith(".cues.ts")) and target.name not in source_files:
            target.unlink(missing_ok=True)
    for name, source in source_files.items():
        target = target_chapters / name
        temporary = target_chapters / f".{name}.{time.time_ns()}.tmp"
        shutil.copy2(source, temporary)
        temporary.replace(target)
    generated.mkdir(parents=True, exist_ok=True)
    scenes_target = generated / "scenes.ts"
    scenes_temporary = generated / f".scenes.{time.time_ns()}.tmp"
    shutil.copy2(root / "scenes.ts", scenes_temporary)
    scenes_temporary.replace(scenes_target)
    (RUNTIME_ROOT / "public").mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / "voiceover.mp3", RUNTIME_ROOT / "public" / "voiceover.mp3")


def prepare_runtime_preview(run_path: Path) -> None:
    """Install one accepted run into the fixed local editor without rendering video."""
    manifest = _load(run_path / "motion_canvas" / "manifest.json")
    assemble(run_path, manifest)
    _sync_runtime(run_path)


def _modern_node_bin() -> Path | None:
    candidates: list[tuple[tuple[int, ...], Path]] = []
    nvm_root = Path.home() / ".nvm" / "versions" / "node"
    if nvm_root.exists():
        for node in nvm_root.glob("v*/bin/node"):
            match = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", node.parents[1].name)
            if match:
                version = tuple(int(part) for part in match.groups())
                if version >= (18, 0, 0): candidates.append((version, node.parent))
    return max(candidates, default=((), None), key=lambda item: item[0])[1]


def _npm(script: str, run_path: Path, timeout: int) -> dict[str, Any]:
    env = os.environ.copy(); env["MAV_MOTION_RUN_ROOT"] = str((run_path / "motion_canvas").resolve())
    node_bin = _modern_node_bin()
    if node_bin: env["PATH"] = str(node_bin) + os.pathsep + env.get("PATH", "")
    result = subprocess.run(["npm", "run", script], cwd=RUNTIME_ROOT, env=env, capture_output=True, text=True, timeout=timeout)
    return {"command": f"npm run {script}", "returncode": result.returncode, "stdout": result.stdout[-12000:], "stderr": result.stderr[-12000:]}


def _npm_live(script: str, run_path: Path, timeout: int) -> dict[str, Any]:
    """Run a long renderer with output inherited by Studio's live log pipe."""
    env = os.environ.copy()
    env["MAV_MOTION_RUN_ROOT"] = str((run_path / "motion_canvas").resolve())
    node_bin = _modern_node_bin()
    if node_bin:
        env["PATH"] = str(node_bin) + os.pathsep + env.get("PATH", "")
    result = subprocess.run(
        ["npm", "run", script],
        cwd=RUNTIME_ROOT,
        env=env,
        timeout=timeout,
    )
    return {"command": f"npm run {script}", "returncode": result.returncode, "stdout": "", "stderr": ""}


def validate_and_assemble(
    run_path: Path,
    manifest: dict[str, Any],
    *,
    allow_model_repair: bool = False,
    max_model_repairs: int = 2,
    model_call: Callable[..., str | None] | None = None,
) -> dict[str, Any]:
    runtime_repairs: list[dict[str, Any]] = []
    chapter_backups: dict[str, str] = {}
    compile_report: dict[str, Any] = {"returncode": 1, "stdout": "", "stderr": ""}
    preview_report: dict[str, Any] = {"status": "skipped"}

    def restore_repaired_chapters() -> None:
        if not chapter_backups:
            return
        root = run_path / "motion_canvas"
        for chapter_id, source in chapter_backups.items():
            _write(_unit_path(root, chapter_id, ".tsx", manifest), source)
        assemble(run_path, manifest)
        _sync_runtime(run_path)

    for repair_attempt in range(max_model_repairs + 1):
        findings = presentation_contract_findings(run_path)
        if findings:
            grouped: dict[str, list[str]] = {}
            for finding in findings:
                grouped.setdefault(str(finding["chapter_id"]), []).append(
                    f"line {finding['line']}: {finding['error']}; value={finding['value']!r}"
                )
            if allow_model_repair and repair_attempt < max_model_repairs:
                try:
                    for chapter_id, errors in grouped.items():
                        chapter_path = _unit_path(run_path / "motion_canvas", chapter_id, ".tsx", manifest)
                        chapter_backups.setdefault(chapter_id, chapter_path.read_text(encoding="utf-8"))
                        runtime_repairs.append(
                            {
                                "attempt": repair_attempt + 1,
                                **_repair_chapter_with_model(run_path, chapter_id, errors, model_call=model_call),
                            }
                        )
                except Exception as exc:
                    restore_repaired_chapters()
                    report = {
                        "status": "failed",
                        "compile": compile_report,
                        "preview": preview_report,
                        "presentation_findings": findings,
                        "runtime_repairs": runtime_repairs,
                        "repair_error": str(exc),
                    }
                    _write_json(run_path / "motion_canvas" / "robot-report.json", report)
                    raise
                continue
            restore_repaired_chapters()
            report = {
                "status": "failed",
                "compile": compile_report,
                "preview": preview_report,
                "presentation_findings": findings,
                "runtime_repairs": runtime_repairs,
            }
            _write_json(run_path / "motion_canvas" / "robot-report.json", report)
            raise RuntimeError(
                "Motion Canvas presentation contract validation failed: "
                + "; ".join(f"{item['chapter_id']} line {item['line']}: {item['error']}" for item in findings)
            )

        assemble(run_path, manifest)
        _sync_runtime(run_path)
        compile_report = _npm("check", run_path, 180)
        preview_report = {"status": "skipped"}
        if compile_report["returncode"] == 0:
            command = _npm("preview-frames", run_path, 300)
            validation_path = run_path / "motion_canvas" / "validation.json"
            preview_report = {"command": command, "validation": _load(validation_path) if validation_path.exists() else {}}
        passed = compile_report["returncode"] == 0 and preview_report.get("command", {}).get("returncode") == 0 and preview_report.get("validation", {}).get("status") == "passed"
        report = {
            "status": "passed" if passed else "failed",
            "compile": compile_report,
            "preview": preview_report,
            "presentation_findings": [],
            "runtime_repairs": runtime_repairs,
        }
        _write_json(run_path / "motion_canvas" / "robot-report.json", report)
        if passed:
            return report
        restore_repaired_chapters()
        break
    raise RuntimeError("Motion Canvas compile/preview validation failed")


def render_video(run_path: Path) -> dict[str, Any]:
    manifest = _load(run_path / "motion_canvas" / "manifest.json")
    print("[render] Stage 1/3: validating and assembling Motion Canvas chapters", flush=True)
    validate_and_assemble(run_path, manifest)
    print("[render] Stage 2/3: rendering animation frames and encoding video", flush=True)
    report = _npm_live("render-video", run_path, 3600)
    if report["returncode"] != 0: raise RuntimeError(report["stderr"] or report["stdout"])
    print("[render] Stage 3/3: Motion Canvas video render completed", flush=True)
    return {"status": "rendered", "output": str(run_path / "motion_canvas" / "final.mp4"), "render": report}
