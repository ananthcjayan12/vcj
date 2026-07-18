from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from motion_canvas.pipeline import _enforce_manifest_duration, parse_response, render_profile_fingerprint, resolve_render_profile
from reels.schemas import validate_narration
from reels.source import load_parent_source
from reels.timeline import build_immutable_shot_timeline, validate_immutable_shot_timeline
from reels.validation import invalidate, validate_portrait_tsx


class NativeReelPipelineTest(unittest.TestCase):
    def source(self) -> dict:
        return {"paragraph_ids": ["paragraph_01"], "claim_ids": ["density-C01"]}

    def test_parent_source_loader_never_reads_motion_canvas_tsx(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            (parent / "input.json").write_text(json.dumps({"run_id": "lesson", "topic": "Density", "facts": {"claims": [{"id": "density-C01", "text": "Density is mass per volume"}]}}))
            (parent / "narration.json").write_text(json.dumps({"paragraphs": [{"id": "paragraph_01", "text": "Two cubes have equal volume."}]}))
            visual = parent / "motion_canvas" / "reels" / "reel_001.tsx"
            visual.parent.mkdir(parents=True); visual.write_text("SECRET_PARENT_VISUAL")
            payload = load_parent_source(parent)
            self.assertNotIn("SECRET_PARENT_VISUAL", json.dumps(payload))
            self.assertNotIn("motion_canvas", json.dumps(payload))

    def test_reel_paragraph_ids_must_be_sequential(self) -> None:
        payload = {"paragraphs": [{"id": "paragraph_02", "text": "Wrong."}, {"id": "paragraph_03", "text": "Still wrong."}, {"id": "paragraph_04", "text": "No."}], "source_claim_ids": ["density-C01"]}
        with self.assertRaisesRegex(RuntimeError, "sequential"):
            validate_narration(payload, self.source())

    def test_immutable_shots_are_contiguous_and_end_on_audio_frame(self) -> None:
        words = {"voiceover_sha256": "abc", "words": [
            {"paragraph_id": "paragraph_01", "word": f"w{i}", "start": i * .7, "end": i * .7 + .35}
            for i in range(20)
        ]}
        timing = {"audio_duration_seconds": 14.0, "paragraphs": [{"id": "paragraph_01", "start": 0, "end": 14, "duration": 14}]}
        timeline = build_immutable_shot_timeline(words, timing)
        validate_immutable_shot_timeline(timeline)
        self.assertGreater(len(timeline["shots"]), 1)
        self.assertEqual(timeline["total_frames"], 420)
        for left, right in zip(timeline["shots"], timeline["shots"][1:]):
            self.assertEqual(left["render_end_frame"], right["render_start_frame"])

    def test_profiles_default_to_landscape_and_portrait_is_native(self) -> None:
        self.assertEqual((resolve_render_profile()["width"], resolve_render_profile()["height"]), (1920, 1080))
        self.assertEqual((resolve_render_profile("reel_portrait")["width"], resolve_render_profile("reel_portrait")["height"]), (1080, 1920))
        self.assertNotEqual(render_profile_fingerprint("lesson_landscape"), render_profile_fingerprint("reel_portrait"))

    def test_shot_duration_is_enforced_without_changing_lesson_contract(self) -> None:
        shot = {"scene_id": "shot_001", "render_duration": 2, "render_start_frame": 0, "render_end_frame": 60}
        source = "const SHOT_DURATION = 9;\nyield* progress(1, SHOT_DURATION, linear);"
        self.assertIn("SHOT_DURATION = 1.9999999", _enforce_manifest_duration(source, shot))

    def test_portrait_source_rejects_landscape_import(self) -> None:
        validate_portrait_tsx("import {HookText} from '../../reel-presentation';", "shot_001")
        with self.assertRaisesRegex(RuntimeError, "portrait"):
            validate_portrait_tsx("import {SceneTitle} from '../../presentation';", "shot_001")

    def test_portrait_parser_uses_mobile_type_scale_and_components(self) -> None:
        portrait = """import {makeScene2D, Txt} from '@motion-canvas/2d';
import {ReelSafeStage} from '../../reel-presentation';
import {CUES} from './shot_001.cues';
export default makeScene2D(function* (view) { view.add(<ReelSafeStage><Txt text='FAST' fontSize={56} /></ReelSafeStage>); });"""
        parsed = parse_response(f"=== shot_001.tsx ===\n{portrait}", ["shot_001"], portrait=True)
        self.assertIn("fontSize={56}", parsed["shot_001.tsx"])
        landscape = portrait.replace("../../reel-presentation", "../../presentation")
        with self.assertRaises(RuntimeError):
            parse_response(f"=== shot_001.tsx ===\n{landscape}", ["shot_001"], portrait=True)

    def test_single_shot_invalidation_preserves_siblings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary); shots = run / "motion_canvas" / "shots"; shots.mkdir(parents=True)
            (shots / "shot_001.tsx").write_text("one"); (shots / "shot_002.tsx").write_text("two")
            invalidate(run, "shot_tsx", shot_id="shot_001")
            self.assertFalse((shots / "shot_001.tsx").exists())
            self.assertTrue((shots / "shot_002.tsx").exists())


if __name__ == "__main__":
    unittest.main()
