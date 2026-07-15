from __future__ import annotations

import argparse
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

TEMPLATE_LAB_ROOT = Path(__file__).resolve().parents[1]
if str(TEMPLATE_LAB_ROOT) not in sys.path:
    sys.path.insert(0, str(TEMPLATE_LAB_ROOT))

from direct_html.constants import DIRECT_HTML_MODE, LEGACY_MODE
from direct_html.pipeline import (
    build_preview_manifest as build_direct_html_preview_manifest,
    compose as compose_direct_html,
    load_prepared as load_direct_html_prepared,
    prepare_input as prepare_direct_html_input,
    validate_and_inspect as validate_and_inspect_direct_html,
)
from mav_audio import generate_audio, is_live_audio_provider, resolve_audio_provider
from mav_build_preview_v3 import build_preview_v3
from mav_costs import cost_summary_for_run
from mav_inputs import read_facts_payload, read_pipeline_inputs
from mav_plan_v3 import generate_v3_scenes, load_v3_plan_with_scene_files
from mav_schema import (
    TARGET_DURATION_SECONDS,
    raise_if_invalid,
    read_json,
    run_dir,
    validate_narration,
    validate_run_input,
    validation_payload,
    write_json,
)
from mav_script import generate_narration
from mav_timing import derive_timing
from mav_validate_v3 import repair_v3_plan, validate_v3_plan

STEP_LABELS = {
    1: "inputs",
    2: "script",
    3: "audio",
    4: "timing",
    5: "scene_plan",
    6: "validate_repair",
    7: "build_preview",
    8: "qa_handoff",
}


def _model_requested(args: argparse.Namespace) -> bool:
    return bool(args.use_model or args.use_gemini or args.use_claude)


def _configure_model_provider(args: argparse.Namespace) -> str:
    provider = getattr(args, "model_provider", "configured")
    if args.use_gemini and args.use_claude and provider == "configured":
        raise RuntimeError("Choose only one provider shortcut: --use-gemini or --use-claude.")
    if provider != "configured" and (
        (args.use_gemini and provider != "gemini") or (args.use_claude and provider != "anthropic")
    ):
        raise RuntimeError(f"--model-provider {provider} conflicts with the selected provider shortcut.")
    os.environ.setdefault("MAV_V3_CREATIVE_DIRECTOR_PROVIDER", "zai")
    os.environ.setdefault("MAV_V3_CREATIVE_DIRECTOR_MODEL", "glm-5.2")
    os.environ.setdefault("MAV_V3_SCENE_CODER_PROVIDER", "moonshot")
    os.environ.setdefault("MAV_V3_SCENE_CODER_MODEL", "kimi-k2.7-code")
    if provider != "configured":
        os.environ["MAV_MODEL_PROVIDER"] = provider
        return provider
    if args.use_gemini:
        os.environ["MAV_MODEL_PROVIDER"] = "gemini"
        return "gemini"
    if args.use_claude:
        os.environ["MAV_MODEL_PROVIDER"] = "anthropic"
        return "anthropic"
    return os.getenv("MAV_MODEL_PROVIDER", "configured")


def _configure_audio_provider(args: argparse.Namespace) -> str:
    return resolve_audio_provider(
        audio_provider=getattr(args, "audio_provider", "auto"),
        use_elevenlabs=bool(getattr(args, "use_elevenlabs", False)),
        use_gemini_tts=bool(getattr(args, "use_gemini_tts", False)),
    )


def build_input(args: argparse.Namespace) -> dict[str, Any]:
    pipeline_inputs = read_pipeline_inputs() if not args.facts else read_facts_payload(args.facts)
    topic = args.topic or str(pipeline_inputs.get("topic") or "").strip()
    if not topic:
        raise RuntimeError("A topic is required. Pass --topic or include top-level topic in the facts JSON.")
    objective_ids = pipeline_inputs.get("objective_ids", [])
    if not isinstance(objective_ids, list):
        raise RuntimeError("Top-level objective_ids in the facts JSON must be a list.")
    return {
        "run_id": args.run_id,
        "template_id": args.template_id or "physics",
        "topic": topic,
        "topic_ref": str(pipeline_inputs.get("topic_ref") or "").strip(),
        "objective_ids": list(dict.fromkeys(str(value).strip() for value in objective_ids if str(value).strip())),
        "tone": args.tone or pipeline_inputs.get("tone") or "patient, precise IGCSE Physics teacher",
        "target_duration_seconds": float(args.duration),
        "facts": pipeline_inputs["facts"],
        "physics_context": pipeline_inputs.get("physics_context", {}),
        "narrative_mode": pipeline_inputs.get("narrative_mode") or "concept_mastery",
        "animation_mode": getattr(args, "animation_mode", LEGACY_MODE),
    }


def _read_cached_json(path: Path, label: str) -> Any:
    if not path.exists():
        raise RuntimeError(f"Cannot resume: missing cached {label} at {path}")
    return read_json(path)


def _log(message: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] MAV generate: {message}", file=sys.stderr, flush=True)


def _write_narration_files(path: Path, narration: dict[str, Any]) -> None:
    (path / "narration.txt").write_text("\n\n".join(item["text"] for item in narration["paragraphs"]) + "\n", encoding="utf-8")
    (path / "narration_elevenlabs.txt").write_text(narration["elevenlabs_narration"] + "\n", encoding="utf-8")


def _step_summary(
    input_payload: dict[str, Any],
    path: Path,
    step: int,
    artifacts: list[str],
    *,
    mode: str = "v3_generative",
    **extra: Any,
) -> dict[str, Any]:
    summary = {
        "run_id": input_payload["run_id"],
        "mode": mode,
        "run_path": str(path),
        "status": "stopped",
        "stopped_after_step": step,
        "stopped_after": STEP_LABELS[step],
        "next_step": step + 1 if step < 8 else None,
        "artifacts": artifacts,
    }
    summary.update(extra)
    cost_summary = cost_summary_for_run(path)
    if cost_summary:
        summary["cost_summary"] = cost_summary
    write_json(path / "generation_summary.json", summary)
    return summary


def generate_preview(args: argparse.Namespace) -> dict[str, Any]:
    initial_payload = build_input(args)
    os.environ["MAV_RUN_ID"] = initial_payload["run_id"]
    from_step = getattr(args, "from_step", 1)
    stop_after_step = getattr(args, "stop_after_step", 7)
    path = run_dir(initial_payload["run_id"])
    model_provider = _configure_model_provider(args)
    audio_provider = _configure_audio_provider(args)
    animation_mode = getattr(args, "animation_mode", LEGACY_MODE)
    use_model = _model_requested(args)
    if stop_after_step < from_step:
        raise RuntimeError("--stop-after-step must be greater than or equal to --from-step")
    paid_requested = (
        (use_model and ((from_step <= 2 <= stop_after_step) or (from_step <= 5 <= stop_after_step)))
        or (animation_mode == DIRECT_HTML_MODE and bool(getattr(args, "auto_repair", False)) and from_step <= 6 <= stop_after_step)
        or (is_live_audio_provider(audio_provider) and from_step <= 3 <= stop_after_step)
    )
    if not use_model and from_step <= 2 <= stop_after_step:
        raise RuntimeError("Script generation requires --use-model, --use-gemini, or --use-claude.")
    if args.clean and from_step > 1:
        raise RuntimeError("--clean cannot be combined with --from-step > 1 because cached artifacts are required.")
    if paid_requested and not args.confirm_paid_api:
        raise RuntimeError("Paid/API generation requires --confirm-paid-api. Repair/build/QA commands never require paid APIs.")
    if paid_requested and args.clean and path.exists() and not args.force_paid_api:
        raise RuntimeError("Refusing to delete an existing paid/API run cache. Use local repair/build/QA, or pass --force-paid-api if you intentionally want to spend again.")
    if args.clean and path.exists():
        shutil.rmtree(path)

    if from_step <= 1:
        input_payload = initial_payload
        raise_if_invalid(validate_run_input(input_payload))
        path.mkdir(parents=True, exist_ok=True)
        write_json(path / "input.json", input_payload)
    else:
        input_payload = _read_cached_json(path / "input.json", "input payload")
        metadata_updated = False
        for key in ("topic_ref", "objective_ids"):
            if not input_payload.get(key) and initial_payload.get(key):
                input_payload[key] = initial_payload[key]
                metadata_updated = True
        if input_payload.get("animation_mode") != animation_mode:
            input_payload["animation_mode"] = animation_mode
            metadata_updated = True
        if getattr(args, "template_id", "") and input_payload.get("template_id") != args.template_id:
            input_payload["template_id"] = args.template_id
            metadata_updated = True
        if metadata_updated:
            write_json(path / "input.json", input_payload)
        raise_if_invalid(validate_run_input(input_payload))
    if stop_after_step == 1:
        return _step_summary(input_payload, path, 1, ["input.json"])

    if from_step <= 2:
        if use_model and (path / "narration.json").exists() and not args.force_paid_api:
            narration = read_json(path / "narration.json")
            script_source = "cached_narration_json"
        else:
            narration = generate_narration(input_payload, use_model=use_model)
            script_source = "model_generation"
        script_violations = validate_narration(narration, input_payload)
        script_validation = validation_payload(script_violations)
        write_json(path / "debug" / "narration_validation.json", script_validation)
        if os.getenv("MAV_STRICT_NARRATION", "1").strip().lower() not in {"0", "false", "no"}:
            raise_if_invalid(script_violations)
        write_json(path / "narration.json", narration)
        _write_narration_files(path, narration)
    else:
        narration = _read_cached_json(path / "narration.json", "narration")
        script_source = "cached_narration_json"
        script_violations = validate_narration(narration, input_payload)
        script_validation = validation_payload(script_violations)
        write_json(path / "debug" / "narration_validation.json", script_validation)
        if os.getenv("MAV_STRICT_NARRATION", "1").strip().lower() not in {"0", "false", "no"}:
            raise_if_invalid(script_violations)
    write_json(
        path / "debug" / "step_02_script.json",
        {
            "run_id": input_payload["run_id"],
            "from_step": from_step,
            "stop_after_step": stop_after_step,
            "use_model": use_model,
            "model_provider": model_provider,
            "use_claude": args.use_claude,
            "use_gemini": args.use_gemini,
            "force_paid_api": args.force_paid_api,
            "script_source": script_source,
            "cache_exists": (path / "narration.json").exists(),
            "story_skeleton_exists": (path / "story_skeleton.json").exists(),
            "paragraphs": len(narration.get("paragraphs", [])),
            "title": narration.get("title", ""),
            "script_validation": script_validation,
        },
    )
    if stop_after_step == 2:
        artifacts = ["narration.json", "narration.txt", "narration_elevenlabs.txt"]
        if (path / "story_skeleton.json").exists():
            artifacts.insert(0, "story_skeleton.json")
        artifacts.append("debug/step_02_script.json")
        artifacts.append("debug/narration_validation.json")
        if (path / "debug" / "script_generation_debug.json").exists():
            artifacts.append("debug/script_generation_debug.json")
        return _step_summary(input_payload, path, 2, artifacts, paragraphs=len(narration["paragraphs"]), script_source=script_source)

    if from_step <= 3:
        audio_report = generate_audio(
            path,
            narration,
            target_duration=float(input_payload.get("target_duration_seconds", TARGET_DURATION_SECONDS)),
            audio_provider=audio_provider,
        )
    else:
        audio_report = _read_cached_json(path / "audio_generation.json", "audio generation report")
    if stop_after_step == 3:
        return _step_summary(
            input_payload,
            path,
            3,
            ["voiceover.mp3", "audio_generation.json"],
            audio_duration_seconds=audio_report.get("audio_duration_seconds"),
            audio_provider=audio_report.get("provider"),
        )

    if from_step <= 4:
        fallback_duration = float(audio_report.get("audio_duration_seconds") or audio_report["estimated_duration_seconds"])
        timing = derive_timing(path, narration, fallback_duration=fallback_duration)
    else:
        timing = _read_cached_json(path / "audio_timing.json", "audio timing")
    if stop_after_step == 4:
        artifacts = ["audio_timing.json"]
        if (path / "audio_word_timestamps.json").exists():
            artifacts.append("audio_word_timestamps.json")
        return _step_summary(input_payload, path, 4, artifacts, audio_duration_seconds=timing["audio_duration_seconds"])

    if animation_mode == DIRECT_HTML_MODE:
        _log(
            f"direct-HTML mode run={input_payload['run_id']} from_step={from_step} "
            f"stop_after_step={stop_after_step}; narration/audio/timing remain shared with legacy mode"
        )
        if from_step <= 5:
            _log("step 5: building full-lesson input bundle and composing one integrated HTML application")
            prepared = prepare_direct_html_input(path, input_payload, narration, timing)
            composition = compose_direct_html(
                path,
                prepared,
                force=bool(args.force_paid_api),
                allow_model_call=use_model,
            )
        else:
            _log("step 5: loading cached direct-HTML input bundle and master.html")
            prepared = load_direct_html_prepared(path)
            master_path = path / "direct_html" / "master.html"
            if not master_path.exists():
                raise RuntimeError(f"Cannot resume direct HTML: missing {master_path}")
            composition = {"status": "cached", "master": master_path}
        chapter_index = read_json(path / "direct_html" / "chapter_index.json")
        if stop_after_step == 5:
            return _step_summary(
                input_payload,
                path,
                5,
                [
                    "direct_html/lesson_input_bundle.json",
                    "direct_html/asset_manifest.json",
                    "direct_html/physics_context.json",
                    "direct_html/composer_prompt.txt",
                    "direct_html/composer_response.html",
                    "direct_html/master.html",
                    "direct_html/chapter_index.json",
                    "direct_html/generation_manifest.json",
                ],
                mode=DIRECT_HTML_MODE,
                chapters=chapter_index.get("chapter_count", 0),
                composition_status=composition.get("status"),
            )

        if from_step <= 6:
            _log("step 6: validating contract and inspecting real Chromium frames")
            direct_validation = validate_and_inspect_direct_html(
                path,
                prepared,
                browser=not bool(getattr(args, "skip_browser_inspection", False)),
                auto_repair=bool(getattr(args, "auto_repair", False)),
            )
        else:
            direct_validation = {
                "static": read_json(path / "direct_html" / "validation" / "html_validation.json"),
                "inspection": read_json(path / "direct_html" / "validation" / "final_direct_html_report.json")
                if (path / "direct_html" / "validation" / "final_direct_html_report.json").exists()
                else {"status": "not_run"},
            }
        if stop_after_step == 6:
            return _step_summary(
                input_payload,
                path,
                6,
                [
                    "direct_html/validation/html_validation.json",
                    "direct_html/validation/layout_validation.json",
                    "direct_html/validation/timeline_validation.json",
                    "direct_html/validation/design_system_validation.json",
                    "direct_html/validation/final_direct_html_report.json",
                ],
                mode=DIRECT_HTML_MODE,
                chapters=chapter_index.get("chapter_count", 0),
                direct_html_validation=direct_validation.get("inspection", {}).get("status", direct_validation.get("static", {}).get("status")),
            )

        if from_step <= 7:
            manifest_payload = build_direct_html_preview_manifest(path)
        else:
            manifest_payload = _read_cached_json(path / "preview_manifest.json", "direct-HTML preview manifest")
        inspection_status = direct_validation.get("inspection", {}).get("status", "not_run")
        summary = {
            "run_id": input_payload["run_id"],
            "mode": DIRECT_HTML_MODE,
            "animation_mode": DIRECT_HTML_MODE,
            "run_path": str(path),
            "audio_duration_seconds": timing["audio_duration_seconds"],
            "chapters": chapter_index.get("chapter_count", 0),
            "direct_html_validation": inspection_status,
            "manual_review": "required",
            "preview": str(path / manifest_payload["master"]),
            "mp4": "not rendered",
        }
        cost_summary = cost_summary_for_run(path)
        if cost_summary:
            summary["cost_summary"] = cost_summary
        write_json(path / "generation_summary.json", summary)
        return summary

    v3_scene_id = getattr(args, "v3_scene_id", None)
    _log(
        f"V3 mode run={input_payload['run_id']} from_step={from_step} "
        f"stop_after_step={stop_after_step}; cached artifacts through step 4 are being reused when present"
        + (f"; target_scene={v3_scene_id}" if v3_scene_id else "")
    )
    if from_step <= 5:
        if v3_scene_id:
            _log(f"step 5: regenerating only {v3_scene_id} through its cached recipe/module/custom route")
        else:
            _log(
                "step 5: selecting objective-grounded local recipes first; "
                "legacy module/custom routing runs only for uncovered groups when explicitly enabled"
            )
        v3_plan = generate_v3_scenes(
            input_payload,
            narration,
            timing,
            target_scene_id=v3_scene_id,
            allow_model_fallback=use_model,
        )
    else:
        _log("step 5: loading cached scene_plan_v3.json plus editable v3_scenes/*.json overrides")
        v3_plan = load_v3_plan_with_scene_files(path)
    v3_plan, v3_repairs = repair_v3_plan(v3_plan)
    if v3_repairs:
        write_json(path / "scene_plan_v3.json", v3_plan)
        for scene in v3_plan.get("scenes", []):
            if scene.get("id"):
                write_json(path / "v3_scenes" / f"{scene['id']}.json", scene)
        write_json(path / "validation" / "v3_repair_report.json", {"status": "repaired", "repairs": v3_repairs})
        _log(f"step 5 repair: normalized {len(v3_repairs)} V3 scenes before validation")
    _log(f"step 5 complete: V3 plan has {v3_plan['scene_count']} scenes")
    if stop_after_step == 5:
        return _step_summary(
            input_payload,
            path,
            5,
            [
                "asset_index_used.json",
                "asset_shortlist.json",
                "asset_catalog_used.json",
                "scene_routes.json",
                "scene_plan_v3.json",
            ],
            mode="v3_generative",
            scenes=v3_plan["scene_count"],
        )

    validation_path = path / "validation" / "plan_validation_v3.json"
    if from_step <= 6:
        _log("step 6: validating typed recipes plus legacy V3 HTML/GSAP safety constraints")
        v3_violations = validate_v3_plan(v3_plan)
        v3_report = {
            "status": "passed" if not v3_violations else "failed",
            "violations": [violation.to_dict() for violation in v3_violations],
        }
        write_json(validation_path, v3_report)
        _log(f"step 6 complete: validation {v3_report['status']} ({len(v3_violations)} violations)")
        if v3_violations:
            raise RuntimeError(f"V3 validation failed: {[violation.message for violation in v3_violations]}")
    elif validation_path.exists():
        _log("step 6: loading cached validation/plan_validation_v3.json")
        v3_report = read_json(validation_path)
    else:
        _log("step 6: cached validation report missing; validating V3 plan locally")
        v3_violations = validate_v3_plan(v3_plan)
        v3_report = {
            "status": "passed" if not v3_violations else "failed",
            "violations": [violation.to_dict() for violation in v3_violations],
        }
    if stop_after_step == 6:
        return _step_summary(
            input_payload,
            path,
            6,
            ["validation/plan_validation_v3.json", "scene_plan_v3.json"],
            mode="v3_generative",
            plan_validation=v3_report["status"],
            scenes=v3_plan["scene_count"],
        )

    if from_step <= 7:
        _log("step 7: building compositions/master_v3.html")
        manifest_payload = build_preview_v3(path)
    else:
        _log("step 7: loading cached preview_manifest_v3.json")
        manifest_payload = _read_cached_json(path / "preview_manifest_v3.json", "V3 preview manifest")
    _log(f"step 7 complete: preview={manifest_payload['master']}")
    summary = {
        "run_id": input_payload["run_id"],
        "mode": "v3_generative",
        "animation_mode": LEGACY_MODE,
        "run_path": str(path),
        "audio_duration_seconds": timing["audio_duration_seconds"],
        "scenes": v3_plan["scene_count"],
        "plan_validation": v3_report["status"],
        "manual_review": "required",
        "preview": str(path / manifest_payload["master"]),
        "mp4": "not rendered",
    }
    cost_summary = cost_summary_for_run(path)
    if cost_summary:
        summary["cost_summary"] = cost_summary
    write_json(path / "generation_summary.json", summary)
    return summary

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a Physics V3 lesson preview.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--template-id", default="physics", help="Template visual identity. The repo-local default is physics.")
    parser.add_argument("--topic", help="Lesson topic. May instead be supplied at the top level of the facts JSON.")
    parser.add_argument("--facts", type=Path, help="Grounded educational facts JSON. Defaults to template_lab/input/facts.json.")
    parser.add_argument("--tone", default="patient, precise IGCSE Physics teacher")
    parser.add_argument("--duration", type=float, default=480.0, help="Target lesson duration in seconds.")
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--use-model", action="store_true", help="Use the configured live model provider for script generation.")
    parser.add_argument("--use-gemini", action="store_true", help="Use Gemini for script generation.")
    parser.add_argument("--use-claude", action="store_true", help="Use Anthropic/Claude for script generation.")
    parser.add_argument(
        "--model-provider",
        choices=("configured", "gemini", "anthropic", "zai", "moonshot"),
        default="configured",
        help="Override the script provider. Scene providers use their task-specific environment settings.",
    )
    parser.add_argument("--v3", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--animation-mode",
        choices=(DIRECT_HTML_MODE, LEGACY_MODE),
        default=LEGACY_MODE,
        help="Visual production route. Legacy remains the default until the direct-HTML rollout gates pass.",
    )
    parser.add_argument("--v3-scene-id", help="Regenerate or rebuild around one V3 scene id, for example scene_02")
    parser.add_argument("--use-gemini-tts", action="store_true", help="Use Gemini TTS for voiceover audio. This is also the default audio provider.")
    parser.add_argument("--use-elevenlabs", action="store_true", help="Use live ElevenLabs timed TTS for voiceover audio.")
    parser.add_argument(
        "--audio-provider",
        choices=("auto", "gemini", "elevenlabs"),
        default="auto",
        help="Override audio generation provider. auto uses --use-elevenlabs when set, otherwise Gemini TTS.",
    )
    parser.add_argument("--confirm-paid-api", action="store_true", help="Required for any command that may call paid external APIs")
    parser.add_argument("--force-paid-api", action="store_true", help="Allow deleting paid run caches or refreshing paid API artifacts")
    parser.add_argument("--skip-browser-inspection", action="store_true", help="Run static direct-HTML validation without launching Chromium (test/debug only).")
    parser.add_argument("--auto-repair", action="store_true", help="Use the paid repair model for up to two measured repair attempts per failing direct-HTML chapter.")
    parser.add_argument(
        "--from-step",
        type=int,
        default=1,
        choices=range(1, 9),
        help="Resume from step N (1=inputs, 2=script, 3=audio, 4=timing, 5=plan, 6=technical validation, 7=build)",
    )
    parser.add_argument(
        "--stop-after-step",
        type=int,
        default=7,
        choices=range(1, 9),
        help="Stop after step N for one-step-at-a-time debugging.",
    )
    return parser.parse_args()


def main() -> int:
    try:
        summary = generate_preview(parse_args())
    except Exception as exc:
        print(f"MAV generation failed: {exc}", file=sys.stderr)
        return 1
    if summary.get("status") == "stopped":
        print("MAV pipeline step completed.")
        print(f"Run: {summary['run_id']}")
        print(f"Stopped after step {summary['stopped_after_step']}: {summary['stopped_after']}")
        print(f"Run path: {summary['run_path']}")
        if summary.get("artifacts"):
            print("Artifacts:")
            for artifact in summary["artifacts"]:
                print(f"  - {artifact}")
        if summary.get("next_step"):
            print(f"Next: rerun with --from-step {summary['next_step']}")
        return 0
    print("MAV preview generated.")
    print(f"Run: {summary['run_id']}")
    print(f"Mode: {summary.get('mode', 'unknown')}")
    print(f"Audio duration: {summary['audio_duration_seconds']:.2f} seconds")
    print(f"Scenes: {summary['scenes']}")
    if "plan_validation" in summary:
        print(f"Plan validation: {summary['plan_validation']}")
    print("Manual visual review: required")
    print("Preview ready")
    print(f"Render MP4: python3 template_lab/scripts/mav_render.py --run-id {summary['run_id']}")
    print(f"Open with: python3 template_lab/scripts/mav_preview.py --run-id {summary['run_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
