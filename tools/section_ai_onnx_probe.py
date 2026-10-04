#!/usr/bin/env python3
import hashlib
import importlib
import json
import os
import sys
import time
import tomllib
import traceback
import types
import urllib.request
from pathlib import Path

OUT = Path(os.environ.get("SECTION_AI_PROBE_OUT", "section-ai-probe"))
UPSTREAM = Path(os.environ.get("ALLIN1_SOURCE_DIR", "upstream-allin1"))
OUT.mkdir(parents=True, exist_ok=True)
REPORT = OUT / "report.json"
TRACE = OUT / "traceback.txt"
MODEL_PATH = OUT / "harmonix-fold0-section-function.onnx"
DYNAMIC_MODEL_PATH = OUT / "harmonix-fold0-section-function-dynamic.onnx"
CHECKPOINT_PATH = OUT / "harmonix-fold0.pth"

report = {
    "probe": "all-in-one harmonix-fold0 ONNX export",
    "input_shape": [1, 4, 600, 81],
    "opset": 18,
    "model": "harmonix-fold0",
    "attempts": [],
    "export_ok": False,
    "ort_ok": False,
    "dynamic": {"export_ok": False, "cases": []},
}

def save():
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

def install_source_package_shims():
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

try:
    import numpy as np
    import torch
    import onnx
    import onnxruntime as ort
    from omegaconf import OmegaConf

    report["versions"] = {
        "python": sys.version.split()[0],
        "torch": torch.__version__,
        "onnx": onnx.__version__,
        "onnxruntime": ort.__version__,
    }

    checkpoint_toml = UPSTREAM / "src" / "allin1_infer" / "config" / "checkpoints.toml"
    metadata = tomllib.loads(checkpoint_toml.read_text(encoding="utf-8"))["models"]["harmonix-fold0"]
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

    if not CHECKPOINT_PATH.exists():
        urllib.request.urlretrieve(artifact["url"], CHECKPOINT_PATH)
    digest = hashlib.sha256(CHECKPOINT_PATH.read_bytes()).hexdigest()
    report["checkpoint_download_bytes"] = CHECKPOINT_PATH.stat().st_size
    report["checkpoint_sha256_actual"] = digest
    if digest != artifact["sha256"]:
        raise ValueError("checkpoint SHA-256 mismatch")

    install_source_package_shims()
    AllInOne = importlib.import_module("allin1_infer.models.allinone").AllInOne

    torch.set_grad_enabled(False)
    started = time.time()
    checkpoint = torch.load(CHECKPOINT_PATH, map_location="cpu")
    config = OmegaConf.create(checkpoint["config"])
    model = AllInOne(config)
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()
    report["load_seconds"] = round(time.time() - started, 3)
    report["config"] = {
        "depth": int(config.depth),
        "dim_embed": int(config.dim_embed),
        "num_heads": int(config.num_heads),
        "kernel_size": int(config.kernel_size),
        "dim_input": int(config.dim_input),
        "num_instruments": int(config.data.num_instruments),
        "num_labels": int(config.data.num_labels),
        "fps": int(config.fps),
    }

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
    report["pytorch_output_shapes"] = [list(ref_section.shape), list(ref_function.shape)]

    attempts = [
        ("legacy", {"dynamo": False}),
        ("dynamo", {"dynamo": True}),
    ]
    all_traces = []

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
            all_traces.append(f"== {name} ==\n{traceback.format_exc()}\n")

    if all_traces:
        TRACE.write_text("\n".join(all_traces), encoding="utf-8")

    if report["export_ok"]:
        graph = onnx.load(str(MODEL_PATH))
        onnx.checker.check_model(graph)
        report["onnx_nodes"] = len(graph.graph.node)
        report["onnx_inputs"] = [n.name for n in graph.graph.input]
        report["onnx_outputs"] = [n.name for n in graph.graph.output]
        report["onnx_bytes"] = MODEL_PATH.stat().st_size

        started = time.time()
        session = ort.InferenceSession(str(MODEL_PATH), providers=["CPUExecutionProvider"])
        got_section, got_function = session.run(None, {"spectrograms": x.numpy()})
        report["ort_seconds"] = round(time.time() - started, 3)
        sec_diff = float(np.max(np.abs(got_section - ref_section.numpy())))
        fun_diff = float(np.max(np.abs(got_function - ref_function.numpy())))
        report["max_abs_diff"] = {"section": sec_diff, "function": fun_diff}
        report["ort_output_shapes"] = [list(got_section.shape), list(got_function.shape)]
        report["ort_ok"] = bool(
            np.isfinite(sec_diff) and np.isfinite(fun_diff)
            and sec_diff < 5e-4 and fun_diff < 5e-4
        )

        # Probe whether the time axis can really be dynamic. The legacy exporter
        # emits tracer warnings around shape-dependent padding, so this must be
        # verified numerically at lengths other than the trace length.
        dynamic = report["dynamic"]
        try:
            started = time.time()
            if DYNAMIC_MODEL_PATH.exists():
                DYNAMIC_MODEL_PATH.unlink()
            torch.onnx.export(
                wrapper,
                (x,),
                str(DYNAMIC_MODEL_PATH),
                input_names=["spectrograms"],
                output_names=["section_logits", "function_logits"],
                opset_version=18,
                do_constant_folding=True,
                dynamo=False,
                dynamic_axes={
                    "spectrograms": {2: "time"},
                    "section_logits": {1: "time"},
                    "function_logits": {2: "time"},
                },
            )
            dynamic["export_seconds"] = round(time.time() - started, 3)
            dynamic["bytes"] = DYNAMIC_MODEL_PATH.stat().st_size
            onnx.checker.check_model(onnx.load(str(DYNAMIC_MODEL_PATH)))
            dyn_session = ort.InferenceSession(
                str(DYNAMIC_MODEL_PATH),
                providers=["CPUExecutionProvider"],
            )
            dynamic["export_ok"] = True

            for frames in [600, 1200, 3000]:
                case = {"frames": frames, "ok": False}
                try:
                    probe_x = torch.randn(1, 4, frames, 81, dtype=torch.float32)
                    started = time.time()
                    with torch.no_grad():
                        ref_s, ref_f = wrapper(probe_x)
                    case["pytorch_seconds"] = round(time.time() - started, 3)

                    started = time.time()
                    got_s, got_f = dyn_session.run(
                        None,
                        {"spectrograms": probe_x.numpy()},
                    )
                    case["ort_seconds"] = round(time.time() - started, 3)
                    sec = float(np.max(np.abs(got_s - ref_s.numpy())))
                    fun = float(np.max(np.abs(got_f - ref_f.numpy())))
                    case["max_abs_diff"] = {"section": sec, "function": fun}
                    case["output_shapes"] = [list(got_s.shape), list(got_f.shape)]
                    case["ok"] = bool(
                        got_s.shape[-1] == frames
                        and got_f.shape[-1] == frames
                        and np.isfinite(sec)
                        and np.isfinite(fun)
                        and sec < 5e-4
                        and fun < 5e-4
                    )
                except Exception as exc:
                    case["error_type"] = type(exc).__name__
                    case["error"] = str(exc)[:4000]
                dynamic["cases"].append(case)

            dynamic["all_cases_ok"] = all(x.get("ok") for x in dynamic["cases"])
        except Exception as exc:
            dynamic["error_type"] = type(exc).__name__
            dynamic["error"] = str(exc)[:4000]
            with TRACE.open("a", encoding="utf-8") as fh:
                fh.write("\n== dynamic export ==\n")
                fh.write(traceback.format_exc())

except Exception as exc:
    report["fatal_error_type"] = type(exc).__name__
    report["fatal_error"] = str(exc)[:4000]
    TRACE.write_text(traceback.format_exc(), encoding="utf-8")

save()
print(REPORT.read_text(encoding="utf-8"))
sys.exit(0)
