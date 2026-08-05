"""Create per-Reel YouTube publishing copy and thumbnails for a rendered Reel pack."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any, Callable

TEMPLATE_LAB_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = Path(__file__).resolve().parent
for candidate in (str(TEMPLATE_LAB_ROOT), str(SCRIPTS_ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from mav_models import call_model_json, load_env, model_config_for_task  # noqa: E402
from mav_schema import read_json, run_dir, write_json  # noqa: E402
from mav_youtube_assets import (  # noqa: E402
    METADATA_SCHEMA,
    _generate_image_with_references,
    _normalize_thumbnail,
    _timestamp,
    _validate_metadata,
    _write_copy_pack,
)
from reel_pack.schema import require_reel_id  # noqa: E402

load_env()

PROMPT_PATH = TEMPLATE_LAB_ROOT / "prompts" / "youtube_reel_metadata.system.txt"
REEL_COVER_SIZE = (1080, 1920)
REEL_COVER_HOLD_SECONDS = 1.0
SHORTS_THUMBNAIL_NOTE = (
    "YouTube Shorts currently does not accept a separately uploaded custom thumbnail like "
    "long-form video. This asset pack therefore appends the exact generated cover as the final "
    "one-second frame of youtube-short.mp4. In the YouTube mobile app, select the final frame as "
    "the Short thumbnail. thumbnail.jpg is the same 9:16 image as a separate reusable file for "
    "Instagram, Facebook, TikTok, channel artwork, and other platforms that accept Reel covers.\n"
)
DELIVERY_ZIP_NAME = "youtube-reel-upload-pack.zip"


def _reel_cover_prompt(
    creative_direction: str,
    overlay_text: str,
    supporting_text: str,
) -> str:
    return (
        "Use case: ads-marketing\n"
        "Asset type: premium vertical Cambridge IGCSE Physics Reel cover\n"
        "Output: one complete, finished 9:16 cover including all typography\n\n"
        "Match the two supplied reference images as one coherent design system: spectacular "
        "photorealistic physics action, cinematic navy/black environment, strong rim lighting, "
        "electric-blue energy, bold yellow/orange emphasis, textured white paint-stroke panels, "
        "and very large condensed uppercase type. Adapt that language to a tall mobile composition. "
        "Keep the key subject and all text inside the central mobile-safe area.\n\n"
        "TEXT — RENDER VERBATIM\n"
        f'Primary headline: "{overlay_text.upper()}"\n'
        f'Supporting line: "{supporting_text}"\n'
        'Small subject label: "IGCSE PHYSICS"\n'
        "Use no other prose. Check every character before finalizing.\n\n"
        "REEL-SPECIFIC CREATIVE DIRECTION\n"
        f"{creative_direction}\n\n"
        "Create one dominant, scientifically correct physics action or comparison with obvious "
        "foreground, midground and background depth. Avoid flat slides, tiny type, grids, generic "
        "infographics, malformed equations, invented logos, watermarks, or unrelated decoration."
    )


def _generate_reel_cover(
    prompt: str,
    overlay_text: str,
    supporting_text: str,
) -> tuple[bytes, str, str, list[str]]:
    return _generate_image_with_references(
        _reel_cover_prompt(prompt, overlay_text, supporting_text),
        aspect_ratio="9:16",
        image_size="2K",
    )


def _video_duration(path: Path) -> float:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("Embedding the Reel cover requires ffprobe")
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Unable to inspect Reel duration: {result.stderr[-2000:]}")
    return float(result.stdout.strip())


def _append_cover_frame(source: Path, cover: Path, target: Path) -> float:
    """Create an upload copy with a selectable one-second cover at the end."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("Embedding the Reel cover requires ffmpeg")
    original_duration = _video_duration(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    filter_graph = (
        "[0:v]scale=1080:1920:force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,settb=AVTB,"
        "setpts=PTS-STARTPTS[main];"
        f"[1:v]scale=1080:1920,setsar=1,fps=30,settb=AVTB,"
        f"trim=duration={REEL_COVER_HOLD_SECONDS:g},setpts=PTS-STARTPTS[cover];"
        "[main][cover]concat=n=2:v=1:a=0[outv]"
    )
    result = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(source),
            "-loop",
            "1",
            "-i",
            str(cover),
            "-filter_complex",
            filter_graph,
            "-map",
            "[outv]",
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            str(target),
        ],
        capture_output=True,
        text=True,
        timeout=1800,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Unable to embed Reel cover frame: {result.stderr[-4000:]}")
    return original_duration + (REEL_COVER_HOLD_SECONDS / 2)


def _paragraphs_by_id(run_path: Path) -> dict[str, dict[str, Any]]:
    narration = read_json(run_path / "narration.json")
    return {
        str(item.get("id") or item.get("reel_id")): item
        for item in narration.get("paragraphs", [])
        if isinstance(item, dict)
    }


def _reel_context(pack: dict[str, Any], record: dict[str, Any], paragraph: dict[str, Any]) -> str:
    return json.dumps(
        {
            "content_product": "youtube-short",
            "reel_id": record["reel_id"],
            "pack_topic": pack.get("topic"),
            "topic_ref": pack.get("topic_ref"),
            "working_title": record.get("working_title"),
            "hook": record.get("hook"),
            "central_question": record.get("central_question"),
            "misconception": record.get("misconception"),
            "answer": record.get("answer"),
            "learning_payoff": record.get("learning_payoff"),
            "required_scientific_relationships": record.get("required_scientific_relationships", []),
            "narration": paragraph.get("text") or paragraph.get("narration") or "",
            "target_duration_seconds": record.get("target_duration_seconds"),
            "timed_reel_structure": [
                {
                    "id": beat.get("id"),
                    "start": beat.get("start"),
                    "end": beat.get("end"),
                    "narrative_job": beat.get("narrative_job"),
                    "spoken_text": beat.get("spoken_text"),
                }
                for beat in record.get("timed_beats", [])
                if isinstance(beat, dict)
            ],
        },
        indent=2,
        ensure_ascii=False,
    )


def _reel_timeline(record: dict[str, Any]) -> list[dict[str, str]]:
    """Build YouTube-valid Short chapters from authoritative timed beats."""
    duration = float(record.get("audio_duration_seconds") or record.get("target_duration_seconds") or 0)
    beats = [beat for beat in record.get("timed_beats", []) if isinstance(beat, dict)]
    opening = str(record.get("working_title") or record.get("title") or "Reel topic").strip()
    chapters: list[tuple[int, str]] = [(0, opening[:80])]
    title_overrides = {
        "prediction_prompt": "Make your prediction",
        "method_intro": "The method",
        "measurement": "Take the measurement",
        "calculation": "Calculate the answer",
        "mechanism": "How it works",
        "reversal": "The surprising result",
        "resolve": "Key takeaway",
        "worked_example": "Worked example",
        "misconception": "Common misconception",
    }
    for beat in beats[1:]:
        start = round(float(beat.get("start") or 0))
        if start - chapters[-1][0] < 10 or duration - start < 10:
            continue
        beat_id = str(beat.get("id") or "").strip()
        title = title_overrides.get(beat_id) or beat_id.replace("_", " ").strip().title()
        if not title:
            continue
        chapters.append((start, title[:80]))
        if len(chapters) == 4:
            break
    if len(chapters) < 3:
        return [{"timestamp": "00:00", "title": opening[:80]}]
    return [{"timestamp": _timestamp(start), "title": title} for start, title in chapters]


def _update_publishing_manifest(
    run_path: Path,
    generated_by_id: dict[str, dict[str, Any]],
) -> None:
    path = run_path / "publishing_manifest.json"
    publishing = read_json(path) if path.exists() else {"reels": []}
    for entry in publishing.get("reels", []):
        reel_id = str(entry.get("reel_id") or "")
        generated = generated_by_id.get(reel_id)
        if generated:
            entry["youtube"] = {
                "metadata": generated["metadata"],
                "thumbnail": generated["thumbnail"],
                "copy_paste": generated["copy_paste"],
                "youtube_video": generated["youtube_video"],
                "thumbnail_frame_seconds": generated["thumbnail_frame_seconds"],
                "status": generated["status"],
            }
    write_json(path, publishing)


def _write_delivery_zip(run_path: Path, manifest: dict[str, Any]) -> str:
    """Bundle every generated Reel's upload-ready assets into one portable ZIP."""
    archive_path = run_path / "youtube" / DELIVERY_ZIP_NAME
    archive_root = "youtube-reel-upload-pack"
    generated = [
        item for item in manifest.get("reels", [])
        if isinstance(item, dict) and item.get("status") == "generated"
    ]
    if not generated:
        raise RuntimeError("No generated YouTube Reel assets are available to package")

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            f"{archive_root}/README.txt",
            "One folder per Reel. Upload youtube-short.mp4, use copy-paste.txt for the "
            "title/description, and use thumbnail.jpg on platforms that accept custom covers.\n",
        )
        for item in generated:
            reel_id = str(item["reel_id"])
            reel_root = f"{archive_root}/{reel_id}"
            for key, filename in (
                ("youtube_video", "youtube-short.mp4"),
                ("thumbnail", "thumbnail.jpg"),
                ("copy_paste", "copy-paste.txt"),
                ("metadata", "metadata.json"),
                ("thumbnail_note", "shorts-thumbnail-note.txt"),
            ):
                relative = str(item.get(key) or "")
                path = run_path / relative
                if relative and path.is_file():
                    archive.write(path, f"{reel_root}/{filename}")
            ascii_copy = run_path / "youtube" / "reels" / reel_id / "copy-paste-ascii.txt"
            if ascii_copy.is_file():
                archive.write(ascii_copy, f"{reel_root}/copy-paste-ascii.txt")
        archive.writestr(
            f"{archive_root}/reel-assets.json",
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        )
    return str(archive_path.relative_to(run_path))


def generate(
    run_id: str,
    *,
    target_reel_id: str | None = None,
    metadata_call: Callable[..., dict[str, Any] | None] = call_model_json,
    thumbnail_call: Callable[..., tuple[bytes, str, str, list[str]]] = _generate_reel_cover,
    embed_cover: Callable[[Path, Path, Path], float] = _append_cover_frame,
) -> Path:
    run_path = run_dir(run_id)
    pack_path = run_path / "reel_pack.json"
    if not pack_path.exists():
        raise RuntimeError(f"{run_id} is not a standalone Reel pack")
    pack = read_json(pack_path)
    paragraphs = _paragraphs_by_id(run_path)
    target = require_reel_id(target_reel_id) if target_reel_id else None
    candidate_records = [
        record
        for record in pack.get("reels", [])
        if isinstance(record, dict)
        and record.get("status") != "rejected"
        and (target is None or record.get("reel_id") == target)
    ]
    records = (
        candidate_records
        if target
        else [
            record
            for record in candidate_records
            if (run_path / "motion_canvas" / "renders" / f"{record['reel_id']}.mp4").is_file()
        ]
    )
    if not records:
        raise RuntimeError("No rendered Reels were selected for YouTube asset generation")

    missing_videos = [
        record["reel_id"]
        for record in records
        if not (run_path / "motion_canvas" / "renders" / f"{record['reel_id']}.mp4").is_file()
    ]
    if missing_videos:
        raise RuntimeError(
            "Render the selected Reel MP4s before generating YouTube assets: "
            + ", ".join(missing_videos)
        )

    system = PROMPT_PATH.read_text(encoding="utf-8")
    output_root = run_path / "youtube" / "reels"
    output_root.mkdir(parents=True, exist_ok=True)
    resolved = model_config_for_task("youtube_metadata", requested_max_tokens=8_000)
    results: list[dict[str, Any]] = []
    generated_by_id: dict[str, dict[str, Any]] = {}

    for record in records:
        reel_id = str(record["reel_id"])
        reel_root = output_root / reel_id
        try:
            paragraph = paragraphs.get(reel_id, {})
            if not str(paragraph.get("text") or paragraph.get("narration") or "").strip():
                raise RuntimeError(f"{reel_id} has no narration")
            metadata = metadata_call(
                task="youtube_metadata",
                system=system,
                user=_reel_context(pack, record, paragraph),
                max_tokens=8_000,
                output_schema=METADATA_SCHEMA,
            )
            if not metadata:
                raise RuntimeError("YouTube metadata model returned no response")
            metadata = _validate_metadata(metadata)
            metadata["chapters"] = _reel_timeline(record)
            generated, mime_type, image_model, reference_images = thumbnail_call(
                metadata["thumbnail"]["visual_prompt"],
                metadata["thumbnail"]["overlay_text"],
                metadata["thumbnail"]["supporting_text"],
            )
            cover_path = reel_root / "thumbnail.jpg"
            _normalize_thumbnail(generated, cover_path, target_size=REEL_COVER_SIZE)
            source_video = run_path / "motion_canvas" / "renders" / f"{reel_id}.mp4"
            youtube_video = reel_root / "youtube-short.mp4"
            thumbnail_frame_seconds = embed_cover(source_video, cover_path, youtube_video)
            report = {
                "status": "generated",
                "reel_id": reel_id,
                "topic_ref": pack.get("topic_ref"),
                "source_video": f"motion_canvas/renders/{reel_id}.mp4",
                "youtube_video": str(youtube_video.relative_to(run_path)),
                "thumbnail_frame_seconds": thumbnail_frame_seconds,
                "thumbnail_hold_seconds": REEL_COVER_HOLD_SECONDS,
                "metadata_provider": resolved.provider,
                "metadata_model": resolved.model,
                "thumbnail_provider": "gemini",
                "thumbnail_model": image_model,
                "thumbnail_source_mime_type": mime_type,
                "thumbnail_reference_images": reference_images,
                "thumbnail_size": list(REEL_COVER_SIZE),
                **metadata,
            }
            write_json(reel_root / "metadata.json", report)
            _write_copy_pack(reel_root, metadata)
            (reel_root / "shorts-thumbnail-note.txt").write_text(
                SHORTS_THUMBNAIL_NOTE,
                encoding="utf-8-sig",
            )
            relative_root = reel_root.relative_to(run_path)
            result = {
                "reel_id": reel_id,
                "status": "generated",
                "metadata": str(relative_root / "metadata.json"),
                "thumbnail": str(relative_root / "thumbnail.jpg"),
                "copy_paste": str(relative_root / "copy-paste.txt"),
                "thumbnail_note": str(relative_root / "shorts-thumbnail-note.txt"),
                "youtube_video": str(relative_root / "youtube-short.mp4"),
                "thumbnail_frame_seconds": thumbnail_frame_seconds,
            }
            results.append(result)
            generated_by_id[reel_id] = result
            print(f"YouTube Reel assets generated: {reel_id}", flush=True)
        except Exception as exc:  # noqa: BLE001
            results.append({"reel_id": reel_id, "status": "failed", "error": str(exc)})
            print(f"WARNING: YouTube Reel assets failed for {reel_id}: {exc}", file=sys.stderr, flush=True)

    manifest_path = run_path / "youtube" / "reel-assets.json"
    existing_manifest = read_json(manifest_path) if manifest_path.exists() else {}
    existing_by_id = {
        str(item.get("reel_id") or ""): item
        for item in existing_manifest.get("reels", [])
        if isinstance(item, dict)
    }
    for item in results:
        existing_by_id[str(item["reel_id"])] = item
    merged_results = [
        existing_by_id[key]
        for key in sorted(existing_by_id)
    ]
    manifest = {
        "version": "1.0",
        "content_product": "topic-reel-pack",
        "status": (
            "generated"
            if merged_results and all(item["status"] == "generated" for item in merged_results)
            else "partial"
        ),
        "metadata_provider": resolved.provider,
        "metadata_model": resolved.model,
        "thumbnail_size": list(REEL_COVER_SIZE),
        "thumbnail_usage": "embedded as the final one-second frame of each youtube-short.mp4",
        "reels": merged_results,
    }
    manifest["download_zip"] = _write_delivery_zip(run_path, manifest)
    write_json(manifest_path, manifest)
    _update_publishing_manifest(run_path, generated_by_id)
    pack["current_step"] = max(int(pack.get("current_step") or 1), 9)
    pack["status"] = "youtube_assets_ready" if manifest["status"] == "generated" else "partial"
    write_json(pack_path, pack)
    if not generated_by_id:
        raise RuntimeError("YouTube asset generation failed for every selected Reel")
    return output_root


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate YouTube publishing assets for rendered standalone Reels."
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--reel-id")
    args = parser.parse_args()
    try:
        output = generate(args.run_id, target_reel_id=args.reel_id)
    except Exception as exc:  # noqa: BLE001
        print(f"YouTube Reel assets failed: {exc}", file=sys.stderr)
        return 1
    print(f"YouTube Reel publishing assets generated: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
