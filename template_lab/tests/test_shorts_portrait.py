import tempfile
import unittest
from pathlib import Path

from template_lab.shorts.portrait import write_manifest
from template_lab.shorts.validation import validate_manifest, validate_tsx


class ShortPortraitTests(unittest.TestCase):
    def test_portrait_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = write_manifest(Path(tmp), "parent", "short_001", 30)
            validate_manifest(manifest)
            self.assertEqual((manifest["profile"]["width"], manifest["profile"]["height"]), (1080, 1920))

    def test_scale_down_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"short_001.tsx"
            path.write_text("import './short_001.cues'; import '../short-presentation'; const x=<Rect width={1920} scale={0.5}/>;")
            with self.assertRaises(ValueError): validate_tsx(path, "short_001")


if __name__ == "__main__": unittest.main()
