"""Objective O3 / RQ5: pretrain the ST-GNN on dense urban traffic (METR-LA, PEMS-BAY), as in the proposal.

    python -m src.pretrain.traffic                       # pretrain on METR-LA, then continue on PEMS-BAY
Data (public, Hugging Face mirror TorchSpatiotemporal/ProcessedDatasets, traffic/metr_la.zip, pems_bay.zip)
unpacked in data/external/traffic/<name>/unzipped/ (not committed).

To make the pretrained weights fit the trail model unchanged, every traffic sensor is turned into the SAME
input layout as a trail segment (TrailData.batch):
  load     congestion = 1 - speed / free-flow speed (95th percentile of the sensor), hourly mean of the 5-min
           readings; missing readings (speed 0) are left out of the mean - the traffic analogue of people on a segment
  covariates (same 17 names, same order): hour / weekday / month cycles, weekend, US public holiday, is_open = 1;
           the Sri Lankan-only flags (Poya, school holiday, long weekend) and the weather columns are 0
           (= their average after scaling) because they do not exist for these roads
  static   13 segment descriptions = 0 (no trail descriptions for road sensors)
  graph    DCRNN's Gaussian kernel on road distances: w = exp(-(d / sigma)^2), kept if w >= 0.1
Splits: first 70 % train, next 10 % validation, last 20 % test, day-ahead forecasts from midnight (like the trail).
Outputs results/<timestamp>_pretrain/: traffic_<kind>_s<seed>.pt, metrics.json
"""
import argparse
import json
from datetime import datetime

import h5py
import holidays
import numpy as np
import pandas as pd
import torch

from src.config import DATA, RESULTS, load_config, processed_dir
from src.eval.data import TrailData
from src.eval.metrics import summary
from src.models.baselines import HistoricalAverage
from src.train.trainer import predict, train
from src.utils import new_run_dir, set_seed

TRAFFIC = DATA / "external" / "traffic"
SETS = {"metr_la": ("metr_la.h5", "distances_la.csv"), "pems_bay": ("pems_bay.h5", "distances_bay.csv")}


def _read(name):
    h5, dist = SETS[name]
    d = TRAFFIC / name / "unzipped"
    with h5py.File(d / h5, "r") as f:
        speed = f["data/block0_values"][:].astype(np.float32)               # [T5, N]
        sensors = [s.decode() for s in f["data/block0_items"][:]]
        t = pd.to_datetime(f["data/axis1"][:])
    dd = pd.read_csv(d / dist)
    return speed, sensors, t, dd


def _adjacency(sensors, dd):
    idx = {s: i for i, s in enumerate(sensors)}
    n = len(sensors)
    D = np.full((n, n), np.inf)
    for a, b, dist in dd.iloc[:, :3].to_numpy():
        i, j = idx.get(str(int(a))), idx.get(str(int(b)))
        if i is not None and j is not None:
            D[i, j] = dist
    sigma = D[np.isfinite(D)].std()
    W = np.exp(-np.square(D / sigma))
    W[W < 0.1] = 0
    np.fill_diagonal(W, 0)
    src, dst = np.nonzero(W)
    return torch.tensor(np.stack([src, dst]), dtype=torch.long), torch.tensor(W[src, dst], dtype=torch.float32)


class TrafficData(TrailData):
    """A traffic network in the trail model's input layout (same covariate and static columns)."""

    def __init__(self, name: str, trail: TrailData, cfg: dict):
        speed, sensors, t5, dd = _read(name)
        speed[speed <= 0] = np.nan
        free = np.nanpercentile(speed, 95, axis=0)
        cong = np.clip(1 - speed / free[None], 0, 1)
        hourly = pd.DataFrame(cong, index=t5).resample("1h").mean()
        hourly = hourly.interpolate(limit=3).fillna(hourly.mean())          # short gaps only; rest = sensor mean
        self.cfg, self.name = cfg, name
        self.times = hourly.index
        self.y = (hourly.values * 100).astype(np.float32)                   # congestion in %
        self.y_true = self.y
        self.cov_names = list(trail.cov_names)
        self.cov = self._covariates(self.times, self.cov_names)
        n_static = trail.static.shape[1]
        self.static = np.zeros((len(sensors), n_static), np.float32)
        self.static_names = list(trail.static_names)
        self.edge_index, self.edge_weight = _adjacency(sensors, dd)
        self.T, self.N = self.y.shape
        self.L, self.H = cfg["task"]["input_steps"], cfg["task"]["horizon"]
        days = self.T // 24
        self.train_end, self.val_end = int(days * 0.7) * 24, int(days * 0.8) * 24
        self.open = np.ones(self.T, bool)                                    # roads are always open
        self.train_start = 0
        mu, sd = self.cov[:self.train_end].mean(0), self.cov[:self.train_end].std(0)
        # a column that never varies in the (short) training months carries no information; scaling it by ~0
        # would blow up rare later values (e.g. a public holiday only in the validation month) -> keep it at 0
        self.cov_s = np.where(sd[None] > 1e-3, (self.cov - mu) / np.maximum(sd, 1e-3), 0.0).astype(np.float32)
        self.static_s = self.static.copy()
        self.segment_trail = np.array(["road"] * self.N)
        self.segment_poi = np.array([""] * self.N)
        self.segment_walk_position = np.linspace(0, 1, self.N)
        self.daily_visitors = np.zeros(days)
        self.daily_visitors_by_trail = np.zeros((days, 1))
        self.trails = ["road"]

    @staticmethod
    def _covariates(times, names):
        h, dow, mon = times.hour.values, times.dayofweek.values, times.month.values
        us = holidays.US(years=sorted(set(times.year)))
        hol = np.array([d in us for d in times.date], dtype=np.float32)
        cols = {"hour_sin": np.sin(2 * np.pi * h / 24), "hour_cos": np.cos(2 * np.pi * h / 24),
                "dow_sin": np.sin(2 * np.pi * dow / 7), "dow_cos": np.cos(2 * np.pi * dow / 7),
                "month_sin": np.sin(2 * np.pi * mon / 12), "month_cos": np.cos(2 * np.pi * mon / 12),
                "is_open": np.ones(len(times)), "is_weekend": (dow >= 5).astype(float), "is_holiday": hol}
        return np.column_stack([cols.get(n, np.zeros(len(times))) for n in names]).astype(np.float32)


def pretrain(kind: str = "stgnn", seed: int = 42, epochs: int | None = None, log=print):
    """METR-LA, then PEMS-BAY (continued from the METR-LA weights). Returns the final state dict and metrics."""
    cfg = load_config(park="horton_plains")
    trail = TrailData(cfg, path=processed_dir("horton_plains") / "dataset.npz")
    tc = dict(cfg["train"])
    if epochs:
        tc["epochs"] = epochs
    cfg = cfg | {"train": tc}
    state, metrics = None, {}
    for name in ("metr_la", "pems_bay"):
        d = TrafficData(name, trail, cfg)
        every = np.ones(d.N, bool)
        m, scale = train(d, kind, every, cfg, seed, log=lambda x: log(f"[{name}] {x}"), init_state=state)
        te = d.origins("test")
        y, om = d.targets(te)
        p = predict(m, d, te, every, scale)
        ha = HistoricalAverage()
        ha.dt = np.zeros(d.T, int)                                           # traffic: hour-of-day profile
        ha.hr = np.asarray(d.times.hour)
        tr = slice(0, d.train_end)
        ha.table = np.stack([d.y[tr][ha.hr[tr] == hh].mean(0) for hh in range(24)])[None]
        metrics[name] = {"sensors": d.N, "hours": d.T, "edges": int(d.edge_index.shape[1]),
                         "stgnn": summary(p, y, om, np.arange(d.N)),
                         "hist_avg": summary(ha.predict(d, te), y, om, np.arange(d.N))}
        log(f"[{name}] test MAE {metrics[name]['stgnn']['MAE']:.2f} (historical average "
            f"{metrics[name]['hist_avg']['MAE']:.2f}) congestion %")
        state = {k: v.clone() for k, v in m.state_dict().items() if k != "adj"}
    return state, metrics


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", default="stgnn", choices=["stgnn", "stgnn_lstm", "gru_nograph", "lstm"])
    ap.add_argument("--seeds", type=int, nargs="+", default=[42])
    ap.add_argument("--epochs", type=int, default=None)
    a = ap.parse_args()
    cfg = load_config()
    run = new_run_dir("pretrain", cfg)
    logf = open(run / "log.txt", "w", encoding="utf-8")

    def log(msg):
        print(msg, flush=True)
        logf.write(msg + "\n")
        logf.flush()

    out = {}
    for s in a.seeds:
        set_seed(s)
        state, met = pretrain(a.kind, s, a.epochs, log)
        torch.save({"state_dict": state, "kind": a.kind, "seed": s, "source": "METR-LA -> PEMS-BAY",
                    "created": datetime.now().isoformat()}, run / f"traffic_{a.kind}_s{s}.pt")
        out[s] = met
    (run / "metrics.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    (RESULTS / "LATEST_PRETRAIN").write_text(run.name, encoding="utf-8")
    log(f"done -> {run}")
