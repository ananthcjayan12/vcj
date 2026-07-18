from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .constants import PORTRAIT_HEIGHT, PORTRAIT_WIDTH, SHORT_FPS


def write_manifest(root: Path, parent_run_id: str, short_id: str, duration: float) -> dict[str, Any]:
    motion = root / "motion_canvas"; motion.mkdir(parents=True, exist_ok=True)
    manifest = {"version": "1.0", "content_type": "short", "short_id": short_id, "parent_run_id": parent_run_id,
                "profile": {"id": "short_portrait", "width": PORTRAIT_WIDTH, "height": PORTRAIT_HEIGHT, "fps": SHORT_FPS, "background": "#07111f"},
                "duration": duration, "render_duration": duration, "render_frames": round(duration*SHORT_FPS),
                "audio_path": "../audio/voiceover.mp3", "scene_file": f"{short_id}.tsx", "cues_file": f"{short_id}.cues.ts",
                "source_provenance": "../source_provenance.json"}
    (motion / "manifest.json").write_text(json.dumps(manifest, indent=2)+"\n", encoding="utf-8")
    return manifest


def write_cues(root: Path, short_id: str, timestamps: dict[str, Any], duration: float) -> None:
    words = timestamps.get("words") or []
    content = "export const SHORT_DURATION = " + repr(duration) + ";\nexport const SHORT_WORDS = " + json.dumps(words, indent=2) + " as const;\n"
    (root / "motion_canvas" / f"{short_id}.cues.ts").write_text(content, encoding="utf-8")


def write_native_scene(root: Path, short_id: str, script: dict[str, Any], timestamps: dict[str, Any]) -> Path:
    """Create a deterministic native portrait fallback scene; model adapters may replace it."""
    import json
    lines = [str(line.get("text", "")) for line in script.get("lines") or []]
    duration = float(timestamps.get("audio_duration_seconds") or script.get("target_duration_seconds") or 40)
    breaks = [0.0] + [duration * i / max(1, len(lines)) for i in range(1, len(lines))] + [duration]
    source = f"""import {{makeScene2D, Rect, Txt}} from '@motion-canvas/2d';
import {{all, createRef, waitFor}} from '@motion-canvas/core';
import {{CaptionSafeArea, PortraitTextCard, ShortHook}} from '../short-presentation';
import {{SHORT_DURATION}} from './{short_id}.cues';

const LINES = {json.dumps(lines)};
const BREAKS = {json.dumps(breaks)};

export default makeScene2D(function* (view) {{
  const text = createRef<Txt>();
  const caption = createRef<Txt>();
  view.fill('#07111f');
  view.add(<Rect layout direction={{'column'}} gap={{60}} width={{940}} height={{1510}} alignItems={{'center'}} justifyContent={{'center'}}>
    <Txt ref={{text}} text={{LINES[0] || ''}} width={{940}} fontSize={{72}} fontWeight={{800}} fill={{'#ffffff'}} textAlign={{'center'}} textWrap />
    <Rect width={{180}} height={{8}} radius={{8}} fill={{'#46d9ff'}} />
  </Rect>);
  view.add(<Rect y={{745}} width={{940}} minHeight={{120}} padding={{24}} radius={{28}} fill={{'#07111fcc'}}><Txt ref={{caption}} text={{LINES[0] || ''}} width={{880}} fontSize={{52}} fill={{'#ffffff'}} textAlign={{'center'}} textWrap /></Rect>);
  for (let i = 0; i < LINES.length; i++) {{
    if (i > 0) yield* all(text().text(LINES[i], .25), caption().text(LINES[i], .25));
    yield* waitFor(Math.max(0, BREAKS[i + 1] - BREAKS[i] - (i > 0 ? .25 : 0)));
  }}
  if (!LINES.length) yield* waitFor(SHORT_DURATION);
}});
"""
    path = root / "motion_canvas" / f"{short_id}.tsx"; path.write_text(source, encoding="utf-8")
    (root / "motion_canvas" / "scenes.ts").write_text(f"import shortScene from './{short_id}?scene';\nexport const scenes = [shortScene];\n", encoding="utf-8")
    return path
