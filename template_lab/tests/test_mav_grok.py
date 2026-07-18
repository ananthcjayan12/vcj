from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from mav_grok import call_grok_text


class GrokCliTest(unittest.TestCase):
    @patch("mav_grok.record_model_usage")
    @patch("mav_grok.subprocess.run")
    @patch("mav_grok._login_status")
    @patch("mav_grok._binary", return_value="/tmp/grok")
    def test_headless_call_is_bounded_and_read_only(self, _binary, _login, run, usage) -> None:
        run.return_value = SimpleNamespace(returncode=0, stdout="answer", stderr="")
        with patch.dict(os.environ, {
            "MAV_REEL_SCRIPT_WRITING_MODEL": "grok-4.5",
            "MAV_REEL_SCRIPT_WRITING_REASONING_EFFORT": "high",
        }, clear=False):
            response = call_grok_text(task="reel_script_writing", system="system", user="user")
        self.assertEqual(response, "answer")
        command = run.call_args.args[0]
        self.assertIn("-p", command)
        self.assertIn("--output-format", command)
        self.assertIn("plain", command)
        self.assertIn("--sandbox", command)
        self.assertIn("read-only", command)
        self.assertIn("--no-subagents", command)
        self.assertIn("dontAsk", command)
        self.assertIn("Bash,Edit,Read,Grep,WebFetch", command)
        self.assertNotIn(str(ROOT.parent), command[command.index("--cwd") + 1])
        self.assertEqual(command[command.index("--model") + 1], "grok-4.5")
        usage.assert_called_once()


if __name__ == "__main__":
    unittest.main()
