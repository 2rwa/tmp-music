#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib
import json
import os
import sys
import tomllib
import types
import urllib.request
from pathlib import Path

OUT_DIR = Path(os.environ.get("SECTION_AI_MODEL_DIR", "docs/m6-status/structure-cutter-lab/models"))
UPSTREAM = Path(os.environ.get("ALLIN1_SOURCE_DIR", "upstream-allin1")).resolve()
MODEL_NAME = "harmonix-fold0-section-function-long.onnx"
MODEL_PATH = OUT_DIR / MODEL_NAME
META_PATH = OUT_DIR / "harmonix-fold0-section-function-long.json"
NOTICE_PATH = OUT_DIR / "NOTICE.md"
CHECKPOINT_PATH = Path(os.environ.get("SECTION_AI_CHECKPOINT", "/tmp/harmonix-fold0.pth"))
SOURCE_REVISION = "797f1d21b115955ed81ff9161440334fefea8855"
MIN_FRAMES = 10240
MAX_FRAMES = 66000
TRACE_FRAMES = 12000


def install_source_package_shims() -> None:
    src = (UPSTREAM / "src" / "allin1_infer").resolve()
    models_dir = src / "models"
    if not src.is_dir():
        raise FileNotFoundError(f"missing upstream source: {src}")
    root = types.ModuleType("allin1_infer")
    root.__path__ = [str(src)]
    root.__package__ = "allin1_infer"
    sys.modules["allin1_infer"] = root
    models = types.ModuleType("allin1_infer.models")
    models.__path__ = [str(models_dir)]
    models.__package__ = "allin1_infer.models"
    sys.modules["allin1_infer.models"] = models


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    import numpy as np
    import onnx
    import onnxruntime as ort
    import torch
    from omegaconf import OmegaConf

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    checkpoint_toml = UPSTREAM / "src" / "allin1_infer" / "config" / "checkpoints.toml"
    metadata = tomllib.loads(checkpoint_toml.read_text(encoding="utf-8"))["models"]["harmonix-fold0"]
    artifact = next(a for a in metadata["artifacts"] if a.get("kind") == "checkpoint")

    if not CHECKPOINT_PATH.exists():
        urllib.request.urlretrieve(artifact["url"], CHECKPOINT_PATH)
    checkpoint_sha = sha256(CHECKPOINT_PATH)
    if checkpoint_sha != artifact["sha256"]:
        raise RuntimeError("checkpoint SHA-256 mismatch")

    install_source_package_shims()
    AllInOne = importlib.import_module("allin1_infer.models.allinone").AllInOne
    na_mod = importlib.import_module("allin1_infer.models.neighborhood_attention")
    if hasattr(na_mod._na1d_indices, "__wrapped__"):
        na_mod._na1d_indices = na_mod._na1d_indices.__wrapped__

    checkpoint = torch.load(CHECKPOINT_PATH, map_location="cpu")
    config = OmegaConf.create(checkpoint["config"])
    model = AllInOne(config)
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()
    torch.set_grad_enabled(False)

    class SectionFunctionWrapper(torch.nn.Module):
        def __init__(self, base):
            super().__init__()
            self.base = base

        def forward(self, x):
            out = self.base(x)
            return out.logits_section, out.logits_function

    wrapper = SectionFunctionWrapper(model).eval()
    trace = torch.zeros(1, 4, TRACE_FRAMES, 81, dtype=torch.float32)
    time_dim = torch.export.Dim("time_long", min=MIN_FRAMES, max=MAX_FRAMES)

    if MODEL_PATH.exists():
        MODEL_PATH.unlink()
    torch.onnx.export(
        wrapper,
        (trace,),
        str(MODEL_PATH),
        input_names=["spectrograms"],
        output_names=["section_logits", "function_logits"],
        opset_version=18,
        dynamo=True,
        dynamic_shapes=({2: time_dim},),
        external_data=False,
    )

    graph = onnx.load(str(MODEL_PATH))
    onnx.checker.check_model(graph)
    session = ort.InferenceSession(str(MODEL_PATH), providers=["CPUExecutionProvider"])

    validations = []
    for frames in (MIN_FRAMES, TRACE_FRAMES):
        x = torch.zeros(1, 4, frames, 81, dtype=torch.float32)
        with torch.no_grad():
            ref_section, ref_function = wrapper(x)
        got_section, got_function = session.run(None, {"spectrograms": x.numpy()})
        sec_diff = float(np.max(np.abs(got_section - ref_section.numpy())))
        fun_diff = float(np.max(np.abs(got_function - ref_function.numpy())))
        ok = (
            got_section.shape[-1] == frames
            and got_function.shape[-1] == frames
            and sec_diff < 5e-4
            and fun_diff < 5e-4
        )
        validations.append({
            "frames": frames,
            "ok": bool(ok),
            "max_abs_diff": {"section": sec_diff, "function": fun_diff},
            "output_shapes": [list(got_section.shape), list(got_function.shape)],
        })
        if not ok:
            raise RuntimeError(f"ORT validation failed at {frames} frames")

    model_sha = sha256(MODEL_PATH)
    result = {
        "model": "harmonix-fold0",
        "file": MODEL_NAME,
        "onnx_bytes": MODEL_PATH.stat().st_size,
        "onnx_sha256": model_sha,
        "opset": 18,
        "input": {
            "name": "spectrograms",
            "shape": [1, 4, "time_long", 81],
            "min_frames": MIN_FRAMES,
            "max_frames": MAX_FRAMES,
            "fps": int(config.fps),
            "min_seconds": MIN_FRAMES / float(config.fps),
            "max_seconds": MAX_FRAMES / float(config.fps),
        },
        "outputs": ["section_logits", "function_logits"],
        "labels": ["start", "end", "intro", "outro", "break", "bridge", "inst", "solo", "verse", "chorus"],
        "source": {
            "repository": "https://github.com/openmirlab/all-in-one-infer",
            "revision": SOURCE_REVISION,
            "checkpoint": artifact["name"],
            "checkpoint_sha256": checkpoint_sha,
            "checkpoint_bytes": artifact.get("size"),
            "checkpoint_license": metadata.get("license"),
        },
        "validation": validations,
    }
    META_PATH.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    NOTICE_PATH.write_text(
        "# Section AI model notice\n\n"
        + MODEL_NAME + " is an ONNX export derived from the openmirlab/all-in-one-infer harmonix-fold0 checkpoint.\n\n"
        + "- Upstream revision: " + SOURCE_REVISION + "\n"
        + "- Checkpoint SHA-256: " + checkpoint_sha + "\n"
        + "- Checkpoint license metadata: " + str(metadata.get("license")) + "\n"
        + "- Generated ONNX SHA-256: " + model_sha + "\n"
        + f"- Input range: {MIN_FRAMES}-{MAX_FRAMES} frames at {int(config.fps)} fps\n\n"
        + "The generated model is kept with its source/checkpoint attribution and license metadata so downstream use can review the upstream terms.\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
