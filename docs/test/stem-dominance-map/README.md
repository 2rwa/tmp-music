# Stem Dominance Map

Independent browser experiment for inspecting time-frequency differences between
two separated stems.

## What the map means

The default Dominance view computes, for every STFT cell:

```text
Vocals magnitude (dB) - Instrumental magnitude (dB)
```

Positive cells are vocal-dominant and negative cells are instrumental-dominant.
The Overlap view highlights cells where both stems have relatively strong energy.

This is **not** a ground-truth leakage score. Without isolated reference stems,
shared energy can represent real overlap in the mix, model cross-talk, ambience,
reverb, or reconstruction characteristics.

## Pipeline

1. Decode a local browser audio file.
2. Crop only the selected source range.
3. Run a fresh MDX separator session.
4. Decode two output stems.
5. Mix each stem to mono.
6. Apply a Hann-window STFT.
7. Render dominance / overlap / individual stem energy maps.
8. Export the map as CSV or the visible canvas as PNG.

Current separator backend is `web-audio-separation@0.3.1` with ONNX Runtime Web,
preferring WebGPU and falling back to WASM. No model binaries are committed here.

## Regression strategy

The headless browser self-test creates synthetic 1000 Hz vocal energy and
250 Hz instrumental energy and verifies that the map reports the expected
frequency-bin dominance. It also verifies that changing the selected range
invalidates the old map.
