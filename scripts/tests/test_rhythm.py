from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATOR = REPO_ROOT / "scripts" / "synthetic" / "generate_rhythm_fixtures.py"


class RhythmFixtureTests(unittest.TestCase):
    def test_rhythm_fixture_manifests(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            subprocess.run([sys.executable, str(GENERATOR), "--out", str(out)], check=True, capture_output=True, text=True)
            manifest = json.loads((out / "manifest.json").read_text())
            r1 = manifest["fixtures"]["r1-100bpm.wav"]["click_times_s"]
            r2 = manifest["fixtures"]["r2-100bpm-eighths.wav"]["click_times_s"]
            r3 = manifest["fixtures"]["r3-drift-90-to-110.wav"]["click_times_s"]
            self.assertAlmostEqual(r1[1] - r1[0], 0.6, places=6)
            self.assertAlmostEqual(r2[1] - r2[0], 0.3, places=6)
            self.assertGreater(r3[1] - r3[0], r3[-1] - r3[-2])
            for name in manifest["fixtures"]:
                self.assertTrue((out / name).is_file())


if __name__ == "__main__":
    unittest.main()
