#!/usr/bin/env python3
"""Generate deterministic multi-view feature fixtures for structure tests."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

MOTIF_FRAMES = 32


def motif_a(frames: int = MOTIF_FRAMES) -> np.ndarray:
    phase = np.linspace(0.0, 2.0 * np.pi, frames, endpoint=False)
    return np.column_stack([
        np.sin(phase),
        np.cos(phase),
        0.5 * np.sin(2.0 * phase + 0.3),
        np.linspace(-1.0, 1.0, frames),
    ])


def motif_b(frames: int = MOTIF_FRAMES) -> np.ndarray:
    phase = np.linspace(0.0, 2.0 * np.pi, frames, endpoint=False)
    return np.column_stack([
        np.sin(phase + 1.1),
        np.cos(2.0 * phase),
        np.sign(np.sin(phase + 0.2)),
        np.linspace(1.0, -1.0, frames),
    ])


def stretch(features: np.ndarray, frames: int) -> np.ndarray:
    old = np.linspace(0.0, 1.0, len(features))
    new = np.linspace(0.0, 1.0, frames)
    return np.column_stack([np.interp(new, old, features[:, dim]) for dim in range(features.shape[1])])


def make_views(sequence: np.ndarray) -> dict[str, np.ndarray]:
    """Synthetic views share structure but intentionally differ in representation."""
    return {
        "mfcc": sequence,
        "chroma": np.column_stack([sequence[:, 0], sequence[:, 1], sequence[:, 0] * sequence[:, 1]]),
        "rhythm": np.column_stack([
            np.abs(np.gradient(sequence[:, 0])),
            np.abs(np.gradient(sequence[:, 3])),
        ]),
    }


def fixture_arrays() -> dict[str, dict[str, np.ndarray]]:
    a = motif_a()
    b = motif_b()
    aaaa = np.vstack([a, a, a, a])
    abab = np.vstack([a, b, a, b])
    stretched = np.vstack([a, stretch(a, 40), a])
    timbre = a.copy()
    timbre[:, 0] *= 0.25
    timbre[:, 1] *= 1.8
    timbre[:, 2] += 0.35 * timbre[:, 3]
    timbre_change = np.vstack([a, timbre, a])
    return {
        "s1-aaaa": make_views(aaaa),
        "s2-abab": make_views(abab),
        "s3-time-stretch": make_views(stretched),
        "s4-timbre-change": make_views(timbre_change),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=Path("tests/fixtures/generated/structure"))
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, object] = {
        "motif_frames": MOTIF_FRAMES,
        "fixtures": {
            "s1-aaaa": {"expected_period_frames": MOTIF_FRAMES, "layout": "A-A-A-A"},
            "s2-abab": {"expected_period_frames": MOTIF_FRAMES * 2, "layout": "A-B-A-B"},
            "s3-time-stretch": {
                "layout": "A-A(stretched)-A",
                "cycle_lengths_frames": [MOTIF_FRAMES, 40, MOTIF_FRAMES],
            },
            "s4-timbre-change": {
                "layout": "A-A(timbre changed)-A",
                "cycle_lengths_frames": [MOTIF_FRAMES] * 3,
            },
        },
    }
    for name, views in fixture_arrays().items():
        np.savez_compressed(args.out / f"{name}.npz", **views)
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
