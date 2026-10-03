from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import cli
from common.provenance import build_provenance
from common.schema import validate_provenance, validate_status


class FoundationTests(unittest.TestCase):
    def test_track_configs_load(self):
        config_dir = cli.REPO_ROOT / "config" / "tracks"
        whisper = cli.load_track("whisper-ao", config_dir)
        jugemu = cli.load_track("jugemu", config_dir)
        self.assertEqual(whisper.language, "en")
        self.assertEqual(jugemu.language, "ja")
        self.assertFalse(whisper.config["analysis"]["repetitions"])
        self.assertTrue(jugemu.config["analysis"]["repetitions"])

    def test_unknown_track_fails_clearly(self):
        with self.assertRaisesRegex(ValueError, "unknown track"):
            cli.load_track("does-not-exist", cli.REPO_ROOT / "config" / "tracks")

    def test_sha_mismatch_is_fatal(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.mp3"
            p.write_bytes(b"not the expected source")
            track = cli.Track("x", p, "x.mp3", "0" * 64, None, "en", {})
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                cli.verify_source(track)

    def test_full_plan_is_track_specific(self):
        config_dir = cli.REPO_ROOT / "config" / "tracks"
        whisper = cli.load_track("whisper-ao", config_dir)
        jugemu = cli.load_track("jugemu", config_dir)
        self.assertEqual(cli.planned_stages(whisper, "full"), ["acoustic", "asr"])
        self.assertEqual(cli.planned_stages(jugemu, "full"), ["acoustic", "repetition", "asr"])

    def test_existing_analyzers_are_mapped(self):
        config_dir = cli.REPO_ROOT / "config" / "tracks"
        jugemu = cli.load_track("jugemu", config_dir)
        acoustic, _, _, _ = cli.stage_command(jugemu, "acoustic", "small")
        repetition, params, _, _ = cli.stage_command(jugemu, "repetition", "small")
        separation, separation_params, separation_models, _ = cli.stage_command(jugemu, "separate", "small")
        asr, asr_params, models, _ = cli.stage_command(jugemu, "asr", "small")
        self.assertIn("scripts/analyze_audio.py", acoustic)
        self.assertIn("scripts/repetition_analysis.py", repetition)
        self.assertIn("scripts/separate_vocals.py", separation)
        self.assertIn("scripts/asr_compare.py", asr)
        self.assertEqual(params["template"]["template_start_s"], 12.0)
        self.assertEqual(separation_params["device"], "cpu")
        self.assertEqual(separation_models["demucs"], "htdemucs")
        self.assertEqual(asr_params["modes"], ["auto", "ja"])
        self.assertEqual(models["faster-whisper"], "small")

    def test_common_schema(self):
        provenance = build_provenance(
            source_path="samples/x.mp3",
            source_sha256="a" * 64,
            analyzer="test",
            parameters={"x": 1},
            models={},
            tool_versions={"python": "test"},
        )
        validate_provenance(provenance)
        validate_status({
            "schema_version": 1,
            "status": "success",
            "warnings": [],
            "started_from": "source",
            "outputs": ["analysis/x/result.json"],
        })
        with self.assertRaisesRegex(ValueError, "at least one output"):
            validate_status({
                "schema_version": 1,
                "status": "success",
                "warnings": [],
                "started_from": "source",
                "outputs": [],
            })


if __name__ == "__main__":
    unittest.main()
