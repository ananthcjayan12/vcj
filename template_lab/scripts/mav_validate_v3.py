"""V3 HTML sanitizer and validator."""
from __future__ import annotations

import copy
import colorsys
import re
from dataclasses import dataclass
from typing import Any


@dataclass
class V3Violation:
    code: str
    message: str
    scene_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {"code": self.code, "message": self.message}
        if self.scene_id:
            payload["scene_id"] = self.scene_id
        return payload


HTML_FORBIDDEN_PATTERNS = [
    (r"</?script\b", "SCRIPT_TAG", "Generated content contains a <script> tag"),
    (r"<iframe\b", "IFRAME_TAG", "Generated HTML contains <iframe> tag"),
    (r"<object\b", "OBJECT_TAG", "Generated HTML contains <object> tag"),
    (r"<embed\b", "EMBED_TAG", "Generated HTML contains <embed> tag"),
    (r"<link\b", "LINK_TAG", "Generated HTML contains <link> tag"),
    (r"javascript:", "JS_URI", "Generated HTML contains javascript: URI"),
    (r"\s+on[a-zA-Z]+\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+)", "EVENT_HANDLER", "Generated HTML contains inline event handler"),
    (r"<image\b", "SVG_IMAGE", "SVG contains <image> tag"),
    (r"base64", "BASE64", "Generated content contains base64 data"),
    (r"url\s*\(\s*[\"']?https?:", "EXTERNAL_URL", "CSS references external URL"),
]

GSAP_FORBIDDEN_PATTERNS = [
    (r"eval\s*\(", "EVAL", "Generated GSAP contains eval()"),
    (r"fetch\s*\(", "FETCH", "Generated code contains fetch()"),
    (r"XMLHttpRequest", "XHR", "Generated code contains XMLHttpRequest"),
    (r"window\.location", "LOCATION", "Generated code accesses window.location"),
    (r"document\.cookie", "COOKIE", "Generated code accesses document.cookie"),
]

HARDCODED_COLOR_PATTERN = re.compile(
    r"(?:color|background|background-color|fill|stroke|border-color|border|box-shadow|outline)\s*:[^;]*#[0-9a-fA-F]{3,8}",
    re.IGNORECASE,
)
SVG_ATTR_COLOR_PATTERN = re.compile(r"\b(?:fill|stroke)\s*=\s*[\"']#[0-9a-fA-F]{3,8}[\"']", re.IGNORECASE)
DIRECT_COLOR_FUNCTION_PATTERN = re.compile(r"\b(?:rgb|hsl)a?\(", re.IGNORECASE)
FUNCTION_CONSTRUCTOR_PATTERN = re.compile(r"(^|[^\w$])(?:new\s+)?Function\s*\(")
RGB_PATTERN = re.compile(r"\brgba?\(\s*([^)]+?)\s*\)", re.IGNORECASE)
HSL_PATTERN = re.compile(r"\bhsla?\(\s*([^)]+?)\s*\)", re.IGNORECASE)
HEX_PATTERN = re.compile(r"#[0-9a-fA-F]{3,8}")
EVENT_HANDLER_ATTR_PATTERN = re.compile(
    r"\s+on[a-zA-Z]+\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+)",
    re.IGNORECASE,
)
CSS_VAR_PATTERN = re.compile(r"var\(\s*(--[a-zA-Z0-9_-]+)")
CSS_VAR_DEFINITION_PATTERN = re.compile(r"(--[a-zA-Z0-9_-]+)\s*:")
STYLE_BLOCK_PATTERN = re.compile(r"<style\b[^>]*>(.*?)</style>", re.DOTALL | re.IGNORECASE)
V3_SCENE_CONTENT_OPEN_PATTERN = re.compile(r"^\s*<div\b[^>]*class=[\"'][^\"']*\bv3-scene-content\b[^\"']*[\"'][^>]*>", re.IGNORECASE)
SHELL_SELECTOR_PATTERN = re.compile(
    r"(^|[\s>+~])\.(?:camera|v3-scene-content|mav-scene|paper-bg|grain|vignette)\b",
    re.IGNORECASE,
)

ALLOWED_HARDCODED = {
    "#fff8e8",
}
DESIGN_TOKEN_VARS = {
    "--paper",
    "--paper-deep",
    "--paper-card",
    "--ink",
    "--muted-ink",
    "--teal",
    "--teal-wash",
    "--yellow",
    "--orange",
    "--red",
    "--pitch",
    "--pitch-dark",
    "--wood",
    "--wood-light",
    "--shadow",
    "--soft-shadow",
    "--serif",
    "--sans",
    "--condensed",
}

TOKEN_RGB = {
    "--paper": (242, 239, 228),
    "--paper-deep": (231, 225, 208),
    "--paper-card": (251, 247, 234),
    "--ink": (23, 23, 20),
    "--muted-ink": (94, 91, 82),
    "--teal": (66, 184, 139),
    "--teal-wash": (205, 233, 221),
    "--yellow": (242, 216, 75),
    "--orange": (231, 154, 99),
    "--red": (224, 70, 70),
    "--pitch": (31, 90, 67),
    "--pitch-dark": (23, 59, 49),
    "--wood": (57, 37, 27),
    "--wood-light": (107, 73, 55),
}

HEX_TO_TOKEN = {
    "#f2efe4": "--paper",
    "#e7e1d0": "--paper-deep",
    "#fbf7ea": "--paper-card",
    "#171714": "--ink",
    "#5e5b52": "--muted-ink",
    "#42b88b": "--teal",
    "#cde9dd": "--teal-wash",
    "#f2d84b": "--yellow",
    "#e79a63": "--orange",
    "#e04646": "--red",
    "#1f5a43": "--pitch",
    "#173b31": "--pitch-dark",
    "#39251b": "--wood",
    "#6b4937": "--wood-light",
    "#000": "--ink",
    "#000000": "--ink",
    "#fff": "--paper-card",
    "#ffffff": "--paper-card",
}


def _forbidden_violations(content: str, scene_id: str, patterns: list[tuple[str, str, str]]) -> list[V3Violation]:
    violations: list[V3Violation] = []
    for pattern, code, message in patterns:
        if re.search(pattern, content, re.IGNORECASE):
            violations.append(V3Violation(code, message, scene_id))
    return violations


def validate_scene_html(scene_html: str, scene_id: str) -> list[V3Violation]:
    """Validate a single scene's generated HTML."""
    violations = _forbidden_violations(scene_html, scene_id, HTML_FORBIDDEN_PATTERNS)

    if "<style" not in scene_html.lower() and "style=" not in scene_html.lower():
        violations.append(V3Violation("MISSING_SCENE_CSS", "Scene has no <style> block or inline styling", scene_id))
    if re.search(re.escape(_scene_scope(scene_id)) + r"\s+" + _scene_data_selector_pattern(scene_id), scene_html):
        violations.append(
            V3Violation(
                "REDUNDANT_SCENE_SCOPE",
                "Scene CSS contains duplicate scene scoping that prevents selectors from matching the scene root",
                scene_id,
            )
        )

    for match in HARDCODED_COLOR_PATTERN.finditer(scene_html):
        color = re.search(r"#[0-9a-fA-F]{3,8}", match.group())
        if color and color.group().lower() not in ALLOWED_HARDCODED:
            violations.append(
                V3Violation(
                    "HARDCODED_COLOR",
                    f"Hardcoded color {color.group()} found; use CSS variables instead",
                    scene_id,
                )
            )

    for match in SVG_ATTR_COLOR_PATTERN.finditer(scene_html):
        color = re.search(r"#[0-9a-fA-F]{3,8}", match.group())
        if color and color.group().lower() not in ALLOWED_HARDCODED:
            violations.append(
                V3Violation(
                    "HARDCODED_COLOR",
                    f"Hardcoded SVG color {color.group()} found; use CSS variables instead",
                    scene_id,
                )
            )

    if DIRECT_COLOR_FUNCTION_PATTERN.search(scene_html):
        violations.append(V3Violation("DIRECT_RGB_HSL", "Generated CSS uses rgb()/rgba()/hsl()/hsla() directly", scene_id))

    defined_vars = set(CSS_VAR_DEFINITION_PATTERN.findall(scene_html))
    allowed_vars = DESIGN_TOKEN_VARS | defined_vars
    for css_var in sorted(set(CSS_VAR_PATTERN.findall(scene_html))):
        if css_var not in allowed_vars:
            violations.append(V3Violation("UNDEFINED_CSS_VARIABLE", f"Generated CSS references undefined token {css_var}", scene_id))

    return violations


def validate_scene_gsap(scene_gsap: str, scene_id: str, start: float, duration: float) -> list[V3Violation]:
    """Validate a scene's GSAP function."""
    del start, duration
    violations = _forbidden_violations(scene_gsap, scene_id, GSAP_FORBIDDEN_PATTERNS)

    if FUNCTION_CONSTRUCTOR_PATTERN.search(scene_gsap):
        violations.append(V3Violation("FUNCTION_CONSTRUCTOR", "Generated GSAP contains Function() constructor", scene_id))

    if "function initScene" not in scene_gsap:
        violations.append(V3Violation("MISSING_INIT_FUNCTION", "GSAP code does not contain initScene function", scene_id))

    if "tl." not in scene_gsap and "tl," not in scene_gsap:
        violations.append(V3Violation("NO_TIMELINE_USAGE", "GSAP code does not use the timeline parameter", scene_id))

    return violations


def sanitize_html(html: str) -> str:
    """Remove dangerous patterns from generated HTML before stitching."""
    html = re.sub(r"<script\b[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = EVENT_HANDLER_ATTR_PATTERN.sub("", html)
    html = re.sub(r"javascript\s*:", "blocked:", html, flags=re.IGNORECASE)
    return html


def _strip_redundant_v3_content_wrapper(html: str) -> tuple[str, bool]:
    """Remove a model-generated v3-scene-content wrapper; the shell already provides it."""
    match = V3_SCENE_CONTENT_OPEN_PATTERN.search(html)
    if not match:
        return html, False
    head = html[: match.start()]
    body = html[match.end() :]
    style_match = re.search(r"<style\b", body, flags=re.IGNORECASE)
    body_part = body[: style_match.start()] if style_match else body
    tail_part = body[style_match.start() :] if style_match else ""
    closing = re.search(r"</div>\s*$", body_part, flags=re.IGNORECASE)
    if not closing:
        return html, False
    unwrapped = head + body_part[: closing.start()].strip() + "\n" + tail_part.lstrip()
    return unwrapped, True


def _split_selector_list(selector_text: str) -> list[str]:
    selectors: list[str] = []
    current: list[str] = []
    depth = 0
    for char in selector_text:
        if char == "(":
            depth += 1
        elif char == ")" and depth:
            depth -= 1
        if char == "," and depth == 0:
            selectors.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    tail = "".join(current).strip()
    if tail:
        selectors.append(tail)
    return selectors


def _scene_scope(scene_id: str) -> str:
    return f'.mav-v3-scene[data-scene-id="{scene_id}"]'


def _scene_data_selector_pattern(scene_id: str) -> str:
    escaped_scene_id = re.escape(scene_id)
    return r'\[data-scene-id\s*=\s*(?:"' + escaped_scene_id + r'"|\'' + escaped_scene_id + r"'|" + escaped_scene_id + r")\]"


def _collapse_redundant_scene_scope(selector: str, scene_id: str) -> str:
    scope = _scene_scope(scene_id)
    duplicate_scope = re.compile(r"^" + re.escape(scope) + r"\s+" + _scene_data_selector_pattern(scene_id))
    while True:
        collapsed = duplicate_scope.sub(scope, selector)
        if collapsed == selector:
            return selector
        selector = collapsed


def _scope_selector(selector: str, scene_id: str) -> str:
    selector = selector.strip()
    if not selector:
        return selector
    scope = _scene_scope(scene_id)
    canonical_scope = re.compile(r"^\.mav-v3-scene" + _scene_data_selector_pattern(scene_id))
    scene_data_scope = re.compile(r"^" + _scene_data_selector_pattern(scene_id))
    if canonical_scope.match(selector):
        match = canonical_scope.match(selector)
        return _collapse_redundant_scene_scope(scope + selector[match.end() :], scene_id) if match else selector
    if scene_data_scope.match(selector):
        match = scene_data_scope.match(selector)
        return _collapse_redundant_scene_scope(scope + selector[match.end() :], scene_id) if match else selector
    if selector.startswith(":root"):
        return selector.replace(":root", scope, 1)
    if selector.startswith(("html", "body")):
        return scope + selector[len(selector.split()[0]) :]
    if selector.startswith("@"):
        return selector
    return f"{scope} {selector}"


def _scope_css_rules(css: str, scene_id: str) -> tuple[str, bool]:
    """Best-effort CSS selector scoping for model-generated scene style blocks."""
    output: list[str] = []
    cursor = 0
    changed = False
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", css, flags=re.DOTALL):
        output.append(css[cursor : match.start()])
        selector_text = match.group(1).strip()
        declarations = match.group(2)
        if selector_text.startswith(("@keyframes", "@font-face", "@property", "from", "to")) or re.match(r"^\d+%", selector_text):
            output.append(match.group(0))
        elif selector_text.startswith("@"):
            output.append(match.group(0))
        else:
            selectors = [selector for selector in _split_selector_list(selector_text) if not SHELL_SELECTOR_PATTERN.search(selector)]
            if not selectors:
                changed = True
                cursor = match.end()
                continue
            scoped_selector_text = ",\n".join(_scope_selector(selector, scene_id) for selector in selectors)
            output.append(f"{scoped_selector_text} {{{declarations}}}")
            if scoped_selector_text != selector_text:
                changed = True
        cursor = match.end()
    output.append(css[cursor:])
    return "".join(output), changed


def _scope_style_blocks(html: str, scene_id: str) -> tuple[str, bool]:
    changed = False

    def replace(match: re.Match[str]) -> str:
        nonlocal changed
        scoped_css, did_scope = _scope_css_rules(match.group(1), scene_id)
        changed = changed or did_scope
        return f"<style>\n{scoped_css.strip()}\n</style>"

    return STYLE_BLOCK_PATTERN.sub(replace, html), changed


def normalize_scene_html_for_shell(scene_html: str, scene_id: str) -> tuple[str, list[str]]:
    """Sanitize and isolate generated scene HTML before validation/build."""
    actions: list[str] = []
    normalized = sanitize_html(scene_html)
    if normalized != scene_html:
        actions.append("removed inline script/event/javascript patterns")
    normalized, unwrapped = _strip_redundant_v3_content_wrapper(normalized)
    if unwrapped:
        actions.append("removed redundant v3-scene-content wrapper")
    normalized, scoped = _scope_style_blocks(normalized, scene_id)
    if scoped:
        actions.append("scoped CSS selectors to scene data-scene-id")
    return normalized, actions


def _nearest_token(r: int, g: int, b: int) -> str:
    return min(
        TOKEN_RGB,
        key=lambda token: (TOKEN_RGB[token][0] - r) ** 2 + (TOKEN_RGB[token][1] - g) ** 2 + (TOKEN_RGB[token][2] - b) ** 2,
    )


def _alpha_color(token: str, alpha: float) -> str:
    alpha = max(0.0, min(1.0, alpha))
    if alpha <= 0.0:
        return "transparent"
    if alpha >= 1.0:
        return f"var({token})"
    percent = max(1, min(99, round(alpha * 100)))
    return f"color-mix(in srgb, var({token}) {percent}%, transparent)"


def _parse_number(value: str) -> float:
    value = value.strip()
    if value.endswith("%"):
        return float(value[:-1]) * 2.55
    return float(value)


def _repair_rgb_match(match: re.Match[str]) -> str:
    parts = [part.strip() for part in match.group(1).split(",")]
    if len(parts) < 3:
        return match.group(0)
    try:
        r = round(_parse_number(parts[0]))
        g = round(_parse_number(parts[1]))
        b = round(_parse_number(parts[2]))
        alpha = float(parts[3].rstrip("%")) / 100.0 if len(parts) >= 4 and parts[3].strip().endswith("%") else float(parts[3]) if len(parts) >= 4 else 1.0
    except ValueError:
        return match.group(0)
    return _alpha_color(_nearest_token(r, g, b), alpha)


def _repair_hsl_match(match: re.Match[str]) -> str:
    parts = [part.strip() for part in match.group(1).split(",")]
    if len(parts) < 3:
        return match.group(0)
    try:
        hue = float(parts[0].rstrip("deg")) % 360.0
        saturation = float(parts[1].rstrip("%")) / 100.0
        lightness = float(parts[2].rstrip("%")) / 100.0
        alpha = float(parts[3].rstrip("%")) / 100.0 if len(parts) >= 4 and parts[3].strip().endswith("%") else float(parts[3]) if len(parts) >= 4 else 1.0
    except ValueError:
        return match.group(0)
    r_float, g_float, b_float = colorsys.hls_to_rgb(hue / 360.0, lightness, saturation)
    return _alpha_color(_nearest_token(round(r_float * 255), round(g_float * 255), round(b_float * 255)), alpha)


def _repair_hex_match(match: re.Match[str]) -> str:
    color = match.group(0).lower()
    if color in ALLOWED_HARDCODED:
        return match.group(0)
    if len(color) == 4:
        color = "#" + "".join(ch * 2 for ch in color[1:])
    token = HEX_TO_TOKEN.get(color)
    return f"var({token})" if token else match.group(0)


def _style_blocks(text: str) -> list[str]:
    return re.findall(r"<style\b[^>]*>.*?</style>", text, flags=re.DOTALL | re.IGNORECASE)


def _recover_orphan_styles(scene_html: str, raw_response: str) -> tuple[str, bool]:
    if "<style" in scene_html.lower() or not raw_response:
        return scene_html, False
    styles = _style_blocks(raw_response)
    if not styles:
        return scene_html, False
    return scene_html.rstrip() + "\n\n" + "\n".join(styles), True


def repair_scene_html(scene_html: str, raw_response: str = "", scene_id: str = "unknown") -> tuple[str, list[str]]:
    """Apply deterministic safety/design-system repairs to generated HTML."""
    repaired, recovered_styles = _recover_orphan_styles(scene_html, raw_response)
    actions: list[str] = []
    if recovered_styles:
        actions.append("recovered style block from raw model response")

    repaired, normalize_actions = normalize_scene_html_for_shell(repaired, scene_id)
    actions.extend(action for action in normalize_actions if action not in actions)

    next_html = RGB_PATTERN.sub(_repair_rgb_match, repaired)
    next_html = HSL_PATTERN.sub(_repair_hsl_match, next_html)
    if next_html != repaired:
        actions.append("converted rgb/rgba/hsl/hsla colors to design-token color-mix values")
    repaired = next_html

    next_html = HEX_PATTERN.sub(_repair_hex_match, repaired)
    if next_html != repaired:
        actions.append("converted hardcoded hex colors to design-token variables")
    return next_html, actions


def repair_v3_plan(plan: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Repair common model drift across a V3 plan without inventing new scene content."""
    repaired = copy.deepcopy(plan)
    repairs: list[dict[str, Any]] = []
    for scene in repaired.get("scenes", []):
        scene_html = scene.get("scene_html", "")
        if not scene_html:
            continue
        fixed_html, actions = repair_scene_html(scene_html, scene.get("raw_response", ""), str(scene.get("id", "unknown")))
        if actions:
            scene["scene_html"] = fixed_html
            repairs.append({"scene_id": scene.get("id", "unknown"), "actions": actions})
    return repaired, repairs


def validate_v3_plan(plan: dict[str, Any]) -> list[V3Violation]:
    """Validate an entire V3 scene plan."""
    violations: list[V3Violation] = []
    scenes = plan.get("scenes", [])

    if not scenes:
        violations.append(V3Violation("NO_SCENES", "V3 plan has no scenes"))
        return violations

    for scene in scenes:
        sid = scene.get("id", "unknown")
        html = scene.get("scene_html", "")
        gsap = scene.get("scene_gsap", "")
        start = float(scene.get("start", 0))
        duration = float(scene.get("duration", 0))

        if not html:
            violations.append(V3Violation("EMPTY_HTML", "Scene has no HTML", sid))
        else:
            violations.extend(validate_scene_html(html, sid))

        if not gsap:
            violations.append(V3Violation("EMPTY_GSAP", "Scene has no GSAP code", sid))
        else:
            violations.extend(validate_scene_gsap(gsap, sid, start, duration))

    return violations
