"""Run the whole data pipeline and save data/processed/dataset.npz.

    python -m src.data.build_dataset            (re-uses cached OSM / DEM / weather downloads)
"""
import json

import geopandas as gpd
import numpy as np
import pandas as pd

from src.config import PROCESSED, load_config
from src.data.calendar_features import build_calendar
from src.data.graph import build_graph
from src.data.terrain import segment_terrain
from src.data.weather import load_weather
from src.sim.simulator import simulate
from src.utils import set_seed

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
    for c in ["is_weekend", "is_holiday", "is_poya", "is_long_weekend", "is_school_holiday", "is_season"]:
        if c in day:                                          # is_season only for parks with a season
            cov[c] = day[c].values.astype(float)
    cov["precip_log1p"] = np.log1p(weather.precipitation.values)
    for c in ["temperature_2m", "relative_humidity_2m", "cloud_cover", "wind_speed_10m"]:
        cov[c] = weather[c].values
    return cov


def viewpoints(cfg) -> set:
    return set(cfg["area"]["poi_roles"]["viewpoint"])


def access_points(cfg) -> set:
    return set(cfg["area"]["poi_roles"]["access"])


def static_features(seg: gpd.GeoDataFrame, walks: dict, cfg) -> pd.DataFrame:
    """Fixed per-segment inputs that *describe* a segment rather than name it, so a model can transfer
    them to segments it never saw counts for (spatial CV). No one-hot of trail or POI identity:
    those values are unique to a few segments and cannot be learned when those segments are held out."""
    sim = cfg["simulator"]
    lf = sim["leisure_speed_factor"]
    poi = seg.poi.fillna("")
    st = seg[STATIC_COLS].astype(float).copy()
    st["is_viewpoint"] = poi.isin(viewpoints(cfg)).astype(float)
    st["is_access_point"] = poi.isin(access_points(cfg)).astype(float)
    st["dwell_min"] = [sim["dwell_minutes"].get(p, [0])[0] if p else 0.0 for p in poi]
    # minutes from the trail's start until a hiker first reaches the segment, passes per visit,
    # and the share of park visitors whose trail uses the segment
    minutes, passes, share = np.zeros(len(seg)), np.zeros(len(seg)), np.zeros(len(seg))
    seen = set()
    for trail, walk in walks.items():
        t, visited = 0.0, set()
        for s, d in walk:
            if s not in seen:
                minutes[s] = t
                seen.add(s)
            if s not in visited:
                share[s] += sim["route_share"].get(trail, 0.0)
                visited.add(s)
            if trail == seg.trail.iloc[s]:
                passes[s] += 1
            t += seg[("tobler_fwd_min" if d > 0 else "tobler_bwd_min")].iloc[s] / lf
    st["minutes_from_trailhead"] = minutes
    st["passes_per_visit"] = passes
    st["visitor_share"] = share
    return st


def main():
    cfg = load_config()
    set_seed(cfg["seed"])
    seg, edge_index, walks = build_graph(cfg)
    seg = segment_terrain(cfg)
    weather = load_weather(cfg)
    cal = build_calendar(cfg)
    assert len(weather) == len(cal) * 24, "weather must cover whole days"

    out = simulate(seg, walks, weather, cal, cfg["simulator"], seed=cfg["seed"])
    cov = hourly_covariates(weather.index, cal, weather, cfg)
    st = static_features(seg, walks, cfg)

    np.savez_compressed(
        PROCESSED / "dataset.npz",
        occ_obs=out["occ_obs"].astype(np.float32), occ_true=out["occ_true"].astype(np.float32),
        cov=cov.values.astype(np.float32), cov_names=np.array(cov.columns),
        static=st.values.astype(np.float32), static_names=np.array(st.columns),
        edge_index=edge_index, edge_weight=np.load(PROCESSED / "edge_weight.npy"),
        times=weather.index.values.astype("datetime64[h]").astype(np.int64),
        daily_visitors=out["daily_visitors"], daily_visitors_by_trail=out["daily_visitors_by_trail"],
        trails=np.array(out["trails"]), segment_trail=seg.trail.values.astype(str),
        segment_poi=seg.poi.fillna("").values.astype(str),
        segment_walk_position=seg.walk_position.values.astype(np.float32),
        median_loop_min=out["median_loop_min"])
    cal.to_csv(PROCESSED / "calendar.csv")

    by_trail = out["daily_visitors_by_trail"]
    years = len(cal) / 365.25
    summary = {
        "segments": int(len(seg)), "edges_undirected": int(edge_index.shape[1] // 2),
        "segments_by_trail": {t: int((seg.trail == t).sum()) for t in out["trails"]},
        "hours": int(len(weather)), "days": int(len(cal)),
        "visitors_total": int(out["daily_visitors"].sum()),
        "visitors_per_year": float(out["daily_visitors"].sum() / years),
        "visitors_per_year_by_trail": {t: float(by_trail[:, i].sum() / years) for i, t in enumerate(out["trails"])},
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
