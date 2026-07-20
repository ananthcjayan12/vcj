from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from mav_grok import _binary, _resolve_model


class GrokDiscoveryTest(unittest.TestCase):
    def test_legacy_build_alias_resolves_to_authenticated_default(self) -> None:
        self.assertEqual(_resolve_model("grok-build", "grok-4.5", ("grok-4.5",)), "grok-4.5")

    def test_unknown_model_reports_available_choices(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "Available models: grok-4.5"):
            _resolve_model("missing", "grok-4.5", ("grok-4.5",))

    def test_explicit_binary_is_discovered(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "grok"
            executable.touch()
            executable.chmod(0o755)
            with patch.dict(os.environ, {"MAV_GROK_BIN": str(executable), "PATH": ""}, clear=False):
                self.assertEqual(_binary(), str(executable))

    def test_missing_binary_has_install_hint(self) -> None:
        with patch.dict(os.environ, {"MAV_GROK_BIN": "", "PATH": ""}, clear=False), patch("mav_grok.Path.home", return_value=Path("/missing")):
            with self.assertRaisesRegex(RuntimeError, "https://x.ai/cli"):
                _binary()
