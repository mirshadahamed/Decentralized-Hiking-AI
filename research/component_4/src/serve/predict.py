"""Day-ahead forecast + Cifuentes capacity for one date, written as versioned JSON (D8, D9 / FR2-FR5, NFR2).

    python -m src.serve.predict --date 2025-05-12            # Vesak Poya (test year)
    python -m src.serve.predict --date 2025-05-12 --no-weather   # NFR2 fallback to historical average

Output: results/forecasts/forecast_<date>.json  (read-only input for Module 3 and the dashboard)
"""
import argparse
import json
from datetime import datetime

import geopandas as gpd
import numpy as np
import pandas as pd
import torch

from src.capacity.cifuentes import capacity
from src.config import PROCESSED, RESULTS, load_config
from src.eval.data import TrailData
from src.models.baselines import HistoricalAverage, day_type
from src.train.trainer import build_model, predict

SCHEMA_VERSION = "1.0"
DISCLAIMER = ("Occupancy is forecast by a model trained on a calibrated SYNTHETIC occupancy target "
              "(no segment-level counts exist for this park yet). Treat values as estimates; "
              "see research/component_4/docs/assumptions.md.")


def load_model(data, cfg, run_name=None, kind="stgnn", seed=42):
    """The deployed model. live.model_input = "gate" (G6): the sensor-sparse model of RQ10, which reads only the
    counts at the gates (what a park really has), from the latest sparse run; "all": the benchmark model that reads
    every segment. The model carries the segments it reads as `model.sensed`."""
    gate = run_name is None and cfg.get("live", {}).get("model_input") == "gate" and (RESULTS / "LATEST_SPARSE").exists()
    run = RESULTS / (run_name or (RESULTS / ("LATEST_SPARSE" if gate else "LATEST")).read_text(encoding="utf-8").strip())
    path = run / "models" / f"temporal_{kind}_s{seed}.pt"
    if not path.exists() and (run / "models" / f"gate_{kind}_s{seed}.pt").exists():
        path = run / "models" / f"gate_{kind}_s{seed}.pt"
    ck = torch.load(path, weights_only=False)
    model = build_model(data, kind, cfg["train"]["hidden"])
    model.load_state_dict(ck["state_dict"])
    model.sensed = np.asarray(ck.get("sensed", np.ones(data.N, bool)), bool)
    return model, ck["scale"], run.name


def model_inputs(model, data) -> np.ndarray:
    """Segments whose counts the model reads: only the gates (sensor-sparse model) or every segment."""
    sensed = getattr(model, "sensed", None)
    return np.ones(data.N, bool) if sensed is None else np.asarray(sensed, bool)


def inputs_note(model, data) -> str:
    s = model_inputs(model, data)
    return "every section's counts" if s.all() else f"gate counts only ({int(s.sum())} of {data.N} sections)"


def expected_visitors(data, day_idx) -> dict:
    """Demand per trail from the calendar alone: train-period mean for the same day type and month."""
    daily_cov = data.cov[::24]
    dt = day_type(daily_cov, data.cov_names)
    months = np.asarray(data.times[::24].month)
    train_days = data.train_end // 24
    sel = (dt[:train_days] == dt[day_idx]) & (months[:train_days] == months[day_idx])
    means = data.daily_visitors_by_trail[:train_days][sel].mean(0)
    return {t: float(v) for t, v in zip(data.trails, means)}


def build_forecast(data, cfg, seg, date: str, model=None, scale=None, run=None) -> dict:
    """Forecast + capacity for one date as a dict (no file written). model=None -> NFR2 fallback."""
    origin = int(np.searchsorted(data.times, pd.Timestamp(date)))
    if origin >= data.T or data.times[origin] != pd.Timestamp(date) or origin < data.L:
        raise ValueError(f"{date} is outside the dataset")
    if model is not None:
        fc = predict(model, data, np.array([origin]), model_inputs(model, data), scale)[0]       # [24, N]
        source = {"model": "stgnn", "run": run, "inputs": inputs_note(model, data)}
        rain = np.expm1(data.cov[origin:origin + 24, data.cov_names.index("precip_log1p")])
    else:                                                                    # NFR2 graceful fallback
        fc = HistoricalAverage().fit(data, np.ones(data.N, bool)).predict(data, np.array([origin]))[0]
        source = {"model": "historical_average", "reason": "no fresh weather forecast"}
        rain = np.zeros(24)
    cap = capacity(seg, fc, rain, expected_visitors(data, origin // 24), cfg["capacity"], cfg["simulator"],
                   cfg["area"]["trail_names"])

    return {"schema_version": SCHEMA_VERSION, "component": 4, "site": cfg["area"]["name"],
            "generated_at": datetime.now().isoformat(timespec="seconds"), "forecast_date": date,
            "source": source, "fallback_used": model is None, "disclaimer": DISCLAIMER, **cap}


def forecast_day(date: str, use_weather=True, run_name=None):
    cfg = load_config()
    data = TrailData(cfg)
    seg = gpd.read_file(PROCESSED / "segments.geojson")
    model, scale, run = load_model(data, cfg, run_name) if use_weather else (None, None, None)
    out = build_forecast(data, cfg, seg, date, model, scale, run)
    path = RESULTS / "forecasts" / f"forecast_{date}{'' if use_weather else '_fallback'}.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out, path


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="2025-05-12")
    ap.add_argument("--no-weather", action="store_true")
    ap.add_argument("--run", default=None)
    a = ap.parse_args()
    out, path = forecast_day(a.date, not a.no_weather, a.run)
    print(f"{path}\npark: expected={out['expected_visitors']} quota={out['recommended_daily_quota']} "
          f"(classic Cifuentes {out['classic_cifuentes_quota']})")
    for v in out["trails"].values():
        print(f"  {v['name']:<18} expected={v['expected_visitors']:>5} quota={v['recommended_daily_quota']:>5} "
              f"classic={v['classic_cifuentes_quota']:>5} limiting seg={v['limiting_segment']:>2} "
              f"bottlenecks={v['bottleneck_segments']} peak={v['peak_occupancy']}")
