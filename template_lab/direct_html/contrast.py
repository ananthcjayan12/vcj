from __future__ import annotations

from typing import Any

from .constants import SCIENCE_TOKENS


def _relative_luminance(hex_color: str) -> float:
    value = hex_color.lstrip("#")
    channels = [int(value[index : index + 2], 16) / 255 for index in (0, 2, 4)]
    linear = [channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4 for channel in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast_ratio(foreground: str, background: str) -> float:
    first = _relative_luminance(foreground)
    second = _relative_luminance(background)
    return (max(first, second) + 0.05) / (min(first, second) + 0.05)


def essential_contrast_report() -> dict[str, Any]:
    pairs = {
        "text_on_deep": ("science-text", "science-bg-deep"),
        "text_on_stage": ("science-text", "science-bg"),
        "muted_on_deep": ("science-muted", "science-bg-deep"),
        "ink_on_light": ("science-ink", "science-light"),
    }
    checks = []
    for name, (foreground_name, background_name) in pairs.items():
        ratio = contrast_ratio(SCIENCE_TOKENS[f"--{foreground_name}"], SCIENCE_TOKENS[f"--{background_name}"])
        checks.append(
            {
                "name": name,
                "foreground": foreground_name,
                "background": background_name,
                "ratio": round(ratio, 3),
                "wcag_aa_normal_text": ratio >= 4.5,
            }
        )
    return {"status": "passed" if all(item["wcag_aa_normal_text"] for item in checks) else "failed", "checks": checks}
