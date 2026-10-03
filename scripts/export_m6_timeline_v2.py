#!/usr/bin/env python3
"""Merge Level-1 M6 timeline snapshots with Level-2 time-series artifacts."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

TRACKS = {
    "whisper-ao": "Whisper AO",
    "jugemu": "Jugemu",
    "chichinu-fiija": "Chichinu Fiija",
}


def f(value):
    if value in (None, ""):
        return None
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--artifacts", type=Path, default=Path(".level2-artifacts"))
    p.add_argument("--level1", type=Path, default=Path("docs/m6-status/timeline/data"))
    p.add_argument("--out", type=Path, default=Path("docs/m6-status/timeline-v2/data"))
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    for track, label in TRACKS.items():
        base = json.loads((args.level1 / f"{track}.json").read_text())
        art = args.artifacts / track
        frames = read_csv(art / "frame-metrics.csv")
        praat = read_csv(art / "praat-timeseries.csv")
        summary = json.loads((art / "summary.json").read_text())
        payload = {
            "track": track,
            "label": label,
            "duration_s": base["duration_s"],
            "source_commit": base["source_commit"],
            "level1": {
                "f0": base["f0"],
                "segments": base["segments"],
                "movement": base["movement"],
                "register": base["register"],
            },
            "level2": {
                "summary": summary,
                "frame": [
                    [
                        f(row.get("time_s")),
                        f(row.get("selected_f0_hz")),
                        f(row.get("selected_confidence")),
                        f(row.get("rms_dbfs")),
                        f(row.get("autocorrelation_hnr_db")),
                        f(row.get("spectral_tilt_db_per_octave")),
                        f(row.get("local_vibrato_extent_cents_p95_p05")),
                        f(row.get("local_vibrato_detrended_std_cents")),
                        f(row.get("local_vibrato_rate_hz")),
                    ]
                    for row in frames
                ],
                "praat": [
                    [f(row.get("time_s")), f(row.get("praat_cpps_db")), f(row.get("praat_hnr_cc_db"))]
                    for row in praat
                ],
            },
        }
        target = args.out / f"{track}.json"
        target.write_text(json.dumps(payload, separators=(",", ":")) + "\n")
        print(f"{track}: frame={len(frames)} praat={len(praat)} -> {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
