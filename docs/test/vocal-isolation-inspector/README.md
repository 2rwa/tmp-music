# Vocal Isolation Inspector

Independent browser experiment for inspecting a two-stem separation result.

## Purpose

This page does not try to assign a single "quality score". It exposes measurements useful for debugging a separator:

- synchronized audition of Original / Vocals / Instrumental / Reconstructed / Residual;
- Residual = Original - (Stem A + Stem B);
- RMS and peak levels;
- residual/original RMS ratio;
- waveform correlation between Original and Reconstructed;
- WAV export for every derived track.

## Backend

Current backend: `web-audio-separation@0.3.1` using MDX models with ONNX Runtime Web execution providers `webgpu`, then `wasm` fallback.

Each separation uses a fresh separator instance. Model assets are not stored in this repository.

## Range and stale-state rules

Only the selected source range is encoded and sent to the separator. A range change invalidates every previous output. Generated object URLs are revoked and the next separation starts from a fresh session.

## Interpretation

Residual and correlation are reconstruction diagnostics, not direct measures of vocal isolation quality. A low residual can coexist with stem leakage, and a high residual can also reflect separator reconstruction characteristics rather than audible quality.
