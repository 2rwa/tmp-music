#!/usr/bin/env python3
"""Reproducible acoustic analysis for tmp-music samples.

Outputs machine-readable measurements plus diagnostic plots. This script does
not attempt to assign an ethnicity, country, or folk tradition to a recording.

ARCHIVE NOTE: this is the first larger exploratory implementation used during
the 2026-10-02 investigation, before the compact supported script was finalized.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import subprocess
from pathlib import Path
from typing import Any

import librosa
import librosa.display
import matplotlib.pyplot as plt
import numpy as np
from mutagen.id3 import ID3, COMM, TIT2, TPE1, USLT, WOAS
from scipy.signal import find_peaks


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def ffprobe(path: Path) -> dict[str, Any]:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration,size,bit_rate:format_tags",
        "-of", "json", str(path),
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def extract_id3(path: Path) -> dict[str, Any]:
    tags = ID3(path)
    out: dict[str, Any] = {}
    for frame in tags.values():
        if isinstance(frame, TIT2):
            out["title"] = str(frame)
        elif isinstance(frame, TPE1):
            out["artist"] = str(frame)
        elif isinstance(frame, COMM):
            out.setdefault("comments", []).append(str(frame))
        elif isinstance(frame, WOAS):
            out.setdefault("source_urls", []).append(str(frame))
        elif isinstance(frame, USLT):
            key = f"lyrics-{frame.lang or 'und'}"
            out[key] = frame.text
    return out


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def active_end_from_energy(y: np.ndarray, sr: int, top_db: float = 50.0) -> float:
    intervals = librosa.effects.split(y, top_db=top_db)
    if len(intervals) == 0:
        return 0.0
    return float(intervals[-1, 1] / sr)


def band_energy(power: np.ndarray, freqs: np.ndarray, lo: float | None, hi: float | None) -> float:
    mask = np.ones_like(freqs, dtype=bool)
    if lo is not None:
        mask &= freqs >= lo
    if hi is not None:
        mask &= freqs < hi
    total = float(np.sum(power))
    if total <= 0:
        return 0.0
    return float(np.sum(power[mask]) / total)


def frame_band_ratio(power: np.ndarray, freqs: np.ndarray, hi: float) -> np.ndarray:
    total = np.sum(power, axis=0) + 1e-20
    low = np.sum(power[freqs < hi, :], axis=0)
    return low / total


def smooth(x: np.ndarray, width: int) -> np.ndarray:
    if width <= 1:
        return x.copy()
    kernel = np.ones(width, dtype=float) / width
    return np.convolve(x, kernel, mode="same")


def detect_boundaries(
    times: np.ndarray,
    feature_rows: list[np.ndarray],
    active_end: float,
    sr: int,
    hop_length: int,
) -> tuple[list[dict[str, float]], np.ndarray]:
    n = min(len(row) for row in feature_rows)
    x = np.vstack([row[:n] for row in feature_rows]).astype(float)
    med = np.nanmedian(x, axis=1, keepdims=True)
    mad = np.nanmedian(np.abs(x - med), axis=1, keepdims=True) + 1e-9
    z = (x - med) / mad

    smooth_frames = max(1, round(1.0 * sr / hop_length))
    z_smooth = np.vstack([smooth(row, smooth_frames) for row in z])
    lag = max(1, round(1.5 * sr / hop_length))
    novelty = np.zeros(n, dtype=float)
    if n > lag:
        delta = z_smooth[:, lag:] - z_smooth[:, :-lag]
        novelty[lag:] = np.sqrt(np.sum(delta * delta, axis=0))
    novelty = smooth(novelty, max(1, round(0.5 * sr / hop_length)))

    min_distance = max(1, round(8.0 * sr / hop_length))
    threshold = float(np.percentile(novelty, 75)) if np.any(novelty) else 0.0
    peaks, _ = find_peaks(novelty, distance=min_distance, prominence=max(0.1, threshold * 0.15))

    candidates: list[dict[str, float]] = []
    for p in peaks:
        t = float(times[min(p, len(times) - 1)])
        if 3.0 <= t <= max(3.0, active_end - 3.0):
            candidates.append({"time_s": t, "novelty": float(novelty[p])})
    candidates.sort(key=lambda item: item["novelty"], reverse=True)
    return candidates[:8], novelty


def section_summary(
    y: np.ndarray,
    sr: int,
    start: float,
    end: float,
    n_fft: int,
    hop_length: int,
) -> dict[str, float]:
    a = max(0, int(start * sr))
    b = min(len(y), int(end * sr))
    ys = y[a:b]
    if len(ys) < n_fft:
        return {"start_s": start, "end_s": end, "duration_s": max(0.0, end - start)}

    stft = librosa.stft(ys, n_fft=n_fft, hop_length=hop_length, window="hann")
    mag = np.abs(stft)
    power = mag * mag
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
    centroid = librosa.feature.spectral_centroid(S=mag, sr=sr)[0]
    flatness = librosa.feature.spectral_flatness(S=mag)[0]
    onset = librosa.onset.onset_strength(y=ys, sr=sr, hop_length=hop_length)
    onset_frames = librosa.onset.onset_detect(onset_envelope=onset, sr=sr, hop_length=hop_length)
    duration = len(ys) / sr

    return {
        "start_s": float(start),
        "end_s": float(end),
        "duration_s": float(duration),
        "spectral_centroid_hz_mean": float(np.nanmean(centroid)),
        "spectral_flatness_mean": float(np.nanmean(flatness)),
        "onset_density_per_s": float(len(onset_frames) / duration) if duration else 0.0,
        "energy_lt_300_ratio": band_energy(power, freqs, None, 300.0),
        "energy_300_1000_ratio": band_energy(power, freqs, 300.0, 1000.0),
        "energy_1000_4000_ratio": band_energy(power, freqs, 1000.0, 4000.0),
        "energy_ge_4000_ratio": band_energy(power, freqs, 4000.0, None),
    }


def analyze_pitch(y: np.ndarray, sr: int, active_end: float, outdir: Path) -> dict[str, Any]:
    hop = 512
    ya = y[: int(active_end * sr)]
    f0, voiced_flag, voiced_prob = librosa.pyin(
        ya,
        fmin=librosa.note_to_hz("C2"),
        fmax=librosa.note_to_hz("C7"),
        sr=sr,
        frame_length=2048,
        hop_length=hop,
    )
    times = librosa.times_like(f0, sr=sr, hop_length=hop)
    valid = np.isfinite(f0)
    midi = np.full_like(f0, np.nan, dtype=float)
    cents_to_nearest = np.full_like(f0, np.nan, dtype=float)
    if np.any(valid):
        midi[valid] = librosa.hz_to_midi(f0[valid])
        cents_to_nearest[valid] = 100.0 * (midi[valid] - np.round(midi[valid]))

    csv_path = outdir / "pitch-f0.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["time_s", "f0_hz", "midi", "cents_to_nearest_12tet", "voiced_probability"])
        for i in range(len(f0)):
            writer.writerow([
                f"{times[i]:.6f}",
                "" if not np.isfinite(f0[i]) else f"{f0[i]:.6f}",
                "" if not np.isfinite(midi[i]) else f"{midi[i]:.6f}",
                "" if not np.isfinite(cents_to_nearest[i]) else f"{cents_to_nearest[i]:.6f}",
                "" if voiced_prob is None or not np.isfinite(voiced_prob[i]) else f"{voiced_prob[i]:.6f}",
            ])

    valid_cents = cents_to_nearest[np.isfinite(cents_to_nearest)]
    valid_f0 = f0[np.isfinite(f0)]
    tuning = float(librosa.estimate_tuning(y=ya, sr=sr) * 100.0)
    return {
        "voiced_frames": int(np.sum(valid)),
        "total_frames": int(len(f0)),
        "voiced_fraction": float(np.mean(valid)) if len(valid) else 0.0,
        "median_f0_hz": float(np.median(valid_f0)) if len(valid_f0) else None,
        "estimated_tuning_offset_cents": tuning,
        "median_abs_distance_to_nearest_12tet_cents": float(np.median(np.abs(valid_cents))) if len(valid_cents) else None,
        "p90_abs_distance_to_nearest_12tet_cents": float(np.percentile(np.abs(valid_cents), 90)) if len(valid_cents) else None,
    }


def make_plots(
    y: np.ndarray,
    sr: int,
    active_end: float,
    stft_db: np.ndarray,
    hop_length: int,
    outdir: Path,
) -> None:
    t = np.arange(len(y)) / sr
    fig, ax = plt.subplots(figsize=(14, 4))
    ax.plot(t, y, linewidth=0.35)
    ax.axvline(active_end, linestyle="--", linewidth=1)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Amplitude")
    ax.set_title("Waveform")
    fig.tight_layout()
    fig.savefig(outdir / "waveform.png", dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(14, 6))
    img = librosa.display.specshow(
        stft_db,
        sr=sr,
        hop_length=hop_length,
        x_axis="time",
        y_axis="log",
        ax=ax,
    )
    ax.set_title("Log-frequency spectrogram")
    fig.colorbar(img, ax=ax, format="%+2.0f dB")
    fig.tight_layout()
    fig.savefig(outdir / "spectrogram.png", dpi=160)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--sr", type=int, default=24000)
    args = parser.parse_args()

    audio = args.audio.resolve()
    outdir = args.out.resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    probe = ffprobe(audio)
    tags = extract_id3(audio)
    digest = sha256_file(audio)
    size = audio.stat().st_size

    y, sr = librosa.load(audio, sr=args.sr, mono=True)
    active_end = active_end_from_energy(y, sr, top_db=50.0)

    n_fft = 2048
    hop = 512
    stft = librosa.stft(y, n_fft=n_fft, hop_length=hop, window="hann")
    mag = np.abs(stft)
    power = mag * mag
    stft_db = librosa.amplitude_to_db(mag, ref=np.max)
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)

    rms = librosa.feature.rms(S=mag)[0]
    centroid = librosa.feature.spectral_centroid(S=mag, sr=sr)[0]
    flatness = librosa.feature.spectral_flatness(S=mag)[0]
    zcr = librosa.feature.zero_crossing_rate(y, frame_length=n_fft, hop_length=hop)[0]
    onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    low_ratio = frame_band_ratio(power, freqs, 300.0)
    times = librosa.times_like(rms, sr=sr, hop_length=hop)

    n = min(len(rms), len(centroid), len(flatness), len(zcr), len(onset), len(low_ratio), len(times))
    rms, centroid, flatness, zcr, onset, low_ratio, times = (
        arr[:n] for arr in (rms, centroid, flatness, zcr, onset, low_ratio, times)
    )

    candidates, novelty = detect_boundaries(
        times,
        [rms, centroid, flatness, zcr, onset, low_ratio],
        active_end,
        sr,
        hop,
    )

    internals = sorted([c["time_s"] for c in candidates if c["time_s"] < active_end - 5.0])
    if len(internals) > 2:
        top = sorted(candidates, key=lambda c: c["novelty"], reverse=True)
        internals = sorted([c["time_s"] for c in top if c["time_s"] < active_end - 5.0][:2])
    bounds = [0.0] + internals[:2] + [active_end]
    sections = [section_summary(y, sr, bounds[i], bounds[i + 1], n_fft, hop) for i in range(len(bounds) - 1)]

    beat_tempo, beat_frames = librosa.beat.beat_track(y=y[: int(active_end * sr)], sr=sr, hop_length=hop)
    tempo_value = float(np.asarray(beat_tempo).reshape(-1)[0]) if np.size(beat_tempo) else 0.0

    metadata = {
        "input": str(audio),
        "sha256": digest,
        "size_bytes": size,
        "sample_rate_analysis_hz": sr,
        "decoded_duration_s": float(len(y) / sr),
        "active_end_s_top_db_50": active_end,
        "trailing_silence_s_estimate": max(0.0, float(len(y) / sr - active_end)),
        "ffprobe": probe,
        "id3": tags,
        "global_beat_tempo_bpm": tempo_value,
        "global_beat_count": int(len(beat_frames)),
    }
    write_json(outdir / "metadata.json", metadata)

    if "lyrics-eng" in tags:
        (outdir / "embedded-lyrics-eng.txt").write_text(tags["lyrics-eng"].rstrip() + "\n", encoding="utf-8")

    with (outdir / "spectral-features.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["time_s", "rms", "spectral_centroid_hz", "spectral_flatness", "zcr", "onset_strength", "energy_lt_300_ratio", "novelty"])
        for i in range(n):
            writer.writerow([
                f"{times[i]:.6f}", f"{rms[i]:.9f}", f"{centroid[i]:.6f}",
                f"{flatness[i]:.9f}", f"{zcr[i]:.9f}", f"{onset[i]:.9f}",
                f"{low_ratio[i]:.9f}", f"{novelty[i]:.9f}",
            ])

    write_json(outdir / "sections.json", {
        "active_end_s": active_end,
        "candidate_boundaries": candidates,
        "selected_boundaries_s": bounds,
        "sections": sections,
    })

    pitch_summary = analyze_pitch(y, sr, active_end, outdir)
    write_json(outdir / "pitch-summary.json", pitch_summary)
    make_plots(y, sr, active_end, stft_db, hop, outdir)

    report_lines = [
        "# Acoustic analysis report",
        "",
        f"- input: `{audio.name}`",
        f"- SHA-256: `{digest}`",
        f"- size: {size:,} bytes",
        f"- decoded duration: {len(y) / sr:.3f} s",
        f"- estimated active end: {active_end:.3f} s",
        f"- estimated trailing silence: {max(0.0, len(y) / sr - active_end):.3f} s",
        f"- global beat tempo estimate: {tempo_value:.2f} BPM",
        f"- estimated tuning offset: {pitch_summary['estimated_tuning_offset_cents']:.2f} cents",
        "",
        "## Candidate boundaries",
        "",
    ]
    for c in candidates:
        report_lines.append(f"- {c['time_s']:.3f} s (novelty {c['novelty']:.3f})")
    report_lines += ["", "## Selected broad sections", ""]
    for i, s in enumerate(sections, 1):
        report_lines.append(
            f"- section {i}: {s['start_s']:.3f}–{s['end_s']:.3f} s; "
            f"centroid {s.get('spectral_centroid_hz_mean', math.nan):.1f} Hz; "
            f"<300 Hz {100*s.get('energy_lt_300_ratio', math.nan):.1f}%; "
            f"300–1000 Hz {100*s.get('energy_300_1000_ratio', math.nan):.1f}%"
        )
    report_lines += [
        "",
        "Interpretation is deliberately kept separate from these measurements. See docs/audio-analysis.md.",
        "",
    ]
    (outdir / "report.md").write_text("\n".join(report_lines), encoding="utf-8")

    print(json.dumps({
        "sha256": digest,
        "active_end_s": active_end,
        "candidate_boundaries": candidates,
        "selected_boundaries_s": bounds,
        "pitch_summary": pitch_summary,
        "outdir": str(outdir),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
