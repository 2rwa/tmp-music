# Vocal HTDemucs Probe

Browser-side HTDemucs experiment using the `unblend` npm package.

## Why this app is bundled

`unblend` creates module workers with URLs relative to its own module. Its browser
documentation explicitly expects a bundler that understands
`new Worker(new URL(..., import.meta.url))`. This probe therefore uses Vite
instead of importing `unblend` through a CDN ESM shim.

The Pages workflow builds this directory before deployment and overlays the
generated Vite output onto the deployed copy of this directory.

## Backend

- Package: `unblend@1.0.0`
- Model: `htdemucs`
- Outputs: drums / bass / other / vocals
- Input sample rate: 44.1 kHz
- Preferred backend: WebGPU, with WASM fallback supported by `unblend`
- WASM assets: `onnxruntime-web@1.26.0` CDN path, matching the exact dependency
  used by `unblend@1.0.0`
- Default precision: weight-only FP16 model (~91 MB); FP32 is ~169 MB
- Model cache: browser Cache Storage when available

GitHub Pages does not normally provide the COOP/COEP headers needed for
cross-origin isolation, so this probe requests one WASM thread when
`crossOriginIsolated` is false.

## Model-weight licensing

The `unblend` source code is MIT licensed. That does **not** automatically
license the HTDemucs weights. The upstream unblend model documentation says no
explicit license grant has been identified for the published HTDemucs weights.
The app displays `separator.license` after the model loads instead of assuming
the code license applies to the weights.

## Range and lifecycle rules

Only the selected source range is passed to the separator. Outputs use local
time starting at 0 seconds while the UI retains the original source offset.

Each run loads a fresh separator. Before a new result is attached, old audio
elements are paused, their `src` attributes are removed, `load()` is called,
and old blob URLs are revoked. The separator is always unloaded in `finally`.

## Regression

The headless browser self-test injects a fake separator loader but executes the
real crop and result lifecycle path:

1. Separate source 1.2–1.4 s and verify the crop begins in the second half of a
   synthetic source.
2. Change to 0.2–0.4 s and verify first-run blob URLs are revoked.
3. Run again and verify the second crop begins in the first half.
4. Verify output URLs are new and both separator instances are unloaded.

The real model is intentionally not downloaded in CI.
