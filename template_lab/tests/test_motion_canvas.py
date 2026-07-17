from __future__ import annotations

import math
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from motion_canvas.pipeline import (
    MOTION_CANVAS_FPS,
    _apply_frame_aligned_timing,
    _assert_immutable_timeline,
    _enforce_manifest_duration,
    _split_from_audio_manifest,
    assemble,
    build_immutable_timeline,
    generate,
    parse_response,
    prepare,
    presentation_contract_findings,
    split_chapters,
    validate_and_assemble,
)


class MotionCanvasPipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.words = {"audio_duration_seconds": 4.0, "words": [
            {"paragraph_id": "paragraph_01", "word": "move", "start": 0.5, "end": 1.0},
            {"paragraph_id": "paragraph_02", "word": "stop", "start": 2.5, "end": 3.0},
        ]}
        self.narration = {"paragraphs": [{"id": "paragraph_01", "text": "Move."}, {"id": "paragraph_02", "text": "Stop."}]}

    def test_split_is_contiguous_and_local(self) -> None:
        chapters = split_chapters(self.words, self.narration)
        self.assertEqual([item["duration"] for item in chapters], [2.5, 1.5])
        self.assertEqual(chapters[1]["words"][0]["start"], 0.0)
        self.assertEqual(sum(item["duration"] for item in chapters), 4.0)

    def test_frame_alignment_quantizes_cumulative_boundaries_without_drift(self) -> None:
        manifest = {
            "chapters": [
                {"scene_id": "chapter_01", "absolute_end": 1.01, "duration": 1.01},
                {"scene_id": "chapter_02", "absolute_end": 2.02, "duration": 1.01},
                {"scene_id": "chapter_03", "absolute_end": 3.03, "duration": 1.01},
            ]
        }
        _apply_frame_aligned_timing(manifest)
        chapters = manifest["chapters"]
        self.assertEqual(chapters[1]["render_start_frame"], chapters[0]["render_end_frame"])
        self.assertEqual(chapters[2]["render_start_frame"], chapters[1]["render_end_frame"])
        self.assertLessEqual(abs(manifest["render_duration"] - 3.03), 1 / MOTION_CANVAS_FPS)

    def test_manifest_duration_overrides_generated_decimal(self) -> None:
        source = "const CHAPTER_DURATION = 1.01;"
        chapter = {"scene_id": "chapter_01", "duration": 1.01, "render_duration": 1.0}
        self.assertEqual(_enforce_manifest_duration(source, chapter), "const CHAPTER_DURATION = 1;")

    def test_manifest_duration_does_not_round_fractional_frame_up(self) -> None:
        source = "const CHAPTER_DURATION = 12.17;"
        chapter = {
            "scene_id": "reel_001",
            "duration": 12.17,
            "render_duration": 365 / MOTION_CANVAS_FPS,
            "render_start_frame": 331,
            "render_end_frame": 696,
        }
        aligned = _enforce_manifest_duration(
            source + "\nyield* progress(1, CHAPTER_DURATION, linear);",
            chapter,
        )
        literal = float(re.search(r"CHAPTER_DURATION = ([0-9.]+)", aligned).group(1))
        measured_end = math.ceil((chapter["render_start_frame"] / MOTION_CANVAS_FPS + literal) * MOTION_CANVAS_FPS)
        self.assertEqual(measured_end, chapter["render_end_frame"])

    def test_audio_reel_stays_one_scene_with_contiguous_edit_beats(self) -> None:
        words = {
            "words": [
                {"paragraph_id": "paragraph_01", "word": f"word{index}", "start": index + 0.1, "end": index + 0.6}
                for index in range(32)
            ]
        }
        audio = {
            "sample_rate": 24_000,
            "chapters": [{"id": "paragraph_01", "path": "audio.wav", "absolute_start": 0, "absolute_end": 32}],
        }
        timeline = build_immutable_timeline(words, audio)
        self.assertEqual(timeline["mode"], "immutable_reels")
        self.assertEqual(len(timeline["reels"]), 1)
        self.assertGreater(len(timeline["beats"]), 1)
        self.assertEqual(timeline["reels"][0]["render_start_frame"], 0)
        self.assertEqual(timeline["reels"][0]["beat_ids"], [item["beat_id"] for item in timeline["beats"]])
        for previous, following in zip(timeline["beats"], timeline["beats"][1:]):
            self.assertEqual(previous["render_end_frame"], following["render_start_frame"])
            self.assertEqual(previous["audio_end_sample"], following["audio_start_sample"])

    def test_immutable_timeline_rejects_boundary_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            import json

            run = Path(temporary)
            root = run / "motion_canvas"
            root.mkdir(parents=True)
            timeline = build_immutable_timeline(
                {"words": [{"word": "move", "start": 0.1, "end": 0.5}]},
                {"sample_rate": 24_000, "chapters": [{"id": "p1", "absolute_start": 0, "absolute_end": 2}]},
            )
            (root / "timeline.json").write_text(json.dumps(timeline))
            manifest = {"timeline_mode": "immutable_reels", "timeline_id": timeline["timeline_id"], "reels": timeline["reels"], "beats": timeline["beats"]}
            _assert_immutable_timeline(run, manifest)
            manifest["reels"][0]["render_end_frame"] += 1
            with self.assertRaisesRegex(RuntimeError, "Immutable timing field"):
                _assert_immutable_timeline(run, manifest)

    def test_strict_markers(self) -> None:
        parsed = parse_response("=== chapter_01.tsx ===\nsource", ["chapter_01"])
        self.assertEqual(parsed["chapter_01.tsx"], "source")
        with self.assertRaises(RuntimeError): parse_response("```tsx\nx\n```", ["chapter_01"])

    def test_prepare_and_assemble(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary); (run / "voiceover.mp3").write_bytes(b"audio")
            import json
            (run / "audio_word_timestamps.json").write_text(json.dumps(self.words))
            manifest = prepare(run, self.narration, batch_size=1)
            self.assertTrue((run / "motion_canvas" / "chapters" / "chapter_01.cues.ts").exists())
            for item in manifest["chapters"]:
                duration = item["duration"]
                source = f"""import {{makeScene2D}} from '@motion-canvas/2d';\nimport {{createSignal, linear}} from '@motion-canvas/core';\nconst CHAPTER_DURATION = {duration};\nexport default makeScene2D(function* () {{ const progress = createSignal(0); yield* progress(1, CHAPTER_DURATION, linear); }});\n"""
                path = run / "motion_canvas" / "chapters" / f"{item['scene_id']}.tsx"; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(source)
            self.assertTrue(assemble(run, manifest).exists())

    def test_parser_rejects_external_import(self) -> None:
        with self.assertRaises(RuntimeError):
            parse_response("=== chapter_01.tsx ===\nimport x from 'https://bad.test/x'", ["chapter_01"])

    def test_audio_manifest_boundaries_are_authoritative(self) -> None:
        words = {"words": [
            {"paragraph_id": "paragraph_01", "word": "move", "start": 0.2, "end": 0.7},
            {"paragraph_id": "paragraph_02", "word": "stop", "start": 2.3, "end": 2.8},
        ]}
        audio = {"chapters": [
            {"id": "paragraph_01", "absolute_start": 0, "absolute_end": 2.1, "speech_duration": 1.75, "trailing_pause": .35},
            {"id": "paragraph_02", "absolute_start": 2.1, "absolute_end": 3.0, "speech_duration": .9, "trailing_pause": 0},
        ]}
        chapters = _split_from_audio_manifest(words, audio)
        self.assertEqual([item["duration"] for item in chapters], [2.1, .9])
        self.assertEqual(chapters[1]["words"][0]["start"], .2)

    def test_generated_scene_requires_presentation_contract(self) -> None:
        source = "import {makeScene2D} from '@motion-canvas/2d'; export default makeScene2D(function*(){});"
        with self.assertRaisesRegex(RuntimeError, "presentation components"):
            parse_response(f"=== chapter_01.tsx ===\n{source}", ["chapter_01"])

    def test_parser_rejects_latex_commands_in_raw_text(self) -> None:
        source = (
            "import {makeScene2D, Txt} from '@motion-canvas/2d'; "
            "import {SceneTitle} from '../../presentation'; "
            "import {CUES} from './chapter_01.cues'; "
            "export default makeScene2D(function*(){ void SceneTitle; void CUES; yield <Txt text=\"\\\\dfrac{s}{t}\" />; });"
        )
        with self.assertRaisesRegex(RuntimeError, "LaTeX through raw Txt"):
            parse_response(f"=== chapter_01.tsx ===\n{source}", ["chapter_01"])

    def test_targeted_generation_replaces_only_the_selected_chapter(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary)
            root = run / "motion_canvas"
            chapters = root / "chapters"
            chapters.mkdir(parents=True)
            source = (
                "import {makeScene2D} from '@motion-canvas/2d';\n"
                "import {SceneTitle} from '../../presentation';\n"
                "import {CUES} from './CHAPTER.cues';\n"
                "export default makeScene2D(function* () { void SceneTitle; void CUES; });\n"
            )
            for chapter_id in ("chapter_01", "chapter_02"):
                (chapters / f"{chapter_id}.tsx").write_text(source.replace("CHAPTER", chapter_id))
                (chapters / f"{chapter_id}.cues.ts").write_text("export const CUES = {} as const;")
            original_sibling = (chapters / "chapter_02.tsx").read_text()
            manifest = {
                "chapters": [
                    {"scene_id": "chapter_01", "duration": 2, "words": []},
                    {"scene_id": "chapter_02", "duration": 2, "words": []},
                ],
                "batches": [{"id": "batch_01", "chapter_ids": ["chapter_01", "chapter_02"], "status": "generated"}],
            }
            response = "=== chapter_01.tsx ===\n" + source.replace("CHAPTER", "chapter_01").replace(
                "void SceneTitle", "const regenerated = true; void regenerated; void SceneTitle"
            )
            with patch("motion_canvas.pipeline._sync_runtime"), patch(
                "motion_canvas.pipeline._npm",
                return_value={"returncode": 0, "stdout": "", "stderr": ""},
            ):
                report = generate(
                    run,
                    manifest,
                    allow_model_call=True,
                    force=True,
                    workers=1,
                    target_chapter_id="chapter_01",
                    instruction="Make the diagram clearer.",
                    model_call=lambda **_kwargs: response,
                )
            self.assertEqual(report["status"], "generated")
            self.assertIn("regenerated", (chapters / "chapter_01.tsx").read_text())
            self.assertEqual((chapters / "chapter_02.tsx").read_text(), original_sibling)
            self.assertEqual(manifest["chapter_status"]["chapter_01"], "generated")
            self.assertIn(
                "Make the diagram clearer.",
                (root / "prompts" / "regenerate_chapter_01.txt").read_text(),
            )

    def test_presentation_preflight_attributes_overlong_equation_to_chapter(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary)
            chapter = run / "motion_canvas" / "chapters" / "chapter_02.tsx"
            chapter.parent.mkdir(parents=True)
            equation = "\\\\text{speed}=" + "\\\\dfrac{\\\\text{ground covered}}{\\\\text{time taken}}" * 3
            chapter.write_text(
                f"<EquationCard equation=\"{equation}\" />"
            )
            findings = presentation_contract_findings(run)
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0]["chapter_id"], "chapter_02")
            self.assertEqual(findings[0]["property"], "equation")
            self.assertEqual(findings[0]["limit"], 120)

    def test_step_six_repairs_measured_presentation_failure_then_revalidates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            import json

            run = Path(temporary)
            root = run / "motion_canvas"
            chapters = root / "chapters"
            chapters.mkdir(parents=True)
            (root / "voiceover.mp3").write_bytes(b"audio")
            (chapters / "chapter_01.cues.ts").write_text("export const CUES = {} as const;")
            (chapters / "chapter_01.tsx").write_text(
                "import {makeScene2D} from '@motion-canvas/2d';\n"
                "import {EquationCard} from '../../presentation';\n"
                "import {CUES} from './chapter_01.cues';\n"
                "export default makeScene2D(function* () { void CUES; yield <EquationCard "
                "equation=\"\\\\text{speed}=\\\\dfrac{\\\\text{ground covered}}{\\\\text{time taken}}"
                "\\\\dfrac{\\\\text{ground covered}}{\\\\text{time taken}}"
                "\\\\dfrac{\\\\text{ground covered}}{\\\\text{time taken}}\" />; });\n"
            )
            manifest = {
                "chapters": [{"scene_id": "chapter_01", "duration": 2, "words": []}],
                "batches": [{"id": "batch_01", "chapter_ids": ["chapter_01"], "status": "generated"}],
            }
            repaired = (
                "=== chapter_01.tsx ===\n"
                "import {makeScene2D} from '@motion-canvas/2d';\n"
                "import {EquationCard} from '../../presentation';\n"
                "import {CUES} from './chapter_01.cues';\n"
                "export default makeScene2D(function* () { void CUES; yield <EquationCard equation=\"speed = distance ÷ time\" />; });"
            )

            def npm_result(script: str, _run: Path, _timeout: int) -> dict[str, object]:
                if script == "preview-frames":
                    (root / "validation.json").write_text(json.dumps({"status": "passed"}))
                return {"command": script, "returncode": 0, "stdout": "", "stderr": ""}

            with patch("motion_canvas.pipeline._sync_runtime"), patch(
                "motion_canvas.pipeline._npm",
                side_effect=npm_result,
            ):
                report = validate_and_assemble(
                    run,
                    manifest,
                    allow_model_repair=True,
                    max_model_repairs=2,
                    model_call=lambda **_kwargs: repaired,
                )
            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["runtime_repairs"][0]["chapter_id"], "chapter_01")
            self.assertIn("speed = distance ÷ time", (chapters / "chapter_01.tsx").read_text())


if __name__ == "__main__": unittest.main()
