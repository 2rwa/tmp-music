#!/usr/bin/env python3
"""Detect stable pitch targets from a consensus F0 trajectory."""
from __future__ import annotations

import argparse
import csv
import json
import sys
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

    times, f0, confidence = [], [], []
    with args.consensus_csv.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            times.append(parse_float(row["time_s"]))
            f0.append(parse_float(row.get("consensus_f0_hz", "")))
            pconf = parse_float(row.get("pyin_confidence", ""))
            cconf = parse_float(row.get("crepe_periodicity", ""))
            if pconf == pconf and cconf == cconf:
                confidence.append(min(pconf, cconf))
            elif pconf == pconf:
                confidence.append(pconf)
            elif cconf == cconf:
                confidence.append(cconf)
            else:
                confidence.append(float("nan"))

    segments = detect_stable_segments(
        times,
        f0,
        confidence,
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
        "median_abs_slope_cents_per_s", "median_detrended_std_cents",
    ]
    with (args.out / "stable-notes.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(segments)

    summary = {
        "stable_target_count": len(segments),
        "stable_duration_s": float(sum(float(x["duration_s"]) for x in segments)),
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
