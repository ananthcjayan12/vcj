from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from .constants import LAB_ROOT, LEGACY_STYLE_TERMS, REPO_ROOT, SCIENCE_TOKENS
from .contrast import essential_contrast_report
from .html_contract import extract_chapter_blocks
from .io_utils import read_json, write_json


def _node_env() -> dict[str, str]:
    env = os.environ.copy()
    candidates = sorted((Path.home() / ".nvm" / "versions" / "node").glob("v*/bin"), reverse=True)
    for candidate in candidates:
        node = candidate / "node"
        if not node.exists():
            continue
        try:
            version = subprocess.run([str(node), "--version"], capture_output=True, text=True, check=True, timeout=5).stdout.strip()
            major, minor, *_ = [int(part) for part in version.lstrip("v").split(".")]
        except Exception:
            continue
        if (major, minor) >= (22, 12):
            env["PATH"] = f"{candidate}{os.pathsep}{env.get('PATH', '')}"
            break
    return env


def resolve_chromium() -> Path:
    hyperframes = LAB_ROOT / "node_modules" / ".bin" / "hyperframes"
    result = subprocess.run(
        [str(hyperframes), "browser", "path"],
        cwd=LAB_ROOT,
        env=_node_env(),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode:
        ensure = subprocess.run([str(hyperframes), "browser", "ensure"], cwd=LAB_ROOT, env=_node_env(), capture_output=True, text=True, timeout=300)
        if ensure.returncode:
            raise RuntimeError((ensure.stderr or ensure.stdout).strip())
        result = subprocess.run([str(hyperframes), "browser", "path"], cwd=LAB_ROOT, env=_node_env(), capture_output=True, text=True, check=True, timeout=120)
    candidates = [Path(line.strip()) for line in result.stdout.splitlines() if line.strip() and Path(line.strip()).exists()]
    if not candidates:
        raise RuntimeError(f"HyperFrames did not return a Chromium path: {result.stdout.strip()}")
    return candidates[-1]


def _design_report(master_path: Path, browser_report: dict[str, Any]) -> dict[str, Any]:
    source = master_path.read_text(encoding="utf-8")
    html = source.lower()
    forbidden = [term for term in LEGACY_STYLE_TERMS if term.lower() in html]
    chapters = browser_report.get("chapters", [])
    findings = []
    allowed_colors = {value.lower() for value in SCIENCE_TOKENS.values()}
    document_raw_colors = sorted({value.lower() for value in re.findall(r"#[0-9a-f]{6}\b", html)} - allowed_colors)
    for chapter in chapters:
        if chapter.get("active_object_peak", 0) > 8:
            findings.append({"chapter_id": chapter["chapter_id"], "code": "TOO_MANY_ACTIVE_OBJECTS", "value": chapter["active_object_peak"]})
        if chapter.get("minimum_text_px") is not None and chapter["minimum_text_px"] < 30:
            findings.append({"chapter_id": chapter["chapter_id"], "code": "SMALL_IMPORTANT_TEXT", "value": chapter["minimum_text_px"]})
        if chapter.get("low_contrast_elements"):
            findings.append({"chapter_id": chapter["chapter_id"], "code": "LOW_TEXT_CONTRAST", "elements": chapter["low_contrast_elements"]})
        if chapter.get("accent_color_peak", 0) > 2:
            findings.append({"chapter_id": chapter["chapter_id"], "code": "EXCESSIVE_ACCENT_COLORS", "value": chapter["accent_color_peak"]})
    blocks = extract_chapter_blocks(source)
    for block_index, block in enumerate(blocks):
        lowered = block.source.lower()
        card_count = len(re.findall(r'(?:class|id)=["\'][^"\']*\bcard\b', lowered))
        panel_count = len(re.findall(r'(?:class|id)=["\'][^"\']*\b(?:panel|surface)\b', lowered))
        visible_words = re.findall(r">\s*([^<>]+?)\s*<", re.sub(r"<script\b.*?</script>", "", block.source, flags=re.IGNORECASE | re.DOTALL))
        word_count = sum(len(re.findall(r"\b[\w'-]+\b", text)) for text in visible_words)
        if card_count >= 3:
            findings.append({"chapter_id": block.chapter_id, "code": "REPEATED_CARD_LAYOUT", "value": card_count})
        if panel_count >= 3:
            findings.append({"chapter_id": block.chapter_id, "code": "EXCESSIVE_PANELS", "value": panel_count})
        if word_count > 120:
            findings.append({"chapter_id": block.chapter_id, "code": "TEXT_HEAVY_STATE", "value": word_count})
        if re.search(r"decorative[-_ ]particle|data-decoration=[\"']particle", lowered):
            findings.append({"chapter_id": block.chapter_id, "code": "DECORATIVE_PARTICLES"})
        if re.search(r"(?:\.to|\.from|\.fromto)\([^\n;]*(?:decorative[-_ ]particle|particle-[0-9])", lowered):
            findings.append({"chapter_id": block.chapter_id, "code": "MEANINGLESS_MOTION"})
        raw_colors = sorted({value.lower() for value in re.findall(r"#[0-9a-f]{6}\b", lowered)} - allowed_colors)
        if block_index == 0:
            raw_colors = sorted(set(raw_colors) | set(document_raw_colors))
        if raw_colors:
            findings.append({"chapter_id": block.chapter_id, "code": "NON_SEMANTIC_RAW_COLORS", "colors": raw_colors})
    contrast = essential_contrast_report()
    return {
        "status": "passed" if not forbidden and not findings and contrast["status"] == "passed" else "failed",
        "forbidden_legacy_terms": forbidden,
        "findings": findings,
        "essential_contrast": contrast,
    }


def inspect_lesson(run_path: Path, *, chromium: Path | None = None) -> dict[str, Any]:
    run_path = run_path.resolve()
    direct_root = run_path / "direct_html"
    master_path = (direct_root / "master.html").resolve()
    if not master_path.exists():
        raise RuntimeError(f"Missing direct-HTML master: {master_path}")
    if not (direct_root / "chapter_index.json").exists():
        raise RuntimeError("Direct-HTML chapter index must be built before browser inspection")
    inspection_root = direct_root / "inspection"
    script = Path(__file__).with_name("browser-inspector.mjs")
    result = subprocess.run(
        ["node", str(script), str(master_path), str(inspection_root), str(REPO_ROOT), str(chromium or resolve_chromium())],
        cwd=LAB_ROOT,
        env=_node_env(),
        capture_output=True,
        text=True,
        timeout=600,
    )
    if result.returncode:
        raise RuntimeError(f"Direct-HTML browser inspection failed: {(result.stderr or result.stdout).strip()}")
    report = json.loads(result.stdout)
    design = _design_report(master_path, report)
    write_json(direct_root / "validation" / "layout_validation.json", report)
    write_json(direct_root / "validation" / "design_system_validation.json", design)
    timeline = {
        "status": "passed" if all(item.get("deterministic_seek") for item in report.get("chapters", [])) else "failed",
        "chapters": [{"chapter_id": item["chapter_id"], "deterministic_seek": item["deterministic_seek"], "frozen_intervals": item["frozen_intervals"]} for item in report.get("chapters", [])],
    }
    write_json(direct_root / "validation" / "timeline_validation.json", timeline)
    combined = {
        "status": "passed" if report.get("status") == design.get("status") == timeline.get("status") == "passed" else "failed",
        "browser": report,
        "design_system": design,
        "timeline": timeline,
        "contact_sheet": "inspection/contact_sheet.png" if (inspection_root / "contact_sheet.png").exists() else None,
    }
    write_json(direct_root / "validation" / "final_direct_html_report.json", combined)
    return combined
