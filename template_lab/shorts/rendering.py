from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


def _portrait_project_meta(width: int = 1080, height: int = 1920, fps: int = 30) -> dict[str, Any]:
    return {
        "version": 0,
        "shared": {
            "background": "#07111f",
            "range": [0, None],
            "size": {"x": width, "y": height},
            "audioOffset": 0,
        },
        "preview": {"fps": fps, "resolutionScale": 1},
        "rendering": {
            "fps": fps,
            "resolutionScale": 1,
            "colorSpace": "srgb",
            "exporter": {
                "name": "@motion-canvas/core/image-sequence",
                "options": {"fileType": "image/png", "quality": 100, "groupByScene": False},
            },
        },
    }


def install_short_runtime(short_root: Path) -> dict[str, Any]:
    """Install one portrait Short into the shared Motion Canvas runtime for live preview or render."""
    runtime = Path(__file__).resolve().parents[2] / "motion_canvas_runtime"
    motion = short_root / "motion_canvas"
    manifest = json.loads((motion / "manifest.json").read_text(encoding="utf-8"))
    profile = manifest.get("profile") or {}
    width = int(profile.get("width") or 1080)
    height = int(profile.get("height") or 1920)
    fps = int(profile.get("fps") or 30)
    generated = runtime / "src" / "generated"
    generated.mkdir(parents=True, exist_ok=True)
    short_id = str(manifest["short_id"])
    for stale in generated.glob("short_*.tsx"):
        stale.unlink()
    for stale in generated.glob("short_*.cues.ts"):
        stale.unlink()
    for stale in generated.glob("short_*.meta"):
        stale.unlink()
    shutil.copy2(motion / f"{short_id}.tsx", generated / f"{short_id}.tsx")
    shutil.copy2(motion / f"{short_id}.cues.ts", generated / f"{short_id}.cues.ts")
    (generated / "scenes.ts").write_text(
        f"import shortScene from './{short_id}?scene';\nexport const scenes = [shortScene];\n",
        encoding="utf-8",
    )
    # Force the Motion Canvas editor/project canvas to portrait. Without this the
    # shared runtime keeps the lesson default 1920×1080 and Shorts look cropped/broken.
    meta = _portrait_project_meta(width=width, height=height, fps=fps)
    (runtime / "src" / "project.meta").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    public = runtime / "public"
    public.mkdir(exist_ok=True)
    voiceover = short_root / "audio" / "voiceover.mp3"
    if voiceover.is_file():
        shutil.copy2(voiceover, public / "voiceover.mp3")
    return {
        "runtime": runtime,
        "manifest": manifest,
        "short_id": short_id,
        "motion": motion,
        "profile": {"id": profile.get("id") or "short_portrait", "width": width, "height": height, "fps": fps},
    }


def render(short_root: Path, *, preview: bool = False) -> int:
    installed = install_short_runtime(short_root)
    runtime = installed["runtime"]
    motion = installed["motion"]
    manifest = installed["manifest"]
    env = os.environ.copy()
    env["MAV_MOTION_RUN_ROOT"] = str(motion.resolve())
    command = ["node", str(runtime / "scripts/render.mjs"), "--preview" if preview else "--video"]
    completed = subprocess.run(command, cwd=runtime, env=env)
    if completed.returncode == 0 and not preview:
        output = motion / "final.mp4"
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(output)],
            capture_output=True,
            text=True,
        )
        data = json.loads(probe.stdout) if probe.returncode == 0 else {}
        streams = data.get("streams") or []
        video = next((x for x in streams if x.get("codec_type") == "video"), {})
        audio = next((x for x in streams if x.get("codec_type") == "audio"), {})
        expected = float(manifest["duration"])
        actual = float((data.get("format") or {}).get("duration") or 0)
        passed = bool(
            video
            and audio
            and video.get("width") == 1080
            and video.get("height") == 1920
            and abs(actual - expected) <= 1 / 30 + 0.08
        )
        report = {
            "status": "passed" if passed else "failed",
            "output": str(output),
            "expected_duration": expected,
            "actual_duration": actual,
            "video_codec": video.get("codec_name"),
            "audio_codec": audio.get("codec_name"),
            "width": video.get("width"),
            "height": video.get("height"),
        }
        (motion / "render-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        if not passed:
            return 1
    return completed.returncode
