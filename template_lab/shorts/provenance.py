from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""): digest.update(chunk)
    return digest.hexdigest()


def build_provenance(parent: Path, parent_run_id: str, segments: list[dict[str, Any]], lines: list[dict[str, Any]]) -> dict[str, Any]:
    timeline = parent / "motion_canvas" / "timeline.json"
    voice = parent / "voiceover.wav"
    reels = []
    for segment in segments:
        reel_id = str(segment["reel_id"])
        source = next((parent / "motion_canvas" / directory / f"{reel_id}.tsx" for directory in ("reels", "shots", "chapters") if (parent / "motion_canvas" / directory / f"{reel_id}.tsx").is_file()), None)
        if source is None: raise FileNotFoundError(f"Missing source visual unit: {reel_id}")
        reels.append({"reel_id": reel_id, "source_sha256": sha256(source), "beat_ids": segment.get("beat_ids", [])})
    reused = []
    for line in lines:
        if line.get("audio_source") != "reuse": continue
        paragraph = str(line["source_paragraph_id"])
        source = parent / "audio_chunks" / paragraph / "audio.wav"
        reused.append({"paragraph_id": paragraph, "audio_sha256": sha256(source),
                       "source_start_seconds": line.get("source_start_seconds"), "source_end_seconds": line.get("source_end_seconds")})
    timeline_source = timeline if timeline.is_file() else parent / "motion_canvas" / "manifest.json"
    return {"version": "1.0", "parent_run_id": parent_run_id, "parent_timeline_id": sha256(timeline_source),
            "parent_voiceover_sha256": sha256(voice), "source_reels": reels, "reused_audio": reused,
            "generated_audio_lines": [str(x["line_id"]) for x in lines if x.get("audio_source") == "generate"],
            "created_at": datetime.now(timezone.utc).isoformat()}


def stale_reasons(parent: Path, data: dict[str, Any]) -> list[str]:
    timeline = parent / "motion_canvas/timeline.json"
    checks = [(timeline if timeline.is_file() else parent / "motion_canvas/manifest.json", data.get("parent_timeline_id")),
              (parent / "voiceover.wav", data.get("parent_voiceover_sha256"))]
    for record in data.get("source_reels", []):
        unit = next((parent / "motion_canvas" / directory / f"{record['reel_id']}.tsx" for directory in ("reels", "shots", "chapters") if (parent / "motion_canvas" / directory / f"{record['reel_id']}.tsx").is_file()), parent / "motion_canvas" / "reels" / f"{record['reel_id']}.tsx")
        checks.append((unit, record.get("source_sha256")))
    checks += [(parent / "audio_chunks" / r["paragraph_id"] / "audio.wav", r.get("audio_sha256")) for r in data.get("reused_audio", [])]
    return [str(path) for path, expected in checks if not path.is_file() or sha256(path) != expected]
