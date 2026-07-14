from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from mav_build_preview_v3 import _audio_src_for_run, _scene_section


class MavBuildPreviewTest(unittest.TestCase):
    def test_audio_source_is_relative_to_composition(self) -> None:
        run_path = ROOT / "runs" / "audio-path-test"
        self.assertEqual(_audio_src_for_run(run_path), "../voiceover.mp3")

    def test_scene_section_injects_content_inside_shell_wrapper(self) -> None:
        html = _scene_section(
            {
                "id": "scene_01",
                "start": 0,
                "duration": 4,
                "scene_html": '<div id="b01_card">Text</div><style>#b01_card{color:var(--ink);}</style>',
            }
        )

        self.assertIn('<div class="camera">', html)
        self.assertIn('<div class="v3-scene-content">', html)
        self.assertLess(html.index('<div class="camera">'), html.index('<div class="v3-scene-content">'))
        self.assertLess(html.index('<div class="v3-scene-content">'), html.index('id="b01_card"'))


if __name__ == "__main__":
    unittest.main()
