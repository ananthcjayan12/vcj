from __future__ import annotations

from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = LAB_ROOT.parent
ENGINE_ROOT = REPO_ROOT / "physics_animation_engine"
RUNTIME_ROOT = ENGINE_ROOT / "direct_html"
PROMPTS_ROOT = LAB_ROOT / "prompts"

DIRECT_HTML_MODE = "direct-html"
LEGACY_MODE = "legacy-recipes"
ANIMATION_MODES = (DIRECT_HTML_MODE, LEGACY_MODE)

CONTRACT_VERSION = "1.0"
PROMPT_VERSION = "1.0"
DESIGN_SYSTEM_VERSION = "1.0"
MOTION_CORE_VERSION = "1.0"
ASSET_MANIFEST_VERSION = "1.0"

VIEWPORT_WIDTH = 1920
VIEWPORT_HEIGHT = 1080
SAFE_MARGIN_PX = 100
MIN_IMPORTANT_TEXT_PX = 30
MIN_SECONDARY_TEXT_PX = 26
MAX_ACTIVE_OBJECTS = 8
MAX_HTML_BYTES = 150_000
MAX_CHAPTER_REPAIRS = 2

REQUIRED_ROOT_IDS = (
    "viewport",
    "stage",
    "camera",
    "background-layer",
    "world-layer",
    "diagram-layer",
    "annotation-layer",
    "overlay-layer",
    "html-overlay-layer",
)

FORBIDDEN_SOURCE_PATTERNS = (
    "fetch(",
    "XMLHttpRequest",
    "WebSocket",
    "EventSource",
    "serviceWorker",
    "eval(",
    "new Function(",
    "requestAnimationFrame(",
    "setInterval(",
)

LEGACY_STYLE_TERMS = (
    "--paper",
    "--wood",
    "paper-bg",
    "grain",
    "vignette",
    "stamp-hit",
)

SCIENCE_TOKENS = {
    "--science-bg-deep": "#07131F",
    "--science-bg": "#0E2234",
    "--science-surface": "#153047",
    "--science-surface-soft": "#1C3A52",
    "--science-light": "#F5F8FC",
    "--science-ink": "#102033",
    "--science-text": "#F4F8FC",
    "--science-muted": "#9FB2C7",
    "--science-cyan": "#35C6F4",
    "--science-blue": "#648BFF",
    "--science-green": "#43D6A0",
    "--science-yellow": "#F5C451",
    "--science-orange": "#FF8A5B",
    "--science-red": "#FF6577",
}
