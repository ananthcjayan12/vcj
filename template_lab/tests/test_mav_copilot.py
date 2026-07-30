from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from mav_copilot import _binary, call_copilot_text


class CopilotCliTest(unittest.TestCase):
    def test_explicit_binary_is_discovered(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "copilot"
            executable.touch()
            executable.chmod(0o755)
            with patch.dict(os.environ, {"MAV_COPILOT_BIN": str(executable), "PATH": ""}, clear=False):
                self.assertEqual(_binary(), str(executable))

    def test_programmatic_call_uses_documented_silent_model_flags(self) -> None:
        completed = SimpleNamespace(returncode=0, stdout="script draft", stderr="")
        with (
            patch("mav_copilot._binary", return_value="/fake/copilot"),
            patch("mav_copilot._login_status"),
            patch("mav_copilot.subprocess.run", return_value=completed) as run,
            patch("mav_copilot.record_model_usage"),
            patch.dict(
                os.environ,
                {"MAV_SCRIPT_WRITING_MODEL": "claude-haiku-4.5"},
                clear=False,
            ),
        ):
            result = call_copilot_text(task="script_writing", system="system", user="user")

        self.assertEqual(result, "script draft")
        command = run.call_args.args[0]
        self.assertIn("-p", command)
        self.assertIn("-s", command)
        self.assertEqual(command[command.index("--model") + 1], "claude-haiku-4.5")
        self.assertIn("--no-custom-instructions", command)


if __name__ == "__main__":
    unittest.main()
