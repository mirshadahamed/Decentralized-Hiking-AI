"""Run the whole data pipeline and save data/processed/dataset.npz.

    python -m src.data.build_dataset            (re-uses cached OSM / DEM / weather downloads)
"""
import json

import geopandas as gpd
import numpy as np
import pandas as pd

from src.config import PROCESSED, load_config
from src.data.calendar_features import build_calendar
from src.data.extension_trails import build_extension_trails
from src.data.graph import build_graph
from src.data.terrain import segment_terrain
from src.data.weather import load_weather
from src.sim.simulator import simulate
from src.utils import set_seed

POIS = ["entrance", "mini_worlds_end", "worlds_end", "bakers_falls"]
STATIC_COLS = ["length_m", "grade_abs_mean", "slope_deg_mean", "twi_mean", "elev_mean",
               "tobler_fwd_min", "tobler_bwd_min"]


def hourly_covariates(index: pd.DatetimeIndex, cal: pd.DataFrame, weather: pd.DataFrame, cfg) -> pd.DataFrame:
    day = cal.reindex(index.normalize())
    h, dow, m = index.hour.values, index.dayofweek.values, index.month.values
    lo, hi = cfg["task"]["open_hours"]
    cov = pd.DataFrame({
        "hour_sin": np.sin(2 * np.pi * h / 24), "hour_cos": np.cos(2 * np.pi * h / 24),
        "dow_sin": np.sin(2 * np.pi * dow / 7), "dow_cos": np.cos(2 * np.pi * dow / 7),
        "month_sin": np.sin(2 * np.pi * (m - 1) / 12), "month_cos": np.cos(2 * np.pi * (m - 1) / 12),
        "is_open": ((h >= lo) & (h <= hi)).astype(float),
    }, index=index)
    for c in ["is_weekend", "is_holiday", "is_poya", "is_long_weekend", "is_school_holiday"]:
        cov[c] = day[c].values.astype(float)
    cov["precip_log1p"] = np.log1p(weather.precipitation.values)
    for c in ["temperature_2m", "relative_humidity_2m", "cloud_cover", "wind_speed_10m"]:
        cov[c] = weather[c].values
    return cov


def static_features(seg: gpd.GeoDataFrame, walk) -> pd.DataFrame:
    st = seg[STATIC_COLS].astype(float).copy()
    for p in POIS:
        st[f"poi_{p}"] = (seg.poi == p).astype(float)
    first = {}
    for k, (s, _) in enumerate(walk):
        first.setdefault(s, k)
    st["walk_position"] = [first[s] / len(walk) for s in range(len(seg))]
    return st


def main():
    cfg = load_config()
    set_seed(cfg["seed"])
    seg, edge_index, walk = build_graph(cfg)
    seg = segment_terrain(cfg)
    build_extension_trails(cfg)      # map layer for the planned diversion extension
    weather = load_weather(cfg)
    cal = build_calendar(cfg)
    assert len(weather) == len(cal) * 24, "weather must cover whole days"

    out = simulate(seg, walk, weather, cal, cfg["simulator"], seed=cfg["seed"])
    cov = hourly_covariates(weather.index, cal, weather, cfg)
    st = static_features(seg, walk)

    np.savez_compressed(
        PROCESSED / "dataset.npz",
        occ_obs=out["occ_obs"].astype(np.float32), occ_true=out["occ_true"].astype(np.float32),
        cov=cov.values.astype(np.float32), cov_names=np.array(cov.columns),
        static=st.values.astype(np.float32), static_names=np.array(st.columns),
        edge_index=edge_index, times=weather.index.values.astype("datetime64[h]").astype(np.int64),
        daily_visitors=out["daily_visitors"], median_loop_min=out["median_loop_min"])
    cal.to_csv(PROCESSED / "calendar.csv")

    summary = {
        "segments": int(len(seg)), "edges_undirected": int(edge_index.shape[1] // 2),
        "hours": int(len(weather)), "days": int(len(cal)),
        "visitors_total": int(out["daily_visitors"].sum()),
        "visitors_per_year": float(out["daily_visitors"].sum() / (len(cal) / 365.25)),
        "visitors_daily_mean": float(out["daily_visitors"].mean()),
        "visitors_daily_p95": float(np.percentile(out["daily_visitors"], 95)),
        "visitors_daily_max": int(out["daily_visitors"].max()),
        "median_loop_hours": float(np.nanmedian(out["median_loop_min"]) / 60),
        "peak_occupancy_by_segment": {int(i): float(v) for i, v in enumerate(out["occ_true"].max(0).round(1))},
    }
    (PROCESSED / "dataset_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "peak_occupancy_by_segment"}, indent=2))


if __name__ == "__main__":
    main()
