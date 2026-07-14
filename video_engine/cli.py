from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
ENGINE_ROOT = Path(__file__).resolve().parent
SYLLABUS_PATH = REPO_ROOT / "pilot" / "output" / "syllabus_topics.json"
QUESTION_INDEX_PATH = REPO_ROOT / "pilot" / "index_output" / "question_index.sqlite3"
ANIMATION_REGISTRY_PATH = REPO_ROOT / "physics_animation_engine" / "modules" / "_registry.js"
ANIMATION_CATALOG_SCRIPT = REPO_ROOT / "physics_animation_engine" / "scripts" / "export-catalog.mjs"
TEMPLATE_LAB_ROOT = REPO_ROOT / "template_lab"
CURRICULUM_DIR = ENGINE_ROOT / "curriculum"
REGISTRY_DIR = ENGINE_ROOT / "registry"
TOPICS_DIR = ENGINE_ROOT / "topics"
COVERAGE_PATH = CURRICULUM_DIR / "coverage_registry.json"

VALID_STATES = (
    "uncovered",
    "planned",
    "scripted",
    "rendered",
    "reviewed",
    "covered",
    "needs_revision",
)

TOPIC_ORDER = (
    "1.1", "1.2", "1.3", "1.4", "1.5.1", "1.5.2", "1.5.3", "1.6",
    "1.7.1", "1.7.2", "1.7.4", "1.7.3", "1.8",
    "2.1.1", "2.1.2", "2.1.3", "2.2.1", "2.2.2", "2.2.3", "2.3.1",
    "2.3.2", "2.3.3", "2.3.4",
    "3.1", "3.4", "3.2.1", "3.2.2", "3.2.3", "3.2.4", "3.3",
    "4.2.1", "4.2.2", "4.2.3", "4.2.4", "4.3.1", "4.3.2", "4.3.3",
    "4.2.5", "4.4", "4.1", "4.5.3", "4.5.4", "4.5.5", "4.5.1",
    "4.5.2", "4.5.6",
    "5.1.1", "5.1.2", "5.2.1", "5.2.2", "5.2.3", "5.2.4", "5.2.5",
    "6.1.1", "6.1.2", "6.2.1", "6.2.2", "6.2.3",
)

SCENE_METADATA: dict[str, tuple[str, str]] = {
    "Scene_TitleCard": ("lesson_structure", "Open a lesson or section with a concise title and subtitle."),
    "Scene_SummaryCard": ("lesson_structure", "Close a section with compact retrieval points."),
    "Scene_DefinitionCard": ("lesson_structure", "Introduce a definition with symbols, units, and a focused visual hierarchy."),
    "Scene_ComparisonTable": ("lesson_structure", "Compare two or more cases without repeating prose."),
    "Scene_MathEquation": ("mathematics", "Reveal and explain a physics equation step by step."),
    "Scene_NumericalExample": ("mathematics", "Show a traceable worked calculation with explicit reasoning steps."),
    "Scene_GraphPlotter": ("graphs", "Plot labelled data and animate how a graph is read."),
    "Scene_SankeyDiagram": ("energy", "Visualise energy input, useful output, and waste flows."),
    "Scene_EnergyBars": ("energy", "Compare energy stores or transfers with animated bars."),
    "Scene_ForceDiagram": ("mechanics", "Draw an object, surface, force vectors, net force, and acceleration."),
    "Scene_CollisionBlocks": ("mechanics", "Visualise before-and-after motion in momentum collisions."),
    "Scene_ProjectileMotion": ("mechanics", "Trace projectile motion with horizontal and vertical components."),
    "Scene_CircularMotion": ("mechanics", "Show tangential velocity and inward centripetal force."),
    "Scene_SpringMass": ("mechanics", "Animate a spring-mass system, restoring force, and optional graph."),
    "Scene_InclinedPlane": ("mechanics", "Resolve forces for an object on an inclined plane."),
    "Scene_OrbitalMotion": ("space", "Visualise orbital velocity and gravitational force vectors."),
    "Scene_WaveForm": ("waves", "Animate transverse or longitudinal wave properties."),
    "Scene_WaveBehavior": ("waves", "Demonstrate reflection, refraction, diffraction, or superposition."),
    "Scene_StandingWave": ("waves", "Show harmonics, nodes, and antinodes on a standing wave."),
    "Scene_EMSpectrum": ("waves", "Navigate the electromagnetic spectrum, wavelengths, and uses."),
    "Scene_RayDiagram": ("optics", "Draw principal rays for lenses, mirrors, or a prism."),
    "Scene_ParticleModel": ("thermal", "Animate solid, liquid, or gas particle arrangements and motion."),
    "Scene_GasParticles": ("thermal", "Relate gas particle motion to temperature, volume, and pressure."),
    "Scene_ThermalHeating": ("thermal", "Show heating curves, temperature change, and energy transfer."),
    "Scene_CircuitDiagram": ("electricity", "Build and animate a circuit from recognised components."),
    "Scene_ElectronFlow": ("electricity", "Contrast electron drift, current, and resistance effects."),
    "Scene_MagneticField": ("magnetism", "Draw magnetic field patterns around magnets or conductors."),
    "Scene_MotorEffect": ("electromagnetism", "Connect field, current, and force directions in the motor effect."),
    "Scene_EMInduction": ("electromagnetism", "Show induced current from changing magnetic flux."),
    "Scene_Transformer": ("electromagnetism", "Relate turns ratio, voltage, and changing core field."),
    "Scene_AtomicModel": ("nuclear", "Build the atomic model with nucleus, electrons, and labels."),
    "Scene_NuclearDecay": ("nuclear", "Animate alpha, beta, or gamma emission from a nucleus."),
    "Scene_NuclearReaction": ("nuclear", "Show reactants, products, and energy in fission or fusion."),
    "Scene_RadiationPenetration": ("nuclear", "Compare alpha, beta, and gamma penetration through barriers."),
    "Scene_StarLifeCycle": ("space", "Trace the ordered stages of average or massive stars."),
}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def _load_syllabus() -> dict[str, Any]:
    if not SYLLABUS_PATH.exists():
        raise RuntimeError(f"Missing syllabus source: {SYLLABUS_PATH}")
    payload = _read_json(SYLLABUS_PATH)
    topics = payload.get("topics")
    if not isinstance(topics, list) or not topics:
        raise RuntimeError(f"Invalid syllabus topics in {SYLLABUS_PATH}")
    return payload


def _objective_records(syllabus: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for topic in syllabus["topics"]:
        for route, key, prefix in (
            ("core", "core_objectives", "C"),
            ("supplement", "supplement_objectives", "S"),
        ):
            for objective in topic.get(key, []):
                number = int(objective["number"])
                records.append(
                    {
                        "objective_id": f"{topic['ref']}-{prefix}{number:02d}",
                        "topic_ref": topic["ref"],
                        "topic_title": topic["title"],
                        "domain_ref": topic["domain_ref"],
                        "domain_title": topic["domain_title"],
                        "route": route,
                        "objective_number": number,
                        "objective_text": objective["text"],
                    }
                )
    return records


def _registered_scenes() -> list[dict[str, Any]]:
    text = ANIMATION_REGISTRY_PATH.read_text(encoding="utf-8")
    imports = re.findall(r"import \{ (Scene_[A-Za-z0-9_]+) \} from '([^']+)'", text)
    schemas: dict[str, Any] = {}
    node = shutil.which("node")
    if node and ANIMATION_CATALOG_SCRIPT.exists():
        try:
            result = subprocess.run(
                [node, str(ANIMATION_CATALOG_SCRIPT)],
                check=True,
                capture_output=True,
                text=True,
                timeout=20,
                cwd=REPO_ROOT,
            )
            schemas = json.loads(result.stdout)
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
            schemas = {}

    examples: dict[str, list[str]] = {scene: [] for scene, _module in imports}
    specs_root = REPO_ROOT / "physics_animation_engine" / "specs"
    for spec_path in sorted(specs_root.rglob("*.json")):
        try:
            spec = _read_json(spec_path)
        except (OSError, json.JSONDecodeError):
            continue
        relative = str(spec_path.relative_to(REPO_ROOT))
        for slide in spec.get("slides", []):
            scene = slide.get("scene")
            if scene in examples and relative not in examples[scene]:
                examples[scene].append(relative)

    scenes: list[dict[str, Any]] = []
    for scene, module in imports:
        category, description = SCENE_METADATA.get(scene, ("other", scene.removeprefix("Scene_").replace("_", " ")))
        item: dict[str, Any] = {
            "scene": scene,
            "category": category,
            "description": description,
            "module": f"physics_animation_engine/modules/{module.removeprefix('./')}",
            "status": "available",
            "example_specs": examples[scene],
        }
        if scene in schemas:
            item["parameter_schema"] = schemas[scene]
        scenes.append(item)
    return scenes


def _coverage_payload(records: list[dict[str, Any]], existing: dict[str, Any] | None = None) -> dict[str, Any]:
    old_objectives = (existing or {}).get("objectives", {})
    objectives: dict[str, Any] = {}
    for record in records:
        objective_id = record["objective_id"]
        old = old_objectives.get(objective_id, {})
        state = old.get("status", "uncovered")
        if state not in VALID_STATES:
            state = "needs_revision"
        objectives[objective_id] = {
            "status": state,
            "primary_video_id": old.get("primary_video_id"),
            "reinforcement_video_ids": old.get("reinforcement_video_ids", []),
            "updated_at": old.get("updated_at"),
        }
    return {
        "schema_version": 1,
        "syllabus": "Cambridge IGCSE Physics 0625",
        "valid_states": list(VALID_STATES),
        "updated_at": _now(),
        "objectives": objectives,
    }


def cmd_init(args: argparse.Namespace) -> int:
    syllabus = _load_syllabus()
    records = _objective_records(syllabus)
    syllabus_refs = {topic["ref"] for topic in syllabus["topics"]}
    if len(TOPIC_ORDER) != len(set(TOPIC_ORDER)) or set(TOPIC_ORDER) != syllabus_refs:
        missing = sorted(syllabus_refs - set(TOPIC_ORDER))
        extra = sorted(set(TOPIC_ORDER) - syllabus_refs)
        raise RuntimeError(f"Topic order does not match syllabus; missing={missing}, extra={extra}")

    existing = _read_json(COVERAGE_PATH) if COVERAGE_PATH.exists() and not args.reset_coverage else None
    _write_json(
        CURRICULUM_DIR / "objectives.json",
        {
            "schema_version": 1,
            "syllabus": syllabus.get("syllabus", "Cambridge IGCSE Physics 0625"),
            "topic_count": len(syllabus["topics"]),
            "objective_count": len(records),
            "objectives": records,
        },
    )
    topics_by_ref = {topic["ref"]: topic for topic in syllabus["topics"]}
    _write_json(
        CURRICULUM_DIR / "topic_order.json",
        {
            "schema_version": 1,
            "strategy": "prerequisite-aware manual production order",
            "topics": [
                {
                    "position": index,
                    "ref": ref,
                    "title": topics_by_ref[ref]["title"],
                    "domain_ref": topics_by_ref[ref]["domain_ref"],
                }
                for index, ref in enumerate(TOPIC_ORDER, 1)
            ],
        },
    )
    _write_json(COVERAGE_PATH, _coverage_payload(records, existing))
    _write_json(
        REGISTRY_DIR / "animation_assets.json",
        {
            "schema_version": 1,
            "source": "repo-local physics_animation_engine/modules/_registry.js",
            "scene_count": len(_registered_scenes()),
            "scenes": _registered_scenes(),
        },
    )
    for filename, key in (
        ("videos.json", "videos"),
        ("original_questions.json", "questions"),
        ("content_fingerprints.json", "fingerprints"),
    ):
        path = REGISTRY_DIR / filename
        if not path.exists() or args.reset_registries:
            _write_json(path, {"schema_version": 1, key: []})

    action = "reset" if args.reset_coverage else "initialized"
    print(f"Curriculum {action}: {len(syllabus['topics'])} topics, {len(records)} objectives, {len(_registered_scenes())} scenes.")
    print(f"Coverage registry: {COVERAGE_PATH.relative_to(REPO_ROOT)}")
    return 0


def _require_registry() -> tuple[dict[str, Any], dict[str, Any]]:
    objectives_path = CURRICULUM_DIR / "objectives.json"
    if not objectives_path.exists() or not COVERAGE_PATH.exists():
        raise RuntimeError("Curriculum registries do not exist. Run: python3 -m video_engine.cli init")
    return _read_json(objectives_path), _read_json(COVERAGE_PATH)


def _topic_progress() -> list[dict[str, Any]]:
    objectives_payload, coverage = _require_registry()
    records = objectives_payload["objectives"]
    by_topic: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_topic.setdefault(record["topic_ref"], []).append(record)
    result = []
    for position, ref in enumerate(TOPIC_ORDER, 1):
        topic_records = by_topic[ref]
        states = Counter(coverage["objectives"][item["objective_id"]]["status"] for item in topic_records)
        result.append(
            {
                "position": position,
                "ref": ref,
                "title": topic_records[0]["topic_title"],
                "total": len(topic_records),
                "covered": states["covered"],
                "states": dict(states),
                "complete": states["covered"] == len(topic_records),
            }
        )
    return result


def cmd_status(args: argparse.Namespace) -> int:
    objectives_payload, coverage = _require_registry()
    counts = Counter(item["status"] for item in coverage["objectives"].values())
    progress = _topic_progress()
    complete_topics = sum(1 for topic in progress if topic["complete"])
    print(f"Topics: {complete_topics}/{len(progress)} complete")
    print(f"Objectives: {counts['covered']}/{objectives_payload['objective_count']} covered")
    print("States: " + ", ".join(f"{state}={counts[state]}" for state in VALID_STATES if counts[state]))
    if args.topic:
        topic = next((item for item in progress if item["ref"] == args.topic), None)
        if not topic:
            raise RuntimeError(f"Unknown topic ref: {args.topic}")
        print(f"{topic['ref']} {topic['title']}: {topic['covered']}/{topic['total']} covered")
        for state, count in sorted(topic["states"].items()):
            print(f"  {state}: {count}")
    else:
        next_topic = next((item for item in progress if not item["complete"]), None)
        if next_topic:
            print(f"Next topic: {next_topic['ref']} {next_topic['title']}")
    return 0


def cmd_next_topic(_args: argparse.Namespace) -> int:
    topic = next((item for item in _topic_progress() if not item["complete"]), None)
    if not topic:
        print("All syllabus topics are covered.")
        return 0
    print(f"{topic['ref']}\t{topic['title']}\t{topic['covered']}/{topic['total']} objectives covered")
    return 0


def _assessment_pattern_summary(topic_ref: str) -> tuple[int, list[str]]:
    if not QUESTION_INDEX_PATH.exists():
        return 0, []
    with sqlite3.connect(QUESTION_INDEX_PATH) as connection:
        rows = connection.execute(
            """
            SELECT command_word, question_type, difficulty, has_visual
            FROM questions
            WHERE topic_ref = ?
            """,
            (topic_ref,),
        ).fetchall()
    if not rows:
        return 0, []
    command_words = Counter(row[0] for row in rows if row[0] and row[0] != "unknown")
    question_types = Counter(row[1] for row in rows if row[1] and row[1] != "unknown")
    difficulties = Counter(row[2] for row in rows if row[2] and row[2] != "unknown")
    visual_count = sum(int(row[3] or 0) for row in rows)
    facts = [
        f"The private index contains {len(rows)} top-level questions classified to this topic; use this only as aggregate assessment-pattern evidence.",
    ]
    if command_words:
        facts.append("Most frequent command words: " + ", ".join(f"{name} ({count})" for name, count in command_words.most_common(6)) + ".")
    if question_types:
        facts.append("Most frequent classified question types: " + ", ".join(f"{name} ({count})" for name, count in question_types.most_common(6)) + ".")
    if difficulties:
        facts.append("Classified difficulty mix: " + ", ".join(f"{name} ({count})" for name, count in difficulties.most_common()) + ".")
    facts.append(f"{visual_count} of these classified questions contain a diagram, graph, table, or other visual.")
    return len(rows), facts


def cmd_prepare_topic(args: argparse.Namespace) -> int:
    objectives_payload, coverage = _require_registry()
    records = [item for item in objectives_payload["objectives"] if item["topic_ref"] == args.topic_ref]
    if not records:
        raise RuntimeError(f"Unknown topic ref: {args.topic_ref}")
    remaining = [item for item in records if coverage["objectives"][item["objective_id"]]["status"] != "covered"]
    selected = records if args.include_covered else remaining
    if not selected:
        print(f"{args.topic_ref} is already fully covered; no facts packet created.")
        return 0

    topic_dir = TOPICS_DIR / args.topic_ref
    facts_path = topic_dir / "facts.json"
    if facts_path.exists() and not args.force:
        raise RuntimeError(f"Refusing to overwrite {facts_path}. Pass --force to rebuild it.")

    facts: list[dict[str, str]] = [
        {
            "id": "syllabus_topic",
            "text": f"Cambridge IGCSE Physics 0625 topic {args.topic_ref}: {records[0]['topic_title']}.",
            "source": "pilot/output/syllabus_topics.json",
        }
    ]
    for record in selected:
        route_label = "Core" if record["route"] == "core" else "Supplement"
        facts.append(
            {
                "id": record["objective_id"].replace(".", "_").replace("-", "_"),
                "text": f"{route_label} syllabus objective {record['objective_id']}: {record['objective_text']}",
                "source": "pilot/output/syllabus_topics.json",
            }
        )
    question_count, pattern_facts = _assessment_pattern_summary(args.topic_ref)
    for index, text in enumerate(pattern_facts, 1):
        facts.append(
            {
                "id": f"private_assessment_pattern_{index:02d}",
                "text": text,
                "source": "private aggregate from pilot/index_output/question_index.sqlite3",
            }
        )
    facts.append(
        {
            "id": "originality_boundary",
            "text": "Past-paper records are private pattern evidence only. Create original examples, numbers, diagrams, and questions; never quote or closely paraphrase a source question or mark scheme.",
            "source": "engine policy",
        }
    )
    payload = {
        "schema_version": 1,
        "topic": f"{args.topic_ref} {records[0]['topic_title']}",
        "topic_ref": args.topic_ref,
        "tone": "patient, precise IGCSE Physics teacher",
        "narrative_mode": "concept_mastery",
        "objective_ids": [item["objective_id"] for item in selected],
        "private_question_count": question_count,
        "facts": facts,
    }
    _write_json(facts_path, payload)
    print(f"Prepared {facts_path.relative_to(REPO_ROOT)}")
    print(f"Objectives included: {len(selected)}; private question patterns: {question_count}")
    run_id = f"physics-{args.topic_ref.replace('.', '-')}-v01"
    print("Generate manually with:")
    print(
        "python3 template_lab/scripts/mav_generate.py "
        f"--run-id {run_id} --facts {facts_path.relative_to(REPO_ROOT)} "
        "--v3 --use-gemini --use-gemini-tts --confirm-paid-api"
    )
    return 0


def cmd_set_status(args: argparse.Namespace) -> int:
    objectives_payload, coverage = _require_registry()
    known = {item["objective_id"] for item in objectives_payload["objectives"]}
    selected: list[str]
    if args.topic:
        selected = [item["objective_id"] for item in objectives_payload["objectives"] if item["topic_ref"] == args.topic]
        if not selected:
            raise RuntimeError(f"Unknown topic ref: {args.topic}")
    else:
        selected = args.objective_ids
    unknown = sorted(set(selected) - known)
    if unknown:
        raise RuntimeError(f"Unknown objective IDs: {', '.join(unknown)}")
    timestamp = _now()
    for objective_id in selected:
        coverage["objectives"][objective_id]["status"] = args.status
        coverage["objectives"][objective_id]["updated_at"] = timestamp
    coverage["updated_at"] = timestamp
    _write_json(COVERAGE_PATH, coverage)
    print(f"Updated {len(selected)} objective(s) to {args.status}.")
    return 0


def _command_version(command: str, *arguments: str) -> tuple[bool, str]:
    path = shutil.which(command)
    if not path:
        return False, "not found"
    try:
        result = subprocess.run([path, *arguments], capture_output=True, text=True, timeout=10, check=False)
        output = (result.stdout or result.stderr).strip().splitlines()
        return result.returncode == 0, output[0] if output else path
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def _module_available(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ModuleNotFoundError, AttributeError):
        return False


def _node_check() -> tuple[bool, str]:
    candidates: list[Path] = []
    if shutil.which("node"):
        candidates.append(Path(shutil.which("node") or ""))
    versions = Path.home() / ".nvm" / "versions" / "node"
    if versions.exists():
        candidates.extend(
            sorted(
                versions.glob("v*/bin/node"),
                key=lambda path: tuple(int(part) for part in re.findall(r"\d+", path.parts[-3])[:3]),
                reverse=True,
            )
        )
    for candidate in candidates:
        try:
            output = subprocess.run([str(candidate), "--version"], capture_output=True, text=True, timeout=5, check=True).stdout.strip()
            match = re.match(r"v(\d+)(?:\.(\d+))?(?:\.(\d+))?", output)
            version = tuple(int(part or 0) for part in match.groups()) if match else (0, 0, 0)
            if version >= (22, 12, 0) and (candidate.parent / "npm").exists():
                return True, f"{output} at {candidate}"
        except Exception:  # noqa: BLE001
            continue
    return False, "Node 22.12+ with npm not found"


def cmd_doctor(_args: argparse.Namespace) -> int:
    checks: list[tuple[str, bool, str, bool]] = []
    try:
        syllabus = _load_syllabus()
        checks.append(("syllabus", len(syllabus["topics"]) == 58, f"{len(syllabus['topics'])} topics", True))
        checks.append(("objectives", len(_objective_records(syllabus)) == 328, f"{len(_objective_records(syllabus))} objectives", True))
    except Exception as exc:  # noqa: BLE001
        checks.append(("syllabus", False, str(exc), True))
    checks.append(("question index", QUESTION_INDEX_PATH.exists(), str(QUESTION_INDEX_PATH.relative_to(REPO_ROOT)), True))
    try:
        scene_count = len(_registered_scenes())
        checks.append(("animation scenes", scene_count == 35, f"{scene_count} registered", True))
    except Exception as exc:  # noqa: BLE001
        checks.append(("animation scenes", False, str(exc), True))
    checks.append(("Template Lab", (TEMPLATE_LAB_ROOT / "scripts" / "mav_generate.py").exists(), "repo-local", True))
    checks.append(("physics template", (TEMPLATE_LAB_ROOT / "templates" / "physics" / "config.json").exists(), "repo-local", True))
    checks.append(
        (
            "animation browser deps",
            (REPO_ROOT / "physics_animation_engine" / "node_modules" / "gsap" / "dist" / "gsap.min.js").exists()
            and (REPO_ROOT / "physics_animation_engine" / "node_modules" / "katex" / "dist" / "katex.min.js").exists(),
            "local GSAP and KaTeX",
            True,
        )
    )
    checks.append(
        (
            "HyperFrames",
            (TEMPLATE_LAB_ROOT / "node_modules" / ".bin" / "hyperframes").exists(),
            "pinned repo-local renderer",
            True,
        )
    )

    node_ok, node_detail = _node_check()
    checks.append(("Node/npm", node_ok, node_detail, True))
    for binary, arguments in (("ffmpeg", ("-version",)), ("ffprobe", ("-version",))):
        ok, detail = _command_version(binary, *arguments)
        checks.append((binary, ok, detail, True))
    checks.append(("google-genai", _module_available("google.genai"), "Python package", False))
    checks.append(("Whisper", _module_available("whisper"), "Python package", False))

    external_source = "/Users/ananthu/Desktop/" + "new_repos"
    offenders: list[str] = []
    for root in (REPO_ROOT / "physics_animation_engine", TEMPLATE_LAB_ROOT, ENGINE_ROOT):
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in {".py", ".js", ".json", ".html", ".css", ".md", ".txt"}:
                try:
                    if external_source in path.read_text(encoding="utf-8"):
                        offenders.append(str(path.relative_to(REPO_ROOT)))
                except UnicodeDecodeError:
                    pass
    checks.append(("source-repo independence", not offenders, ", ".join(offenders) if offenders else "no old absolute paths", True))

    for name, ok, detail, required in checks:
        severity = "OK" if ok else ("FAIL" if required else "WARN")
        print(f"[{severity:4}] {name}: {detail}")
    required_failures = [name for name, ok, _detail, required in checks if required and not ok]
    if required_failures:
        print("Required failures: " + ", ".join(required_failures), file=sys.stderr)
        return 1
    print("Core local engine is ready. WARN items are needed only for live model/audio generation.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Control curriculum coverage and prepare manual IGCSE Physics video runs.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Build local curriculum and asset registries.")
    init_parser.add_argument("--reset-coverage", action="store_true", help="Reset every objective to uncovered.")
    init_parser.add_argument("--reset-registries", action="store_true", help="Reset video, question, and fingerprint registries.")
    init_parser.set_defaults(func=cmd_init)

    status_parser = subparsers.add_parser("status", help="Show coverage progress.")
    status_parser.add_argument("--topic", help="Show one topic ref in detail.")
    status_parser.set_defaults(func=cmd_status)

    next_parser = subparsers.add_parser("next-topic", help="Print the next incomplete topic in production order.")
    next_parser.set_defaults(func=cmd_next_topic)

    prepare_parser = subparsers.add_parser("prepare-topic", help="Create a grounded facts packet for one manual run.")
    prepare_parser.add_argument("topic_ref")
    prepare_parser.add_argument("--include-covered", action="store_true")
    prepare_parser.add_argument("--force", action="store_true")
    prepare_parser.set_defaults(func=cmd_prepare_topic)

    status_setter = subparsers.add_parser("set-status", help="Manually update objective coverage state.")
    target = status_setter.add_mutually_exclusive_group(required=True)
    target.add_argument("--topic", help="Update every objective in a topic.")
    target.add_argument("--objective-ids", nargs="+", help="Update explicit stable objective IDs.")
    status_setter.add_argument("--status", required=True, choices=VALID_STATES)
    status_setter.set_defaults(func=cmd_set_status)

    doctor_parser = subparsers.add_parser("doctor", help="Check local sources and full-render dependencies.")
    doctor_parser.set_defaults(func=cmd_doctor)
    return parser


def main() -> int:
    try:
        args = build_parser().parse_args()
        return int(args.func(args))
    except (RuntimeError, ValueError, OSError, json.JSONDecodeError, sqlite3.Error) as exc:
        print(f"video_engine: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
