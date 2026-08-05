from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from reel_pack.visuals import _generate_one_reel, generate_visual_sources, render_pack, validate_visuals


class ReelVisualRecoveryTest(unittest.TestCase):
    def test_compile_ready_reel_can_render_without_screening(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            pack = {
                "run_id": "optional-screening-test",
                "status": "visuals_ready",
                "current_step": 6,
                "reels": [{"reel_id": "reel_001", "status": "visual_ready"}],
            }
            (run / "reel_pack.json").write_text(json.dumps(pack), encoding="utf-8")
            rendered_file = run / "motion_canvas" / "renders" / "reel_001.mp4"
            rendered_file.parent.mkdir(parents=True)
            rendered_file.write_bytes(b"mp4")

            fake_render = Mock(return_value=rendered_file)
            with patch.dict(sys.modules, {"mav_render": type("MavRender", (), {"render_reel_mp4": fake_render})}):
                result = render_pack(run, target_reel_id="reel_001")

            fake_render.assert_called_once_with(run.name, "reel_001")
            self.assertEqual(result["current_step"], 8)
            self.assertEqual(result["reels"][0]["status"], "rendered")

    def test_flagged_reel_remains_gated_after_optional_screening(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            pack = {
                "run_id": "screening-gate-test",
                "status": "screened",
                "current_step": 7,
                "reels": [{"reel_id": "reel_001", "status": "flagged"}],
            }
            (run / "reel_pack.json").write_text(json.dumps(pack), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "compile & preview"):
                render_pack(run, target_reel_id="reel_001")

    def test_raw_response_is_not_reused_when_accepted_source_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            responses = run / "motion_canvas" / "responses"
            responses.mkdir(parents=True)
            (responses / "reel_002.txt").write_text(
                "=== reel_002.tsx ===\nSTALE INVALID SOURCE",
                encoding="utf-8",
            )
            manifest = {
                "timeline_mode": "immutable_reels",
                "reels": [{
                    "scene_id": "reel_002",
                    "source_id": "reel_002",
                    "render_duration": 35,
                }],
            }
            model = Mock(return_value="=== reel_002.tsx ===\nNEW SOURCE")
            with (
                patch("reel_pack.visuals.visual_user_prompt", return_value="prompt"),
                patch("reel_pack.visuals.motion_pipeline._normalize_chapter_source", side_effect=lambda value: value),
                patch("reel_pack.visuals.motion_pipeline._enforce_manifest_duration", side_effect=lambda value, _unit: value),
                patch("reel_pack.visuals.motion_pipeline._validate_chapter_source", return_value=[]),
                patch("reel_pack.visuals.motion_pipeline._validate_cue_references"),
                patch("reel_pack.visuals.extract_visual_contract", return_value=({"kind": "test"}, [])),
            ):
                _generate_one_reel(
                    run,
                    {"reel_id": "reel_002"},
                    manifest,
                    allow_model_call=True,
                    force=False,
                    model_call=model,
                )

            model.assert_called_once()
            self.assertIn("NEW SOURCE", (responses / "reel_002.txt").read_text(encoding="utf-8"))
            self.assertEqual(
                (run / "motion_canvas" / "reels" / "reel_002.tsx").read_text(encoding="utf-8").strip(),
                "NEW SOURCE",
            )

    def test_partial_visual_failure_is_saved_as_warning_not_raised(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            pack = {
                "run_id": "warning-test",
                "status": "timing_ready",
                "current_step": 4,
                "reels": [
                    {"reel_id": "reel_001", "status": "timing_ready"},
                    {"reel_id": "reel_002", "status": "timing_ready"},
                ],
            }
            (run / "reel_pack.json").write_text(json.dumps(pack), encoding="utf-8")
            manifest = {
                "timeline_mode": "immutable_reels",
                "reels": [
                    {"scene_id": "reel_001", "source_id": "reel_001"},
                    {"scene_id": "reel_002", "source_id": "reel_002"},
                ],
            }

            def generate(_run, record, _manifest, **_kwargs):
                if record["reel_id"] == "reel_002":
                    raise RuntimeError("generated TSX was incomplete")
                return []

            with (
                patch("reel_pack.visuals._prepare_manifest", return_value=manifest),
                patch("reel_pack.visuals._generate_one_reel", side_effect=generate),
            ):
                result = generate_visual_sources(run, allow_model_call=True)

            self.assertEqual(result["status"], "partial")
            self.assertEqual(result["current_step"], 5)
            self.assertEqual(result["reels"][0]["status"], "visual_ready")
            self.assertEqual(result["reels"][1]["status"], "failed")
            self.assertIn("generated TSX was incomplete", result["reels"][1]["error"])

    def test_compile_failure_uses_bounded_model_repair_then_rechecks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            motion = run / "motion_canvas"
            reels = motion / "reels"
            reels.mkdir(parents=True)
            (reels / "reel_005.tsx").write_text("BROKEN", encoding="utf-8")
            pack = {
                "run_id": "compile-repair-test",
                "status": "visuals_ready",
                "current_step": 5,
                "reels": [{"reel_id": "reel_005", "status": "visual_ready"}],
            }
            manifest = {
                "timeline_mode": "immutable_reels",
                "reels": [{"scene_id": "reel_005", "source_id": "reel_005"}],
            }
            (run / "reel_pack.json").write_text(json.dumps(pack), encoding="utf-8")
            (motion / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            compile_failure = {
                "script": "typecheck",
                "returncode": 2,
                "stdout": "src/generated/reels/reel_005.tsx(12,4): error TS1127: Invalid character.",
                "stderr": "",
            }
            success = {"script": "typecheck", "returncode": 0, "stdout": "", "stderr": ""}

            def npm_result(_run, _manifest, script, _timeout):
                if script == "typecheck":
                    return compile_failure if npm_result.typechecks == 0 else success
                (motion / "validation.json").write_text(
                    json.dumps({"status": "passed", "canvas": {"width": 1080, "height": 1920}}),
                    encoding="utf-8",
                )
                return {"script": script, "returncode": 0, "stdout": "", "stderr": ""}

            npm_result.typechecks = 0

            def count_typecheck(*args, **kwargs):
                result = npm_result(*args, **kwargs)
                if args[2] == "typecheck":
                    npm_result.typechecks += 1
                return result

            with (
                patch("reel_pack.visuals.motion_pipeline.assemble"),
                patch("reel_pack.visuals.motion_pipeline._sync_runtime"),
                patch(
                    "reel_pack.visuals.motion_pipeline._repair_chapter_with_model",
                    return_value={"chapter_id": "reel_005", "response": "repair.txt"},
                ) as repair,
                patch("reel_pack.visuals.npm", side_effect=count_typecheck),
            ):
                result = validate_visuals(run, allow_model_call=True)

            repair.assert_called_once()
            self.assertEqual(repair.call_args.args[1], "reel_005")
            self.assertEqual(result["current_step"], 6)
            report = json.loads((motion / "robot-report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "passed")
            self.assertEqual(len(report["compile_repairs"]), 1)


if __name__ == "__main__":
    unittest.main()
