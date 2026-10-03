from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common.voice_quality import (
    autocorrelation_hnr_db,
    normalized_autocorrelation_peak,
    segment_voice_quality,
    spectral_tilt_db_per_octave,
)


class VoiceQualityTests(unittest.TestCase):
    def test_periodic_tone_has_higher_hnr_than_noisy_tone(self):
        sr = 16000
        t = np.arange(int(0.25 * sr), dtype=float) / sr
        tone = np.sin(2.0 * np.pi * 200.0 * t)
        rng = np.random.default_rng(20261003)
        noisy = tone + 0.7 * rng.normal(size=tone.size)
        frame = int(0.06 * sr)
        clean_hnr = autocorrelation_hnr_db(tone[:frame], sr, 200.0)
        noisy_hnr = autocorrelation_hnr_db(noisy[:frame], sr, 200.0)
        self.assertIsNotNone(clean_hnr)
        self.assertIsNotNone(noisy_hnr)
        self.assertGreater(clean_hnr, noisy_hnr + 3.0)

    def test_autocorrelation_search_tracks_expected_period(self):
        sr = 16000
        t = np.arange(int(0.08 * sr), dtype=float) / sr
        tone = np.sin(2.0 * np.pi * 250.0 * t)
        peak = normalized_autocorrelation_peak(tone, sr, 250.0)
        self.assertIsNotNone(peak)
        self.assertGreater(peak, 0.75)

    def test_steeper_harmonic_envelope_has_more_negative_tilt(self):
        sr = 16000
        t = np.arange(4096, dtype=float) / sr

        def harmonic_stack(power: float) -> np.ndarray:
            y = np.zeros_like(t)
            for harmonic in range(1, 40):
                freq = 150.0 * harmonic
                if freq >= sr / 2:
                    break
                y += (1.0 / (harmonic ** power)) * np.sin(2.0 * np.pi * freq * t)
            return y

        flat = spectral_tilt_db_per_octave(harmonic_stack(0.2), sr)
        steep = spectral_tilt_db_per_octave(harmonic_stack(1.5), sr)
        self.assertIsNotNone(flat)
        self.assertIsNotNone(steep)
        self.assertLess(steep, flat - 1.0)

    def test_segment_summary_reports_usable_frames(self):
        sr = 16000
        t = np.arange(int(0.3 * sr), dtype=float) / sr
        tone = np.zeros_like(t)
        for harmonic in range(1, 20):
            tone += (0.5 / harmonic) * np.sin(2.0 * np.pi * 180.0 * harmonic * t)
        result = segment_voice_quality(tone, sr, 180.0)
        self.assertGreater(result["frame_count"], 0)
        self.assertEqual(result["usable_frame_count"], result["frame_count"])
        self.assertGreater(result["autocorrelation_hnr_db"]["count"], 0)
        self.assertGreater(result["spectral_tilt_db_per_octave"]["count"], 0)


if __name__ == "__main__":
    unittest.main()
