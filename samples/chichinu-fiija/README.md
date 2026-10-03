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
