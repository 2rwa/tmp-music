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

    def test_consensus_octave_agreement(self):
        t = [0.0, 0.01]
        pyin = [440.0, 440.0]
        crepe = [880.0, 220.0]  # Octave up, Octave down
        rows = consensus_frames(t, pyin, crepe, [0.9, 0.2], [0.8, 0.9])
        self.assertEqual([r["agreement"] for r in rows], ["octave-strong", "octave-strong"])
        # First frame: pyin has higher confidence (0.9 vs 0.8), so it uses pyin (440.0)
        self.assertEqual(rows[0]["consensus_f0_hz"], 440.0)
        # Second frame: crepe has higher confidence (0.9 vs 0.2), so it uses crepe (220.0)
        self.assertEqual(rows[1]["consensus_f0_hz"], 220.0)

    def test_consensus_respects_pyin_confidence(self):
        t = [0.0]
        pyin = [440.0]
        crepe = [440.0]
        # pYIN confidence is below the threshold of 0.1
        rows = consensus_frames(t, pyin, crepe, [0.05], [0.9])
        self.assertEqual(rows[0]["agreement"], "crepe-only")
        self.assertIsNone(rows[0]["consensus_f0_hz"])

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

    def test_stable_detector_rejects_slow_glissando(self):
        t = np.arange(0.0, 2.0, 0.01)
        confidence = np.ones_like(t)
        # Slow glissando: 40 cents per second (slope < 100 max_abs_slope_cents_per_s)
        # But overall drift over 2s is 80 cents, which > 50 max_drift_cents
        slow_gliss = 440.0 * 2 ** ((40.0 * t) / 1200.0)
        slow_gliss_segments = detect_stable_segments(t, slow_gliss, confidence)
        self.assertEqual(len(slow_gliss_segments), 0)

    def test_fit_equal_divisions_circular_offset(self):
        # Targets around the boundary of 12-TET (-49 cents and +49 cents from A4)
        targets = [
            {
                "median_f0_hz": 440.0 * 2 ** (49 / 1200.0),
                "duration_s": 1.0,
                "median_confidence": 1.0,
            },
            {
                "median_f0_hz": 440.0 * 2 ** (-49 / 1200.0),
                "duration_s": 1.0,
                "median_confidence": 1.0,
            }
        ]
        result = fit_equal_divisions(targets, [12])
        models = {row["edo"]: row for row in result["models"]}
        # The offset should be exactly at the boundary (50 cents or -50 cents)
        offset = models[12]["estimated_global_offset_cents"]
        self.assertAlmostEqual(abs(offset), 50.0, places=1)
        # Residual should be very small since they are both 1 cent away from the boundary
        self.assertAlmostEqual(models[12]["weighted_rmse_cents"], 1.0, places=1)

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
