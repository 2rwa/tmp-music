# Section AI browser probe

Goal: determine whether the current All-In-One Harmonix model can be exported to ONNX before wiring it into Structure Cutter Lab.

## Scope

- Upstream: `openmirlab/all-in-one-infer` pinned to revision `797f1d21b115955ed81ff9161440334fefea8855`.
- Model: `harmonix-fold0` only.
- Checkpoint size from upstream metadata: 1,400,571 bytes.
- Checkpoint license: CC-BY-NC-SA-4.0.
- Input contract: `[1, 4, 600, 81]` = batch × stems × frames × log-filterbank bins.
- Output contract: section logits + functional label logits only.
- Export attempts: legacy `torch.onnx.export`, then dynamo exporter.
- Validation: ONNX checker + ONNX Runtime CPU numerical comparison.

## Why probe first

The model itself is small. The main browser-portability risk is Dilated Neighborhood Attention implemented with gather/einsum and relative positional bias. The second risk is reproducing the upstream madmom-compatible 81-bin log-filtered spectrogram.

No generated ONNX file is committed to `tmp-music` by this workflow. Probe outputs live only as short-retention Actions artifacts. If a generated model later needs to be stored in the repository and is large, use the established Dropbox → bridge repo → tmp-music route.

## Probe results

### Fixed 600-frame graph

- Legacy ONNX export succeeds at opset 18.
- ONNX size: 3,199,894 bytes.
- ONNX Runtime CPU matches PyTorch within about 1e-5 maximum absolute error.
- ORT Web/WASM can load and execute the same exported graph in headless Chrome.
- GitHub-hosted Chrome exposes `navigator.gpu`, but the SwiftShader WebGPU inference probe times out; real hardware WebGPU remains a physical-device validation item.

### Dynamic time axis

Marking the time dimension dynamic is not sufficient with the legacy exporter. A graph traced at 600 frames works at 600, but 1200 and 3000 frames fail in encoder layer 6 because a padding/index dimension is frozen at trace time (`640 by 1200` / `640 by 3000` broadcast failures).

Do not treat the current dynamic export as usable.

### Fixed-length scaling

| Frames | Audio at 100 fps | ONNX bytes | ORT CPU inference |
| ---: | ---: | ---: | ---: |
| 6,000 | 60 s | 7,575,137 | 1.812 s |
| 30,000 | 300 s | 29,140,538 | 8.495 s |

Both fixed graphs pass ONNX checker and numerical comparison against PyTorch. The growth is mainly trace-length-dependent indexing/padding constants, not learned weights.

### Current direction

Before accepting a 29 MB five-minute graph, probe a symbolic/dynamo export or isolate the shape-dependent neighborhood-attention indexing. If a generated ONNX is eventually retained in `tmp-music`, transfer it through Dropbox → bridge repo → tmp-music rather than committing the binary directly.
