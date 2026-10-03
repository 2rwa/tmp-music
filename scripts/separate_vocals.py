#!/usr/bin/env python3
"""Separate vocals/accompaniment with Demucs and validate the resulting stems."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import librosa
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common.separation import separation_diagnostics


def load_audio(path: Path, sample_rate: int) -> np.ndarray:
    y, _ = librosa.load(path, sr=sample_rate, mono=False)
    x = np.asarray(y, dtype=np.float64)
    if x.ndim == 1:
        x = x[np.newaxis, :]
    return x


def find_single(root: Path, name: str) -> Path:
    matches = list(root.rglob(name))
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one {name}, found {len(matches)} below {root}")
    return matches[0]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("audio", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--model", default="htdemucs")
    p.add_argument("--device", default="cpu")
    p.add_argument("--diagnostic-sr", type=int, default=44100)
    args = p.parse_args()

    source = args.audio.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="tmp-music-demucs-") as td:
        work = Path(td)
        command = [
            sys.executable,
            "-m",
            "demucs",
            "-n",
            args.model,
            "--two-stems",
            "vocals",
            "-d",
            args.device,
            "--out",
            str(work),
            str(source),
        ]
        subprocess.run(command, check=True)
        vocal_src = find_single(work, "vocals.wav")
        accompaniment_src = find_single(work, "no_vocals.wav")
        shutil.copy2(vocal_src, out / "vocals.wav")
        shutil.copy2(accompaniment_src, out / "accompaniment.wav")

    source_audio = load_audio(source, args.diagnostic_sr)
    vocals = load_audio(out / "vocals.wav", args.diagnostic_sr)
    accompaniment = load_audio(out / "accompaniment.wav", args.diagnostic_sr)
    diagnostics = separation_diagnostics(source_audio, vocals, accompaniment, args.diagnostic_sr)
    diagnostics["demucs_model"] = args.model
    diagnostics["device"] = args.device
    diagnostics["source"] = diagnostics["source"] | {"path": str(source)}
    diagnostics["vocals"] = diagnostics["vocals"] | {"path": str(out / "vocals.wav")}
    diagnostics["accompaniment"] = diagnostics["accompaniment"] | {"path": str(out / "accompaniment.wav")}

    (out / "diagnostics.json").write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    if not diagnostics["valid"]:
        print(json.dumps(diagnostics, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2

    print(json.dumps(diagnostics, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
