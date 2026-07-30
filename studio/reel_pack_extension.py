"""Additive Studio integration for standalone topic Reel packs.

The long-form Studio server remains authoritative.  This module is installed at
server startup and delegates every non-Reel-pack request to the original
implementation.
"""
from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from template_lab.reel_pack.common import create_pack, load_pack, read_json, reel_path, save_pack
from template_lab.reel_pack.pipeline import approve_reel, reject_reel, restore_reel
from template_lab.reel_pack.schema import CONTENT_PRODUCT, bounded_reel_count, reel_id, require_reel_id

FULL_LESSON_PRODUCT = "full-lesson"
_INSTALLED = False


def _is_pack_path(run_path: Path) -> bool:
    return (run_path / "reel_pack.json").exists()


def _is_pack_meta(meta: dict[str, Any], server: Any) -> bool:
    return (
        str(meta.get("content_product") or (meta.get("settings") or {}).get("content_product") or "")
        == CONTENT_PRODUCT
        or _is_pack_path(server._run_dir(str(meta.get("id") or "")))
    )


def _facts_payload(server: Any, facts_path: Path) -> dict[str, Any]:
    payload = server._read_json(facts_path, {}) or {}
    if isinstance(payload, list):
        return {"facts": payload, "physics_context": {}, "objective_ids": []}
    return payload if isinstance(payload, dict) else {"facts": [], "physics_context": {}, "objective_ids": []}


def _child_source_relative(child: Path) -> str | None:
    for relative in (
        "motion_canvas/reels/reel_001.tsx",
        "motion_canvas/chapters/reel_001.tsx",
    ):
        if (child / relative).exists():
            return relative
    return None


def _pack_artifacts(server: Any, run_id: str) -> dict[str, Any]:
    run_path = server._run_dir(run_id)
    pack = load_pack(run_path)
    summary = server._read_json(run_path / "generation_summary.json", {}) or {}
    review = server._read_json(run_path / "pack-review.json", {}) or {}
    evidence = server._read_json(run_path / "review" / "evidence.json", {}) or {}
    publishing = server._read_json(run_path / "publishing_manifest.json", {}) or {}
    findings_by_reel: dict[str, list[dict[str, Any]]] = {}
    for finding in review.get("findings", []) if isinstance(review.get("findings"), list) else []:
        findings_by_reel.setdefault(str(finding.get("reel_id") or ""), []).append(finding)

    reels: list[dict[str, Any]] = []
    files: list[str] = []
    for relative in (
        "input.json",
        "reel_pack.json",
        "pack_plan.json",
        "pack-review.json",
        "publishing_manifest.json",
        "generation_summary.json",
        "review/evidence.json",
        "costs/summary.json",
        "costs/model_usage.json",
    ):
        if (run_path / relative).exists():
            files.append(relative)

    narration = read_json(run_path / "narration.json", {}) or {}
    paragraphs = {str(item.get("id")): item for item in narration.get("paragraphs", [])}
    motion_manifest = read_json(run_path / "motion_canvas" / "manifest.json", {}) or {}
    preview_url = (
        server._preview_url
        if server._preview_run_id == run_id
        and server._preview_process
        and server._preview_process.poll() is None
        else None
    )
    for record in pack.get("reels", []):
        parent_id = str(record.get("reel_id") or "")
        if not parent_id:
            continue
        paragraph = paragraphs.get(parent_id, {})
        brief = record
        script = paragraph
        audio = read_json(run_path / "audio_generation.json", {}) or {}
        validation = read_json(run_path / "validation-report.json", {}) or {}
        source_relative = f"motion_canvas/reels/{parent_id}.tsx"
        preview_relative = "motion_canvas/preview/contact-sheet.png"
        audio_relative = f"audio_chunks/{parent_id}/audio.wav"
        video_relative = f"motion_canvas/renders/{parent_id}.mp4"
        evidence_payload = read_json(run_path / "review" / "evidence" / parent_id / "evidence.json", {}) or {}
        timeline_unit = next((item for item in motion_manifest.get("reels", []) if item.get("scene_id") == parent_id), {})
        reels.append(
            {
                **record,
                "reel_id": parent_id,
                "title": script.get("title") or brief.get("working_title") or parent_id,
                "hook": brief.get("hook") or script.get("hook") or "",
                "learning_payoff": brief.get("learning_payoff") or "",
                "narration": script.get("narration") or script.get("text") or "",
                "duration": timeline_unit.get("duration") or record.get("target_duration_seconds"),
                "absolute_start": timeline_unit.get("absolute_start"),
                "absolute_end": timeline_unit.get("absolute_end"),
                "render_absolute_start": timeline_unit.get("render_absolute_start"),
                "render_absolute_end": timeline_unit.get("render_absolute_end"),
                "render_start_frame": timeline_unit.get("render_start_frame"),
                "render_end_frame": timeline_unit.get("render_end_frame"),
                "source_ready": (run_path / source_relative).exists(),
                "source": source_relative if (run_path / source_relative).exists() else None,
                "audio": audio_relative if (run_path / audio_relative).exists() else None,
                "preview": preview_relative if (run_path / preview_relative).exists() else None,
                "video": video_relative if (run_path / video_relative).exists() else None,
                "validation": validation,
                "findings": findings_by_reel.get(parent_id, []),
                "evidence_frames": evidence_payload.get("reels", [{}])[0].get("frames", [])
                if evidence_payload.get("reels")
                else [],
            }
        )
        for relative in (
            "narration.json",
            "voiceover.mp3",
            "audio_timing.json",
            "audio_word_timestamps.json",
            source_relative,
            preview_relative,
            video_relative,
        ):
            if (run_path / relative).exists():
                files.append(relative)

    return {
        "content_product": CONTENT_PRODUCT,
        "render_profile": pack.get("render_profile"),
        "animation_mode": "motion-canvas",
        "pack": pack,
        "summary": summary,
        "reels": reels,
        "chapters": [],
        "scenes": [],
        "files": files,
        "pack_review": review,
        "review_contact_sheets": list(evidence.get("contact_sheets") or []),
        "publishing_manifest": publishing,
        "preview_url": preview_url,
        "validation_preview_url": (
            f"/artifacts/runs/{run_id}/motion_canvas/preview/contact-sheet.png"
            if (run_path / "motion_canvas" / "preview" / "contact-sheet.png").exists()
            else None
        ),
        "mp4_url": None,
        "cost_summary": server._read_json(run_path / "costs" / "summary.json", {}) or {},
        "usage_records": (server._read_json(run_path / "costs" / "model_usage.json", {}) or {}).get("records", []),
        "direct_html_cost_summary": {},
        "routing_summary": {},
                "asset_shortlist": {},
    }


def _task_environment(server: Any, *, settings: dict[str, Any], request: dict[str, Any]) -> dict[str, str]:
    task_models = server._validate_task_models(request.get("task_models", settings.get("task_models", {})))
    env = os.environ.copy()
    provider = str(settings.get("model_provider", "configured"))
    if provider != "configured":
        catalog = {item["task"]: item for item in server.model_map_payload()["tasks"]}
        for task in ("script_structure", "script_writing"):
            config = catalog[task]
            if provider not in config["provider_models"]:
                raise ValueError(f"{provider} is not available for {task}")
            prefix = f"MAV_{task.upper()}"
            env[f"{prefix}_PROVIDER"] = provider
            env[f"{prefix}_MODEL"] = config["provider_models"][provider]
    for task, selection in task_models.items():
        if task == "audio_generation":
            env["GEMINI_TTS_MODEL" if selection["provider"] == "gemini" else "ELEVENLABS_MODEL_ID"] = selection["model"]
            continue
        prefix = f"MAV_{task.upper()}"
        env[f"{prefix}_PROVIDER"] = selection["provider"]
        env[f"{prefix}_MODEL"] = selection["model"]
        if selection["provider"] in {"codex", "grok"}:
            env[f"{prefix}_REASONING_EFFORT"] = selection.get("reasoning_effort", "low")
    return env


def install(server: Any) -> None:
    """Patch the loaded Studio server with additive Reel-pack behavior."""
    global _INSTALLED
    if _INSTALLED or getattr(server, "_reel_pack_extension_installed", False):
        return
    _INSTALLED = True
    server._reel_pack_extension_installed = True

    original_infer_step = server._infer_step
    original_synthesized_meta = server._synthesized_meta
    original_normalized_meta = server._normalized_meta
    original_artifact_snapshot = server._artifact_snapshot
    original_create_run = server.create_run
    original_build_generation_command = server.build_generation_command
    original_reset_run_from_step = server.reset_run_from_step
    original_do_post = server.StudioHandler.do_POST

    def infer_step(run_path: Path) -> int:
        if _is_pack_path(run_path):
            pack = server._read_json(run_path / "reel_pack.json", {}) or {}
            return max(1, min(8, int(pack.get("current_step") or 1)))
        return original_infer_step(run_path)

    def synthesized_meta(run_path: Path) -> dict[str, Any]:
        if not _is_pack_path(run_path):
            return original_synthesized_meta(run_path)
        pack = server._read_json(run_path / "reel_pack.json", {}) or {}
        input_payload = server._read_json(run_path / "input.json", {}) or {}
        step = infer_step(run_path)
        return {
            "id": run_path.name,
            "content_product": CONTENT_PRODUCT,
            "topic_ref": input_payload.get("topic_ref", ""),
            "topic": input_payload.get("topic", run_path.name),
            "objective_ids": input_payload.get("objective_ids", []),
            "facts_path": f"video_engine/topics/{input_payload.get('topic_ref', '')}/facts.json",
            "status": "completed" if step >= 8 else ("created" if step <= 1 else "paused"),
            "current_step": step,
            "created_at": pack.get("created_at") or server._now(),
            "updated_at": pack.get("updated_at") or server._now(),
            "settings": {
                "content_product": CONTENT_PRODUCT,
                "animation_mode": server.MOTION_CANVAS_MODE,
                "duration": input_payload.get("target_duration_seconds", 35),
                "reel_count": input_payload.get("reel_count", 5),
                "model_provider": "gemini",
                "audio_provider": input_payload.get("audio_provider", "gemini"),
                "scene_concurrency": 2,
                "confirm_paid_api": True,
                "task_models": {},
            },
            "error": None,
        }

    def normalized_meta(run_path: Path, meta: dict[str, Any]) -> dict[str, Any]:
        if not _is_pack_path(run_path) and str(meta.get("content_product") or "") != CONTENT_PRODUCT:
            return original_normalized_meta(run_path, meta)
        base = synthesized_meta(run_path)
        merged = {**base, **meta}
        settings = {**base.get("settings", {}), **(meta.get("settings") or {})}
        settings["content_product"] = CONTENT_PRODUCT
        settings["animation_mode"] = server.MOTION_CANVAS_MODE
        merged["settings"] = settings
        merged["content_product"] = CONTENT_PRODUCT
        merged["current_step"] = infer_step(run_path)
        return merged

    def artifact_snapshot(run_id: str) -> dict[str, Any]:
        if _is_pack_path(server._run_dir(run_id)):
            return _pack_artifacts(server, run_id)
        return original_artifact_snapshot(run_id)

    def reset_run_from_step(run_id: str, step: int) -> dict[str, Any]:
        run_path = server._run_dir(run_id)
        if not _is_pack_path(run_path):
            return original_reset_run_from_step(run_id, step)
        if step not in range(1, 9):
            raise ValueError("Reset step must be between 1 and 8")
        if step == 1:
            return original_reset_run_from_step(run_id, step)
        with server._process_lock:
            process = server._processes.get(run_id)
            if process and process.poll() is None:
                raise RuntimeError("Stop the active process before regenerating from a step")

        def remove(relative: str) -> None:
            path = run_path / relative
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink(missing_ok=True)

        if step <= 2:
            for relative in (
                "pack_plan.json",
                "narration.json",
                "narration.txt",
                "narration_elevenlabs.txt",
                "responses",
            ):
                remove(relative)
        if step <= 3:
            for relative in (
                "voiceover.mp3",
                "voiceover.wav",
                "audio_generation.json",
                "audio_alignment.json",
                "audio_chunks",
            ):
                remove(relative)
        if step <= 4:
            for relative in (
                "audio_timing.json",
                "audio_word_timestamps.json",
                "beat_timing.json",
            ):
                remove(relative)
        if step <= 5:
            remove("motion_canvas")
            remove("validation-report.json")
        elif step <= 6:
            for relative in (
                "motion_canvas/validation.json",
                "motion_canvas/robot-report.json",
                "motion_canvas/preview",
                "motion_canvas/frames",
                "motion_canvas/renders",
                "validation-report.json",
            ):
                remove(relative)
        if step <= 7:
            for relative in ("review", "pack-review.json"):
                remove(relative)
        if step <= 8:
            for relative in (
                "motion_canvas/renders",
                "publishing_manifest.json",
                "render_report.json",
            ):
                remove(relative)

        pack = load_pack(run_path)
        status_before_step = {
            2: "planned",
            3: "scripted",
            4: "audio_ready",
            5: "timed",
            6: "visual_ready",
            7: "visual_ready",
            8: "approved",
        }[step]
        pack_status_before_step = {
            2: "created",
            3: "scripts_ready",
            4: "audio_ready",
            5: "timing_ready",
            6: "visuals_ready",
            7: "visuals_ready",
            8: "approved",
        }[step]
        if step == 2:
            input_payload = read_json(run_path / "input.json", {}) or {}
            duration = float(input_payload.get("target_duration_seconds") or 35)
            pack["reels"] = [
                {
                    "reel_id": record["reel_id"],
                    "status": "planned",
                    "target_duration_seconds": duration,
                    "path": ".",
                }
                for record in pack.get("reels", [])
            ]
        else:
            for record in pack.get("reels", []):
                if record.get("status") == "rejected":
                    continue
                if step == 8:
                    if record.get("status") == "rendered":
                        record["status"] = "approved"
                else:
                    record["status"] = status_before_step
                record.pop("error", None)
                if step <= 7:
                    record.pop("approved_at", None)
                record.pop("rendered_at", None)
        pack["status"] = pack_status_before_step
        pack["current_step"] = step - 1
        save_pack(run_path, pack)

        meta = server._load_meta(run_id)
        meta.update({
            "status": "paused",
            "current_step": step - 1,
            "error": None,
            "settings": {
                **meta.get("settings", {}),
                "confirm_paid_api": True,
                "animation_mode": server.MOTION_CANVAS_MODE,
            },
        })
        server._save_meta(meta)
        server._append_log(run_id, f"Reset Reel pack from step {step}; downstream artifacts removed")
        return server.run_detail(run_id)

    def create_run(payload: dict[str, Any]) -> dict[str, Any]:
        if str(payload.get("content_product") or FULL_LESSON_PRODUCT) != CONTENT_PRODUCT:
            return original_create_run(payload)
        topic_ref = server._require_topic_ref(str(payload.get("topic_ref", "")))
        detail = server.topic_detail(topic_ref)
        facts_path = server.TOPICS_ROOT / topic_ref / "facts.json"
        if not facts_path.exists():
            server._prepare_topic(topic_ref)
        requested_id = str(payload.get("run_id", "")).strip()
        run_id = requested_id or f"physics-{topic_ref.replace('.', '-')}-reels-{server.datetime.now().strftime('%Y%m%d-%H%M%S')}"
        server._require_run_id(run_id)
        run_path = server._run_dir(run_id)
        if run_path.exists() and any(run_path.iterdir()):
            raise FileExistsError(f"Run already exists: {run_id}")
        facts_payload = _facts_payload(server, facts_path)
        objectives = [
            objective["objective_id"]
            for objective in detail["objectives"]
            if objective.get("status") != "covered"
        ]
        count = max(1, min(int(payload.get("reel_count", 5)), 24))
        duration = max(20.0, min(float(payload.get("duration", 35)), 75.0))
        audio_provider = str(payload.get("audio_provider", "gemini"))
        create_pack(
            run_id=run_id,
            topic=f"{topic_ref} {detail['topic']['title']}",
            topic_ref=topic_ref,
            objective_ids=objectives or list(facts_payload.get("objective_ids") or []),
            facts=list(facts_payload.get("facts") or []),
            physics_context=dict(facts_payload.get("physics_context") or {}),
            tone=str(payload.get("tone") or "warm, precise IGCSE Physics teacher"),
            reel_count=count,
            target_duration_seconds=duration,
            audio_provider=audio_provider,
        )
        settings = {
            "content_product": CONTENT_PRODUCT,
            "duration": duration,
            "reel_count": count,
            "model_provider": payload.get("model_provider", "gemini"),
            "audio_provider": audio_provider,
            "scene_concurrency": max(1, min(int(payload.get("scene_concurrency", 2)), 3)),
            "confirm_paid_api": bool(payload.get("confirm_paid_api", True)),
            "task_models": server._validate_task_models(payload.get("task_models")),
            "animation_mode": server.MOTION_CANVAS_MODE,
        }
        meta = {
            "id": run_id,
            "content_product": CONTENT_PRODUCT,
            "topic_ref": topic_ref,
            "topic": f"{topic_ref} {detail['topic']['title']} · Independent Reel pack",
            "objective_ids": objectives,
            "facts_path": str(facts_path.relative_to(server.REPO_ROOT)),
            "status": "created",
            "current_step": 1,
            "created_at": server._now(),
            "updated_at": server._now(),
            "settings": settings,
            "error": None,
        }
        server._save_meta(meta)
        server._append_log(run_id, f"Standalone Reel pack created for topic {topic_ref}")
        if payload.get("execute"):
            command, env = build_generation_command(
                meta,
                {"from_step": 1, "stop_after_step": 7, "confirm_paid_api": settings["confirm_paid_api"]},
            )
            return server._start_process(run_id, command, env, mode="Reel-pack generation", target_step=7)
        return server.run_detail(run_id)

    def build_generation_command(meta: dict[str, Any], request: dict[str, Any]) -> tuple[list[str], dict[str, str]]:
        if not _is_pack_meta(meta, server):
            return original_build_generation_command(meta, request)
        from_step = int(request.get("from_step", 1))
        stop_after_step = int(request.get("stop_after_step", 8))
        if not 1 <= from_step <= stop_after_step <= 8:
            raise ValueError("Reel-pack steps must satisfy 1 <= from <= stop <= 8")
        settings = {**meta.get("settings", {}), **request.get("settings", {})}
        paid = any(step in {2, 3, 5, 6, 7} for step in range(from_step, stop_after_step + 1))
        confirmed = bool(request.get("confirm_paid_api", settings.get("confirm_paid_api", False)))
        if paid and not confirmed:
            raise PermissionError("Reel-pack planning, audio, visual generation, and screening require paid-API confirmation")
        facts_path = Path(meta["facts_path"])
        if not facts_path.is_absolute():
            facts_path = server.REPO_ROOT / facts_path
        if not facts_path.exists():
            raise FileNotFoundError(facts_path)
        audio_provider = str(settings.get("audio_provider", "gemini"))
        if audio_provider not in server.AUDIO_PROVIDERS:
            raise ValueError("Unsupported audio provider")
        command = [
            server.PYTHON_EXECUTABLE,
            str(server.TEMPLATE_LAB_ROOT / "scripts" / "mav_generate_reel_pack.py"),
            "--run-id",
            str(meta["id"]),
            "--facts",
            str(facts_path),
            "--reel-count",
            str(int(settings.get("reel_count", 12))),
            "--duration",
            str(float(settings.get("duration", 45))),
            "--audio-provider",
            audio_provider,
            "--workers",
            str(max(1, min(int(settings.get("scene_concurrency", 2)), 3))),
            "--from-step",
            str(from_step),
            "--stop-after-step",
            str(stop_after_step),
        ]
        if paid:
            command.extend(["--use-model", "--confirm-paid-api"])
        if request.get("force") or request.get("force_paid_api"):
            command.append("--force")
        target = request.get("target_reel_id")
        if target:
            command.extend(["--reel-id", require_reel_id(str(target))])
        if request.get("auto_repair") is False:
            command.append("--screen-only")
        if request.get("render_all"):
            command.append("--render-all")
        env = _task_environment(server, settings=settings, request=request)
        env["MAV_RUN_ID"] = str(meta["id"])
        return command, env

    def resize_pack(run_id: str, requested_count: Any) -> dict[str, Any]:
        run_id = server._require_run_id(run_id)
        run_path = server._run_dir(run_id)
        meta = server._load_meta(run_id)
        if not _is_pack_meta(meta, server):
            raise ValueError("Run is not a Reel pack")
        count = bounded_reel_count(requested_count)
        with server._process_lock:
            process = server._processes.get(run_id)
            if process and process.poll() is None:
                raise RuntimeError("Stop the active generation before changing the Reel count")
        current_count = int((meta.get("settings") or {}).get("reel_count") or 0)
        if current_count == count:
            return server.run_detail(run_id)

        input_payload = read_json(run_path / "input.json", {}) or {}
        duration = float(
            input_payload.get("target_duration_seconds")
            or (meta.get("settings") or {}).get("duration")
            or 35
        )
        input_payload["reel_count"] = count
        server._write_json(run_path / "input.json", input_payload)

        pack = load_pack(run_path)
        pack["target_reel_count"] = count
        pack["reels"] = [
            {
                "reel_id": reel_id(index),
                "status": "planned",
                "target_duration_seconds": duration,
                "path": ".",
            }
            for index in range(1, count + 1)
        ]
        save_pack(run_path, pack)
        meta["settings"] = {**meta.get("settings", {}), "reel_count": count}
        server._save_meta(meta)

        result = reset_run_from_step(run_id, 2)
        server._append_log(
            run_id,
            f"Reel count changed from {current_count or 'unknown'} to {count}; "
            "planning and downstream artifacts were reset",
        )
        return result

    server._resize_reel_pack = resize_pack

    def do_post(self: Any) -> None:
        path = urlparse(self.path).path
        try:
            match = re.fullmatch(r"/api/runs/([^/]+)/reel-pack/settings", path)
            if match:
                body = self._body()
                return self._json({
                    "run": resize_pack(match.group(1), body.get("reel_count")),
                })
            match = re.fullmatch(r"/api/runs/([^/]+)/reel-pack/reels/([^/]+)/approve", path)
            if match:
                run_id = server._require_run_id(match.group(1))
                reel_id = require_reel_id(match.group(2))
                approve_reel(server._run_dir(run_id), reel_id)
                server._append_log(run_id, f"Approved standalone {reel_id}")
                return self._json({"run": server.run_detail(run_id)})
            match = re.fullmatch(r"/api/runs/([^/]+)/reel-pack/reels/([^/]+)/reject", path)
            if match:
                run_id = server._require_run_id(match.group(1))
                reel_id = require_reel_id(match.group(2))
                body = self._body()
                reject_reel(server._run_dir(run_id), reel_id, str(body.get("reason") or ""))
                server._append_log(run_id, f"Rejected standalone {reel_id} during script review")
                return self._json({"run": server.run_detail(run_id)})
            match = re.fullmatch(r"/api/runs/([^/]+)/reel-pack/reels/([^/]+)/restore", path)
            if match:
                run_id = server._require_run_id(match.group(1))
                reel_id = require_reel_id(match.group(2))
                restore_reel(server._run_dir(run_id), reel_id)
                server._append_log(run_id, f"Restored standalone {reel_id} for downstream stages")
                return self._json({"run": server.run_detail(run_id)})
            match = re.fullmatch(r"/api/runs/([^/]+)/reel-pack/reels/([^/]+)/regenerate", path)
            if match:
                body = self._body()
                body.update(
                    {
                        "from_step": 5,
                        "stop_after_step": 6,
                        "target_reel_id": require_reel_id(match.group(2)),
                        "force": True,
                        "confirm_paid_api": True,
                    }
                )
                return self._json({"run": server.execute_run(match.group(1), body)}, 202)
            match = re.fullmatch(r"/api/runs/([^/]+)/reel-pack/reels/([^/]+)/run", path)
            if match:
                body = self._body()
                body["target_reel_id"] = require_reel_id(match.group(2))
                return self._json({"run": server.execute_run(match.group(1), body)}, 202)
            match = re.fullmatch(r"/api/runs/([^/]+)/reel-pack/screen", path)
            if match:
                body = self._body()
                body.update({"from_step": 7, "stop_after_step": 7, "confirm_paid_api": True})
                return self._json({"run": server.execute_run(match.group(1), body)}, 202)
            match = re.fullmatch(r"/api/runs/([^/]+)/reel-pack/render", path)
            if match:
                body = self._body()
                body.update({"from_step": 8, "stop_after_step": 8})
                return self._json({"run": server.execute_run(match.group(1), body)}, 202)
            return original_do_post(self)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return
        except Exception as exc:  # noqa: BLE001
            self._error(exc)

    server._infer_step = infer_step
    server._synthesized_meta = synthesized_meta
    server._normalized_meta = normalized_meta
    server._artifact_snapshot = artifact_snapshot
    server.create_run = create_run
    server.build_generation_command = build_generation_command
    server.reset_run_from_step = reset_run_from_step
    server.StudioHandler.do_POST = do_post
