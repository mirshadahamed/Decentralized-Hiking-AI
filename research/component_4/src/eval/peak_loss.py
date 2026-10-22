"""G8 / claim C3: does a peak-aware loss stop the ST-GNN from smoothing away bottlenecks on segments without counts?

    python -m src.eval.peak_loss                        (both parks, spatial CV, 3 seeds; hours on CPU)
    python -m src.eval.peak_loss --parks horton_plains --weight 4 --quick

RQ1b found that, on held-out segments, every model under-forecasts over-capacity hours and the ST-GNN flags fewest
(recall 0.26 at Horton Plains), because a plain MAE rewards smoothing rare peaks. Here the same ST-GNN is trained
with errors at or above `threshold` x capacity_at_once weighted `weight` times (trainer.masked_l1, peak=...), on the
same spatial blocks and seeds as the benchmark, and compared with the benchmark's ST-GNN and LSTM:
  MAE on held-out segments, and precision / recall / F1 of over-capacity segment-hours (bootstrap over days).
Outputs results/<timestamp>_peak_loss/: metrics.csv, tests.json, models/
"""
import argparse
import json

import numpy as np
import pandas as pd
import torch

from src.config import RESULTS, load_config, processed_dir
from src.eval.bottlenecks import (RUNS, bootstrap_diff, capacity_at_once, checkpoints, counts, mean_counts,
                                  scores)
from src.eval.data import TrailData
from src.train.trainer import build_model, predict, train
from src.utils import new_run_dir


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--parks", nargs="+", default=list(RUNS))
    ap.add_argument("--weight", type=float, default=4.0, help="weight of errors on over-threshold hours")
    ap.add_argument("--threshold", type=float, default=0.8, help="x capacity_at_once (0.8 = 'busy')")
    ap.add_argument("--quick", action="store_true", help="1 seed, 2 epochs, first fold only")
    a = ap.parse_args()
    run = new_run_dir("peak_loss", load_config(park="horton_plains") | {"peak_loss": vars(a)})
    (run / "models").mkdir(exist_ok=True)
    logf = open(run / "log.txt", "w", encoding="utf-8")

    def log(m):
        print(m, flush=True)
        logf.write(m + "\n")
        logf.flush()

    rows, tests = [], {}
    for park in a.parks:
        cfg = load_config(park=park)
        if a.quick:
            cfg["train"] = cfg["train"] | {"epochs": 2}
        data = TrailData(cfg, path=processed_dir(park) / "dataset.npz")
        te = data.origins("test")
        y, open_ = data.targets(te)
        cap = capacity_at_once(cfg, park)
        base = checkpoints(park, "spatial")                         # benchmark ST-GNN / LSTM per fold
        folds = sorted({f for f, _ in base})[:1 if a.quick else None]
        seeds = cfg["train"]["seeds"][:1 if a.quick else None]
        per = {}                                                    # model -> summed daily counts over folds
        mae = {}
        for fold in folds:
            ref = base[(fold, "stgnn")]
            sensed = ref[0]["sensed"]
            nodes = np.where(~sensed)[0]
            preds = {"stgnn_peak": []}
            for s in seeds:
                m, scale = train(data, "stgnn", sensed, cfg, s, log=lambda x: log(f"[{park} {fold}] {x}"),
                                 peak=(a.threshold * cap, a.weight))
                torch.save({"state_dict": m.state_dict(), "scale": scale, "kind": "stgnn", "sensed": sensed,
                            "peak": [a.threshold, a.weight]}, run / "models" / f"{park}_{fold}_stgnn_peak_s{s}.pt")
                preds["stgnn_peak"].append(predict(m.eval(), data, te, sensed, scale))
            for kind in ("stgnn", "lstm"):
                preds[kind] = []
                for ck in base[(fold, kind)][:len(seeds)]:
                    mm = build_model(data, kind, cfg["train"]["hidden"])
                    mm.load_state_dict(ck["state_dict"])
                    preds[kind].append(predict(mm.eval(), data, te, ck["sensed"], ck["scale"]))
            om = open_[:, :, None].astype(bool) & np.ones((1, 1, len(nodes)), bool)
            for kind, ps in preds.items():
                c = mean_counts([counts(p, y, open_, cap, nodes) for p in ps])
                prev = per.get(kind)
                per[kind] = c if prev is None else {
                    k: (prev[k] + c[k] if k not in ("day_true", "day_pred") else prev[k] | c[k]) for k in c}
                err = np.mean([np.abs(p[:, :, nodes] - y[:, :, nodes])[om].mean() for p in ps])
                mae.setdefault(kind, []).append(err)
                log(f"[{park} {fold}] {kind}: MAE held-out {err:.3f}")
        for kind, c in per.items():
            rows.append({"park": park, "model": kind, "MAE_heldout": round(float(np.mean(mae[kind])), 4),
                         **{k: (round(float(v), 4) if isinstance(v, float) else v) for k, v in scores(c).items()}})
        tests[park] = {other: bootstrap_diff(per["stgnn_peak"], per[other]) for other in ("stgnn", "lstm")}
        log(json.dumps(tests[park]))
    df = pd.DataFrame(rows)
    df.to_csv(run / "metrics.csv", index=False)
    (run / "tests.json").write_text(json.dumps(tests, indent=2), encoding="utf-8")
    if not a.quick:
        (RESULTS / "LATEST_PEAK_LOSS").write_text(run.name, encoding="utf-8")
    log(df[["park", "model", "MAE_heldout", "precision", "recall", "F1"]].to_string(index=False))
    log(str(run))


if __name__ == "__main__":
    main()
