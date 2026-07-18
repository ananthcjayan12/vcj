import unittest

from template_lab.shorts.schemas import ShortsValidationError, validate_script


class ShortScriptTests(unittest.TestCase):
    def test_reuse_requires_range(self):
        script = {"target_duration_seconds": 30, "claim_ids": ["C"], "lines": [
            {"role": "hook", "text": "Why?", "audio_source": "generate"},
            {"role": "payoff", "text": "Because physics.", "audio_source": "reuse", "source_paragraph_id": "p"},
        ]}
        with self.assertRaises(ShortsValidationError): validate_script(script, {"C"})


if __name__ == "__main__": unittest.main()
