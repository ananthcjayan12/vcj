from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from mav_build_preview_v3 import build_preview_v3
from mav_schema import LAB_ROOT, read_json, run_dir, write_json


_AUDIO_TAG_RE = re.compile(r"\n\s*<audio\b[^>]*\bid=[\"']mav-audio[\"'][^>]*>\s*</audio>", re.IGNORECASE)
HYPERFRAMES_BIN = LAB_ROOT / "node_modules" / ".bin" / "hyperframes"


def _require_binary(name: str, *, env: dict[str, str] | None = None) -> None:
    if not shutil.which(name, path=(env or os.environ).get("PATH")):
        raise RuntimeError(f"{name} is required to render MP4 output")


def _node_version_key(version_dir: Path) -> tuple[int, int, int]:
    match = re.search(r"v?(\d+)(?:\.(\d+))?(?:\.(\d+))?", version_dir.name)
    if not match:
        return (0, 0, 0)
    return tuple(int(part or 0) for part in match.groups())


def _node_major(node_path: Path) -> int:
    try:
        result = subprocess.run(
            [str(node_path), "--version"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return 0
    match = re.search(r"v(\d+)", result.stdout.strip())
    return int(match.group(1)) if match else 0


def _node_version(node_path: Path) -> tuple[int, int, int]:
    try:
        result = subprocess.run(
            [str(node_path), "--version"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return (0, 0, 0)
    match = re.search(r"v(\d+)(?:\.(\d+))?(?:\.(\d+))?", result.stdout.strip())
    return tuple(int(part or 0) for part in match.groups()) if match else (0, 0, 0)


def _candidate_node_bin_dirs() -> list[Path]:
    candidates: list[Path] = []
    for env_name in ("MAV_NODE_BIN_DIR", "NODE_BIN_DIR"):
        value = os.getenv(env_name)
        if value:
            candidates.append(Path(value).expanduser())
    node_home = os.getenv("MAV_NODE_HOME") or os.getenv("NODE_HOME")
    if node_home:
        candidates.append(Path(node_home).expanduser() / "bin")

    nvm_root = Path(os.getenv("NVM_DIR", str(Path.home() / ".nvm"))).expanduser()
    node_versions = nvm_root / "versions" / "node"
    if node_versions.exists():
        for version_dir in sorted(node_versions.glob("v*"), key=_node_version_key, reverse=True):
            candidates.append(version_dir / "bin")

    current_node = shutil.which("node")
    if current_node:
        candidates.append(Path(current_node).resolve().parent)

    seen: set[str] = set()
    unique = []
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def _resolve_node_bin_dir(min_version: tuple[int, int, int] = (22, 12, 0)) -> Path | None:
    for bin_dir in _candidate_node_bin_dirs():
        node_path = bin_dir / "node"
        npx_path = bin_dir / "npx"
        if node_path.exists() and npx_path.exists() and _node_version(node_path) >= min_version:
            return bin_dir
    return None


def _probe_media(path: Path) -> dict[str, Any]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=index,codec_type,codec_name,width,height,r_frame_rate",
            "-show_entries",
            "format=duration,size",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    stream_types = {item.get("codec_type") for item in payload.get("streams", [])}
    if "video" not in stream_types or "audio" not in stream_types:
        raise RuntimeError(f"Rendered MP4 must contain video and audio streams: {path}")
    return payload


def _write_hyperframes_composition(composition_path: Path) -> Path:
    """Create a render-only composition that lets FFmpeg own audio muxing."""
    html = composition_path.read_text(encoding="utf-8")
    render_html, replacements = _AUDIO_TAG_RE.subn("", html, count=1)
    if replacements != 1:
        raise RuntimeError(f"Expected exactly one mav-audio tag in {composition_path}")

    render_path = composition_path.with_name(f"{composition_path.stem}.hyperframes.html")
    render_path.write_text(render_html, encoding="utf-8")
    return render_path


def _hyperframes_env() -> dict[str, str]:
    env = os.environ.copy()
    node_bin_dir = _resolve_node_bin_dir()
    if node_bin_dir:
        env["PATH"] = f"{node_bin_dir}{os.pathsep}{env.get('PATH', '')}"
        env["MAV_NODE_BIN_DIR"] = str(node_bin_dir)
    env["PRODUCER_ENABLE_STREAMING_ENCODE"] = "false"
    env["HF_STATIC_DEDUP"] = "false"
    return env


def _require_hyperframes_node(env: dict[str, str]) -> None:
    node = shutil.which("node", path=env.get("PATH"))
    if not node:
        raise RuntimeError("Node.js is required to render MP4 output")
    if not HYPERFRAMES_BIN.exists():
        raise RuntimeError(f"Missing pinned HyperFrames renderer. Run npm install in {LAB_ROOT}.")
    version = _node_version(Path(node))
    if version < (22, 12, 0):
        raise RuntimeError(
            f"The pinned HyperFrames renderer requires Node 22.12 or newer, but render found {node} "
            f"(version {'.'.join(map(str, version))}). Set MAV_NODE_BIN_DIR to a Node 22.12+ bin directory."
        )


def _hyperframes_command(
    *,
    composition_path: Path,
    output_path: Path,
    fps: int,
    quality: str,
    workers: int,
) -> list[str]:
    return [
        str(HYPERFRAMES_BIN),
        "render",
        "-c",
        composition_path.relative_to(LAB_ROOT).as_posix(),
        "-o",
        str(output_path),
        "--format",
        "mp4",
        "--fps",
        str(fps),
        "--resolution",
        "1080p",
        "--quality",
        quality,
        "--workers",
        str(workers),
        "--browser-timeout",
        "180",
        "--protocol-timeout",
        "600000",
        "--player-ready-timeout",
        "120000",
        "--low-memory-mode",
        str(LAB_ROOT),
    ]


def _render_hyperframes_visual(
    *,
    composition_path: Path,
    visual_path: Path,
    fps: int,
    quality: str,
    workers: int,
    strip_audio: bool,
    env: dict[str, str],
) -> None:
    render_composition_path = _write_hyperframes_composition(composition_path) if strip_audio else composition_path
    try:
        subprocess.run(
            _hyperframes_command(
                composition_path=render_composition_path,
                output_path=visual_path,
                fps=fps,
                quality=quality,
                workers=workers,
            ),
            check=True,
            cwd=LAB_ROOT.parent,
            env=env,
        )
    finally:
        if strip_audio:
            render_composition_path.unlink(missing_ok=True)


def render_mp4(
    run_id: str,
    *,
    output: Path | None = None,
    fps: int = 30,
    quality: str = "standard",
    workers: int = 1,
    keep_visual: bool = False,
) -> Path:
    hyperframes_env = _hyperframes_env()
    _require_hyperframes_node(hyperframes_env)
    _require_binary("ffmpeg")
    _require_binary("ffprobe")

    run_path = run_dir(run_id)
    voiceover_path = run_path / "voiceover.mp3"
    if not voiceover_path.exists():
        raise RuntimeError(f"Missing voiceover audio: {voiceover_path}")
    scene_plan_path = run_path / "scene_plan_v3.json"
    if not scene_plan_path.exists():
        raise RuntimeError(f"Missing Physics V3 scene plan: {scene_plan_path}")
    build_preview_v3(run_path)
    composition_version = "v3"

    composition_path = run_path / "compositions" / f"master_{composition_version}.html"
    if not composition_path.exists():
        raise RuntimeError(f"Missing preview composition: {composition_path}")

    renders_dir = run_path / "renders"
    renders_dir.mkdir(parents=True, exist_ok=True)
    output_path = (output or (renders_dir / f"master_{composition_version}.mp4")).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    visual_path = renders_dir / f"master_{composition_version}.visual.mp4"
    if visual_path.exists():
        visual_path.unlink()

    _render_hyperframes_visual(
        composition_path=composition_path,
        visual_path=visual_path,
        fps=fps,
        quality=quality,
        workers=workers,
        strip_audio=True,
        env=hyperframes_env,
    )

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(visual_path),
            "-i",
            str(voiceover_path),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(output_path),
        ],
        check=True,
    )

    probe = _probe_media(output_path)
    report = {
        "run_id": run_id,
        "composition_version": composition_version,
        "composition": str(composition_path),
        "output": str(output_path),
        "visual_renderer": "hyperframes",
        "visual_render_mode": "single_composition",
        "audio_source": str(voiceover_path),
        "fps": fps,
        "quality": quality,
        "workers": workers,
        "ffprobe": probe,
    }
    write_json(run_path / "render_report.json", report)

    summary_path = run_path / "generation_summary.json"
    if summary_path.exists():
        summary = read_json(summary_path)
        summary["mp4"] = str(output_path)
        write_json(summary_path, summary)

    if not keep_visual and visual_path.exists():
        visual_path.unlink()
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a Template Lab MAV preview to an MP4 with voiceover audio.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--fps", type=int, default=30, choices=(24, 25, 30, 50, 60))
    parser.add_argument("--quality", choices=("draft", "standard", "high"), default="standard")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--keep-visual", action="store_true", help="Keep the intermediate video-only MP4.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        output = render_mp4(
            args.run_id,
            output=args.output,
            fps=args.fps,
            quality=args.quality,
            workers=args.workers,
            keep_visual=args.keep_visual,
        )
    except Exception as exc:
        print(f"MAV render failed: {exc}")
        return 1
    print(f"MAV MP4 rendered: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
