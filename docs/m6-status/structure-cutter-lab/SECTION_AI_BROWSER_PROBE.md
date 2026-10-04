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
