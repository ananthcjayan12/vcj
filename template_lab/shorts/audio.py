from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import difflib
from pathlib import Path
from typing import Any


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _tokens(value: str) -> list[str]:
    value = re.sub(r"\[[^\]]+\]", " ", value)
    aliases = {"travelling": "traveling", "kilometre": "km", "kilometres": "km", "kilometer": "km", "kilometers": "km"}
    return [aliases.get(token, token) for token in re.findall(r"[a-z0-9]+(?:'[a-z0-9]+)?", value.lower().replace("’", "'"))]


def _best_window(target: list[str], source: list[str]) -> tuple[float, int]:
    best = (0.0, 0)
    for start in range(len(source)):
        candidate = source[start:start + len(target)]
        score = difflib.SequenceMatcher(None, target, candidate).ratio()
        if score > best[0]: best = (score, start)
    return best


def match_source_range(text: str, paragraph_id: str, timestamps: dict[str, Any], threshold: float = .9,
                       source_text: str | None = None) -> tuple[float, float, float]:
    target = _tokens(text)
    source = [w for w in timestamps.get("words", []) if str(w.get("paragraph_id")) == paragraph_id]
    transcript = [_tokens(str(word.get("word", "")))[0] for word in source if _tokens(str(word.get("word", "")))]
    if not target or not source: raise ValueError("Reusable narration clause or timestamps are empty")
    if source_text is None:
        best = _best_window(target, transcript)
        if best[0] < threshold: raise ValueError(f"Source narration match confidence {best[0]:.2f} is below {threshold:.2f}")
        selected = source[best[1]:best[1] + len(target)]
        return float(selected[0]["start"]), float(selected[-1]["end"]), best[0]

    canonical = _tokens(source_text)
    clause_score, clause_start = _best_window(target, canonical)
    if clause_score < threshold:
        raise ValueError(f"Reusable line paraphrases source narration; canonical match confidence {clause_score:.2f} is below {threshold:.2f}")
    clause_end = min(len(canonical) - 1, clause_start + len(target) - 1)
    matcher = difflib.SequenceMatcher(None, canonical, transcript, autojunk=False)
    mapping: dict[int, int] = {}
    for a, b, size in matcher.get_matching_blocks():
        for offset in range(size): mapping[a + offset] = b + offset
    mapped_start = mapping.get(clause_start)
    if mapped_start is None:
        mapped_start = next((mapping[index] for index in range(clause_start, clause_end + 1) if index in mapping), None)
    if mapped_start is None: raise ValueError("Reusable clause start could not be mapped to measured audio timestamps")
    mapped_end = mapping.get(clause_end)
    if mapped_end is not None:
        end = float(source[mapped_end]["end"])
    else:
        next_anchor = next((mapping[index] for index in range(clause_end + 1, len(canonical)) if index in mapping), None)
        end = max(float(source[mapped_start]["end"]), float(source[next_anchor]["start"]) - .03) if next_anchor is not None else float(source[-1]["end"])
    return float(source[mapped_start]["start"]), end, clause_score


def create_edl(parent: Path, short_root: Path, script: dict[str, Any], timestamps: dict[str, Any]) -> dict[str, Any]:
    manifest_path = parent / "audio_chunks" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    paragraph_offsets = {str(item.get("id")): float(item.get("absolute_start", 0)) for item in manifest.get("chapters") or []}
    narration_path = parent / "narration.json"
    narration = json.loads(narration_path.read_text(encoding="utf-8")) if narration_path.is_file() else {}
    paragraph_texts = {str(item.get("id")): str(item.get("text", "")) for item in narration.get("paragraphs") or []}
    segments = []
    for index, line in enumerate(script["lines"], 1):
        base = {"segment_id": f"segment_{index:03d}", "line_id": line["line_id"], "type": "generated" if line["audio_source"] == "generate" else "source"}
        if base["type"] == "generated": base["target_path"] = f"generated_lines/{line['line_id']}.wav"
        else:
            start, end, confidence = match_source_range(line["text"], line["source_paragraph_id"], timestamps,
                                                        source_text=paragraph_texts.get(str(line["source_paragraph_id"])))
            offset = paragraph_offsets.get(str(line["source_paragraph_id"]), 0.0); start, end = max(0.0, start-offset), max(0.0, end-offset)
            base.update({"source_path": f"../../../audio_chunks/{line['source_paragraph_id']}/audio.wav", "source_start_seconds": start,
                         "source_end_seconds": end, "fade_in_ms": 20, "fade_out_ms": 25, "match_confidence": confidence})
            line.update({"source_start_seconds": start, "source_end_seconds": end})
        segments.append(base)
    return {"version": "1.0", "sample_rate": 24000, "segments": segments}


def assemble(short_root: Path, edl: dict[str, Any]) -> tuple[Path, Path]:
    audio_root = short_root / "audio"; reuse = audio_root / "reused_segments"; reuse.mkdir(parents=True, exist_ok=True)
    parts = []
    for segment in edl["segments"]:
        if segment["type"] == "generated": source = audio_root / segment["target_path"]
        else:
            source = (audio_root / segment["source_path"]).resolve(); target = reuse / f"{segment['segment_id']}.wav"
            command = ["ffmpeg", "-y", "-ss", str(segment["source_start_seconds"]), "-to", str(segment["source_end_seconds"]), "-i", str(source),
                       "-af", f"afade=t=in:d={segment['fade_in_ms']/1000},areverse,afade=t=in:d={segment['fade_out_ms']/1000},areverse", "-ar", "24000", "-ac", "1", str(target)]
            done = subprocess.run(command, capture_output=True, text=True)
            if done.returncode: raise RuntimeError(done.stderr)
            source = target
        if not source.is_file(): raise FileNotFoundError(f"Missing generated audio line: {source}")
        parts.append(source)
    list_file = audio_root / "concat.txt"
    list_file.write_text("".join(f"file '{str(p).replace(chr(39), chr(39)+chr(92)+chr(39)+chr(39))}'\n" for p in parts), encoding="utf-8")
    wav = audio_root / "voiceover.wav"; mp3 = audio_root / "voiceover.mp3"
    for args in (["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-ar", "24000", "-ac", "1", str(wav)],
                 ["ffmpeg", "-y", "-i", str(wav), "-b:a", "192k", str(mp3)]):
        done = subprocess.run(args, capture_output=True, text=True)
        if done.returncode: raise RuntimeError(done.stderr)
    return wav, mp3


def generate_missing_lines(short_root: Path, script: dict[str, Any], *, provider: str = "gemini") -> list[str]:
    """Generate each missing line independently through the existing cached TTS implementation."""
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    if str(scripts) not in sys.path: sys.path.insert(0, str(scripts))
    from mav_audio import generate_audio  # type: ignore
    generated = []
    for line in script.get("lines") or []:
        if line.get("audio_source") != "generate": continue
        target = short_root / "audio" / "generated_lines" / f"{line['line_id']}.wav"
        if target.is_file() and target.stat().st_size > 100: continue
        cache_root = short_root / "audio" / "generated_lines" / f".{line['line_id']}-cache"
        narration = {"title": line["line_id"], "target_duration_seconds": 10, "spoken_word_count": len(str(line["text"]).split()),
                     "paragraphs": [{"id": line["line_id"], "text": line["text"], "claim_ids": line.get("claim_ids", [])}],
                     "elevenlabs_narration": line["text"]}
        generate_audio(cache_root, narration, target_duration=10, audio_provider=provider)
        shutil.copy2(cache_root / "voiceover.wav", target)
        generated.append(str(line["line_id"]))
    return generated


def align_final_audio(short_root: Path, script: dict[str, Any]) -> dict[str, Any]:
    """Run local Whisper over assembled audio; its measured words become authoritative."""
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    if str(scripts) not in sys.path: sys.path.insert(0, str(scripts))
    from mav_audio import ffprobe_duration  # type: ignore
    from mav_timing import _transcribe_audio_with_whisper  # type: ignore
    wav = short_root / "audio" / "voiceover.wav"
    transcript = _transcribe_audio_with_whisper(wav)
    duration = float(ffprobe_duration(wav) or (transcript[-1]["end"] if transcript else 0))
    expected = [(line["line_id"], token) for line in script.get("lines") or [] for token in _norm(str(line["text"])).split()]
    result = []
    for index, word in enumerate(transcript):
        line_id = expected[min(index, len(expected)-1)][0] if expected else "line_001"
        result.append({"index": index, "paragraph_id": line_id, "word": word["word"], "start": round(float(word["start"]), 3),
                       "end": round(float(word["end"]), 3), "duration": round(float(word["end"])-float(word["start"]), 3)})
    payload = {"audio_duration_seconds": round(duration, 3), "source": "short_local_whisper_word_timestamps", "words": result}
    (short_root / "audio" / "audio_word_timestamps.json").write_text(json.dumps(payload, indent=2)+"\n", encoding="utf-8")
    (short_root / "audio" / "audio_timing.json").write_text(json.dumps({"audio_duration_seconds": round(duration,3), "source": payload["source"], "word_timestamps": "audio_word_timestamps.json"}, indent=2)+"\n", encoding="utf-8")
    return payload
