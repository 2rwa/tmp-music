#!/usr/bin/env python3
"""Run Japanese ASR per detected cycle and measure character/mora variation."""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

from mutagen.id3 import ID3, USLT

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common.japanese import (
    edit_alignment,
    morae_from_kana,
    normalize_kana,
    partition_repeated_reference_lines,
)


def reference_text(path: Path) -> str:
    frames = [frame for frame in ID3(path).values() if isinstance(frame, USLT)]
    for frame in frames:
        if frame.lang == "eng":
            return frame.text.strip()
    return frames[0].text.strip() if frames else ""


def to_hiragana_reading(text: str) -> str:
    import pykakasi

    converter = pykakasi.kakasi()
    return normalize_kana("".join(str(chunk["hira"]) for chunk in converter.convert(text)))


def clip_audio(source: Path, start_s: float, end_s: float, out: Path) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-ss", str(start_s),
            "-i", str(source),
            "-t", str(end_s - start_s),
            "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
            str(out),
        ],
        check=True,
    )


def transcribe(model, path: Path, language: str) -> dict[str, object]:
    segments, info = model.transcribe(
        str(path),
        language=language,
        beam_size=5,
        vad_filter=True,
        word_timestamps=False,
    )
    rows = []
    text = []
    for seg in segments:
        part = seg.text.strip()
        if part:
            text.append(part)
        rows.append({
            "start": float(seg.start),
            "end": float(seg.end),
            "text": seg.text,
            "avg_logprob": getattr(seg, "avg_logprob", None),
            "no_speech_prob": getattr(seg, "no_speech_prob", None),
        })
    return {
        "text": " ".join(text),
        "detected_language": info.language,
        "language_probability": float(info.language_probability),
        "segments": rows,
    }


def write_alignment(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["op", "ref", "hyp"], delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def pairwise_mora_matrix(cycle_morae: list[list[str]]) -> list[list[float]]:
    n = len(cycle_morae)
    matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            metrics, _ = edit_alignment(cycle_morae[i], cycle_morae[j])
            errors = int(metrics["substitutions"]) + int(metrics["deletions"]) + int(metrics["insertions"])
            denom = max(len(cycle_morae[i]), len(cycle_morae[j]), 1)
            distance = errors / denom
            matrix[i][j] = matrix[j][i] = distance
    return matrix


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("audio", type=Path)
    p.add_argument("structure_json", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--model", default="small")
    p.add_argument("--language", default="ja")
    p.add_argument("--device", default="cpu")
    p.add_argument("--compute-type", default="int8")
    p.add_argument("--boundary-source", choices=("aligned_cycles", "cycles"), default="aligned_cycles")
    p.add_argument("--reference-cycle-lines", type=int, default=10)
    args = p.parse_args()

    source = args.audio.resolve()
    structure = json.loads(args.structure_json.read_text(encoding="utf-8"))
    cycles = list(structure.get(args.boundary_source) or [])
    if not cycles:
        raise RuntimeError(f"no cycles found in structure field {args.boundary_source!r}")

    reference_surface = reference_text(source)
    if not reference_surface:
        raise RuntimeError("embedded reference lyrics not found")
    reference_chunks = partition_repeated_reference_lines(
        reference_surface,
        len(cycles),
        canonical_line_count=args.reference_cycle_lines,
    )
    reference_chunk_readings = [to_hiragana_reading(chunk) for chunk in reference_chunks]
    reference_chunk_morae = [morae_from_kana(reading) for reading in reference_chunk_readings]
    full_reference_reading = to_hiragana_reading(reference_surface)
    full_reference_morae = morae_from_kana(full_reference_reading)

    from faster_whisper import WhisperModel

    model = WhisperModel(args.model, device=args.device, compute_type=args.compute_type)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "reference-surface.txt").write_text(reference_surface + "\n", encoding="utf-8")
    (args.out / "reference-reading.txt").write_text(full_reference_reading + "\n", encoding="utf-8")
    (args.out / "reference-morae.txt").write_text(" ".join(full_reference_morae) + "\n", encoding="utf-8")

    cycle_rows: list[dict[str, object]] = []
    cycle_morae: list[list[str]] = []
    with tempfile.TemporaryDirectory(prefix="tmp-music-cycle-asr-") as td:
        temp = Path(td)
        for index, cycle in enumerate(cycles, start=1):
            cycle_id = str(cycle.get("id") or f"cycle-{index:02d}")
            start_s = float(cycle["start_s"])
            end_s = float(cycle["end_s"])
            cycle_reference_surface = reference_chunks[index - 1]
            cycle_reference_reading = reference_chunk_readings[index - 1]
            cycle_reference_chars = list(cycle_reference_reading)
            cycle_reference_morae = reference_chunk_morae[index - 1]
            clip = temp / f"{cycle_id}.wav"
            clip_audio(source, start_s, end_s, clip)
            asr = transcribe(model, clip, args.language)
            surface = str(asr["text"])
            reading = to_hiragana_reading(surface)
            chars = list(reading)
            morae = morae_from_kana(reading)
            char_metrics, char_alignment = edit_alignment(cycle_reference_chars, chars)
            mora_metrics, mora_alignment = edit_alignment(cycle_reference_morae, morae)
            cycle_morae.append(morae)

            (args.out / f"{cycle_id}-reference.txt").write_text(
                cycle_reference_surface + "\n",
                encoding="utf-8",
            )
            detail = {
                "cycle_id": cycle_id,
                "start_s": start_s,
                "end_s": end_s,
                "duration_s": end_s - start_s,
                "reference_surface": cycle_reference_surface,
                "reference_reading": cycle_reference_reading,
                "reference_morae": cycle_reference_morae,
                "surface": surface,
                "reading": reading,
                "morae": morae,
                "detected_language": asr["detected_language"],
                "language_probability": asr["language_probability"],
                "segments": asr["segments"],
                "character": char_metrics,
                "mora": mora_metrics,
            }
            (args.out / f"{cycle_id}.json").write_text(
                json.dumps(detail, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            write_alignment(args.out / f"{cycle_id}-mora-alignment.tsv", mora_alignment)
            write_alignment(args.out / f"{cycle_id}-character-alignment.tsv", char_alignment)
            cycle_rows.append({
                "cycle_id": cycle_id,
                "start_s": start_s,
                "end_s": end_s,
                "duration_s": end_s - start_s,
                "language_probability": asr["language_probability"],
                "character_error_rate": char_metrics["error_rate"],
                "mora_error_rate": mora_metrics["error_rate"],
                "mora_substitutions": mora_metrics["substitutions"],
                "mora_deletions": mora_metrics["deletions"],
                "mora_insertions": mora_metrics["insertions"],
                "reference_lines": len(cycle_reference_surface.splitlines()),
                "reference_morae": len(cycle_reference_morae),
                "hypothesis_morae": len(morae),
                "text": surface,
            })

    with (args.out / "cycles.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(cycle_rows[0]))
        writer.writeheader()
        writer.writerows(cycle_rows)

    matrix = pairwise_mora_matrix(cycle_morae)
    with (args.out / "pairwise-mora-distance.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        labels = [str(row["cycle_id"]) for row in cycle_rows]
        writer.writerow(["cycle", *labels])
        for label, row in zip(labels, matrix):
            writer.writerow([label, *row])

    off_diagonal = [
        matrix[i][j]
        for i in range(len(matrix))
        for j in range(i + 1, len(matrix))
    ]
    summary = {
        "model": args.model,
        "language": args.language,
        "boundary_source": args.boundary_source,
        "cycle_count": len(cycle_rows),
        "reference_scope": "cycle-specific-contiguous-partition",
        "reference_total_character_count": len(list(full_reference_reading)),
        "reference_total_mora_count": len(full_reference_morae),
        "reference_cycle_line_counts": [len(chunk.splitlines()) for chunk in reference_chunks],
        "reference_cycle_mora_counts": [len(morae) for morae in reference_chunk_morae],
        "reference_partition": {
            "canonical_line_count": args.reference_cycle_lines,
            "max_line_deviation": 3,
            "method": "dynamic-programming line edit distance to first canonical cycle",
        },
        "cycles": cycle_rows,
        "pairwise_mora_distance": {
            "mean": statistics.mean(off_diagonal) if off_diagonal else None,
            "median": statistics.median(off_diagonal) if off_diagonal else None,
            "max": max(off_diagonal) if off_diagonal else None,
        },
        "interpretation_warning": (
            "Per-cycle CER/MER uses the corresponding contiguous reference-lyric chunk. "
            "Cycle-to-cycle transcript differences combine pronunciation variation, source-separation/"
            "acoustic differences, and ASR error. They are evidence for where to listen, not a direct "
            "measurement of pronunciation change."
        ),
    }
    (args.out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
