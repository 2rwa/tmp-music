#!/usr/bin/env python3
import json
import os
import sys
import time
import traceback
from pathlib import Path

OUT = Path(os.environ.get("SECTION_AI_PROBE_OUT", "section-ai-probe"))
OUT.mkdir(parents=True, exist_ok=True)
REPORT = OUT / "report.json"
TRACE = OUT / "traceback.txt"
MODEL_PATH = OUT / "harmonix-fold0-section-function.onnx"

report = {
    "probe": "all-in-one harmonix-fold0 ONNX export",
    "input_shape": [1, 4, 600, 81],
    "opset": 18,
    "model": "harmonix-fold0",
    "attempts": [],
    "export_ok": False,
    "ort_ok": False,
}

def save():
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

try:
    import numpy as np
    import torch
    import onnx
    import onnxruntime as ort
    from allin1_infer.models.loaders import load_pretrained_model
    from allin1_infer.checkpoints import checkpoint_metadata

    report["versions"] = {
        "python": sys.version.split()[0],
        "torch": torch.__version__,
        "onnx": onnx.__version__,
        "onnxruntime": ort.__version__,
    }

    metadata = checkpoint_metadata("harmonix-fold0")
    artifact = next(a for a in metadata["artifacts"] if a.get("kind") == "checkpoint")
    report["checkpoint"] = {
        "license": metadata.get("license"),
        "source_revision": metadata.get("source_revision"),
        "updated_at": metadata.get("updated_at"),
        "name": artifact.get("name"),
        "url": artifact.get("url"),
        "sha256": artifact.get("sha256"),
        "size": artifact.get("size"),
    }

    torch.set_grad_enabled(False)
    started = time.time()
    model = load_pretrained_model("harmonix-fold0", device="cpu")
    report["load_seconds"] = round(time.time() - started, 3)

    class SectionFunctionWrapper(torch.nn.Module):
        def __init__(self, base):
            super().__init__()
            self.base = base

        def forward(self, x):
            out = self.base(x)
            return out.logits_section, out.logits_function

    wrapper = SectionFunctionWrapper(model).eval()
    x = torch.randn(*report["input_shape"], dtype=torch.float32)

    with torch.no_grad():
        ref_section, ref_function = wrapper(x)
    report["pytorch_output_shapes"] = [
        list(ref_section.shape),
        list(ref_function.shape),
    ]

    attempts = [
        ("legacy", {"dynamo": False}),
        ("dynamo", {"dynamo": True}),
    ]

    for name, extra in attempts:
        attempt = {"name": name, "ok": False}
        started = time.time()
        try:
            if MODEL_PATH.exists():
                MODEL_PATH.unlink()
            torch.onnx.export(
                wrapper,
                (x,),
                str(MODEL_PATH),
                input_names=["spectrograms"],
                output_names=["section_logits", "function_logits"],
                opset_version=18,
                do_constant_folding=True,
                **extra,
            )
            attempt["seconds"] = round(time.time() - started, 3)
            attempt["bytes"] = MODEL_PATH.stat().st_size
            attempt["ok"] = True
            report["attempts"].append(attempt)
            report["exporter"] = name
            report["export_ok"] = True
            break
        except Exception as exc:
            attempt["seconds"] = round(time.time() - started, 3)
            attempt["error_type"] = type(exc).__name__
            attempt["error"] = str(exc)[:4000]
            report["attempts"].append(attempt)
            TRACE.write_text(
                f"== {name} ==\n" + traceback.format_exc() + "\n",
                encoding="utf-8",
            )

    if report["export_ok"]:
        graph = onnx.load(str(MODEL_PATH))
        onnx.checker.check_model(graph)
        report["onnx_nodes"] = len(graph.graph.node)
        report["onnx_inputs"] = [n.name for n in graph.graph.input]
        report["onnx_outputs"] = [n.name for n in graph.graph.output]
        report["onnx_bytes"] = MODEL_PATH.stat().st_size

        started = time.time()
        session = ort.InferenceSession(str(MODEL_PATH), providers=["CPUExecutionProvider"])
        got_section, got_function = session.run(
            None,
            {"spectrograms": x.numpy()},
        )
        report["ort_seconds"] = round(time.time() - started, 3)
        sec_diff = float(np.max(np.abs(got_section - ref_section.numpy())))
        fun_diff = float(np.max(np.abs(got_function - ref_function.numpy())))
        report["max_abs_diff"] = {
            "section": sec_diff,
            "function": fun_diff,
        }
        report["ort_output_shapes"] = [list(got_section.shape), list(got_function.shape)]
        report["ort_ok"] = bool(np.isfinite(sec_diff) and np.isfinite(fun_diff) and sec_diff < 5e-4 and fun_diff < 5e-4)

except Exception as exc:
    report["fatal_error_type"] = type(exc).__name__
    report["fatal_error"] = str(exc)[:4000]
    TRACE.write_text(traceback.format_exc(), encoding="utf-8")

save()
print(REPORT.read_text(encoding="utf-8"))
sys.exit(0)
