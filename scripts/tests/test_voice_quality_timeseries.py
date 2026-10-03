from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common.voice_quality import autocorrelation_hnr_db
from common.voice_quality_timeseries import (
    decimate_pitch_points,
    frame_voice_quality_series,
    local_pitch_modulation_metrics,
    local_autocorrelation_hnr_db,
    parse_pitch_consensus,
)


class VoiceQualityTimeSeriesTests(unittest.TestCase):
    def test_parse_and_decimate_pitch_points(self):
        rows = [
            {"time_s": f"{i * 0.01:.2f}", "selected_f0_hz": "220", "selected_confidence": "0.9"}
            for i in range(11)
        ]
        points = parse_pitch_consensus(rows)
        selected = decimate_pitch_points(points, hop_s=0.02)
        self.assertEqual(len(points), 11)
        self.assertEqual([round(x[0], 2) for x in selected], [0.0, 0.02, 0.04, 0.06, 0.08, 0.1])

    def test_local_vibrato_finds_extent_and_rate(self):
        times = np.arange(0.0, 1.01, 0.01)
        cents = 35.0 * np.sin(2.0 * np.pi * 6.0 * times)
        points = [
            (float(t), float(220.0 * 2.0 ** (c / 1200.0)), 0.95)
            for t, c in zip(times, cents)
        ]
        metric = local_pitch_modulation_metrics(points, 0.5, window_s=0.8)
        self.assertIsNotNone(metric["extent_cents_p95_p05"])
        self.assertGreater(metric["extent_cents_p95_p05"], 55.0)
        self.assertIsNotNone(metric["rate_hz"])
        self.assertAlmostEqual(metric["rate_hz"], 6.0, delta=1.0)

    def test_local_vibrato_rejects_low_confidence(self):
        times = np.arange(0.0, 1.01, 0.01)
        points = [(float(t), 220.0, 0.2) for t in times]
        metric = local_pitch_modulation_metrics(points, 0.5, window_s=0.8)
        self.assertIsNone(metric["extent_cents_p95_p05"])
        self.assertIsNone(metric["rate_hz"])


    def test_fast_local_autocorrelation_matches_m6_definition(self):
        sr = 16000
        t = np.arange(int(0.08 * sr), dtype=float) / sr
        tone = np.zeros_like(t)
        for harmonic in range(1, 12):
            tone += (0.6 / harmonic) * np.sin(2.0 * np.pi * 220.0 * harmonic * t)
        reference = autocorrelation_hnr_db(tone, sr, 220.0)
        fast = local_autocorrelation_hnr_db(tone, sr, 220.0)
        self.assertIsNotNone(reference)
        self.assertIsNotNone(fast)
        self.assertAlmostEqual(fast, reference, places=10)

    def test_frame_series_reports_local_metrics(self):
        sr = 16000
        duration = 1.2
        times = np.arange(0.0, duration, 0.01)
        cents = 20.0 * np.sin(2.0 * np.pi * 5.5 * times)
        f0 = 220.0 * (2.0 ** (cents / 1200.0))
        t_audio = np.arange(int(duration * sr), dtype=float) / sr
        audio = np.zeros_like(t_audio)
        for harmonic in range(1, 20):
            audio += (0.5 / harmonic) * np.sin(
                2.0 * np.pi * 220.0 * harmonic * t_audio
            )
        points = [(float(t), float(freq), 0.95) for t, freq in zip(times, f0)]
        rows = frame_voice_quality_series(audio, sr, points, hop_s=0.02)
        self.assertGreater(len(rows), 20)
        self.assertTrue(any(row["autocorrelation_hnr_db"] is not None for row in rows))
        self.assertTrue(any(row["spectral_tilt_db_per_octave"] is not None for row in rows))
        self.assertTrue(any(row["local_vibrato_extent_cents_p95_p05"] is not None for row in rows))


if __name__ == "__main__":
    unittest.main()
