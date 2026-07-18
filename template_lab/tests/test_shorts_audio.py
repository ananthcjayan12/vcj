import unittest

from template_lab.shorts.audio import match_source_range


class ShortAudioTests(unittest.TestCase):
    def test_word_boundary_match(self):
        data = {"words": [{"paragraph_id": "p", "word": word, "start": i*.2, "end": (i+1)*.2} for i, word in enumerate("mass stays constant on moon".split())]}
        start, end, confidence = match_source_range("stays constant", "p", data)
        self.assertAlmostEqual(start, .2)
        self.assertAlmostEqual(end, .6)
        self.assertEqual(confidence, 1)


if __name__ == "__main__": unittest.main()
