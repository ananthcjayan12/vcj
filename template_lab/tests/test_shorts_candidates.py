import unittest

from template_lab.shorts.candidates import analyze, process_model_candidates
from template_lab.shorts.context import build_discovery_context
from template_lab.shorts.quality import deduplicate_candidates, hook_similarity
from template_lab.shorts.schemas import ShortsValidationError, validate_candidate


class ShortCandidateTests(unittest.TestCase):
    def test_sorted_candidates_and_scores(self):
        narration = {"paragraphs": [{"id": f"paragraph_{i:02d}", "text": f"Physics idea {i} makes a measurable prediction.", "claim_ids": [f"C{i}"]} for i in range(1, 5)]}
        story = {"beats": [{"beat_id": f"beat_{i:03d}", "claim_ids": [f"C{i}"]} for i in range(1, 5)]}
        manifest = {"reels": [{"scene_id": f"reel_{i:03d}"} for i in range(1, 5)]}
        result = analyze("parent", narration, story, manifest, "hash")
        self.assertGreaterEqual(len(result["candidates"]), 3)
        scores = [x["scores"]["overall_score"] for x in result["candidates"]]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertTrue(all(0 <= score <= 100 for score in scores))
        self.assertEqual(result.get("analysis_mode"), "deterministic_fallback")

    def test_dependent_language_rejected(self):
        item = {"archetype": "exam_trap", "hook": "As we saw earlier", "promise": "x", "payoff": "x", "claim_ids": ["C"], "source_segments": [],
                "scores": {k: 50 for k in ("standalone_score", "hook_score", "payoff_score", "visual_reuse_score", "audio_reuse_score", "exam_relevance_score", "portrait_suitability_score")}}
        with self.assertRaises(ShortsValidationError):
            validate_candidate(item, {"C"})

    def test_late_paragraph_can_become_candidate(self):
        paragraphs = [{"id": f"paragraph_{i:02d}", "text": f"Early filler sentence number {i}.", "claim_ids": [f"C{i}"]} for i in range(1, 8)]
        paragraphs.append({
            "id": "paragraph_08",
            "text": "An astronaut weighs less on the Moon. Did she lose matter?",
            "claim_ids": ["C8"],
        })
        narration = {"paragraphs": paragraphs}
        story = {"beats": [{"beat_id": f"beat_{i:03d}", "reel_id": f"reel_{i:03d}", "claim_ids": [f"C{i}"]} for i in range(1, 9)]}
        manifest = {"reels": [{"scene_id": f"reel_{i:03d}", "start": i * 10, "end": i * 10 + 8} for i in range(1, 9)]}
        result = analyze("parent", narration, story, manifest, "hash")
        source_ids = {pid for item in result["candidates"] for pid in item.get("source_paragraph_ids") or []}
        self.assertIn("paragraph_08", source_ids)

    def test_model_candidates_dedupe_same_concept(self):
        artifacts = {
            "parent": __import__("pathlib").Path("."),
            "narration": {"paragraphs": [
                {"id": "paragraph_01", "text": "Mass stays constant when gravity changes.", "claim_ids": ["C1"]},
                {"id": "paragraph_02", "text": "Weight equals mass times g.", "claim_ids": ["C2"]},
            ]},
            "story": {"beats": [
                {"beat_id": "beat_001", "reel_id": "reel_001", "claim_ids": ["C1"], "start": 0, "end": 8},
                {"beat_id": "beat_002", "reel_id": "reel_002", "claim_ids": ["C2"], "start": 8, "end": 16},
            ]},
            "manifest": {"reels": [
                {"scene_id": "reel_001", "start": 0, "end": 8},
                {"scene_id": "reel_002", "start": 8, "end": 16},
            ]},
            "timeline": {},
            "audio_manifest": {},
            "timestamps": {},
            "input": {"title": "Mass and weight"},
            "known_claims": {"C1", "C2"},
        }
        context = build_discovery_context(artifacts, parent_run_id="parent")
        raw = [
            {
                "concept_key": "mass-stays",
                "primary_claim_id": "C1",
                "supporting_claim_ids": [],
                "archetype": "misconception",
                "hook_mechanism": "counterintuitive_question",
                "working_title": "Lost Matter?",
                "hook": "She weighs less on the Moon. Did she lose matter?",
                "promise": "Separate mass from weight.",
                "payoff": "Mass stays constant. Weight changes with g.",
                "target_duration_seconds": 35,
                "source_paragraph_ids": ["paragraph_01"],
                "source_beat_ids": ["beat_001"],
                "source_reel_ids": ["reel_001"],
                "creative_rationale": "Contradiction.",
                "warnings": [],
                "self_scores": {"hook_score": 90, "payoff_score": 88, "standalone_score": 92, "exam_relevance_score": 80},
            },
            {
                "concept_key": "mass-stays",
                "primary_claim_id": "C1",
                "supporting_claim_ids": [],
                "archetype": "misconception",
                "hook_mechanism": "counterintuitive_question",
                "working_title": "Lost Matter Again?",
                "hook": "She weighs less on the Moon. Did she lose any matter?",
                "promise": "Separate mass from weight quickly.",
                "payoff": "Mass remains constant while weight changes.",
                "target_duration_seconds": 36,
                "source_paragraph_ids": ["paragraph_01"],
                "source_beat_ids": ["beat_001"],
                "source_reel_ids": ["reel_001"],
                "creative_rationale": "Same idea.",
                "warnings": [],
                "self_scores": {"hook_score": 89, "payoff_score": 87, "standalone_score": 91, "exam_relevance_score": 80},
            },
            {
                "concept_key": "weight-equals-mg",
                "primary_claim_id": "C2",
                "supporting_claim_ids": [],
                "archetype": "exam_trap",
                "hook_mechanism": "formula_trap",
                "working_title": "Is Weight Just Mass?",
                "hook": "Is weight just another word for mass?",
                "promise": "See the exam distinction in one line.",
                "payoff": "Weight is the force mg, not mass itself.",
                "target_duration_seconds": 32,
                "source_paragraph_ids": ["paragraph_02"],
                "source_beat_ids": ["beat_002"],
                "source_reel_ids": ["reel_002"],
                "creative_rationale": "Exam trap.",
                "warnings": [],
                "self_scores": {"hook_score": 84, "payoff_score": 86, "standalone_score": 90, "exam_relevance_score": 95},
            },
        ]
        # pad to satisfy process expectations when only 2 unique survive after needing 3
        for i in range(3, 7):
            raw.append({
                "concept_key": f"extra-{i}",
                "primary_claim_id": "C2" if i % 2 else "C1",
                "supporting_claim_ids": [],
                "archetype": "visual_explanation",
                "hook_mechanism": "comparison",
                "working_title": f"Extra Idea {i}",
                "hook": f"What does comparison number {i} reveal about gravity?",
                "promise": f"Spot distinction {i} fast.",
                "payoff": f"Distinction {i}: weight depends on g while mass does not.",
                "target_duration_seconds": 30 + i,
                "source_paragraph_ids": ["paragraph_02" if i % 2 else "paragraph_01"],
                "source_beat_ids": ["beat_002" if i % 2 else "beat_001"],
                "source_reel_ids": ["reel_002" if i % 2 else "reel_001"],
                "creative_rationale": "Variety.",
                "warnings": [],
                "self_scores": {"hook_score": 70 + i, "payoff_score": 70, "standalone_score": 75, "exam_relevance_score": 70},
            })
        payload = process_model_candidates(raw, context, timeline_id="hash")
        self.assertEqual(payload["analysis_mode"], "model_discovery")
        self.assertTrue(3 <= len(payload["candidates"]) <= 5)
        concept_keys = [item["concept_key"] for item in payload["candidates"]]
        self.assertEqual(len(concept_keys), len(set(concept_keys)))
        self.assertNotIn("mass-stays", concept_keys[1:])  # only one mass-stays at most
        self.assertEqual(concept_keys.count("mass-stays"), 1)
        self.assertGreaterEqual(hook_similarity("Did she lose matter?", "Did she lose any matter?"), 0.72)

    def test_dedupe_helper(self):
        items = [
            {"concept_key": "a", "hook": "Why does mass stay the same?", "primary_claim_id": "C1", "source_paragraph_ids": ["p1"], "scores": {"overall_score": 90}},
            {"concept_key": "a", "hook": "Why does mass remain the same?", "primary_claim_id": "C1", "source_paragraph_ids": ["p1"], "scores": {"overall_score": 88}},
            {"concept_key": "b", "hook": "Is weight a force?", "primary_claim_id": "C2", "source_paragraph_ids": ["p2"], "scores": {"overall_score": 85}},
            {"concept_key": "c", "hook": "What is g on the Moon?", "primary_claim_id": "C3", "source_paragraph_ids": ["p3"], "scores": {"overall_score": 80}},
        ]
        kept, rejected = deduplicate_candidates(items, final_count=5)
        self.assertGreaterEqual(len(kept), 3)
        self.assertTrue(any("duplicate_concept_key" in entry["reasons"] for entry in rejected))


if __name__ == "__main__":
    unittest.main()
