import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from template_lab.shorts.context import build_discovery_context, build_script_context, public_discovery_context
from template_lab.shorts.pipeline import ShortsPipeline
from template_lab.shorts.prompting import render_user_prompt, prompts_dir


class ShortPromptPayloadTests(unittest.TestCase):
    def test_user_templates_render_and_exclude_anchors(self):
        candidate_user = render_user_prompt(
            prompts_dir() / "short_candidate_analysis.user.txt",
            {"DISCOVERY_CONTEXT_JSON": '{"lesson":{"topic":"mass"}}'},
        )
        script_user = render_user_prompt(
            prompts_dir() / "short_script_writing.user.txt",
            {"SCRIPT_CONTEXT_JSON": '{"candidate":{"hook":"x"}}'},
        )
        self.assertIn("EVIDENCE PACK", candidate_user)
        self.assertIn("SCRIPT CONTEXT", script_user)
        for text in (candidate_user, script_user):
            self.assertNotIn("deterministic_seed_candidates", text)
            self.assertNotIn("required_schema_example", text)

    def test_public_discovery_hides_index(self):
        context = {
            "lesson": {"parent_run_id": "p"},
            "claims": [],
            "paragraphs": [{"paragraph_id": "paragraph_01", "text": "hello", "claim_ids": ["C1"], "word_count": 1}],
            "_index": {"known_claims": {"C1"}},
        }
        public = public_discovery_context(context)
        self.assertNotIn("_index", public)
        self.assertIn("paragraphs", public)

    def test_script_context_filters_narration(self):
        artifacts = {
            "parent": Path("."),
            "narration": {"paragraphs": [
                {"id": "paragraph_01", "text": "One. Mass is matter.", "claim_ids": ["C1"]},
                {"id": "paragraph_02", "text": "Two. Weight is a force.", "claim_ids": ["C2"]},
                {"id": "paragraph_03", "text": "Three. Density is mass over volume.", "claim_ids": ["C3"]},
            ]},
            "story": {},
            "manifest": {},
            "timeline": {},
            "audio_manifest": {},
            "timestamps": {},
            "input": {},
            "known_claims": {"C1", "C2", "C3"},
        }
        candidate = {
            "candidate_id": "candidate_001",
            "claim_ids": ["C2"],
            "primary_claim_id": "C2",
            "source_paragraph_ids": ["paragraph_02"],
            "source_segments": [],
            "hook": "Is weight a force?",
            "working_title": "Weight",
            "target_duration_seconds": 30,
        }
        discovery = build_discovery_context(artifacts, parent_run_id="p")
        ctx = build_script_context(artifacts, candidate, discovery)
        ids = [p["paragraph_id"] for p in ctx["source_paragraphs"]]
        self.assertIn("paragraph_02", ids)
        self.assertLessEqual(len(ids), 3)
        self.assertNotIn("parent_narration", ctx)
        self.assertIn("reusable_clauses", ctx)

    def test_analyze_model_prompt_has_no_seeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parent = root / "parent"
            for rel in (
                "input.json", "story_skeleton.json", "narration.json",
                "audio_chunks/manifest.json", "audio_word_timestamps.json",
                "motion_canvas/manifest.json", "motion_canvas/robot-report.json",
            ):
                path = parent / rel
                path.parent.mkdir(parents=True, exist_ok=True)
            (parent / "voiceover.wav").write_bytes(b"RIFF")
            (parent / "motion_canvas/final.mp4").write_bytes(b"\x00")
            (parent / "motion_canvas/reels").mkdir(parents=True)
            (parent / "motion_canvas/reels/reel_001.tsx").write_text("export default function Reel(){ return null }", encoding="utf-8")
            (parent / "input.json").write_text(json.dumps({"title": "Mass"}), encoding="utf-8")
            (parent / "story_skeleton.json").write_text(json.dumps({
                "beats": [{"beat_id": "beat_001", "reel_id": "reel_001", "claim_ids": ["C1"], "summary": "mass"}]
            }), encoding="utf-8")
            (parent / "narration.json").write_text(json.dumps({
                "paragraphs": [
                    {"id": "paragraph_01", "text": "Mass stays constant when gravity changes.", "claim_ids": ["C1"]},
                    {"id": "paragraph_02", "text": "Weight equals mass times g.", "claim_ids": ["C2"]},
                    {"id": "paragraph_03", "text": "On the Moon weight falls but mass does not.", "claim_ids": ["C1"]},
                ]
            }), encoding="utf-8")
            (parent / "audio_chunks/manifest.json").write_text(json.dumps({"chapters": []}), encoding="utf-8")
            (parent / "audio_word_timestamps.json").write_text(json.dumps({"words": []}), encoding="utf-8")
            (parent / "motion_canvas/manifest.json").write_text(json.dumps({
                "reels": [{"scene_id": "reel_001", "start": 0, "end": 12, "claim_ids": ["C1"]}]
            }), encoding="utf-8")
            (parent / "motion_canvas/robot-report.json").write_text(json.dumps({"status": "passed"}), encoding="utf-8")

            pipeline = ShortsPipeline(root, "parent")
            fake_response = {
                "candidates": [
                    {
                        "concept_key": f"idea-{i}",
                        "primary_claim_id": "C1" if i % 2 else "C2",
                        "supporting_claim_ids": [],
                        "archetype": "misconception",
                        "hook_mechanism": "question",
                        "working_title": f"Title {i}",
                        "hook": f"What changes in case {i} when gravity drops?",
                        "promise": f"See distinction {i}.",
                        "payoff": f"Mass stays; weight changes in case {i}.",
                        "target_duration_seconds": 30 + i,
                        "source_paragraph_ids": ["paragraph_01" if i % 2 else "paragraph_02"],
                        "source_beat_ids": ["beat_001"],
                        "source_reel_ids": ["reel_001"],
                        "creative_rationale": "test",
                        "warnings": [],
                        "self_scores": {"hook_score": 80, "payoff_score": 80, "standalone_score": 85, "exam_relevance_score": 75},
                    }
                    for i in range(1, 7)
                ]
            }

            def fake_model_json(task, system_file, user, output_schema=None):
                self.assertEqual(task, "short_candidate_analysis")
                self.assertNotIn("deterministic_seed_candidates", user)
                self.assertNotIn("required_schema_example", user)
                self.assertIn("paragraph_03", user)
                self.assertIsNotNone(output_schema)
                return fake_response

            with patch.object(pipeline, "_model_json", side_effect=fake_model_json):
                payload = pipeline.analyze(use_model=True)
            self.assertEqual(payload["analysis_mode"], "model_discovery")
            prompt_path = parent / "shorts/debug/candidate_analysis_prompt.txt"
            self.assertTrue(prompt_path.is_file())
            prompt_text = prompt_path.read_text(encoding="utf-8")
            self.assertNotIn("deterministic_seed_candidates", prompt_text)
            self.assertIn("You are NOT given candidate ideas", prompt_text)

    def test_create_model_prompt_has_no_schema_example(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parent = root / "parent"
            parent.mkdir()
            (parent / "shorts").mkdir()
            (parent / "narration.json").write_text(json.dumps({
                "paragraphs": [{"id": "paragraph_01", "text": "Mass stays constant. Weight changes with gravity.", "claim_ids": ["C1"]}]
            }), encoding="utf-8")
            (parent / "audio_word_timestamps.json").write_text(json.dumps({"words": []}), encoding="utf-8")
            (parent / "story_skeleton.json").write_text(json.dumps({"beats": []}), encoding="utf-8")
            (parent / "motion_canvas").mkdir(parents=True, exist_ok=True)
            (parent / "audio_chunks").mkdir(parents=True, exist_ok=True)
            (parent / "motion_canvas/manifest.json").write_text(json.dumps({"reels": [{"scene_id": "reel_001", "start": 0, "end": 10}]}), encoding="utf-8")
            (parent / "input.json").write_text(json.dumps({"title": "Mass"}), encoding="utf-8")
            (parent / "audio_chunks/manifest.json").write_text(json.dumps({"chapters": []}), encoding="utf-8")
            candidate = {
                "candidate_id": "candidate_001",
                "archetype": "misconception",
                "working_title": "Mass Stays",
                "hook": "Did mass change?",
                "promise": "See the split.",
                "payoff": "Mass stays; weight changes.",
                "target_duration_seconds": 35,
                "claim_ids": ["C1"],
                "primary_claim_id": "C1",
                "source_paragraph_ids": ["paragraph_01"],
                "source_segments": [{
                    "reel_id": "reel_001",
                    "beat_ids": ["beat_001"],
                    "absolute_start": 0,
                    "absolute_end": 10,
                    "visual_reuse_mode": "adapt",
                    "audio_reuse_mode": "partial",
                }],
                "scores": {k: 80 for k in (
                    "standalone_score", "hook_score", "payoff_score", "visual_reuse_score",
                    "audio_reuse_score", "exam_relevance_score", "portrait_suitability_score", "overall_score",
                )},
                "warnings": [],
            }
            (parent / "shorts/candidates.json").write_text(json.dumps({
                "version": "1.0", "parent_run_id": "parent", "candidates": [candidate]
            }), encoding="utf-8")

            pipeline = ShortsPipeline(root, "parent")

            def fake_model_json(task, system_file, user, output_schema=None):
                self.assertEqual(task, "short_script_writing")
                self.assertNotIn("required_schema_example", user)
                self.assertNotIn("deterministic_seed_candidates", user)
                self.assertNotIn('"paragraphs": [', user)  # full narration dump avoided
                self.assertIn("reusable_clauses", user)
                self.assertIsNotNone(output_schema)
                return {
                    "title": "Mass Stays",
                    "target_duration_seconds": 35,
                    "claim_ids": ["C1"],
                    "lines": [
                        {"line_id": "line_001", "role": "hook", "text": "Did mass change on the Moon?", "claim_ids": ["C1"], "audio_source": "generate", "visual_intent": "question"},
                        {"line_id": "line_002", "role": "setup", "text": "An astronaut stands on a lunar scale.", "claim_ids": ["C1"], "audio_source": "generate", "visual_intent": "scale"},
                        {"line_id": "line_003", "role": "tension", "text": "The reading drops. So what left the body?", "claim_ids": ["C1"], "audio_source": "generate", "visual_intent": "drop"},
                        {"line_id": "line_004", "role": "explanation", "text": "Mass stays constant.", "claim_ids": ["C1"], "audio_source": "generate", "visual_intent": "label"},
                        {"line_id": "line_005", "role": "payoff", "text": "Nothing left. Weight fell because g fell.", "claim_ids": ["C1"], "audio_source": "generate", "visual_intent": "reveal"},
                    ],
                }

            with patch.object(pipeline, "_model_json", side_effect=fake_model_json):
                with patch("template_lab.shorts.pipeline.create_edl", return_value={"version": "1.0", "segments": []}):
                    with patch("template_lab.shorts.pipeline.build_provenance", return_value={"source_reels": []}):
                        with patch("template_lab.shorts.pipeline.write_manifest"):
                            state = pipeline.create("candidate_001", "short_001", use_model=True)
            self.assertEqual(state["short_id"], "short_001")
            prompt = (parent / "shorts/short_001/debug/script_writing_prompt.txt").read_text(encoding="utf-8")
            self.assertNotIn("required_schema_example", prompt)


if __name__ == "__main__":
    unittest.main()
