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


_PRAAT_RESULT_RE = re.compile(r"CPPS=([^\t\r\n]+)\tHNR=([^\t\r\n]+)")
_PRAAT_FORMANTS_RE = re.compile(r"\tF1=([^\t\r\n]+)\tF2=([^\t\r\n]+)\tF3=([^\t\r\n]+)")
_PRAAT_VERSION_RE = re.compile(r"Praat\s+(\d+)\.(\d+)\.(\d+)")


def parse_praat_cpps_hnr(text: str) -> tuple[float, float]:
    match = _PRAAT_RESULT_RE.search(text)
    if not match:
        raise ValueError(f"unparseable Praat CPPS/HNR output: {text!r}")
    return float(match.group(1)), float(match.group(2))



def parse_praat_voice_measurements(text: str) -> dict[str, float]:
    cpps, hnr = parse_praat_cpps_hnr(text)
    formants = _PRAAT_FORMANTS_RE.search(text)
    if not formants:
        raise ValueError(f"unparseable Praat formant output: {text!r}")
    return {
        "praat_cpps_db": cpps,
        "praat_hnr_cc_db": hnr,
        "praat_f1_hz": float(formants.group(1)),
        "praat_f2_hz": float(formants.group(2)),
        "praat_f3_hz": float(formants.group(3)),
    }

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


def _as_finite_float(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def detect_pitch_movement_events(
    rows: Iterable[dict[str, object]],
    *,
    window_s: float = 0.30,
    min_abs_slope_cents_per_s: float = 200.0,
    min_total_change_cents: float = 60.0,
    min_r2: float = 0.80,
    max_gap_s: float = 0.05,
) -> list[dict[str, object]]:
    """Detect sustained monotonic F0 movement candidates from M2 consensus frames.

    The detector intentionally reports candidates rather than asserting that a
    movement is a sung glissando. A window must be well approximated by a line
    in cents, exceed both slope and total-change thresholds, and remain
    contiguous in time. This rejects most periodic vibrato excursions.
    """
    parsed: list[tuple[float, float, float | None]] = []
    for row in rows:
        t = _as_finite_float(row.get("time_s"))
        f0 = _as_finite_float(row.get("selected_f0_hz"))
        conf = _as_finite_float(row.get("selected_confidence"))
        if t is not None and f0 is not None and f0 > 0:
            parsed.append((t, f0, conf))
    if len(parsed) < 5:
        return []
    parsed.sort(key=lambda x: x[0])
    times = np.asarray([x[0] for x in parsed], dtype=float)
    cents = 1200.0 * np.log2(np.asarray([x[1] for x in parsed], dtype=float) / 440.0)
    confidence = np.asarray(
        [x[2] if x[2] is not None else np.nan for x in parsed], dtype=float
    )

    windows: list[tuple[float, float, int]] = []
    for i in range(len(times)):
        j = int(np.searchsorted(times, times[i] + window_s, side="left"))
        if j >= len(times):
            break
        segment_times = times[i : j + 1]
        if len(segment_times) < 5 or float(np.max(np.diff(segment_times))) > max_gap_s:
            continue
        segment_cents = cents[i : j + 1]
        slope, intercept = np.polyfit(segment_times, segment_cents, 1)
        fitted = slope * segment_times + intercept
        residual = float(np.sum((segment_cents - fitted) ** 2))
        centered = float(np.sum((segment_cents - np.mean(segment_cents)) ** 2))
        r2 = 1.0 - residual / centered if centered > 1e-12 else 0.0
        duration = float(segment_times[-1] - segment_times[0])
        total_change = float(slope * duration)
        if (
            abs(float(slope)) >= min_abs_slope_cents_per_s
            and abs(total_change) >= min_total_change_cents
            and r2 >= min_r2
        ):
            windows.append(
                (float(segment_times[0]), float(segment_times[-1]), 1 if slope > 0 else -1)
            )

    if not windows:
        return []

    merged: list[list[float | int]] = []
    for start, end, direction in windows:
        if (
            merged
            and int(merged[-1][2]) == direction
            and start <= float(merged[-1][1]) + max_gap_s
        ):
            merged[-1][1] = max(float(merged[-1][1]), end)
        else:
            merged.append([start, end, direction])

    events: list[dict[str, object]] = []
    for start, end, direction in merged:
        mask = (times >= float(start)) & (times <= float(end))
        segment_times = times[mask]
        segment_cents = cents[mask]
        if len(segment_times) < 5:
            continue
        slope, intercept = np.polyfit(segment_times, segment_cents, 1)
        fitted = slope * segment_times + intercept
        residual = float(np.sum((segment_cents - fitted) ** 2))
        centered = float(np.sum((segment_cents - np.mean(segment_cents)) ** 2))
        r2 = 1.0 - residual / centered if centered > 1e-12 else 0.0
        duration = float(segment_times[-1] - segment_times[0])
        total_change = float(slope * duration)
        if (
            abs(float(slope)) < min_abs_slope_cents_per_s
            or abs(total_change) < min_total_change_cents
            or r2 < min_r2
        ):
            continue
        conf = confidence[mask]
        finite_conf = conf[np.isfinite(conf)]
        events.append({
            "start_s": float(segment_times[0]),
            "end_s": float(segment_times[-1]),
            "duration_s": duration,
            "direction": "ascending" if int(direction) > 0 else "descending",
            "slope_cents_per_s": float(slope),
            "total_change_cents": total_change,
            "linear_fit_r2": float(r2),
            "median_confidence": float(np.median(finite_conf)) if finite_conf.size else None,
            "interpretation": "glissando_candidate",
        })
    return events


def detect_register_transition_candidates(
    segments: Iterable[dict[str, object]],
    *,
    max_gap_s: float = 1.0,
    thresholds: dict[str, float] | None = None,
) -> list[dict[str, object]]:
    """Return multi-feature register-transition candidates between stable segments."""
    limits = {
        "f0_cents": 180.0,
        "praat_cpps_db": 3.0,
        "praat_hnr_cc_db": 3.0,
        "autocorrelation_hnr_db": 3.0,
        "spectral_tilt_db_per_octave": 2.0,
        "rms_dbfs": 4.0,
        "praat_f1_hz": 150.0,
        "praat_f2_hz": 250.0,
        "praat_f3_hz": 300.0,
        "vibrato_extent_cents": 50.0,
    }
    if thresholds:
        limits.update({k: float(v) for k, v in thresholds.items()})

    ordered = sorted(
        list(segments),
        key=lambda row: float(row.get("start_s", 0.0)),
    )
    candidates: list[dict[str, object]] = []
    for before, after in zip(ordered, ordered[1:]):
        before_end = _as_finite_float(before.get("end_s"))
        after_start = _as_finite_float(after.get("start_s"))
        if before_end is None or after_start is None:
            continue
        gap_s = after_start - before_end
        if gap_s < -1e-6 or gap_s > max_gap_s:
            continue

        deltas: dict[str, float | None] = {}
        b_f0 = _as_finite_float(before.get("median_f0_hz"))
        a_f0 = _as_finite_float(after.get("median_f0_hz"))
        deltas["f0_cents"] = (
            1200.0 * math.log2(a_f0 / b_f0)
            if b_f0 is not None and a_f0 is not None and b_f0 > 0 and a_f0 > 0
            else None
        )
        metric_map = {
            "praat_cpps_db": "praat_cpps_db",
            "praat_hnr_cc_db": "praat_hnr_cc_db",
            "autocorrelation_hnr_db": "median_autocorrelation_hnr_db",
            "spectral_tilt_db_per_octave": "median_spectral_tilt_db_per_octave",
            "rms_dbfs": "median_rms_dbfs",
            "praat_f1_hz": "praat_f1_hz",
            "praat_f2_hz": "praat_f2_hz",
            "praat_f3_hz": "praat_f3_hz",
            "vibrato_extent_cents": "vibrato_extent_cents_p95_p05",
        }
        for delta_name, field in metric_map.items():
            b = _as_finite_float(before.get(field))
            a = _as_finite_float(after.get(field))
            deltas[delta_name] = a - b if a is not None and b is not None else None

        changed = [
            name for name, value in deltas.items()
            if value is not None and abs(value) >= limits[name]
        ]
        # A register-transition candidate requires a pitch discontinuity plus
        # at least two independent laryngeal/voice-quality changes. Formants,
        # intensity and vibrato remain supporting context because phoneme changes
        # can move them substantially without a register change.
        voice_quality_evidence = {
            "praat_cpps_db",
            "praat_hnr_cc_db",
            "autocorrelation_hnr_db",
            "spectral_tilt_db_per_octave",
        }
        changed_voice_quality = [name for name in changed if name in voice_quality_evidence]
        if "f0_cents" not in changed or len(changed_voice_quality) < 2:
            continue
        candidates.append({
            "time_s": float((before_end + after_start) / 2.0),
            "gap_s": float(gap_s),
            "before_stable_target_index": before.get("stable_target_index"),
            "after_stable_target_index": after.get("stable_target_index"),
            "changed_features": changed,
            "changed_feature_count": len(changed),
            "deltas": deltas,
            "before": {
                "start_s": before.get("start_s"),
                "end_s": before.get("end_s"),
                "median_f0_hz": before.get("median_f0_hz"),
            },
            "after": {
                "start_s": after.get("start_s"),
                "end_s": after.get("end_s"),
                "median_f0_hz": after.get("median_f0_hz"),
            },
            "interpretation": "register_transition_candidate",
        })
    return candidates
