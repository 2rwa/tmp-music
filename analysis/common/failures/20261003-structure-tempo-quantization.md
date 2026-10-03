# 2026-10-03 — Structure tempo quantization on coarse frame grid

## Symptom

After adding explicit primary / half / double tempo candidates to the Milestone 3 structure analyzer, the real Jugemu validation runs failed:

- Actions run `37086741133`
- Actions run `37087024183`

The structure analysis itself completed and produced its normal recurrence/cycle outputs, but tempo validation rejected:

- primary: 120 BPM
- half: 60 BPM
- double: 240 BPM

The established higher-resolution preliminary measurement is approximately 98.68 BPM with an approximately 197.37 BPM double-time candidate.

## Root cause

The new beat tracker reused the structure-analysis frame step:

- `frame_step_s = 0.25`

That is appropriate for the relatively slow self-similarity / recurrence representation, but too coarse for tempo estimation.

The detected beat timestamps were quantized to exact 0.5 s spacing, e.g. 0.75, 1.25, 1.75, ... s. This mechanically implies 120 BPM and also made the beat-interval regularity confidence appear artificially perfect.

## Why this matters

Tempo and recurrence operate at different useful time resolutions.

A 0.25 s structure grid should not constrain onset/beat timing. Reusing one hop for both analyses introduces quantization bias and can create overconfident but wrong tempo candidates.

## Required fix

- use a separate, higher-resolution onset/tempo hop
- retain primary / half / double candidates
- keep tempo confidence separate from metrical-level certainty
- treat approximately 99 / 197 BPM as a soft real-track regression, not a hard exact value
- preserve the failed run as regression evidence

## Regression expectation

A future real Jugemu structure run should:

1. still recover the approximately 28.75 s recurrence period;
2. still recover the aligned cycle starts;
3. emit non-empty beat timestamps from a finer tempo time base;
4. include a tempo candidate near 99 BPM and a double-time candidate near 197 BPM within a deliberately broad tolerance;
5. not report confidence=1 merely because coarse quantization forced equal beat intervals.
