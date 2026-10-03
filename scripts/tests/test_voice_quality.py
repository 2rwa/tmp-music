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
    parse_praat_cpps_hnr,
    parse_praat_voice_measurements,
    parse_praat_version,
    parse_version_triplet,
    segment_voice_quality,
    detect_pitch_movement_events,
    detect_register_transition_candidates,
    version_at_least,
    spectral_tilt_db_per_octave,
)


class VoiceQualityTests(unittest.TestCase):
    def test_praat_output_and_version_parsing(self):
        self.assertEqual(
            parse_praat_cpps_hnr("CPPS=27.25\tHNR=12.5\n"),
            (27.25, 12.5),
        )
        current = parse_praat_version("Praat 6.4.49 (December 23 2025)")
        self.assertEqual(current, (6, 4, 49))
        self.assertTrue(version_at_least(current, parse_version_triplet("6.4.39")))
        self.assertFalse(version_at_least((6, 4, 38), parse_version_triplet("6.4.39")))

    def test_extended_praat_formant_parsing(self):
        result = parse_praat_voice_measurements(
            "CPPS=27.25\tHNR=12.5\tF1=510.0\tF2=1510.0\tF3=2510.0\n"
        )
        self.assertEqual(result["praat_cpps_db"], 27.25)
        self.assertEqual(result["praat_hnr_cc_db"], 12.5)
        self.assertEqual(result["praat_f1_hz"], 510.0)
        self.assertEqual(result["praat_f2_hz"], 1510.0)
        self.assertEqual(result["praat_f3_hz"], 2510.0)

    def test_pitch_movement_detects_ramp_but_not_vibrato(self):
        times = np.arange(0.0, 0.61, 0.01)
        ramp_cents = 500.0 * times
        ramp = [
            {
                "time_s": float(t),
                "selected_f0_hz": float(220.0 * (2.0 ** (c / 1200.0))),
                "selected_confidence": 0.9,
            }
            for t, c in zip(times, ramp_cents)
        ]
        vibrato_cents = 35.0 * np.sin(2.0 * np.pi * 6.0 * times)
        vibrato = [
            {
                "time_s": float(t),
                "selected_f0_hz": float(220.0 * (2.0 ** (c / 1200.0))),
                "selected_confidence": 0.9,
            }
            for t, c in zip(times, vibrato_cents)
        ]
        self.assertGreaterEqual(len(detect_pitch_movement_events(ramp)), 1)
        self.assertEqual(detect_pitch_movement_events(vibrato), [])

        low_confidence_ramp = [
            {**row, "selected_confidence": 0.2}
            for row in ramp
        ]
        self.assertEqual(detect_pitch_movement_events(low_confidence_ramp), [])

        missing_confidence_ramp = [
            {key: value for key, value in row.items() if key != "selected_confidence"}
            for row in ramp
        ]
        self.assertEqual(detect_pitch_movement_events(missing_confidence_ramp), [])

    def test_register_transition_requires_multiple_features(self):
        before = {
            "stable_target_index": 1,
            "start_s": 0.0,
            "end_s": 0.4,
            "median_f0_hz": 200.0,
            "praat_cpps_db": 20.0,
            "praat_hnr_cc_db": 15.0,
            "median_autocorrelation_hnr_db": 14.0,
            "median_spectral_tilt_db_per_octave": -3.0,
            "median_rms_dbfs": -20.0,
            "praat_f1_hz": 500.0,
            "praat_f2_hz": 1500.0,
            "praat_f3_hz": 2500.0,
            "vibrato_extent_cents_p95_p05": 30.0,
        }
        after = dict(before)
        after.update({
            "stable_target_index": 2,
            "start_s": 0.5,
            "end_s": 0.9,
            "median_f0_hz": 300.0,
            "praat_cpps_db": 14.0,
            "praat_hnr_cc_db": 9.0,
        })
        candidates = detect_register_transition_candidates([before, after])
        self.assertEqual(len(candidates), 1)
        self.assertIn("f0_cents", candidates[0]["changed_features"])
        self.assertIn("praat_cpps_db", candidates[0]["changed_features"])

        f0_only = dict(after)
        f0_only["praat_cpps_db"] = before["praat_cpps_db"]
        f0_only["praat_hnr_cc_db"] = before["praat_hnr_cc_db"]
        self.assertEqual(
            detect_register_transition_candidates([before, f0_only]),
            [],
        )

        formant_only = dict(before)
        formant_only.update({
            "stable_target_index": 2,
            "start_s": 0.5,
            "end_s": 0.9,
            "median_f0_hz": 300.0,
            "praat_f1_hz": 800.0,
            "praat_f2_hz": 1900.0,
            "praat_f3_hz": 3000.0,
        })
        self.assertEqual(
            detect_register_transition_candidates([before, formant_only]),
            [],
        )

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
