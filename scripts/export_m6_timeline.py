#!/usr/bin/env python3
"""Export an M6 Level-1 timeline snapshot from retained M2/M6 artifacts."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path


def number(value):
    if value in (None, ""):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def r(value, digits=3, default=None):
    value = number(value)
    if value is None:
        return default
    return round(value, digits)


def read_pitch(path: Path):
    points = []
    duration = 0.0
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            time_s = number(row["time_s"])
            if time_s is None:
                continue
            duration = max(duration, time_s)
            f0 = number(row["selected_f0_hz"])
            if f0 is None:
                continue
            confidence = number(row["selected_confidence"]) or 0.0
            points.append([round(time_s, 3), round(f0, 3), round(confidence, 4)])
    return points, round(duration, 3)


def read_segments(path: Path):
    rows = []
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            rows.append({
                "i": int(row["stable_target_index"]),
                "s": r(row["start_s"]),
                "e": r(row["end_s"]),
                "f0": r(row["median_f0_hz"]),
                "conf": r(row["m2_median_confidence"], 4, 0.0),
                "vib": r(row["vibrato_extent_cents_p95_p05"], 3, 0.0),
                "cpps": r(row["praat_cpps_db"]),
                "hnr_praat": r(row["praat_hnr_cc_db"]),
                "hnr_auto": r(row["median_autocorrelation_hnr_db"]),
                "tilt": r(row["median_spectral_tilt_db_per_octave"]),
                "f1": r(row["praat_f1_hz"], 2),
                "f2": r(row["praat_f2_hz"], 2),
                "f3": r(row["praat_f3_hz"], 2),
            })
    return rows


def read_movements(path: Path):
    rows = []
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            rows.append({
                "s": r(row["start_s"]),
                "e": r(row["end_s"]),
                "dir": row["direction"],
                "slope": r(row["slope_cents_per_s"], 2),
                "change": r(row["total_change_cents"], 2),
                "r2": r(row["linear_fit_r2"], 4),
                "conf": r(row["median_confidence"], 4),
            })
    return rows


def read_register(path: Path):
    payload = json.loads(path.read_text())
    rows = []
    for item in payload.get("candidates", []):
        rows.append({
            "t": r(item["time_s"]),
            "features": item.get("changed_features", []),
            "count": item.get("changed_feature_count", 0),
            "deltas": {
                key: round(float(value), 3)
                for key, value in item.get("deltas", {}).items()
                if isinstance(value, (int, float)) and math.isfinite(float(value))
            },
        })
    return rows


def export_track(args, track, label, pitch_dir, m6_dir, m6_artifact, pitch_artifact):
    f0, duration = read_pitch(pitch_dir / "consensus.csv")
    segments = read_segments(m6_dir / "segments.csv")
    movement = read_movements(m6_dir / "pitch-movement-events.csv")
    register = read_register(m6_dir / "register-transitions.json")
    summary = json.loads((m6_dir / "summary.json").read_text())
    payload = {
        "track": track,
        "label": label,
        "duration_s": duration,
        "source_commit": args.source_commit,
        "artifacts": {"m6": m6_artifact, "pitch": pitch_artifact},
        "summary": {
            "stable_targets": summary.get("stable_target_count_measured"),
            "measured_duration_s": summary.get("measured_duration_s"),
            "movement_candidates": summary.get("pitch_movement", {}).get("candidate_count"),
            "register_candidates": summary.get("register_transitions", {}).get("candidate_count"),
            "movement_confidence_floor": summary.get("pitch_movement", {}).get("minimum_median_selected_confidence"),
        },
        "f0": f0,
        "segments": segments,
        "movement": movement,
        "register": register,
    }
    target = args.output / f"{track}.json"
    target.write_text(json.dumps(payload, separators=(",", ":")) + "\n")
    print(
        f"{track}: {len(f0)} F0 points, {len(segments)} stable segments, "
        f"{len(movement)} movements, {len(register)} register candidates -> {target}"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path(".timeline-artifacts"))
    parser.add_argument("--output", type=Path, default=Path("docs/m6-status/timeline/data"))
    parser.add_argument(
        "--source-commit",
        default="4da2a606afc647b5997895b9e870ef48330af98c",
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    export_track(
        args,
        "whisper-ao",
        "Whisper AO",
        args.input / "whisper-pitch",
        args.input / "whisper-m6",
        11268226119,
        11267179670,
    )
    export_track(
        args,
        "jugemu",
        "Jugemu",
        args.input / "jugemu-pitch",
        args.input / "jugemu-m6",
        11268640196,
        11267723366,
    )
    holdout = args.input / "chichinu-holdout"
    export_track(
        args,
        "chichinu-fiija",
        "Chichinu Fiija",
        holdout / "measurements/pitch/vocals",
        holdout / "measurements/voice-quality/vocals",
        11267579268,
        11267579268,
    )


if __name__ == "__main__":
    main()
