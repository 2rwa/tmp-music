from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common.japanese import edit_alignment, mora_error, morae_from_kana, normalize_kana


class JapaneseMetricTests(unittest.TestCase):
    def test_katakana_and_punctuation_normalize(self):
        self.assertEqual(normalize_kana("ジュゲム、じゅげむ！"), "じゅげむじゅげむ")

    def test_mora_segmentation(self):
        self.assertEqual(morae_from_kana("じゅげむ"), ["じゅ", "げ", "む"])
        self.assertEqual(morae_from_kana("きょう"), ["きょ", "う"])
        self.assertEqual(morae_from_kana("がっこう"), ["が", "っ", "こ", "う"])
        self.assertEqual(morae_from_kana("スーパー"), ["す", "ー", "ぱ", "ー"])
        self.assertEqual(morae_from_kana("ティファ"), ["てぃ", "ふぁ"])

    def test_mora_error_separates_substitution_deletion_insertion(self):
        metrics, rows = mora_error("じゅげむ", "じゅけむ")
        self.assertEqual(metrics["substitutions"], 1)
        self.assertEqual(metrics["deletions"], 0)
        self.assertEqual(metrics["insertions"], 0)
        self.assertAlmostEqual(metrics["error_rate"], 1 / 3)
        self.assertEqual([row["op"] for row in rows], ["=", "S", "="])

    def test_edit_alignment_counts_insertion(self):
        metrics, _ = edit_alignment(["じゅ", "げ", "む"], ["じゅ", "げ", "む", "よ"])
        self.assertEqual(metrics["insertions"], 1)
        self.assertEqual(metrics["reference_units"], 3)


if __name__ == "__main__":
    unittest.main()
