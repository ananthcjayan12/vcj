from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
for path in (ROOT, ROOT / "scripts"):
    sys.path.insert(0, str(path))

from direct_html.asset_manifest import prepare_runtime_assets
from direct_html.browser_inspector import inspect_lesson
from direct_html.chapter_index import build_chapter_index
from direct_html.composer import compose_lesson
from direct_html.contrast import essential_contrast_report
from direct_html.direct_html_validator import validate_html, validation_report
from direct_html.html_contract import extract_chapter_blocks
from direct_html.io_utils import sync_direct_cost_records
from direct_html.prompt_builder import composer_system_prompt, repair_system_prompt, review_system_prompt
from direct_html.render_adapter import DIRECT_HTML_MODE, LEGACY_MODE, animation_mode_for_run, composition_for_run, write_render_copy
from direct_html.repair_loop import replace_chapter
from direct_html.review_gate import REVIEW_CATEGORIES, evaluate_visual_review

FIXTURES = ROOT / "tests" / "fixtures" / "direct_html"


class PromptContractTest(unittest.TestCase):
    def test_prompts_define_modern_science_identity_and_forbid_legacy_style(self) -> None:
        composer = composer_system_prompt()
        for prompt in (composer, repair_system_prompt(), review_system_prompt()):
            for token in ("--science-bg-deep", "--science-cyan", "--science-green", "--font-ui"):
                self.assertIn(token, prompt)
            self.assertIn("paper", prompt.lower())
            self.assertIn("notebook", prompt.lower())
        for term in ("wood", "grain", "vignette", "heading plus three boxes"):
            self.assertIn(term, composer.lower())
        self.assertIn("replacement block", repair_system_prompt())
        self.assertIn("destructured function parameter", composer)
        self.assertIn("modern_platform_polish", review_system_prompt())


class ContractValidationTest(unittest.TestCase):
    def test_essential_token_pairs_meet_wcag_aa_contrast(self) -> None:
        report = essential_contrast_report()
        self.assertEqual(report["status"], "passed", report)
        self.assertTrue(all(item["ratio"] >= 4.5 for item in report["checks"]))

    def test_vector_poc_satisfies_static_contract_and_physics_values(self) -> None:
        html = (FIXTURES / "vector_poc.html").read_text(encoding="utf-8")
        report = validation_report(
            validate_html(
                html,
                expected_duration=46.64,
                physics_context={"values": {"resultant_force_n": 5}, "units": {"resultant_force_n": "N"}},
                full_lesson=False,
            )
        )
        self.assertEqual(report["status"], "passed", report)
        chapters = extract_chapter_blocks(html)
        self.assertEqual([(item.chapter_id, item.start, item.end) for item in chapters], [("chapter_01", 0.0, 46.64)])

    def test_light_equation_fixture_satisfies_static_contract(self) -> None:
        html = (FIXTURES / "light_equation.html").read_text(encoding="utf-8")
        self.assertEqual(validation_report(validate_html(html, expected_duration=12, full_lesson=False))["status"], "passed")

    def test_contract_rejects_remote_and_legacy_visual_source(self) -> None:
        html = (FIXTURES / "light_equation.html").read_text(encoding="utf-8").replace(
            "</head>", '<link rel="stylesheet" href="https://example.com/theme.css"><style>.x{color:var(--paper)}</style></head>'
        )
        codes = {item.code for item in validate_html(html, expected_duration=12, full_lesson=False)}
        self.assertIn("REMOTE_ASSET", codes)
        self.assertIn("LEGACY_VISUAL_STYLE", codes)

    def test_contract_rejects_hyperframes_incompatible_builder_parameter(self) -> None:
        html = (FIXTURES / "light_equation.html").read_text(encoding="utf-8").replace(
            "build: function (chapter) { const tl = chapter.tl; const root = chapter.root;",
            "build: ({ tl, root }) => {",
        )
        codes = {item.code for item in validate_html(html, expected_duration=12, full_lesson=False)}
        self.assertIn("HYPERFRAMES_BUILD_PARAMETER", codes)

    def test_chapter_replacement_enforces_hash_and_id(self) -> None:
        html = (FIXTURES / "light_equation.html").read_text(encoding="utf-8")
        chapter = extract_chapter_blocks(html)[0]
        replacement = chapter.full_source.replace("acceleration", "rate of change of velocity")
        updated = replace_chapter(html, "chapter_01", replacement, expected_hash=chapter.sha256)
        self.assertIn("rate of change of velocity", updated)
        with self.assertRaisesRegex(RuntimeError, "stale repair"):
            replace_chapter(html, "chapter_01", replacement, expected_hash="wrong")

    def test_visual_review_gate_enforces_rollout_thresholds(self) -> None:
        passing = {
            "chapters": [
                {"chapter_id": "chapter_01", "scores": {category: 4 for category in REVIEW_CATEGORIES}},
                {"chapter_id": "chapter_02", "scores": {category: 5 for category in REVIEW_CATEGORIES}},
            ]
        }
        self.assertEqual(evaluate_visual_review(passing)["status"], "passed")
        passing["chapters"][1]["scores"]["teaching_value"] = 2
        failed = evaluate_visual_review(passing)
        self.assertEqual(failed["status"], "failed")
        self.assertIn("CHAPTER_SCORE_BELOW_3", {item["code"] for item in failed["failures"]})


class ArtifactsAndCacheTest(unittest.TestCase):
    def test_direct_cost_ledger_contains_only_direct_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_path = Path(directory)
            ledger = {
                "records": [
                    {"task": "script_writing", "total_tokens": 100, "estimated_cost_usd": 1},
                    {"task": "direct_html_composer", "input_tokens": 20, "output_tokens": 30, "total_tokens": 50, "estimated_cost_usd": 0.25},
                ]
            }
            (run_path / "costs").mkdir()
            (run_path / "costs" / "model_usage.json").write_text(json.dumps(ledger), encoding="utf-8")
            summary = sync_direct_cost_records(run_path)
            mirrored = json.loads((run_path / "direct_html" / "costs" / "model_usage.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["calls"], 1)
            self.assertEqual(summary["total_tokens"], 50)
            self.assertEqual([item["task"] for item in mirrored["records"]], ["direct_html_composer"])

    def test_runtime_assets_include_local_fonts_and_gsap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_path = Path(directory)
            manifest = prepare_runtime_assets(run_path)
            ids = {item["id"] for item in manifest["runtime"]}
            self.assertIn("gsap", ids)
            self.assertIn("inter-latin-wght-normal.woff2", ids)
            self.assertIn("ibm-plex-mono-latin-400-normal.woff2", ids)

    def test_composer_promotes_valid_html_and_then_uses_cache(self) -> None:
        html = (FIXTURES / "light_equation.html").read_text(encoding="utf-8")
        bundle = {"video": {"duration_seconds": 12}, "input_hash": "bundle-hash"}
        assets = {"version": "test"}
        calls = []

        def fake_model_call(**_kwargs):
            calls.append(1)
            return html

        with tempfile.TemporaryDirectory() as directory:
            run_path = Path(directory)
            first = compose_lesson(run_path, bundle, {}, assets, model_call=fake_model_call)
            second = compose_lesson(run_path, bundle, {}, assets, model_call=fake_model_call)
            self.assertEqual(first["status"], "composed")
            self.assertEqual(second["status"], "cached")
            self.assertEqual(len(calls), 1)
            self.assertTrue((run_path / "direct_html" / "master.html").exists())

    def test_forced_recomposition_archives_previous_valid_master(self) -> None:
        first_html = (FIXTURES / "light_equation.html").read_text(encoding="utf-8")
        second_html = first_html.replace("What does the gradient measure?", "Read the gradient")
        responses = [first_html, second_html]

        def fake_model_call(**_kwargs):
            return responses.pop(0)

        with tempfile.TemporaryDirectory() as directory:
            run_path = Path(directory)
            bundle = {"video": {"duration_seconds": 12}, "input_hash": "bundle-hash"}
            compose_lesson(run_path, bundle, {}, {"version": "test"}, model_call=fake_model_call)
            compose_lesson(run_path, bundle, {}, {"version": "test"}, force=True, model_call=fake_model_call)
            versions = list((run_path / "direct_html" / "versions").glob("master_before_composition_*.html"))
            self.assertEqual(len(versions), 1)
            self.assertIn("What does the gradient measure?", versions[0].read_text(encoding="utf-8"))

    def test_composer_refuses_cache_miss_without_model_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "cache miss"):
                compose_lesson(
                    Path(directory),
                    {"video": {"duration_seconds": 12}, "input_hash": "bundle-hash"},
                    {},
                    {"version": "test"},
                    allow_model_call=False,
                )

    def test_composer_allows_one_global_contract_repair(self) -> None:
        valid = (FIXTURES / "light_equation.html").read_text(encoding="utf-8")
        invalid = valid.replace("<!doctype html>", "")
        responses = [invalid, valid]

        def fake_model_call(**_kwargs):
            return responses.pop(0)

        with tempfile.TemporaryDirectory() as directory:
            result = compose_lesson(
                Path(directory),
                {"video": {"duration_seconds": 12}, "input_hash": "repair-bundle"},
                {},
                {"version": "test"},
                model_call=fake_model_call,
            )
            self.assertEqual(result["manifest"]["global_contract_repair_count"], 1)
            self.assertFalse(responses)

    def test_render_adapter_detects_both_modes_and_strips_preview_audio(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_path = Path(directory)
            direct = run_path / "direct_html" / "master.html"
            direct.parent.mkdir(parents=True)
            direct.write_text((FIXTURES / "vector_poc.html").read_text(encoding="utf-8"), encoding="utf-8")
            self.assertEqual(animation_mode_for_run(run_path), DIRECT_HTML_MODE)
            self.assertEqual(composition_for_run(run_path)[1], "direct_html")
            render_copy = write_render_copy(direct)
            render_html = render_copy.read_text(encoding="utf-8")
            self.assertNotIn("lesson-audio", render_html)
            self.assertEqual(render_html.count('data-composition-id="direct_html_master"'), 1)
            (run_path / "generation_summary.json").write_text(json.dumps({"animation_mode": LEGACY_MODE}), encoding="utf-8")
            legacy = run_path / "compositions" / "master_v3.html"
            legacy.parent.mkdir()
            legacy.write_text("<!doctype html>", encoding="utf-8")
            self.assertEqual(animation_mode_for_run(run_path), LEGACY_MODE)


@unittest.skipUnless(os.getenv("MAV_RUN_BROWSER_TESTS") == "1", "set MAV_RUN_BROWSER_TESTS=1 for Chromium integration")
class BrowserInspectionTest(unittest.TestCase):
    def test_vector_poc_passes_browser_inspection(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "runs") as directory:
            run_path = Path(directory)
            (run_path / "direct_html").mkdir()
            prepare_runtime_assets(run_path)
            shutil.copy2(FIXTURES / "vector_poc.html", run_path / "direct_html" / "master.html")
            shutil.copy2(ROOT / "runs" / "physics-1-1-v01" / "voiceover.mp3", run_path / "voiceover.mp3")
            build_chapter_index(run_path / "direct_html" / "master.html")
            report = inspect_lesson(run_path)
            self.assertEqual(report["status"], "passed", report)

    def test_deliberate_design_failures_are_reported(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "runs") as directory:
            run_path = Path(directory)
            (run_path / "direct_html").mkdir()
            prepare_runtime_assets(run_path)
            shutil.copy2(FIXTURES / "deliberate_failures.html", run_path / "direct_html" / "master.html")
            build_chapter_index(run_path / "direct_html" / "master.html")
            report = inspect_lesson(run_path)
            codes = {item["code"] for item in report["design_system"]["findings"]}
            self.assertEqual(report["status"], "failed")
            self.assertIn("REPEATED_CARD_LAYOUT", codes)
            self.assertIn("EXCESSIVE_PANELS", codes)
            self.assertIn("DECORATIVE_PARTICLES", codes)
            self.assertIn("SMALL_IMPORTANT_TEXT", codes)
            self.assertIn("LOW_TEXT_CONTRAST", codes)
            self.assertIn("NON_SEMANTIC_RAW_COLORS", codes)
            self.assertIn("MEANINGLESS_MOTION", codes)


if __name__ == "__main__":
    unittest.main()
