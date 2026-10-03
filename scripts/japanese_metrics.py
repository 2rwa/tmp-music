#!/usr/bin/env python3
"""Compute Japanese character and mora metrics with explicit reading conversion."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from importlib.metadata import version
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common.japanese import edit_alignment, morae_from_kana, normalize_kana


def to_hiragana_reading(text: str) -> str:
    import pykakasi

    converter = pykakasi.kakasi()
    chunks = converter.convert(text)
    return "".join(str(chunk["hira"]) for chunk in chunks)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def write_alignment(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["op", "ref", "hyp"], delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--reference", type=Path, required=True)
    p.add_argument("--hypothesis", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()

    reference_surface = read_text(args.reference)
    hypothesis_surface = read_text(args.hypothesis)
    reference_reading_raw = to_hiragana_reading(reference_surface)
    hypothesis_reading_raw = to_hiragana_reading(hypothesis_surface)
    reference_kana = normalize_kana(reference_reading_raw)
    hypothesis_kana = normalize_kana(hypothesis_reading_raw)

    ref_chars = list(reference_kana)
    hyp_chars = list(hypothesis_kana)
    character_metrics, character_rows = edit_alignment(ref_chars, hyp_chars)
    reference_morae = morae_from_kana(reference_kana)
    hypothesis_morae = morae_from_kana(hypothesis_kana)
    mora_metrics, mora_rows = edit_alignment(reference_morae, hypothesis_morae)

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "reference-surface.txt").write_text(reference_surface + "\n", encoding="utf-8")
    (args.out / "hypothesis-surface.txt").write_text(hypothesis_surface + "\n", encoding="utf-8")
    (args.out / "reference-reading.txt").write_text(reference_kana + "\n", encoding="utf-8")
    (args.out / "hypothesis-reading.txt").write_text(hypothesis_kana + "\n", encoding="utf-8")
    (args.out / "reference-morae.txt").write_text(" ".join(reference_morae) + "\n", encoding="utf-8")
    (args.out / "hypothesis-morae.txt").write_text(" ".join(hypothesis_morae) + "\n", encoding="utf-8")
    write_alignment(args.out / "character-alignment.tsv", character_rows)
    write_alignment(args.out / "mora-alignment.tsv", mora_rows)

    result = {
        "character": character_metrics,
        "mora": mora_metrics,
        "normalization": {
            "unicode": "NFKC",
            "reading_converter": "pykakasi",
            "pykakasi_version": version("pykakasi"),
            "katakana_to_hiragana": True,
            "spaces_and_punctuation_removed": True,
        },
        "interpretation_warning": (
            "Kanji-to-reading conversion is an additional model/dictionary transformation. "
            "Reading-conversion errors must not be attributed to the ASR system."
        ),
    }
    (args.out / "metrics.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
