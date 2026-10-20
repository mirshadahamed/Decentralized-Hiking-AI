"""Live dataset: same layout as data/processed/dataset.npz, but from the research start to today + horizon.

Past research years are copied unchanged. Days after them up to *today* get a visitor history:
DWC daily totals if provided (the simulator spreads them over segments and hours), otherwise simulated with
the real weather (fixed seed per day, so a refresh is repeatable). Future days have no counts (zeros, source
'future'); nothing uses them as targets. Every day keeps its source so screens can say "estimated".
"""
from copy import deepcopy
from datetime import date, timedelta

import geopandas as gpd
import numpy as np
import pandas as pd

from src.config import PROCESSED, load_config
from src.data.build_dataset import hourly_covariates
from src.data.calendar_features import build_calendar
from src.data.graph import load_walks
from src.live.inputs import LIVE, dwc_totals, live_weather, research_meta
from src.sim.simulator import TrailSimulator, daily_demand

LIVE_NPZ = LIVE / "dataset_live.npz"
LIVE_CAL = LIVE / "calendar_live.csv"
LIVE_WEATHER = LIVE / "weather_live.csv"


def build_live(today: date, cfg=None):
    cfg = cfg or load_config()
    horizon = cfg["live"]["horizon_days"]
    weather, wsrc = live_weather(cfg, today, horizon)

    ccfg = deepcopy(cfg)
    ccfg["dates"]["end"] = (today + timedelta(days=max(horizon, cfg["live"]["calendar_extra_days"]))).isoformat()
    days = pd.date_range(cfg["dates"]["start"], weather.index[-1].normalize(), freq="D")
    cal = build_calendar(ccfg).reindex(days)
    cov = hourly_covariates(weather.index, cal, weather, cfg)

    r, _ = research_meta()
    trails = list(r["trails"])
    T, D, N = len(weather), len(days), r["occ_obs"].shape[1]
    Tr, Dr = r["occ_obs"].shape[0], r["daily_visitors"].shape[0]
    occ_obs, occ_true = np.zeros((T, N), np.float32), np.zeros((T, N), np.float32)
    by_trail = np.zeros((D, len(trails)), int)
    occ_obs[:Tr], occ_true[:Tr], by_trail[:Dr] = r["occ_obs"], r["occ_true"], r["daily_visitors_by_trail"]
    day_source = np.array(["future"] * D, dtype=object)
    day_source[:Dr] = "simulated (research years)"

    seg = gpd.read_file(PROCESSED / "segments.geojson")
    seg["poi"] = seg["poi"].fillna("")
    sim = TrailSimulator(seg, load_walks(), cfg["simulator"])
    precip = weather.precipitation.values.reshape(D, 24)
    dwc = dwc_totals(cfg)
    t_idx = int((pd.Timestamp(today) - days[0]).days)
    for di in range(Dr, t_idx + 1):                       # history after the research years, up to today
        rng = np.random.default_rng([cfg["seed"], di])
        n = daily_demand(cal.iloc[[di]], precip[[di]], cfg["simulator"], rng)[0]
        source = "simulated"
        if dwc is not None and days[di] in dwc.index:
            n, source = float(dwc.loc[days[di]].sum()), "DWC total (spread by simulator)"
        h, _, v = sim.simulate_day(int(round(n)), precip[di], rng)
        occ_true[di * 24:(di + 1) * 24] = h
        occ_obs[di * 24:(di + 1) * 24] = rng.poisson(h * rng.lognormal(0, cfg["simulator"]["obs_noise_sd"], h.shape))
        by_trail[di] = [v[t] for t in trails]
        day_source[di] = source

    keep = {k: r[k] for k in ("static", "static_names", "edge_index", "edge_weight", "trails", "segment_trail",
                              "segment_poi", "segment_walk_position")}
    np.savez_compressed(
        LIVE_NPZ, occ_obs=occ_obs, occ_true=occ_true, cov=cov.values.astype(np.float32),
        cov_names=np.array(cov.columns), times=weather.index.values.astype("datetime64[h]").astype(np.int64),
        daily_visitors=by_trail.sum(1), daily_visitors_by_trail=by_trail,
        median_loop_min=np.zeros(D), day_source=day_source.astype(str), weather_source=wsrc.values.astype(str),
        live_today=np.array(today.isoformat()), **keep)
    cal.to_csv(LIVE_CAL)
    weather.assign(source=wsrc.values).to_csv(LIVE_WEATHER)
    return LIVE_NPZ, cal, weather, wsrc


def load_live():
    """The last built live dataset (no downloads, no simulation): for the API between refreshes."""
    if not (LIVE_NPZ.exists() and LIVE_CAL.exists() and LIVE_WEATHER.exists()):
        raise FileNotFoundError("Run python -m src.live.refresh first")
    cal = pd.read_csv(LIVE_CAL, index_col=0, parse_dates=True)
    w = pd.read_csv(LIVE_WEATHER, index_col=0, parse_dates=True)
    today = date.fromisoformat(str(np.load(LIVE_NPZ, allow_pickle=True)["live_today"]))
    return today, LIVE_NPZ, cal, w.drop(columns="source"), w["source"]
