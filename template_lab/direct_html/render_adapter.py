from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .constants import DIRECT_HTML_MODE, LAB_ROOT, LEGACY_MODE
from .io_utils import read_json

_AUDIO_RE = re.compile(r"\n?\s*<audio\b[^>]*\bid=[\"'](?:mav-audio|lesson-audio)[\"'][^>]*>.*?</audio>", re.IGNORECASE | re.DOTALL)
_VIEWPORT_COMPOSITION_RE = re.compile(
    r'(<[^>]+\bid=["\']viewport["\'][^>]*?)\s+data-composition-id=["\'][^"\']+["\']',
    re.IGNORECASE,
)


def animation_mode_for_run(run_path: Path) -> str:
    for relative in ("generation_summary.json", "studio_run.json", "input.json"):
        payload = read_json(run_path / relative, {}) or {}
        mode = payload.get("animation_mode") or (payload.get("settings") or {}).get("animation_mode")
        if mode in {DIRECT_HTML_MODE, LEGACY_MODE}:
            return mode
        if payload.get("mode") in {"v3_generative", "legacy-recipes"}:
            return LEGACY_MODE
    return DIRECT_HTML_MODE if (run_path / "direct_html" / "master.html").exists() else LEGACY_MODE


def composition_for_run(run_path: Path, mode: str | None = None) -> tuple[Path, str]:
    selected = mode or animation_mode_for_run(run_path)
    if selected == DIRECT_HTML_MODE:
        path = run_path / "direct_html" / "master.html"
        version = "direct_html"
    else:
        path = run_path / "compositions" / "master_v3.html"
        version = "v3"
    if not path.exists():
        raise RuntimeError(f"Missing {selected} composition: {path}")
    return path, version


def write_render_copy(composition_path: Path) -> Path:
    html = composition_path.read_text(encoding="utf-8")
    render_html, _count = _AUDIO_RE.subn("", html)
    # The canonical browser document advertises the composition on both the
    # document and viewport. HyperFrames treats nested composition hosts as
    # independent sub-compositions, so retain only the document host in its
    # temporary render copy. This leaves one timeline registration target.
    render_html = _VIEWPORT_COMPOSITION_RE.sub(r"\1", render_html)
    # HyperFrames serves a top-level composition from the Template Lab project
    # root, even when the source file lives in a run subdirectory. Rebase only
    # the temporary render copy; the canonical master keeps browser-friendly
    # paths relative to itself.
    try:
        parent = composition_path.resolve().parent.relative_to(LAB_ROOT.resolve()).as_posix()
    except ValueError:
        parent = ""
    if parent:
        render_html = render_html.replace('="./runtime/', f'="./{parent}/runtime/')
        render_html = render_html.replace('="./lesson-data.js"', f'="./{parent}/lesson-data.js"')
    render_path = composition_path.with_name(f"{composition_path.stem}.hyperframes.html")
    render_path.write_text(render_html, encoding="utf-8")
    return render_path
