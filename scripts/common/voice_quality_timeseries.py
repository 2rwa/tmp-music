"""High-resolution M6 voice-quality helpers.

Level 2 keeps the segment-level M6 definitions intact and adds time-aligned
measurements for visualization and exploratory analysis.  Praat CPPS/HNR are
produced by the companion Praat script; this module covers F0-guided local
Python metrics and local pitch-modulation descriptors.
"""
from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from typing import Iterable

import numpy as np

from .voice_quality import rms_dbfs, spectral_tilt_db_per_octave


def _finite(value: object) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if np.isfinite(x) else None


def parse_pitch_consensus(rows: Iterable[dict[str, object]]) -> list[tuple[float, float, float]]:
    """Return sorted (time_s, selected_f0_hz, selected_confidence) tuples."""
    points: list[tuple[float, float, float]] = []
    for row in rows:
        t = _finite(row.get("time_s"))
        f0 = _finite(row.get("selected_f0_hz"))
        conf = _finite(row.get("selected_confidence"))
        if t is None or f0 is None or f0 <= 0:
            continue
        points.append((t, f0, conf if conf is not None else 0.0))
    points.sort(key=lambda x: x[0])
    return points


def decimate_pitch_points(
    points: Iterable[tuple[float, float, float]], *, hop_s: float
) -> list[tuple[float, float, float]]:
    """Select pitch observations no closer than hop_s while preserving timestamps."""
    if hop_s <= 0:
        raise ValueError("hop_s must be positive")
    selected: list[tuple[float, float, float]] = []
    next_time = -math.inf
    for point in points:
        if point[0] + 1e-12 < next_time:
            continue
        selected.append(point)
        next_time = point[0] + hop_s
    return selected


def local_pitch_modulation_metrics(
    points: list[tuple[float, float, float]],
    center_s: float,
    *,
    window_s: float = 0.8,
    min_confidence: float = 0.5,
    max_gap_s: float = 0.05,
    min_points: int = 12,
    rate_min_hz: float = 3.0,
    rate_max_hz: float = 9.0,
) -> dict[str, float | None]:
    """Estimate local detrended F0 modulation extent and dominant rate.

    This is reported as a vibrato-oriented local descriptor, not as proof that
    the interval contains intentional vibrato.  Windows crossing large pitch
    gaps are rejected rather than interpolated across unvoiced regions.
    """
    half = 0.5 * float(window_s)
    lo = bisect_left(points, center_s - half, key=lambda p: p[0])
    hi = bisect_right(points, center_s + half, key=lambda p: p[0])
    local = [p for p in points[lo:hi] if p[2] >= min_confidence]
    if len(local) < min_points:
        return {"extent_cents_p95_p05": None, "detrended_std_cents": None, "rate_hz": None, "median_confidence": None}
    times = np.asarray([p[0] for p in local], dtype=float)
    if times.size < 2 or float(np.max(np.diff(times))) > max_gap_s:
        return {"extent_cents_p95_p05": None, "detrended_std_cents": None, "rate_hz": None, "median_confidence": None}
    f0 = np.asarray([p[1] for p in local], dtype=float)
    conf = np.asarray([p[2] for p in local], dtype=float)
    cents = 1200.0 * np.log2(f0 / 440.0)
    slope, intercept = np.polyfit(times, cents, 1)
    residual = cents - (slope * times + intercept)
    extent = float(np.quantile(residual, 0.95) - np.quantile(residual, 0.05))
    std = float(np.std(residual))

    duration = float(times[-1] - times[0])
    rate = None
    if duration >= max(0.45, 2.0 / rate_min_hz):
        dt = float(np.median(np.diff(times)))
        if dt > 0 and np.isfinite(dt):
            grid = np.arange(times[0], times[-1] + 0.5 * dt, dt)
            if grid.size >= min_points:
                values = np.interp(grid, times, residual)
                values = (values - float(np.mean(values))) * np.hanning(values.size)
                spec = np.abs(np.fft.rfft(values))
                freq = np.fft.rfftfreq(values.size, d=dt)
                mask = (freq >= rate_min_hz) & (freq <= rate_max_hz)
                if np.any(mask):
                    masked = spec[mask]
                    if masked.size and float(np.max(masked)) > 1e-9:
                        rate = float(freq[mask][int(np.argmax(masked))])

    return {
        "extent_cents_p95_p05": extent if np.isfinite(extent) else None,
        "detrended_std_cents": std if np.isfinite(std) else None,
        "rate_hz": rate if rate is None or np.isfinite(rate) else None,
        "median_confidence": float(np.median(conf)),
    }



def local_autocorrelation_hnr_db(
    frame: np.ndarray,
    sample_rate_hz: int,
    f0_hz: float,
    *,
    search_fraction: float = 0.15,
) -> float | None:
    """Equivalent F0-near HNR using only the relevant lag interval.

    This matches the existing M6 autocorrelation definition but avoids
    calculating the full autocorrelation sequence for every Level-2 frame.
    """
    x = np.asarray(frame, dtype=float)
    if x.size < 8 or not np.isfinite(f0_hz) or f0_hz <= 0:
        return None
    x = (x - float(np.mean(x))) * np.hanning(x.size)
    energy = float(np.dot(x, x))
    if energy <= 1e-12:
        return None
    low = max(1, int(math.floor(sample_rate_hz / (f0_hz * (1.0 + search_fraction)))))
    high = min(
        x.size - 1,
        int(math.ceil(sample_rate_hz / (f0_hz * (1.0 - search_fraction)))),
    )
    if high < low:
        return None
    peak = max(float(np.dot(x[:-lag], x[lag:])) for lag in range(low, high + 1))
    r = float(np.clip(peak / energy, 1e-9, 1.0 - 1e-9))
    if r <= 0:
        return None
    return float(10.0 * np.log10(r / (1.0 - r)))

def frame_voice_quality_series(
    samples: np.ndarray,
    sample_rate_hz: int,
    pitch_points: list[tuple[float, float, float]],
    *,
    hop_s: float = 0.02,
    frame_length_ms: float = 60.0,
    hnr_search_fraction: float = 0.15,
    tilt_min_hz: float = 200.0,
    tilt_max_hz: float = 5000.0,
    min_rms_dbfs: float = -70.0,
    vibrato_window_s: float = 0.8,
    vibrato_min_confidence: float = 0.5,
) -> list[dict[str, float | None]]:
    """Measure local Python metrics at decimated selected-F0 timestamps."""
    x = np.asarray(samples, dtype=float)
    frame_n = max(16, int(round(sample_rate_hz * frame_length_ms / 1000.0)))
    half = frame_n // 2
    selected = decimate_pitch_points(pitch_points, hop_s=hop_s)
    out: list[dict[str, float | None]] = []
    for t, f0, conf in selected:
        center = int(round(t * sample_rate_hz))
        start = center - half
        end = start + frame_n
        if start < 0 or end > x.size:
            continue
        frame = x[start:end]
        rms = rms_dbfs(frame)
        if rms is None or rms < min_rms_dbfs:
            continue
        modulation = local_pitch_modulation_metrics(
            pitch_points,
            t,
            window_s=vibrato_window_s,
            min_confidence=vibrato_min_confidence,
        )
        out.append({
            "time_s": float(t),
            "selected_f0_hz": float(f0),
            "selected_confidence": float(conf),
            "rms_dbfs": rms,
            "autocorrelation_hnr_db": local_autocorrelation_hnr_db(
                frame,
                sample_rate_hz,
                f0,
                search_fraction=hnr_search_fraction,
            ),
            "spectral_tilt_db_per_octave": spectral_tilt_db_per_octave(
                frame,
                sample_rate_hz,
                min_hz=tilt_min_hz,
                max_hz=tilt_max_hz,
            ),
            "local_vibrato_extent_cents_p95_p05": modulation["extent_cents_p95_p05"],
            "local_vibrato_detrended_std_cents": modulation["detrended_std_cents"],
            "local_vibrato_rate_hz": modulation["rate_hz"],
            "local_vibrato_median_confidence": modulation["median_confidence"],
        })
    return out
