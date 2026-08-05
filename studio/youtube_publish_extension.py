"""Add local YouTube channel management and publishing queues to MAV Studio."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_INSTALLED = False
_LOCK = threading.RLock()
_JOBS: dict[str, dict[str, Any]] = {}
_SERVER: Any = None
DEFAULT_COURSE_PLAYLIST_TITLE = "Cambridge IGCSE Physics (0625) — Complete Course"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _youtube_root(server: Any) -> Path:
    return server.REPO_ROOT / ".youtube"


def _profiles_path(server: Any) -> Path:
    return _youtube_root(server) / "profiles.json"


def _jobs_path(server: Any) -> Path:
    return _youtube_root(server) / "studio-jobs.json"


def _publisher_path(server: Any) -> Path:
    return server.TEMPLATE_LAB_ROOT / "scripts" / "mav_youtube_publish.py"


def _read_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_private_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass
    temporary = path.with_suffix(path.suffix + f".tmp-{os.getpid()}-{threading.get_ident()}")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)


def _load_profiles(server: Any) -> dict[str, Any]:
    payload = _read_json(_profiles_path(server), {"version": 1, "selected_profile_id": None, "profiles": []})
    payload.setdefault("version", 1)
    payload.setdefault("selected_profile_id", None)
    payload.setdefault("profiles", [])
    if not payload["profiles"]:
        channel = _read_json(_youtube_root(server) / "channel.json", {})
        token = _youtube_root(server) / "token.json"
        if token.is_file() and channel.get("channel_id"):
            profile = {
                "id": _profile_id(str(channel["channel_id"])),
                "channel_id": str(channel["channel_id"]),
                "channel_title": str(channel.get("channel_title") or "YouTube channel"),
                "label": str(channel.get("channel_title") or "YouTube channel"),
                "token_path": str(token.relative_to(server.REPO_ROOT)),
                "status": "authorized",
                "authorized_at": channel.get("authorized_at") or _now(),
                "last_verified_at": _now(),
            }
            payload["profiles"] = [profile]
            payload["selected_profile_id"] = profile["id"]
            _write_private_json(_profiles_path(server), payload)
    return payload


def _save_profiles(server: Any, payload: dict[str, Any]) -> None:
    _write_private_json(_profiles_path(server), payload)


def _profile_id(channel_id: str) -> str:
    suffix = re.sub(r"[^a-zA-Z0-9]", "", channel_id)[-12:].lower()
    return f"channel-{suffix or uuid.uuid4().hex[:12]}"


def _require_profile(server: Any, profile_id: str) -> dict[str, Any]:
    profiles = _load_profiles(server)
    profile = next((item for item in profiles["profiles"] if item.get("id") == profile_id), None)
    if not profile:
        raise ValueError("Choose an authorized YouTube channel")
    token_path = (server.REPO_ROOT / str(profile.get("token_path") or "")).resolve()
    root = _youtube_root(server).resolve()
    if token_path != root and root not in token_path.parents:
        raise ValueError("Invalid YouTube token path")
    if not token_path.is_file():
        raise FileNotFoundError("The selected channel token is missing; reauthorize the channel")
    return {**profile, "resolved_token_path": token_path}


def select_profile(server: Any, profile_id: str) -> dict[str, Any]:
    _require_profile(server, profile_id)
    with _LOCK:
        payload = _load_profiles(server)
        payload["selected_profile_id"] = profile_id
        _save_profiles(server, payload)
    return youtube_dashboard_payload(server)


def _video_path(run_path: Path) -> Path | None:
    for relative in (
        "motion_canvas/final.mp4",
        "renders/master_v3.mp4",
        "renders/master_direct_html.mp4",
    ):
        candidate = run_path / relative
        if candidate.is_file():
            return candidate
    return None


def _run_topic_ref(run_path: Path) -> str | None:
    for relative in ("studio_run.json", "input.json", "reel_pack.json"):
        payload = _read_json(run_path / relative, {})
        topic_ref = str(payload.get("topic_ref") or "").strip()
        if topic_ref:
            return topic_ref
        topic = str(payload.get("topic") or "").strip()
        match = re.match(r"^(\d+(?:\.\d+)+)\b", topic)
        if match:
            return match.group(1)
    return None


def _longform_candidates(server: Any) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    if not server.RUNS_ROOT.is_dir():
        return candidates
    for run_path in sorted(server.RUNS_ROOT.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True):
        if not run_path.is_dir() or (run_path / "reel_pack.json").is_file():
            continue
        metadata_path = run_path / "youtube" / "metadata.json"
        video = _video_path(run_path)
        if not video and not metadata_path.is_file():
            continue
        metadata = _read_json(metadata_path, {})
        thumbnail = run_path / "youtube" / "thumbnail.jpg"
        receipt = _read_json(run_path / "youtube" / "upload-result.json", {})
        candidates.append(
            {
                "key": f"longform:{run_path.name}",
                "kind": "longform",
                "run_id": run_path.name,
                "topic_ref": _run_topic_ref(run_path),
                "title": metadata.get("video_title") or metadata.get("title") or run_path.name,
                "video_ready": bool(video),
                "metadata_ready": metadata_path.is_file(),
                "thumbnail_ready": thumbnail.is_file(),
                "ready": bool(video and metadata_path.is_file()),
                "video_size": video.stat().st_size if video else 0,
                "privacy": receipt.get("privacy"),
                "upload_status": receipt.get("status") or "not_uploaded",
                "youtube_url": receipt.get("url"),
                "uploaded_channel_id": receipt.get("channel_id"),
            }
        )
    return candidates


def _reel_candidates(server: Any) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    if not server.RUNS_ROOT.is_dir():
        return candidates
    for run_path in sorted(server.RUNS_ROOT.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True):
        if not run_path.is_dir() or not (run_path / "reel_pack.json").is_file():
            continue
        pack = _read_json(run_path / "reel_pack.json", {})
        asset_manifest = _read_json(run_path / "youtube" / "reel-assets.json", {})
        generated_by_id = {
            str(item.get("reel_id")): item
            for item in asset_manifest.get("reels", [])
            if isinstance(item, dict) and item.get("reel_id")
        }
        for reel in pack.get("reels", []):
            reel_id = str(reel.get("reel_id") or "")
            if not reel_id:
                continue
            generated = generated_by_id.get(reel_id, {})
            metadata_path = run_path / str(generated.get("metadata") or f"youtube/reels/{reel_id}/metadata.json")
            video = run_path / str(generated.get("youtube_video") or f"youtube/reels/{reel_id}/youtube-short.mp4")
            thumbnail = run_path / str(generated.get("thumbnail") or f"youtube/reels/{reel_id}/thumbnail.jpg")
            metadata = _read_json(metadata_path, {})
            receipt = _read_json(metadata_path.parent / "upload-result.json", {})
            if not video.is_file() and not metadata_path.is_file():
                continue
            candidates.append(
                {
                    "key": f"reel:{run_path.name}:{reel_id}",
                    "kind": "reel",
                    "run_id": run_path.name,
                    "topic_ref": str(pack.get("topic_ref") or _run_topic_ref(run_path) or "") or None,
                    "reel_id": reel_id,
                    "title": metadata.get("video_title") or metadata.get("title") or reel.get("working_title") or reel_id,
                    "video_ready": video.is_file(),
                    "metadata_ready": metadata_path.is_file(),
                    "thumbnail_ready": thumbnail.is_file(),
                    "thumbnail_mode": "embedded_final_frame",
                    "ready": video.is_file() and metadata_path.is_file(),
                    "video_size": video.stat().st_size if video.is_file() else 0,
                    "privacy": receipt.get("privacy"),
                    "upload_status": receipt.get("status") or "not_uploaded",
                    "youtube_url": receipt.get("url"),
                    "uploaded_channel_id": receipt.get("channel_id"),
                }
            )
    return candidates


def _public_jobs(server: Any) -> list[dict[str, Any]]:
    stored = _read_json(_jobs_path(server), {"jobs": []}).get("jobs", [])
    with _LOCK:
        merged = {str(item.get("id")): item for item in stored if item.get("id")}
        merged.update(_JOBS)
    return sorted(merged.values(), key=lambda item: item.get("created_at", ""), reverse=True)[:30]


def youtube_dashboard_payload(server: Any) -> dict[str, Any]:
    profiles = _load_profiles(server)
    selected = next(
        (item for item in profiles["profiles"] if item.get("id") == profiles.get("selected_profile_id")),
        None,
    )
    return {
        "project": {"id": "capture-3494f", "name": "Capture", "youtube_api_enabled": True},
        "client_ready": (_youtube_root(server) / "client_secret.json").is_file(),
        "selected_profile_id": profiles.get("selected_profile_id"),
        "selected_channel": selected,
        "profiles": profiles["profiles"],
        "candidates": {
            "longform": _longform_candidates(server),
            "reels": _reel_candidates(server),
        },
        "jobs": _public_jobs(server),
        "defaults": {
            "privacy": "private",
            "category_id": "27",
            "made_for_kids": False,
            "notify_subscribers": False,
            "auto_organize_course": True,
            "course_playlist_title": DEFAULT_COURSE_PLAYLIST_TITLE,
        },
    }


def _save_jobs(server: Any) -> None:
    with _LOCK:
        existing = _read_json(_jobs_path(server), {"jobs": []}).get("jobs", [])
        merged = {str(item.get("id")): item for item in existing if item.get("id")}
        merged.update(_JOBS)
        jobs = sorted(merged.values(), key=lambda item: item.get("created_at", ""), reverse=True)[:100]
        _write_private_json(_jobs_path(server), {"version": 1, "jobs": jobs})


def _update_job(server: Any, job_id: str, **values: Any) -> None:
    with _LOCK:
        if job_id not in _JOBS:
            return
        _JOBS[job_id].update(values)
        _JOBS[job_id]["updated_at"] = _now()
    _save_jobs(server)


def _last_json(text: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    positions = [match.start() for match in re.finditer(r"\{", text)]
    for start in reversed(positions):
        try:
            value, _end = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise RuntimeError("The YouTube command returned no result")


def _safe_error(result: subprocess.CompletedProcess[str]) -> str:
    message = (result.stderr or result.stdout or "YouTube command failed").strip()
    return message[-4000:]


def _authorization_worker(
    server: Any,
    job_id: str,
    *,
    label: str,
    existing_profile: dict[str, Any] | None,
) -> None:
    root = _youtube_root(server)
    client_secrets = root / "client_secret.json"
    backup_path: Path | None = None
    if existing_profile:
        token_path = Path(existing_profile["resolved_token_path"])
        if token_path.is_file():
            backup_path = token_path.with_suffix(token_path.suffix + f".backup-{job_id}")
            shutil.copy2(token_path, backup_path)
    else:
        token_path = root / "tokens" / f"authorization-{job_id}.json"
    command = [
        server.PYTHON_EXECUTABLE,
        str(_publisher_path(server)),
        "--authorize-only",
        "--reauthorize",
        "--client-secrets",
        str(client_secrets),
        "--token",
        str(token_path),
    ]
    if existing_profile:
        command.extend(["--expected-channel-id", str(existing_profile["channel_id"])])
    _update_job(server, job_id, status="waiting_for_browser", message="Choose the YouTube channel in your browser")
    result = subprocess.run(command, cwd=server.REPO_ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        if backup_path and backup_path.is_file():
            shutil.copy2(backup_path, token_path)
        _update_job(server, job_id, status="failed", error=_safe_error(result), message="Authorization failed")
        if backup_path:
            backup_path.unlink(missing_ok=True)
        return
    try:
        authorization = _last_json(result.stdout)
        channel_id = str(authorization.get("channel_id") or "")
        channel_title = str(authorization.get("channel_title") or "YouTube channel")
        if not channel_id:
            raise RuntimeError("Google returned no YouTube channel")
        profile_id = existing_profile["id"] if existing_profile else _profile_id(channel_id)
        profile = {
            "id": profile_id,
            "channel_id": channel_id,
            "channel_title": channel_title,
            "label": label or channel_title,
            "token_path": str(token_path.relative_to(server.REPO_ROOT)),
            "status": "authorized",
            "authorized_at": _now(),
            "last_verified_at": _now(),
        }
        with _LOCK:
            registry = _load_profiles(server)
            registry["profiles"] = [
                item for item in registry["profiles"]
                if item.get("id") != profile_id and item.get("channel_id") != channel_id
            ]
            registry["profiles"].append(profile)
            registry["selected_profile_id"] = profile_id
            _save_profiles(server, registry)
        _update_job(
            server,
            job_id,
            status="completed",
            message=f"Authorized {channel_title}",
            channel_id=channel_id,
            channel_title=channel_title,
            profile_id=profile_id,
            completed_at=_now(),
        )
    except Exception as exc:  # noqa: BLE001
        if backup_path and backup_path.is_file():
            shutil.copy2(backup_path, token_path)
        _update_job(server, job_id, status="failed", error=str(exc), message="Authorization result was invalid")
    finally:
        if backup_path:
            backup_path.unlink(missing_ok=True)


def start_authorization(server: Any, request: dict[str, Any]) -> dict[str, Any]:
    if not (_youtube_root(server) / "client_secret.json").is_file():
        raise FileNotFoundError("YouTube OAuth client credential is missing")
    label = str(request.get("label") or "").strip()[:80]
    profile_id = str(request.get("profile_id") or "").strip()
    existing = _require_profile(server, profile_id) if profile_id else None
    job_id = f"auth-{uuid.uuid4().hex[:12]}"
    job = {
        "id": job_id,
        "type": "authorization",
        "status": "starting",
        "message": "Opening Google authorization",
        "created_at": _now(),
        "updated_at": _now(),
        "profile_id": profile_id or None,
    }
    with _LOCK:
        _JOBS[job_id] = job
    _save_jobs(server)
    threading.Thread(
        target=_authorization_worker,
        args=(server, job_id),
        kwargs={"label": label, "existing_profile": existing},
        daemon=True,
        name=f"youtube-auth-{job_id}",
    ).start()
    return job


def _candidate_lookup(server: Any) -> dict[str, dict[str, Any]]:
    all_items = [*_longform_candidates(server), *_reel_candidates(server)]
    return {item["key"]: item for item in all_items}


def _item_paths(server: Any, item: dict[str, Any]) -> tuple[Path, Path, Path | None]:
    run_path = server._run_dir(str(item["run_id"]))
    if item["kind"] == "longform":
        video = _video_path(run_path)
        if not video:
            raise FileNotFoundError(f"Rendered MP4 is missing for {item['run_id']}")
        metadata = run_path / "youtube" / "metadata.json"
        thumbnail = run_path / "youtube" / "thumbnail.jpg"
        return video, metadata, thumbnail if thumbnail.is_file() else None
    reel_id = str(item.get("reel_id") or "")
    manifest = _read_json(run_path / "youtube" / "reel-assets.json", {})
    generated = next((entry for entry in manifest.get("reels", []) if entry.get("reel_id") == reel_id), None)
    if not generated:
        raise FileNotFoundError(f"YouTube assets are missing for {item['run_id']} {reel_id}")
    video = run_path / str(generated.get("youtube_video") or "")
    metadata = run_path / str(generated.get("metadata") or "")
    # Shorts use the generated one-second final frame as their selectable cover.
    return video, metadata, None


def _full_lesson_video_id(server: Any, item: dict[str, Any]) -> str | None:
    """Resolve a Reel's corresponding uploaded long-form lesson by topic reference."""
    if item.get("kind") != "reel" or not item.get("topic_ref"):
        return None
    for lesson in _longform_candidates(server):
        if lesson.get("topic_ref") != item.get("topic_ref"):
            continue
        receipt = _read_json(
            server._run_dir(str(lesson["run_id"])) / "youtube" / "upload-result.json",
            {},
        )
        video_id = str(receipt.get("video_id") or "").strip()
        if receipt.get("status") == "uploaded" and video_id:
            return video_id
    return None


def _publish_worker(
    server: Any,
    job_id: str,
    *,
    profile: dict[str, Any],
    items: list[dict[str, Any]],
    settings: dict[str, Any],
) -> None:
    results: list[dict[str, Any]] = []
    for index, item in enumerate(items, 1):
        _update_job(
            server,
            job_id,
            status="running",
            current=index,
            message=f"Publishing {item['title']}",
            results=results,
        )
        try:
            video, metadata, thumbnail = _item_paths(server, item)
            receipt_path = metadata.parent / "upload-result.json"
            existing_receipt = _read_json(receipt_path, {})
            if existing_receipt.get("status") == "uploaded":
                raise FileExistsError(f"{item['title']} already has an upload receipt")
            command = [
                server.PYTHON_EXECUTABLE,
                str(_publisher_path(server)),
                "--video",
                str(video),
                "--metadata",
                str(metadata),
                "--client-secrets",
                str(_youtube_root(server) / "client_secret.json"),
                "--token",
                str(profile["resolved_token_path"]),
                "--expected-channel-id",
                str(profile["channel_id"]),
                "--privacy",
                settings["privacy"],
                "--category-id",
                settings["category_id"],
                "--made-for-kids" if settings["made_for_kids"] else "--not-made-for-kids",
                "--content-kind",
                "short" if item["kind"] == "reel" else "longform",
                "--course-playlist-title",
                settings["course_playlist_title"],
                "--confirm-upload",
            ]
            if not settings.get("auto_organize_course", True):
                command.append("--skip-course-organization")
            full_lesson_video_id = _full_lesson_video_id(server, item)
            if full_lesson_video_id:
                command.extend(["--full-lesson-video-id", full_lesson_video_id])
            if thumbnail:
                command.extend(["--thumbnail", str(thumbnail)])
            if settings.get("publish_at"):
                command.extend(["--publish-at", settings["publish_at"]])
            for playlist_id in settings.get("playlist_ids", []):
                command.extend(["--playlist-id", playlist_id])
            if settings.get("notify_subscribers"):
                command.append("--notify-subscribers")
            if settings.get("post_first_comment"):
                command.append("--post-first-comment")
            result = subprocess.run(command, cwd=server.REPO_ROOT, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(_safe_error(result))
            receipt = _last_json(result.stdout)
            results.append(
                {
                    "key": item["key"],
                    "title": item["title"],
                    "status": "uploaded",
                    "video_id": receipt.get("video_id"),
                    "url": receipt.get("url"),
                }
            )
        except Exception as exc:  # noqa: BLE001
            results.append({"key": item["key"], "title": item["title"], "status": "failed", "error": str(exc)})
            _update_job(
                server,
                job_id,
                status="failed",
                current=index,
                results=results,
                error=str(exc),
                message=f"Publishing stopped at {item['title']}",
                completed_at=_now(),
            )
            return
    _update_job(
        server,
        job_id,
        status="completed",
        current=len(items),
        results=results,
        message=f"Published {len(items)} item{'s' if len(items) != 1 else ''}",
        completed_at=_now(),
    )


def start_publish_job(server: Any, request: dict[str, Any]) -> dict[str, Any]:
    if request.get("confirm_publish") is not True:
        raise PermissionError("Confirm the YouTube publish operation before starting")
    profile = _require_profile(server, str(request.get("profile_id") or ""))
    keys = [str(item) for item in request.get("item_keys", []) if str(item)]
    if not keys:
        raise ValueError("Select at least one long-form video or Reel")
    if len(keys) > 24:
        raise ValueError("A publish job can contain at most 24 items")
    lookup = _candidate_lookup(server)
    items: list[dict[str, Any]] = []
    for key in keys:
        item = lookup.get(key)
        if not item:
            raise ValueError(f"Unknown publishing item: {key}")
        if not item.get("ready"):
            raise ValueError(f"Publishing assets are incomplete for {item['title']}")
        if item.get("upload_status") == "uploaded":
            raise FileExistsError(f"{item['title']} is already uploaded")
        items.append(item)
    privacy = str(request.get("privacy") or "private")
    if privacy not in {"private", "unlisted", "public"}:
        raise ValueError("Invalid YouTube privacy setting")
    publish_at = str(request.get("publish_at") or "").strip() or None
    if publish_at and (privacy != "private" or len(items) != 1):
        raise ValueError("Scheduling requires one item with private visibility")
    playlist_ids = [str(value).strip() for value in request.get("playlist_ids", []) if str(value).strip()]
    settings = {
        "privacy": privacy,
        "publish_at": publish_at,
        "category_id": str(request.get("category_id") or "27"),
        "made_for_kids": bool(request.get("made_for_kids")),
        "notify_subscribers": bool(request.get("notify_subscribers")),
        "post_first_comment": bool(request.get("post_first_comment")),
        "playlist_ids": playlist_ids,
        "auto_organize_course": bool(request.get("auto_organize_course", True)),
        "course_playlist_title": str(
            request.get("course_playlist_title") or DEFAULT_COURSE_PLAYLIST_TITLE
        ).strip(),
    }
    if not settings["course_playlist_title"]:
        raise ValueError("Course playlist title cannot be empty")
    job_id = f"publish-{uuid.uuid4().hex[:12]}"
    job = {
        "id": job_id,
        "type": "publish",
        "status": "queued",
        "message": "Publish job queued",
        "created_at": _now(),
        "updated_at": _now(),
        "profile_id": profile["id"],
        "channel_id": profile["channel_id"],
        "channel_title": profile["channel_title"],
        "total": len(items),
        "current": 0,
        "items": [{"key": item["key"], "title": item["title"], "kind": item["kind"]} for item in items],
        "settings": settings,
        "results": [],
    }
    with _LOCK:
        _JOBS[job_id] = job
    _save_jobs(server)
    threading.Thread(
        target=_publish_worker,
        args=(server, job_id),
        kwargs={"profile": profile, "items": items, "settings": settings},
        daemon=True,
        name=f"youtube-publish-{job_id}",
    ).start()
    return job


def install(server: Any) -> None:
    """Patch the loaded Studio server with additive YouTube dashboard APIs."""
    global _INSTALLED, _SERVER
    if _INSTALLED or getattr(server, "_youtube_publish_extension_installed", False):
        return
    _INSTALLED = True
    _SERVER = server
    server._youtube_publish_extension_installed = True
    server.youtube_dashboard_payload = lambda: youtube_dashboard_payload(server)
    server.youtube_select_profile = lambda profile_id: select_profile(server, profile_id)
    server.youtube_start_authorization = lambda request: start_authorization(server, request)
    server.youtube_start_publish_job = lambda request: start_publish_job(server, request)

    original_do_get = server.StudioHandler.do_GET
    original_do_post = server.StudioHandler.do_POST

    def do_get(self: Any) -> None:
        path = urlparse(self.path).path
        if path == "/api/youtube/dashboard":
            try:
                return self._json(youtube_dashboard_payload(server))
            except Exception as exc:  # noqa: BLE001
                return self._error(exc)
        return original_do_get(self)

    def do_post(self: Any) -> None:
        path = urlparse(self.path).path
        try:
            if path == "/api/youtube/profiles/select":
                body = self._body()
                return self._json(select_profile(server, str(body.get("profile_id") or "")))
            if path == "/api/youtube/profiles/authorize":
                return self._json({"job": start_authorization(server, self._body())}, 202)
            if path == "/api/youtube/publish":
                return self._json({"job": start_publish_job(server, self._body())}, 202)
        except Exception as exc:  # noqa: BLE001
            return self._error(exc)
        return original_do_post(self)

    server.StudioHandler.do_GET = do_get
    server.StudioHandler.do_POST = do_post
