# Chichinu Fiija holdout

This directory contains a third real-audio holdout fixture for acoustic validation.

- source: `source/chichinu-fiija.mp3`
- source SHA-256: `3630aaaa598cb9535a9f3e0cd6fdbfd639b65403a8b151fc0645d21160bbe15a`
- size: 3,011,315 bytes
- ingestion: Dropbox -> `2rwa/bridge` -> this repository
- bridge commit: `356fb03cf85e5a30cc4d34752f558a8b009ab3ba`

The track config uses `language: und` intentionally. This fixture is currently for
language-independent acoustic stages only: Demucs separation, pitch/stable targets,
tuning, and M6 voice-quality measurements. It is not enrolled in M4/M5 language or
forced-alignment validation.

M6 remains complete based on the original Whisper AO / Jugemu acceptance runs; this
fixture is a post-completion holdout for generalization checks.

## Validation result — 2026-10-03

The dedicated holdout workflow completed successfully.

- workflow: `M6 holdout acoustic validation`
- run: `37104331999`
- artifact: `m6-holdout-chichinu-fiija` (`11267267610`)
- artifact digest: `sha256:ea221dd81d08bfa4a7e2d7f8ab26546836f298f7798d49fe71e35bb370756858`
- Praat: 6.4.49
- stable targets: 40
- measured stable-vocal duration: 12.85 s
- CPPS median: 13.70 dB
- Praat HNR(cc) median: 19.81 dB
- autocorrelation HNR median: 12.93 dB
- spectral tilt median: -2.66 dB/oct
- F1/F2/F3 median: 715 / 1480 / 2617 Hz
- vibrato extent median: 15.68 cent
- pitch-movement candidates: 58
- register-transition candidates: 1

These are measurement outputs and candidate counts, not a linguistic or vocal-quality
classification.
