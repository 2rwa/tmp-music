#!/usr/bin/env python3
"""Measure baseline voice quality on stable voiced intervals."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import librosa
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common.voice_quality import finite_summary, segment_voice_quality


def _f(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("audio", type=Path)
    p.add_argument("stable_notes_csv", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--sr", type=int, default=16000)
    p.add_argument("--frame-length-ms", type=float, default=60.0)
    p.add_argument("--hop-length-ms", type=float, default=20.0)
    p.add_argument("--hnr-search-fraction", type=float, default=0.15)
    p.add_argument("--tilt-min-hz", type=float, default=200.0)
    p.add_argument("--tilt-max-hz", type=float, default=5000.0)
    p.add_argument("--min-rms-dbfs", type=float, default=-70.0)
    args = p.parse_args()

    y, sr = librosa.load(args.audio.resolve(), sr=args.sr, mono=True)
    rows = []
    with args.stable_notes_csv.open(newline="", encoding="utf-8") as f:
        targets = list(csv.DictReader(f))

    for index, target in enumerate(targets, start=1):
        start_s, end_s = _f(target.get("start_s", "")), _f(target.get("end_s", ""))
        f0_hz = _f(target.get("median_f0_hz", ""))
        if not np.isfinite(start_s) or not np.isfinite(end_s) or end_s <= start_s:
            continue
        if not np.isfinite(f0_hz) or f0_hz <= 0:
            continue
        a = max(0, int(round(start_s * sr)))
        b = min(len(y), int(round(end_s * sr)))
        if b <= a:
            continue
        measurement = segment_voice_quality(
            y[a:b],
            sr,
            float(f0_hz),
            frame_length_ms=args.frame_length_ms,
            hop_length_ms=args.hop_length_ms,
            hnr_search_fraction=args.hnr_search_fraction,
            tilt_min_hz=args.tilt_min_hz,
            tilt_max_hz=args.tilt_max_hz,
            min_rms_dbfs=args.min_rms_dbfs,
        )
        if int(measurement["usable_frame_count"]) == 0:
            continue
        rows.append({
            "stable_target_index": index,
            "start_s": start_s,
            "end_s": end_s,
            "duration_s": end_s - start_s,
            "median_f0_hz": f0_hz,
            "frame_count": measurement["frame_count"],
            "usable_frame_count": measurement["usable_frame_count"],
            "median_rms_dbfs": measurement["rms_dbfs"]["median"],
            "median_autocorrelation_peak": measurement["autocorrelation_peak"]["median"],
            "median_autocorrelation_hnr_db": measurement["autocorrelation_hnr_db"]["median"],
            "median_spectral_tilt_db_per_octave": measurement["spectral_tilt_db_per_octave"]["median"],
        })

    args.out.mkdir(parents=True, exist_ok=True)
    fields = [
        "stable_target_index", "start_s", "end_s", "duration_s", "median_f0_hz",
        "frame_count", "usable_frame_count", "median_rms_dbfs",
        "median_autocorrelation_peak", "median_autocorrelation_hnr_db",
        "median_spectral_tilt_db_per_octave",
    ]
    with (args.out / "segments.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "measurement_status": "ok" if rows else "insufficient_stable_voiced_audio",
        "audio": str(args.audio),
        "stable_notes_csv": str(args.stable_notes_csv),
        "sample_rate_hz": sr,
        "stable_target_count_input": len(targets),
        "stable_target_count_measured": len(rows),
        "measured_duration_s": float(sum(float(row["duration_s"]) for row in rows)),
        "parameters": {
            "frame_length_ms": args.frame_length_ms,
            "hop_length_ms": args.hop_length_ms,
            "hnr_search_fraction": args.hnr_search_fraction,
            "tilt_min_hz": args.tilt_min_hz,
            "tilt_max_hz": args.tilt_max_hz,
            "min_rms_dbfs": args.min_rms_dbfs,
        },
        "metric_definitions": {
            "autocorrelation_hnr_db": (
                "F0-guided normalized-autocorrelation HNR estimate 10*log10(r/(1-r)); "
                "not Praat Harmonicity."
            ),
            "spectral_tilt_db_per_octave": (
                "Least-squares slope of retained log-magnitude spectrum bins versus log2 frequency."
            ),
            "rms_dbfs": "Frame RMS relative to full-scale amplitude 1.0.",
            "cpps": "not implemented in this baseline; do not infer CPPS from these metrics.",
        },
        "aggregate_segment_medians": {
            "rms_dbfs": finite_summary(row["median_rms_dbfs"] for row in rows),
            "autocorrelation_peak": finite_summary(row["median_autocorrelation_peak"] for row in rows),
            "autocorrelation_hnr_db": finite_summary(row["median_autocorrelation_hnr_db"] for row in rows),
            "spectral_tilt_db_per_octave": finite_summary(
                row["median_spectral_tilt_db_per_octave"] for row in rows
            ),
        },
    }
    (args.out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if rows else 2


if __name__ == "__main__":
    raise SystemExit(main())
