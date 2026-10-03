#!/usr/bin/env python3
"""Run pYIN and optional torchcrepe, then write estimator agreement."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import librosa
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common.pitch import consensus_frames, consensus_summary, hz_to_midi


def write_estimator_csv(path: Path, times: np.ndarray, f0: np.ndarray, confidence: np.ndarray, confidence_name: str) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["time_s", "f0_hz", "midi", "cents_to_nearest_12tet", confidence_name])
        for t, hz, conf in zip(times, f0, confidence):
            if np.isfinite(hz) and hz > 0:
                midi = hz_to_midi(float(hz))
                cents = 100.0 * (midi - round(midi))
                w.writerow([float(t), float(hz), midi, cents, float(conf) if np.isfinite(conf) else ""])
            else:
                w.writerow([float(t), "", "", "", float(conf) if np.isfinite(conf) else ""])


def run_pyin(y: np.ndarray, sr: int, hop: int, fmin: float, fmax: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    f0, voiced, probability = librosa.pyin(y, fmin=fmin, fmax=fmax, sr=sr, hop_length=hop)
    times = np.arange(len(f0), dtype=float) * hop / sr
    if probability is None:
        probability = np.where(voiced, 1.0, 0.0).astype(float)
    return times, np.asarray(f0, dtype=float), np.asarray(probability, dtype=float)


def run_crepe(
    y: np.ndarray,
    sr: int,
    hop: int,
    fmin: float,
    fmax: float,
    model: str,
    device: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    import torch
    import torchcrepe

    audio = torch.tensor(y, dtype=torch.float32, device=device).unsqueeze(0)
    pitch, periodicity = torchcrepe.predict(
        audio,
        sr,
        hop,
        fmin,
        fmax,
        model,
        batch_size=2048,
        device=device,
        return_periodicity=True,
    )
    f0 = pitch.squeeze(0).detach().cpu().numpy().astype(float)
    conf = periodicity.squeeze(0).detach().cpu().numpy().astype(float)
    times = np.arange(len(f0), dtype=float) * hop / sr
    return times, f0, conf


def write_consensus(path: Path, rows: list[dict[str, float | str | None]]) -> None:
    fields = [
        "time_s",
        "pyin_f0_hz",
        "crepe_f0_hz",
        "consensus_f0_hz",
        "disagreement_cents",
        "agreement",
        "pyin_confidence",
        "crepe_periodicity",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in rows:
            w.writerow({k: "" if row.get(k) is None else row.get(k) for k in fields})


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("audio", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--estimators", default="pyin,crepe")
    p.add_argument("--sr", type=int, default=16000)
    p.add_argument("--hop-length", type=int, default=160)
    p.add_argument("--fmin", type=float, default=float(librosa.note_to_hz("C2")))
    p.add_argument("--fmax", type=float, default=float(librosa.note_to_hz("C7")))
    p.add_argument("--crepe-model", choices=("tiny", "full"), default="full")
    p.add_argument("--device", default="cpu")
    p.add_argument("--crepe-periodicity-threshold", type=float, default=0.21)
    p.add_argument("--strong-cents", type=float, default=25.0)
    p.add_argument("--weak-cents", type=float, default=50.0)
    args = p.parse_args()

    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    y, sr = librosa.load(args.audio.resolve(), sr=args.sr, mono=True)
    estimators = {x.strip() for x in args.estimators.split(",") if x.strip()}
    unknown = estimators - {"pyin", "crepe"}
    if unknown:
        raise ValueError(f"unknown estimator(s): {', '.join(sorted(unknown))}")

    result: dict[str, object] = {
        "audio": str(args.audio),
        "sample_rate_hz": sr,
        "hop_length": args.hop_length,
        "fmin_hz": args.fmin,
        "fmax_hz": args.fmax,
        "estimators": sorted(estimators),
    }

    tracks: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    if "pyin" in estimators:
        tracks["pyin"] = run_pyin(y, sr, args.hop_length, args.fmin, args.fmax)
        write_estimator_csv(out / "pyin.csv", *tracks["pyin"], "voiced_probability")
        result["pyin"] = {"frames": len(tracks["pyin"][1]), "voiced_fraction": float(np.mean(np.isfinite(tracks["pyin"][1])))}

    if "crepe" in estimators:
        tracks["crepe"] = run_crepe(y, sr, args.hop_length, args.fmin, args.fmax, args.crepe_model, args.device)
        write_estimator_csv(out / "crepe.csv", *tracks["crepe"], "periodicity")
        result["crepe"] = {
            "model": args.crepe_model,
            "frames": len(tracks["crepe"][1]),
            "periodicity_threshold": args.crepe_periodicity_threshold,
            "reliable_fraction": float(np.mean(tracks["crepe"][2] >= args.crepe_periodicity_threshold)),
        }

    if "pyin" in tracks and "crepe" in tracks:
        n = min(len(tracks["pyin"][1]), len(tracks["crepe"][1]))
        rows = consensus_frames(
            tracks["pyin"][0][:n],
            tracks["pyin"][1][:n],
            tracks["crepe"][1][:n],
            tracks["pyin"][2][:n],
            tracks["crepe"][2][:n],
            crepe_periodicity_threshold=args.crepe_periodicity_threshold,
            strong_cents=args.strong_cents,
            weak_cents=args.weak_cents,
        )
        write_consensus(out / "consensus.csv", rows)
        result["consensus"] = consensus_summary(rows) | {
            "strong_cents": args.strong_cents,
            "weak_cents": args.weak_cents,
        }

    (out / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
