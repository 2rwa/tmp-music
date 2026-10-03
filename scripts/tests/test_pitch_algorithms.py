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

    def test_low_confidence_crepe_falls_back_to_high_confidence_pyin(self):
        rows = consensus_frames(
            [0.0, 0.01],
            [440.0, 440.0],
            [441.0, 441.0],
            [0.95, 0.50],
            [0.05, 0.05],
            pyin_fallback_confidence=0.80,
        )
        self.assertEqual(rows[0]["agreement"], "low-confidence-crepe")
        self.assertEqual(rows[0]["selected_source"], "pyin-fallback")
        self.assertAlmostEqual(rows[0]["selected_f0_hz"], 440.0)
        self.assertEqual(rows[1]["selected_source"], "none")

    def test_stable_detector_preserves_evidence_label(self):
        t = np.arange(0.0, 1.0, 0.01)
        f0 = np.full_like(t, 440.0)
        confidence = np.ones_like(t)
        evidence = ["pyin-fallback"] * len(t)
        segments = detect_stable_segments(t, f0, confidence, evidence=evidence)
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0]["evidence"], "pyin-fallback")
        self.assertEqual(segments[0]["pyin_fallback_fraction"], 1.0)

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
        slow_gliss = 440.0 * 2 ** ((40.0 * t) / 1200.0)
        segments = detect_stable_segments(t, slow_gliss, confidence)
        self.assertEqual(len(segments), 0)

    def test_fit_equal_divisions_handles_wrap_boundary(self):
        targets = [
            {
                "median_f0_hz": 440.0 * 2 ** (cents / 1200.0),
                "duration_s": 1.0,
                "median_confidence": 1.0,
            }
            for cents in (49.0, -49.0)
        ]
        result = fit_equal_divisions(targets, (12,))
        model = result["models"][0]
        self.assertAlmostEqual(abs(float(model["estimated_global_offset_cents"])), 50.0, places=1)
        self.assertAlmostEqual(float(model["weighted_rmse_cents"]), 1.0, places=1)

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
        self.assertEqual(result["measurement_status"], "ok")
        models = {row["edo"]: row for row in result["models"]}
        self.assertLess(models[19]["weighted_rmse_cents"], 1e-6)
        self.assertLess(models[19]["weighted_rmse_cents"], models[12]["weighted_rmse_cents"])


    def test_empty_tuning_is_explicitly_insufficient(self):
        result = fit_equal_divisions([], (12, 19, 24, 31))
        self.assertEqual(result["measurement_status"], "insufficient_stable_targets")
        self.assertEqual(result["target_count"], 0)
        self.assertEqual(result["models"], [])

if __name__ == "__main__":
    unittest.main()
