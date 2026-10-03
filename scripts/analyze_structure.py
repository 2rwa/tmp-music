#!/usr/bin/env python3
"""Multi-view recurrence, period, and cycle-distance analysis for repeated music."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import librosa
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common.structure import (
    cosine_similarity_matrix,
    cycle_boundaries_from_period,
    lag_similarity_profile,
    multiview_lag_profile,
    pairwise_cycle_distances,
    period_candidates,
    template_alignment_starts,
    view_agreement,
    zscore_features,
)


def extract_views(
    y: np.ndarray,
    sr: int,
    hop_length: int,
) -> dict[str, np.ndarray]:
    n_fft = min(4096, max(1024, 2 ** int(np.ceil(np.log2(hop_length)))))
    mfcc = librosa.feature.mfcc(
        y=y,
        sr=sr,
        n_mfcc=20,
        n_fft=n_fft,
        hop_length=hop_length,
    ).T
    chroma = librosa.feature.chroma_stft(
        y=y,
        sr=sr,
        n_fft=n_fft,
        hop_length=hop_length,
        n_chroma=12,
    ).T
    onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop_length)
    tempogram = librosa.feature.tempogram(
        onset_envelope=onset,
        sr=sr,
        hop_length=hop_length,
        win_length=32,
        center=True,
    ).T
    rhythm = np.column_stack([onset[: len(tempogram)], tempogram])
    n = min(len(mfcc), len(chroma), len(rhythm))
    return {
        "mfcc": mfcc[:n],
        "chroma": chroma[:n],
        "rhythm": rhythm[:n],
    }


def write_lag_profile(path: Path, profile: list[dict[str, object]], frame_step_s: float) -> None:
    view_names = sorted({
        name
        for row in profile
        for name in dict(row.get("views", {})).keys()
    })
    with path.open("w", newline="", encoding="utf-8") as f:
        fields = ["lag_frames", "lag_s", "combined_similarity", "support", *view_names]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in profile:
            views = dict(row.get("views", {}))
            writer.writerow({
                "lag_frames": row["lag_frames"],
                "lag_s": float(row["lag_frames"]) * frame_step_s,
                "combined_similarity": row["combined_similarity"],
                "support": row["support"],
                **{name: views.get(name) for name in view_names},
            })


def write_matrix_csv(path: Path, matrix: np.ndarray) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["cycle", *[f"cycle-{i + 1:02d}" for i in range(matrix.shape[1])]])
        for i, row in enumerate(matrix):
            writer.writerow([f"cycle-{i + 1:02d}", *[float(x) for x in row]])


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("audio", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--sr", type=int, default=16000)
    p.add_argument("--frame-step", type=float, default=0.25)
    p.add_argument("--min-period", type=float, default=20.0)
    p.add_argument("--max-period", type=float, default=40.0)
    p.add_argument("--anchor-start", type=float, default=0.0)
    p.add_argument("--alignment-template-duration", type=float, default=22.0)
    p.add_argument("--alignment-search-radius", type=float, default=4.0)
    p.add_argument("--top-k", type=int, default=8)
    args = p.parse_args()

    if args.frame_step <= 0:
        raise ValueError("frame-step must be positive")
    if args.min_period <= 0 or args.max_period <= args.min_period:
        raise ValueError("period search range is invalid")

    y, sr = librosa.load(args.audio.resolve(), sr=args.sr, mono=True)
    hop_length = max(1, round(sr * args.frame_step))
    frame_step_s = hop_length / sr
    views = extract_views(y, sr, hop_length)
    frames = min(len(v) for v in views.values())
    duration_s = len(y) / sr

    min_lag = max(1, round(args.min_period / frame_step_s))
    max_lag = min(frames - 1, round(args.max_period / frame_step_s))
    profile = multiview_lag_profile(
        views,
        min_lag=min_lag,
        max_lag=max_lag,
    )
    candidates = period_candidates(
        profile,
        top_k=args.top_k,
        min_separation_frames=max(1, round(1.0 / frame_step_s)),
    )
    if not candidates:
        raise RuntimeError("no recurrence period candidates found")

    per_view_candidates: dict[str, list[dict[str, object]]] = {}
    for name, feature in views.items():
        rows = lag_similarity_profile(feature, min_lag=min_lag, max_lag=max_lag)
        per_view_candidates[name] = period_candidates(
            rows,
            score_key="similarity",
            top_k=args.top_k,
            min_separation_frames=max(1, round(1.0 / frame_step_s)),
        )

    selected_frames = int(candidates[0]["lag_frames"])
    selected_period_s = selected_frames * frame_step_s
    anchor_frame = min(frames - 1, max(0, round(args.anchor_start / frame_step_s)))
    full_boundaries = cycle_boundaries_from_period(
        frames,
        selected_frames,
        start_frame=anchor_frame,
        include_partial=False,
    )
    if len(full_boundaries) < 3:
        raise RuntimeError(
            f"selected period yields fewer than two full cycles: period={selected_period_s:.3f}s"
        )

    cycles = [
        {
            "id": f"cycle-{i + 1:02d}",
            "start_frame": start,
            "end_frame": end,
            "start_s": start * frame_step_s,
            "end_s": end * frame_step_s,
            "duration_s": (end - start) * frame_step_s,
            "boundary_method": "period-grid",
        }
        for i, (start, end) in enumerate(zip(full_boundaries[:-1], full_boundaries[1:]))
    ]

    alignment_template_frames = max(1, round(args.alignment_template_duration / frame_step_s))
    alignment_radius_frames = max(0, round(args.alignment_search_radius / frame_step_s))
    alignment_rows = template_alignment_starts(
        views,
        anchor_frame=anchor_frame,
        period_frames=selected_frames,
        template_frames=alignment_template_frames,
        search_radius_frames=alignment_radius_frames,
        view_names=("mfcc", "chroma"),
    )
    alignment_rows = [
        {
            **row,
            "expected_s": float(row["expected_frame"]) * frame_step_s,
            "aligned_s": float(row["aligned_frame"]) * frame_step_s,
            "offset_s": float(row["offset_frames"]) * frame_step_s,
        }
        for row in alignment_rows
    ]
    aligned_starts = [int(row["aligned_frame"]) for row in alignment_rows]
    aligned_boundaries = list(aligned_starts)
    minimum_tail = max(1, round(selected_frames * 0.5))
    if aligned_boundaries and frames - aligned_boundaries[-1] >= minimum_tail:
        aligned_boundaries.append(frames)
    aligned_cycles = [
        {
            "id": f"cycle-{i + 1:02d}",
            "start_frame": start,
            "end_frame": end,
            "start_s": start * frame_step_s,
            "end_s": min(duration_s, end * frame_step_s),
            "duration_s": (end - start) * frame_step_s,
            "boundary_method": "template-aligned",
        }
        for i, (start, end) in enumerate(zip(aligned_boundaries[:-1], aligned_boundaries[1:]))
    ]

    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    ssm_payload = {
        name: cosine_similarity_matrix(zscore_features(feature)).astype(np.float32)
        for name, feature in views.items()
    }
    np.savez_compressed(out / "ssm.npz", **ssm_payload)
    np.savez_compressed(out / "features.npz", **{name: value.astype(np.float32) for name, value in views.items()})
    write_lag_profile(out / "lag-profile.csv", profile, frame_step_s)

    distance_summary: dict[str, object] = {}
    aligned_distance_summary: dict[str, object] = {}
    for name, feature in views.items():
        matrix = pairwise_cycle_distances(feature, full_boundaries)
        write_matrix_csv(out / f"cycle-distance-{name}.csv", matrix)
        off_diagonal = matrix[np.triu_indices_from(matrix, k=1)]
        distance_summary[name] = {
            "cycle_count": int(matrix.shape[0]),
            "mean_pairwise_distance": float(np.mean(off_diagonal)) if len(off_diagonal) else None,
            "median_pairwise_distance": float(np.median(off_diagonal)) if len(off_diagonal) else None,
            "max_pairwise_distance": float(np.max(off_diagonal)) if len(off_diagonal) else None,
        }
        if len(aligned_boundaries) >= 3:
            aligned_matrix = pairwise_cycle_distances(feature, aligned_boundaries)
            write_matrix_csv(out / f"aligned-cycle-distance-{name}.csv", aligned_matrix)
            aligned_off_diagonal = aligned_matrix[np.triu_indices_from(aligned_matrix, k=1)]
            aligned_distance_summary[name] = {
                "cycle_count": int(aligned_matrix.shape[0]),
                "mean_pairwise_distance": float(np.mean(aligned_off_diagonal)) if len(aligned_off_diagonal) else None,
                "median_pairwise_distance": float(np.median(aligned_off_diagonal)) if len(aligned_off_diagonal) else None,
                "max_pairwise_distance": float(np.max(aligned_off_diagonal)) if len(aligned_off_diagonal) else None,
            }

    agreement = view_agreement(
        {
            name: [int(row["lag_frames"]) for row in rows]
            for name, rows in per_view_candidates.items()
        },
        tolerance_frames=max(1, round(1.0 / frame_step_s)),
    )

    result = {
        "audio": str(args.audio),
        "duration_s": duration_s,
        "sample_rate_hz": sr,
        "frame_step_s": frame_step_s,
        "frames": frames,
        "views": {
            name: {"frames": int(value.shape[0]), "dimensions": int(value.shape[1])}
            for name, value in views.items()
        },
        "period_search_s": [args.min_period, args.max_period],
        "period_candidates": [
            {
                **row,
                "period_s": float(row["lag_frames"]) * frame_step_s,
            }
            for row in candidates
        ],
        "per_view_period_candidates": {
            name: [
                {**row, "period_s": float(row["lag_frames"]) * frame_step_s}
                for row in rows
            ]
            for name, rows in per_view_candidates.items()
        },
        "view_agreement": [
            {
                **row,
                "period_s": float(row["period_frames"]) * frame_step_s,
            }
            for row in agreement
        ],
        "selected_period_frames": selected_frames,
        "selected_period_s": selected_period_s,
        "anchor_start_requested_s": args.anchor_start,
        "anchor_start_effective_s": anchor_frame * frame_step_s,
        "alignment_template_duration_s": args.alignment_template_duration,
        "alignment_search_radius_s": args.alignment_search_radius,
        "cycle_alignment_starts": alignment_rows,
        "cycles": cycles,
        "aligned_cycles": aligned_cycles,
        "cycle_distance_summary": distance_summary,
        "aligned_cycle_distance_summary": aligned_distance_summary,
        "interpretation_warning": (
            "A recurrence period and low DTW distance describe repeated signal structure. "
            "They do not identify lyrical, cultural, or compositional meaning."
        ),
    }
    (out / "structure.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
