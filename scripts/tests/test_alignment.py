from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from align_lyrics import parse_alignment, project_morae_from_words, main as align_main


class ForcedAlignmentTests(unittest.TestCase):
    def test_parse_mfa_json_adds_cycle_offset(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            payload = {
                "start": 0,
                "end": 2.0,
                "tiers": {
                    "words": {"type": "interval", "entries": [[0.2, 0.8, "じゅげむ"]]},
                    "phones": {"type": "interval", "entries": [[0.2, 0.4, "dʑ"], [0.4, 0.8, "e"]]},
                },
            }
            (root / "cycle-01.json").write_text(json.dumps(payload), encoding="utf-8")
            units, failed = parse_alignment(
                root,
                [{"id": "cycle-01", "start_s": 12.0, "end_s": 14.0, "reference": "じゅげむ"}],
                language="ja",
            )
            self.assertEqual(failed, [])
            self.assertAlmostEqual(units["words"][0]["start_s"], 12.2)
            self.assertAlmostEqual(units["phones"][1]["end_s"], 12.8)
            self.assertEqual([row["label"] for row in units["morae"]], ["じゅ", "げ", "む"])

    def test_missing_segment_is_preserved_as_failure(self):
        with tempfile.TemporaryDirectory() as td:
            units, failed = parse_alignment(
                Path(td),
                [{"id": "cycle-09", "start_s": 1.0, "end_s": 2.0, "reference": "x"}],
                language="ja",
            )
            self.assertEqual(units["words"], [])
            self.assertEqual(failed[0]["reason"], "mfa-output-missing")

    def test_mora_projection_declares_approximation(self):
        rows = project_morae_from_words([
            {"segment_id": "x", "start_s": 1.0, "end_s": 1.6, "label": "じゅげむ"}
        ])
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["timing_method"], "within-word-equal-projection-from-mfa-word")
        self.assertAlmostEqual(rows[-1]["end_s"], 1.6)

    def test_mfa_log_is_printed_on_failure(self):
        import io
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            audio = root / "dummy.wav"
            audio.write_text("dummy audio", encoding="utf-8")

            # mock mutagen reference text since clip_audio and other tools rely on it
            with patch("align_lyrics.reference_text", return_value="dummy lyrics\n"), \
                 patch("align_lyrics.clip_audio"), \
                 patch("sys.argv", ["align_lyrics.py", str(audio), "--out", str(root / "out"), "--language", "en", "--dictionary", "dummy_dict", "--acoustic-model", "dummy_model"]), \
                 patch("subprocess.run") as mock_run, \
                 patch("sys.stderr", new_callable=io.StringIO) as mock_stderr:

                mock_run.return_value.returncode = 1
                mock_run.return_value.stdout = "dummy mfa stdout"
                mock_run.return_value.stderr = "dummy mfa stderr"

                with self.assertRaisesRegex(RuntimeError, "MFA exited with code 1; log content printed to stderr"):
                    align_main()

                err_output = mock_stderr.getvalue()
                self.assertIn("--- MFA LOG OUTPUT START ---", err_output)
                self.assertIn("dummy mfa stdout\ndummy mfa stderr", err_output)


if __name__ == "__main__":
    unittest.main()
