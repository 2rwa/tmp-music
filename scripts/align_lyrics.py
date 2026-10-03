#!/usr/bin/env python3
"""Known-lyrics forced alignment using Montreal Forced Aligner.

MFA is invoked as an external tool so alignment preparation/parsing remains
deterministic and cheap-testable without importing Kaldi/MFA. Partial alignment
failures are retained in failed-spans.json.
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common.japanese import morae_from_kana, partition_repeated_reference_lines, to_hiragana_reading


def reference_text(path: Path) -> str:
    from mutagen.id3 import ID3, USLT
    frames = [frame for frame in ID3(path).values() if isinstance(frame, USLT)]
    for frame in frames:
        if frame.lang == "eng":
            return frame.text.strip()
    return frames[0].text.strip() if frames else ""


def clip_audio(source: Path, start_s: float | None, end_s: float | None, out: Path) -> None:
    cmd = ["ffmpeg", "-y", "-v", "error"]
    if start_s is not None:
        cmd += ["-ss", str(start_s)]
    cmd += ["-i", str(source)]
    if end_s is not None:
        cmd += ["-t", str(end_s - start_s)] if start_s is not None else ["-to", str(end_s)]
    cmd += ["-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(out)]
    subprocess.run(cmd, check=True)


def prepare_segments(source: Path, reference_surface: str, corpus_dir: Path, *,
                     structure: dict[str, Any] | None, boundary_source: str,
                     reference_cycle_lines: int) -> list[dict[str, Any]]:
    corpus_dir.mkdir(parents=True, exist_ok=True)
    if structure is None:
        clip_audio(source, None, None, corpus_dir / "full-track.wav")
        (corpus_dir / "full-track.lab").write_text(reference_surface.strip() + "\n", encoding="utf-8")
        return [{"id": "full-track", "start_s": 0.0, "end_s": None,
                 "reference": reference_surface.strip(), "reference_lines": len(reference_surface.splitlines())}]

    cycles = list(structure.get(boundary_source) or [])
    if not cycles:
        raise RuntimeError(f"no cycles found in structure field {boundary_source!r}")
    chunks = partition_repeated_reference_lines(reference_surface, len(cycles),
                                                canonical_line_count=reference_cycle_lines)
    segments = []
    for index, (cycle, text) in enumerate(zip(cycles, chunks), start=1):
        segment_id = str(cycle.get("id") or f"cycle-{index:02d}")
        start_s, end_s = float(cycle["start_s"]), float(cycle["end_s"])
        clip_audio(source, start_s, end_s, corpus_dir / f"{segment_id}.wav")
        (corpus_dir / f"{segment_id}.lab").write_text(text.strip() + "\n", encoding="utf-8")
        segments.append({"id": segment_id, "start_s": start_s, "end_s": end_s,
                         "reference": text.strip(), "reference_lines": len(text.splitlines())})
    return segments


def _tier_entries(payload: dict[str, Any], kind: str) -> list[list[Any]]:
    tiers = payload.get("tiers", {})
    if not isinstance(tiers, dict):
        return []
    for name, tier in tiers.items():
        if kind.lower() in str(name).lower() and isinstance(tier, dict):
            entries = tier.get("entries", [])
            if isinstance(entries, list):
                return [x for x in entries if isinstance(x, list) and len(x) >= 3]
    return []


def project_morae_from_words(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for word in words:
        label = str(word["label"])
        morae = morae_from_kana(to_hiragana_reading(label))
        if not morae:
            continue
        start_s, end_s = float(word["start_s"]), float(word["end_s"])
        step = (end_s - start_s) / len(morae)
        for index, mora in enumerate(morae):
            out.append({"segment_id": word["segment_id"],
                        "start_s": start_s + step * index, "end_s": start_s + step * (index + 1),
                        "label": mora, "source_word": label,
                        "timing_method": "within-word-equal-projection-from-mfa-word"})
    return out


def parse_alignment(aligned_dir: Path, segments: list[dict[str, Any]], *,
                    language: str) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    outputs = {"words": [], "phones": [], "morae": []}
    failed = []
    by_stem = {p.stem: p for p in aligned_dir.rglob("*.json")}
    for segment in segments:
        segment_id = str(segment["id"])
        path = by_stem.get(segment_id)
        if path is None:
            failed.append({"segment_id": segment_id, "start_s": segment["start_s"],
                           "end_s": segment["end_s"], "reason": "mfa-output-missing"})
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        offset = float(segment["start_s"])
        words, phones = _tier_entries(payload, "word"), _tier_entries(payload, "phone")
        if not words:
            failed.append({"segment_id": segment_id, "start_s": segment["start_s"],
                           "end_s": segment["end_s"], "reason": "no-word-alignment"})
        if not phones:
            failed.append({"segment_id": segment_id, "start_s": segment["start_s"],
                           "end_s": segment["end_s"], "reason": "no-phone-alignment"})
        for begin, end, label, *_ in words:
            if str(label).strip():
                outputs["words"].append({"segment_id": segment_id, "start_s": offset + float(begin),
                                         "end_s": offset + float(end), "label": str(label),
                                         "timing_method": "mfa-word"})
        for begin, end, label, *_ in phones:
            if str(label).strip():
                outputs["phones"].append({"segment_id": segment_id, "start_s": offset + float(begin),
                                          "end_s": offset + float(end), "label": str(label),
                                          "timing_method": "mfa-phone"})
    if language == "ja":
        outputs["morae"] = project_morae_from_words(outputs["words"])
    return outputs, failed


def write_tsv(path: Path, units: dict[str, list[dict[str, Any]]]) -> None:
    fields = ["level", "segment_id", "unit_index", "start_s", "end_s", "label", "timing_method", "source_word"]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        for level in ("words", "phones", "morae"):
            for index, row in enumerate(units[level], start=1):
                writer.writerow({"level": level[:-1] if level.endswith("s") else level,
                                 "segment_id": row["segment_id"], "unit_index": index,
                                 "start_s": row["start_s"], "end_s": row["end_s"],
                                 "label": row["label"], "timing_method": row["timing_method"],
                                 "source_word": row.get("source_word", "")})


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("audio", type=Path); p.add_argument("--out", type=Path, required=True)
    p.add_argument("--language", required=True); p.add_argument("--dictionary", required=True)
    p.add_argument("--acoustic-model", required=True); p.add_argument("--g2p-model")
    p.add_argument("--structure-json", type=Path); p.add_argument("--boundary-source", default="aligned_cycles")
    p.add_argument("--reference-cycle-lines", type=int, default=10)
    args = p.parse_args()
    source = args.audio.resolve()
    reference_surface = reference_text(source)
    if not reference_surface:
        raise RuntimeError("embedded reference lyrics not found")
    structure = json.loads(args.structure_json.read_text(encoding="utf-8")) if args.structure_json else None
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "reference-surface.txt").write_text(reference_surface + "\n", encoding="utf-8")

    with tempfile.TemporaryDirectory(prefix="tmp-music-mfa-") as td:
        temp = Path(td); corpus, aligned = temp / "corpus", temp / "aligned"
        segments = prepare_segments(source, reference_surface, corpus, structure=structure,
                                    boundary_source=args.boundary_source,
                                    reference_cycle_lines=args.reference_cycle_lines)
        (args.out / "prepared-segments.json").write_text(json.dumps(segments, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        cmd = ["mfa", "align", str(corpus), args.dictionary, args.acoustic_model, str(aligned),
               "--output_format", "json", "--include_original_text"]
        if args.g2p_model:
            cmd += ["--g2p_model_path", args.g2p_model]
        proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
        (args.out / "mfa.log").write_text((proc.stdout or "") + ("\n" if proc.stdout and proc.stderr else "") + (proc.stderr or ""), encoding="utf-8")
        if proc.returncode != 0:
            failed = [{"segment_id": x["id"], "start_s": x["start_s"], "end_s": x["end_s"],
                       "reason": "mfa-command-failed", "return_code": proc.returncode} for x in segments]
            (args.out / "failed-spans.json").write_text(json.dumps(failed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            raise RuntimeError(f"MFA exited with code {proc.returncode}; see {args.out / 'mfa.log'}")

        units, failed = parse_alignment(aligned, segments, language=args.language)
        (args.out / "failed-spans.json").write_text(json.dumps(failed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_tsv(args.out / "alignment.tsv", units)
        failed_segments = {x["segment_id"] for x in failed}
        result = {"backend": "montreal-forced-aligner", "language": args.language,
                  "dictionary": args.dictionary, "acoustic_model": args.acoustic_model,
                  "g2p_model": args.g2p_model, "segment_count": len(segments),
                  "aligned_segment_count": len(segments) - len(failed_segments),
                  "failed_span_count": len(failed),
                  "unit_counts": {k: len(v) for k, v in units.items()},
                  "mora_timing_note": ("Japanese mora timestamps are projections within MFA-aligned word intervals; "
                                       "MFA phone timestamps remain the acoustic boundary measurement."
                                       if args.language == "ja" else None),
                  "units": units}
        (args.out / "alignment.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({k: v for k, v in result.items() if k != "units"}, ensure_ascii=False, indent=2))
        if not units["words"] or not units["phones"]:
            raise RuntimeError("MFA returned no usable word/phone alignment")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
