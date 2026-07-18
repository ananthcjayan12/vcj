from __future__ import annotations

from pathlib import Path
from typing import Any

from .constants import MAX_CAPTION_WORDS


def groups(timestamps: dict[str, Any]) -> list[dict[str, Any]]:
    source = timestamps.get("words") or []; result = []
    for offset in range(0, len(source), MAX_CAPTION_WORDS):
        chunk = source[offset:offset + MAX_CAPTION_WORDS]
        if chunk: result.append({"start": float(chunk[0]["start"]), "end": max(float(chunk[-1]["end"]), float(chunk[0]["start"])+.65),
                                 "words": [{"text": str(w.get("word", "")), "emphasis": len(str(w.get("word", ""))) >= 7} for w in chunk]})
    return result


def _clock(seconds: float, srt: bool = True) -> str:
    millis = round(seconds * 1000); h, millis = divmod(millis, 3600000); m, millis = divmod(millis, 60000); s, ms = divmod(millis, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{',' if srt else '.'}{ms:03d}"


def write_captions(root: Path, timestamps: dict[str, Any]) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True); items = groups(timestamps); payload = {"version": "1.0", "language": "en", "captions": items}
    import json
    (root / "captions.json").write_text(json.dumps(payload, indent=2)+"\n", encoding="utf-8")
    (root / "captions.srt").write_text("\n".join(f"{i}\n{_clock(x['start'])} --> {_clock(x['end'])}\n{' '.join(w['text'] for w in x['words'])}\n" for i,x in enumerate(items,1)), encoding="utf-8")
    header = "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, Alignment, MarginL, MarginR, MarginV\nStyle: Default,Arial,52,&H00FFFFFF,2,70,110,220\n[Events]\nFormat: Layer, Start, End, Style, Text\n"
    body = "".join(f"Dialogue: 0,{_clock(x['start'],False)},{_clock(x['end'],False)},Default,{' '.join(w['text'] for w in x['words'])}\n" for x in items)
    (root / "captions.ass").write_text(header+body, encoding="utf-8")
    return payload
