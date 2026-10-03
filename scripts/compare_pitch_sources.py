#!/usr/bin/env python3
"""Compare mix and vocal-only pitch measurements without interpreting musical intent."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def edo_map(tuning: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {int(row["edo"]): row for row in tuning.get("models", [])}


def summarize_source(root: Path) -> dict[str, Any]:
    pitch = load_json(root / "summary.json")
    targets = load_json(root / "targets" / "summary.json")
    tuning = load_json(root / "tuning" / "tuning-models.json")
    consensus = pitch.get("consensus", {})
    crepe = pitch.get("crepe", {})
    pyin = pitch.get("pyin", {})
    periodicity = crepe.get("periodicity", {})

    return {
        "pyin_voiced_fraction": pyin.get("voiced_fraction"),
        "crepe_reliable_fraction": crepe.get("reliable_fraction"),
        "crepe_periodicity_median": periodicity.get("median"),
        "consensus_coverage": consensus.get("consensus_coverage"),
        "selected_coverage": consensus.get("selected_coverage", consensus.get("consensus_coverage")),
        "selected_source_counts": consensus.get("selected_source_counts", {}),
        "stable_target_count": targets.get("stable_target_count", 0),
        "stable_duration_s": targets.get("stable_duration_s", 0.0),
        "stable_measurement_status": targets.get(
            "measurement_status",
            "ok" if targets.get("stable_target_count", 0) else "insufficient_stable_targets",
        ),
        "stable_segment_evidence_counts": targets.get("stable_segment_evidence_counts", {}),
        "tuning_measurement_status": tuning.get(
            "measurement_status",
            "ok" if tuning.get("target_count", 0) else "insufficient_stable_targets",
        ),
        "tuning_target_count": tuning.get("target_count", 0),
        "tuning_models": tuning.get("models", []),
    }


def numeric_delta(vocal: Any, mix: Any) -> float | None:
    if isinstance(vocal, (int, float)) and isinstance(mix, (int, float)):
        return float(vocal) - float(mix)
    return None


def compare_sources(mix: dict[str, Any], vocals: dict[str, Any]) -> dict[str, Any]:
    scalar_keys = [
        "pyin_voiced_fraction",
        "crepe_reliable_fraction",
        "crepe_periodicity_median",
        "consensus_coverage",
        "selected_coverage",
        "stable_target_count",
        "stable_duration_s",
        "tuning_target_count",
    ]
    deltas = {key: numeric_delta(vocals.get(key), mix.get(key)) for key in scalar_keys}

    mix_edos = edo_map({"models": mix.get("tuning_models", [])})
    vocal_edos = edo_map({"models": vocals.get("tuning_models", [])})
    edo_rows = []
    for edo in sorted(set(mix_edos) | set(vocal_edos)):
        m = mix_edos.get(edo, {})
        v = vocal_edos.get(edo, {})
        mix_rmse = m.get("weighted_rmse_cents")
        vocal_rmse = v.get("weighted_rmse_cents")
        edo_rows.append({
            "edo": edo,
            "mix_weighted_rmse_cents": mix_rmse,
            "vocal_weighted_rmse_cents": vocal_rmse,
            "vocal_minus_mix_rmse_cents": numeric_delta(vocal_rmse, mix_rmse),
            "mix_global_offset_cents": m.get("estimated_global_offset_cents"),
            "vocal_global_offset_cents": v.get("estimated_global_offset_cents"),
        })

    return {
        "mix": mix,
        "vocals": vocals,
        "vocals_minus_mix": deltas,
        "tuning_model_comparison": edo_rows,
        "measurement_note": (
            "Differences between mix and vocal-only outputs can expose accompaniment interference "
            "or separation effects. They do not by themselves identify a scale, culture, vocal style, "
            "or compositional intent."
        ),
    }


def fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def render_markdown(track: str, result: dict[str, Any]) -> str:
    mix = result["mix"]
    vocals = result["vocals"]
    delta = result["vocals_minus_mix"]
    rows = [
        ("pYIN voiced fraction", "pyin_voiced_fraction"),
        ("CREPE reliable fraction", "crepe_reliable_fraction"),
        ("CREPE periodicity median", "crepe_periodicity_median"),
        ("strict consensus coverage", "consensus_coverage"),
        ("selected F0 coverage", "selected_coverage"),
        ("stable target count", "stable_target_count"),
        ("stable duration (s)", "stable_duration_s"),
    ]
    lines = [
        f"# Pitch mix vs vocal comparison — {track}",
        "",
        "## Measurement summary",
        "",
        "| Metric | Mix | Vocals | Vocals - mix |",
        "| --- | ---: | ---: | ---: |",
    ]
    for label, key in rows:
        lines.append(f"| {label} | {fmt(mix.get(key))} | {fmt(vocals.get(key))} | {fmt(delta.get(key))} |")

    lines += [
        "",
        "## Stable-target evidence",
        "",
        f"- Mix status: `{mix.get('stable_measurement_status')}`",
        f"- Vocal status: `{vocals.get('stable_measurement_status')}`",
        f"- Mix evidence counts: `{json.dumps(mix.get('stable_segment_evidence_counts', {}), sort_keys=True)}`",
        f"- Vocal evidence counts: `{json.dumps(vocals.get('stable_segment_evidence_counts', {}), sort_keys=True)}`",
        "",
        "## Equal-division residuals",
        "",
        "| EDO | Mix RMSE (cent) | Vocal RMSE (cent) | Vocal - mix |",
        "| ---: | ---: | ---: | ---: |",
    ]
    for row in result["tuning_model_comparison"]:
        lines.append(
            f"| {row['edo']} | {fmt(row['mix_weighted_rmse_cents'])} | "
            f"{fmt(row['vocal_weighted_rmse_cents'])} | {fmt(row['vocal_minus_mix_rmse_cents'])} |"
        )
    lines += [
        "",
        "## Interpretation boundary",
        "",
        result["measurement_note"],
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--track", required=True)
    p.add_argument("--mix", type=Path, required=True)
    p.add_argument("--vocals", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()

    mix = summarize_source(args.mix)
    vocals = summarize_source(args.vocals)
    result = compare_sources(mix, vocals)
    result["track"] = args.track

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "comparison.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (args.out / "measurements.md").write_text(render_markdown(args.track, result), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
