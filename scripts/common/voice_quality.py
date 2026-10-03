"""Transparent baseline voice-quality measurements for stable voiced audio.

These metrics deliberately use explicit names rather than claiming equivalence
to Praat or other standardized implementations. In particular,
autocorrelation_hnr_db is an F0-guided autocorrelation estimate and
spectral_tilt_db_per_octave is a log-spectrum regression over retained bins.
"""
from __future__ import annotations

import math
import re
from typing import Iterable

import numpy as np

_EPS = 1e-12


def rms_dbfs(frame: np.ndarray) -> float | None:
    x = np.asarray(frame, dtype=float)
    if x.size == 0:
        return None
    rms = float(np.sqrt(np.mean(np.square(x))))
    if not np.isfinite(rms):
        return None
    return float(20.0 * np.log10(max(rms, _EPS)))


def normalized_autocorrelation_peak(
    frame: np.ndarray,
    sample_rate_hz: int,
    f0_hz: float,
    *,
    search_fraction: float = 0.15,
) -> float | None:
    x = np.asarray(frame, dtype=float)
    if x.size < 8 or not np.isfinite(f0_hz) or f0_hz <= 0:
        return None
    x = x - float(np.mean(x))
    x = x * np.hanning(x.size)
    energy = float(np.dot(x, x))
    if energy <= _EPS:
        return None

    corr = np.correlate(x, x, mode="full")[x.size - 1 :]
    low = max(1, int(math.floor(sample_rate_hz / (f0_hz * (1.0 + search_fraction)))))
    high = min(
        corr.size - 1,
        int(math.ceil(sample_rate_hz / (f0_hz * (1.0 - search_fraction)))),
    )
    if high < low:
        return None
    peak = float(np.max(corr[low : high + 1]) / corr[0])
    return float(np.clip(peak, 0.0, 1.0 - 1e-9))


def autocorrelation_hnr_db(
    frame: np.ndarray,
    sample_rate_hz: int,
    f0_hz: float,
    *,
    search_fraction: float = 0.15,
) -> float | None:
    """Return 10*log10(r/(1-r)) from the F0-near autocorrelation peak.

    This is a transparent autocorrelation HNR estimate, not Praat Harmonicity.
    """
    peak = normalized_autocorrelation_peak(
        frame, sample_rate_hz, f0_hz, search_fraction=search_fraction
    )
    if peak is None or peak <= 0:
        return None
    r = float(np.clip(peak, 1e-9, 1.0 - 1e-9))
    return float(10.0 * np.log10(r / (1.0 - r)))


def spectral_tilt_db_per_octave(
    frame: np.ndarray,
    sample_rate_hz: int,
    *,
    min_hz: float = 200.0,
    max_hz: float = 5000.0,
    dynamic_range_db: float = 50.0,
) -> float | None:
    """Fit spectral magnitude in dB against log2 frequency.

    Bins farther than dynamic_range_db below the frame maximum are excluded so
    numerical-floor bins do not dominate the regression.
    """
    x = np.asarray(frame, dtype=float)
    if x.size < 16:
        return None
    x = (x - float(np.mean(x))) * np.hanning(x.size)
    magnitude = np.abs(np.fft.rfft(x))
    freq = np.fft.rfftfreq(x.size, d=1.0 / sample_rate_hz)
    upper = min(float(max_hz), sample_rate_hz * 0.49)
    select = (freq >= float(min_hz)) & (freq <= upper)
    if int(np.count_nonzero(select)) < 8:
        return None

    mag = magnitude[select]
    hz = freq[select]
    peak = float(np.max(mag))
    if peak <= _EPS:
        return None
    threshold = peak * (10.0 ** (-float(dynamic_range_db) / 20.0))
    keep = mag >= max(threshold, _EPS)
    if int(np.count_nonzero(keep)) < 8:
        return None

    x_oct = np.log2(hz[keep] / 1000.0)
    y_db = 20.0 * np.log10(np.maximum(mag[keep], _EPS))
    slope = np.polyfit(x_oct, y_db, 1)[0]
    return float(slope) if np.isfinite(slope) else None


def finite_summary(values: Iterable[float | None]) -> dict[str, float | int | None]:
    x = np.asarray(
        [float(v) for v in values if v is not None and np.isfinite(float(v))],
        dtype=float,
    )
    if not x.size:
        return {"count": 0, "min": None, "p10": None, "median": None, "p90": None, "max": None}
    q = np.quantile(x, [0.0, 0.10, 0.50, 0.90, 1.0])
    return {
        "count": int(x.size),
        "min": float(q[0]),
        "p10": float(q[1]),
        "median": float(q[2]),
        "p90": float(q[3]),
        "max": float(q[4]),
    }


def segment_voice_quality(
    samples: np.ndarray,
    sample_rate_hz: int,
    f0_hz: float,
    *,
    frame_length_ms: float = 60.0,
    hop_length_ms: float = 20.0,
    hnr_search_fraction: float = 0.15,
    tilt_min_hz: float = 200.0,
    tilt_max_hz: float = 5000.0,
    min_rms_dbfs: float = -70.0,
) -> dict[str, object]:
    x = np.asarray(samples, dtype=float)
    frame_length = max(16, int(round(sample_rate_hz * frame_length_ms / 1000.0)))
    hop_length = max(1, int(round(sample_rate_hz * hop_length_ms / 1000.0)))
    if x.size < frame_length:
        return {
            "frame_count": 0,
            "usable_frame_count": 0,
            "rms_dbfs": finite_summary([]),
            "autocorrelation_peak": finite_summary([]),
            "autocorrelation_hnr_db": finite_summary([]),
            "spectral_tilt_db_per_octave": finite_summary([]),
        }

    rms_values: list[float] = []
    peak_values: list[float] = []
    hnr_values: list[float] = []
    tilt_values: list[float] = []
    frame_count = 0
    usable = 0
    for start in range(0, x.size - frame_length + 1, hop_length):
        frame_count += 1
        frame = x[start : start + frame_length]
        rms = rms_dbfs(frame)
        if rms is None or rms < min_rms_dbfs:
            continue
        usable += 1
        rms_values.append(rms)
        peak = normalized_autocorrelation_peak(
            frame, sample_rate_hz, f0_hz, search_fraction=hnr_search_fraction
        )
        hnr = autocorrelation_hnr_db(
            frame, sample_rate_hz, f0_hz, search_fraction=hnr_search_fraction
        )
        tilt = spectral_tilt_db_per_octave(
            frame,
            sample_rate_hz,
            min_hz=tilt_min_hz,
            max_hz=tilt_max_hz,
        )
        if peak is not None:
            peak_values.append(peak)
        if hnr is not None:
            hnr_values.append(hnr)
        if tilt is not None:
            tilt_values.append(tilt)

    return {
        "frame_count": frame_count,
        "usable_frame_count": usable,
        "rms_dbfs": finite_summary(rms_values),
        "autocorrelation_peak": finite_summary(peak_values),
        "autocorrelation_hnr_db": finite_summary(hnr_values),
        "spectral_tilt_db_per_octave": finite_summary(tilt_values),
    }


_PRAAT_RESULT_RE = re.compile(r"CPPS=([^\\t\\r\\n]+)\\tHNR=([^\\r\\n]+)")
_PRAAT_VERSION_RE = re.compile(r"Praat\\s+(\\d+)\\.(\\d+)\\.(\\d+)")


def parse_praat_cpps_hnr(text: str) -> tuple[float, float]:
    match = _PRAAT_RESULT_RE.search(text)
    if not match:
        raise ValueError(f"unparseable Praat CPPS/HNR output: {text!r}")
    return float(match.group(1)), float(match.group(2))


def parse_praat_version(text: str) -> tuple[int, int, int]:
    match = _PRAAT_VERSION_RE.search(text)
    if not match:
        raise ValueError(f"unparseable Praat version: {text!r}")
    return tuple(int(match.group(i)) for i in range(1, 4))


def parse_version_triplet(text: str) -> tuple[int, int, int]:
    parts = text.strip().split(".")
    if len(parts) != 3:
        raise ValueError(f"expected major.minor.patch version, got {text!r}")
    return tuple(int(x) for x in parts)


def version_at_least(current: tuple[int, int, int], required: tuple[int, int, int]) -> bool:
    return current >= required
