from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .constants import PORTRAIT_HEIGHT, PORTRAIT_WIDTH, SHORT_FPS


def write_manifest(root: Path, parent_run_id: str, short_id: str, duration: float) -> dict[str, Any]:
    motion = root / "motion_canvas"
    motion.mkdir(parents=True, exist_ok=True)
    manifest = {
        "version": "1.0",
        "content_type": "short",
        "short_id": short_id,
        "parent_run_id": parent_run_id,
        "profile": {
            "id": "short_portrait",
            "width": PORTRAIT_WIDTH,
            "height": PORTRAIT_HEIGHT,
            "fps": SHORT_FPS,
            "background": "#07111f",
        },
        "duration": duration,
        "render_duration": duration,
        "render_frames": round(duration * SHORT_FPS),
        "audio_path": "../audio/voiceover.mp3",
        "scene_file": f"{short_id}.tsx",
        "cues_file": f"{short_id}.cues.ts",
        "source_provenance": "../source_provenance.json",
    }
    (motion / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def write_cues(root: Path, short_id: str, timestamps: dict[str, Any], duration: float) -> None:
    words = timestamps.get("words") or []
    content = (
        "export const SHORT_DURATION = "
        + repr(duration)
        + ";\nexport const SHORT_WORDS = "
        + json.dumps(words, indent=2)
        + " as const;\n"
    )
    (root / "motion_canvas" / f"{short_id}.cues.ts").write_text(content, encoding="utf-8")


def write_native_scene(root: Path, short_id: str, script: dict[str, Any], timestamps: dict[str, Any]) -> Path:
    """Deterministic native 1080×1920 fallback. Model adapters may replace it."""
    lines = [str(line.get("text", "")).strip() for line in script.get("lines") or [] if str(line.get("text", "")).strip()]
    roles = [str(line.get("role", "line")) for line in script.get("lines") or [] if str(line.get("text", "")).strip()]
    title = str(script.get("title") or short_id)
    duration = float(timestamps.get("audio_duration_seconds") or script.get("target_duration_seconds") or 40)
    if not lines:
        lines = [title]
        roles = ["hook"]
    breaks = [0.0]
    for index in range(1, len(lines)):
        breaks.append(duration * index / len(lines))
    breaks.append(duration)
    source = f"""import {{makeScene2D, Rect, Txt, Layout}} from '@motion-canvas/2d';
import {{createSignal, linear}} from '@motion-canvas/core';
import {{
  CaptionSafeArea,
  DiagramStage,
  ProgressBar,
  ShortHook,
  ShortSubtitle,
  ShortTitle,
}} from '../short-presentation';
import {{SHORT_DURATION}} from './{short_id}.cues';

const LINES = {json.dumps(lines)};
const ROLES = {json.dumps(roles)};
const BREAKS = {json.dumps(breaks)};
const TITLE = {json.dumps(title)};

export default makeScene2D(function* (view) {{
  const progress = createSignal(0);
  const time = () => progress() * SHORT_DURATION;
  const index = () => {{
    const t = time();
    for (let i = 0; i < BREAKS.length - 1; i++) {{
      if (t < BREAKS[i + 1]) return i;
    }}
    return Math.max(0, LINES.length - 1);
  }};
  const line = () => LINES[Math.min(index(), LINES.length - 1)] || '';
  const role = () => ROLES[Math.min(index(), ROLES.length - 1)] || 'line';

  view.fill('#07111f');
  view.add(
    <>
      <Rect width={{1080}} height={{1920}} fill={{'#07111f'}} />
      <Rect y={{-820}} width={{940}} height={{170}} radius={{32}} fill={{'#0e1d31'}} stroke={{'#294563'}} lineWidth={{4}}>
        <Layout direction={{'column'}} gap={{10}} alignItems={{'center'}} y={{0}}>
          <ShortTitle title={{TITLE}} fontSize={{48}} />
          <ShortSubtitle subtitle={{() => String(role()).toUpperCase()}} fontSize={{34}} />
        </Layout>
      </Rect>

      <DiagramStage y={{-40}} width={{940}} height={{980}}>
        <Rect width={{900}} height={{920}} radius={{40}} fill={{'#0a1728'}} stroke={{'#294563'}} lineWidth={{4}} />
        <ShortHook
          text={{() => (line().length > 90 ? line().slice(0, 88) + '…' : line())}}
          fontSize={{56}}
          y={{-40}}
          width={{820}}
        />
        <Rect y={{320}} width={{220}} height={{10}} radius={{8}} fill={{'#46d9ff'}} />
      </DiagramStage>

      <CaptionSafeArea y={{780}}>
        <Rect width={{960}} minHeight={{200}} padding={{28}} radius={{32}} fill={{'#07111fee'}} stroke={{'#294563'}} lineWidth={{3}}>
          <Txt text={{line}} width={{900}} fontSize={{40}} fontWeight={{650}} fill={{'#ffffff'}} textAlign={{'center'}} textWrap />
        </Rect>
      </CaptionSafeArea>

      <ProgressBar y={{930}} width={{960}} progress={{progress}} accent={{'#46d9ff'}} />
    </>,
  );

  yield* progress(1, SHORT_DURATION, linear);
}});
"""
    path = root / "motion_canvas" / f"{short_id}.tsx"
    path.write_text(source, encoding="utf-8")
    (root / "motion_canvas" / "scenes.ts").write_text(
        f"import shortScene from './{short_id}?scene';\nexport const scenes = [shortScene];\n",
        encoding="utf-8",
    )
    return path
