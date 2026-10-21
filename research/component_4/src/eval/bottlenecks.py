"""G3 / claim C3: is the day-ahead forecast a defensible *bottleneck* forecast, not just a low-error one?

    python -m src.eval.bottlenecks                  (both parks; re-uses the trained benchmark models, no training)

An event is a segment-hour (open hours, test year 2025) in which the people on a segment exceed what it holds at
Cifuentes social spacing (`capacity_at_once`: groups of 10, 50 m apart) - the bottleneck the app shows in red.
A secondary event, "busy", uses >= busy_utilisation x capacity (0.8).

For every model of the benchmark runs (all seeds; temporal protocol = every segment counted, spatial protocol =
the held-out block, i.e. segments WITHOUT counts):
  precision, recall, F1, CSI of segment-hour events
  segment-day hit rate: a segment-day with real events counts as caught if the forecast flags that segment
                        within +-1 h of a real event; false-alarm segment-days likewise
  day level:            days with any bottleneck - caught / false alarms
  warning               hours between the forecast (issued at midnight) and the caught events
Model comparison: bootstrap over days (2,000 resamples) of the F1 difference ST-GNN - each model, 95 % interval.
Outputs results/<park>/<timestamp>_bottlenecks/: metrics.csv, tests.json
"""
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import torch

from src.config import DEFAULT_PARK, RESULTS, ROOT, load_config, processed_dir
from src.eval.data import TrailData
from src.models.baselines import HistoricalAverage
from src.train.trainer import build_model, predict
from src.utils import new_run_dir

RUNS = {  # temporal (every segment counted) and spatial (held-out blocks), 3 seeds each
    "horton_plains": {"temporal": ["20261020_020459_benchmark_p04", "20261015_095519_benchmark"],
                      "spatial": ["20261021_013444_benchmark_p04s"]},
    "adams_peak": {"temporal": ["20261020_002150_benchmark_p04", "20261016_000119_benchmark"],
                   "spatial": ["20261020_110028_benchmark_p04s"]},
}
KINDS = ["lstm", "gru_nograph", "stgnn"]


def results_dir(park: str) -> Path:
    return ROOT / "results" if park == DEFAULT_PARK else ROOT / "results" / park


def capacity_at_once(cfg, park) -> np.ndarray:
    seg = gpd.read_file(processed_dir(park) / "segments.geojson").sort_values("seg_id")
    c = cfg["capacity"]
    return (seg.length_m.values / (c["group_gap_m"] + c["group_size"] * c["space_per_person_m"]) * c["group_size"])


def counts(pred, y, open_, cap, nodes, thr=1.0):
    """Daily TP / FP / FN of segment-hour events, segment-day hits and warning hours. pred, y: [D, H, N]."""
    open3 = open_[:, :, None].astype(bool)
    p = (pred[:, :, nodes] > thr * cap[nodes]) & open3
    t = (y[:, :, nodes] > thr * cap[nodes]) & open3
    tp, fp, fn = (p & t).sum((1, 2)), (p & ~t).sum((1, 2)), (~p & t).sum((1, 2))
    # segment-day: caught if a forecast event lies within +-1 h of a real one
    near = p | np.roll(p, 1, axis=1) | np.roll(p, -1, axis=1)
    sd_true, sd_pred = t.any(1), p.any(1)                                  # [D, n]
    sd_hit = (t & near).any(1)
    hours = np.broadcast_to(np.arange(pred.shape[1])[None, :, None], t.shape)
    warn = np.where(p & t, hours, np.nan)
    return {"tp": tp, "fp": fp, "fn": fn, "sd_true": sd_true.sum(1), "sd_hit": sd_hit.sum(1),
            "sd_false": (sd_pred & ~sd_true).sum(1), "day_true": t.any((1, 2)), "day_pred": p.any((1, 2)),
            "warn_sum": np.nansum(warn, (1, 2)), "warn_n": np.isfinite(warn).sum((1, 2))}


def scores(c: dict) -> dict:
    tp, fp, fn = c["tp"].sum(), c["fp"].sum(), c["fn"].sum()
    prec = tp / max(tp + fp, 1e-9)
    rec = tp / max(tp + fn, 1e-9)
    dt, dp = np.asarray(c["day_true"], bool), np.asarray(c["day_pred"], bool)
    return {
        "events": int(round(tp + fn)), "precision": prec, "recall": rec,
        "F1": 2 * prec * rec / max(prec + rec, 1e-9), "CSI": tp / max(tp + fp + fn, 1e-9),
        "segment_day_hit_rate": c["sd_hit"].sum() / max(c["sd_true"].sum(), 1e-9),
        "false_alarm_segment_days": float(c["sd_false"].sum()),
        "bottleneck_days": int(dt.sum()), "days_caught": int((dt & dp).sum()), "false_alarm_days": int((~dt & dp).sum()),
        "warning_hours_mean": c["warn_sum"].sum() / max(c["warn_n"].sum(), 1e-9),
    }


def f1_of(c, idx):
    tp, fp, fn = c["tp"][idx].sum(), c["fp"][idx].sum(), c["fn"][idx].sum()
    return 2 * tp / max(2 * tp + fp + fn, 1e-9)


def bootstrap_diff(a: dict, b: dict, n=2000, seed=0) -> dict:
    rng = np.random.default_rng(seed)
    D = len(a["tp"])
    diffs = np.array([f1_of(a, i) - f1_of(b, i) for i in (rng.integers(0, D, D) for _ in range(n))])
    return {"F1_diff": float(f1_of(a, np.arange(D)) - f1_of(b, np.arange(D))),
            "ci95": [float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))],
            "share_positive": float((diffs > 0).mean())}


def mean_counts(cs: list) -> dict:
    """Average the daily counts of several seeds (event counts become expected counts)."""
    return {k: (np.mean([c[k] for c in cs], 0) if k not in ("day_true",) else cs[0][k]) for k in cs[0]} | \
        {"day_pred": np.mean([c["day_pred"] for c in cs], 0) >= 0.5}


def checkpoints(park, protocol):
    out = {}
    for run in RUNS[park][protocol]:
        for p in sorted((results_dir(park) / run / "models").glob(f"{'temporal' if protocol == 'temporal' else 'spatial'}*_*_s*.pt")):
            ck = torch.load(p, weights_only=False)
            if ck["kind"] not in KINDS:
                continue
            fold = p.stem.split("_")[0]
            key = (fold, ck["kind"])
            if key in out and out[key][0] != run:                 # first run listed wins (the 3-seed one)
                continue
            out.setdefault(key, (run, []))[1].append(ck)
    return {k: v[1] for k, v in out.items()}


def evaluate_park(park: str, log=print) -> tuple[list, dict]:
    cfg = load_config(park=park)
    data = TrailData(cfg, path=processed_dir(park) / "dataset.npz")
    te = data.origins("test")
    y, open_ = data.targets(te)
    cap = capacity_at_once(cfg, park)
    busy = cfg["capacity"]["busy_utilisation"]
    rows, tests = [], {}
    for protocol in ("temporal", "spatial"):
        cks = checkpoints(park, protocol)
        folds = sorted({f for f, _ in cks})
        per_model = {}                                             # kind -> (counts over all folds, counts busy)
        for fold in folds:
            sensed = next(iter(c for (f, _), cs in cks.items() if f == fold for c in cs))["sensed"]
            nodes = np.arange(data.N) if protocol == "temporal" else np.where(~sensed)[0]
            preds = {"HA": [HistoricalAverage().fit(data, sensed).predict(data, te)]}
            for (f, kind), cs in cks.items():
                if f != fold:
                    continue
                preds[kind] = []
                for ck in cs:
                    m = build_model(data, kind, cfg["train"]["hidden"])
                    m.load_state_dict(ck["state_dict"])
                    preds[kind].append(predict(m.eval(), data, te, ck["sensed"], ck["scale"]))
            for kind, ps in preds.items():
                for name, thr in (("over", 1.0), ("busy", busy)):
                    c = mean_counts([counts(p, y, open_, cap, nodes, thr) for p in ps])
                    prev = per_model.get((kind, name))
                    per_model[(kind, name)] = c if prev is None else {
                        k: (prev[k] + c[k] if k not in ("day_true", "day_pred") else prev[k] | c[k]) for k in c}
            log(f"[{park} {protocol} {fold}] {sorted(preds)}")
        for (kind, name), c in per_model.items():
            n_seeds = 1 if kind == "HA" else len(next(cs for (f, k), cs in cks.items() if k == kind))
            rows.append({"park": park, "protocol": protocol, "event": name, "model": kind, "seeds": n_seeds,
                         **{k: (round(float(v), 4) if isinstance(v, float) else v) for k, v in scores(c).items()}})
        for name in ("over", "busy"):
            if ("stgnn", name) in per_model:
                tests[f"{protocol}_{name}"] = {
                    other: bootstrap_diff(per_model[("stgnn", name)], per_model[(other, name)])
                    for other in ("HA", "lstm", "gru_nograph") if (other, name) in per_model}
    return rows, tests


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--parks", nargs="+", default=list(RUNS))
    a = ap.parse_args()
    run = new_run_dir("bottlenecks", load_config(park="horton_plains"))
    logf = open(run / "log.txt", "w", encoding="utf-8")

    def log(m):
        print(m, flush=True)
        logf.write(m + "\n")

    rows, tests = [], {}
    for park in a.parks:
        r, t = evaluate_park(park, log)
        rows += r
        tests[park] = t
    df = pd.DataFrame(rows)
    df.to_csv(run / "metrics.csv", index=False)
    (run / "tests.json").write_text(json.dumps(tests, indent=2), encoding="utf-8")
    (RESULTS / "LATEST_BOTTLENECKS").write_text(run.name, encoding="utf-8")
    cols = ["park", "protocol", "event", "model", "events", "precision", "recall", "F1", "segment_day_hit_rate",
            "days_caught", "bottleneck_days", "false_alarm_days", "warning_hours_mean"]
    log(df[df.event == "over"][cols].round(3).to_string(index=False))
    log(json.dumps(tests, indent=1))
    log(str(run))


if __name__ == "__main__":
    main()
