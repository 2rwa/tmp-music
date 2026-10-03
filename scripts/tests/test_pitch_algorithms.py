from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common.pitch import consensus_frames, detect_stable_segments, fit_equal_divisions


class PitchAlgorithmTests(unittest.TestCase):
    def test_consensus_classifies_agreement(self):
        t = [0.0, 0.01, 0.02]
        pyin = [440.0, 440.0, 440.0]
        crepe = [440.0 * 2 ** (10 / 1200), 440.0 * 2 ** (35 / 1200), 440.0 * 2 ** (80 / 1200)]
        rows = consensus_frames(t, pyin, crepe, [0.9] * 3, [0.9] * 3)
        self.assertEqual([r["agreement"] for r in rows], ["strong", "weak", "disagreement"])
        self.assertIsNotNone(rows[0]["consensus_f0_hz"])
        self.assertIsNone(rows[2]["consensus_f0_hz"])

    def test_stable_detector_rejects_glissando_and_keeps_vibrato(self):
        t = np.arange(0.0, 2.0, 0.01)
        confidence = np.ones_like(t)
        stable = np.full_like(t, 440.0)
        gliss = 440.0 * 2 ** ((600.0 * t) / 1200.0)
        vibrato = 440.0 * 2 ** ((30.0 * np.sin(2 * np.pi * 6 * t)) / 1200.0)

        stable_segments = detect_stable_segments(t, stable, confidence)
        gliss_segments = detect_stable_segments(t, gliss, confidence)
        vibrato_segments = detect_stable_segments(t, vibrato, confidence)

        self.assertEqual(len(stable_segments), 1)
        self.assertEqual(len(gliss_segments), 0)
        self.assertEqual(len(vibrato_segments), 1)
        self.assertAlmostEqual(stable_segments[0]["median_f0_hz"], 440.0, places=3)
        self.assertGreater(vibrato_segments[0]["vibrato_extent_cents_p95_p05"], 40.0)

    def test_19edo_fixture_fits_19edo_better_than_12tet(self):
        targets = [
            {
                "median_f0_hz": 220.0 * 2 ** (step / 19.0),
                "duration_s": 0.25,
                "median_confidence": 1.0,
            }
            for step in range(20)
        ]
        result = fit_equal_divisions(targets, (12, 19, 24, 31))
        models = {row["edo"]: row for row in result["models"]}
        self.assertLess(models[19]["weighted_rmse_cents"], 1e-6)
        self.assertLess(models[19]["weighted_rmse_cents"], models[12]["weighted_rmse_cents"])


if __name__ == "__main__":
    unittest.main()
