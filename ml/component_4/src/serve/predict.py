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
              "see ml/component_4/docs/assumptions.md.")


def load_model(data, cfg, run_name=None, kind="stgnn", seed=42):
    run = RESULTS / (run_name or (RESULTS / "LATEST").read_text(encoding="utf-8").strip())
    ck = torch.load(run / "models" / f"temporal_{kind}_s{seed}.pt", weights_only=False)
    model = build_model(data, kind, cfg["train"]["hidden"])
    model.load_state_dict(ck["state_dict"])
    return model, ck["scale"], run.name


def expected_visitors(data, day_idx):
    """Demand expected from the calendar alone: train-period mean for the same day type and month."""
    daily_cov = data.cov[::24]
    dt = day_type(daily_cov, data.cov_names)
    months = np.asarray(data.times[::24].month)
    train_days = data.train_end // 24
    sel = (dt[:train_days] == dt[day_idx]) & (months[:train_days] == months[day_idx])
    return float(data.daily_visitors[:train_days][sel].mean())


def build_forecast(data, cfg, seg, date: str, model=None, scale=None, run=None) -> dict:
    """Forecast + capacity for one date as a dict (no file written). model=None -> NFR2 fallback."""
    origin = int(np.searchsorted(data.times, pd.Timestamp(date)))
    if origin >= data.T or data.times[origin] != pd.Timestamp(date) or origin < data.L:
        raise ValueError(f"{date} is outside the dataset")
    sensed = np.ones(data.N, bool)

    if model is not None:
        fc = predict(model, data, np.array([origin]), sensed, scale)[0]       # [24, N]
        source = {"model": "stgnn", "run": run}
        rain = np.expm1(data.cov[origin:origin + 24, data.cov_names.index("precip_log1p")])
    else:                                                                    # NFR2 graceful fallback
        fc = HistoricalAverage().fit(data, sensed).predict(data, np.array([origin]))[0]
        source = {"model": "historical_average", "reason": "no fresh weather forecast"}
        rain = np.zeros(24)
    cap = capacity(seg, fc, rain, expected_visitors(data, origin // 24), cfg["capacity"], cfg["simulator"])

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
    busy = [s for s in out["segments"] if s["status"] != "ok"]
    print(f"{path}\nexpected visitors={out['expected_visitors']} recommended quota={out['recommended_daily_quota']} "
          f"(classic Cifuentes {out['classic_cifuentes_quota']}) limiting segment={out['limiting_segment']} "
          f"trail factors={out['trail_correction_factors']}")
    for s in busy:
        print(f"  seg {s['seg_id']:>2} {s['poi'] or '':<16} peak={s['peak_occupancy']:>6} at {s['peak_hour']:02d}:00 "
              f"holds={s['capacity_at_once']:>5} crowded_hours={s['crowded_hours_share']} {s['status']}")
