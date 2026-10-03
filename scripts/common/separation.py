"""Pure numeric diagnostics for source-separation outputs."""
from __future__ import annotations

import numpy as np


def _as_channels(samples: np.ndarray) -> np.ndarray:
    x = np.asarray(samples, dtype=np.float64)
    if x.ndim == 1:
        x = x[np.newaxis, :]
    if x.ndim != 2:
        raise ValueError(f"audio must be 1-D or 2-D, got shape {x.shape}")
    return x


def signal_stats(samples: np.ndarray, sample_rate: int) -> dict[str, float | int | bool]:
    x = _as_channels(samples)
    finite = bool(np.isfinite(x).all())
    rms = float(np.sqrt(np.mean(x * x))) if x.size else 0.0
    peak = float(np.max(np.abs(x))) if x.size else 0.0
    clipping = float(np.mean(np.abs(x) >= 0.999)) if x.size else 0.0
    return {
        "channels": int(x.shape[0]),
        "samples": int(x.shape[1]),
        "duration_s": float(x.shape[1] / sample_rate),
        "rms": rms,
        "peak": peak,
        "clipping_fraction": clipping,
        "finite": finite,
    }


def separation_diagnostics(
    source: np.ndarray,
    vocals: np.ndarray,
    accompaniment: np.ndarray,
    sample_rate: int,
) -> dict[str, object]:
    src = _as_channels(source)
    voc = _as_channels(vocals)
    acc = _as_channels(accompaniment)

    channels = min(src.shape[0], voc.shape[0], acc.shape[0])
    samples = min(src.shape[1], voc.shape[1], acc.shape[1])
    if channels < 1 or samples < 1:
        raise ValueError("empty source or stem")

    src = src[:channels, :samples]
    voc = voc[:channels, :samples]
    acc = acc[:channels, :samples]
    residual = src - (voc + acc)

    source_rms = float(np.sqrt(np.mean(src * src)))
    residual_rms = float(np.sqrt(np.mean(residual * residual)))
    ratio = residual_rms / source_rms if source_rms > 0 else None

    source_stats = signal_stats(src, sample_rate)
    vocal_stats = signal_stats(voc, sample_rate)
    accompaniment_stats = signal_stats(acc, sample_rate)
    residual_stats = signal_stats(residual, sample_rate)

    duration_spread = max(
        source_stats["duration_s"],
        vocal_stats["duration_s"],
        accompaniment_stats["duration_s"],
    ) - min(
        source_stats["duration_s"],
        vocal_stats["duration_s"],
        accompaniment_stats["duration_s"],
    )

    warnings: list[str] = []
    if vocal_stats["rms"] <= 1e-7:
        warnings.append("vocal stem is effectively silent")
    if accompaniment_stats["rms"] <= 1e-7:
        warnings.append("accompaniment stem is effectively silent")
    if not (source_stats["finite"] and vocal_stats["finite"] and accompaniment_stats["finite"]):
        warnings.append("non-finite samples detected")
    if duration_spread > 0.1:
        warnings.append(f"duration spread exceeds 0.1 s: {duration_spread:.6f}")

    return {
        "sample_rate_hz": sample_rate,
        "compared_channels": channels,
        "compared_samples": samples,
        "source": source_stats,
        "vocals": vocal_stats,
        "accompaniment": accompaniment_stats,
        "residual": residual_stats,
        "resum_residual_rms_ratio": ratio,
        "duration_spread_s": float(duration_spread),
        "warnings": warnings,
        "valid": not warnings,
    }
