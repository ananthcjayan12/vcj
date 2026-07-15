from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .constants import ASSET_MANIFEST_VERSION, LAB_ROOT, REPO_ROOT, RUNTIME_ROOT, SCIENCE_TOKENS
from .io_utils import sha256_file, write_json

RUNTIME_FILES = (
    "motion-core.js",
    "motion-core.css",
    "phrase-timing.js",
    "physics-helpers.js",
    "asset-loader.js",
    "browser-probe.js",
)


def _first_existing(candidates: list[Path]) -> Path | None:
    return next((path for path in candidates if path.exists()), None)


def _font_sources() -> dict[str, Path]:
    modules = LAB_ROOT / "node_modules"
    inter = _first_existing(
        [
            modules / "@fontsource-variable" / "inter" / "files" / "inter-latin-wght-normal.woff2",
            modules / "@fontsource" / "inter" / "files" / "inter-latin-400-normal.woff2",
        ]
    )
    plex = _first_existing(
        [
            modules / "@fontsource" / "ibm-plex-mono" / "files" / "ibm-plex-mono-latin-400-normal.woff2",
            modules / "@fontsource" / "ibm-plex-mono" / "files" / "ibm-plex-mono-latin-400-normal.woff",
        ]
    )
    missing = [name for name, path in (("Inter", inter), ("IBM Plex Mono", plex)) if path is None]
    if missing:
        raise RuntimeError(f"Missing bundled direct-HTML fonts: {', '.join(missing)}. Run npm install in template_lab.")
    return {"inter-latin-wght-normal.woff2": inter, "ibm-plex-mono-latin-400-normal.woff2": plex}  # type: ignore[dict-item]


def prepare_runtime_assets(run_path: Path) -> dict[str, Any]:
    output_root = run_path / "direct_html" / "runtime"
    output_root.mkdir(parents=True, exist_ok=True)
    files: list[dict[str, Any]] = []
    for name in RUNTIME_FILES:
        source = RUNTIME_ROOT / name
        if not source.exists():
            raise RuntimeError(f"Missing direct-HTML runtime file: {source}")
        target = output_root / name
        shutil.copy2(source, target)
        files.append({"id": name, "path": f"./runtime/{name}", "sha256": sha256_file(target), "kind": "runtime"})

    gsap_source = LAB_ROOT / "project" / "vendor" / "gsap.min.js"
    gsap_target = output_root / "gsap.min.js"
    shutil.copy2(gsap_source, gsap_target)
    files.append({"id": "gsap", "path": "./runtime/gsap.min.js", "sha256": sha256_file(gsap_target), "kind": "runtime"})

    fonts_dir = output_root / "fonts"
    fonts_dir.mkdir(parents=True, exist_ok=True)
    for name, source in _font_sources().items():
        target = fonts_dir / name
        shutil.copy2(source, target)
        files.append({"id": name, "path": f"./runtime/fonts/{name}", "sha256": sha256_file(target), "kind": "font"})

    assets: list[dict[str, Any]] = []
    for root in (LAB_ROOT / "project" / "assets", REPO_ROOT / "physics_animation_engine" / "assets"):
        if not root.exists():
            continue
        for source in sorted(root.rglob("*")):
            if source.is_file() and source.suffix.lower() in {".svg", ".png", ".webp"}:
                assets.append({"id": source.stem, "source": str(source.relative_to(REPO_ROOT)), "kind": source.suffix[1:]})

    manifest = {
        "version": ASSET_MANIFEST_VERSION,
        "runtime": files,
        "assets": assets,
        "tokens": SCIENCE_TOKENS,
        "network_policy": "local-only",
    }
    write_json(run_path / "direct_html" / "asset_manifest.json", manifest)
    return manifest
