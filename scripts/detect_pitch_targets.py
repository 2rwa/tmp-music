#!/usr/bin/env python3
"""Detect stable pitch targets from confidence-aware F0 selections."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common.pitch import detect_stable_segments


def parse_float(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("consensus_csv", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--window-s", type=float, default=0.5)
    p.add_argument("--max-slope", type=float, default=100.0)
    p.add_argument("--max-residual-std", type=float, default=40.0)
    p.add_argument("--min-duration", type=float, default=0.15)
    p.add_argument("--min-confidence", type=float, default=0.5)
    args = p.parse_args()

    times, f0, confidence, evidence = [], [], [], []
    with args.consensus_csv.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            times.append(parse_float(row["time_s"]))
            f0.append(parse_float(row.get("selected_f0_hz", "")))
            confidence.append(parse_float(row.get("selected_confidence", "")))
            evidence.append(row.get("selected_source", "none") or "none")

    segments = detect_stable_segments(
        times,
        f0,
        confidence,
        evidence=evidence,
        window_s=args.window_s,
        max_abs_slope_cents_per_s=args.max_slope,
        max_detrended_std_cents=args.max_residual_std,
        min_duration_s=args.min_duration,
        min_confidence=args.min_confidence,
    )
    args.out.mkdir(parents=True, exist_ok=True)
    fields = [
        "start_s", "end_s", "duration_s", "frames", "median_f0_hz", "median_midi",
        "cents_to_nearest_12tet", "vibrato_extent_cents_p95_p05", "median_confidence",
        "median_abs_slope_cents_per_s", "median_detrended_std_cents", "evidence",
        "consensus_fraction", "pyin_fallback_fraction", "crepe_only_fraction",
    ]
    with (args.out / "stable-notes.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(segments)

    input_source_counts = Counter(evidence)
    segment_evidence_counts = Counter(str(x["evidence"]) for x in segments)
    summary = {
        "measurement_status": "ok" if segments else "insufficient_stable_targets",
        "stable_target_count": len(segments),
        "stable_duration_s": float(sum(float(x["duration_s"]) for x in segments)),
        "input_selected_source_counts": dict(sorted(input_source_counts.items())),
        "stable_segment_evidence_counts": dict(sorted(segment_evidence_counts.items())),
        "parameters": {
            "window_s": args.window_s,
            "max_slope_cents_per_s": args.max_slope,
            "max_detrended_std_cents": args.max_residual_std,
            "min_duration_s": args.min_duration,
            "min_confidence": args.min_confidence,
        },
    }
    (args.out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
