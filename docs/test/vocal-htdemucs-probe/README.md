# Vocal HTDemucs Probe

This is an experimental browser app for testing HTDemucs separation directly in the browser.

## Backend
It uses the [unblend](https://www.npmjs.com/package/unblend) library, which executes ONNX HTDemucs models inside the browser using ONNX Runtime Web. It requires no backend server for processing audio.

## Execution Fallback
- **WebGPU**: Expected to be much faster, but relies on `navigator.gpu` support.
- **WASM**: Fallback execution when WebGPU is unavailable.
- **Multithreading**: WASM multi-threading expects Cross-Origin-Opener-Policy (`same-origin`) and Cross-Origin-Embedder-Policy (`require-corp`) to be set. Otherwise, it runs single-threaded.

## Precision and Sizes
- Supports **FP32** and **FP16** precision models.
- **FP16** offers significant bandwidth savings (~half download size) and is roughly bit-identical to FP32 for HTDemucs.

## Limitations
- **Memory Heavy**: Full track execution may run out of memory. This tool crops a selected timeframe (e.g. 30 seconds) to avoid crashing the browser tab.
- **Performance**: Expect longer processing times than backend inference.
- **Static Site Limits**: Since this runs purely client-side, the model binaries must be fetched from external CDN or cached locally. Model binaries are intentionally omitted from git and fetched at runtime.
