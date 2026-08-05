"""Create publish-ready YouTube metadata and a thumbnail for a rendered lesson."""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

from mav_costs import record_model_usage
from mav_models import load_env
from mav_schema import read_json, run_dir, write_json

load_env()

ASPECT_RATIO = "16:9"
THUMBNAIL_IMAGE_SIZE = "2K"
THUMBNAIL_SIZE = (1280, 720)
THUMBNAIL_REFERENCE_ROOT = Path(__file__).resolve().parents[1] / "assets" / "youtube_thumbnail_references"
THUMBNAIL_REFERENCE_NAMES = ("reference-04.png", "reference-05.png")
COPY_REFERENCE_PATH = Path(__file__).resolve().parents[1] / "prompts" / "youtube_copy_reference.txt"
MOJIBAKE_MARKERS = frozenset("ÃÂâðÎï")
INVISIBLE_FORMATTING = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff"), None)

# Reverse the Windows-1252 table, including its undefined C1 bytes.  Those C1
# characters sometimes survive a broken copy/paste and are needed to recover
# emoji variation selectors and keycaps.
WINDOWS_1252_BYTES = {
    bytes((byte,)).decode("cp1252"): byte
    for byte in range(256)
    if byte not in {0x81, 0x8D, 0x8F, 0x90, 0x9D}
}
WINDOWS_1252_BYTES.update({chr(byte): byte for byte in (0x81, 0x8D, 0x8F, 0x90, 0x9D)})

METADATA_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "video_title": {"type": "string"},
        "alternative_titles": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "search_led": {"type": "string"},
                "curiosity_led": {"type": "string"},
            },
            "required": ["search_led", "curiosity_led"],
        },
        "description": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "hashtags": {"type": "array", "items": {"type": "string"}},
        "pinned_comment": {"type": "string"},
        "chapters": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {"timestamp": {"type": "string"}, "title": {"type": "string"}}, "required": ["timestamp", "title"]}},
        "filename": {"type": "string"},
        "playlist_placement": {"type": "array", "items": {"type": "string"}},
        "upload_settings": {"type": "array", "items": {"type": "string"}},
        "thumbnail": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "overlay_text": {"type": "string"},
                "supporting_text": {"type": "string"},
                "visual_prompt": {"type": "string"},
                "alt_text": {"type": "string"},
            },
            "required": ["overlay_text", "supporting_text", "visual_prompt", "alt_text"],
        },
    },
    "required": [
        "video_title", "alternative_titles", "description", "tags", "hashtags",
        "pinned_comment", "chapters", "filename", "playlist_placement",
        "upload_settings", "thumbnail",
    ],
}


def _timestamp(seconds: float) -> str:
    total = max(0, round(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def _repair_mojibake(text: str) -> str:
    """Recover UTF-8 that was mistakenly decoded as Windows-1252.

    The repair is deliberately marker-gated so legitimate Unicode text is not
    transliterated or otherwise changed.
    """
    # Some clipboard paths turn the final NBSP-looking byte of 🧠 into ordinary
    # spaces before we receive the text, leaving only this three-byte prefix.
    text = re.sub(r"ðŸ§ +", "🧠 ", text)
    if not any(character in MOJIBAKE_MARKERS or 0x80 <= ord(character) <= 0x9F for character in text):
        return text

    def repair_run(run: str) -> str:
        if not run:
            return ""
        raw = bytes(WINDOWS_1252_BYTES[character] for character in run)
        try:
            candidate = raw.decode("utf-8")
        except UnicodeDecodeError as error:
            # Preserve the character that cannot belong to UTF-8, then attempt
            # recovery on the text on either side of it.
            pivot = max(error.start, 0)
            return repair_run(run[:pivot]) + run[pivot : pivot + 1] + repair_run(run[pivot + 1 :])
        original_markers = sum(character in MOJIBAKE_MARKERS or 0x80 <= ord(character) <= 0x9F for character in run)
        candidate_markers = sum(character in MOJIBAKE_MARKERS or 0x80 <= ord(character) <= 0x9F for character in candidate)
        return candidate if candidate_markers < original_markers else run

    pieces: list[str] = []
    run: list[str] = []
    for character in text:
        if character in WINDOWS_1252_BYTES:
            run.append(character)
        else:
            pieces.append(repair_run("".join(run)))
            run = []
            pieces.append(character)
    pieces.append(repair_run("".join(run)))
    return "".join(pieces)


def _clean_model_text(value: Any) -> str:
    """Make model-authored copy safe for plain-text copy/paste."""
    text = str(value)
    text = text.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", "\t")
    text = re.sub(
        r"\\u([dD][89aAbB][0-9a-fA-F]{2})\\u([dD][c-fC-F][0-9a-fA-F]{2})",
        lambda match: chr(
            0x10000
            + ((int(match.group(1), 16) - 0xD800) << 10)
            + (int(match.group(2), 16) - 0xDC00)
        ),
        text,
    )
    text = re.sub(r"\\u([0-9a-fA-F]{4})", lambda match: chr(int(match.group(1), 16)), text)
    text = _repair_mojibake(text)
    text = unicodedata.normalize("NFC", text).translate(INVISIBLE_FORMATTING)
    return "".join(character for character in text if ord(character) >= 32 or character in "\n\t").strip()


def _ascii_copy(text: str) -> str:
    """Create a compatibility copy for editors that corrupt Unicode."""
    replacements = {
        "—": "-", "–": "-", "’": "'", "‘": "'", "“": '"', "”": '"',
        "•": "-", "▶": ">", "½": "1/2", "²": "^2", "³": "^3",
        "Δ": "delta ", "🧠": "[CHALLENGE]", "📘": "[COURSE]",
        "⚡": "[CHALLENGE]", "👇": "[SEE BELOW]", "1️⃣": "1.", "2️⃣": "2.",
    }
    for source, replacement in replacements.items():
        text = text.replace(source, replacement)
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def _narration_context(run_path: Path) -> str:
    narration = read_json(run_path / "narration.json")
    paragraphs = narration.get("paragraphs") or []
    transcript = "\n\n".join(str(item.get("text") or "") for item in paragraphs).strip()
    if not transcript:
        raise RuntimeError("narration.json contains no transcript for YouTube asset generation")
    timed_lines: list[str] = []
    manifest_path = run_path / "motion_canvas" / "manifest.json"
    if manifest_path.exists():
        manifest = read_json(manifest_path)
        units = manifest.get("reels") or manifest.get("shots") or manifest.get("chapters") or []
        for unit in units:
            start = float(unit.get("absolute_start") or unit.get("render_absolute_start") or 0)
            label = str(
                unit.get("narration")
                or unit.get("title")
                or unit.get("source_paragraph_id")
                or unit.get("scene_id")
                or ""
            ).strip()
            if label:
                timed_lines.append(f"{_timestamp(start)} {label[:180]}")
    timing = "\n".join(timed_lines) or "00:00 Lesson opening"
    return (
        f"LESSON TITLE: {narration.get('title', '')}\n\n"
        f"TIMED LESSON STRUCTURE (use these real times for YouTube chapters):\n{timing}\n\n"
        f"TRANSCRIPT:\n{transcript}"
    )


def _metadata_warning(message: str) -> None:
    """Report publish-platform guidance without discarding a paid model response."""
    print(f"YouTube metadata warning: {message}", file=sys.stderr)


def _clean_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        _metadata_warning("expected a list; using an empty list instead")
        return []
    return [_clean_model_text(item) for item in value if _clean_model_text(item)]


def _validate_metadata(value: dict[str, Any]) -> dict[str, Any]:
    """Normalize metadata and warn about YouTube guidance; never reject it for limits.

    This runs after a paid model call. Platform limits are useful publishing guidance,
    but must not turn an otherwise usable generation into a failed run.
    """
    if not isinstance(value, dict):
        _metadata_warning("model response was not an object; creating a minimal metadata pack")
        value = {}
    required = set(METADATA_SCHEMA["required"])
    missing = sorted(required - set(value))
    unexpected = sorted(set(value) - required)
    if missing or unexpected:
        _metadata_warning(
            "metadata fields differ from the requested schema"
            + (f"; missing: {missing}" if missing else "")
            + (f"; ignoring unexpected: {unexpected}" if unexpected else "")
        )

    title = _clean_model_text(value.get("video_title") or "")
    if not title:
        _metadata_warning("title is empty; using 'IGCSE Physics Lesson'")
        title = "IGCSE Physics Lesson"
    elif len(title) > 100:
        _metadata_warning(f"title is {len(title)} characters (YouTube recommends 100 or fewer)")
    description = _clean_model_text(value.get("description") or "")
    if not description:
        _metadata_warning("description is empty")
    elif len(description) > 5_000:
        _metadata_warning(f"description is {len(description)} characters (YouTube allows up to 5000)")

    tags = _clean_list(value.get("tags", []))
    hashtags = [item.lstrip("#") for item in _clean_list(value.get("hashtags", []))]
    tag_length = len(", ".join(tags))
    if tag_length > 500:
        _metadata_warning(f"tags are {tag_length} characters (YouTube allows up to 500); keeping all generated tags")
    if len(hashtags) > 3:
        _metadata_warning(f"metadata has {len(hashtags)} hashtags (recommended maximum is 3); keeping all generated hashtags")

    alternatives = value.get("alternative_titles")
    if not isinstance(alternatives, dict):
        _metadata_warning("alternative titles are missing or malformed; using the recommended title")
        alternatives = {}
    normalized_alternatives: dict[str, str] = {}
    for key in ("search_led", "curiosity_led"):
        alternative = _clean_model_text(alternatives.get(key) or "")
        if not alternative:
            _metadata_warning(f"alternative title '{key}' is empty; using the recommended title")
            alternative = title
        elif len(alternative) > 100:
            _metadata_warning(f"alternative title '{key}' is {len(alternative)} characters (YouTube recommends 100 or fewer)")
        normalized_alternatives[key] = alternative

    thumbnail = value.get("thumbnail")
    if not isinstance(thumbnail, dict):
        _metadata_warning("thumbnail brief is missing or malformed; using fallback thumbnail copy")
        thumbnail = {}
    overlay_text = _clean_model_text(thumbnail.get("overlay_text") or "")
    if not overlay_text:
        _metadata_warning("thumbnail overlay text is empty; using 'IGCSE PHYSICS'")
        overlay_text = "IGCSE PHYSICS"
    elif len(overlay_text) > 32:
        _metadata_warning(f"thumbnail overlay text is {len(overlay_text)} characters (recommended maximum is 32)")
    supporting_text = _clean_model_text(thumbnail.get("supporting_text") or "")
    if len(supporting_text) > 48:
        _metadata_warning(f"thumbnail supporting text is {len(supporting_text)} characters (recommended maximum is 48)")
    visual_prompt = _clean_model_text(thumbnail.get("visual_prompt") or "")
    if not visual_prompt:
        _metadata_warning("thumbnail visual prompt is empty; using a generic IGCSE Physics thumbnail brief")
        visual_prompt = f"Create a clear, premium IGCSE Physics thumbnail for: {title}"

    chapters_value = value.get("chapters", [])
    if not isinstance(chapters_value, list):
        _metadata_warning("chapters are malformed; using a single opening chapter")
        chapters_value = []
    chapters = [
        {
            "timestamp": _clean_model_text(item.get("timestamp") or ""),
            "title": _clean_model_text(item.get("title") or ""),
        }
        for item in chapters_value
        if isinstance(item, dict)
    ]
    if not chapters:
        _metadata_warning("no usable chapters were generated; using a single opening chapter")
        chapters = [{"timestamp": "00:00", "title": "Lesson opening"}]
    return {
        **value,
        "video_title": title,
        "alternative_titles": normalized_alternatives,
        "description": description,
        "tags": tags,
        "hashtags": [f"#{item}" for item in hashtags],
        "pinned_comment": _clean_model_text(value.get("pinned_comment") or ""),
        "chapters": chapters,
        "filename": _clean_model_text(value.get("filename") or ""),
        "playlist_placement": _clean_list(value.get("playlist_placement", [])),
        "upload_settings": _clean_list(value.get("upload_settings", [])),
        "thumbnail": {
            "overlay_text": overlay_text,
            "supporting_text": supporting_text,
            "visual_prompt": visual_prompt,
            "alt_text": _clean_model_text(thumbnail.get("alt_text") or ""),
        },
    }


def _thumbnail_references() -> list[Path]:
    configured_names = [
        name.strip()
        for name in os.getenv(
            "MAV_YOUTUBE_THUMBNAIL_REFERENCES",
            ",".join(THUMBNAIL_REFERENCE_NAMES),
        ).split(",")
        if name.strip()
    ]
    references = [THUMBNAIL_REFERENCE_ROOT / name for name in configured_names]
    missing = [path.name for path in references if not path.is_file()]
    if missing:
        raise RuntimeError(
            "Missing required thumbnail style reference(s): "
            f"{', '.join(missing)}. Add them to {THUMBNAIL_REFERENCE_ROOT} "
            "or set MAV_YOUTUBE_THUMBNAIL_REFERENCES."
        )
    if len(references) != 2:
        raise RuntimeError(
            "Thumbnail generation requires exactly two coherent style references. "
            "Set MAV_YOUTUBE_THUMBNAIL_REFERENCES to two comma-separated filenames."
        )
    return references


def _thumbnail_prompt(
    creative_direction: str,
    overlay_text: str,
    supporting_text: str,
) -> str:
    return (
        "Use case: ads-marketing\n"
        "Asset type: premium high-click-through Cambridge IGCSE Physics YouTube thumbnail\n"
        "Output: one complete, finished 16:9 thumbnail including all typography\n\n"
        "STYLE REFERENCES\n"
        "Image 1 and Image 2 are the only approved visual references. Treat them as one coherent design "
        "system and match their visual language closely: spectacular photorealistic physics action, cinematic "
        "navy/black environment, dramatic speed and depth, strong rim lighting, electric-blue energy effects, "
        "bold yellow/orange emphasis, textured white paint-stroke panels, very large condensed uppercase type, "
        "clear visual comparison or transformation, and dense but controlled educational detail. Create a new "
        "topic-specific composition; do not copy their vehicles, equations, lesson subject, or logo.\n\n"
        "COMPOSITION AND HIERARCHY\n"
        "The thumbnail must feel dramatic, active, premium, and immediately understandable at mobile size. "
        "Use one dominant physics hero action or comparison, not generic floating objects. Build obvious "
        "foreground, midground, and background depth. Make the headline the strongest element, the hero action "
        "the second strongest, and keep supporting science details subordinate. Use the reference thumbnails' "
        "large-scale tension, motion blur, sparks or particles, luminous separation, brush-stroke labels, and "
        "high contrast. Keep every important element inside generous YouTube safe margins.\n\n"
        "TEXT — RENDER VERBATIM\n"
        f'Primary headline: "{overlay_text.upper()}"\n'
        f'Supporting line: "{supporting_text}"\n'
        'Small subject label: "IGCSE PHYSICS"\n'
        "Render those three text elements exactly, letter-for-letter, with no missing, duplicated, or substituted "
        "characters. Check spelling before finalizing. Use no other prose. Short scientifically correct symbols "
        "or equations are allowed only when requested below and only when they materially strengthen the design.\n\n"
        "LESSON-SPECIFIC CREATIVE DIRECTION\n"
        f"{creative_direction}\n\n"
        "QUALITY BAR\n"
        "Polished professional YouTube key art, crisp edges, realistic materials, cinematic color grading, "
        "excellent typography, strong thumbnail readability, and compelling visual storytelling. Avoid a flat "
        "classroom slide, sparse corporate layout, sterile blue grid, generic infographic, simple split-screen, "
        "tiny headline, weak contrast, excessive empty space, duplicated objects, nonsense apparatus, malformed "
        "equations, misspelled text, invented logo, watermark, or unrelated decoration."
    )


def _generate_thumbnail(
    prompt: str,
    overlay_text: str,
    supporting_text: str,
) -> tuple[bytes, str, str, list[str]]:
    """Generate the complete thumbnail using approved multimodal references."""
    return _generate_image_with_references(
        _thumbnail_prompt(prompt, overlay_text, supporting_text),
        aspect_ratio=ASPECT_RATIO,
        image_size=os.getenv("MAV_YOUTUBE_THUMBNAIL_IMAGE_SIZE", THUMBNAIL_IMAGE_SIZE),
    )


def _generate_image_with_references(
    full_prompt: str,
    *,
    aspect_ratio: str,
    image_size: str,
) -> tuple[bytes, str, str, list[str]]:
    """Generate one publishing image using the approved thumbnail reference pair."""
    from google import genai
    from google.genai import types

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("Gemini thumbnail generation requires GEMINI_API_KEY or GOOGLE_API_KEY")
    model = os.getenv("MAV_YOUTUBE_THUMBNAIL_IMAGE_MODEL", "gemini-3-pro-image")
    client = genai.Client(api_key=api_key)
    references = _thumbnail_references()
    contents: list[Any] = [full_prompt]
    for reference in references:
        mime_type = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }.get(reference.suffix.lower(), "image/png")
        contents.append(types.Part.from_bytes(data=reference.read_bytes(), mime_type=mime_type))
    try:
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
                image_config=types.ImageConfig(
                    aspect_ratio=aspect_ratio,
                    image_size=image_size,
                ),
            ),
        )
    except Exception as exc:
        raise RuntimeError(f"Gemini thumbnail image generation failed: {exc}") from exc
    for candidate in getattr(response, "candidates", []) or []:
        for part in getattr(getattr(candidate, "content", None), "parts", []) or []:
            inline_data = getattr(part, "inline_data", None)
            data = getattr(inline_data, "data", None)
            if data:
                record_model_usage(task="youtube_thumbnail_image", provider="gemini", model=model, usage={})
                return (
                    bytes(data),
                    str(getattr(inline_data, "mime_type", "image/png")),
                    model,
                    [str(path.relative_to(Path(__file__).resolve().parents[1])) for path in references],
                )
    raise RuntimeError("Gemini image model returned no image data")


def _normalize_thumbnail(
    image_data: bytes,
    target: Path,
    *,
    target_size: tuple[int, int] = THUMBNAIL_SIZE,
) -> None:
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Thumbnail compositing requires Pillow. Install it with `pip install Pillow`.") from exc
    image = Image.open(io.BytesIO(image_data)).convert("RGB")
    scale = max(target_size[0] / image.width, target_size[1] / image.height)
    resized = image.resize((round(image.width * scale), round(image.height * scale)), Image.Resampling.LANCZOS)
    left = (resized.width - target_size[0]) // 2
    top = (resized.height - target_size[1]) // 2
    canvas = resized.crop((left, top, left + target_size[0], top + target_size[1]))
    target.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(target, "JPEG", quality=94, optimize=True)


def _write_copy_pack(output_root: Path, metadata: dict[str, Any]) -> None:
    chapters = "\n".join(f"{item['timestamp']} {item['title']}" for item in metadata["chapters"])
    tags = ", ".join(metadata["tags"])
    hashtags = " ".join(metadata["hashtags"])
    playlists = "\n".join(f"- {item}" for item in metadata["playlist_placement"])
    settings = "\n".join(f"- {item}" for item in metadata["upload_settings"])
    pack = (
        "RECOMMENDED TITLE\n"
        f"{metadata['video_title']}\n\n"
        "ALTERNATIVE TITLE — SEARCH-LED\n"
        f"{metadata['alternative_titles']['search_led']}\n\n"
        "ALTERNATIVE TITLE — CURIOSITY-LED\n"
        f"{metadata['alternative_titles']['curiosity_led']}\n\n"
        "DESCRIPTION\n"
        f"{metadata['description']}\n\n"
        "TAGS\n"
        f"{tags}\n\n"
        "HASHTAGS\n"
        f"{hashtags}\n\n"
        "PINNED COMMENT\n"
        f"{metadata['pinned_comment']}\n\n"
        "CHAPTERS\n"
        f"{chapters}\n\n"
        "FILENAME\n"
        f"{metadata['filename']}\n\n"
        "PLAYLIST PLACEMENT\n"
        f"{playlists}\n\n"
        "UPLOAD SETTINGS\n"
        f"{settings}\n"
    )
    files = {
        "copy-paste.txt": pack,
        "copy-paste-ascii.txt": _ascii_copy(pack),
        "title.txt": metadata["video_title"] + "\n",
        "description.txt": metadata["description"] + "\n",
        "tags.txt": tags + "\n",
        "hashtags.txt": hashtags + "\n",
        "pinned-comment.txt": metadata["pinned_comment"] + "\n",
        "chapters.txt": chapters + "\n",
        "upload-checklist.txt": (
            f"Filename: {metadata['filename']}\n\n"
            f"Playlists:\n{playlists}\n\nSettings:\n{settings}\n"
        ),
    }
    for name, content in files.items():
        # A UTF-8 BOM prevents Windows editors and clipboard tools from
        # guessing Windows-1252 and producing strings such as "â€”".
        (output_root / name).write_text(content, encoding="utf-8-sig")


def generate(run_id: str) -> Path:
    run_path = run_dir(run_id)
    from mav_models import call_model_json, model_config_for_task

    system_path = Path(__file__).resolve().parents[1] / "prompts" / "youtube_metadata.system.txt"
    system = system_path.read_text(encoding="utf-8")
    if COPY_REFERENCE_PATH.exists():
        system += (
            "\n\nCOPY FORMAT REFERENCE\n"
            "Use the following as the benchmark for completeness, tone, formatting, challenge, "
            "tags, pinned comment, playlists and upload settings. Adapt every fact to the current transcript; "
            "do not copy lesson-specific claims from the example.\n\n"
            + COPY_REFERENCE_PATH.read_text(encoding="utf-8")
        )
    metadata = call_model_json(
        task="youtube_metadata",
        system=system,
        user=_narration_context(run_path),
        max_tokens=8_000,
        output_schema=METADATA_SCHEMA,
    )
    if not metadata:
        raise RuntimeError("YouTube metadata model returned no response")
    metadata = _validate_metadata(metadata)
    generated, mime_type, image_model, reference_images = _generate_thumbnail(
        metadata["thumbnail"]["visual_prompt"],
        metadata["thumbnail"]["overlay_text"],
        metadata["thumbnail"]["supporting_text"],
    )
    output_root = run_path / "youtube"
    _normalize_thumbnail(generated, output_root / "thumbnail.jpg")
    resolved = model_config_for_task("youtube_metadata", requested_max_tokens=8_000)
    report = {
        "status": "generated",
        "metadata_provider": resolved.provider,
        "metadata_model": resolved.model,
        "thumbnail_provider": "gemini",
        "thumbnail_model": image_model,
        "thumbnail_source_mime_type": mime_type,
        "thumbnail_reference_images": reference_images,
        "thumbnail_size": list(THUMBNAIL_SIZE),
        **metadata,
    }
    write_json(output_root / "metadata.json", report)
    _write_copy_pack(output_root, metadata)
    return output_root


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate YouTube publishing assets for a rendered MAV lesson.")
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    try:
        output = generate(args.run_id)
    except Exception as exc:
        print(f"YouTube assets failed: {exc}", file=sys.stderr)
        return 1
    print(f"YouTube publishing assets generated: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
