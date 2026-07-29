from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import signal
import shutil
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlparse
from urllib.request import urlopen

from video_engine.cli import TOPIC_ORDER, VALID_STATES
from template_lab.mav_env import load_repo_env

load_repo_env()


REPO_ROOT = Path(__file__).resolve().parents[1]
STATIC_ROOT = Path(__file__).resolve().parent / "static"
VIDEO_ENGINE_ROOT = REPO_ROOT / "video_engine"
CURRICULUM_ROOT = VIDEO_ENGINE_ROOT / "curriculum"
REGISTRY_ROOT = VIDEO_ENGINE_ROOT / "registry"
TOPICS_ROOT = VIDEO_ENGINE_ROOT / "topics"
TEMPLATE_LAB_ROOT = REPO_ROOT / "template_lab"
RUNS_ROOT = TEMPLATE_LAB_ROOT / "runs"
SCENE_LIBRARY_ROOT = REPO_ROOT / "physics_animation_engine"
QUESTION_INDEX_PATH = REPO_ROOT / "pilot" / "index_output" / "question_index.sqlite3"
OBJECTIVES_PATH = CURRICULUM_ROOT / "objectives.json"
COVERAGE_PATH = CURRICULUM_ROOT / "coverage_registry.json"
ASSETS_PATH = REGISTRY_ROOT / "animation_assets.json"
VIDEOS_PATH = REGISTRY_ROOT / "videos.json"
MODEL_MAP_PATH = TEMPLATE_LAB_ROOT / "prompts" / "prompt_model_mapping.json"
RENDER_QUEUE_PATH = TEMPLATE_LAB_ROOT / "render_queue.json"
PROJECT_PYTHON = REPO_ROOT / ".venv" / "bin" / "python3"
PYTHON_EXECUTABLE = str(PROJECT_PYTHON if PROJECT_PYTHON.exists() else Path(sys.executable))

STEP_NAMES = ("Inputs", "Script", "Audio", "Timing", "Scenes", "Validate", "Preview", "QA")
PAID_STEPS = {2, 3, 5, 6}
DIRECT_HTML_MODE = "direct-html"
MOTION_CANVAS_MODE = "motion-canvas"
LEGACY_MODE = "legacy-recipes"
RUN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,95}$")
TOPIC_REF_RE = re.compile(r"^\d+(?:\.\d+){1,2}$")
SCENE_ID_RE = re.compile(r"^scene_\d{2,3}$")
CHAPTER_ID_RE = re.compile(r"^chapter_\d{2,3}$")
MOTION_UNIT_ID_RE = re.compile(r"^(?:chapter|shot|reel|beat)_\d{2,3}$")
MODEL_PROVIDERS = {"configured", "gemini", "anthropic", "codex", "grok"}
AUDIO_PROVIDERS = {"gemini", "elevenlabs"}
CODEX_MODELS = ("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna", "gpt-5.5", "gpt-5.4", "gpt-5.4-mini")
CODEX_REASONING_EFFORTS = ("low", "medium", "high", "xhigh", "max", "ultra")
GROK_MODELS = ("grok-4.5",)
GROK_REASONING_EFFORTS = ("low", "medium", "high")
RENDER_QUALITIES = {"draft", "standard", "high"}

_processes: dict[str, subprocess.Popen[str]] = {}
_process_lock = threading.Lock()
_preview_process: subprocess.Popen[str] | None = None
_preview_run_id: str | None = None
_preview_url: str | None = None
_render_queue_lock = threading.RLock()
_render_queue_thread: threading.Thread | None = None
_render_queue_monitors: set[int] = set()


def _invalidate_motion_preview(run_id: str) -> None:
    """Stop a live preview whose loaded module graph is about to become stale."""
    global _preview_process, _preview_run_id, _preview_url
    with _process_lock:
        if _preview_run_id != run_id:
            return
        process = _preview_process
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        _preview_process = None
        _preview_run_id = None
        _preview_url = None


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".tmp-{os.getpid()}-{threading.get_ident()}")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def _require_run_id(run_id: str) -> str:
    if not RUN_ID_RE.fullmatch(run_id):
        raise ValueError("Invalid run ID")
    return run_id


def _require_topic_ref(topic_ref: str) -> str:
    if not TOPIC_REF_RE.fullmatch(topic_ref) or topic_ref not in TOPIC_ORDER:
        raise ValueError(f"Unknown topic reference: {topic_ref}")
    return topic_ref


def _run_dir(run_id: str) -> Path:
    return RUNS_ROOT / _require_run_id(run_id)


def model_map_payload() -> dict[str, Any]:
    payload = _read_json(MODEL_MAP_PATH, {"tasks": {}}) or {"tasks": {}}
    tasks = []
    step_by_task = {"script_structure": 2, "script_writing": 2, "audio_generation": 3, "scene_asset_shortlister": 5, "scene_asset_router": 5, "module_parameterizer": 5, "v3_creative_director": 5, "v3_scene_coder": 5, "direct_html_composer": 5, "direct_html_repair": 6, "direct_html_review": 8, "motion_canvas_batch": 5, "motion_canvas_repair": 5, "motion_canvas_lesson_screen": 7, "youtube_metadata": 9}
    labels = {"script_structure": "Script structure", "script_writing": "Script writing", "audio_generation": "Voice generation", "scene_asset_shortlister": "Asset shortlister", "scene_asset_router": "Asset router", "module_parameterizer": "Module parameterizer", "v3_creative_director": "Creative director", "v3_scene_coder": "Scene coder", "direct_html_composer": "Direct HTML composer", "direct_html_repair": "Chapter repair", "direct_html_review": "Visual reviewer", "motion_canvas_batch": "Motion Canvas reel coder", "motion_canvas_repair": "Motion Canvas compile repair", "motion_canvas_lesson_screen": "Optional AI visual reviewer", "youtube_metadata": "YouTube metadata and thumbnail brief"}
    retained_tasks = {"script_structure", "script_writing", "motion_canvas_batch", "motion_canvas_repair", "motion_canvas_lesson_screen", "youtube_metadata"}
    for task, config in payload.get("tasks", {}).items():
        if task not in retained_tasks:
            continue
        provider_models = dict(config.get("provider_models") or {})
        provider_models.setdefault(str(config.get("provider")), str(config.get("model")))
        configured_options = config.get("provider_model_options") or {}
        provider_model_options = {
            provider: list(configured_options.get(provider) or [model])
            for provider, model in provider_models.items()
        }
        if task in {"script_structure", "script_writing", "motion_canvas_batch", "motion_canvas_repair"}:
            provider_models["codex"] = CODEX_MODELS[0]
            provider_model_options["codex"] = list(CODEX_MODELS)
            provider_models["grok"] = GROK_MODELS[0]
            provider_model_options["grok"] = list(GROK_MODELS)
        tasks.append({"task": task, "label": labels.get(task, task.replace("_", " ").title()), "step": step_by_task.get(task), "provider": config.get("provider"), "model": config.get("model"), "provider_models": provider_models, "provider_model_options": provider_model_options, "reasoning_efforts": list(CODEX_REASONING_EFFORTS), "prompt_files": config.get("prompt_files", []), "max_tokens": config.get("max_tokens")})
    tasks.append({"task": "audio_generation", "label": labels["audio_generation"], "step": 3, "provider": "gemini", "model": os.getenv("GEMINI_TTS_MODEL", "gemini-3.1-flash-tts-preview"), "provider_models": {"gemini": "gemini-3.1-flash-tts-preview", "elevenlabs": os.getenv("ELEVENLABS_MODEL_ID", "eleven_v3")}, "prompt_files": [], "max_tokens": None})
    return {"version": payload.get("version"), "tasks": sorted(tasks, key=lambda item: (item.get("step") or 99, item["task"]))}


def _validate_task_models(value: Any) -> dict[str, dict[str, str]]:
    if value in (None, {}):
        return {}
    if not isinstance(value, dict):
        raise ValueError("Task model overrides must be an object")
    catalog = {item["task"]: item for item in model_map_payload()["tasks"]}
    overrides: dict[str, dict[str, str]] = {}
    for task, selection in value.items():
        if task not in catalog or not isinstance(selection, dict):
            raise ValueError(f"Unsupported model task: {task}")
        provider = str(selection.get("provider", "")).strip().lower()
        model = str(selection.get("model", "")).strip()
        reasoning = str(selection.get("reasoning_effort", "low")).strip().lower()
        allowed = catalog[task].get("provider_model_options") or {key: [item] for key, item in catalog[task]["provider_models"].items()}
        if provider not in allowed or model not in allowed[provider]:
            raise ValueError(f"Unsupported model selection for {task}: {provider}:{model}")
        if provider == "codex" and reasoning not in CODEX_REASONING_EFFORTS:
            raise ValueError(f"Unsupported Codex reasoning effort for {task}: {reasoning}")
        if provider == "grok" and reasoning not in GROK_REASONING_EFFORTS:
            raise ValueError(f"Unsupported Grok reasoning effort for {task}: {reasoning}")
        overrides[task] = {"provider": provider, "model": model}
        if provider in {"codex", "grok"}:
            overrides[task]["reasoning_effort"] = reasoning
    return overrides


def update_run_models(run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    meta = _load_meta(run_id)
    with _process_lock:
        process = _processes.get(run_id)
        if process and process.poll() is None:
            raise RuntimeError("Stop the active process before changing its model map")
    meta.setdefault("settings", {})["task_models"] = _validate_task_models(payload.get("task_models"))
    _append_log(run_id, "Prompt/model map updated")
    _save_meta(meta)
    return run_detail(run_id)


def _meta_path(run_id: str) -> Path:
    return _run_dir(run_id) / "studio_run.json"


def _log_path(run_id: str) -> Path:
    return _run_dir(run_id) / "studio.log"


def _append_log(run_id: str, line: str) -> None:
    path = _log_path(run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%H:%M:%S")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{stamp}] {line.rstrip()}\n")


def _load_curriculum() -> tuple[dict[str, Any], dict[str, Any]]:
    objectives = _read_json(OBJECTIVES_PATH)
    coverage = _read_json(COVERAGE_PATH)
    if not objectives or not coverage:
        raise RuntimeError("Curriculum registries are missing. Run python3 -m video_engine.cli init")
    return objectives, coverage


def _question_patterns(topic_ref: str) -> dict[str, Any]:
    empty = {"question_count": 0, "visual_count": 0, "command_words": [], "question_types": [], "difficulties": []}
    if not QUESTION_INDEX_PATH.exists():
        return empty
    with sqlite3.connect(QUESTION_INDEX_PATH) as connection:
        rows = connection.execute(
            "SELECT command_word, question_type, difficulty, has_visual FROM questions WHERE topic_ref = ?",
            (topic_ref,),
        ).fetchall()
    if not rows:
        return empty

    def ranked(index: int, *, ignore_unknown: bool = True) -> list[dict[str, Any]]:
        counts = Counter(str(row[index]).strip() for row in rows if row[index] not in (None, ""))
        if ignore_unknown:
            counts.pop("unknown", None)
        return [{"label": label, "count": count} for label, count in counts.most_common(8)]

    return {
        "question_count": len(rows),
        "visual_count": sum(int(row[3] or 0) for row in rows),
        "command_words": ranked(0),
        "question_types": ranked(1),
        "difficulties": ranked(2),
    }


def _topic_payloads() -> list[dict[str, Any]]:
    objectives_payload, coverage = _load_curriculum()
    records_by_topic: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in objectives_payload["objectives"]:
        records_by_topic[record["topic_ref"]].append(record)
    topics: list[dict[str, Any]] = []
    for position, topic_ref in enumerate(TOPIC_ORDER, 1):
        records = records_by_topic[topic_ref]
        states = Counter(coverage["objectives"][record["objective_id"]]["status"] for record in records)
        advanced = sum(1 for record in records if record["route"] == "supplement")
        topics.append(
            {
                "position": position,
                "ref": topic_ref,
                "title": records[0]["topic_title"],
                "domain_ref": records[0]["domain_ref"],
                "domain_title": records[0]["domain_title"],
                "total": len(records),
                "covered": states["covered"],
                "active": sum(states[state] for state in ("planned", "scripted", "rendered", "reviewed", "needs_revision")),
                "core": len(records) - advanced,
                "supplement": advanced,
                "states": dict(states),
                "complete": states["covered"] == len(records),
                "facts_ready": (TOPICS_ROOT / topic_ref / "facts.json").exists(),
            }
        )
    return topics


def dashboard_payload() -> dict[str, Any]:
    objectives_payload, coverage = _load_curriculum()
    topics = _topic_payloads()
    counts = Counter(item["status"] for item in coverage["objectives"].values())
    assets = _read_json(ASSETS_PATH, {"scenes": []}).get("scenes", [])
    videos = _read_json(VIDEOS_PATH, {"videos": []}).get("videos", [])
    next_topic = next((topic for topic in topics if not topic["complete"]), None)
    domains: dict[str, dict[str, Any]] = {}
    for topic in topics:
        domain = domains.setdefault(
            topic["domain_ref"],
            {"ref": topic["domain_ref"], "title": topic["domain_title"], "topics": 0, "objectives": 0, "covered": 0},
        )
        domain["topics"] += 1
        domain["objectives"] += topic["total"]
        domain["covered"] += topic["covered"]
    return {
        "syllabus": objectives_payload.get("syllabus", "Cambridge IGCSE Physics 0625"),
        "topics": topics,
        "domains": list(domains.values()),
        "next_topic": next_topic,
        "summary": {
            "topic_count": len(topics),
            "complete_topics": sum(topic["complete"] for topic in topics),
            "objective_count": objectives_payload["objective_count"],
            "covered_objectives": counts["covered"],
            "status_counts": {state: counts[state] for state in VALID_STATES},
            "scene_count": len(assets),
            "video_count": len(videos),
        },
        "providers": {
            "gemini": bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")),
            "elevenlabs": bool(os.getenv("ELEVENLABS_API_KEY")),
            "zai": bool(os.getenv("ZAI_API_KEY") or os.getenv("ZHIPU_API_KEY") or os.getenv("BIGMODEL_API_KEY")),
            "moonshot": bool(os.getenv("MOONSHOT_API_KEY")),
        },
    }


def topic_detail(topic_ref: str) -> dict[str, Any]:
    topic_ref = _require_topic_ref(topic_ref)
    objectives_payload, coverage = _load_curriculum()
    records = [record for record in objectives_payload["objectives"] if record["topic_ref"] == topic_ref]
    objectives = []
    for record in records:
        status = coverage["objectives"][record["objective_id"]]
        objectives.append({**record, **status})
    topic = next(topic for topic in _topic_payloads() if topic["ref"] == topic_ref)
    facts_path = TOPICS_ROOT / topic_ref / "facts.json"
    return {
        "topic": topic,
        "objectives": objectives,
        "assessment": _question_patterns(topic_ref),
        "facts_path": str(facts_path.relative_to(REPO_ROOT)),
        "facts": _read_json(facts_path),
        "runs": [run for run in list_runs() if run.get("topic_ref") == topic_ref],
    }


def _infer_step(run_path: Path) -> int:
    markers = (
        (1, "input.json"),
        (2, "narration.json"),
        (3, "audio_generation.json"),
        (4, "audio_timing.json"),
        (5, "motion_canvas/generation-report.json"),
        (6, "motion_canvas/robot-report.json"),
        # The contact sheet is produced by Step 6 browser-frame validation;
        # it is evidence for that step, not proof that Step 7 ran.
        (6, "motion_canvas/preview/contact-sheet.png"),
        (8, "motion_canvas/final.mp4"),
    )
    completed = 0
    for step, marker in markers:
        if (run_path / marker).exists():
            completed = max(completed, step)
    summary = _read_json(run_path / "generation_summary.json", {}) or {}
    if summary.get("stopped_after_step") is not None:
        completed = max(completed, max(0, min(int(summary["stopped_after_step"]), 8)))
    return completed


def _synthesized_meta(run_path: Path) -> dict[str, Any]:
    input_payload = _read_json(run_path / "input.json", {}) or {}
    summary = _read_json(run_path / "generation_summary.json", {}) or {}
    run_id = run_path.name
    step = int(summary.get("stopped_after_step") or _infer_step(run_path))
    status = "completed" if step >= 8 else ("created" if step == 0 else "paused")
    return {
        "id": run_id,
        "topic_ref": input_payload.get("topic_ref", ""),
        "topic": input_payload.get("topic", summary.get("topic", run_id)),
        "objective_ids": input_payload.get("objective_ids", []),
        "status": status,
        "current_step": step,
        "created_at": datetime.fromtimestamp(run_path.stat().st_ctime, timezone.utc).isoformat(),
        "updated_at": datetime.fromtimestamp(run_path.stat().st_mtime, timezone.utc).isoformat(),
        "settings": {"animation_mode": MOTION_CANVAS_MODE},
        "error": None,
    }


def _normalized_meta(run_path: Path, meta: dict[str, Any]) -> dict[str, Any]:
    """Backfill fields needed to resume runs created before the Studio schema."""
    normalized = dict(meta)
    input_payload = _read_json(run_path / "input.json", {}) or {}
    summary = _read_json(run_path / "generation_summary.json", {}) or {}
    topic_ref = str(normalized.get("topic_ref") or input_payload.get("topic_ref") or "").strip()
    if topic_ref:
        normalized["topic_ref"] = topic_ref
    normalized.setdefault("topic", input_payload.get("topic") or summary.get("topic") or run_path.name)
    normalized.setdefault("objective_ids", input_payload.get("objective_ids", []))
    normalized.setdefault("content_product", "full-lesson")
    if not normalized.get("facts_path") and TOPIC_REF_RE.fullmatch(topic_ref):
        facts_path = TOPICS_ROOT / topic_ref / "facts.json"
        if facts_path.exists():
            normalized["facts_path"] = str(facts_path.relative_to(REPO_ROOT))

    existing_settings = normalized.get("settings") if isinstance(normalized.get("settings"), dict) else {}
    settings = dict(existing_settings)
    settings.setdefault("content_product", normalized["content_product"])
    settings.setdefault("duration", float(input_payload.get("target_duration_seconds") or 480))
    settings.setdefault("model_provider", "gemini")
    settings.setdefault("audio_provider", "gemini")
    settings.setdefault("scene_concurrency", 1)
    settings.setdefault("confirm_paid_api", True)
    settings.setdefault("task_models", {})
    settings["animation_mode"] = MOTION_CANVAS_MODE
    normalized["settings"] = settings
    return normalized


def _load_meta(run_id: str) -> dict[str, Any]:
    run_path = _run_dir(run_id)
    if not run_path.exists():
        raise FileNotFoundError(run_id)
    stored = _read_json(_meta_path(run_id))
    meta = stored or _synthesized_meta(run_path)
    normalized = _normalized_meta(run_path, meta)
    if stored is not None and normalized != stored:
        _write_json(_meta_path(run_id), normalized)
    return normalized


def _save_meta(meta: dict[str, Any]) -> dict[str, Any]:
    meta["updated_at"] = _now()
    _write_json(_meta_path(meta["id"]), meta)
    return meta


def _artifact_snapshot(run_id: str) -> dict[str, Any]:
    run_path = _run_dir(run_id)
    summary = _read_json(run_path / "generation_summary.json", {}) or {}
    meta = _read_json(run_path / "studio_run.json", {}) or {}
    animation_mode = MOTION_CANVAS_MODE
    manifest_path = run_path / "preview_manifest.json" if animation_mode == DIRECT_HTML_MODE else run_path / "preview_manifest_v3.json"
    manifest = _read_json(manifest_path, {}) or {}
    master = manifest.get("master")
    render_report = _read_json(run_path / "render_report.json", {}) or {}
    output = render_report.get("output")
    scenes_payload = _read_json(run_path / "scene_plan_v3.json", {}) or {}
    scenes = [
        {
            "id": scene.get("id"),
            "start": scene.get("start"),
            "duration": scene.get("duration"),
            "beat_label": scene.get("beat_label", ""),
            "narration_text": scene.get("narration_text", ""),
            "renderer": scene.get("renderer", "v3_custom"),
            "route": scene.get("route", "custom"),
            "module": (scene.get("module") or {}).get("scene"),
            "routing": scene.get("routing", {}),
        }
        for scene in scenes_payload.get("scenes", [])
    ]
    chapters_payload = _read_json(run_path / "direct_html" / "chapter_index.json", {}) or {}
    direct_validation = _read_json(run_path / "direct_html" / "validation" / "final_direct_html_report.json", {}) or {}
    visual_review = _read_json(run_path / "direct_html" / "validation" / "visual_review.json", {}) or {}
    browser_metrics = {item.get("chapter_id"): item for item in (direct_validation.get("browser") or {}).get("chapters", [])}
    design_findings: dict[str, list[dict[str, Any]]] = {}
    for finding in (direct_validation.get("design_system") or {}).get("findings", []):
        design_findings.setdefault(str(finding.get("chapter_id", "")), []).append(finding)
    review_chapters = {item.get("chapter_id"): item for item in visual_review.get("chapters", [])}
    chapters = []
    if animation_mode == DIRECT_HTML_MODE:
        for chapter in chapters_payload.get("chapters", []):
            chapter_id = str(chapter.get("chapter_id", ""))
            screenshots = {}
            for label in ("start", "peak", "end"):
                relative = f"direct_html/inspection/{chapter_id}/{label}.png"
                if (run_path / relative).exists():
                    screenshots[label] = f"/artifacts/runs/{run_id}/{relative}"
            chapters.append(
                {
                    **chapter,
                    "screenshots": screenshots,
                    "metrics": browser_metrics.get(chapter_id, {}),
                    "findings": design_findings.get(chapter_id, []),
                    "visual_review": review_chapters.get(chapter_id, {}),
                }
            )
    motion_manifest = _read_json(run_path / "motion_canvas" / "manifest.json", {}) or {}
    motion_report = _read_json(run_path / "motion_canvas" / "generation-report.json", {}) or {}
    audio_manifest = _read_json(run_path / "audio_chunks" / "manifest.json", {}) or {}
    audio_by_id = {str(item.get("id")): item for item in audio_manifest.get("chapters", [])}
    batch_status = {}
    for batch in motion_manifest.get("batches", []):
        for scene_id in batch.get("chapter_ids", []):
            batch_status[scene_id] = batch.get("status", "pending")
    chapter_status = motion_manifest.get("chapter_status", {}) or {}
    chapters = []
    motion_units = (
        motion_manifest.get("reels") if motion_manifest.get("timeline_mode") == "immutable_reels"
        else motion_manifest.get("shots") or motion_manifest.get("chapters") or []
    )
    motion_directory = (
        "reels" if motion_manifest.get("timeline_mode") == "immutable_reels"
        else "shots" if motion_manifest.get("timeline_mode") == "immutable_shots"
        else "chapters"
    )
    for chapter in motion_units:
        audio = audio_by_id.get(str(chapter.get("source_paragraph_id") or chapter.get("id")), {})
        audio_path = str(audio.get("path") or "")
        chapters.append(
            {
                **chapter,
                "status": chapter_status.get(chapter.get("scene_id"), batch_status.get(chapter.get("scene_id"), "pending")),
                "source_ready": (run_path / "motion_canvas" / motion_directory / f"{chapter.get('scene_id')}.tsx").exists(),
                "audio_url": (
                    f"/artifacts/runs/{run_id}/voiceover.mp3#t={float(chapter.get('absolute_start', 0)):.3f},{float(chapter.get('absolute_end', 0)):.3f}"
                    if motion_manifest.get("timeline_mode") in {"immutable_shots", "immutable_reels"} and (run_path / "voiceover.mp3").exists()
                    else f"/artifacts/runs/{run_id}/" + "/".join(quote(part) for part in audio_path.split("/"))
                    if audio_path and (run_path / audio_path).exists()
                    else None
                ),
                "audio_quality": audio.get("quality", {}),
            }
        )
    files = []
    for relative in (
        "input.json", "story_skeleton.json", "narration.json", "narration.txt",
        "narration_elevenlabs.txt", "voiceover.mp3", "audio_generation.json",
        "audio_timing.json", "audio_word_timestamps.json", "generation_summary.json",
        "render_report.json", "debug/script_generation_debug.json",
        "debug/narration_model_raw.json", "debug/narration_normalized.json",
        "debug/narration_validation.json", "debug/step_02_script.json",
        "costs/summary.json", "costs/model_usage.json",
        "motion_canvas/manifest.json", "motion_canvas/generation-report.json",
        "motion_canvas/timeline.json",
        "motion_canvas/render-checkpoint.json",
        "motion_canvas/scenes.ts", "motion_canvas/validation.json",
        "motion_canvas/robot-report.json", "motion_canvas/preview/contact-sheet.png",
        "motion_canvas/lesson-review.json",
        "motion_canvas/final.mp4", "youtube/metadata.json", "youtube/copy-paste.txt",
        "youtube/title.txt", "youtube/description.txt", "youtube/tags.txt",
        "youtube/hashtags.txt", "youtube/pinned-comment.txt", "youtube/chapters.txt",
        "youtube/upload-checklist.txt", "youtube/thumbnail.jpg",
    ):
        if (run_path / relative).exists():
            files.append(relative)
    return {
        "files": files,
        "animation_mode": animation_mode,
        "scenes": scenes,
        "chapters": chapters,
        "timeline_mode": motion_manifest.get("timeline_mode", "legacy_chapters"),
        "timeline_id": motion_manifest.get("timeline_id"),
        "reels": motion_manifest.get("reels", []),
        "preview_url": _preview_url if _preview_run_id == run_id and _preview_process and _preview_process.poll() is None else None,
        "validation_preview_url": f"/artifacts/runs/{run_id}/motion_canvas/preview/contact-sheet.png" if (run_path / "motion_canvas" / "preview" / "contact-sheet.png").exists() else None,
        "mp4_url": f"/artifacts/runs/{run_id}/motion_canvas/final.mp4" if (run_path / "motion_canvas" / "final.mp4").exists() else (f"/artifacts/runs/{run_id}/{Path(output).relative_to(run_path)}" if output and Path(output).is_relative_to(run_path) else None),
        "summary": summary,
        "validation": _read_json(run_path / "motion_canvas" / "robot-report.json", {}) or {},
        "cost_summary": _read_json(run_path / "costs" / "summary.json", {}) or {},
        "usage_records": (_read_json(run_path / "costs" / "model_usage.json", {}) or {}).get("records", []),
        "direct_html_cost_summary": {},
        "routing_summary": {},
        "asset_shortlist": {},
    }


def run_detail(run_id: str) -> dict[str, Any]:
    meta = _load_meta(run_id)
    meta["current_step"] = max(int(meta.get("current_step", 0)), _infer_step(_run_dir(run_id)))
    meta["artifacts"] = _artifact_snapshot(run_id)
    meta["model_map"] = model_map_payload()
    with _process_lock:
        process = _processes.get(run_id)
        meta["process_active"] = bool(process and process.poll() is None)
    return meta


def list_runs() -> list[dict[str, Any]]:
    if not RUNS_ROOT.exists():
        return []
    runs = []
    for run_path in RUNS_ROOT.iterdir():
        if not run_path.is_dir() or not RUN_ID_RE.fullmatch(run_path.name):
            continue
        try:
            runs.append(run_detail(run_path.name))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    return sorted(runs, key=lambda item: item.get("updated_at", ""), reverse=True)


def _prepare_topic(topic_ref: str, force: bool = False) -> dict[str, Any]:
    topic_ref = _require_topic_ref(topic_ref)
    command = [PYTHON_EXECUTABLE, "-m", "video_engine.cli", "prepare-topic", topic_ref]
    facts_path = TOPICS_ROOT / topic_ref / "facts.json"
    if force or facts_path.exists():
        command.append("--force")
    result = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip())
    return {"message": result.stdout.strip(), "detail": topic_detail(topic_ref)}


def _paid_range(from_step: int, stop_after_step: int) -> bool:
    return any(from_step <= step <= stop_after_step for step in PAID_STEPS)


def build_generation_command(meta: dict[str, Any], request: dict[str, Any]) -> tuple[list[str], dict[str, str]]:
    from_step = int(request.get("from_step", 1))
    stop_after_step = int(request.get("stop_after_step", 8))
    if not (1 <= from_step <= stop_after_step <= 8):
        raise ValueError("Pipeline steps must satisfy 1 <= from <= stop <= 8")
    settings = {**meta.get("settings", {}), **request.get("settings", {})}
    animation_mode = MOTION_CANVAS_MODE
    paid = _paid_range(from_step, stop_after_step) or (animation_mode == DIRECT_HTML_MODE and from_step <= 6 <= stop_after_step)
    confirmed = bool(request.get("confirm_paid_api", settings.get("confirm_paid_api", False)))
    if paid and not confirmed:
        raise PermissionError("Steps 2, 3, 5, and conditional step-6 repairs require explicit paid-API confirmation")
    facts_path = Path(meta["facts_path"])
    if not facts_path.is_absolute():
        facts_path = REPO_ROOT / facts_path
    if not facts_path.exists():
        raise FileNotFoundError(facts_path)
    if from_step >= 6:
        motion_root = _run_dir(str(meta["id"])) / "motion_canvas"
        manifest = _read_json(motion_root / "manifest.json", {}) or {}
        units = manifest.get("reels") if manifest.get("timeline_mode") == "immutable_reels" else manifest.get("shots") or manifest.get("chapters") or []
        directory = "reels" if manifest.get("timeline_mode") == "immutable_reels" else "shots" if manifest.get("timeline_mode") == "immutable_shots" else "chapters"
        required = [str(item.get("scene_id")) for item in units if item.get("scene_id")]
        missing = [chapter_id for chapter_id in required if not (motion_root / directory / f"{chapter_id}.tsx").exists()]
        generation = _read_json(motion_root / "generation-report.json", {}) or {}
        if not required or missing or generation.get("status") != "generated":
            detail = f" Missing: {', '.join(missing)}." if missing else ""
            raise RuntimeError(f"Complete all Motion Canvas visual reels before starting step 6.{detail} Resume from step 5.")
    task_models = _validate_task_models(request.get("task_models", settings.get("task_models", {})))
    audio_selection = task_models.get("audio_generation", {})
    provider = str(settings.get("model_provider", "gemini"))
    audio_provider = str(audio_selection.get("provider") or settings.get("audio_provider", "gemini"))
    if provider not in MODEL_PROVIDERS:
        raise ValueError("Unsupported model provider")
    if audio_provider not in AUDIO_PROVIDERS:
        raise ValueError("Unsupported audio provider")
    command = [
        PYTHON_EXECUTABLE,
        str(TEMPLATE_LAB_ROOT / "scripts" / "mav_generate.py"),
        "--run-id", meta["id"],
        "--facts", str(facts_path),
        "--duration", str(float(settings.get("duration", 480))),
        "--model-provider", "configured",
        "--audio-provider", audio_provider,
        "--animation-mode", animation_mode,
        "--from-step", str(from_step),
        "--stop-after-step", str(stop_after_step),
    ]
    if paid:
        command.extend(["--use-model", "--confirm-paid-api"])
    if animation_mode == DIRECT_HTML_MODE and from_step <= 6 <= stop_after_step:
        command.append("--auto-repair")
    if request.get("force_paid_api"):
        command.append("--force-paid-api")
    scene_id = request.get("target_scene_id")
    if scene_id:
        if not SCENE_ID_RE.fullmatch(str(scene_id)):
            raise ValueError("Invalid scene ID")
        command.extend(["--v3-scene-id", str(scene_id)])
    motion_chapter_id = request.get("target_motion_chapter_id")
    if motion_chapter_id:
        if not MOTION_UNIT_ID_RE.fullmatch(str(motion_chapter_id)):
            raise ValueError("Invalid Motion Canvas reel or beat ID")
        command.extend(["--motion-chapter-id", str(motion_chapter_id)])
    env = os.environ.copy()
    if provider != "configured":
        catalog = {item["task"]: item for item in model_map_payload()["tasks"]}
        for script_task in ("script_structure", "script_writing"):
            task_config = catalog[script_task]
            if provider not in task_config["provider_models"]:
                raise ValueError(f"{provider} is not available for {script_task}")
            prefix = f"MAV_{script_task.upper()}"
            env[f"{prefix}_PROVIDER"] = provider
            env[f"{prefix}_MODEL"] = task_config["provider_models"][provider]
    for task, selection in task_models.items():
        if task == "audio_generation":
            env["GEMINI_TTS_MODEL" if selection["provider"] == "gemini" else "ELEVENLABS_MODEL_ID"] = selection["model"]
            continue
        prefix = f"MAV_{task.upper()}"
        env[f"{prefix}_PROVIDER"] = selection["provider"]
        env[f"{prefix}_MODEL"] = selection["model"]
        if selection["provider"] in {"codex", "grok"}:
            env[f"{prefix}_REASONING_EFFORT"] = selection.get("reasoning_effort", "low")
    motion_selection = task_models.get("motion_canvas_batch")
    if motion_selection and motion_selection["provider"] == "grok":
        # Grok Build uses a local leader/session service. Serialize long
        # headless generations so concurrent agents cannot contend for it.
        concurrency = 1
    elif motion_selection and motion_selection["provider"] == "codex":
        # Subscription-backed Codex runs are intentionally conservative; the
        # normal batch cache still preserves every successful result.
        concurrency = min(int(settings.get("scene_concurrency", 1)), 2)
    else:
        concurrency = int(settings.get("scene_concurrency", 1))
    instruction = str(request.get("custom_instruction", "")).strip()
    if instruction:
        if motion_chapter_id:
            env["MAV_MOTION_CHAPTER_REGEN_INSTRUCTION"] = instruction
        else:
            env["MAV_SCENE_REGEN_INSTRUCTION" if scene_id else "MAV_STEP_REGEN_INSTRUCTION"] = instruction
    env["MAV_V3_SCENE_CONCURRENCY"] = str(max(1, min(concurrency, 8)))
    # Moonshot currently permits three organization-wide concurrent requests.
    # Keep one slot free for targeted repairs and unrelated activity.
    env["MAV_MOTION_CANVAS_WORKERS"] = str(max(1, min(concurrency, 2)))
    # Compile & QA remains deterministic and technical-only. Multimodal
    # screening is launched explicitly through the optional review endpoint.
    env["MAV_MOTION_CANVAS_LESSON_REVIEW"] = "0"
    return command, env


def _start_process(run_id: str, command: list[str], env: dict[str, str], *, mode: str, target_step: int) -> dict[str, Any]:
    with _process_lock:
        existing = _processes.get(run_id)
        if existing and existing.poll() is None:
            raise RuntimeError("This run already has an active process")
    if target_step >= 5:
        _invalidate_motion_preview(run_id)
    meta = _load_meta(run_id)
    active_step = None
    if "--from-step" in command:
        try:
            active_step = int(command[command.index("--from-step") + 1])
        except (ValueError, IndexError):
            active_step = None
    meta.update({
        "status": "rendering" if mode == "render" else "running",
        "error": None,
        "process_started_at": _now(),
        "process_mode": mode,
        "process_target_step": target_step,
        "process_active_step": active_step,
    })
    _save_meta(meta)
    _append_log(run_id, f"Starting {mode}: {' '.join(command[:3])} …")
    if mode == "generation" and target_step >= 5 and env.get("MAV_MOTION_CANVAS_BATCH_PROVIDER"):
        provider = env["MAV_MOTION_CANVAS_BATCH_PROVIDER"]
        model = env.get("MAV_MOTION_CANVAS_BATCH_MODEL", "authenticated default")
        reasoning = env.get("MAV_MOTION_CANVAS_BATCH_REASONING_EFFORT")
        suffix = f" reasoning={reasoning}" if reasoning else ""
        _append_log(run_id, f"Step 5 chapter generator: provider={provider} model={model}{suffix}")

    def worker() -> None:
        process: subprocess.Popen[str] | None = None
        try:
            process = subprocess.Popen(
                command,
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            with _process_lock:
                _processes[run_id] = process
            assert process.stdout is not None
            for line in process.stdout:
                _append_log(run_id, line)
            return_code = process.wait()
            latest = _load_meta(run_id)
            if latest.get("status") == "stopped":
                return
            if return_code == 0:
                generation_report = _read_json(_run_dir(run_id) / "motion_canvas" / "generation-report.json", {}) or {}
                if mode == "generation" and target_step == 5 and generation_report.get("status") == "partial":
                    failures = generation_report.get("failures") or []
                    latest["status"] = "partial"
                    latest["current_step"] = min(int(latest.get("current_step", 0)), 4)
                    latest["error"] = f"Motion Canvas chapters are partial ({len(failures)} batch failures). Resume step 5."
                    _append_log(run_id, latest["error"])
                else:
                    latest["status"] = "rendered" if mode in {"render", "youtube_assets"} else "completed"
                    latest["current_step"] = max(int(latest.get("current_step", 0)), target_step)
                    latest["error"] = None
                    latest.pop("process_started_at", None)
                    latest.pop("process_mode", None)
                    latest.pop("process_target_step", None)
                    latest.pop("process_active_step", None)
                    _append_log(run_id, f"{mode.title()} completed")
            else:
                latest["status"] = "failed"
                latest["error"] = f"{mode.title()} exited with code {return_code}"
                latest.pop("process_started_at", None)
                latest.pop("process_mode", None)
                latest.pop("process_target_step", None)
                latest.pop("process_active_step", None)
                _append_log(run_id, latest["error"])
            _save_meta(latest)
        except Exception as exc:  # noqa: BLE001
            latest = _load_meta(run_id)
            latest.update({"status": "failed", "error": str(exc)})
            latest.pop("process_started_at", None)
            latest.pop("process_mode", None)
            latest.pop("process_target_step", None)
            latest.pop("process_active_step", None)
            _save_meta(latest)
            _append_log(run_id, f"Failed: {exc}")
        finally:
            with _process_lock:
                if _processes.get(run_id) is process:
                    _processes.pop(run_id, None)

    threading.Thread(target=worker, daemon=True, name=f"studio-{mode}-{run_id}").start()
    return run_detail(run_id)


def create_run(payload: dict[str, Any]) -> dict[str, Any]:
    content_product = str(payload.get("content_product") or "full-lesson")
    if content_product != "full-lesson":
        raise ValueError(f"Unsupported content product for the full-lesson pipeline: {content_product}")
    topic_ref = _require_topic_ref(str(payload.get("topic_ref", "")))
    detail = topic_detail(topic_ref)
    facts_path = TOPICS_ROOT / topic_ref / "facts.json"
    if not facts_path.exists():
        _prepare_topic(topic_ref)
    requested_id = str(payload.get("run_id", "")).strip()
    run_id = requested_id or f"physics-{topic_ref.replace('.', '-')}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    _require_run_id(run_id)
    run_path = _run_dir(run_id)
    if run_path.exists() and any(run_path.iterdir()):
        raise FileExistsError(f"Run already exists: {run_id}")
    animation_mode = MOTION_CANVAS_MODE
    settings = {
        "content_product": content_product,
        "duration": max(30, min(float(payload.get("duration", 480)), 1800)),
        "model_provider": payload.get("model_provider", "gemini"),
        "audio_provider": payload.get("audio_provider", "gemini"),
        "scene_concurrency": max(1, min(int(payload.get("scene_concurrency", 1)), 8)),
        "confirm_paid_api": bool(payload.get("confirm_paid_api", True)),
        "task_models": _validate_task_models(payload.get("task_models")),
        "animation_mode": animation_mode,
    }
    meta = {
        "id": run_id,
        "content_product": content_product,
        "topic_ref": topic_ref,
        "topic": f"{topic_ref} {detail['topic']['title']}",
        "objective_ids": [objective["objective_id"] for objective in detail["objectives"] if objective["status"] != "covered"],
        "facts_path": str(facts_path.relative_to(REPO_ROOT)),
        "status": "created",
        "current_step": 0,
        "created_at": _now(),
        "updated_at": _now(),
        "settings": settings,
        "error": None,
    }
    _save_meta(meta)
    _append_log(run_id, f"Run created for topic {topic_ref}")
    if payload.get("execute"):
        command, env = build_generation_command(meta, {"from_step": 1, "stop_after_step": 8, "confirm_paid_api": settings["confirm_paid_api"]})
        return _start_process(run_id, command, env, mode="generation", target_step=8)
    return run_detail(run_id)


def execute_run(run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    meta = _load_meta(run_id)
    settings_changed = False
    if "task_models" in payload:
        meta.setdefault("settings", {})["task_models"] = _validate_task_models(payload.get("task_models"))
        settings_changed = True
    if "confirm_paid_api" in payload:
        meta.setdefault("settings", {})["confirm_paid_api"] = bool(payload.get("confirm_paid_api"))
        settings_changed = True
    if settings_changed:
        _save_meta(meta)
    command, env = build_generation_command(meta, payload)
    return _start_process(run_id, command, env, mode="generation", target_step=int(payload.get("stop_after_step", 8)))


def _render_settings(payload: dict[str, Any]) -> dict[str, Any]:
    quality = str(payload.get("quality", "standard"))
    fps = int(payload.get("fps", 30))
    workers = int(payload.get("workers", 1))
    if quality not in RENDER_QUALITIES or fps not in {24, 25, 30, 50, 60} or not 1 <= workers <= 8:
        raise ValueError("Invalid render settings")
    return {"quality": quality, "fps": fps, "workers": workers, "force": bool(payload.get("force", False))}


def _clear_render_checkpoint(run_id: str) -> None:
    """Discard resumable frame state while preserving the last completed MP4."""
    motion_root = _run_dir(run_id) / "motion_canvas"
    shutil.rmtree(motion_root / "frames", ignore_errors=True)
    (motion_root / "render-checkpoint.json").unlink(missing_ok=True)


def _render_command(run_id: str, settings: dict[str, Any]) -> list[str]:
    return [
        PYTHON_EXECUTABLE,
        str(TEMPLATE_LAB_ROOT / "scripts" / "mav_render.py"),
        "--run-id", run_id,
        "--quality", str(settings["quality"]),
        "--fps", str(settings["fps"]),
        "--workers", str(settings["workers"]),
        "--animation-mode", MOTION_CANVAS_MODE,
    ]


def _read_render_queue() -> dict[str, Any]:
    payload = _read_json(RENDER_QUEUE_PATH, {}) or {}
    return {"version": 1, "entries": list(payload.get("entries") or [])}


def render_queue_payload() -> dict[str, Any]:
    with _render_queue_lock:
        payload = _read_render_queue()
    # Queue state and process output are requested together by the Studio UI.
    # Include a bounded log tail for active entries so a retry cannot look
    # stalled merely because a second client-side request races or fails.
    for entry in payload["entries"]:
        if entry.get("status") != "running":
            continue
        log_path = _log_path(str(entry.get("run_id") or ""))
        try:
            entry["live_log"] = log_path.read_text(encoding="utf-8")[-80_000:] if log_path.exists() else ""
        except OSError:
            # The render itself must never be affected by a transient log read.
            entry["live_log"] = ""
    payload["summary"] = dict(Counter(str(item.get("status")) for item in payload["entries"]))
    return payload


def _save_render_queue(payload: dict[str, Any]) -> None:
    _write_json(RENDER_QUEUE_PATH, payload)


def _set_queue_entry(entry_id: str, **updates: Any) -> dict[str, Any] | None:
    with _render_queue_lock:
        payload = _read_render_queue()
        entry = next((item for item in payload["entries"] if item.get("id") == entry_id), None)
        if entry is None:
            return None
        entry.update(updates)
        _save_render_queue(payload)
        return dict(entry)


def _pid_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def _finish_external_render(entry_id: str, run_id: str, pid: int) -> None:
    try:
        while _pid_is_alive(pid):
            time.sleep(2)
        report = _read_json(_run_dir(run_id) / "render_report.json", {}) or {}
        report_path = _run_dir(run_id) / "render_report.json"
        output = Path(str(report.get("output") or ""))
        with _render_queue_lock:
            entry = next((item for item in _read_render_queue()["entries"] if item.get("id") == entry_id), {})
        previous_report_mtime = float(entry.get("report_mtime_before") or 0)
        completed = bool(
            report and output.is_file() and report_path.exists()
            and report_path.stat().st_mtime_ns > previous_report_mtime
        )
        meta = _load_meta(run_id)
        stopped = meta.get("status") == "stopped"
        _set_queue_entry(
            entry_id,
            status="completed" if completed else "paused" if stopped else "queued",
            finished_at=_now() if completed or stopped else None,
            pid=None,
            error=None if completed else "Stopped by user; requeue to resume" if stopped
            else "Renderer stopped before completion; queued for checkpoint resume",
        )
        if completed:
            meta.update({"status": "rendered", "current_step": max(int(meta.get("current_step", 0)), 8), "error": None})
            _save_meta(meta)
    finally:
        with _render_queue_lock:
            _render_queue_monitors.discard(pid)
        _ensure_render_queue_worker()


def _render_queue_worker() -> None:
    global _render_queue_thread
    try:
        while True:
            with _render_queue_lock:
                payload = _read_render_queue()
                if any(item.get("status") == "running" for item in payload["entries"]):
                    return
                entry = next((item for item in payload["entries"] if item.get("status") == "queued"), None)
                if entry is None:
                    return
                entry.update({"status": "running", "started_at": _now(), "finished_at": None, "error": None})
                _save_render_queue(payload)
                entry = dict(entry)
            run_id = str(entry["run_id"])
            command = _render_command(run_id, dict(entry["settings"]))
            process: subprocess.Popen[str] | None = None
            try:
                meta = _load_meta(run_id)
                meta.update({"status": "rendering", "error": None})
                _save_meta(meta)
                if entry["settings"].get("force"):
                    _clear_render_checkpoint(run_id)
                    _append_log(run_id, "Force re-render requested; discarded saved frames and restarting from frame 0")
                _append_log(run_id, f"Starting queued render: {' '.join(command[:3])} …")
                report_path = _run_dir(run_id) / "render_report.json"
                _set_queue_entry(
                    str(entry["id"]),
                    report_mtime_before=report_path.stat().st_mtime_ns if report_path.exists() else 0,
                )
                process = subprocess.Popen(
                    command, cwd=REPO_ROOT, env=os.environ.copy(), stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, text=True, bufsize=1, start_new_session=True,
                )
                with _process_lock:
                    _processes[run_id] = process
                _set_queue_entry(str(entry["id"]), pid=process.pid)
                assert process.stdout is not None
                for line in process.stdout:
                    _append_log(run_id, line)
                return_code = process.wait()
                latest = _load_meta(run_id)
                if return_code == 0:
                    latest.update({"status": "rendered", "current_step": max(int(latest.get("current_step", 0)), 8), "error": None})
                    _set_queue_entry(str(entry["id"]), status="completed", finished_at=_now(), pid=None, error=None)
                    _append_log(run_id, "Queued render completed")
                elif latest.get("status") == "stopped":
                    _set_queue_entry(str(entry["id"]), status="paused", finished_at=_now(), pid=None, error="Stopped by user; requeue to resume")
                else:
                    latest.update({"status": "failed", "error": f"Render exited with code {return_code}; retry resumes saved frames"})
                    _set_queue_entry(str(entry["id"]), status="failed", finished_at=_now(), pid=None, error=latest["error"])
                    _append_log(run_id, latest["error"])
                _save_meta(latest)
            except Exception as exc:  # noqa: BLE001
                latest = _load_meta(run_id)
                latest.update({"status": "failed", "error": str(exc)})
                _save_meta(latest)
                _set_queue_entry(str(entry["id"]), status="failed", finished_at=_now(), pid=None, error=str(exc))
                _append_log(run_id, f"Queued render failed: {exc}")
            finally:
                with _process_lock:
                    if _processes.get(run_id) is process:
                        _processes.pop(run_id, None)
    finally:
        with _render_queue_lock:
            _render_queue_thread = None


def _ensure_render_queue_worker() -> None:
    global _render_queue_thread
    with _render_queue_lock:
        payload = _read_render_queue()
        running = [item for item in payload["entries"] if item.get("status") == "running"]
        for entry in running:
            pid = int(entry.get("pid") or 0)
            if pid and _pid_is_alive(pid):
                if pid not in _render_queue_monitors:
                    _render_queue_monitors.add(pid)
                    threading.Thread(
                        target=_finish_external_render,
                        args=(str(entry["id"]), str(entry["run_id"]), pid),
                        daemon=True,
                        name=f"render-monitor-{pid}",
                    ).start()
                return
            entry.update({"status": "queued", "pid": None, "error": "Resuming after interrupted Studio session"})
            _save_render_queue(payload)
        if _render_queue_thread and _render_queue_thread.is_alive():
            return
        if not any(item.get("status") == "queued" for item in payload["entries"]):
            return
        _render_queue_thread = threading.Thread(target=_render_queue_worker, daemon=True, name="studio-render-queue")
        _render_queue_thread.start()


def enqueue_render_runs(run_ids: list[str], payload: dict[str, Any]) -> dict[str, Any]:
    settings = _render_settings(payload)
    requested = list(dict.fromkeys(_require_run_id(str(run_id)) for run_id in run_ids))
    if not requested or len(requested) > 20:
        raise ValueError("Select between 1 and 20 runs for the render queue")
    with _render_queue_lock:
        queue = _read_render_queue()
        active_ids = {str(item.get("run_id")) for item in queue["entries"] if item.get("status") in {"queued", "running"}}
        for run_id in requested:
            meta = _load_meta(run_id)
            if int(meta.get("current_step", 0)) < 7:
                raise RuntimeError(f"{run_id} must complete preview/QA before MP4 rendering")
            if run_id in active_ids:
                continue
            queue["entries"].append({
                "id": f"render-{run_id}-{time.time_ns()}",
                "run_id": run_id,
                "topic": meta.get("topic"),
                "status": "queued",
                "settings": dict(settings),
                "queued_at": _now(),
                "started_at": None,
                "finished_at": None,
                "pid": None,
                "error": None,
            })
            active_ids.add(run_id)
        _save_render_queue(queue)
    _ensure_render_queue_worker()
    return render_queue_payload()


def render_run(run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    enqueue_render_runs([run_id], payload)
    return run_detail(run_id)


def generate_youtube_assets(run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Start Stage 9 after the lesson MP4 is available."""
    meta = _load_meta(run_id)
    if not (_run_dir(run_id) / "motion_canvas" / "final.mp4").is_file():
        raise RuntimeError("Render the MP4 before generating YouTube publishing assets")
    if "task_models" in payload:
        meta.setdefault("settings", {})["task_models"] = _validate_task_models(payload.get("task_models"))
        _save_meta(meta)
    # Reuse the established task-model environment builder so the saved
    # Gemini/Codex/Grok selection for youtube_metadata reaches the CLI.
    _, env = build_generation_command(meta, {"from_step": 1, "stop_after_step": 1, "confirm_paid_api": True})
    command = [PYTHON_EXECUTABLE, str(TEMPLATE_LAB_ROOT / "scripts" / "mav_youtube_assets.py"), "--run-id", run_id]
    return _start_process(run_id, command, env, mode="youtube_assets", target_step=9)


def regenerate_motion_chapter(run_id: str, chapter_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    meta = _load_meta(run_id)
    if not MOTION_UNIT_ID_RE.fullmatch(chapter_id):
        raise ValueError("Invalid Motion Canvas reel or beat ID")
    if not payload.get("confirm_paid_api"):
        raise PermissionError("Chapter regeneration requires explicit paid-API confirmation")
    run_path = _run_dir(run_id)
    manifest = _read_json(run_path / "motion_canvas" / "manifest.json", {}) or {}
    units = manifest.get("reels") if manifest.get("timeline_mode") == "immutable_reels" else manifest.get("shots") or manifest.get("chapters") or []
    chapter_ids = {str(item.get("scene_id")) for item in units}
    target_id = chapter_id
    custom_instruction = str(payload.get("custom_instruction", "")).strip()
    if chapter_id.startswith("beat_"):
        beat = next((item for item in manifest.get("beats", []) if str(item.get("beat_id")) == chapter_id), None)
        if beat is None:
            raise FileNotFoundError(f"Unknown visual beat: {chapter_id}")
        target_id = str(beat["reel_id"])
        custom_instruction = (
            f"Edit only {chapter_id} inside {target_id}, from reel-local {float(beat['local_start']):.3f}s "
            f"to {float(beat['local_end']):.3f}s. Preserve the visual state before this window and the persistent "
            f"composition after it. Do not clear or restart the stage at either beat boundary. "
            f"Beat narration: {beat.get('narration', '')}\nUser request: {custom_instruction or 'Improve this beat visually.'}"
        )
    if target_id not in chapter_ids:
        raise FileNotFoundError(f"Unknown Motion Canvas timeline unit: {chapter_id}")
    command, env = build_generation_command(
        meta,
        {
            "from_step": 5,
            "stop_after_step": 6,
            "confirm_paid_api": True,
            "force_paid_api": True,
            "target_motion_chapter_id": target_id,
            "custom_instruction": custom_instruction,
            "task_models": payload.get("task_models", (meta.get("settings") or {}).get("task_models", {})),
        },
    )
    _append_log(run_id, f"Regenerating bounded visual beat {chapter_id} in continuous reel {target_id}; immutable timeline and audio are preserved")
    return _start_process(run_id, command, env, mode="beat regeneration", target_step=6)


def start_motion_preview(run_id: str) -> dict[str, Any]:
    global _preview_process, _preview_run_id, _preview_url
    run_path = _run_dir(run_id)
    report = _read_json(run_path / "motion_canvas" / "robot-report.json", {}) or {}
    if report.get("status") != "passed":
        raise RuntimeError("Complete step 6 successfully before starting the video preview")
    if str(TEMPLATE_LAB_ROOT) not in sys.path:
        sys.path.insert(0, str(TEMPLATE_LAB_ROOT))
    from motion_canvas.pipeline import RUNTIME_ROOT, _modern_node_bin, prepare_runtime_preview

    manifest = _read_json(run_path / "motion_canvas" / "manifest.json", {}) or {}
    canvas = manifest.get("canvas") or {}
    width = int(canvas.get("width") or 1920)
    height = int(canvas.get("height") or 1080)

    with _process_lock:
        if _preview_process and _preview_process.poll() is None:
            if _preview_run_id == run_id and _preview_url:
                return {"status": "running", "url": _preview_url}
            _preview_process.terminate()
            try:
                _preview_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _preview_process.kill()
        prepare_runtime_preview(run_path)
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = int(probe.getsockname()[1])
        env = os.environ.copy()
        node_bin = _modern_node_bin()
        if node_bin:
            env["PATH"] = str(node_bin) + os.pathsep + env.get("PATH", "")
        env["VITE_MAV_CANVAS_WIDTH"] = str(width)
        env["VITE_MAV_CANVAS_HEIGHT"] = str(height)
        log_path = run_path / "motion_canvas" / "preview-server.log"
        with log_path.open("a", encoding="utf-8") as log_handle:
            _preview_process = subprocess.Popen(
                ["npm", "run", "serve", "--", "--port", str(port)],
                cwd=RUNTIME_ROOT,
                env=env,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                text=True,
            )
        _preview_run_id = run_id
        _preview_url = f"http://127.0.0.1:{port}/"
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if _preview_process.poll() is not None:
            tail = log_path.read_text(encoding="utf-8", errors="replace")[-2000:]
            raise RuntimeError(f"Motion Canvas preview failed to start:\n{tail}")
        try:
            with urlopen(_preview_url, timeout=1) as response:  # noqa: S310 - fixed localhost URL
                if response.status == 200:
                    return {"status": "running", "url": _preview_url}
        except OSError:
            time.sleep(0.25)
    raise RuntimeError(f"Motion Canvas preview did not become ready. See {log_path}")


def start_motion_lesson_review(run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Launch the optional multimodal review as an independent paid job."""
    if not payload.get("confirm_paid_api"):
        raise PermissionError("Optional AI visual review requires explicit paid-API confirmation")
    meta = _load_meta(run_id)
    run_path = _run_dir(run_id)
    technical = _read_json(run_path / "motion_canvas" / "robot-report.json", {}) or {}
    if technical.get("status") != "passed":
        raise RuntimeError("Complete Compile & QA successfully before running optional AI visual review")
    task_models = _validate_task_models(payload.get("task_models", (meta.get("settings") or {}).get("task_models", {})))
    screen = task_models.get("motion_canvas_lesson_screen")
    if not screen:
        catalog = {item["task"]: item for item in model_map_payload()["tasks"]}
        configured = catalog["motion_canvas_lesson_screen"]
        screen = {"provider": configured["provider"], "model": configured["model"]}
        task_models["motion_canvas_lesson_screen"] = screen
    meta.setdefault("settings", {})["task_models"] = task_models
    _save_meta(meta)

    command = [PYTHON_EXECUTABLE, str(TEMPLATE_LAB_ROOT / "scripts" / "mav_lesson_review.py"), "--run-id", run_id]
    auto_repair = bool(payload.get("auto_repair", True))
    if not auto_repair:
        command.append("--screen-only")
    env = os.environ.copy()
    for task in ("motion_canvas_lesson_screen", "motion_canvas_batch", "motion_canvas_repair"):
        selection = task_models.get(task)
        if not selection:
            continue
        prefix = f"MAV_{task.upper()}"
        env[f"{prefix}_PROVIDER"] = selection["provider"]
        env[f"{prefix}_MODEL"] = selection["model"]
        if selection["provider"] in {"codex", "grok"}:
            env[f"{prefix}_REASONING_EFFORT"] = selection.get("reasoning_effort", "low")
    _append_log(run_id, f"Optional AI visual review requested: reviewer={screen['provider']}:{screen['model']} auto_repair={auto_repair}")
    repair = task_models.get("motion_canvas_batch", {})
    if auto_repair and repair:
        _append_log(run_id, f"Flagged-reel regeneration model: {repair.get('provider')}:{repair.get('model')} reasoning={repair.get('reasoning_effort', 'default')}")
    return _start_process(
        run_id,
        command,
        env,
        mode="optional AI visual review",
        target_step=max(6, int(meta.get("current_step", 6))),
    )


def approve_motion_lesson_review(run_id: str) -> dict[str, Any]:
    run_path = _run_dir(run_id)
    report_path = run_path / "motion_canvas" / "lesson-review.json"
    report = _read_json(report_path, {}) or {}
    status = str(report.get("status") or "")
    if status == "approved":
        return report
    if status != "repaired_pending_review":
        raise ValueError("Only a repaired_pending_review report can be manually approved")
    corrected = list(report.get("corrected_contact_sheets") or [])
    if not corrected or any(not (run_path / relative).exists() for relative in corrected):
        raise ValueError("Corrected review evidence is missing; rerun the optional AI visual review")
    report.update({
        "status": "approved",
        "approved_at": _now(),
        "approved_from_status": status,
        "approval": "manual_corrected_evidence_review",
    })
    _write_json(report_path, report)
    robot_path = run_path / "motion_canvas" / "robot-report.json"
    robot = _read_json(robot_path, {}) or {}
    robot["lesson_review"] = report
    robot["lesson_review_status"] = "approved"
    _write_json(robot_path, robot)
    _append_log(run_id, "Corrected Gemini lesson-review evidence manually approved")
    return report


def repair_chapter_run(run_id: str, chapter_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    meta = _load_meta(run_id)
    if not CHAPTER_ID_RE.fullmatch(chapter_id):
        raise ValueError("Invalid chapter ID")
    if (meta.get("settings") or {}).get("animation_mode") != DIRECT_HTML_MODE:
        raise ValueError("Chapter repair is available only for direct-HTML runs")
    if not payload.get("confirm_paid_api"):
        raise PermissionError("Chapter repair requires explicit paid-API confirmation")
    command = [PYTHON_EXECUTABLE, "-m", "video_engine.cli", "repair-html", run_id, "--chapter", chapter_id, "--confirm-paid-api"]
    instruction = str(payload.get("custom_instruction", "")).strip()
    if instruction:
        command.extend(["--instruction", instruction])
    env = os.environ.copy()
    for task, selection in _validate_task_models(payload.get("task_models", (meta.get("settings") or {}).get("task_models", {}))).items():
        if task == "audio_generation":
            continue
        prefix = f"MAV_{task.upper()}"
        env[f"{prefix}_PROVIDER"] = selection["provider"]
        env[f"{prefix}_MODEL"] = selection["model"]
    return _start_process(run_id, command, env, mode="chapter repair", target_step=6)


def stop_run(run_id: str) -> dict[str, Any]:
    meta = _load_meta(run_id)
    with _process_lock:
        process = _processes.get(run_id)
        if process and process.poll() is None:
            # Render workers own npm, Node, Vite and Chrome descendants. New
            # workers run in their own process group so Stop terminates the
            # whole pipeline instead of leaving an orphan renderer blocking
            # the queue. Fall back safely for older in-flight workers that
            # share Studio's process group.
            process_group = os.getpgid(process.pid)
            if process_group == process.pid:
                os.killpg(process_group, signal.SIGTERM)
            else:
                process.terminate()
    meta.update({"status": "stopped", "error": None})
    with _render_queue_lock:
        queue = _read_render_queue()
        changed = False
        for entry in queue["entries"]:
            if entry.get("run_id") == run_id and entry.get("status") == "queued":
                entry.update({"status": "paused", "finished_at": _now(), "error": "Stopped before rendering started"})
                changed = True
        if changed:
            _save_render_queue(queue)
    _append_log(run_id, "Stop requested")
    return _save_meta(meta)


def delete_run(run_id: str) -> dict[str, Any]:
    run_id = _require_run_id(run_id)
    run_path = _run_dir(run_id)
    if not run_path.exists():
        raise FileNotFoundError(run_id)
    with _process_lock:
        process = _processes.get(run_id)
        if process and process.poll() is None:
            raise RuntimeError("Stop the active process before deleting this run")
        _processes.pop(run_id, None)
    with _render_queue_lock:
        queue = _read_render_queue()
        queue["entries"] = [item for item in queue["entries"] if item.get("run_id") != run_id]
        _save_render_queue(queue)
    shutil.rmtree(run_path)
    return {"status": "deleted", "run_id": run_id}


def reset_run_from_step(run_id: str, step: int) -> dict[str, Any]:
    if step not in range(1, 9):
        raise ValueError("Reset step must be between 1 and 8")
    run_path = _run_dir(run_id)
    meta = _load_meta(run_id)
    with _process_lock:
        process = _processes.get(run_id)
        if process and process.poll() is None:
            raise RuntimeError("Stop the active process before regenerating from a step")

    def remove(relative: str) -> None:
        path = run_path / relative
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)

    if step <= 1:
        for child in run_path.iterdir():
            if child.name not in {"studio_run.json", "studio.log"}:
                remove(child.name)
    else:
        if step <= 2:
            for relative in ("story_skeleton.json", "narration.json", "narration.txt", "narration_elevenlabs.txt"):
                remove(relative)
        if step <= 3:
            for relative in ("voiceover.mp3", "voiceover.wav", "audio_generation.json", "audio_alignment.json", "audio_chunks"):
                remove(relative)
        if step <= 4:
            for relative in ("audio_timing.json", "audio_word_timestamps.json"):
                remove(relative)
        if step <= 5:
            remove("motion_canvas")
        elif step <= 6:
            for relative in ("motion_canvas/validation.json", "motion_canvas/robot-report.json", "motion_canvas/preview", "motion_canvas/frames", "motion_canvas/final.mp4"):
                remove(relative)
        if step <= 8:
            for relative in ("generation_summary.json", "render_report.json"):
                remove(relative)
        remove("debug")
    meta.update({"status": "paused", "current_step": step - 1, "error": None, "settings": {**meta.get("settings", {}), "confirm_paid_api": True, "animation_mode": MOTION_CANVAS_MODE}})
    _append_log(run_id, f"Reset from step {step}; downstream artifacts removed")
    return run_detail(_save_meta(meta)["id"])


def update_topic_status(topic_ref: str, status: str) -> dict[str, Any]:
    topic_ref = _require_topic_ref(topic_ref)
    if status not in VALID_STATES:
        raise ValueError("Invalid coverage status")
    result = subprocess.run(
        [PYTHON_EXECUTABLE, "-m", "video_engine.cli", "set-status", "--topic", topic_ref, "--status", status],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip())
    return {"message": result.stdout.strip(), "detail": topic_detail(topic_ref)}


def _safe_file(root: Path, relative: str) -> Path:
    candidate = (root / unquote(relative)).resolve()
    if not candidate.is_relative_to(root.resolve()) or not candidate.is_file():
        raise FileNotFoundError(relative)
    return candidate


def _parse_byte_range(value: str, size: int) -> tuple[int, int]:
    """Parse one RFC 7233 byte range and return inclusive start/end offsets."""
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", value.strip())
    if not match or size <= 0:
        raise ValueError("Invalid byte range")
    raw_start, raw_end = match.groups()
    if not raw_start and not raw_end:
        raise ValueError("Invalid byte range")
    if not raw_start:
        suffix = int(raw_end)
        if suffix <= 0:
            raise ValueError("Invalid byte range")
        return max(0, size - suffix), size - 1
    start = int(raw_start)
    end = min(int(raw_end), size - 1) if raw_end else size - 1
    if start >= size or end < start:
        raise ValueError("Unsatisfiable byte range")
    return start, end


class StudioHandler(BaseHTTPRequestHandler):
    server_version = "PhysicsStudio/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        if getattr(self.server, "quiet", False):
            return
        super().log_message(format, *args)

    def _json(self, payload: Any, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 1_000_000:
            raise ValueError("Request body is too large")
        return json.loads(self.rfile.read(length) or b"{}")

    def _file(self, path: Path, *, cache: bool = False) -> None:
        size = path.stat().st_size
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        range_header = self.headers.get("Range")
        if range_header:
            try:
                start, end = _parse_byte_range(range_header, size)
            except ValueError:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            status = HTTPStatus.PARTIAL_CONTENT
        else:
            start, end = 0, size - 1
            status = HTTPStatus.OK
        length = max(0, end - start + 1)
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        if status == HTTPStatus.PARTIAL_CONTENT:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Cache-Control", "public, max-age=3600" if cache else "no-cache")
        self.end_headers()
        with path.open("rb") as handle:
            handle.seek(start)
            remaining = length
            while remaining:
                chunk = handle.read(min(64 * 1024, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def _error(self, exc: Exception) -> None:
        if isinstance(exc, PermissionError):
            status = HTTPStatus.PAYMENT_REQUIRED
        elif isinstance(exc, (ValueError, json.JSONDecodeError)):
            status = HTTPStatus.BAD_REQUEST
        elif isinstance(exc, FileNotFoundError):
            status = HTTPStatus.NOT_FOUND
        elif isinstance(exc, FileExistsError):
            status = HTTPStatus.CONFLICT
        else:
            status = HTTPStatus.INTERNAL_SERVER_ERROR
        try:
            self._json({"error": str(exc)}, int(status))
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return

    def do_GET(self) -> None:  # noqa: N802
        try:
            path = urlparse(self.path).path
            if path == "/api/dashboard":
                return self._json(dashboard_payload())
            if path == "/api/assets":
                return self._json(_read_json(ASSETS_PATH, {"scenes": []}))
            if path == "/api/runs":
                return self._json({"runs": list_runs()})
            if path == "/api/render-queue":
                return self._json({"queue": render_queue_payload()})
            if path == "/api/model-map":
                return self._json(model_map_payload())
            match = re.fullmatch(r"/api/topics/([^/]+)", path)
            if match:
                return self._json(topic_detail(match.group(1)))
            match = re.fullmatch(r"/api/runs/([^/]+)/logs", path)
            if match:
                run_id = _require_run_id(match.group(1))
                log = _log_path(run_id).read_text(encoding="utf-8") if _log_path(run_id).exists() else ""
                return self._json({"log": log[-80_000:]})
            match = re.fullmatch(r"/api/runs/([^/]+)", path)
            if match:
                return self._json({"run": run_detail(match.group(1))})
            if path.startswith("/artifacts/runs/"):
                relative = path.removeprefix("/artifacts/runs/")
                run_id, separator, artifact = relative.partition("/")
                if not separator:
                    raise FileNotFoundError(path)
                return self._file(_safe_file(_run_dir(run_id), artifact))
            if path.startswith("/artifacts/project/"):
                relative = path.removeprefix("/artifacts/project/")
                return self._file(_safe_file(TEMPLATE_LAB_ROOT / "project", relative), cache=True)
            if path.startswith("/scene-library/"):
                relative = path.removeprefix("/scene-library/") or "index.html"
                return self._file(_safe_file(SCENE_LIBRARY_ROOT, relative), cache=True)
            relative = "index.html" if path in {"/", ""} else path.lstrip("/")
            return self._file(_safe_file(STATIC_ROOT, relative))
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return
        except Exception as exc:  # noqa: BLE001
            self._error(exc)

    def do_POST(self) -> None:  # noqa: N802
        try:
            path = urlparse(self.path).path
            body = self._body()
            if path == "/api/runs":
                return self._json({"run": create_run(body)}, 201)
            if path == "/api/render-queue":
                queue = enqueue_render_runs(list(body.get("run_ids") or []), body)
                return self._json({"queue": queue}, 202)
            match = re.fullmatch(r"/api/topics/([^/]+)/prepare", path)
            if match:
                return self._json(_prepare_topic(match.group(1), bool(body.get("force"))))
            match = re.fullmatch(r"/api/topics/([^/]+)/status", path)
            if match:
                return self._json(update_topic_status(match.group(1), str(body.get("status", ""))))
            match = re.fullmatch(r"/api/runs/([^/]+)/execute", path)
            if match:
                return self._json({"run": execute_run(match.group(1), body)}, 202)
            match = re.fullmatch(r"/api/runs/([^/]+)/reset", path)
            if match:
                return self._json({"run": reset_run_from_step(match.group(1), int(body.get("step", 1)))})
            match = re.fullmatch(r"/api/runs/([^/]+)/models", path)
            if match:
                return self._json({"run": update_run_models(match.group(1), body)})
            match = re.fullmatch(r"/api/runs/([^/]+)/scenes/([^/]+)/regenerate", path)
            if match:
                body.update({"from_step": 5, "stop_after_step": 8, "target_scene_id": match.group(2), "force_paid_api": True})
                return self._json({"run": execute_run(match.group(1), body)}, 202)
            match = re.fullmatch(r"/api/runs/([^/]+)/chapters/([^/]+)/repair", path)
            if match:
                return self._json({"run": repair_chapter_run(match.group(1), match.group(2), body)}, 202)
            match = re.fullmatch(r"/api/runs/([^/]+)/motion-chapters/([^/]+)/regenerate", path)
            if match:
                return self._json({"run": regenerate_motion_chapter(match.group(1), match.group(2), body)}, 202)
            match = re.fullmatch(r"/api/runs/([^/]+)/motion-shots/([^/]+)/regenerate", path)
            if match:
                return self._json({"run": regenerate_motion_chapter(match.group(1), match.group(2), body)}, 202)
            match = re.fullmatch(r"/api/runs/([^/]+)/motion-beats/([^/]+)/regenerate", path)
            if match:
                return self._json({"run": regenerate_motion_chapter(match.group(1), match.group(2), body)}, 202)
            match = re.fullmatch(r"/api/runs/([^/]+)/render", path)
            if match:
                return self._json({"run": render_run(match.group(1), body)}, 202)
            match = re.fullmatch(r"/api/runs/([^/]+)/youtube-assets", path)
            if match:
                return self._json({"run": generate_youtube_assets(match.group(1), body)}, 202)
            match = re.fullmatch(r"/api/runs/([^/]+)/preview", path)
            if match:
                result = start_motion_preview(match.group(1))
                return self._json({"preview": result, "run": run_detail(match.group(1))}, 202)
            match = re.fullmatch(r"/api/runs/([^/]+)/lesson-review/run", path)
            if match:
                return self._json({"run": start_motion_lesson_review(match.group(1), body)}, 202)
            match = re.fullmatch(r"/api/runs/([^/]+)/lesson-review/approve", path)
            if match:
                return self._json({"report": approve_motion_lesson_review(match.group(1))})
            match = re.fullmatch(r"/api/runs/([^/]+)/stop", path)
            if match:
                return self._json({"run": stop_run(match.group(1))})
            raise FileNotFoundError(path)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return
        except Exception as exc:  # noqa: BLE001
            self._error(exc)

    def do_DELETE(self) -> None:  # noqa: N802
        try:
            path = urlparse(self.path).path
            match = re.fullmatch(r"/api/runs/([^/]+)", path)
            if match:
                return self._json(delete_run(match.group(1)))
            raise FileNotFoundError(path)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return
        except Exception as exc:  # noqa: BLE001
            self._error(exc)


def build_server(host: str = "127.0.0.1", port: int = 8765, *, quiet: bool = False) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), StudioHandler)
    server.quiet = quiet  # type: ignore[attr-defined]
    return server


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Physics Production Studio.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    server = build_server(args.host, args.port, quiet=args.quiet)
    _ensure_render_queue_worker()
    print(f"Physics Production Studio: http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStudio stopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
