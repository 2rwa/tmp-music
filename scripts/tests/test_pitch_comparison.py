from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from compare_pitch_sources import compare_sources, render_markdown, summarize_source


class PitchComparisonTests(unittest.TestCase):
    def test_compare_sources_reports_scalar_and_edo_deltas(self):
        mix = {
            "pyin_voiced_fraction": 0.5,
            "crepe_reliable_fraction": 0.2,
            "crepe_periodicity_median": 0.1,
            "consensus_coverage": 0.1,
            "selected_coverage": 0.4,
            "stable_target_count": 10,
            "stable_duration_s": 5.0,
            "tuning_target_count": 10,
            "tuning_models": [
                {"edo": 12, "weighted_rmse_cents": 14.0, "estimated_global_offset_cents": 2.0}
            ],
        }
        vocals = {
            "pyin_voiced_fraction": 0.7,
            "crepe_reliable_fraction": 0.6,
            "crepe_periodicity_median": 0.4,
            "consensus_coverage": 0.5,
            "selected_coverage": 0.65,
            "stable_target_count": 16,
            "stable_duration_s": 8.0,
            "tuning_target_count": 16,
            "tuning_models": [
                {"edo": 12, "weighted_rmse_cents": 9.0, "estimated_global_offset_cents": 3.0}
            ],
        }
        result = compare_sources(mix, vocals)
        self.assertAlmostEqual(result["vocals_minus_mix"]["pyin_voiced_fraction"], 0.2)
        self.assertEqual(result["vocals_minus_mix"]["stable_target_count"], 6.0)
        self.assertEqual(result["tuning_model_comparison"][0]["vocal_minus_mix_rmse_cents"], -5.0)
        md = render_markdown("x", result)
        self.assertIn("Pitch mix vs vocal comparison", md)
        self.assertIn("Interpretation boundary", md)

    def test_summarize_source_supports_old_consensus_schema(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "targets").mkdir()
            (root / "tuning").mkdir()
            (root / "summary.json").write_text(json.dumps({
                "pyin": {"voiced_fraction": 0.6},
                "crepe": {"reliable_fraction": 0.4},
                "consensus": {"consensus_coverage": 0.3},
            }))
            (root / "targets" / "summary.json").write_text(json.dumps({
                "stable_target_count": 4,
                "stable_duration_s": 2.5,
            }))
            (root / "tuning" / "tuning-models.json").write_text(json.dumps({
                "target_count": 4,
                "models": [],
            }))
            summary = summarize_source(root)
            self.assertEqual(summary["selected_coverage"], 0.3)
            self.assertEqual(summary["stable_measurement_status"], "ok")
            self.assertEqual(summary["tuning_measurement_status"], "ok")


if __name__ == "__main__":
    unittest.main()
