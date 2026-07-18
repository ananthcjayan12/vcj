import unittest

from template_lab.shorts.candidates import analyze
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

    def test_dependent_language_rejected(self):
        item = {"archetype": "exam_trap", "hook": "As we saw earlier", "promise": "x", "payoff": "x", "claim_ids": ["C"], "source_segments": [],
                "scores": {k: 50 for k in ("standalone_score", "hook_score", "payoff_score", "visual_reuse_score", "audio_reuse_score", "exam_relevance_score", "portrait_suitability_score")}}
        with self.assertRaises(ShortsValidationError): validate_candidate(item, {"C"})


if __name__ == "__main__": unittest.main()
