"""G5: do the conclusions survive when the simulator's assumptions are wrong?

    python -m src.eval.robustness                 ($env:C4_PARK = "adams_peak" for the other park)
    python -m src.eval.robustness --quick         (3 worlds, 1 seed: checks the pipeline)

Models: the realistic-world spot-count models (LATEST_SPARSE_S1: gates + ranger spots; LSTM, GRU without graph,
ST-GNN; 3 seeds), trained once on the world we assumed (S1). Each test world changes ONE assumption of S1 and is
simulated with the same random seed. The model's inputs keep describing the ASSUMED park (segment descriptions,
forecast weather, calendar), as they would in a real park that differs from our assumptions; only the counts
come from the changed world. HA is fitted on each world's own training years (the record a park would have).
Scored like RQ11b: uncounted sections, test year 2025, day-ahead from midnight and from 10:00.
Questions: does the ST-GNN still beat the LSTM and the GRU without graph on uncounted sections (C1, C4)? Is a
network trained on wrong assumptions still better than the park's own average? How much does each degrade?
Outputs results/<park>/<timestamp>_robustness/: metrics.csv, tests.json, summary.csv;
the simulated worlds are cached in data/processed/robust/.
"""
import argparse
import copy
import json

import geopandas as gpd
import numpy as np
import pandas as pd
import torch

from src.config import PARK, PROCESSED, RESULTS, load_config
from src.data.calendar_features import build_calendar
from src.data.graph import load_walks
from src.data.weather import load_weather
from src.eval.data import TrailData
from src.eval.metrics import paired_tests
from src.eval.sparse_sensors import intraday_mae, settings
from src.models.baselines import HistoricalAverage
from src.run_benchmark import evaluate
from src.sim.simulator import simulate
from src.train.trainer import build_model, predict
from src.utils import new_run_dir

KINDS = ["lstm", "gru_nograph", "stgnn"]
SIM_KEYS = ["occ_obs", "occ_true", "daily_visitors", "daily_visitors_by_trail", "median_loop_min"]


def _scale(key, f):
    def change(p):
        p[key] = p[key] * f
    return change


def _arrive(dh):
    def change(p):
        p["arrival_early_mean_h"] += dh
        p["arrival_late_range_h"] = [x + dh for x in p["arrival_late_range_h"]]
    return change


def _flat_routes(p):
    s = p["route_share"]
    p["route_share"] = {k: 0.5 * v + 0.5 / len(s) for k, v in s.items()}


def _dwell(f):
    def change(p):
        p["dwell_minutes"] = {k: [v[0] * f, v[1]] for k, v in (p.get("dwell_minutes") or {}).items()}
        if p.get("bottleneck"):
            m, sd = p["bottleneck"]["summit_dwell_min"]
            p["bottleneck"]["summit_dwell_min"] = [m * f, sd]
    return change


def _crowd(f):
    def change(p):
        p["crowd_rho0_per_m"] *= f
    return change


def _flow(f):
    def change(p):
        p["bottleneck"]["flow_per_min"] *= f
    return change


def worlds(p: dict) -> dict:
    """name -> (what is wrong, change to the simulator parameters). 'assumed' = S1 itself."""
    w = {"assumed": ("nothing (S1 as assumed)", lambda p: None),
         "demand_-30": ("30 % fewer visitors", _scale("base_daily_visitors", 0.7)),
         "demand_+30": ("30 % more visitors", _scale("base_daily_visitors", 1.3)),
         "arrive_-1h": ("arrivals 1 h earlier", _arrive(-1.0)),
         "arrive_+1h": ("arrivals 1 h later", _arrive(1.0)),
         "routes_flat": ("trail shares half-way to equal", _flat_routes),
         "dwell_x2": ("stops at viewpoints / summit twice as long", _dwell(2.0)),
         "crowd_slow": ("crowds slow walkers twice as much", _crowd(0.5))}
    if p.get("bottleneck"):
        w["summit_-30"] = ("summit steps take 30 % fewer people a minute", _flow(0.7))
        w["summit_+30"] = ("summit steps take 30 % more people a minute", _flow(1.3))
    return w


def build_world(cfg, name, change, base_path):
    """The S1 dataset with the simulated counts of a world where one assumption is wrong (cached)."""
    out_dir = PROCESSED / "robust"
    out_dir.mkdir(exist_ok=True)
    path = out_dir / f"dataset_s1_{name}.npz"
    if path.exists():
        return path
    p = copy.deepcopy(cfg["simulator"])
    p["realism"]["enabled"] = True
    change(p)
    seg = gpd.read_file(PROCESSED / "segments.geojson")
    seg["poi"] = seg["poi"].fillna("")
    out = simulate(seg, load_walks(), load_weather(cfg), build_calendar(cfg), p, seed=cfg["seed"])
    base = np.load(base_path, allow_pickle=True)
    d = {k: base[k] for k in base.files}                 # inputs describe the assumed park
    d.update({k: np.asarray(out[k]).astype(base[k].dtype) for k in SIM_KEYS})
    np.savez_compressed(path, **d)
    return path


def load_models(run, data, cfg, seeds):
    out = {}
    for kind in KINDS:
        for s in seeds:
            ck = torch.load(run / "models" / f"spot_{kind}_s{s}.pt", weights_only=False)
            m = build_model(data, kind, cfg["train"]["hidden"])
            m.load_state_dict(ck["state_dict"])
            out[kind, s] = (m.eval(), ck["scale"])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--seeds", type=int, nargs="+", default=[42, 43, 44])
    a = ap.parse_args()
    cfg = load_config()
    base_path = PROCESSED / "dataset_s1.npz"
    src = RESULTS / (RESULTS / "LATEST_SPARSE_S1").read_text(encoding="utf-8").strip()
    ws = worlds(cfg["simulator"])
    if a.quick:
        ws = {k: ws[k] for k in list(ws)[:3]}
        a.seeds = a.seeds[:1]
    run = new_run_dir("robustness" + ("_quick" if a.quick else ""), cfg)
    logf = open(run / "log.txt", "w", encoding="utf-8")

    def log(m):
        print(m, flush=True)
        logf.write(m + "\n")
        logf.flush()

    log(f"models from {src.name}; seeds {a.seeds}; worlds {list(ws)}")
    rows, tests = [], {}
    models = None
    for name, (what, change) in ws.items():
        path = build_world(cfg, name, change, base_path)
        data = TrailData(cfg, path=path)
        if models is None:
            models = load_models(src, data, cfg, a.seeds)
        sensed = settings(data)["spot"]
        gate = settings(data)["gate"]
        te = data.origins("test")[:30] if a.quick else data.origins("test")
        uncounted = np.where(~sensed & ~gate)[0]
        every = np.ones(data.N, bool)
        ha = HistoricalAverage().fit(data, every).predict(data, te)
        r, de_ha = evaluate("HA", ha, data, te, uncounted, cfg)
        rows.append({"world": name, "what": what, "seed": np.nan, **r})
        day_err = {"HA": de_ha}
        for kind in KINDS:
            des = []
            for s in a.seeds:
                model, scale = models[kind, s]
                p = predict(model, data, te, sensed, scale)
                r, de = evaluate(kind, p, data, te, uncounted, cfg)
                r["MAE_from_10h"] = intraday_mae(model, data, sensed, scale, uncounted, 10)
                rows.append({"world": name, "what": what, "seed": s, **r})
                des.append(de)
            day_err[kind] = np.mean(des, 0)
        tests[name] = paired_tests(day_err, "stgnn")
        m = pd.DataFrame([x for x in rows if x["world"] == name]).groupby("model")["MAE"].mean()
        log(f"[{name}] " + "  ".join(f"{k} {v:.3f}" for k, v in m.items()))
    df = pd.DataFrame(rows)
    df.to_csv(run / "metrics.csv", index=False)
    (run / "tests.json").write_text(json.dumps(tests, indent=2), encoding="utf-8")

    # one row per world: mean MAE per model, change vs the assumed world, and whether each conclusion holds
    mean = df.groupby(["world", "model"])[["MAE", "MAE_from_10h"]].mean()
    summary = []
    for name, (what, _) in ws.items():
        s = {"world": name, "what": what}
        for k in ["HA"] + KINDS:
            s[f"MAE_{k}"] = float(mean.loc[(name, k), "MAE"])
        s["MAE_stgnn_from_10h"] = float(mean.loc[(name, "stgnn"), "MAE_from_10h"])
        s["stgnn_change_vs_assumed_pct"] = 100 * (s["MAE_stgnn"] / float(mean.loc[(list(ws)[0], "stgnn"), "MAE"]) - 1)
        for t in tests[name]:
            b = t["baseline"]
            s[f"stgnn_minus_{b}"] = t["mean_diff_MAE"]
            s[f"p_holm_vs_{b}"] = t["p_holm"]
            s[f"stgnn_better_than_{b}"] = bool(t["mean_diff_MAE"] < 0 and t["p_holm"] < 0.05)
        summary.append(s)
    summary = pd.DataFrame(summary)
    summary.to_csv(run / "summary.csv", index=False)
    if not a.quick:
        (RESULTS / "LATEST_ROBUSTNESS").write_text(run.name, encoding="utf-8")
    cols = ["world"] + [f"MAE_{k}" for k in ["HA"] + KINDS] + [c for c in summary.columns if c.startswith("stgnn_better")]
    log(summary[cols].round(3).to_string(index=False))
    log(f"park {PARK}; done -> {run}")


if __name__ == "__main__":
    main()
