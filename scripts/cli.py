#!/usr/bin/env python3
"""Common entry point for tmp-music analyzers.

The wrapper owns track configuration, source-integrity checks and common
provenance/status files. Existing analyzers remain independently runnable.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common.provenance import (
    build_provenance,
    collect_tool_versions,
    sha256_file,
    write_stage_state,
)

STAGES = (
    "verify",
    "metadata",
    "acoustic",
    "repetition",
    "separate",
    "pitch",
    "targets",
    "tuning",
    "pitch-compare",
    "asr",
    "full",
)


@dataclass(frozen=True)
class Track:
    id: str
    source: Path
    source_rel: str
    expected_sha256: str
    expected_size_bytes: int | None
    language: str
    config: dict[str, Any]


def load_track(track_id: str, config_dir: Path) -> Track:
    path = config_dir / f"{track_id}.yml"
    if not path.is_file():
        available = sorted(p.stem for p in config_dir.glob("*.yml")) if config_dir.is_dir() else []
        suffix = f" Available: {', '.join(available)}" if available else ""
        raise ValueError(f"unknown track: {track_id}.{suffix}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"track config must be an object: {path}")
    required = ("id", "source", "expected_sha256", "language")
    missing = [key for key in required if not data.get(key)]
    if missing:
        raise ValueError(f"track config missing {', '.join(missing)}: {path}")
    if data["id"] != track_id:
        raise ValueError(f"track config id mismatch: requested {track_id}, file says {data['id']}")
    source_rel = str(data["source"])
    return Track(
        id=track_id,
        source=(REPO_ROOT / source_rel).resolve(),
        source_rel=source_rel,
        expected_sha256=str(data["expected_sha256"]).lower(),
        expected_size_bytes=int(data["expected_size_bytes"]) if data.get("expected_size_bytes") is not None else None,
        language=str(data["language"]),
        config=data,
    )


def verify_source(track: Track) -> dict[str, Any]:
    if not track.source.is_file():
        raise FileNotFoundError(f"source audio not found: {track.source_rel}")
    actual_size = track.source.stat().st_size
    actual_sha = sha256_file(track.source)
    if actual_sha != track.expected_sha256:
        raise ValueError(
            f"source SHA-256 mismatch for {track.id}: expected {track.expected_sha256}, got {actual_sha}"
        )
    if track.expected_size_bytes is not None and actual_size != track.expected_size_bytes:
        raise ValueError(
            f"source size mismatch for {track.id}: expected {track.expected_size_bytes}, got {actual_size}"
        )
    return {"sha256": actual_sha, "size_bytes": actual_size, "source": track.source_rel}


def analysis_input(track: Track, source: str) -> str:
    if source == "mix":
        return track.source_rel
    if source == "vocals":
        return str(Path("analysis") / track.id / "stems" / "demucs" / "vocals.wav")
    raise ValueError(f"unknown analysis source: {source}")


def stage_output(track: Track, stage: str, model: str, source: str = "mix") -> Path:
    if stage == "separate":
        return REPO_ROOT / "analysis" / track.id / "stems" / "demucs"
    if stage == "pitch-compare":
        return REPO_ROOT / "analysis" / track.id / "comparisons" / "pitch-mix-vs-vocals"
    if stage in {"pitch", "targets", "tuning"}:
        root = REPO_ROOT / "analysis" / track.id / "measurements" / "pitch" / source
        if stage == "pitch":
            return root
        return root / stage
    suffix = f"asr-{model}" if stage == "asr" else stage
    return REPO_ROOT / "analysis" / track.id / "measurements" / suffix


def _list_outputs(out_dir: Path) -> list[str]:
    return sorted(
        str(p.relative_to(REPO_ROOT))
        for p in out_dir.rglob("*")
        if p.is_file() and p.name not in {"provenance.json", "status.json"}
    )


def stage_command(
    track: Track,
    stage: str,
    model: str,
    source: str = "mix",
    estimators: str | None = None,
) -> tuple[list[str], dict[str, Any], dict[str, Any], list[str]]:
    py = sys.executable
    out = stage_output(track, stage, model, source)
    if stage == "metadata":
        command = [py, "scripts/analyze_audio.py", track.source_rel, "--out", str(out.relative_to(REPO_ROOT)), "--skip-pitch"]
        return command, {"skip_pitch": True}, {}, ["librosa", "numpy", "scipy", "matplotlib", "mutagen"]
    if stage == "acoustic":
        command = [py, "scripts/analyze_audio.py", track.source_rel, "--out", str(out.relative_to(REPO_ROOT))]
        return command, {"skip_pitch": False}, {}, ["librosa", "numpy", "scipy", "matplotlib", "mutagen"]
    if stage == "repetition":
        rep = track.config.get("analysis", {}).get("repetition", {})
        command = [py, "scripts/repetition_analysis.py", track.source_rel, "--out", str(out.relative_to(REPO_ROOT))]
        if rep.get("template_start_s") is not None:
            command += ["--template-start", str(rep["template_start_s"])]
        if rep.get("template_end_s") is not None:
            command += ["--template-end", str(rep["template_end_s"])]
        return command, {"template": rep}, {}, ["librosa", "numpy", "scipy"]
    if stage == "separate":
        separation = track.config.get("analysis", {}).get("separation", {})
        demucs_model = str(separation.get("model", "htdemucs"))
        device = str(separation.get("device", "cpu"))
        command = [
            py,
            "scripts/separate_vocals.py",
            track.source_rel,
            "--out",
            str(out.relative_to(REPO_ROOT)),
            "--model",
            demucs_model,
            "--device",
            device,
        ]
        return command, {"device": device}, {"demucs": demucs_model}, ["demucs", "librosa", "numpy", "soundfile"]
    if stage == "pitch":
        pitch = track.config.get("analysis", {}).get("pitch", {})
        input_path = analysis_input(track, source)
        selected_estimators = estimators or str(pitch.get("estimators", "pyin,crepe"))
        crepe_model = str(pitch.get("crepe_model", "full"))
        command = [
            py,
            "scripts/analyze_pitch.py",
            input_path,
            "--out",
            str(out.relative_to(REPO_ROOT)),
            "--estimators",
            selected_estimators,
            "--sr",
            str(pitch.get("sample_rate_hz", 16000)),
            "--hop-length",
            str(pitch.get("hop_length", 160)),
            "--fmin",
            str(pitch.get("fmin_hz", 65.40639132514966)),
            "--fmax",
            str(pitch.get("fmax_hz", 2006.0)),
            "--crepe-model",
            crepe_model,
            "--device",
            str(pitch.get("device", "cpu")),
            "--crepe-periodicity-threshold",
            str(pitch.get("crepe_periodicity_threshold", 0.21)),
            "--pyin-fallback-confidence",
            str(pitch.get("pyin_fallback_confidence", 0.80)),
            "--strong-cents",
            str(pitch.get("consensus_strong_cents", 25.0)),
            "--weak-cents",
            str(pitch.get("consensus_weak_cents", 50.0)),
        ]
        parameters = {
            "input": input_path,
            "source": source,
            "estimators": selected_estimators,
            "fmin_hz": pitch.get("fmin_hz", 65.40639132514966),
            "fmax_hz": pitch.get("fmax_hz", 2006.0),
            "crepe_periodicity_threshold": pitch.get("crepe_periodicity_threshold", 0.21),
            "pyin_fallback_confidence": pitch.get("pyin_fallback_confidence", 0.80),
        }
        models = {"torchcrepe": crepe_model} if "crepe" in selected_estimators.split(",") else {}
        return command, parameters, models, ["librosa", "numpy", "torchcrepe", "torch", "torchaudio"]
    if stage == "targets":
        target_cfg = track.config.get("analysis", {}).get("pitch_targets", {})
        pitch_root = stage_output(track, "pitch", model, source)
        input_path = pitch_root / "consensus.csv"
        command = [
            py,
            "scripts/detect_pitch_targets.py",
            str(input_path.relative_to(REPO_ROOT)),
            "--out",
            str(out.relative_to(REPO_ROOT)),
            "--window-s",
            str(target_cfg.get("window_s", 0.5)),
            "--max-slope",
            str(target_cfg.get("max_slope_cents_per_s", 100.0)),
            "--max-residual-std",
            str(target_cfg.get("max_detrended_std_cents", 40.0)),
            "--min-duration",
            str(target_cfg.get("min_duration_s", 0.15)),
            "--min-confidence",
            str(target_cfg.get("min_confidence", 0.5)),
        ]
        return command, {"input": str(input_path.relative_to(REPO_ROOT)), "source": source, **target_cfg}, {}, ["numpy"]
    if stage == "tuning":
        tuning_cfg = track.config.get("analysis", {}).get("tuning", {})
        targets_root = stage_output(track, "targets", model, source)
        input_path = targets_root / "stable-notes.csv"
        edos = tuning_cfg.get("edos", [12, 19, 24, 31])
        command = [
            py,
            "scripts/analyze_tuning.py",
            str(input_path.relative_to(REPO_ROOT)),
            "--out",
            str(out.relative_to(REPO_ROOT)),
            "--edos",
            ",".join(str(x) for x in edos),
        ]
        return command, {"input": str(input_path.relative_to(REPO_ROOT)), "source": source, "edos": edos}, {}, ["numpy"]
    if stage == "pitch-compare":
        mix_root = REPO_ROOT / "analysis" / track.id / "measurements" / "pitch" / "mix"
        vocal_root = REPO_ROOT / "analysis" / track.id / "measurements" / "pitch" / "vocals"
        command = [
            py,
            "scripts/compare_pitch_sources.py",
            "--track",
            track.id,
            "--mix",
            str(mix_root.relative_to(REPO_ROOT)),
            "--vocals",
            str(vocal_root.relative_to(REPO_ROOT)),
            "--out",
            str(out.relative_to(REPO_ROOT)),
        ]
        return command, {
            "mix": str(mix_root.relative_to(REPO_ROOT)),
            "vocals": str(vocal_root.relative_to(REPO_ROOT)),
        }, {}, []
    if stage == "asr":
        asr = track.config.get("analysis", {}).get("asr", {})
        modes = asr.get("modes", ["auto", track.language])
        command = [
            py,
            "scripts/asr_compare.py",
            track.source_rel,
            "--out",
            str(out.relative_to(REPO_ROOT)),
            "--model",
            model,
            "--modes",
            ",".join(str(x) for x in modes),
            "--device",
            "cpu",
            "--compute-type",
            "int8",
        ]
        return command, {"modes": modes, "device": "cpu", "compute_type": "int8"}, {"faster-whisper": model}, ["faster-whisper", "av", "mutagen"]
    raise ValueError(f"no analyzer mapping for stage: {stage}")


def run_stage(
    track: Track,
    stage: str,
    source_sha: str,
    model: str,
    dry_run: bool,
    source: str = "mix",
    estimators: str | None = None,
) -> dict[str, Any]:
    command, parameters, models, packages = stage_command(track, stage, model, source, estimators)
    out = stage_output(track, stage, model, source)
    plan = {
        "stage": stage,
        "source": source,
        "out": str(out.relative_to(REPO_ROOT)),
        "command": command,
        "parameters": parameters,
        "models": models,
    }
    if dry_run:
        return plan

    out.mkdir(parents=True, exist_ok=True)
    provenance = build_provenance(
        source_path=track.source_rel,
        source_sha256=source_sha,
        analyzer=stage,
        parameters=parameters,
        models=models,
        tool_versions=collect_tool_versions(packages),
    )
    write_stage_state(out, provenance=provenance, status="running", started_from=source)
    result = subprocess.run(command, cwd=REPO_ROOT, check=False)
    outputs = _list_outputs(out)
    if result.returncode != 0:
        write_stage_state(
            out,
            provenance=provenance,
            status="failed",
            warnings=[f"analyzer exited with code {result.returncode}"],
            started_from=source,
            outputs=outputs,
            return_code=result.returncode,
        )
        raise subprocess.CalledProcessError(result.returncode, command)
    if not outputs:
        write_stage_state(
            out,
            provenance=provenance,
            status="failed",
            warnings=["analyzer exited successfully but produced no outputs"],
            started_from=source,
            outputs=[],
            return_code=result.returncode,
        )
        raise RuntimeError(f"{stage} produced no outputs")
    write_stage_state(
        out,
        provenance=provenance,
        status="success",
        started_from=source,
        outputs=outputs,
        return_code=result.returncode,
    )
    return plan | {"outputs": outputs}


def planned_stages(track: Track, requested: str) -> list[str]:
    if requested != "full":
        return [] if requested == "verify" else [requested]
    stages = ["acoustic"]
    if track.config.get("analysis", {}).get("repetitions", False):
        stages.append("repetition")
    stages.append("asr")
    return stages


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=STAGES)
    parser.add_argument("--track", required=True)
    parser.add_argument("--model", default=None, help="ASR model override")
    parser.add_argument("--source", choices=("mix", "vocals", "mix-vocals"), default="mix")
    parser.add_argument("--estimators", default=None, help="Pitch estimator override, e.g. pyin or pyin,crepe")
    parser.add_argument("--dry-run", action="store_true", help="verify source and print analyzer commands without running them")
    parser.add_argument("--config-dir", type=Path, default=REPO_ROOT / "config" / "tracks")
    args = parser.parse_args()

    try:
        track = load_track(args.track, args.config_dir.resolve())
        integrity = verify_source(track)
        default_model = track.config.get("analysis", {}).get("asr", {}).get("default_model", "small")
        model = args.model or default_model
        stages = planned_stages(track, args.stage)
        result: dict[str, Any] = {
            "track": track.id,
            "integrity": integrity,
            "requested_stage": args.stage,
            "source": args.source,
            "dry_run": args.dry_run,
            "stages": [],
        }
        for stage in stages:
            result["stages"].append(
                run_stage(
                    track,
                    stage,
                    integrity["sha256"],
                    model,
                    args.dry_run,
                    source=args.source,
                    estimators=args.estimators,
                )
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (FileNotFoundError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
