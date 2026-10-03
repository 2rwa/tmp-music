"""Cheap structure-analysis primitives for recurrence and cycle comparison."""
from __future__ import annotations

from typing import Iterable, Mapping

import numpy as np


def _frames(features: np.ndarray) -> np.ndarray:
    x = np.asarray(features, dtype=np.float64)
    if x.ndim == 1:
        x = x[:, None]
    if x.ndim != 2:
        raise ValueError(f"features must be 1-D or 2-D, got {x.shape}")
    if x.shape[0] < 1:
        raise ValueError("features must contain at least one frame")
    return x


def zscore_features(features: np.ndarray, eps: float = 1e-12) -> np.ndarray:
    """Standardize each feature dimension over time without creating NaNs."""
    x = _frames(features)
    mean = np.mean(x, axis=0, keepdims=True)
    std = np.std(x, axis=0, keepdims=True)
    return (x - mean) / np.where(std > eps, std, 1.0)


def cosine_similarity_matrix(features: np.ndarray, eps: float = 1e-12) -> np.ndarray:
    """Frame-by-frame cosine similarity in [-1, 1]."""
    x = _frames(features)
    norms = np.linalg.norm(x, axis=1, keepdims=True)
    unit = x / np.where(norms > eps, norms, 1.0)
    return np.clip(unit @ unit.T, -1.0, 1.0)


def lag_similarity_profile_from_ssm(
    ssm: np.ndarray,
    *,
    min_lag: int = 1,
    max_lag: int | None = None,
) -> list[dict[str, float | int]]:
    """Average self-similarity along each positive lag diagonal."""
    matrix = np.asarray(ssm, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        raise ValueError("ssm must be a square matrix")
    n = matrix.shape[0]
    if max_lag is None:
        max_lag = n - 1
    max_lag = min(int(max_lag), n - 1)
    min_lag = max(1, int(min_lag))
    if min_lag > max_lag:
        return []

    rows: list[dict[str, float | int]] = []
    for lag in range(min_lag, max_lag + 1):
        values = np.diag(matrix, k=lag)
        finite = values[np.isfinite(values)]
        score = float(np.mean(finite)) if len(finite) else float("nan")
        rows.append({"lag_frames": lag, "similarity": score, "support": int(len(finite))})
    return rows


def lag_similarity_profile(
    features: np.ndarray,
    *,
    min_lag: int = 1,
    max_lag: int | None = None,
) -> list[dict[str, float | int]]:
    return lag_similarity_profile_from_ssm(
        cosine_similarity_matrix(zscore_features(features)),
        min_lag=min_lag,
        max_lag=max_lag,
    )


def multiview_lag_profile(
    views: Mapping[str, np.ndarray],
    *,
    min_lag: int = 1,
    max_lag: int | None = None,
    weights: Mapping[str, float] | None = None,
) -> list[dict[str, object]]:
    """Combine recurrence evidence while preserving every view's score."""
    if not views:
        raise ValueError("at least one feature view is required")
    frame_counts = {name: _frames(value).shape[0] for name, value in views.items()}
    if len(set(frame_counts.values())) != 1:
        raise ValueError(f"all views must share frame count: {frame_counts}")

    profiles = {
        name: lag_similarity_profile(value, min_lag=min_lag, max_lag=max_lag)
        for name, value in views.items()
    }
    count = min(len(rows) for rows in profiles.values())
    if count == 0:
        return []

    result: list[dict[str, object]] = []
    for i in range(count):
        per_view = {name: float(rows[i]["similarity"]) for name, rows in profiles.items()}
        lag = int(next(iter(profiles.values()))[i]["lag_frames"])
        support = int(next(iter(profiles.values()))[i]["support"])
        valid: list[tuple[float, float]] = []
        for name, score in per_view.items():
            if np.isfinite(score):
                weight = float(weights.get(name, 1.0)) if weights else 1.0
                if weight > 0:
                    valid.append((score, weight))
        combined = (
            float(sum(score * weight for score, weight in valid) / sum(weight for _, weight in valid))
            if valid
            else float("nan")
        )
        result.append({
            "lag_frames": lag,
            "combined_similarity": combined,
            "support": support,
            "views": per_view,
        })
    return result


def period_candidates(
    profile: Iterable[Mapping[str, object]],
    *,
    score_key: str = "combined_similarity",
    top_k: int = 8,
    min_separation_frames: int = 1,
) -> list[dict[str, object]]:
    """Pick local maxima, preferring the shorter lag on exact-score ties."""
    rows = [dict(row) for row in profile]
    if not rows:
        return []

    local: list[dict[str, object]] = []
    for i, row in enumerate(rows):
        score = float(row.get(score_key, float("nan")))
        if not np.isfinite(score):
            continue
        left = float(rows[i - 1].get(score_key, -np.inf)) if i > 0 else -np.inf
        right = float(rows[i + 1].get(score_key, -np.inf)) if i + 1 < len(rows) else -np.inf
        if score >= left and score >= right:
            local.append(row)

    ranked = sorted(local, key=lambda row: (-float(row[score_key]), int(row["lag_frames"])))
    selected: list[dict[str, object]] = []
    for row in ranked:
        lag = int(row["lag_frames"])
        if any(abs(lag - int(other["lag_frames"])) < min_separation_frames for other in selected):
            continue
        selected.append(row)
        if len(selected) >= top_k:
            break
    return selected


def cycle_boundaries_from_period(
    total_frames: int,
    period_frames: int,
    *,
    start_frame: int = 0,
    include_partial: bool = False,
) -> list[int]:
    if total_frames <= 0 or period_frames <= 0:
        raise ValueError("total_frames and period_frames must be positive")
    if start_frame < 0 or start_frame >= total_frames:
        raise ValueError("start_frame must be within the feature sequence")

    boundaries = [int(start_frame)]
    cursor = int(start_frame)
    while cursor + period_frames <= total_frames:
        cursor += int(period_frames)
        boundaries.append(cursor)
    if include_partial and boundaries[-1] < total_frames:
        boundaries.append(int(total_frames))
    return boundaries


def _cosine_cost(a: np.ndarray, b: np.ndarray, eps: float = 1e-12) -> np.ndarray:
    a = _frames(a)
    b = _frames(b)
    an = np.linalg.norm(a, axis=1, keepdims=True)
    bn = np.linalg.norm(b, axis=1, keepdims=True)
    au = a / np.where(an > eps, an, 1.0)
    bu = b / np.where(bn > eps, bn, 1.0)
    return 1.0 - np.clip(au @ bu.T, -1.0, 1.0)


def dtw_distance(a: np.ndarray, b: np.ndarray) -> dict[str, float | int]:
    """Cosine-cost DTW with path-length normalized distance."""
    cost = _cosine_cost(a, b)
    n, m = cost.shape
    acc = np.full((n + 1, m + 1), np.inf, dtype=np.float64)
    steps = np.zeros((n + 1, m + 1), dtype=np.int64)
    acc[0, 0] = 0.0

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            predecessors = (
                (acc[i - 1, j - 1], steps[i - 1, j - 1]),
                (acc[i - 1, j], steps[i - 1, j]),
                (acc[i, j - 1], steps[i, j - 1]),
            )
            best_cost, best_steps = min(predecessors, key=lambda item: (item[0], item[1]))
            acc[i, j] = cost[i - 1, j - 1] + best_cost
            steps[i, j] = best_steps + 1

    path_length = int(steps[n, m])
    total = float(acc[n, m])
    return {
        "total_cost": total,
        "path_length": path_length,
        "normalized_distance": total / path_length if path_length else float("nan"),
    }


def pairwise_cycle_distances(
    features: np.ndarray,
    boundaries: Iterable[int],
) -> np.ndarray:
    x = _frames(features)
    edges = [int(v) for v in boundaries]
    if len(edges) < 2:
        raise ValueError("at least two boundaries are required")
    if edges != sorted(edges) or len(set(edges)) != len(edges):
        raise ValueError("boundaries must be strictly increasing")
    if edges[0] < 0 or edges[-1] > len(x):
        raise ValueError("boundaries fall outside feature sequence")

    cycles = [x[a:b] for a, b in zip(edges[:-1], edges[1:])]
    if any(len(cycle) == 0 for cycle in cycles):
        raise ValueError("cycles must contain at least one frame")
    matrix = np.zeros((len(cycles), len(cycles)), dtype=np.float64)
    for i in range(len(cycles)):
        for j in range(i + 1, len(cycles)):
            distance = float(dtw_distance(cycles[i], cycles[j])["normalized_distance"])
            matrix[i, j] = matrix[j, i] = distance
    return matrix


def view_agreement(candidates: Mapping[str, Iterable[int]], tolerance_frames: int = 2) -> list[dict[str, object]]:
    """Group candidate periods from multiple views by frame tolerance."""
    points = sorted(
        (int(lag), str(view))
        for view, lags in candidates.items()
        for lag in lags
    )
    groups: list[list[tuple[int, str]]] = []
    for lag, view in points:
        if not groups or lag - int(round(np.mean([x for x, _ in groups[-1]]))) > tolerance_frames:
            groups.append([(lag, view)])
        else:
            groups[-1].append((lag, view))
    return [
        {
            "period_frames": int(round(np.median([lag for lag, _ in group]))),
            "views": sorted({view for _, view in group}),
            "view_count": len({view for _, view in group}),
            "lags": [lag for lag, _ in group],
        }
        for group in groups
    ]


def template_alignment_starts(
    views: Mapping[str, np.ndarray],
    *,
    anchor_frame: int,
    period_frames: int,
    template_frames: int,
    search_radius_frames: int,
    view_names: Iterable[str] | None = None,
    min_separation_fraction: float = 0.5,
) -> list[dict[str, object]]:
    """Refine repeated-content start positions around a fixed recurrence grid.

    This does not redefine the recurrence period. It answers a different
    question: near each expected period-grid position, where does the same
    template content align best?
    """
    selected = list(view_names) if view_names is not None else list(views)
    if not selected:
        raise ValueError("at least one alignment view is required")
    frame_counts = {_name: _frames(views[_name]).shape[0] for _name in selected}
    if len(set(frame_counts.values())) != 1:
        raise ValueError(f"alignment views must share frame count: {frame_counts}")
    total_frames = next(iter(frame_counts.values()))
    if period_frames <= 0 or template_frames <= 0:
        raise ValueError("period_frames and template_frames must be positive")
    if anchor_frame < 0 or anchor_frame + template_frames > total_frames:
        raise ValueError("alignment template falls outside feature sequence")

    normalized: dict[str, np.ndarray] = {}
    templates: dict[str, np.ndarray] = {}
    for name in selected:
        x = zscore_features(views[name])
        norms = np.linalg.norm(x, axis=1, keepdims=True)
        unit = x / np.where(norms > 1e-12, norms, 1.0)
        normalized[name] = unit
        templates[name] = unit[anchor_frame:anchor_frame + template_frames]

    min_sep = max(1, round(period_frames * min_separation_fraction))
    rows: list[dict[str, object]] = []
    previous: int | None = None
    k = 0
    while True:
        expected = anchor_frame + k * period_frames
        if expected - search_radius_frames > total_frames - template_frames:
            break
        low = max(0, expected - search_radius_frames)
        high = min(total_frames - template_frames, expected + search_radius_frames)
        if previous is not None:
            low = max(low, previous + min_sep)
        if low > high:
            break

        candidates: list[tuple[float, int, int, dict[str, float]]] = []
        for start in range(low, high + 1):
            per_view: dict[str, float] = {}
            for name in selected:
                segment = normalized[name][start:start + template_frames]
                per_view[name] = float(np.mean(np.sum(templates[name] * segment, axis=1)))
            combined = float(np.mean(list(per_view.values())))
            candidates.append((combined, -abs(start - expected), -start, per_view))

        best = max(candidates, key=lambda item: (item[0], item[1], item[2]))
        start = -best[2]
        rows.append({
            "index": k,
            "expected_frame": expected,
            "aligned_frame": start,
            "offset_frames": start - expected,
            "combined_similarity": best[0],
            "views": best[3],
        })
        previous = start
        k += 1
    return rows
