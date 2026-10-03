#!/usr/bin/env python3
"""Generate deterministic click-track fixtures without audio dependencies."""
from __future__ import annotations

import argparse
import json
import math
import struct
import wave
from pathlib import Path

SR = 16000
DURATION = 12.0


def click_track(times: list[float]) -> list[float]:
    n = round(DURATION * SR)
    samples = [0.0] * n
    click_len = round(0.02 * SR)
    for t in times:
        start = round(t * SR)
        for i in range(click_len):
            j = start + i
            if j >= n:
                break
            samples[j] += 0.65 * math.exp(-i / (0.004 * SR)) * math.sin(2 * math.pi * 1800 * i / SR)
    return [max(-1.0, min(1.0, x)) for x in samples]


def write_wav(path: Path, samples: list[float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = b"".join(struct.pack("<h", round(x * 32767)) for x in samples)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm)


def regular_times(bpm: float, subdivision: int = 1) -> list[float]:
    step = 60.0 / bpm / subdivision
    count = int(DURATION / step)
    return [i * step for i in range(count)]


def drift_times(start_bpm: float, end_bpm: float) -> list[float]:
    times = []
    t = 0.0
    while t < DURATION:
        frac = t / DURATION
        bpm = start_bpm + (end_bpm - start_bpm) * frac
        times.append(t)
        t += 60.0 / bpm
    return times


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=Path("tests/fixtures/generated/rhythm"))
    args = p.parse_args()
    fixtures = {
        "r1-100bpm.wav": (regular_times(100), {"kind": "clicks", "bpm": 100.0}),
        "r2-100bpm-eighths.wav": (regular_times(100, 2), {"kind": "eighth_notes", "tactus_bpm": 100.0, "subdivision_bpm": 200.0}),
        "r3-drift-90-to-110.wav": (drift_times(90, 110), {"kind": "tempo_drift", "start_bpm": 90.0, "end_bpm": 110.0}),
    }
    manifest = {"sample_rate_hz": SR, "duration_s": DURATION, "fixtures": {}}
    for name, (times, meta) in fixtures.items():
        write_wav(args.out / name, click_track(times))
        manifest["fixtures"][name] = meta | {"click_times_s": times}
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
