from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sqlite3
import subprocess
import sys
import threading
from collections import Counter, defaultdict
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from video_engine.cli import TOPIC_ORDER, VALID_STATES


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

STEP_NAMES = ("Inputs", "Script", "Audio", "Timing", "Scenes", "Validate", "Preview", "QA")
PAID_STEPS = {2, 3, 5}
RUN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,95}$")
TOPIC_REF_RE = re.compile(r"^\d+(?:\.\d+){1,2}$")
SCENE_ID_RE = re.compile(r"^scene_\d{2,3}$")
MODEL_PROVIDERS = {"configured", "gemini", "anthropic"}
AUDIO_PROVIDERS = {"gemini", "elevenlabs"}
RENDER_QUALITIES = {"draft", "standard", "high"}

_processes: dict[str, subprocess.Popen[str]] = {}
_process_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
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
        "input.json",
        "narration.json",
        "audio_generation.json",
        "audio_timing.json",
        "scene_plan_v3.json",
        "validation/plan_validation_v3.json",
        "preview_manifest_v3.json",
        "generation_summary.json",
    )
    completed = 0
    for index, marker in enumerate(markers, 1):
        if (run_path / marker).exists():
            completed = index
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
        "settings": {},
        "error": None,
    }


def _load_meta(run_id: str) -> dict[str, Any]:
    run_path = _run_dir(run_id)
    if not run_path.exists():
        raise FileNotFoundError(run_id)
    return _read_json(_meta_path(run_id)) or _synthesized_meta(run_path)


def _save_meta(meta: dict[str, Any]) -> dict[str, Any]:
    meta["updated_at"] = _now()
    _write_json(_meta_path(meta["id"]), meta)
    return meta


def _artifact_snapshot(run_id: str) -> dict[str, Any]:
    run_path = _run_dir(run_id)
    manifest = _read_json(run_path / "preview_manifest_v3.json", {}) or {}
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
        }
        for scene in scenes_payload.get("scenes", [])
    ]
    files = []
    for relative in (
        "input.json", "story_skeleton.json", "narration.json", "voiceover.mp3", "audio_timing.json",
        "scene_plan_v3.json", "preview_manifest_v3.json", "generation_summary.json", "render_report.json",
    ):
        if (run_path / relative).exists():
            files.append(relative)
    return {
        "files": files,
        "scenes": scenes,
        "preview_url": f"/artifacts/runs/{run_id}/{master}" if master else None,
        "mp4_url": f"/artifacts/runs/{run_id}/{Path(output).relative_to(run_path)}" if output and Path(output).is_relative_to(run_path) else None,
        "summary": _read_json(run_path / "generation_summary.json", {}) or {},
        "validation": _read_json(run_path / "validation" / "plan_validation_v3.json", {}) or {},
    }


def run_detail(run_id: str) -> dict[str, Any]:
    meta = _load_meta(run_id)
    meta["current_step"] = max(int(meta.get("current_step", 0)), _infer_step(_run_dir(run_id)))
    meta["artifacts"] = _artifact_snapshot(run_id)
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
    command = [sys.executable, "-m", "video_engine.cli", "prepare-topic", topic_ref]
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
    paid = _paid_range(from_step, stop_after_step)
    confirmed = bool(request.get("confirm_paid_api", settings.get("confirm_paid_api", False)))
    if paid and not confirmed:
        raise PermissionError("Steps 2, 3, and 5 require explicit paid-API confirmation")
    facts_path = Path(meta["facts_path"])
    if not facts_path.is_absolute():
        facts_path = REPO_ROOT / facts_path
    if not facts_path.exists():
        raise FileNotFoundError(facts_path)
    provider = str(settings.get("model_provider", "gemini"))
    audio_provider = str(settings.get("audio_provider", "gemini"))
    if provider not in MODEL_PROVIDERS:
        raise ValueError("Unsupported model provider")
    if audio_provider not in AUDIO_PROVIDERS:
        raise ValueError("Unsupported audio provider")
    command = [
        sys.executable,
        str(TEMPLATE_LAB_ROOT / "scripts" / "mav_generate.py"),
        "--run-id", meta["id"],
        "--facts", str(facts_path),
        "--duration", str(float(settings.get("duration", 480))),
        "--model-provider", provider,
        "--audio-provider", audio_provider,
        "--from-step", str(from_step),
        "--stop-after-step", str(stop_after_step),
    ]
    if paid:
        command.extend(["--use-model", "--confirm-paid-api"])
    if request.get("force_paid_api"):
        command.append("--force-paid-api")
    scene_id = request.get("target_scene_id")
    if scene_id:
        if not SCENE_ID_RE.fullmatch(str(scene_id)):
            raise ValueError("Invalid scene ID")
        command.extend(["--v3-scene-id", str(scene_id)])
    env = os.environ.copy()
    instruction = str(request.get("custom_instruction", "")).strip()
    if instruction:
        env["MAV_SCENE_REGEN_INSTRUCTION" if scene_id else "MAV_STEP_REGEN_INSTRUCTION"] = instruction
    concurrency = int(settings.get("scene_concurrency", 1))
    env["MAV_V3_SCENE_CONCURRENCY"] = str(max(1, min(concurrency, 8)))
    return command, env


def _start_process(run_id: str, command: list[str], env: dict[str, str], *, mode: str, target_step: int) -> dict[str, Any]:
    with _process_lock:
        existing = _processes.get(run_id)
        if existing and existing.poll() is None:
            raise RuntimeError("This run already has an active process")
    meta = _load_meta(run_id)
    meta.update({"status": "rendering" if mode == "render" else "running", "error": None})
    _save_meta(meta)
    _append_log(run_id, f"Starting {mode}: {' '.join(command[:3])} …")

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
                latest["status"] = "rendered" if mode == "render" else "completed"
                latest["current_step"] = max(int(latest.get("current_step", 0)), target_step)
                _append_log(run_id, f"{mode.title()} completed")
            else:
                latest["status"] = "failed"
                latest["error"] = f"{mode.title()} exited with code {return_code}"
                _append_log(run_id, latest["error"])
            _save_meta(latest)
        except Exception as exc:  # noqa: BLE001
            latest = _load_meta(run_id)
            latest.update({"status": "failed", "error": str(exc)})
            _save_meta(latest)
            _append_log(run_id, f"Failed: {exc}")
        finally:
            with _process_lock:
                if _processes.get(run_id) is process:
                    _processes.pop(run_id, None)

    threading.Thread(target=worker, daemon=True, name=f"studio-{mode}-{run_id}").start()
    return run_detail(run_id)


def create_run(payload: dict[str, Any]) -> dict[str, Any]:
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
    settings = {
        "duration": max(30, min(float(payload.get("duration", 480)), 1800)),
        "model_provider": payload.get("model_provider", "gemini"),
        "audio_provider": payload.get("audio_provider", "gemini"),
        "scene_concurrency": max(1, min(int(payload.get("scene_concurrency", 1)), 8)),
        "confirm_paid_api": bool(payload.get("confirm_paid_api", False)),
    }
    meta = {
        "id": run_id,
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
    command, env = build_generation_command(meta, payload)
    return _start_process(run_id, command, env, mode="generation", target_step=int(payload.get("stop_after_step", 8)))


def render_run(run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    _load_meta(run_id)
    quality = str(payload.get("quality", "standard"))
    fps = int(payload.get("fps", 30))
    workers = int(payload.get("workers", 1))
    if quality not in RENDER_QUALITIES or fps not in {24, 25, 30, 50, 60} or not 1 <= workers <= 8:
        raise ValueError("Invalid render settings")
    command = [
        sys.executable,
        str(TEMPLATE_LAB_ROOT / "scripts" / "mav_render.py"),
        "--run-id", run_id,
        "--quality", quality,
        "--fps", str(fps),
        "--workers", str(workers),
    ]
    return _start_process(run_id, command, os.environ.copy(), mode="render", target_step=8)


def stop_run(run_id: str) -> dict[str, Any]:
    meta = _load_meta(run_id)
    with _process_lock:
        process = _processes.get(run_id)
        if process and process.poll() is None:
            process.terminate()
    meta.update({"status": "stopped", "error": None})
    _append_log(run_id, "Stop requested")
    return _save_meta(meta)


def update_topic_status(topic_ref: str, status: str) -> dict[str, Any]:
    topic_ref = _require_topic_ref(topic_ref)
    if status not in VALID_STATES:
        raise ValueError("Invalid coverage status")
    result = subprocess.run(
        [sys.executable, "-m", "video_engine.cli", "set-status", "--topic", topic_ref, "--status", status],
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
        data = path.read_bytes()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "public, max-age=3600" if cache else "no-cache")
        self.end_headers()
        self.wfile.write(data)

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
        self._json({"error": str(exc)}, int(status))

    def do_GET(self) -> None:  # noqa: N802
        try:
            path = urlparse(self.path).path
            if path == "/api/dashboard":
                return self._json(dashboard_payload())
            if path == "/api/assets":
                return self._json(_read_json(ASSETS_PATH, {"scenes": []}))
            if path == "/api/runs":
                return self._json({"runs": list_runs()})
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
        except Exception as exc:  # noqa: BLE001
            self._error(exc)

    def do_POST(self) -> None:  # noqa: N802
        try:
            path = urlparse(self.path).path
            body = self._body()
            if path == "/api/runs":
                return self._json({"run": create_run(body)}, 201)
            match = re.fullmatch(r"/api/topics/([^/]+)/prepare", path)
            if match:
                return self._json(_prepare_topic(match.group(1), bool(body.get("force"))))
            match = re.fullmatch(r"/api/topics/([^/]+)/status", path)
            if match:
                return self._json(update_topic_status(match.group(1), str(body.get("status", ""))))
            match = re.fullmatch(r"/api/runs/([^/]+)/execute", path)
            if match:
                return self._json({"run": execute_run(match.group(1), body)}, 202)
            match = re.fullmatch(r"/api/runs/([^/]+)/scenes/([^/]+)/regenerate", path)
            if match:
                body.update({"from_step": 5, "stop_after_step": 8, "target_scene_id": match.group(2), "force_paid_api": True})
                return self._json({"run": execute_run(match.group(1), body)}, 202)
            match = re.fullmatch(r"/api/runs/([^/]+)/render", path)
            if match:
                return self._json({"run": render_run(match.group(1), body)}, 202)
            match = re.fullmatch(r"/api/runs/([^/]+)/stop", path)
            if match:
                return self._json({"run": stop_run(match.group(1))})
            raise FileNotFoundError(path)
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
