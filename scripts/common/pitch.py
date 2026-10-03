"""Pitch consensus, stable-target detection, and equal-division fitting."""
from __future__ import annotations

import math
from typing import Iterable

import numpy as np


def cents_between(a_hz: float, b_hz: float) -> float:
    if a_hz <= 0 or b_hz <= 0:
        return math.nan
    return 1200.0 * math.log2(a_hz / b_hz)


def hz_to_midi(hz: float) -> float:
    if hz <= 0:
        return math.nan
    return 69.0 + 12.0 * math.log2(hz / 440.0)


def consensus_frames(
    times_s: Iterable[float],
    pyin_hz: Iterable[float],
    crepe_hz: Iterable[float],
    pyin_confidence: Iterable[float],
    crepe_periodicity: Iterable[float],
    *,
    crepe_periodicity_threshold: float = 0.21,
    strong_cents: float = 25.0,
    weak_cents: float = 50.0,
) -> list[dict[str, float | str | None]]:
    arrays = [
        np.asarray(list(times_s), dtype=float),
        np.asarray(list(pyin_hz), dtype=float),
        np.asarray(list(crepe_hz), dtype=float),
        np.asarray(list(pyin_confidence), dtype=float),
        np.asarray(list(crepe_periodicity), dtype=float),
    ]
    n = min(len(x) for x in arrays)
    t, p, c, pc, cc = (x[:n] for x in arrays)

    rows: list[dict[str, float | str | None]] = []
    for i in range(n):
        p_ok = bool(np.isfinite(p[i]) and p[i] > 0)
        c_ok = bool(np.isfinite(c[i]) and c[i] > 0 and np.isfinite(cc[i]) and cc[i] >= crepe_periodicity_threshold)
        agreement = "none"
        delta: float | None = None
        consensus: float | None = None
        if p_ok and c_ok:
            delta = abs(cents_between(float(p[i]), float(c[i])))
            if delta <= strong_cents:
                agreement = "strong"
                consensus = math.sqrt(float(p[i]) * float(c[i]))
            elif delta <= weak_cents:
                agreement = "weak"
                consensus = math.sqrt(float(p[i]) * float(c[i]))
            else:
                agreement = "disagreement"
        elif p_ok:
            agreement = "pyin-only"
        elif c_ok:
            agreement = "crepe-only"

        rows.append({
            "time_s": float(t[i]),
            "pyin_f0_hz": float(p[i]) if p_ok else None,
            "crepe_f0_hz": float(c[i]) if c_ok else None,
            "consensus_f0_hz": consensus,
            "disagreement_cents": delta,
            "agreement": agreement,
            "pyin_confidence": float(pc[i]) if np.isfinite(pc[i]) else None,
            "crepe_periodicity": float(cc[i]) if np.isfinite(cc[i]) else None,
        })
    return rows


def consensus_summary(rows: list[dict[str, float | str | None]]) -> dict[str, float | int]:
    total = len(rows)
    counts = {key: 0 for key in ("strong", "weak", "disagreement", "pyin-only", "crepe-only", "none")}
    consensus_count = 0
    for row in rows:
        counts[str(row["agreement"])] = counts.get(str(row["agreement"]), 0) + 1
        if row["consensus_f0_hz"] is not None:
            consensus_count += 1
    out: dict[str, float | int] = {"frames": total, **counts, "consensus_frames": consensus_count}
    out["consensus_coverage"] = consensus_count / total if total else 0.0
    out["strong_agreement_fraction"] = counts["strong"] / total if total else 0.0
    out["weak_or_strong_fraction"] = (counts["strong"] + counts["weak"]) / total if total else 0.0
    return out


def _local_linear_metrics(times: np.ndarray, cents: np.ndarray, window_s: float) -> tuple[np.ndarray, np.ndarray]:
    slope = np.full(len(times), np.nan)
    residual_std = np.full(len(times), np.nan)
    half = window_s / 2.0
    finite = np.isfinite(cents)
    for i, center in enumerate(times):
        mask = finite & (times >= center - half) & (times <= center + half)
        if int(mask.sum()) < 5:
            continue
        x = times[mask]
        y = cents[mask]
        x0 = float(np.mean(x))
        y0 = float(np.mean(y))
        den = float(np.sum((x - x0) ** 2))
        m = float(np.sum((x - x0) * (y - y0)) / den) if den > 0 else 0.0
        fit = y0 + m * (x - x0)
        slope[i] = m
        residual_std[i] = float(np.sqrt(np.mean((y - fit) ** 2)))
    return slope, residual_std


def detect_stable_segments(
    times_s: Iterable[float],
    f0_hz: Iterable[float],
    confidence: Iterable[float],
    *,
    window_s: float = 0.5,
    max_abs_slope_cents_per_s: float = 100.0,
    max_detrended_std_cents: float = 40.0,
    min_duration_s: float = 0.15,
    min_confidence: float = 0.5,
    max_gap_s: float = 0.04,
) -> list[dict[str, float | int]]:
    times = np.asarray(list(times_s), dtype=float)
    f0 = np.asarray(list(f0_hz), dtype=float)
    conf = np.asarray(list(confidence), dtype=float)
    n = min(len(times), len(f0), len(conf))
    times, f0, conf = times[:n], f0[:n], conf[:n]
    if n == 0:
        return []

    cents = np.full(n, np.nan)
    valid_f0 = np.isfinite(f0) & (f0 > 0)
    cents[valid_f0] = 1200.0 * np.log2(f0[valid_f0] / 440.0)
    slope, residual_std = _local_linear_metrics(times, cents, window_s)
    candidate = (
        valid_f0
        & np.isfinite(conf)
        & (conf >= min_confidence)
        & np.isfinite(slope)
        & (np.abs(slope) <= max_abs_slope_cents_per_s)
        & np.isfinite(residual_std)
        & (residual_std <= max_detrended_std_cents)
    )

    if len(times) > 1:
        step = float(np.median(np.diff(times)))
    else:
        step = 0.0

    groups: list[list[int]] = []
    current: list[int] = []
    for idx in np.flatnonzero(candidate):
        if not current or times[idx] - times[current[-1]] <= step + max_gap_s + 1e-12:
            current.append(int(idx))
        else:
            groups.append(current)
            current = [int(idx)]
    if current:
        groups.append(current)

    out: list[dict[str, float | int]] = []
    for group in groups:
        start_i, end_i = group[0], group[-1]
        duration = float(times[end_i] - times[start_i] + step)
        if duration < min_duration_s:
            continue
        seg_f0 = f0[group]
        seg_cents = cents[group]
        seg_conf = conf[group]
        median_f0 = float(np.median(seg_f0))
        midi = hz_to_midi(median_f0)
        nearest_12tet = 100.0 * (midi - round(midi))
        centered = seg_cents - float(np.median(seg_cents))
        vibrato_extent = float(np.percentile(centered, 95) - np.percentile(centered, 5))
        out.append({
            "start_s": float(times[start_i]),
            "end_s": float(times[end_i] + step),
            "duration_s": duration,
            "frames": len(group),
            "median_f0_hz": median_f0,
            "median_midi": midi,
            "cents_to_nearest_12tet": nearest_12tet,
            "vibrato_extent_cents_p95_p05": vibrato_extent,
            "median_confidence": float(np.median(seg_conf)),
            "median_abs_slope_cents_per_s": float(np.median(np.abs(slope[group]))),
            "median_detrended_std_cents": float(np.median(residual_std[group])),
        })
    return out


def weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    order = np.argsort(values)
    v = values[order]
    w = weights[order]
    cumulative = np.cumsum(w)
    return float(v[np.searchsorted(cumulative, cumulative[-1] / 2.0)])


def _wrap_residual(cents: np.ndarray, step_cents: float) -> np.ndarray:
    return ((cents + step_cents / 2.0) % step_cents) - step_cents / 2.0


def fit_equal_divisions(
    targets: Iterable[dict[str, float | int]],
    divisions: Iterable[int] = (12, 19, 24, 31),
) -> dict[str, object]:
    rows = list(targets)
    freqs = np.asarray([float(x["median_f0_hz"]) for x in rows], dtype=float)
    durations = np.asarray([float(x.get("duration_s", 1.0)) for x in rows], dtype=float)
    confidence = np.asarray([float(x.get("median_confidence", 1.0)) for x in rows], dtype=float)
    valid = np.isfinite(freqs) & (freqs > 0) & np.isfinite(durations) & (durations > 0) & np.isfinite(confidence) & (confidence > 0)
    freqs, durations, confidence = freqs[valid], durations[valid], confidence[valid]
    weights = durations * confidence
    if not len(freqs):
        return {"target_count": 0, "models": [], "ambiguity": None}

    absolute_cents = 1200.0 * np.log2(freqs / 440.0)
    models = []
    for edo in divisions:
        step = 1200.0 / int(edo)
        raw = _wrap_residual(absolute_cents, step)
        offset = weighted_median(raw, weights)
        residual = _wrap_residual(absolute_cents - offset, step)
        rmse = float(np.sqrt(np.average(residual ** 2, weights=weights)))
        mae = float(np.average(np.abs(residual), weights=weights))
        models.append({
            "edo": int(edo),
            "step_cents": step,
            "estimated_global_offset_cents": offset,
            "weighted_rmse_cents": rmse,
            "weighted_mae_cents": mae,
            "target_count": int(len(freqs)),
            "weighted_duration_confidence": float(weights.sum()),
        })

    by_rmse = sorted(models, key=lambda x: float(x["weighted_rmse_cents"]))
    ambiguity = None
    if len(by_rmse) >= 2:
        ambiguity = {
            "lowest_residual_edo": by_rmse[0]["edo"],
            "rmse_gap_to_second_cents": float(by_rmse[1]["weighted_rmse_cents"] - by_rmse[0]["weighted_rmse_cents"]),
            "note": "Lowest residual is a fit statistic, not an identification of the track's scale or tuning system.",
        }
    return {"target_count": int(len(freqs)), "models": models, "ambiguity": ambiguity}
