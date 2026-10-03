from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common.structure import (
    cycle_boundaries_from_period,
    dtw_distance,
    multiview_lag_profile,
    pairwise_cycle_distances,
    period_candidates,
    template_alignment_starts,
    view_agreement,
)
from synthetic.generate_structure_fixtures import MOTIF_FRAMES, fixture_arrays, main as generate_main


class StructureAlgorithmTests(unittest.TestCase):
    def test_aaaa_recovers_shortest_exact_period(self):
        views = fixture_arrays()["s1-aaaa"]
        profile = multiview_lag_profile(
            views,
            min_lag=MOTIF_FRAMES - 4,
            max_lag=MOTIF_FRAMES * 3 + 4,
        )
        candidates = period_candidates(profile, top_k=4, min_separation_frames=4)
        self.assertEqual(candidates[0]["lag_frames"], MOTIF_FRAMES)
        self.assertGreater(candidates[0]["combined_similarity"], 0.98)

    def test_abab_prefers_two_motif_period(self):
        views = fixture_arrays()["s2-abab"]
        profile = multiview_lag_profile(
            views,
            min_lag=MOTIF_FRAMES - 4,
            max_lag=MOTIF_FRAMES * 2 + 4,
        )
        candidates = period_candidates(profile, top_k=3, min_separation_frames=4)
        self.assertEqual(candidates[0]["lag_frames"], MOTIF_FRAMES * 2)
        self.assertGreater(candidates[0]["combined_similarity"], 0.98)

    def test_dtw_handles_time_stretch(self):
        views = fixture_arrays()["s3-time-stretch"]
        x = views["mfcc"]
        a = x[:MOTIF_FRAMES]
        stretched = x[MOTIF_FRAMES:MOTIF_FRAMES + 40]
        unrelated = fixture_arrays()["s2-abab"]["mfcc"][MOTIF_FRAMES:MOTIF_FRAMES * 2]
        stretch_distance = dtw_distance(a, stretched)["normalized_distance"]
        unrelated_distance = dtw_distance(a, unrelated)["normalized_distance"]
        self.assertLess(stretch_distance, 0.08)
        self.assertLess(stretch_distance, unrelated_distance)

    def test_pairwise_cycle_matrix_is_symmetric(self):
        x = fixture_arrays()["s1-aaaa"]["mfcc"]
        boundaries = cycle_boundaries_from_period(len(x), MOTIF_FRAMES)
        matrix = pairwise_cycle_distances(x, boundaries)
        self.assertEqual(matrix.shape, (4, 4))
        self.assertTrue(np.allclose(matrix, matrix.T))
        self.assertTrue(np.allclose(np.diag(matrix), 0.0))
        self.assertLess(float(np.max(matrix)), 1e-10)

    def test_view_agreement_groups_nearby_periods(self):
        groups = view_agreement({
            "mfcc": [32, 64],
            "chroma": [33, 65],
            "rhythm": [31, 96],
        }, tolerance_frames=2)
        best = max(groups, key=lambda row: row["view_count"])
        self.assertEqual(best["period_frames"], 32)
        self.assertEqual(best["view_count"], 3)

    def test_template_alignment_recovers_local_start_jitter(self):
        views = fixture_arrays()["s5-start-jitter"]
        rows = template_alignment_starts(
            {"mfcc": views["mfcc"]},
            anchor_frame=0,
            period_frames=MOTIF_FRAMES,
            template_frames=20,
            search_radius_frames=6,
        )
        self.assertEqual([row["expected_frame"] for row in rows[:3]], [0, 32, 64])
        self.assertEqual([row["aligned_frame"] for row in rows[:3]], [0, 36, 68])
        self.assertEqual([row["offset_frames"] for row in rows[:3]], [0, 4, 4])

    def test_generator_writes_known_answer_files(self):
        with tempfile.TemporaryDirectory() as td:
            old_argv = sys.argv
            try:
                sys.argv = ["generate_structure_fixtures.py", "--out", td]
                generate_main()
            finally:
                sys.argv = old_argv
            root = Path(td)
            self.assertTrue((root / "manifest.json").is_file())
            self.assertTrue((root / "s1-aaaa.npz").is_file())
            with np.load(root / "s1-aaaa.npz") as payload:
                self.assertEqual(payload["mfcc"].shape[0], MOTIF_FRAMES * 4)


if __name__ == "__main__":
    unittest.main()
