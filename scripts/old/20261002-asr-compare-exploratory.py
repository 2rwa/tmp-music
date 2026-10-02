#!/usr/bin/env python3
"""Transcribe a music sample with faster-whisper and compare with embedded lyrics.

ARCHIVE NOTE: first larger exploratory implementation used during the 2026-10-02
investigation, before the compact supported script was finalized.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from mutagen.id3 import ID3, USLT


def extract_reference(path: Path, language: str = "eng") -> str:
    tags = ID3(path)
    candidates: list[USLT] = [f for f in tags.values() if isinstance(f, USLT)]
    for frame in candidates:
        if frame.lang == language:
            return frame.text.strip()
    return candidates[0].text.strip() if candidates else ""


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:'[a-z0-9]+)?", text.lower().replace("’", "'"))


def chars(text: str) -> list[str]:
    return list("".join(words(text)))


def edit_stats(ref: list[str], hyp: list[str]) -> dict[str, Any]:
    n, m = len(ref), len(hyp)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    op = [[""] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        dp[i][0] = i
        op[i][0] = "D"
    for j in range(1, m + 1):
        dp[0][j] = j
        op[0][j] = "I"
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if ref[i - 1] == hyp[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
                op[i][j] = "="
                continue
            choices = [
                (dp[i - 1][j - 1] + 1, "S"),
                (dp[i - 1][j] + 1, "D"),
                (dp[i][j - 1] + 1, "I"),
            ]
            dp[i][j], op[i][j] = min(choices, key=lambda x: x[0])

    i, j = n, m
    counts = {"substitutions": 0, "deletions": 0, "insertions": 0, "correct": 0}
    alignment: list[dict[str, str]] = []
    while i > 0 or j > 0:
        code = op[i][j]
        if code == "=":
            counts["correct"] += 1
            alignment.append({"op": "=", "ref": ref[i - 1], "hyp": hyp[j - 1]})
            i -= 1; j -= 1
        elif code == "S":
            counts["substitutions"] += 1
            alignment.append({"op": "S", "ref": ref[i - 1], "hyp": hyp[j - 1]})
            i -= 1; j -= 1
        elif code == "D":
            counts["deletions"] += 1
            alignment.append({"op": "D", "ref": ref[i - 1], "hyp": ""})
            i -= 1
        elif code == "I":
            counts["insertions"] += 1
            alignment.append({"op": "I", "ref": "", "hyp": hyp[j - 1]})
            j -= 1
        else:
            break
    alignment.reverse()
    errors = counts["substitutions"] + counts["deletions"] + counts["insertions"]
    counts["reference_units"] = n
    counts["hypothesis_units"] = m
    counts["error_rate"] = (errors / n) if n else None
    counts["alignment"] = alignment
    return counts


def clip_audio(source: Path, start: float | None, end: float | None, workdir: Path) -> Path:
    if start is None and end is None:
        return source
    out = workdir / "clip.wav"
    cmd = ["ffmpeg", "-y", "-v", "error"]
    if start is not None:
        cmd += ["-ss", str(start)]
    cmd += ["-i", str(source)]
    if end is not None:
        if start is not None:
            cmd += ["-t", str(max(0.0, end - start))]
        else:
            cmd += ["-to", str(end)]
    cmd += ["-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(out)]
    subprocess.run(cmd, check=True)
    return out


def run_transcription(audio: Path, model_name: str, language: str | None, device: str, compute_type: str) -> dict[str, Any]:
    from faster_whisper import WhisperModel

    model = WhisperModel(model_name, device=device, compute_type=compute_type)
    segments, info = model.transcribe(
        str(audio),
        language=language,
        beam_size=5,
        vad_filter=True,
        word_timestamps=True,
    )
    rows = []
    text_parts = []
    for seg in segments:
        text_parts.append(seg.text.strip())
        rows.append({
            "start": seg.start,
            "end": seg.end,
            "text": seg.text,
            "avg_logprob": getattr(seg, "avg_logprob", None),
            "no_speech_prob": getattr(seg, "no_speech_prob", None),
            "words": [
                {"start": w.start, "end": w.end, "word": w.word, "probability": w.probability}
                for w in (seg.words or [])
            ],
        })
    return {
        "detected_language": info.language,
        "language_probability": info.language_probability,
        "duration": info.duration,
        "duration_after_vad": getattr(info, "duration_after_vad", None),
        "text": " ".join(x for x in text_parts if x),
        "segments": rows,
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("audio", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--model", default="small")
    p.add_argument("--modes", default="auto,en", help="comma-separated: auto,en")
    p.add_argument("--device", default="cpu")
    p.add_argument("--compute-type", default="int8")
    p.add_argument("--start", type=float)
    p.add_argument("--end", type=float)
    args = p.parse_args()

    source = args.audio.resolve()
    outdir = args.out.resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    reference = extract_reference(source)
    (outdir / "reference.txt").write_text(reference.rstrip() + "\n", encoding="utf-8")

    all_metrics: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="tmp-music-asr-") as td:
        clip = clip_audio(source, args.start, args.end, Path(td))
        for mode in [x.strip() for x in args.modes.split(",") if x.strip()]:
            language = None if mode == "auto" else mode
            result = run_transcription(clip, args.model, language, args.device, args.compute_type)
            stem = mode.replace("/", "-")
            (outdir / f"{stem}.txt").write_text(result["text"].rstrip() + "\n", encoding="utf-8")
            (outdir / f"{stem}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            word_stats = edit_stats(words(reference), words(result["text"]))
            char_stats = edit_stats(chars(reference), chars(result["text"]))
            alignment = word_stats.pop("alignment")
            char_stats.pop("alignment")
            with (outdir / f"{stem}-alignment.tsv").open("w", encoding="utf-8") as f:
                f.write("op\tref\thyp\n")
                for row in alignment:
                    f.write(f"{row['op']}\t{row['ref']}\t{row['hyp']}\n")
            all_metrics[mode] = {"word": word_stats, "character": char_stats}

    (outdir / "metrics.json").write_text(json.dumps(all_metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(all_metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
