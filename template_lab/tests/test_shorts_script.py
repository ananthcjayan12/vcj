import unittest

from template_lab.shorts.schemas import ShortsValidationError, validate_script
from template_lab.shorts.script import finalize_model_script, resolve_clause_references


class ShortScriptTests(unittest.TestCase):
    def test_reuse_requires_range(self):
        script = {"target_duration_seconds": 30, "claim_ids": ["C"], "lines": [
            {"line_id": "line_001", "role": "hook", "text": "Why?", "audio_source": "generate", "claim_ids": ["C"]},
            {"line_id": "line_002", "role": "payoff", "text": "Because physics.", "audio_source": "reuse", "source_paragraph_id": "p", "claim_ids": ["C"]},
        ]}
        with self.assertRaises(ShortsValidationError):
            validate_script(script, {"C"})

    def test_clause_id_resolves_exact_range(self):
        clauses = [{
            "clause_id": "clause_001",
            "paragraph_id": "paragraph_04",
            "text": "Her mass remains constant.",
            "source_word_start": 18,
            "source_word_end": 21,
            "claim_ids": ["C1"],
        }]
        script = {
            "lines": [{
                "line_id": "line_002",
                "role": "explanation",
                "text": "Her mass remains constant.",
                "audio_source": "reuse",
                "clause_id": "clause_001",
                "claim_ids": ["C1"],
            }]
        }
        resolve_clause_references(script, clauses)
        line = script["lines"][0]
        self.assertEqual(line["source_paragraph_id"], "paragraph_04")
        self.assertEqual(line["source_word_start"], 18)
        self.assertEqual(line["source_word_end"], 21)

    def test_paraphrased_reuse_forced_to_catalogue(self):
        clauses = [{
            "clause_id": "clause_001",
            "paragraph_id": "paragraph_04",
            "text": "Her mass remains constant.",
            "source_word_start": 18,
            "source_word_end": 21,
        }]
        script = {
            "lines": [{
                "line_id": "line_002",
                "text": "Her mass stays constant for the whole jump.",
                "audio_source": "reuse",
                "clause_id": "clause_001",
            }]
        }
        resolve_clause_references(script, clauses)
        self.assertEqual(script["lines"][0]["text"], "Her mass remains constant.")
        self.assertEqual(script["lines"][0]["audio_source"], "reuse")
        self.assertEqual(script["lines"][0]["source_word_start"], 18)

    def test_near_paraphrase_reuse_forced_to_catalogue(self):
        clauses = [{
            "clause_id": "clause_008",
            "paragraph_id": "paragraph_04",
            "text": "Right after jumping, air resistance is small, so gravity dominates and she accelerates close to g.",
            "source_word_start": 0,
            "source_word_end": 14,
        }]
        script = {
            "lines": [{
                "line_id": "l2",
                "text": "Right after she jumps, air resistance is tiny, so gravity's basically in charge, and she speeds up at almost exactly g — 9.8 metres per second, every second.",
                "audio_source": "reuse",
                "clause_id": "clause_008",
            }]
        }
        resolve_clause_references(script, clauses)
        self.assertEqual(script["lines"][0]["audio_source"], "reuse")
        self.assertEqual(
            script["lines"][0]["text"],
            "Right after jumping, air resistance is small, so gravity dominates and she accelerates close to g.",
        )

    def test_clause_id_always_wins_over_model_wording(self):
        clauses = [{
            "clause_id": "clause_001",
            "paragraph_id": "paragraph_04",
            "text": "Density equals mass divided by volume.",
            "source_word_start": 0,
            "source_word_end": 5,
        }]
        script = {
            "lines": [{
                "line_id": "l2",
                "text": "The skydiver keeps falling faster until drag balances weight completely.",
                "audio_source": "reuse",
                "clause_id": "clause_001",
            }]
        }
        resolve_clause_references(script, clauses)
        self.assertEqual(script["lines"][0]["audio_source"], "reuse")
        self.assertEqual(script["lines"][0]["text"], "Density equals mass divided by volume.")

    def test_unknown_clause_rejected(self):
        with self.assertRaises(ValueError):
            resolve_clause_references({
                "lines": [{"line_id": "line_001", "text": "x", "audio_source": "reuse", "clause_id": "missing"}]
            }, [])

    def test_finalize_model_script(self):
        candidate = {
            "candidate_id": "candidate_001",
            "working_title": "Mass vs Weight",
            "target_duration_seconds": 35,
            "claim_ids": ["C1"],
            "hook": "Did she lose matter?",
            "payoff": "Mass stays constant.",
        }
        modeled = {
            "title": "Mass vs Weight",
            "target_duration_seconds": 35,
            "claim_ids": ["C1"],
            "lines": [
                {"line_id": "line_001", "role": "hook", "text": "Did she lose matter on the Moon?", "claim_ids": ["C1"], "audio_source": "generate", "visual_intent": "question card"},
                {"line_id": "line_002", "role": "setup", "text": "An astronaut steps onto the lunar surface.", "claim_ids": ["C1"], "audio_source": "generate", "visual_intent": "astronaut"},
                {"line_id": "line_003", "role": "tension", "text": "The scale reading drops. So what changed?", "claim_ids": ["C1"], "audio_source": "generate", "visual_intent": "scale"},
                {"line_id": "line_004", "role": "explanation", "text": "Her mass remains constant.", "claim_ids": ["C1"], "audio_source": "reuse", "clause_id": "clause_001", "visual_intent": "equation"},
                {"line_id": "line_005", "role": "payoff", "text": "Mass stays put. Weight changes because g changes.", "claim_ids": ["C1"], "audio_source": "generate", "visual_intent": "reveal"},
            ],
        }
        clauses = [{
            "clause_id": "clause_001",
            "paragraph_id": "paragraph_04",
            "text": "Her mass remains constant.",
            "source_word_start": 10,
            "source_word_end": 13,
            "claim_ids": ["C1"],
        }]
        narration = {"paragraphs": [{"id": "paragraph_04", "text": "Her mass remains constant.", "claim_ids": ["C1"]}]}
        script = finalize_model_script(modeled, short_id="short_001", candidate=candidate, narration=narration, clauses=clauses)
        self.assertEqual(script["short_id"], "short_001")
        reuse = next(line for line in script["lines"] if line["audio_source"] == "reuse")
        self.assertEqual(reuse["source_word_start"], 10)
        self.assertIn("quality_warnings", script)

    def test_generic_intro_rejected(self):
        script = {
            "target_duration_seconds": 30,
            "claim_ids": ["C"],
            "lines": [
                {"line_id": "line_001", "role": "hook", "text": "In this video we explain mass.", "audio_source": "generate", "claim_ids": ["C"]},
                {"line_id": "line_002", "role": "explanation", "text": "Mass is the amount of matter.", "audio_source": "generate", "claim_ids": ["C"]},
                {"line_id": "line_003", "role": "payoff", "text": "That is mass.", "audio_source": "generate", "claim_ids": ["C"]},
            ],
        }
        with self.assertRaises(ShortsValidationError):
            validate_script(script, {"C"})


if __name__ == "__main__":
    unittest.main()
