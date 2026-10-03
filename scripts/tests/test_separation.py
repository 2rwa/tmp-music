from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common.separation import separation_diagnostics


class SeparationDiagnosticsTests(unittest.TestCase):
    def test_exact_resum_is_valid(self):
        sr = 16000
        t = np.arange(sr, dtype=np.float64) / sr
        vocals = 0.2 * np.sin(2 * np.pi * 440 * t)
        accompaniment = 0.1 * np.sin(2 * np.pi * 110 * t)
        source = vocals + accompaniment
        result = separation_diagnostics(source, vocals, accompaniment, sr)
        self.assertTrue(result["valid"])
        self.assertLess(result["resum_residual_rms_ratio"], 1e-12)
        self.assertGreater(result["vocals"]["rms"], 0)
        self.assertGreater(result["accompaniment"]["rms"], 0)

    def test_silent_stem_is_rejected(self):
        sr = 16000
        t = np.arange(sr, dtype=np.float64) / sr
        source = 0.2 * np.sin(2 * np.pi * 440 * t)
        result = separation_diagnostics(source, np.zeros_like(source), source, sr)
        self.assertFalse(result["valid"])
        self.assertTrue(any("vocal stem" in x for x in result["warnings"]))


if __name__ == "__main__":
    unittest.main()
