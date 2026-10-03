#!/usr/bin/env python3
"""Generate M6 Level-2 time-series voice-quality measurements."""
from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import librosa
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common.voice_quality import parse_praat_version, parse_version_triplet, version_at_least
from common.voice_quality_timeseries import frame_voice_quality_series, parse_pitch_consensus

_CPP_MEAN_RE = re.compile(r"CPPS_MEAN=([^\t\r\n]+)")


def _float_or_none(value: object) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if np.isfinite(x) else None


def _read_praat_timeseries(path: Path, *, hop_s: float) -> list[dict[str, float | None]]:
    rows: list[dict[str, float | None]] = []
    next_time = -1e30
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        required = {"time_s", "praat_cpps_db", "praat_hnr_cc_db"}
        if not required.issubset(set(reader.fieldnames or [])):
            raise ValueError(f"unexpected Praat time-series columns: {reader.fieldnames}")
        for row in reader:
            t = _float_or_none(row.get("time_s"))
            cpps = _float_or_none(row.get("praat_cpps_db"))
            hnr = _float_or_none(row.get("praat_hnr_cc_db"))
            if t is None:
                continue
            if t + 1e-12 < next_time:
                continue
            rows.append({"time_s": t, "praat_cpps_db": cpps, "praat_hnr_cc_db": hnr})
            next_time = t + hop_s
    return rows


def _write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("audio", type=Path)
    p.add_argument("pitch_consensus", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--sr", type=int, default=16000)
    p.add_argument("--hop-ms", type=float, default=20.0)
    p.add_argument("--frame-length-ms", type=float, default=60.0)
    p.add_argument("--hnr-search-fraction", type=float, default=0.15)
    p.add_argument("--tilt-min-hz", type=float, default=200.0)
    p.add_argument("--tilt-max-hz", type=float, default=5000.0)
    p.add_argument("--min-rms-dbfs", type=float, default=-70.0)
    p.add_argument("--vibrato-window-s", type=float, default=0.8)
    p.add_argument("--vibrato-min-confidence", type=float, default=0.5)
    p.add_argument("--praat-bin", default="praat")
    p.add_argument(
        "--praat-script",
        type=Path,
        default=SCRIPT_DIR / "praat" / "measure_cpps_hnr_timeseries.praat",
    )
    p.add_argument("--praat-min-version", default="6.4.39")
    p.add_argument("--require-praat", action="store_true")
    args = p.parse_args()

    if args.hop_ms <= 0:
        raise ValueError("--hop-ms must be positive")
    hop_s = args.hop_ms / 1000.0
    y, sr = librosa.load(args.audio.resolve(), sr=args.sr, mono=True)
    with args.pitch_consensus.open(newline="", encoding="utf-8") as handle:
        consensus_rows = list(csv.DictReader(handle))
    pitch_points = parse_pitch_consensus(consensus_rows)
    if not pitch_points:
        raise RuntimeError("pitch consensus contains no selected-F0 observations")

    frame_rows = frame_voice_quality_series(
        y,
        sr,
        pitch_points,
        hop_s=hop_s,
        frame_length_ms=args.frame_length_ms,
        hnr_search_fraction=args.hnr_search_fraction,
        tilt_min_hz=args.tilt_min_hz,
        tilt_max_hz=args.tilt_max_hz,
        min_rms_dbfs=args.min_rms_dbfs,
        vibrato_window_s=args.vibrato_window_s,
        vibrato_min_confidence=args.vibrato_min_confidence,
    )

    args.out.mkdir(parents=True, exist_ok=True)
    frame_fields = [
        "time_s",
        "selected_f0_hz",
        "selected_confidence",
        "rms_dbfs",
        "autocorrelation_hnr_db",
        "spectral_tilt_db_per_octave",
        "local_vibrato_extent_cents_p95_p05",
        "local_vibrato_detrended_std_cents",
        "local_vibrato_rate_hz",
        "local_vibrato_median_confidence",
    ]
    _write_csv(args.out / "frame-metrics.csv", frame_rows, frame_fields)

    praat_path = shutil.which(args.praat_bin)
    praat_version_text = None
    praat_version = None
    praat_rows: list[dict[str, float | None]] = []
    praat_cpps_global = None
    required_praat = parse_version_triplet(args.praat_min_version)
    if praat_path:
        version_proc = subprocess.run(
            [praat_path, "--version"], check=True, capture_output=True, text=True
        )
        praat_version_text = (version_proc.stdout or version_proc.stderr).strip()
        praat_version = parse_praat_version(praat_version_text)
        if not version_at_least(praat_version, required_praat):
            raise RuntimeError(
                f"Praat {args.praat_min_version}+ required for calibrated CPPS; "
                f"found {praat_version_text}"
            )
        praat_script = args.praat_script.resolve()
        if not praat_script.is_file():
            raise FileNotFoundError(f"Praat time-series script not found: {praat_script}")
        with tempfile.TemporaryDirectory(prefix="tmp-music-vq-timeseries-") as td:
            raw_tsv = Path(td) / "praat-timeseries.tsv"
            proc = subprocess.run(
                [praat_path, "--run", str(praat_script), str(args.audio.resolve()), str(raw_tsv)],
                check=True,
                capture_output=True,
                text=True,
            )
            match = _CPP_MEAN_RE.search((proc.stdout or "") + "\n" + (proc.stderr or ""))
            praat_cpps_global = _float_or_none(match.group(1)) if match else None
            praat_rows = _read_praat_timeseries(raw_tsv, hop_s=hop_s)
    elif args.require_praat:
        raise RuntimeError("Praat executable not found but --require-praat was requested")

    praat_fields = ["time_s", "praat_cpps_db", "praat_hnr_cc_db"]
    _write_csv(args.out / "praat-timeseries.csv", praat_rows, praat_fields)

    summary = {
        "measurement_status": "ok" if frame_rows and (praat_rows or not args.require_praat) else "insufficient_data",
        "audio": str(args.audio),
        "pitch_consensus_csv": str(args.pitch_consensus),
        "sample_rate_hz": sr,
        "duration_s": len(y) / sr,
        "frame_series": {
            "hop_ms": args.hop_ms,
            "frame_length_ms": args.frame_length_ms,
            "row_count": len(frame_rows),
            "selected_f0_input_count": len(pitch_points),
            "autocorrelation_hnr_definition": "F0-guided 10*log10(r/(1-r)); not Praat Harmonicity.",
            "spectral_tilt_definition": "Local log-spectrum slope in dB/octave over retained 200-5000 Hz bins by default.",
        },
        "local_vibrato": {
            "window_s": args.vibrato_window_s,
            "minimum_selected_f0_confidence": args.vibrato_min_confidence,
            "extent_definition": "Local detrended selected-F0 p95 minus p05; exploratory vibrato-oriented descriptor, not an assertion of intentional vibrato.",
            "rate_definition": "Dominant detrended selected-F0 modulation frequency in the 3-9 Hz band when enough contiguous data are present.",
        },
        "praat_timeseries": {
            "enabled": bool(praat_path),
            "version": ".".join(map(str, praat_version)) if praat_version else None,
            "version_text": praat_version_text,
            "minimum_version_for_calibrated_cpps": args.praat_min_version,
            "row_count": len(praat_rows),
            "full_track_cpps_db": praat_cpps_global,
            "cpps_definition": "Per-frame CPP from the same calibrated PowerCepstrogram after 0.01 s time and 0.001 s quefrency smoothing used by the M6 CPPS configuration.",
            "hnr_definition": "Praat Sound: To Harmonicity (cc), 0.01 s step, 75 Hz pitch floor, 0.1 silence threshold, 1.0 period/window; sampled at PowerCepstrogram frame times.",
        },
    }
    (args.out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["measurement_status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
