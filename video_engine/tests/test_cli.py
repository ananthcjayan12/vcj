from __future__ import annotations

import unittest

from video_engine.cli import (
    TOPIC_ORDER,
    _assessment_pattern_summary,
    _load_syllabus,
    _objective_records,
    _registered_scenes,
)


class VideoEngineRegistryTest(unittest.TestCase):
    def test_curriculum_counts_and_order_match(self) -> None:
        syllabus = _load_syllabus()
        refs = {topic["ref"] for topic in syllabus["topics"]}
        self.assertEqual(len(syllabus["topics"]), 58)
        self.assertEqual(len(_objective_records(syllabus)), 328)
        self.assertEqual(len(TOPIC_ORDER), 58)
        self.assertEqual(set(TOPIC_ORDER), refs)

    def test_animation_catalog_is_complete_and_machine_readable(self) -> None:
        scenes = _registered_scenes()
        self.assertEqual(len(scenes), 41)
        self.assertEqual(len({item["scene"] for item in scenes}), 41)
        self.assertTrue(all(item.get("category") for item in scenes))
        self.assertTrue(all(item.get("description") for item in scenes))
        self.assertTrue(all(item.get("parameter_schema", {}).get("type") == "object" for item in scenes))

    def test_question_research_returns_aggregates_not_question_text(self) -> None:
        count, facts = _assessment_pattern_summary("1.1")
        self.assertGreater(count, 0)
        self.assertTrue(facts)
        self.assertTrue(all(len(fact) < 500 for fact in facts))
        self.assertTrue(any("aggregate assessment-pattern evidence" in fact for fact in facts))


if __name__ == "__main__":
    unittest.main()
