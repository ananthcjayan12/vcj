from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from mav_render import HYPERFRAMES_BIN, _hyperframes_command, _hyperframes_env, _write_hyperframes_composition


class MavRenderTest(unittest.TestCase):
    def test_hyperframes_env_disables_streaming_encode(self) -> None:
        self.assertEqual(_hyperframes_env()["PRODUCER_ENABLE_STREAMING_ENCODE"], "false")

    def test_hyperframes_env_disables_static_dedup(self) -> None:
        self.assertEqual(_hyperframes_env()["HF_STATIC_DEDUP"], "false")

    def test_render_uses_repo_pinned_hyperframes_binary(self) -> None:
        command = _hyperframes_command(
            composition_path=ROOT / "runs" / "smoke" / "compositions" / "master_v3.html",
            output_path=ROOT / "runs" / "smoke" / "renders" / "master_v3.mp4",
            fps=24,
            quality="draft",
            workers=1,
        )
        self.assertEqual(command[0], str(HYPERFRAMES_BIN))
        self.assertNotIn("--yes", command)
        self.assertNotIn("--no-install", command)

    def test_hyperframes_composition_removes_audio_tag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            composition_path = Path(tmp) / "master_v3.html"
            composition_path.write_text(
                """<!doctype html>
<html>
  <body>
    <div class="composition-root">
      <audio id="mav-audio" src="../voiceover.mp3" preload="auto"></audio>
    </div>
    <script>const audio = document.querySelector("#mav-audio");</script>
  </body>
</html>
""",
                encoding="utf-8",
            )

            render_path = _write_hyperframes_composition(composition_path)
            render_html = render_path.read_text(encoding="utf-8")

        self.assertTrue(render_path.name.endswith(".hyperframes.html"))
        self.assertNotIn("<audio", render_html)
        self.assertIn('document.querySelector("#mav-audio")', render_html)


if __name__ == "__main__":
    unittest.main()
