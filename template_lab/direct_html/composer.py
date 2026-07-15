from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .chapter_index import build_chapter_index
from .constants import (
    CONTRACT_VERSION,
    DESIGN_SYSTEM_VERSION,
    MOTION_CORE_VERSION,
    PROMPT_VERSION,
)
from .direct_html_validator import validate_html, validation_report
from .io_utils import canonical_hash, read_json, sha256_text, sync_direct_cost_records, write_json, write_text
from .prompt_builder import composer_system_prompt, composer_user_prompt, write_prompt

ModelCall = Callable[..., str | None]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _default_model_call(**kwargs: Any) -> str | None:
    from mav_models import call_model_text

    return call_model_text(**kwargs)


def _model_metadata(task: str) -> dict[str, Any]:
    try:
        from mav_models import model_config_for_task

        config = model_config_for_task(task)
        return {"provider": config.provider, "model": config.model, "max_tokens": config.max_tokens}
    except Exception as exc:  # Configuration errors should still be visible in the manifest.
        return {"provider": "unresolved", "model": "unresolved", "error": str(exc)}


def composition_cache_key(bundle: dict[str, Any], system: str, model: dict[str, Any], asset_manifest: dict[str, Any]) -> str:
    return canonical_hash(
        {
            "bundle": bundle,
            "system": system,
            "model": model,
            "asset_manifest": asset_manifest,
            "prompt_version": PROMPT_VERSION,
            "design_system_version": DESIGN_SYSTEM_VERSION,
            "motion_core_version": MOTION_CORE_VERSION,
            "contract_version": CONTRACT_VERSION,
        }
    )


def compose_lesson(
    run_path: Path,
    bundle: dict[str, Any],
    physics_context: dict[str, Any],
    asset_manifest: dict[str, Any],
    *,
    force: bool = False,
    allow_model_call: bool = True,
    model_call: ModelCall | None = None,
) -> dict[str, Any]:
    direct_root = run_path / "direct_html"
    manifest_path = direct_root / "generation_manifest.json"
    master_path = direct_root / "master.html"
    system = composer_system_prompt()
    user = composer_user_prompt(bundle)
    model = _model_metadata("direct_html_composer")
    cache_key = composition_cache_key(bundle, system, model, asset_manifest)
    previous = read_json(manifest_path, {}) or {}
    if not force and master_path.exists() and previous.get("composition_cache_key") == cache_key and previous.get("status") in {"composed", "validated", "approved"}:
        return {"status": "cached", "master": master_path, "manifest": previous, "chapter_index": build_chapter_index(master_path)}
    if not allow_model_call:
        raise RuntimeError(
            "Direct-HTML composition cache miss. Pass --use-model and --confirm-paid-api to authorize the coding-model call."
        )

    write_prompt(direct_root / "composer_prompt.txt", system, user)
    call = model_call or _default_model_call
    response = call(
        task="direct_html_composer",
        system=system,
        user=user,
        max_tokens=64_000,
    )
    sync_direct_cost_records(run_path)
    if not response or not response.strip():
        raise RuntimeError("Direct-HTML composer returned no text")
    response = response.strip()
    write_text(direct_root / "composer_response.html", response + "\n")
    if response.startswith("```") or response.endswith("```"):
        raise RuntimeError("Direct-HTML composer returned Markdown fences instead of a raw HTML document")

    violations = validate_html(
        response,
        expected_duration=float(bundle["video"]["duration_seconds"]),
        physics_context=physics_context,
    )
    report = validation_report(violations)
    write_json(direct_root / "validation" / "html_validation.json", report)
    contract_repair_count = 0
    if report["status"] != "passed":
        contract_repair_count = 1
        errors = [item for item in report["violations"] if item["severity"] == "error"]
        repair_user = (
            "The initial full document could not be indexed under the direct-HTML runtime contract. "
            "Repair only contract/executability defects while preserving its lesson, chapter timing, claims, and visual direction. "
            "Return one corrected complete HTML document and no explanation. This is the only global contract-repair attempt.\n\n"
            f"VALIDATION ERRORS\n{errors}\n\nCURRENT DOCUMENT\n{response}"
        )
        write_prompt(direct_root / "composer_contract_repair_prompt.txt", system, repair_user)
        repaired = call(
            task="direct_html_composer",
            system=system,
            user=repair_user,
            max_tokens=64_000,
        )
        sync_direct_cost_records(run_path)
        if repaired and repaired.strip():
            repaired = repaired.strip()
            write_text(direct_root / "composer_contract_repair_response.html", repaired + "\n")
            if not repaired.startswith("```") and not repaired.endswith("```"):
                response = repaired
                violations = validate_html(
                    response,
                    expected_duration=float(bundle["video"]["duration_seconds"]),
                    physics_context=physics_context,
                )
                report = validation_report(violations)
                write_json(direct_root / "validation" / "html_validation.json", report)
    manifest = {
        "version": "1.0",
        "status": "composed" if report["status"] == "passed" else "contract_failed",
        "animation_mode": "direct-html",
        "created_at": _now(),
        "composition_cache_key": cache_key,
        "input_hash": bundle.get("input_hash"),
        "html_hash": sha256_text(response),
        "prompt_version": PROMPT_VERSION,
        "design_system_version": DESIGN_SYSTEM_VERSION,
        "motion_core_version": MOTION_CORE_VERSION,
        "contract_version": CONTRACT_VERSION,
        "asset_manifest_version": asset_manifest.get("version"),
        "composer": model,
        "repair_counts": {},
        "global_contract_repair_count": contract_repair_count,
        "validation": report["status"],
    }
    write_json(manifest_path, manifest)
    if report["status"] != "passed":
        messages = [item["message"] for item in report["violations"] if item["severity"] == "error"]
        raise RuntimeError(f"Direct-HTML contract validation failed: {messages[:8]}")

    if master_path.exists():
        previous_html = master_path.read_text(encoding="utf-8")
        previous_report = validation_report(
            validate_html(
                previous_html,
                expected_duration=float(bundle["video"]["duration_seconds"]),
                physics_context=physics_context,
            )
        )
        if previous_report["status"] == "passed" and sha256_text(previous_html.strip()) != sha256_text(response.strip()):
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            previous_hash = sha256_text(previous_html)[:12]
            write_text(direct_root / "versions" / f"master_before_composition_{stamp}_{previous_hash}.html", previous_html)
    write_text(master_path, response + "\n")
    index = build_chapter_index(master_path)
    return {"status": "composed", "master": master_path, "manifest": manifest, "chapter_index": index}
