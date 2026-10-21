"""S3 / claim C3: from a point forecast to a calibrated CHANCE of over-capacity, and a better bottleneck alert.

    python -m src.eval.uncertainty --run <sparse run folder>      (models of src.eval.sparse_sensors)

G3 showed point forecasts under-call peaks. Instead of "forecast > capacity", calibrate on the validation year:
for each predicted fullness bin (forecast / capacity_at_once), the share of segment-hours that really were over
capacity. That table (a few numbers) turns any forecast into P(over capacity) - on the server or on the phone.
The alert threshold on P is chosen on the validation year (max F1), then scored on the test year:
  Brier score and reliability of P, and precision / recall / F1 of the alert vs the point rule of G3.
Outputs <run>/uncertainty/: calibration.json (the table, per model and setting), scores.csv
"""
import argparse
import json

import numpy as np
import pandas as pd
import torch

from src.config import PARK, PROCESSED, RESULTS, load_config
from src.eval.bottlenecks import capacity_at_once
from src.eval.data import TrailData
from src.train.trainer import build_model, predict

BINS = np.array([0.0, 0.2, 0.4, 0.6, 0.8, 0.9, 1.0, 1.1, 1.25, 1.5, 2.0, np.inf])


def calibrate(util_pred: np.ndarray, over_true: np.ndarray, prior: float = 2.0) -> dict:
    """P(over | predicted fullness bin), with a light prior towards the overall rate (sparse bins)."""
    b = np.clip(np.searchsorted(BINS, util_pred, side="right") - 1, 0, len(BINS) - 2)
    base = float(over_true.mean())
    n = np.bincount(b, minlength=len(BINS) - 1)
    k = np.bincount(b, weights=over_true.astype(float), minlength=len(BINS) - 1)
    p = (k + prior * base) / (n + prior)
    p = np.maximum.accumulate(p)                                # fuller forecast -> never a lower chance
    return {"bins": [float(x) for x in BINS[:-1]], "p_over": [round(float(x), 4) for x in p], "n": n.tolist()}


def prob_over(util_pred: np.ndarray, table: dict) -> np.ndarray:
    edges = np.array(table["bins"])
    return np.array(table["p_over"])[np.clip(np.searchsorted(edges, util_pred, side="right") - 1, 0, len(edges) - 1)]


def f1(alert, truth):
    tp, fp, fn = (alert & truth).sum(), (alert & ~truth).sum(), (~alert & truth).sum()
    prec, rec = tp / max(tp + fp, 1), tp / max(tp + fn, 1)
    return prec, rec, 2 * prec * rec / max(prec + rec, 1e-9)


def _flat(pred, y, open_, cap, nodes):
    m = np.broadcast_to(open_[:, :, None].astype(bool), pred.shape)[:, :, nodes]
    u = (pred[:, :, nodes] / cap[nodes])[m]
    t = (y[:, :, nodes] > cap[nodes])[m]
    return u, t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True, help="folder of a src.eval.sparse_sensors run (results/...)")
    ap.add_argument("--world", choices=["default", "s1"], default="default")
    a = ap.parse_args()
    cfg = load_config()
    run = RESULTS / a.run if not a.run.startswith(str(RESULTS)) else __import__("pathlib").Path(a.run)
    data = TrailData(cfg, path=PROCESSED / ("dataset_s1.npz" if a.world == "s1" else "dataset.npz"))
    cap = capacity_at_once(cfg, PARK)
    va, te = data.origins("val"), data.origins("test")
    (yv, ov), (yt, ot) = data.targets(va), data.targets(te)
    pred_npz = np.load(run / "predictions.npz")
    nodes = pred_npz["interior"]
    out_dir = run / "uncertainty"
    out_dir.mkdir(exist_ok=True)
    rows, tables = [], {}
    for p in sorted((run / "models").glob("*_s42.pt")):            # one seed: the model the app would ship
        ck = torch.load(p, weights_only=False)
        setting, kind = p.stem.split("_", 1)[0], ck["kind"]
        m = build_model(data, kind, cfg["train"]["hidden"])
        m.load_state_dict(ck["state_dict"])
        pv = predict(m, data, va, ck["sensed"], ck["scale"])
        pt = predict(m, data, te, ck["sensed"], ck["scale"])
        uv, tv = _flat(pv, yv, ov, cap, nodes)
        ut, tt = _flat(pt, yt, ot, cap, nodes)
        table = calibrate(uv, tv)
        ps_v, ps_t = prob_over(uv, table), prob_over(ut, table)
        grid = np.linspace(0.05, 0.95, 19)
        best = grid[int(np.argmax([f1(ps_v >= g, tv)[2] for g in grid]))]
        point = f1(ut > 1.0, tt)
        prob = f1(ps_t >= best, tt)
        table["alert_threshold"] = round(float(best), 2)
        tables[f"{setting}_{kind}"] = table
        rel = pd.DataFrame({"p": ps_t, "t": tt}).groupby(pd.cut(ps_t, [0, .1, .3, .5, .7, .9, 1.0]), observed=True).mean()
        rows.append({"setting": setting, "model": kind, "brier": float(np.mean((ps_t - tt) ** 2)),
                     "brier_climatology": float(np.mean((tt.mean() - tt) ** 2)),
                     "point_precision": point[0], "point_recall": point[1], "point_F1": point[2],
                     "alert_threshold": float(best), "prob_precision": prob[0], "prob_recall": prob[1],
                     "prob_F1": prob[2], "reliability": json.dumps(rel.round(3).values.tolist())})
        print(rows[-1] | {"reliability": None}, flush=True)
    pd.DataFrame(rows).to_csv(out_dir / "scores.csv", index=False)
    (out_dir / "calibration.json").write_text(json.dumps(tables, indent=2), encoding="utf-8")
    print(out_dir)


if __name__ == "__main__":
    main()
