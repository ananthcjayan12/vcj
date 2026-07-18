from __future__ import annotations

import json
import shutil
import sys
import os
import threading
import math
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import candidates as candidate_module
from .audio import align_final_audio, assemble, create_edl, generate_missing_lines
from .captions import write_captions
from .constants import ARCHETYPES
from .context import (
    build_discovery_context,
    build_script_context,
    load_parent_artifacts,
    public_discovery_context,
)
from .portrait import write_cues, write_manifest, write_native_scene
from .prompting import prompts_dir, render_user_prompt
from .provenance import build_provenance, sha256
from .schemas import claim_ids, validate_script
from .script import compile_script, finalize_model_script
from .validation import extract_tsx_source, validate_parent, validate_sources, validate_tsx


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


_MODEL_ENV_LOCK = threading.RLock()


class ShortsPipeline:
    def __init__(self, runs_root: Path, parent_run_id: str):
        self.parent_run_id = parent_run_id
        self.parent = runs_root / parent_run_id
        self.shorts = self.parent / "shorts"
        if not self.parent.is_dir():
            raise FileNotFoundError(f"Parent run not found: {parent_run_id}")

    def _log(self, message: str, short_id: str | None = None) -> None:
        path = self.shorts / short_id / "short.log" if short_id else self.shorts / "shorts.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(f"[{_now()}] {message.rstrip()}\n")

    @contextmanager
    def _model_environment(self):
        selections_path = self.shorts / "models.json"
        selections = _read(selections_path) if selections_path.is_file() else {}
        changes = {"MAV_RUN_ID": self.parent_run_id}
        for task, selection in selections.items():
            prefix = f"MAV_{str(task).upper()}"
            if selection.get("provider"):
                changes[f"{prefix}_PROVIDER"] = str(selection["provider"])
            if selection.get("model"):
                changes[f"{prefix}_MODEL"] = str(selection["model"])
            if selection.get("reasoning_effort"):
                changes[f"{prefix}_CODEX_REASONING_EFFORT"] = str(selection["reasoning_effort"])
        with _MODEL_ENV_LOCK:
            old = {key: os.environ.get(key) for key in changes}
            os.environ.update(changes)
            try:
                yield
            finally:
                for key, value in old.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

    def _model_json(self, task: str, system_file: Path, user: str, *, output_schema: dict[str, Any] | None = None) -> dict[str, Any]:
        scripts = Path(__file__).resolve().parents[1] / "scripts"
        if str(scripts) not in sys.path:
            sys.path.insert(0, str(scripts))
        from mav_models import call_model_json, load_env  # type: ignore
        load_env()
        with self._model_environment():
            result = call_model_json(task=task, system=system_file.read_text(encoding="utf-8"), user=user, output_schema=output_schema)
        if not isinstance(result, dict):
            raise RuntimeError(f"{task} returned no JSON object")
        return result

    def _model_text(self, task: str, system_file: Path, user: str) -> str:
        scripts = Path(__file__).resolve().parents[1] / "scripts"
        if str(scripts) not in sys.path:
            sys.path.insert(0, str(scripts))
        from mav_models import call_model_text, load_env  # type: ignore
        load_env()
        with self._model_environment():
            result = call_model_text(task=task, system=system_file.read_text(encoding="utf-8"), user=user)
        if not result:
            raise RuntimeError(f"{task} returned no source")
        return result

    @staticmethod
    def _candidate_output_schema() -> dict[str, Any]:
        self_scores = {
            "type": "object",
            "properties": {
                "hook_score": {"type": "number"},
                "payoff_score": {"type": "number"},
                "standalone_score": {"type": "number"},
                "exam_relevance_score": {"type": "number"},
            },
        }
        candidate = {
            "type": "object",
            "properties": {
                "concept_key": {"type": "string"},
                "primary_claim_id": {"type": "string"},
                "supporting_claim_ids": {"type": "array", "items": {"type": "string"}},
                "archetype": {"type": "string", "enum": list(ARCHETYPES)},
                "hook_mechanism": {"type": "string"},
                "working_title": {"type": "string"},
                "hook": {"type": "string"},
                "promise": {"type": "string"},
                "payoff": {"type": "string"},
                "target_duration_seconds": {"type": "number"},
                "source_paragraph_ids": {"type": "array", "items": {"type": "string"}},
                "source_beat_ids": {"type": "array", "items": {"type": "string"}},
                "source_reel_ids": {"type": "array", "items": {"type": "string"}},
                "creative_rationale": {"type": "string"},
                "warnings": {"type": "array", "items": {"type": "string"}},
                "self_scores": self_scores,
            },
            "required": [
                "concept_key", "primary_claim_id", "archetype", "hook_mechanism",
                "working_title", "hook", "promise", "payoff", "target_duration_seconds",
                "source_paragraph_ids", "warnings", "self_scores",
            ],
        }
        return {
            "type": "object",
            "properties": {
                "candidates": {"type": "array", "minItems": 6, "maxItems": 8, "items": candidate},
            },
            "required": ["candidates"],
        }

    @staticmethod
    def _short_script_output_schema() -> dict[str, Any]:
        line = {
            "type": "object",
            "properties": {
                "line_id": {"type": "string"},
                "role": {
                    "type": "string",
                    "enum": ["hook", "setup", "context", "tension", "prediction", "explanation", "evidence", "payoff", "answer", "reveal", "loop"],
                },
                "text": {"type": "string"},
                "claim_ids": {"type": "array", "items": {"type": "string"}},
                "audio_source": {"type": "string", "enum": ["generate", "reuse"]},
                "clause_id": {"type": ["string", "null"]},
                "visual_intent": {"type": "string"},
            },
            "required": ["line_id", "role", "text", "claim_ids", "audio_source", "visual_intent"],
        }
        return {
            "type": "object",
            "properties": {
                "version": {"type": "string"},
                "title": {"type": "string"},
                "target_duration_seconds": {"type": "number"},
                "claim_ids": {"type": "array", "items": {"type": "string"}},
                "lines": {"type": "array", "minItems": 4, "maxItems": 8, "items": line},
                "closing_loop": {
                    "type": "object",
                    "properties": {
                        "enabled": {"type": "boolean"},
                        "instruction": {"type": "string"},
                    },
                },
            },
            "required": ["title", "target_duration_seconds", "claim_ids", "lines"],
        }

    def _debug_dir(self, short_id: str | None = None) -> Path:
        path = self.shorts / short_id / "debug" if short_id else self.shorts / "debug"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def analyze(self, *, use_model: bool = False, use_fallback: bool = False) -> dict[str, Any]:
        self._log(f"Candidate analysis started; model={use_model}; fallback={use_fallback}")
        try:
            validate_parent(self.parent)
        except Exception as exc:
            self._log(f"Candidate analysis failed during parent validation: {exc}")
            raise

        artifacts = load_parent_artifacts(self.parent)
        context = build_discovery_context(artifacts, parent_run_id=self.parent_run_id)
        timeline = self.parent / "motion_canvas/timeline.json"
        timeline_id = sha256(timeline if timeline.is_file() else self.parent / "motion_canvas/manifest.json")
        debug = self._debug_dir()
        _write(debug / "discovery_context.json", public_discovery_context(context))

        if use_model and not use_fallback:
            system_path = prompts_dir() / "short_candidate_analysis.system.txt"
            user_path = prompts_dir() / "short_candidate_analysis.user.txt"
            user_prompt = render_user_prompt(
                user_path,
                {"DISCOVERY_CONTEXT_JSON": json.dumps(public_discovery_context(context), ensure_ascii=False, indent=2)},
            )
            if "deterministic_seed_candidates" in user_prompt or "required_schema_example" in user_prompt:
                raise RuntimeError("Anchoring fields leaked into candidate analysis prompt")
            (debug / "candidate_analysis_prompt.txt").write_text(
                f"SYSTEM:\n{system_path.read_text(encoding='utf-8')}\n\nUSER:\n{user_prompt}\n",
                encoding="utf-8",
            )
            try:
                modeled = self._model_json(
                    "short_candidate_analysis",
                    system_path,
                    user_prompt,
                    output_schema=self._candidate_output_schema(),
                )
                _write(debug / "candidate_analysis_response.json", modeled)
                payload = candidate_module.process_model_candidates(
                    list(modeled.get("candidates") or []),
                    context,
                    timeline_id=timeline_id,
                )
                _write(debug / "candidate_analysis_validation.json", {
                    "accepted": len(payload["candidates"]),
                    "rejected": payload.get("rejected_candidates") or [],
                    "raw_candidate_count": payload.get("raw_candidate_count"),
                    "analysis_mode": "model_discovery",
                })
            except Exception as exc:
                message = f"Candidate analysis failed; no fallback was used: {type(exc).__name__}: {exc}"
                self._log(message)
                _write(self.shorts / "candidates.json", {
                    "version": "1.0",
                    "parent_run_id": self.parent_run_id,
                    "created_at": _now(),
                    "source_timeline_id": timeline_id,
                    "status": "failed",
                    "analysis_mode": "model_discovery_failed",
                    "error": message,
                    "candidates": [],
                })
                raise
        else:
            payload = candidate_module.deterministic_fallback_candidates(context, timeline_id=timeline_id)
            payload["parent_run_id"] = self.parent_run_id
            if use_fallback:
                payload["analysis_mode"] = "deterministic_fallback_explicit"
            _write(debug / "candidate_analysis_validation.json", {
                "accepted": len(payload["candidates"]),
                "analysis_mode": payload.get("analysis_mode"),
            })

        payload["parent_run_id"] = self.parent_run_id
        payload["created_at"] = payload.get("created_at") or _now()
        _write(self.shorts / "candidates.json", payload)
        self._registry()
        self._log(f"Candidate analysis completed with {len(payload['candidates'])} candidates ({payload.get('analysis_mode')})")
        return payload

    def analysis_estimate(self) -> dict[str, Any]:
        artifacts = load_parent_artifacts(self.parent)
        context = build_discovery_context(artifacts, parent_run_id=self.parent_run_id)
        public = public_discovery_context(context)
        system_path = prompts_dir() / "short_candidate_analysis.system.txt"
        user_path = prompts_dir() / "short_candidate_analysis.user.txt"
        user_prompt = render_user_prompt(
            user_path,
            {"DISCOVERY_CONTEXT_JSON": json.dumps(public, ensure_ascii=False, indent=2)},
        )
        system_text = system_path.read_text(encoding="utf-8")
        prompt_chars = len(system_text) + len(user_prompt)
        sample_output = {
            "candidates": [
                {
                    "concept_key": "sample",
                    "primary_claim_id": "C1",
                    "supporting_claim_ids": [],
                    "archetype": "misconception",
                    "hook_mechanism": "counterintuitive_question",
                    "working_title": "Sample",
                    "hook": "Sample hook?",
                    "promise": "Sample promise",
                    "payoff": "Sample payoff",
                    "target_duration_seconds": 40,
                    "source_paragraph_ids": ["paragraph_01"],
                    "source_beat_ids": [],
                    "source_reel_ids": [],
                    "creative_rationale": "x" * 80,
                    "warnings": [],
                    "self_scores": {"hook_score": 80, "payoff_score": 80, "standalone_score": 80, "exam_relevance_score": 80},
                }
            ] * 8
        }
        output_chars = len(json.dumps(sample_output, ensure_ascii=False))
        input_tokens = math.ceil(prompt_chars / 2.2)
        expected_output = max(4000, math.ceil(output_chars / 2.2))
        high_output = max(8000, expected_output * 2)
        selections = _read(self.shorts / "models.json") if (self.shorts / "models.json").is_file() else {}
        mapping = _read(prompts_dir() / "prompt_model_mapping.json")["tasks"]["short_candidate_analysis"]
        selected = selections.get("short_candidate_analysis") or {"provider": mapping["provider"], "model": mapping["model"]}
        pricing = _read(Path(__file__).resolve().parents[1] / "model_pricing.json").get("models", {})
        price = pricing.get(f"{selected['provider']}:{selected['model']}") or pricing.get(selected["model"]) or {}
        input_rate, output_rate = float(price.get("input_usd_per_million", 0)), float(price.get("output_usd_per_million", 0))
        cost = lambda output: round((input_tokens * input_rate + output * output_rate) / 1_000_000, 4)
        ledger_path = self.parent / "costs/model_usage.json"
        records = (_read(ledger_path).get("records", []) if ledger_path.is_file() else [])
        observed = next((
            record for record in reversed(records)
            if record.get("task") == "short_candidate_analysis"
            and record.get("provider") == selected["provider"]
            and record.get("model") == selected["model"]
        ), None)
        return {
            "provider": selected["provider"],
            "model": selected["model"],
            "prompt_characters": prompt_chars,
            "estimated_input_tokens": input_tokens,
            "expected_output_tokens": expected_output,
            "high_output_tokens": high_output,
            "configured_max_output_tokens": int(mapping["max_tokens"]),
            "estimated_cost_usd": cost(expected_output),
            "high_estimated_cost_usd": cost(high_output),
            "maximum_estimated_cost_usd": cost(int(mapping["max_tokens"])),
            "last_actual": ({
                "input_tokens": observed.get("input_tokens"),
                "output_tokens": observed.get("output_tokens"),
                "total_tokens": observed.get("total_tokens"),
                "estimated_cost_usd": observed.get("estimated_cost_usd"),
                "timestamp": observed.get("timestamp"),
            } if observed else None),
            "method": "evidence-pack estimate for 6–8 raw discovery candidates; no seed candidates included",
        }

    def _registry(self) -> dict[str, Any]:
        path = self.shorts / "shorts_registry.json"
        data = _read(path) if path.is_file() else {"version": "1.0", "parent_run_id": self.parent_run_id, "shorts": []}
        _write(path, data)
        return data

    def create(self, candidate_id: str, short_id: str, *, use_model: bool = False) -> dict[str, Any]:
        self._log(f"Creating {short_id} from {candidate_id}; model={use_model}")
        if not __import__("re").fullmatch(r"short_[a-zA-Z0-9_-]+", short_id):
            raise ValueError("Invalid Short ID")
        registry = self._registry()
        if any(x.get("short_id") == short_id for x in registry["shorts"]):
            raise FileExistsError(short_id)
        if len([x for x in registry["shorts"] if x.get("status") not in {"deleted", "rendered"}]) >= 3:
            raise RuntimeError("Maximum three active Shorts per parent run")
        source = _read(self.shorts / "candidates.json")
        candidate = next((x for x in source["candidates"] if x["candidate_id"] == candidate_id), None)
        if not candidate:
            raise ValueError(f"Unknown candidate: {candidate_id}")
        root = self.shorts / short_id
        for directory in ("audio/reused_segments", "audio/generated_lines", "motion_canvas/preview", "motion_canvas/frames", "captions", "debug", "costs"):
            (root / directory).mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.shorts / "candidates.json", root / "debug/candidate_source.json")
        existing_script_path = root / "script.json"
        narration = _read(self.parent / "narration.json")
        if existing_script_path.is_file() and _read(existing_script_path).get("candidate_id") == candidate_id:
            script = validate_script(_read(existing_script_path), claim_ids(narration), candidate_claims=set(map(str, candidate.get("claim_ids") or [])))
            self._log(f"Resuming {short_id} with its existing paid script response")
        else:
            artifacts = load_parent_artifacts(self.parent)
            discovery = build_discovery_context(artifacts, parent_run_id=self.parent_run_id)
            script_context = build_script_context(artifacts, candidate, discovery)
            _write(root / "debug/script_context.json", script_context)
            if use_model:
                try:
                    system_path = prompts_dir() / "short_script_writing.system.txt"
                    user_path = prompts_dir() / "short_script_writing.user.txt"
                    user_prompt = render_user_prompt(
                        user_path,
                        {"SCRIPT_CONTEXT_JSON": json.dumps(script_context, ensure_ascii=False, indent=2)},
                    )
                    if "required_schema_example" in user_prompt or "deterministic_seed_candidates" in user_prompt:
                        raise RuntimeError("Anchoring fields leaked into script writing prompt")
                    (root / "debug/script_writing_prompt.txt").write_text(
                        f"SYSTEM:\n{system_path.read_text(encoding='utf-8')}\n\nUSER:\n{user_prompt}\n",
                        encoding="utf-8",
                    )
                    modeled = self._model_json(
                        "short_script_writing",
                        system_path,
                        user_prompt,
                        output_schema=self._short_script_output_schema(),
                    )
                    _write(root / "debug/script_writing_response.json", modeled)
                    script = finalize_model_script(
                        modeled,
                        short_id=short_id,
                        candidate=candidate,
                        narration=narration,
                        clauses=script_context.get("reusable_clauses") or [],
                    )
                    _write(root / "debug/script_writing_validation.json", {
                        "quality_warnings": script.get("quality_warnings") or [],
                        "line_count": len(script.get("lines") or []),
                    })
                except Exception as exc:
                    self._log(f"Short script generation failed; no fallback was used for {short_id}: {type(exc).__name__}: {exc}")
                    raise
            else:
                script = compile_script(candidate, narration)
                script["short_id"] = short_id
        _write(root / "script.json", script)
        _write(root / "plan.json", candidate)
        edl = create_edl(self.parent, root, script, _read(self.parent / "audio_word_timestamps.json"))
        _write(root / "audio/audio_edl.json", edl)
        _write(root / "script.json", script)
        provenance = build_provenance(self.parent, self.parent_run_id, candidate["source_segments"], script["lines"])
        _write(root / "source_provenance.json", provenance)
        write_manifest(root, self.parent_run_id, short_id, script["target_duration_seconds"])
        state = {
            "short_id": short_id,
            "parent_run_id": self.parent_run_id,
            "candidate_id": candidate_id,
            "status": "audio_edl_ready",
            "current_step": 3,
            "created_at": _now(),
            "updated_at": _now(),
            "error": None,
        }
        _write(root / "short_run.json", state)
        registry["shorts"].append(state)
        _write(self.shorts / "shorts_registry.json", registry)
        self._log(f"Created {short_id}; audio EDL ready")
        return state

    def detail(self, short_id: str) -> dict[str, Any]:
        root = self.shorts / short_id
        if not root.is_dir():
            raise FileNotFoundError(short_id)
        return {
            "run": _read(root / "short_run.json"),
            "script": _read(root / "script.json"),
            "plan": _read(root / "plan.json"),
            "manifest": _read(root / "motion_canvas/manifest.json"),
            "provenance": _read(root / "source_provenance.json"),
        }

    def _state(self, short_id: str, *, step: int, status: str, error: str | None = None) -> dict[str, Any]:
        root = self.shorts / short_id
        state = _read(root / "short_run.json")
        state.update({"current_step": step, "status": status, "updated_at": _now(), "error": error})
        _write(root / "short_run.json", state)
        registry = self._registry()
        registry["shorts"] = [state if item.get("short_id") == short_id else item for item in registry["shorts"]]
        _write(self.shorts / "shorts_registry.json", registry)
        return state

    def generate(self, short_id: str, *, from_step: int = 1, stop_after_step: int = 7,
                 audio_provider: str = "gemini", force: set[str] | None = None, use_model: bool = False) -> dict[str, Any]:
        root = self.shorts / short_id
        force = force or set()
        detail = self.detail(short_id)
        validate_sources(self.parent, detail["provenance"])
        script = detail["script"]
        try:
            if from_step <= 4 <= stop_after_step:
                if "audio" in force:
                    for path in (root / "audio/generated_lines").glob("*.wav"):
                        path.unlink()
                self._log("Generating missing audio lines", short_id)
                with self._model_environment():
                    generate_missing_lines(root, script, provider=audio_provider)
                assemble(root, _read(root / "audio/audio_edl.json"))
                self._state(short_id, step=4, status="audio_assembled")
            if from_step <= 5 <= stop_after_step:
                timing = align_final_audio(root, script)
                self._state(short_id, step=5, status="word_timing_ready")
            else:
                timing_path = root / "audio/audio_word_timestamps.json"
                timing = _read(timing_path) if timing_path.is_file() else {
                    "audio_duration_seconds": script["target_duration_seconds"],
                    "words": [],
                }
            if from_step <= 6 <= stop_after_step:
                write_captions(root / "captions", timing)
                self._state(short_id, step=6, status="captions_ready")
            if from_step <= 7 <= stop_after_step:
                duration = float(timing.get("audio_duration_seconds") or script["target_duration_seconds"])
                write_manifest(root, self.parent_run_id, short_id, duration)
                write_cues(root, short_id, timing, duration)
                scene = write_native_scene(root, short_id, script, timing)
                if use_model:
                    provenance = detail["provenance"]
                    sources = []
                    for record in provenance.get("source_reels") or []:
                        source_path = next((
                            self.parent / "motion_canvas" / directory / f"{record['reel_id']}.tsx"
                            for directory in ("reels", "shots", "chapters")
                            if (self.parent / "motion_canvas" / directory / f"{record['reel_id']}.tsx").is_file()
                        ), None)
                        if source_path:
                            sources.append({"id": record["reel_id"], "tsx": source_path.read_text(encoding="utf-8")})
                    adapter_prompt = json.dumps({
                        "short_id": short_id,
                        "script": script,
                        "word_timestamps": timing,
                        "source_visuals": sources,
                        "approved_api": (Path(__file__).resolve().parent / "prompts/portrait-approved-api.md").read_text(encoding="utf-8"),
                        "fallback_example": scene.read_text(encoding="utf-8"),
                    })
                    (root / "debug/visual_adapter_prompt.txt").write_text(adapter_prompt, encoding="utf-8")
                    response = self._model_text(
                        "short_motion_canvas_adapter",
                        Path(__file__).resolve().parent / "prompts/portrait_adapter.system.txt",
                        adapter_prompt,
                    )
                    (root / "debug/visual_adapter_response.txt").write_text(response, encoding="utf-8")
                    scene.write_text(extract_tsx_source(response), encoding="utf-8")
                sanitize_notes = validate_tsx(scene, short_id, sanitize=True)
                _write(root / "motion_canvas/validation.json", {
                    "status": "passed",
                    "checks": ["schema", "provenance", "portrait_static"],
                    "sanitize_notes": sanitize_notes,
                })
                self._state(short_id, step=7, status="preview_ready")
                self._log("Portrait visuals ready for live preview", short_id)
            return self.detail(short_id)
        except Exception as exc:
            self._log(f"Generation failed: {type(exc).__name__}: {exc}", short_id)
            current = int(_read(root / "short_run.json").get("current_step", 0))
            self._state(short_id, step=current, status="failed", error=str(exc))
            raise
