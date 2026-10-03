#!/usr/bin/env python3
"""Measure baseline voice quality on stable voiced intervals."""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common.voice_quality import (
    detect_pitch_movement_events,
    detect_register_transition_candidates,
    finite_summary,
    parse_praat_voice_measurements,
    parse_praat_version,
    parse_version_triplet,
    segment_voice_quality,
    version_at_least,
)


def _f(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def _finite_or_none(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("audio", type=Path)
    p.add_argument("stable_notes_csv", type=Path)
    p.add_argument("--pitch-consensus", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--sr", type=int, default=16000)
    p.add_argument("--frame-length-ms", type=float, default=60.0)
    p.add_argument("--hop-length-ms", type=float, default=20.0)
    p.add_argument("--hnr-search-fraction", type=float, default=0.15)
    p.add_argument("--tilt-min-hz", type=float, default=200.0)
    p.add_argument("--tilt-max-hz", type=float, default=5000.0)
    p.add_argument("--min-rms-dbfs", type=float, default=-70.0)
    p.add_argument("--praat-bin", default="praat")
    p.add_argument("--praat-script", type=Path, default=SCRIPT_DIR / "praat" / "measure_cpps_hnr.praat")
    p.add_argument("--praat-min-version", default="6.4.39")
    p.add_argument("--require-praat", action="store_true")
    args = p.parse_args()

    y, sr = librosa.load(args.audio.resolve(), sr=args.sr, mono=True)

    praat_path = shutil.which(args.praat_bin)
    praat_version_text = None
    praat_version = None
    required_praat = parse_version_triplet(args.praat_min_version)
    if praat_path:
        version_proc = subprocess.run(
            [praat_path, "--version"],
            check=True,
            capture_output=True,
            text=True,
        )
        praat_version_text = (version_proc.stdout or version_proc.stderr).strip()
        praat_version = parse_praat_version(praat_version_text)
        if not version_at_least(praat_version, required_praat):
            raise RuntimeError(
                f"Praat {args.praat_min_version}+ required for calibrated CPPS; "
                f"found {praat_version_text}"
            )
    elif args.require_praat:
        raise RuntimeError("Praat executable not found but --require-praat was requested")

    praat_script = args.praat_script.resolve()
    if praat_path and not praat_script.is_file():
        raise FileNotFoundError(f"Praat measurement script not found: {praat_script}")

    rows = []
    with args.stable_notes_csv.open(newline="", encoding="utf-8") as f:
        targets = list(csv.DictReader(f))

    with tempfile.TemporaryDirectory(prefix="tmp-music-voice-quality-") as td:
        praat_temp = Path(td)
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
            segment = y[a:b]
            measurement = segment_voice_quality(
                segment,
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

            praat_metrics = {
                "praat_cpps_db": None,
                "praat_hnr_cc_db": None,
                "praat_f1_hz": None,
                "praat_f2_hz": None,
                "praat_f3_hz": None,
            }
            if praat_path:
                wav_path = praat_temp / f"segment-{index:04d}.wav"
                sf.write(wav_path, segment, sr, subtype="PCM_16")
                proc = subprocess.run(
                    [praat_path, "--run", str(praat_script), str(wav_path)],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                praat_metrics = parse_praat_voice_measurements(
                    (proc.stdout or "") + ("\n" if proc.stdout and proc.stderr else "") + (proc.stderr or "")
                )

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
                "vibrato_extent_cents_p95_p05": _finite_or_none(
                    target.get("vibrato_extent_cents_p95_p05")
                ),
                "m2_median_abs_slope_cents_per_s": _finite_or_none(
                    target.get("median_abs_slope_cents_per_s")
                ),
                "m2_median_detrended_std_cents": _finite_or_none(
                    target.get("median_detrended_std_cents")
                ),
                "m2_median_confidence": _finite_or_none(target.get("median_confidence")),
                "m2_evidence": target.get("evidence") or None,
                **praat_metrics,
            })

    args.out.mkdir(parents=True, exist_ok=True)
    fields = [
        "stable_target_index", "start_s", "end_s", "duration_s", "median_f0_hz",
        "frame_count", "usable_frame_count", "median_rms_dbfs",
        "median_autocorrelation_peak", "median_autocorrelation_hnr_db",
        "median_spectral_tilt_db_per_octave",
        "vibrato_extent_cents_p95_p05", "m2_median_abs_slope_cents_per_s",
        "m2_median_detrended_std_cents", "m2_median_confidence", "m2_evidence",
        "praat_cpps_db", "praat_hnr_cc_db", "praat_f1_hz", "praat_f2_hz", "praat_f3_hz",
    ]
    with (args.out / "segments.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    pitch_movement_events: list[dict[str, object]] = []
    pitch_movement_status = "not_requested"
    if args.pitch_consensus is not None:
        if not args.pitch_consensus.is_file():
            raise FileNotFoundError(f"pitch consensus not found: {args.pitch_consensus}")
        with args.pitch_consensus.open(newline="", encoding="utf-8") as f:
            consensus_rows = list(csv.DictReader(f))
        pitch_movement_events = detect_pitch_movement_events(consensus_rows)
        pitch_movement_status = "ok"
    movement_fields = [
        "start_s", "end_s", "duration_s", "direction", "slope_cents_per_s",
        "total_change_cents", "linear_fit_r2", "median_confidence", "interpretation",
    ]
    with (args.out / "pitch-movement-events.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=movement_fields)
        writer.writeheader()
        writer.writerows(pitch_movement_events)

    register_candidates = detect_register_transition_candidates(rows)
    register_payload = {
        "measurement_status": "ok",
        "candidate_count": len(register_candidates),
        "definition": (
            "Candidate boundaries require changes in at least two features and never use "
            "F0 alone as sufficient evidence of a register transition."
        ),
        "candidates": register_candidates,
    }
    (args.out / "register-transitions.json").write_text(
        json.dumps(register_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    summary = {
        "measurement_status": "ok" if rows else "insufficient_stable_voiced_audio",
        "audio": str(args.audio),
        "stable_notes_csv": str(args.stable_notes_csv),
        "pitch_consensus_csv": str(args.pitch_consensus) if args.pitch_consensus else None,
        "sample_rate_hz": sr,
        "praat": {
            "enabled": bool(praat_path),
            "path": praat_path,
            "version": ".".join(map(str, praat_version)) if praat_version else None,
            "version_text": praat_version_text,
            "minimum_version_for_calibrated_cpps": args.praat_min_version,
            "script": str(praat_script) if praat_path else None,
        },
        "stable_target_count_input": len(targets),
        "stable_target_count_measured": len(rows),
        "measured_duration_s": float(sum(float(row["duration_s"]) for row in rows)),
        "pitch_movement": {
            "measurement_status": pitch_movement_status,
            "candidate_count": len(pitch_movement_events),
            "definition": "Sustained monotonic M2 F0 movement candidates; not asserted sung glissandi.",
        },
        "register_transitions": {
            "measurement_status": "ok",
            "candidate_count": len(register_candidates),
            "definition": register_payload["definition"],
        },
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
            "praat_cpps_db": (
                "Calibrated Praat PowerCepstrogram Get CPPS: 60 Hz pitch floor, "
                "0.002 s time step, 5000 Hz maximum frequency, 50 Hz pre-emphasis; "
                "Get CPPS uses no trend subtraction, 0.01 s time smoothing, "
                "0.001 s quefrency smoothing, 60-330 Hz search, tolerance 0.05, "
                "parabolic interpolation, 0.001-0.0 s Straight/Robust trend fit. "
                "Praat >=6.4.39 is required."
            ),
            "praat_hnr_cc_db": (
                "Praat Sound: To Harmonicity (cc), 0.01 s step, 75 Hz pitch floor, "
                "0.1 silence threshold, 1.0 period/window; whole-segment mean."
            ),
            "praat_f1_hz/praat_f2_hz/praat_f3_hz": (
                "Praat Burg formants measured per stable vocal segment with 5 formants, "
                "5500 Hz ceiling, 0.025 s window and 50 Hz pre-emphasis. Source separation "
                "and singing acoustics can bias these estimates."
            ),
            "vibrato_extent_cents_p95_p05": (
                "Copied from the M2 stable-target detector: detrended F0 95th minus 5th percentile."
            ),
            "pitch_movement_events": (
                "M2 selected-F0 windows with sustained approximately linear pitch motion; "
                "reported only as glissando candidates."
            ),
            "register_transitions": (
                "Candidate boundaries requiring at least two thresholded feature changes; "
                "F0 alone is explicitly insufficient."
            ),
        },
        "aggregate_segment_medians": {
            "rms_dbfs": finite_summary(row["median_rms_dbfs"] for row in rows),
            "autocorrelation_peak": finite_summary(row["median_autocorrelation_peak"] for row in rows),
            "autocorrelation_hnr_db": finite_summary(row["median_autocorrelation_hnr_db"] for row in rows),
            "spectral_tilt_db_per_octave": finite_summary(
                row["median_spectral_tilt_db_per_octave"] for row in rows
            ),
            "praat_cpps_db": finite_summary(row["praat_cpps_db"] for row in rows),
            "praat_hnr_cc_db": finite_summary(row["praat_hnr_cc_db"] for row in rows),
            "praat_f1_hz": finite_summary(row["praat_f1_hz"] for row in rows),
            "praat_f2_hz": finite_summary(row["praat_f2_hz"] for row in rows),
            "praat_f3_hz": finite_summary(row["praat_f3_hz"] for row in rows),
            "vibrato_extent_cents_p95_p05": finite_summary(
                row["vibrato_extent_cents_p95_p05"] for row in rows
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
