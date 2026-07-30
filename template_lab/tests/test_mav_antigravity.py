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

from mav_antigravity import _binary, _model_catalog, call_antigravity_text


class AntigravityCliTest(unittest.TestCase):
    def test_explicit_binary_is_discovered(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "agy"
            executable.touch()
            executable.chmod(0o755)
            with patch.dict(os.environ, {"MAV_ANTIGRAVITY_BIN": str(executable), "PATH": ""}, clear=False):
                self.assertEqual(_binary(), str(executable))

    def test_desktop_launcher_gets_specific_install_hint(self) -> None:
        response = SimpleNamespace(returncode=0, stdout="Usage: agy chat [options]", stderr="")
        with patch("mav_antigravity.subprocess.run", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "desktop launcher"):
                _model_catalog("/fake/agy")

    def test_headless_call_is_sandboxed_and_omits_default_model_flag(self) -> None:
        completed = SimpleNamespace(returncode=0, stdout="planned script", stderr="")
        with (
            patch("mav_antigravity._binary", return_value="/fake/agy"),
            patch("mav_antigravity._model_catalog", return_value=("claude-sonnet-4-6",)),
            patch("mav_antigravity.subprocess.run", return_value=completed) as run,
            patch("mav_antigravity.record_model_usage"),
            patch.dict(
                os.environ,
                {
                    "MAV_SCRIPT_STRUCTURE_MODEL": "authenticated-default",
                },
                clear=False,
            ),
        ):
            result = call_antigravity_text(task="script_structure", system="system", user="user")

        self.assertEqual(result, "planned script")
        command = run.call_args.args[0]
        self.assertIn("--print", command)
        self.assertIn("--sandbox", command)
        self.assertNotIn("--effort", command)
        self.assertNotIn("--model", command)

    def test_explicit_authenticated_model_is_forwarded(self) -> None:
        completed = SimpleNamespace(returncode=0, stdout="planned script", stderr="")
        with (
            patch("mav_antigravity._binary", return_value="/fake/agy"),
            patch(
                "mav_antigravity._model_catalog",
                return_value=("claude-sonnet-4-6", "claude-opus-4-6-thinking"),
            ),
            patch("mav_antigravity.subprocess.run", return_value=completed) as run,
            patch("mav_antigravity.record_model_usage"),
            patch.dict(
                os.environ,
                {"MAV_SCRIPT_STRUCTURE_MODEL": "claude-opus-4-6-thinking"},
                clear=False,
            ),
        ):
            call_antigravity_text(task="script_structure", system="system", user="user")

        command = run.call_args.args[0]
        self.assertEqual(command[command.index("--model") + 1], "claude-opus-4-6-thinking")

    def test_model_missing_from_authenticated_catalog_is_rejected(self) -> None:
        with (
            patch("mav_antigravity._binary", return_value="/fake/agy"),
            patch("mav_antigravity._model_catalog", return_value=("claude-sonnet-4-6",)),
            patch.dict(
                os.environ,
                {"MAV_SCRIPT_STRUCTURE_MODEL": "claude-sonnet-5"},
                clear=False,
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "Available models: claude-sonnet-4-6"):
                call_antigravity_text(task="script_structure", system="system", user="user")


if __name__ == "__main__":
    unittest.main()
