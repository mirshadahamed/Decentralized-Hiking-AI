"""G1 / claim C4: forecasting a trail with no sensor record - only gate counts, or nothing at all.

    python -m src.eval.sparse_sensors                     (current park; $env:C4_PARK = "adams_peak" for the other)
    python -m src.eval.sparse_sensors --quick             (1 epoch, 1 seed: checks the pipeline)

The synthetic target exists for every segment, so the training LOSS covers every segment; the model's INPUT holds
only what a real park measures:
  gate    occupancy history of the access segments (where tickets are checked in / walk-ins sold), nothing inside
  zero    no counts at all: calendar + weather + segment descriptions only
Scored on the interior segments (every segment except the gates), test year 2025, day-ahead from midnight.
Baselines: historical average of the simulation (the prior a park would have without any model), LSTM and
GRU without graph (same inputs), ST-GNN. 3 seeds; paired tests per day (Holm), and bottleneck events (G3).
Outputs results/<park>/<timestamp>_sparse/: metrics.csv, events.csv, stats.json, predictions.npz, models/*.pt
"""
import argparse
import json

import numpy as np
import pandas as pd
import torch

from src.config import RESULTS, load_config
from src.data.build_dataset import access_points
from src.eval.bottlenecks import capacity_at_once, counts, scores
from src.eval.metrics import paired_tests
from src.models.baselines import HistoricalAverage
from src.run_benchmark import evaluate
from src.eval.data import TrailData
from src.train.trainer import predict, train
from src.utils import new_run_dir

NEURAL = ["lstm", "gru_nograph", "stgnn"]


def settings(data):
    gate = np.isin(data.segment_poi, list(access_points(data.cfg)))
    return {"gate": gate, "zero": np.zeros(data.N, bool)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--settings", nargs="+", default=["gate", "zero"])
    ap.add_argument("--seeds", type=int, nargs="+", default=[42, 43, 44])
    a = ap.parse_args()
    cfg = load_config()
    if a.quick:
        cfg["train"].update(epochs=1)
        a.seeds = a.seeds[:1]
    from src.config import PARK
    data = TrailData(cfg)
    te = data.origins("test")
    y, open_ = data.targets(te)
    cap = capacity_at_once(cfg, PARK)
    every = np.ones(data.N, bool)
    run = new_run_dir("sparse" + ("_quick" if a.quick else ""), cfg)
    (run / "models").mkdir()
    logf = open(run / "log.txt", "w", encoding="utf-8")

    def log(m):
        print(m, flush=True)
        logf.write(m + "\n")
        logf.flush()

    sets = settings(data)
    interior = np.where(~sets["gate"])[0]
    log(f"gates: {np.where(sets['gate'])[0].tolist()}; scored interior segments: {len(interior)}")
    rows, events, stats, saved = [], [], {}, {}
    ha = HistoricalAverage().fit(data, every).predict(data, te)       # simulation prior (no counts needed)
    for name in a.settings:
        sensed = sets[name]
        day_err, preds = {}, {"HA": [ha]}
        r, day_err["HA"] = evaluate("HA", ha, data, te, interior, cfg, {"setting": name})
        rows.append(r)
        for kind in NEURAL:
            ps, des = [], []
            for s in a.seeds:
                model, scale = train(data, kind, sensed, cfg, s, log=log, loss_nodes=every)
                p = predict(model, data, te, sensed, scale)
                r, de = evaluate(kind, p, data, te, interior, cfg, {"setting": name, "seed": s})
                rows.append(r)
                ps.append(p), des.append(de)
                torch.save({"state_dict": model.state_dict(), "scale": scale, "kind": kind, "sensed": sensed,
                            "loss_nodes": every, "seed": s}, run / "models" / f"{name}_{kind}_s{s}.pt")
                log(f"[{name}] {kind} seed={s} MAE={r['MAE']:.3f} RMSE={r['RMSE']:.3f}")
            day_err[kind], preds[kind] = np.mean(des, 0), ps
            saved[f"{name}_{kind}"] = ps[0].astype(np.float32)
        stats[name] = paired_tests(day_err, "stgnn")
        for kind, ps in preds.items():
            for ev, thr in (("over", 1.0), ("busy", cfg["capacity"]["busy_utilisation"])):
                cs = [counts(p, y, open_, cap, interior, thr) for p in ps]
                sc = pd.DataFrame([scores(c) for c in cs]).mean()
                events.append({"setting": name, "model": kind, "event": ev, "seeds": len(ps), **sc.round(4).to_dict()})
    df = pd.DataFrame(rows)
    df.to_csv(run / "metrics.csv", index=False)
    pd.DataFrame(events).to_csv(run / "events.csv", index=False)
    (run / "stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    np.savez_compressed(run / "predictions.npz", origins=te, interior=interior, HA=ha.astype(np.float32), **saved)
    if not a.quick:
        (RESULTS / "LATEST_SPARSE").write_text(run.name, encoding="utf-8")
    log(df.groupby(["setting", "model"])[["MAE", "RMSE"]].agg(["mean", "std"]).round(3).to_string())
    ev = pd.DataFrame(events)
    log(ev[ev.event == "over"][["setting", "model", "precision", "recall", "F1"]].to_string(index=False))
    log(json.dumps(stats, indent=1))
    log(f"done -> {run}")


if __name__ == "__main__":
    main()
