from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATOR = REPO_ROOT / "scripts" / "synthetic" / "generate_pitch_fixtures.py"


def zero_crossing_frequency(path: Path, start_s: float = 0.25, end_s: float = 1.75) -> float:
    with wave.open(str(path), "rb") as wf:
        sr = wf.getframerate()
        frames = wf.readframes(wf.getnframes())
    import array
    samples = array.array("h")
    samples.frombytes(frames)
    a = int(start_s * sr)
    b = min(len(samples), int(end_s * sr))
    crossings = sum(1 for x, y in zip(samples[a:b-1], samples[a+1:b]) if x <= 0 < y)
    return crossings / ((b - a) / sr)


class PitchFixtureTests(unittest.TestCase):
    def test_known_pitch_fixtures(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            subprocess.run([sys.executable, str(GENERATOR), "--out", str(out)], check=True, capture_output=True, text=True)
            manifest = json.loads((out / "manifest.json").read_text())
            self.assertEqual(manifest["sample_rate_hz"], 16000)
            f440 = zero_crossing_frequency(out / "p1-a4-440.wav")
            f25 = zero_crossing_frequency(out / "p2-a4-plus25c.wav")
            expected25 = 440 * 2 ** (25 / 1200)
            self.assertLess(abs(f440 - 440), 1.0)
            self.assertLess(abs(f25 - expected25), 1.0)
            self.assertGreater(f25, f440)
            self.assertTrue((out / "p3-glissando.wav").is_file())
            self.assertTrue((out / "p4-vibrato.wav").is_file())
            self.assertEqual(manifest["fixtures"]["p5-19edo-scale.wav"]["divisions"], 19)
            self.assertTrue((out / "p5-19edo-scale.wav").is_file())


if __name__ == "__main__":
    unittest.main()
