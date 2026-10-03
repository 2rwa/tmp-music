# 2026-10-03 — Jugemu mix CREPE confidence collapse

## Symptom

Milestone 2 mix-pitch run `37084031038` failed only for Jugemu.

The pitch estimators themselves completed, but the original consensus policy produced no consensus frames:

- pYIN voiced fraction: ~0.722
- CREPE reliable fraction at periodicity >= 0.21: 0.0
- strict consensus frames: 0
- stable targets: 0
- tuning stage then exited non-zero because it had zero targets

Whisper AO in the same run did not show this failure mode.

## Root cause

The initial implementation treated CREPE periodicity >= 0.21 as a universal hard gate.

That value is an example used by torchcrepe for clean speech and is explicitly data-dependent. A polyphonic music mix can have much lower periodicity even when pYIN supplies a usable F0 trajectory.

A second configuration issue was also found: `fmax_hz=2093.0` exceeded torchcrepe's documented maximum of 2006 Hz.

## Fix

- cap configured CREPE `fmax_hz` at 2006 Hz
- median-filter CREPE periodicity and mean-filter pitch as recommended by torchcrepe
- silence-mask CREPE periodicity
- preserve raw pYIN/CREPE disagreement even when CREPE is below the reliability threshold
- keep strict consensus for strong/weak agreement
- when strict consensus is unavailable, allow only high-confidence pYIN as an explicitly labeled `pyin-fallback`
- carry evidence labels into stable-target segments
- treat zero stable targets as a valid `insufficient_stable_targets` measurement, not as a process crash
- add a synthetic 440 Hz torchcrepe smoke test to heavy pitch workflows

## Regression expectation

A future Jugemu run must preserve the fact that CREPE confidence is low on the mix instead of fabricating consensus. Stable targets derived from fallback frames must remain labeled so tuning measurements are not mistaken for two-estimator agreement.
