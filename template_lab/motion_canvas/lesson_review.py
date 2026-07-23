"""One-call lesson-level rendered screening and targeted reel regeneration."""
from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import base64
import subprocess
import time
import urllib.request
from pathlib import Path
from types import ModuleType
from typing import Any

from .generation_contract import CONTRACT_END, CONTRACT_START

TASK = "motion_canvas_lesson_screen"
VERSION = "2.0"
DEFAULT_MAX_FINDINGS = 5
DEFAULT_MIN_CONFIDENCE = 0.85


def _log(message: str) -> None:
    print(f"[lesson-review] {message}", flush=True)


def _load(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".tmp-{os.getpid()}-{time.time_ns()}")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def _units(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return list(manifest.get("reels") or manifest.get("shots") or manifest.get("chapters") or [])


def _directory(manifest: dict[str, Any]) -> str:
    if manifest.get("timeline_mode") == "immutable_reels":
        return "reels"
    if manifest.get("timeline_mode") == "immutable_shots":
        return "shots"
    return "chapters"


def extract_visual_contract(source: str, reel_id: str) -> tuple[dict[str, Any], list[str]]:
    pattern = re.escape(CONTRACT_START) + r"\s*(\{[\s\S]*?\})\s*" + re.escape(CONTRACT_END)
    match = re.search(pattern, source)
    if not match:
        return {}, [f"{reel_id} omitted MAV_VISUAL_CONTRACT; fallback checkpoint selection will be used"]
    try:
        contract = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        return {}, [f"{reel_id} has invalid MAV_VISUAL_CONTRACT JSON: {exc}"]
    if not isinstance(contract, dict):
        return {}, [f"{reel_id} MAV_VISUAL_CONTRACT must be an object"]
    checkpoints = contract.get("review_checkpoints")
    if not isinstance(checkpoints, list) or not (1 <= len(checkpoints) <= 3):
        return contract, [f"{reel_id} should provide one to three review_checkpoints"]
    return contract, []


def build_screening_context(run_path: Path, manifest: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    input_payload = _load(run_path / "input.json", {}) or {}
    unit_by_id = {str(unit["scene_id"]): unit for unit in _units(manifest)}
    context_reels = []
    warnings: list[str] = []
    for reel in evidence.get("reels", []):
        reel_id = str(reel.get("reel_id"))
        unit = unit_by_id.get(reel_id, {})
        source_path = run_path / "motion_canvas" / _directory(manifest) / f"{reel_id}.tsx"
        source = source_path.read_text(encoding="utf-8") if source_path.exists() else ""
        contract, contract_warnings = extract_visual_contract(source, reel_id)
        warnings.extend(contract_warnings)
        context_reels.append(
            {
                "reel_id": reel_id,
                "chapter_number": reel.get("chapter_number"),
                "narration": unit.get("narration", ""),
                "beats": [
                    {
                        "beat_id": beat.get("beat_id") or beat.get("id"),
                        "local_start": beat.get("local_start"),
                        "local_end": beat.get("local_end"),
                        "narration": beat.get("narration", ""),
                    }
                    for beat in unit.get("beats", [])
                ],
                "visual_contract": contract,
                "frames": reel.get("frames", []),
            }
        )
    return {
        "version": VERSION,
        "topic": input_payload.get("topic"),
        "topic_ref": input_payload.get("topic_ref"),
        "objective_ids": input_payload.get("objective_ids", []),
        "grounded_facts": input_payload.get("facts", []),
        "physics_context": input_payload.get("physics_context", {}),
        "review_rules": {
            "maximum_findings": DEFAULT_MAX_FINDINGS,
            "minimum_confidence": DEFAULT_MIN_CONFIDENCE,
            "zero_findings_allowed": True,
            "ignore_minor_style_preferences": True,
        },
        "warnings": warnings,
        "reels": context_reels,
    }


def parse_screening_response(
    response: str,
    *,
    evidence: dict[str, Any],
    max_findings: int = DEFAULT_MAX_FINDINGS,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
) -> dict[str, Any]:
    cleaned = response.replace("```json", "").replace("```", "").strip()
    start = cleaned.find("{")
    if start < 0:
        raise RuntimeError("Lesson screening response contained no JSON object")
    try:
        payload, _ = json.JSONDecoder().raw_decode(cleaned[start:])
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Lesson screening response is invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Lesson screening response must be a JSON object")

    frames_by_reel = {
        str(reel.get("reel_id")): {str(frame.get("frame_id")) for frame in reel.get("frames", [])}
        for reel in evidence.get("reels", [])
    }
    accepted: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for raw in payload.get("findings", []) if isinstance(payload.get("findings"), list) else []:
        if not isinstance(raw, dict):
            continue
        reel_id = str(raw.get("reel_id") or "")
        frame_id = str(raw.get("frame_id") or "")
        try:
            confidence = float(raw.get("confidence", 0))
        except (TypeError, ValueError):
            confidence = 0
        if reel_id not in frames_by_reel or frame_id not in frames_by_reel[reel_id] or confidence < min_confidence:
            continue
        severity = str(raw.get("severity") or "major").lower()
        if severity not in {"critical", "major"}:
            continue
        category = str(raw.get("category") or "visible_defect")
        key = (reel_id, frame_id, category)
        if key in seen:
            continue
        seen.add(key)
        accepted.append(
            {
                "rank": int(raw.get("rank") or len(accepted) + 1),
                "chapter_number": raw.get("chapter_number"),
                "reel_id": reel_id,
                "frame_id": frame_id,
                "timestamp": raw.get("timestamp"),
                "category": category,
                "severity": severity,
                "confidence": round(confidence, 4),
                "visible_evidence": str(raw.get("visible_evidence") or "").strip(),
                "expected_behaviour": str(raw.get("expected_behaviour") or "").strip(),
                "repair_instruction": str(raw.get("repair_instruction") or "").strip(),
            }
        )
    accepted.sort(key=lambda item: (-item["confidence"], 0 if item["severity"] == "critical" else 1, item["rank"]))
    accepted = accepted[: max(0, min(5, max_findings))]
    return {
        "status": "ISSUES_FOUND" if accepted else "PASS",
        "findings": accepted,
        "raw_status": payload.get("status"),
    }


def _screen_cache_key(run_path: Path, manifest: dict[str, Any], prompt: str) -> str:
    digest = hashlib.sha256()
    digest.update(VERSION.encode())
    digest.update(prompt.encode())
    for relative in ("input.json", "narration.json", "story_skeleton.json"):
        path = run_path / relative
        if path.exists():
            digest.update(relative.encode())
            digest.update(path.read_bytes())
    directory = _directory(manifest)
    for unit in _units(manifest):
        reel_id = str(unit.get("scene_id"))
        for suffix in (".tsx", ".cues.ts"):
            path = run_path / "motion_canvas" / directory / f"{reel_id}{suffix}"
            if path.exists():
                digest.update(path.name.encode())
                digest.update(path.read_bytes())
    return digest.hexdigest()


def _resolved_model() -> Any:
    from mav_models import load_env, model_config_for_task

    load_env()
    return model_config_for_task(TASK, requested_max_tokens=8_000)


def _gemini_screen(*, system: str, user: str, images: list[Path]) -> str:
    from google import genai
    from google.genai import types
    from mav_costs import record_model_usage
    from mav_models import (
        _api_key_for_provider,
        _gemini_finish_reasons,
        _gemini_response_text,
        _gemini_usage,
        model_timeout_seconds,
    )

    resolved = _resolved_model()
    parts = [types.Part.from_text(text=user)]
    for image in images:
        mime_type = mimetypes.guess_type(image.name)[0] or "image/png"
        parts.append(types.Part.from_bytes(data=image.read_bytes(), mime_type=mime_type))
    http_options = types.HttpOptions(timeout=model_timeout_seconds(resolved) * 1000)
    client = genai.Client(api_key=_api_key_for_provider("gemini"), http_options=http_options)
    _log(f"screen request: provider={resolved.provider} model={resolved.model} images={len(images)} max_tokens={resolved.max_tokens}")
    response = client.models.generate_content(
        model=resolved.model,
        contents=[types.Content(role="user", parts=parts)],
        config=types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=resolved.max_tokens,
            temperature=0.1,
            http_options=http_options,
        ),
    )
    reasons = ",".join(_gemini_finish_reasons(response)).upper()
    if any(reason in reasons for reason in ("MAX_TOKENS", "SAFETY", "RECITATION", "PROHIBITED")):
        raise RuntimeError(f"Gemini {TASK} stopped with {reasons}")
    record_model_usage(
        task=TASK,
        provider=resolved.provider,
        model=resolved.model,
        usage=_gemini_usage(response),
        response_id=None,
    )
    text = _gemini_response_text(response)
    if not text:
        raise RuntimeError("Lesson screening model returned no text")
    _log(f"screen response received: model={resolved.model} characters={len(text)}")
    return text


def _anthropic_screen(*, system: str, user: str, images: list[Path], resolved: Any) -> str:
    from mav_costs import record_model_usage
    from mav_models import _anthropic_request_json, _api_key_for_provider, model_timeout_seconds

    content: list[dict[str, Any]] = [{"type": "text", "text": user}]
    for image in images:
        media_type = mimetypes.guess_type(image.name)[0] or "image/png"
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": base64.b64encode(image.read_bytes()).decode("ascii")},
        })
    payload = {"model": resolved.model, "max_tokens": resolved.max_tokens, "system": system, "messages": [{"role": "user", "content": content}]}
    request = urllib.request.Request(
        os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/") + "/v1/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json", "anthropic-version": "2023-06-01", "x-api-key": _api_key_for_provider("anthropic") or ""},
        method="POST",
    )
    _log(f"screen request: provider=anthropic model={resolved.model} images={len(images)} max_tokens={resolved.max_tokens}")
    data = _anthropic_request_json(request, resolved, model_timeout_seconds(resolved))
    if data.get("stop_reason") in {"max_tokens", "refusal"}:
        raise RuntimeError(f"Anthropic {TASK} stopped with {data.get('stop_reason')}")
    record_model_usage(task=TASK, provider="anthropic", model=resolved.model, usage=data.get("usage") or {}, response_id=data.get("id"))
    text = "\n".join(block.get("text", "") for block in data.get("content", []) if block.get("type") == "text")
    if not text:
        raise RuntimeError("Anthropic lesson screening returned no text")
    _log(f"screen response received: model={resolved.model} characters={len(text)}")
    return text


def _moonshot_screen(*, system: str, user: str, images: list[Path], resolved: Any) -> str:
    from mav_costs import record_model_usage
    from mav_models import MOONSHOT_CHAT_COMPLETIONS_URL, _api_key_for_provider, model_timeout_seconds

    content: list[dict[str, Any]] = [{"type": "text", "text": user}]
    for image in images:
        media_type = mimetypes.guess_type(image.name)[0] or "image/png"
        data = base64.b64encode(image.read_bytes()).decode("ascii")
        content.append({"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{data}"}})
    payload = {
        "model": resolved.model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}],
        "response_format": {"type": "json_object"},
    }
    if resolved.model == "kimi-k3":
        # K3 uses the newer completion-token field and always reasons. Keep its
        # reasoning budget bounded so the reviewer still returns final JSON.
        payload["max_completion_tokens"] = resolved.max_tokens
        payload["reasoning_effort"] = os.getenv("MAV_MOTION_CANVAS_LESSON_SCREEN_REASONING_EFFORT", "low")
    else:
        payload["max_completion_tokens"] = resolved.max_tokens
    request = urllib.request.Request(
        MOONSHOT_CHAT_COMPLETIONS_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {_api_key_for_provider('moonshot') or ''}", "Content-Type": "application/json"},
        method="POST",
    )
    _log(f"screen request: provider=moonshot model={resolved.model} images={len(images)} max_completion_tokens={resolved.max_tokens}")
    with urllib.request.urlopen(request, timeout=model_timeout_seconds(resolved)) as response:
        data = json.loads(response.read().decode("utf-8"))
    record_model_usage(task=TASK, provider="moonshot", model=resolved.model, usage=data.get("usage") or {}, response_id=data.get("id"))
    choices = data.get("choices") or []
    message = choices[0].get("message", {}) if choices and isinstance(choices[0], dict) else {}
    finish_reason = choices[0].get("finish_reason") if choices and isinstance(choices[0], dict) else None
    _log(
        "moonshot response metadata: "
        f"keys={sorted(data.keys())} choices={len(choices)} "
        f"message_keys={sorted(message.keys()) if isinstance(message, dict) else []} "
        f"finish_reason={finish_reason!r} usage_keys={sorted((data.get('usage') or {}).keys())}"
    )
    text = message.get("content", "") if isinstance(message, dict) else ""
    if isinstance(text, list):
        parts = []
        for item in text:
            piece = item.get("text", item.get("content", "")) if isinstance(item, dict) else item
            if piece:
                parts.append(str(piece))
        text = "\n".join(parts)
    if not text:
        error = data.get("error")
        detail = f" error={error!r}" if error else ""
        raise RuntimeError(
            "Kimi lesson screening returned no text "
            f"(model={resolved.model!r}, choices={len(choices)}, finish_reason={finish_reason!r}, "
            f"response_keys={sorted(data.keys())}, message_keys={sorted(message.keys()) if isinstance(message, dict) else []}).{detail}"
        )
    _log(f"screen response received: model={resolved.model} characters={len(text)}")
    return str(text)


def _codex_screen(*, system: str, user: str, images: list[Path], resolved: Any) -> str:
    from mav_codex import _binary, _login_status, _tokens
    from mav_costs import record_model_usage
    import tempfile

    codex = _binary()
    _login_status(codex)
    reasoning = os.getenv("MAV_MOTION_CANVAS_LESSON_SCREEN_REASONING_EFFORT", "low").strip().lower()
    prompt = f"Return JSON only.\n\nSYSTEM INSTRUCTIONS\n{system}\n\nUSER REQUEST\n{user}"
    with tempfile.TemporaryDirectory(prefix="mav-codex-screen-") as directory:
        output = Path(directory) / "response.txt"
        command = [codex, "exec", "-", "--ephemeral", "--sandbox", "read-only", "--color", "never", "--output-last-message", str(output), "--cd", str(Path(__file__).resolve().parents[2]), "--model", resolved.model]
        for image in images:
            command.extend(["--image", str(image)])
        command.extend(["--config", f'model_reasoning_effort="{reasoning}"'])
        _log(f"screen request: provider=codex model={resolved.model} images={len(images)} max_tokens={resolved.max_tokens}")
        result = subprocess.run(command, input=prompt, capture_output=True, text=True, timeout=int(os.getenv("MAV_CODEX_TIMEOUT_SECONDS", "2400")))
        if result.returncode != 0:
            raise RuntimeError(f"Codex lesson screening exited with code {result.returncode}: {(result.stderr or result.stdout)[-3000:]}")
        if not output.exists():
            raise RuntimeError("Codex lesson screening produced no response")
        text = output.read_text(encoding="utf-8")
    record_model_usage(task=TASK, provider="codex", model=resolved.model, usage={"total_tokens": _tokens(result.stderr)})
    _log(f"screen response received: model={resolved.model} characters={len(text)}")
    return text


def _screen_with_model(*, system: str, user: str, images: list[Path], resolved: Any) -> str:
    if resolved.provider == "gemini":
        return _gemini_screen(system=system, user=user, images=images)
    if resolved.provider == "anthropic":
        return _anthropic_screen(system=system, user=user, images=images, resolved=resolved)
    if resolved.provider == "moonshot":
        return _moonshot_screen(system=system, user=user, images=images, resolved=resolved)
    if resolved.provider == "codex":
        return _codex_screen(system=system, user=user, images=images, resolved=resolved)
    raise RuntimeError(f"Unsupported multimodal lesson-screen provider: {resolved.provider}")


def _run_evidence(
    run_path: Path,
    pipeline: ModuleType,
    *,
    output: Path,
    reel_ids: list[str] | None = None,
) -> dict[str, Any]:
    env = os.environ.copy()
    env["MAV_MOTION_RUN_ROOT"] = str((run_path / "motion_canvas").resolve())
    node_bin = pipeline._modern_node_bin()
    if node_bin:
        env["PATH"] = str(node_bin) + os.pathsep + env.get("PATH", "")
    command = ["npm", "run", "lesson-evidence", "--", "--output", str(output)]
    if reel_ids:
        command.extend(["--reels", ",".join(reel_ids)])
    result = subprocess.run(
        command,
        cwd=pipeline.RUNTIME_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=1_200,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "Lesson evidence generation failed")[-12_000:])
    evidence_path = output / "evidence.json"
    if not evidence_path.exists():
        raise RuntimeError("Lesson evidence script did not create evidence.json")
    return _load(evidence_path, {}) or {}


def _repair_instruction(reel_id: str, findings: list[dict[str, Any]], contract: dict[str, Any]) -> str:
    return (
        "TARGETED RENDERED-EVIDENCE CORRECTION\n\n"
        "The reel compiled, but one lesson-level multimodal screening call found the following high-confidence visible defects:\n"
        + json.dumps(findings, indent=2, ensure_ascii=False)
        + "\n\nORIGINAL VISUAL BEHAVIOUR CONTRACT\n"
        + json.dumps(contract, indent=2, ensure_ascii=False)
        + "\n\nCorrect only these proven defects and directly related layout consequences. Preserve the overall cinematic concept and unaffected code.\n"
        "IMMUTABLE REQUIREMENTS:\n"
        "- preserve CHAPTER_DURATION and the reel's absolute audio window;\n"
        "- preserve every existing cue key, occurrence, order, and cue-to-visual event mapping;\n"
        "- do not move a semantic event earlier or later merely to simplify the repair;\n"
        "- derive displayed arrows and resulting motion from one consistent state;\n"
        "- preserve or update MAV_VISUAL_CONTRACT so it accurately describes the corrected reel;\n"
        "- return the complete corrected TSX through the normal reel-generation marker.\n"
        f"TARGET REEL: {reel_id}"
    )


def screen_and_repair(
    run_path: Path,
    manifest: dict[str, Any],
    pipeline: ModuleType,
    *,
    model_call: Any = None,
    allow_repairs: bool = True,
) -> dict[str, Any]:
    """Run one lesson-level screen, then regenerate only flagged reels once."""
    root = run_path / "motion_canvas" / "lesson-review"
    report_path = run_path / "motion_canvas" / "lesson-review.json"
    prompt_path = Path(__file__).with_name("prompts") / "lesson_screen.system.txt"
    system = prompt_path.read_text(encoding="utf-8")
    resolved = _resolved_model() if model_call is None else None
    model_signature = f"{resolved.provider}:{resolved.model}" if resolved is not None else "injected-model-call"
    cache_key = _screen_cache_key(run_path, manifest, system + "\nMODEL=" + model_signature)
    previous = _load(report_path, {}) or {}
    if previous.get("status") == "passed" and previous.get("cache_key") == cache_key:
        return {**previous, "cached": True}
    started = time.monotonic()
    report: dict[str, Any] = {
        "version": VERSION,
        "status": "running",
        "phase": "capturing_evidence",
        "started_at": time.time(),
        "screening_calls": 0,
        "cache_key": cache_key,
        "screening_model": model_signature,
        "findings": [],
        "repairs": [],
    }
    _write_json(report_path, report)

    _log(f"starting optional visual review: run={run_path.name} model={model_signature} auto_repair={allow_repairs}")
    _log("capturing lesson evidence from the accepted Motion Canvas sources")
    evidence = _run_evidence(run_path, pipeline, output=root / "evidence")
    context = build_screening_context(run_path, manifest, evidence)
    _write_json(root / "screening-context.json", context)
    user = "LESSON SCREENING CONTEXT\n" + json.dumps(context, ensure_ascii=False, separators=(",", ":"))
    images = [root / "evidence" / name for name in evidence.get("contact_sheets", [])]
    images = [image for image in images if image.exists()]
    if not images:
        raise RuntimeError("Lesson screening produced no contact sheets")
    frame_count = sum(len(reel.get("frames", [])) for reel in evidence.get("reels", []))
    _log(f"evidence ready: reels={len(evidence.get('reels', []))} frames={frame_count} contact_sheets={len(images)}")

    report.update({"phase": "screening", "contact_sheets": [str(path.relative_to(run_path)) for path in images]})
    _write_json(report_path, report)
    response = (
        model_call(system=system, user=user, images=images)
        if model_call is not None
        else _screen_with_model(system=system, user=user, images=images, resolved=resolved)
    )
    (root / "screening-response.txt").write_text(response.rstrip() + "\n", encoding="utf-8")
    max_findings = int(os.getenv("MAV_MOTION_CANVAS_SCREEN_MAX_FINDINGS", str(DEFAULT_MAX_FINDINGS)))
    min_confidence = float(os.getenv("MAV_MOTION_CANVAS_SCREEN_MIN_CONFIDENCE", str(DEFAULT_MIN_CONFIDENCE)))
    decision = parse_screening_response(
        response,
        evidence=evidence,
        max_findings=max_findings,
        min_confidence=min_confidence,
    )
    report.update({"screening_calls": 1, "screening": decision, "findings": decision["findings"]})
    _log(f"screen decision: status={decision['status']} accepted_findings={len(decision['findings'])}")
    _write_json(report_path, report)

    if not decision["findings"]:
        report.update({"status": "passed", "phase": "complete", "elapsed_seconds": round(time.monotonic() - started, 2)})
        _write_json(report_path, report)
        return report

    findings_by_reel: dict[str, list[dict[str, Any]]] = {}
    for finding in decision["findings"]:
        findings_by_reel.setdefault(str(finding["reel_id"]), []).append(finding)
    if not allow_repairs:
        report.update({"status": "issues_found", "phase": "complete", "elapsed_seconds": round(time.monotonic() - started, 2)})
        _write_json(report_path, report)
        return report

    unit_by_id = {str(unit["scene_id"]): unit for unit in _units(manifest)}
    source_directory = run_path / "motion_canvas" / _directory(manifest)
    repaired_ids: list[str] = []
    report["phase"] = "targeted_regeneration"
    _write_json(report_path, report)
    for reel_id, reel_findings in findings_by_reel.items():
        source_path = source_directory / f"{reel_id}.tsx"
        if reel_id not in unit_by_id or not source_path.exists():
            report["repairs"].append({"reel_id": reel_id, "status": "failed", "error": "missing reel source"})
            _write_json(report_path, report)
            continue
        original = source_path.read_text(encoding="utf-8")
        contract, _ = extract_visual_contract(original, reel_id)
        try:
            _log(f"repairing {reel_id}: findings={len(reel_findings)} using configured motion_canvas_batch model")
            generation = pipeline.generate(
                run_path,
                manifest,
                allow_model_call=True,
                force=True,
                workers=1,
                target_chapter_id=reel_id,
                instruction=_repair_instruction(reel_id, reel_findings, contract),
            )
            if generation.get("status") != "generated":
                raise RuntimeError(f"targeted regeneration returned {generation.get('status')}")
            repaired_ids.append(reel_id)
            _log(f"repair completed: reel={reel_id}")
            report["repairs"].append({"reel_id": reel_id, "status": "regenerated", "finding_count": len(reel_findings)})
        except Exception as exc:
            source_path.write_text(original.rstrip() + "\n", encoding="utf-8")
            pipeline.assemble(run_path, manifest)
            pipeline._sync_runtime(run_path)
            report["repairs"].append({"reel_id": reel_id, "status": "failed_restored", "error": str(exc)})
            _log(f"repair failed and original restored: reel={reel_id} error={exc}")
        _write_json(report_path, report)

    if repaired_ids:
        _log(f"capturing corrected evidence for {len(repaired_ids)} repaired reel(s)")
        corrected = _run_evidence(
            run_path,
            pipeline,
            output=root / "corrected-evidence",
            reel_ids=repaired_ids,
        )
        report["corrected_contact_sheets"] = [
            str((root / "corrected-evidence" / name).relative_to(run_path))
            for name in corrected.get("contact_sheets", [])
        ]

    failed = [item for item in report["repairs"] if item.get("status") != "regenerated"]
    report.update(
        {
            "status": "repaired_pending_review" if repaired_ids and not failed else "needs_review",
            "phase": "complete",
            "repaired_reels": repaired_ids,
            "unresolved_reels": [item["reel_id"] for item in failed],
            "elapsed_seconds": round(time.monotonic() - started, 2),
        }
    )
    _log(f"optional visual review complete: status={report['status']} repaired={len(repaired_ids)} unresolved={len(failed)}")
    _write_json(report_path, report)
    return report
