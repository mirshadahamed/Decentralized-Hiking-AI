"""NFR4: a range around every forecast ("between 12 and 31 people, 9 times in 10"), by split conformal prediction.

    python -m src.eval.conformal                 (the deployed model, src.serve.predict.load_model)
    python -m src.eval.conformal --run <run>     (another run's temporal_stgnn_s42 / gate_stgnn_s42 model)

On the validation year the deployed model forecasts each day from midnight (as it does in service). Residuals
(counted - forecast, open hours, every segment) are grouped by the size of the forecast, because a forecast of 2
people is off by a person or two and one of 200 by dozens. Per group, the residual quantiles with the finite-sample
correction of split conformal prediction (Vovk et al. 2005; Angelopoulos & Bates 2023) give a range that contains
the true count with probability >= level on exchangeable days. A group with fewer than MIN_N residuals (the
largest forecasts are rare) takes the range of the nearest smaller group that has enough, scaled by the ratio of
the group sizes (errors grow about in proportion to the forecast); with none below, all residuals. Scored on the test year 2025: coverage (overall, per group, and at busy segment-hours, which conformal
does NOT guarantee) and mean width, against one range for all forecast sizes.
Outputs results/<park>/<timestamp>_conformal/: table.json (what src.serve.predict reads), scores.csv;
results/<park>/LATEST_CONFORMAL.
"""
import argparse
import json

import numpy as np
import pandas as pd

from src.config import PARK, RESULTS, load_config
from src.eval.bottlenecks import capacity_at_once
from src.eval.data import TrailData
from src.serve.predict import load_model, model_inputs
from src.train.trainer import predict
from src.utils import new_run_dir

EDGES = [0.0, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0, 200.0]     # forecast people: group lower edges
LEVELS = (0.8, 0.9)
MIN_N = 200


def _q(r: np.ndarray, level: float) -> tuple:
    """(lower, upper) residual offsets for a central range at `level`, finite-sample corrected."""
    n, a = len(r), 1 - level
    lo = np.quantile(r, max(0.0, np.floor((n + 1) * a / 2) / n), method="lower")
    hi = np.quantile(r, min(1.0, np.ceil((n + 1) * (1 - a / 2)) / n), method="higher")
    return float(lo), float(hi)


def group(pred: np.ndarray, edges=EDGES) -> np.ndarray:
    return np.clip(np.searchsorted(np.asarray(edges), pred, side="right") - 1, 0, len(edges) - 1)


def calibrate(pred: np.ndarray, y: np.ndarray, levels=LEVELS, edges=EDGES) -> dict:
    """pred, y: 1-d (open segment-hours of the calibration days). -> {"edges", "<level>": [[lo, hi] per group]}"""
    g, r = group(pred, edges), y - pred
    out = {"edges": list(edges), "n": np.bincount(g, minlength=len(edges)).tolist()}
    for lv in levels:
        pooled, rows, last = _q(r, lv), [], None
        for k in range(len(edges)):
            if (g == k).sum() >= MIN_N:
                rows.append(list(_q(r[g == k], lv)))
                last = k
            elif last is not None and edges[last] > 0:
                f = edges[k] / edges[last]
                rows.append([rows[last][0] * f, rows[last][1] * f])
            else:
                rows.append(list(pooled))
        out[str(lv)] = rows
    return out


def bounds(pred: np.ndarray, table: dict, level: float = 0.9) -> tuple:
    """(low, high) people for forecasts `pred` (any shape); never below 0."""
    off = np.asarray(table[str(level)])[group(pred, table["edges"])]
    return np.clip(pred + off[..., 0], 0, None), np.clip(pred + off[..., 1], 0, None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default=None, help="model run (default: the deployed one)")
    a = ap.parse_args()
    cfg = load_config()
    data = TrailData(cfg)
    model, scale, run_name = load_model(data, cfg, a.run)
    sensed = model_inputs(model, data)
    run = new_run_dir("conformal", cfg)

    def open_values(split):
        o = data.origins(split)
        p = predict(model, data, o, sensed, scale)
        y, om = data.targets(o)
        m = np.broadcast_to(om[:, :, None], p.shape)
        return p[m], y[m], m

    pv, yv, _ = open_values("val")
    table = {"model_run": run_name, "kind": "stgnn", "seed": 42, **calibrate(pv, yv)}
    flat = {"edges": [0.0], "n": [len(pv)], **{str(lv): [list(_q(yv - pv, lv))] for lv in LEVELS}}

    pt, yt, m = open_values("test")
    cap = np.broadcast_to(capacity_at_once(cfg, PARK)[None, None, :], m.shape)[m]
    busy = yt >= cfg["capacity"]["busy_utilisation"] * cap
    rows = []
    for name, tb in (("by forecast size", table), ("one range", flat)):
        for lv in LEVELS:
            lo, hi = bounds(pt, tb, lv)
            inside = (yt >= lo) & (yt <= hi)
            rows.append({"method": name, "level": lv, "coverage": float(inside.mean()),
                         "coverage_busy": float(inside[busy].mean()) if busy.any() else np.nan,
                         "mean_width": float((hi - lo).mean()), "n": int(len(yt)), "n_busy": int(busy.sum())})
            if name == "by forecast size":
                g = group(pt, tb["edges"])
                for k, e in enumerate(tb["edges"]):
                    if (g == k).any():
                        rows.append({"method": f"group >= {e:g}", "level": lv, "coverage": float(inside[g == k].mean()),
                                     "mean_width": float((hi - lo)[g == k].mean()), "n": int((g == k).sum())})
    df = pd.DataFrame(rows)
    df.to_csv(run / "scores.csv", index=False)
    (run / "table.json").write_text(json.dumps(table, indent=2), encoding="utf-8")
    (RESULTS / "LATEST_CONFORMAL").write_text(run.name, encoding="utf-8")
    print(df.round(3).to_string(index=False))
    print(f"model {run_name}; done -> {run}")


if __name__ == "__main__":
    main()
