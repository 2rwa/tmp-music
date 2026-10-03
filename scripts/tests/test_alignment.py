from __future__ import annotations

import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from align_lyrics import main as align_main
from align_lyrics import (
    parse_alignment,
    prepare_segments,
    project_morae_from_phone_spans,
    project_morae_from_words,
)


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

    @patch("align_lyrics.clip_audio")
    def test_full_track_reference_window_is_preserved(self, mock_clip_audio):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source.mp3"
            source.touch()
            corpus = root / "corpus"
            segments = prepare_segments(
                source,
                "line one\nline two",
                corpus,
                structure=None,
                boundary_source="aligned_cycles",
                reference_cycle_lines=10,
                segment_start_s=0.0,
                segment_end_s=77.5,
            )
            mock_clip_audio.assert_called_once_with(source, 0.0, 77.5, corpus / "full-track.wav")
            self.assertEqual(segments[0]["start_s"], 0.0)
            self.assertEqual(segments[0]["end_s"], 77.5)
            self.assertEqual((corpus / "full-track.lab").read_text(encoding="utf-8"), "line one\nline two\n")

    def test_invalid_full_track_reference_window_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError, "greater than"):
                prepare_segments(
                    Path(td) / "source.mp3",
                    "line",
                    Path(td) / "corpus",
                    structure=None,
                    boundary_source="aligned_cycles",
                    reference_cycle_lines=10,
                    segment_start_s=10.0,
                    segment_end_s=5.0,
                )

    def test_mfa_log_is_printed_on_failure(self):
        import io

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            audio = root / "dummy.wav"
            audio.write_text("dummy audio", encoding="utf-8")
            out = root / "out"

            with patch("align_lyrics.reference_text", return_value="dummy lyrics\n"), \
                 patch("align_lyrics.clip_audio"), \
                 patch("sys.argv", [
                     "align_lyrics.py", str(audio), "--out", str(out),
                     "--language", "en", "--dictionary", "dummy_dict",
                     "--acoustic-model", "dummy_model",
                 ]), \
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
                self.assertIn("--- MFA LOG OUTPUT END ---", err_output)
                self.assertEqual(
                    (out / "mfa.log").read_text(encoding="utf-8"),
                    "dummy mfa stdout\ndummy mfa stderr",
                )

    def test_mora_projection_uses_phone_supported_span(self):
        rows, failed = project_morae_from_phone_spans(
            [{"segment_id": "x", "start_s": 1.0, "end_s": 2.0, "label": "じゅげむ"}],
            [
                {"segment_id": "x", "start_s": 1.2, "end_s": 1.3, "label": "dʑ"},
                {"segment_id": "x", "start_s": 1.3, "end_s": 1.5, "label": "ɯ"},
                {"segment_id": "x", "start_s": 1.5, "end_s": 1.6, "label": "g"},
                {"segment_id": "x", "start_s": 1.6, "end_s": 1.8, "label": "e"},
            ],
        )
        self.assertEqual(failed, [])
        self.assertEqual(len(rows), 3)
        self.assertAlmostEqual(rows[0]["start_s"], 1.2)
        self.assertAlmostEqual(rows[-1]["end_s"], 1.8)
        self.assertEqual(
            rows[0]["timing_method"],
            "within-word-equal-projection-over-mfa-phone-span",
        )

    def test_mora_projection_preserves_word_without_phone_support(self):
        rows, failed = project_morae_from_phone_spans(
            [{"segment_id": "cycle-07", "start_s": 1.0, "end_s": 5.0, "label": "ぽん"}],
            [{"segment_id": "cycle-07", "start_s": 5.0, "end_s": 5.1, "label": "p"}],
        )
        self.assertEqual(rows, [])
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["reason"], "no-phone-support-for-word")
        self.assertEqual(failed[0]["label"], "ぽん")

    def test_mora_projection_declares_approximation(self):
        rows = project_morae_from_words([
            {"segment_id": "x", "start_s": 1.0, "end_s": 1.6, "label": "じゅげむ"}
        ])
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["timing_method"], "within-word-equal-projection-from-mfa-word")
        self.assertAlmostEqual(rows[-1]["end_s"], 1.6)


if __name__ == "__main__":
    unittest.main()
