"""RQ6 / objective O6 / NFR1: can the trained ST-GNN run on a phone, offline, fast enough and as accurate?

    python -m src.edge.export                      # Horton Plains (or $env:C4_PARK = "adams_peak")

1. Export the trained day-ahead model (temporal protocol, from results/LATEST) to ONNX (opset 17).
2. Quantise the weights to int8 (ONNX Runtime dynamic quantisation: linear and GRU weights int8, activations
   float) - the standard path for CPU / mobile.
3. Check accuracy on the whole test year: MAE of PyTorch fp32, ONNX fp32 and ONNX int8 against the target,
   and the largest difference between them.
4. Latency and memory of ONE forecast (batch 1 = one day for every segment) with ONNX Runtime on ONE CPU
   thread, the closest a laptop gets to a phone core; median and p95 over 200 runs after warm-up. Memory: model
   file size and the rise in process memory when the session is created and run.
NFR1 target: under 2 s per forecast cycle. A phone core is several times slower than a laptop core, so the
laptop figure is reported with that margin in mind until it is measured on a phone (Flutter, next step).
Outputs results/<park>/<timestamp>_edge/: stgnn_fp32.onnx, stgnn_int8.onnx, metrics.json
"""
import json
import os
import time

import numpy as np
import psutil
import torch

from src.config import RESULTS, load_config
from src.eval.data import TrailData
from src.eval.metrics import summary
from src.serve.predict import load_model
from src.utils import new_run_dir, set_seed


def _ort_session(path, threads=1):
    import onnxruntime as ort
    so = ort.SessionOptions()
    so.intra_op_num_threads = threads
    so.inter_op_num_threads = 1
    return ort.InferenceSession(str(path), so, providers=["CPUExecutionProvider"])


def _predict_ort(sess, data, origins, sensed, scale, batch=64):
    out = []
    for i in range(0, len(origins), batch):
        xp, xf, _, _ = data.batch(origins[i:i + batch], sensed, scale)
        out.append(sess.run(None, {"x_past": xp.numpy(), "x_fut": xf.numpy()})[0])
    return np.clip(np.concatenate(out) * scale, 0, None)


def _latency(sess, xp, xf, runs=200):
    for _ in range(10):
        sess.run(None, {"x_past": xp, "x_fut": xf})
    t = []
    for _ in range(runs):
        t0 = time.perf_counter()
        sess.run(None, {"x_past": xp, "x_fut": xf})
        t.append((time.perf_counter() - t0) * 1000)
    return {"median_ms": round(float(np.median(t)), 2), "p95_ms": round(float(np.percentile(t, 95)), 2)}


def run():
    from onnxruntime.quantization import QuantType, quantize_dynamic
    cfg = load_config()
    set_seed(cfg["seed"])
    data = TrailData(cfg)
    model, scale, run_name = load_model(data, cfg)
    model.eval()
    every = np.ones(data.N, bool)
    te = data.origins("test")
    out = new_run_dir("edge", cfg)
    fp32, int8 = out / "stgnn_fp32.onnx", out / "stgnn_int8.onnx"

    xp, xf, _, _ = data.batch(te[:1], every, scale)
    torch.onnx.export(model, (xp, xf), str(fp32), input_names=["x_past", "x_fut"], output_names=["occupancy"],
                      dynamic_axes={"x_past": {0: "batch"}, "x_fut": {0: "batch"}, "occupancy": {0: "batch"}},
                      opset_version=17, dynamo=False)
    quantize_dynamic(str(fp32), str(int8), weight_type=QuantType.QInt8)

    # accuracy on the whole test year
    with torch.no_grad():
        p_torch = []
        for i in range(0, len(te), 64):
            a, b, _, _ = data.batch(te[i:i + 64], every, scale)
            p_torch.append(model(a, b).numpy())
    p_torch = np.clip(np.concatenate(p_torch) * scale, 0, None)
    s32, s8 = _ort_session(fp32, threads=os.cpu_count()), _ort_session(int8, threads=os.cpu_count())
    p32, p8 = _predict_ort(s32, data, te, every, scale), _predict_ort(s8, data, te, every, scale)
    y, om = data.targets(te)
    nodes = np.arange(data.N)
    acc = {name: summary(p, y, om, nodes) for name, p in (("pytorch_fp32", p_torch), ("onnx_fp32", p32),
                                                          ("onnx_int8", p8))}

    # latency + memory, one forecast, one thread
    proc = psutil.Process()
    lat, mem = {}, {}
    a, b = xp.numpy(), xf.numpy()
    for name, path in (("onnx_fp32", fp32), ("onnx_int8", int8)):
        before = proc.memory_info().rss
        sess = _ort_session(path, threads=1)
        lat[name] = _latency(sess, a, b)
        mem[name] = {"file_kb": round(path.stat().st_size / 1024, 1),
                     "process_increase_mb": round((proc.memory_info().rss - before) / 2 ** 20, 1)}
        del sess
    torch.set_num_threads(1)
    with torch.no_grad():
        for _ in range(10):
            model(xp, xf)
        t = []
        for _ in range(100):
            t0 = time.perf_counter()
            model(xp, xf)
            t.append((time.perf_counter() - t0) * 1000)
    lat["pytorch_fp32"] = {"median_ms": round(float(np.median(t)), 2), "p95_ms": round(float(np.percentile(t, 95)), 2)}

    res = {"park": cfg["park"], "model_run": run_name, "segments": int(data.N), "test_days": int(len(te)),
           "input_shapes": {"x_past": list(a.shape), "x_fut": list(b.shape)},
           "parameters": int(sum(p.numel() for p in model.parameters())),
           "accuracy": acc,
           "max_abs_diff_people": {"onnx_fp32_vs_pytorch": round(float(np.abs(p32 - p_torch).max()), 4),
                                   "onnx_int8_vs_pytorch": round(float(np.abs(p8 - p_torch).max()), 3)},
           "mae_change_int8_pct": round(100 * (acc["onnx_int8"]["MAE"] / acc["pytorch_fp32"]["MAE"] - 1), 2),
           "latency_one_forecast_1_thread": lat, "memory": mem,
           "nfr1_target_ms": 2000, "cpu": f"{os.cpu_count()} logical cores (laptop); 1 thread used for latency"}
    (out / "metrics.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    (RESULTS / "LATEST_EDGE").write_text(out.name, encoding="utf-8")
    return res, out


if __name__ == "__main__":
    r, d = run()
    print(json.dumps({k: r[k] for k in ("parameters", "accuracy", "max_abs_diff_people", "mae_change_int8_pct",
                                        "latency_one_forecast_1_thread", "memory")}, indent=1))
    print(d)
