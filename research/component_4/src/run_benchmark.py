"""Benchmark HA, ARIMA, LSTM, GRU (no graph) and ST-GNN on the test year (D3, D5).

    python -m src.run_benchmark                      # both protocols, seeds from config
    python -m src.run_benchmark --protocol temporal  # only the temporal holdout
    python -m src.run_benchmark --quick              # 1 epoch, 1 seed: checks the pipeline end to end

Protocol 'temporal': all segments sensed; train 2022-23, validate 2024, test 2025 (day-ahead, midnight origins).
Protocol 'spatial' : spatial block CV - one contiguous block of segments is unsensed (no history input,
                     no training loss) and scored; tests forecasting on segments without counts.
Outputs go to results/<timestamp>_benchmark/: metrics.csv, stats.json, predictions.npz, models/*.pt
"""
import argparse
import json
import time

import numpy as np
import pandas as pd
import torch

from src.config import RESULTS, load_config
from src.data.build_dataset import viewpoints
from src.eval.data import TrailData
from src.eval.metrics import paired_tests, per_day_mae, summary
from src.models.baselines import ARIMABaseline, HistoricalAverage
from src.train.trainer import predict, train
from src.utils import new_run_dir

NEURAL = ["lstm", "gru_nograph", "stgnn"]


def masks(data, origins, cfg):
    fut = np.asarray(origins)[:, None] + np.arange(data.H)
    hr = np.asarray(data.times.hour)[fut]
    lo, hi = cfg["train"]["peak_hours"]
    return (hr >= lo) & (hr <= hi)


def poi_nodes(data):
    return np.where(np.isin(data.segment_poi, list(viewpoints(data.cfg))))[0]


def evaluate(name, pred, data, origins, nodes, cfg, extra=None):
    y, om = data.targets(origins)
    row = {"model": name, **(extra or {}),
           **summary(pred, y, om, nodes, masks(data, origins, cfg), poi_nodes(data))}
    return row, per_day_mae(pred, y, om, nodes)


def run_protocol(data, cfg, run, sensed, nodes, seeds, tag, use_arima, log):
    te = data.origins("test")
    rows, day_err, preds = [], {}, {}

    ha = HistoricalAverage().fit(data, sensed)
    preds["HA"] = ha.predict(data, te)
    r, day_err["HA"] = evaluate("HA", preds["HA"], data, te, nodes, cfg)
    rows.append(r)

    if use_arima:
        t0 = time.time()
        preds["ARIMA"] = ARIMABaseline(cfg).predict(data, te, nodes)
        r, day_err["ARIMA"] = evaluate("ARIMA", preds["ARIMA"], data, te, nodes, cfg)
        rows.append(r)
        log(f"[{tag}] ARIMA done in {time.time() - t0:.0f}s")

    for kind in NEURAL:
        seed_rows, seed_days, seed_preds = [], [], []
        for s in seeds:
            model, scale = train(data, kind, sensed, cfg, s, log=log)
            p = predict(model, data, te, sensed, scale)
            r, de = evaluate(kind, p, data, te, nodes, cfg, {"seed": s})
            seed_rows.append(r), seed_days.append(de), seed_preds.append(p)
            torch.save({"state_dict": model.state_dict(), "scale": scale, "kind": kind,
                        "sensed": sensed, "seed": s}, run / "models" / f"{tag}_{kind}_s{s}.pt")
            log(f"[{tag}] {kind} seed={s} MAE={r['MAE']:.3f} RMSE={r['RMSE']:.3f}")
        df = pd.DataFrame(seed_rows)
        row = {"model": kind, "n_seeds": len(seeds)}
        for c in df.columns.drop(["model", "seed"]):
            row[c], row[c + "_sd"] = float(df[c].mean()), float(df[c].std(ddof=0))
        rows.append(row)
        day_err[kind] = np.mean(seed_days, axis=0)       # average error over seeds, per day
        preds[kind] = seed_preds[0]
    return rows, day_err, preds


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--protocol", choices=["temporal", "spatial", "both"], default="both")
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--no-arima", action="store_true")
    args = ap.parse_args()

    cfg = load_config()
    if args.quick:
        cfg["train"].update(epochs=1, seeds=[42], spatial_seeds=[42])
    data = TrailData(cfg)
    run = new_run_dir("benchmark" + ("_quick" if args.quick else ""), cfg)
    (run / "models").mkdir()
    logf = open(run / "log.txt", "w", encoding="utf-8")

    def log(msg):
        print(msg, flush=True)
        logf.write(msg + "\n")
        logf.flush()

    all_nodes = np.arange(data.N)
    out = {}
    if args.protocol in ("temporal", "both"):
        rows, day_err, preds = run_protocol(data, cfg, run, np.ones(data.N, bool), all_nodes,
                                            cfg["train"]["seeds"], "temporal", not args.no_arima, log)
        pd.DataFrame(rows).to_csv(run / "metrics_temporal.csv", index=False)
        out["temporal"] = {"tests_vs_stgnn": paired_tests(day_err, "stgnn")}
        np.savez_compressed(run / "predictions_temporal.npz", origins=data.origins("test"),
                            **{k: v.astype(np.float32) for k, v in preds.items()})

    if args.protocol in ("spatial", "both"):
        blocks = data.spatial_blocks(cfg["task"]["spatial_blocks"])
        fold_rows, fold_days = [], {}
        for f, block in enumerate(blocks):
            sensed = np.ones(data.N, bool)
            sensed[block] = False
            log(f"[spatial fold {f}] held-out segments: {block.tolist()}")
            rows, day_err, _ = run_protocol(data, cfg, run, sensed, block, cfg["train"]["spatial_seeds"],
                                            f"spatial{f}", False, log)
            for r in rows:
                r["fold"] = f
            fold_rows += rows
            for k, v in day_err.items():
                fold_days.setdefault(k, []).append(v)
        df = pd.DataFrame(fold_rows)
        df.to_csv(run / "metrics_spatial_folds.csv", index=False)
        df.groupby("model")[["MAE", "RMSE"]].agg(["mean", "std"]).to_csv(run / "metrics_spatial.csv")
        pooled = {k: np.concatenate(v) for k, v in fold_days.items()}   # pairs = (fold, day)
        out["spatial"] = {"blocks": [b.tolist() for b in blocks],
                          "tests_vs_stgnn": paired_tests(pooled, "stgnn")}

    (run / "stats.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    if not args.quick:                         # a pipeline check must not replace the model the app uses
        (RESULTS / "LATEST").write_text(run.name, encoding="utf-8")
    log(f"done -> {run}")


if __name__ == "__main__":
    main()
