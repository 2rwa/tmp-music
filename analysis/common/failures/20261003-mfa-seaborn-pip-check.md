# MFA pip-check dependency gap — 2026-10-03

## Symptom

Milestone 5 forced-alignment run `37090798722` failed before alignment started, during dependency installation.

```text
montreal-forced-aligner 3.4.2 requires seaborn, which is not installed.
```

## Root cause

MFA 3.4.2 was installed from conda-forge. The environment satisfied the core runtime package install, but the subsequent `python -m pip check` detected that MFA's Python package metadata required `seaborn`, which was not present.

## Fix

Add `seaborn>=0.13` to `requirements-alignment.txt` so the explicit alignment environment passes dependency validation before model download/alignment.

The Jugemu alignment config also records the currently validated MFA version as `3.4.2`.

## Regression

Milestone 5 must continue to run `python -m pip check`. A missing dependency must fail during setup rather than becoming a later runtime error.

The next M3 success triggers M5 again; both Jugemu and Whisper AO alignment jobs use the corrected alignment requirements.
