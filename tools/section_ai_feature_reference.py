#!/usr/bin/env python3
import json
import math
import os
import sys
import types
from pathlib import Path

import numpy as np

UPSTREAM = Path(os.environ.get("ALLIN1_SOURCE_DIR", "upstream-allin1")).resolve()
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "section-ai-probe/feature-reference")
OUT.mkdir(parents=True, exist_ok=True)

src = UPSTREAM / "src" / "allin1_infer"
root = types.ModuleType("allin1_infer")
root.__path__ = [str(src)]
root.__package__ = "allin1_infer"
sys.modules["allin1_infer"] = root

from allin1_infer.spectrogram import compute_spectrogram_from_stem_arrays, STEM_NAMES

SR = 44100
SECONDS = 2.0
SAMPLES = int(SR * SECONDS)

def stereo_for(name: str) -> np.ndarray:
    t = np.arange(SAMPLES, dtype=np.float64) / SR
    cfg = {
        "bass": (82.41, 0.31, 1.2),
        "drums": (913.0, 0.19, 4.0),
        "other": (329.63, 0.22, 0.7),
        "vocals": (220.0, 0.27, 2.1),
    }[name]
    freq, amp, trem = cfg
    envelope = 0.82 + 0.18 * np.sin(2 * np.pi * trem * t)
    left = amp * envelope * np.sin(2 * np.pi * freq * t)
    right = amp * envelope * np.sin(2 * np.pi * (freq * 1.003) * t + 0.17)
    if name == "drums":
        click_phase = np.mod(t, 0.25)
        click = np.exp(-click_phase / 0.018) * np.sin(2 * np.pi * 1400 * click_phase)
        left += 0.22 * click
        right += 0.18 * click
    return np.stack([left, right]).astype(np.float32)

def quantize_like_allin1(stereo: np.ndarray) -> np.ndarray:
    peak = float(np.max(np.abs(stereo)))
    stereo = stereo / max(1.01 * peak, 1.0)
    q = np.rint(np.clip(stereo, -1.0, 1.0) * 32768.0)
    q = np.clip(q, -32768, 32767).astype(np.int16)
    return np.mean(q.T, axis=-1).astype(np.int16)

stems = {name: quantize_like_allin1(stereo_for(name)) for name in STEM_NAMES}
spec = compute_spectrogram_from_stem_arrays(stems, SR).astype(np.float32)
(OUT / "reference.f32").write_bytes(spec.tobytes(order="C"))
meta = {
    "shape": list(spec.shape),
    "dtype": "float32",
    "sample_rate": SR,
    "seconds": SECONDS,
    "stem_order": STEM_NAMES,
    "min": float(spec.min()),
    "max": float(spec.max()),
    "mean": float(spec.mean()),
    "selected": {
        "0,0,0": float(spec[0,0,0]),
        "0,50,20": float(spec[0,50,20]),
        "1,100,40": float(spec[1,100,40]),
        "2,150,60": float(spec[2,150,60]),
        "3,199,80": float(spec[3,199,80]),
    },
}
(OUT / "reference.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
print(json.dumps(meta, indent=2))
