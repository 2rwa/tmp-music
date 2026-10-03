#!/usr/bin/env python3
"""Compare stable pitch targets against equal divisions of the octave."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common.pitch import fit_equal_divisions


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("stable_notes_csv", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--edos", default="12,19,24,31")
    args = p.parse_args()

    with args.stable_notes_csv.open(newline="", encoding="utf-8") as f:
        rows = [
            {
                "median_f0_hz": float(row["median_f0_hz"]),
                "duration_s": float(row["duration_s"]),
                "median_confidence": float(row["median_confidence"]),
            }
            for row in csv.DictReader(f)
            if row.get("median_f0_hz")
        ]

    edos = [int(x.strip()) for x in args.edos.split(",") if x.strip()]
    result = fit_equal_divisions(rows, edos)
    result["interpretation_warning"] = (
        "Equal-division residuals are measurements only. A lower residual does not by itself identify "
        "the intended scale, tuning system, culture, or compositional method."
    )
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "tuning-models.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
