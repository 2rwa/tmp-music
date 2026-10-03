#!/usr/bin/env python3
"""Generate deterministic mono WAV pitch fixtures without heavy dependencies."""
from __future__ import annotations

import argparse
import json
import math
import struct
import wave
from pathlib import Path

SR = 16000
AMPLITUDE = 0.35


def write_wav(path: Path, samples: list[float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = b"".join(struct.pack("<h", max(-32768, min(32767, round(x * 32767)))) for x in samples)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm)


def sine(freq: float, seconds: float) -> list[float]:
    n = round(seconds * SR)
    return [AMPLITUDE * math.sin(2 * math.pi * freq * i / SR) for i in range(n)]


def chirp(start_hz: float, end_hz: float, seconds: float) -> list[float]:
    n = round(seconds * SR)
    phase = 0.0
    out = []
    for i in range(n):
        frac = i / max(1, n - 1)
        freq = start_hz + (end_hz - start_hz) * frac
        phase += 2 * math.pi * freq / SR
        out.append(AMPLITUDE * math.sin(phase))
    return out


def vibrato(center_hz: float, rate_hz: float, extent_cents: float, seconds: float) -> list[float]:
    n = round(seconds * SR)
    phase = 0.0
    out = []
    for i in range(n):
        t = i / SR
        cents = extent_cents * math.sin(2 * math.pi * rate_hz * t)
        freq = center_hz * 2 ** (cents / 1200)
        phase += 2 * math.pi * freq / SR
        out.append(AMPLITUDE * math.sin(phase))
    return out


def edo_scale(steps: int, divisions: int, root_hz: float = 220.0, note_s: float = 0.25) -> list[float]:
    out: list[float] = []
    for step in range(steps):
        out.extend(sine(root_hz * 2 ** (step / divisions), note_s))
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=Path("tests/fixtures/generated/pitch"))
    args = p.parse_args()
    fixtures = {
        "p1-a4-440.wav": (sine(440.0, 2.0), {"kind": "stable", "frequency_hz": 440.0, "cents_from_a4": 0.0}),
        "p2-a4-plus25c.wav": (sine(440.0 * 2 ** (25 / 1200), 2.0), {"kind": "stable", "frequency_hz": 440.0 * 2 ** (25 / 1200), "cents_from_a4": 25.0}),
        "p3-glissando.wav": (chirp(220.0, 440.0, 2.0), {"kind": "glissando", "start_hz": 220.0, "end_hz": 440.0}),
        "p4-vibrato.wav": (vibrato(440.0, 6.0, 30.0, 2.0), {"kind": "vibrato", "center_hz": 440.0, "rate_hz": 6.0, "extent_cents": 30.0}),
        "p5-19edo-scale.wav": (edo_scale(20, 19), {"kind": "edo_scale", "divisions": 19, "root_hz": 220.0, "steps": 20}),
    }
    manifest = {"sample_rate_hz": SR, "fixtures": {}}
    for name, (samples, meta) in fixtures.items():
        write_wav(args.out / name, samples)
        manifest["fixtures"][name] = meta | {"duration_s": len(samples) / SR}
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
