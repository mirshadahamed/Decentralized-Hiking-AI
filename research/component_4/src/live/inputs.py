"""Live inputs up to real dates: weather, calendar and visitor history (docs/archive/live_and_ux_plan.md, section 2.1).

weather   2022-01-01 .. yesterday  Open-Meteo archive (cached per finished year, recent part refreshed)
          today .. today+15        Open-Meteo forecast
          after that               typical weather: hourly mean for the same day of year (+-7 days), 2022-25
calendar  to today + 120 days      holidays package (LK), same features as the research dataset
visitors  research years           research dataset (simulated)
          2026 .. today            DWC daily totals if provided (scale the simulated day to them), otherwise
                                   simulated with the real weather; every day carries its source
"""
import json
from datetime import date, timedelta

import numpy as np
import pandas as pd
import requests

from src.config import DATA, PROCESSED, ROOT
from src.data.weather import ARCHIVE_URL, VARIABLES

LIVE = DATA / "live"
LIVE.mkdir(parents=True, exist_ok=True)
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


def _get(url, params):
    r = requests.get(url, params=params, timeout=120)
    r.raise_for_status()
    df = pd.DataFrame(r.json()["hourly"])
    df["time"] = pd.to_datetime(df["time"])
    return df.set_index("time").astype(float)


def _archive(cfg, start: date, end: date, cache_name: str | None):
    lat, lon = cfg["area"]["weather_point"]
    cache = LIVE / cache_name if cache_name else None
    if cache is not None and cache.exists():
        return pd.read_csv(cache, index_col=0, parse_dates=True)
    df = _get(ARCHIVE_URL, {"latitude": lat, "longitude": lon, "start_date": start.isoformat(),
                            "end_date": end.isoformat(), "hourly": ",".join(VARIABLES), "timezone": "Asia/Colombo"})
    if cache is not None:
        df.to_csv(cache)
    return df


def climatology(weather: pd.DataFrame, years=(2022, 2025)) -> pd.DataFrame:
    """Typical hourly weather per (day of year, hour): mean over the years, +-7 days."""
    w = weather[(weather.index.year >= years[0]) & (weather.index.year <= years[1])]
    doy, hr = w.index.dayofyear.values, w.index.hour.values
    out = np.zeros((367, 24, len(VARIABLES)))
    vals = w[VARIABLES].values
    for d in range(1, 367):
        dist = np.minimum(np.abs(doy - d), 366 - np.abs(doy - d))
        sel = dist <= 7
        for h in range(24):
            out[d, h] = vals[sel & (hr == h)].mean(0)
    return out


def live_weather(cfg, today: date, horizon_days: int) -> tuple[pd.DataFrame, pd.Series]:
    """Hourly weather from the research start to today + horizon, and the source of every hour."""
    start = date.fromisoformat(cfg["dates"]["start"])
    parts = []
    for y in range(start.year, today.year):                       # finished years: cached forever
        parts.append(_archive(cfg, date(y, 1, 1), date(y, 12, 31), f"weather_{y}.csv"))
    yesterday = today - timedelta(days=1)
    if yesterday >= date(today.year, 1, 1):
        parts.append(_archive(cfg, date(today.year, 1, 1), yesterday, f"weather_{today.year}_to_{yesterday}.csv"))
    hist = pd.concat(parts).sort_index()
    hist = hist[~hist.index.duplicated()]
    src = pd.Series("observed", index=hist.index)

    lat, lon = cfg["area"]["weather_point"]
    fc_cache = LIVE / f"forecast_{today}.csv"
    if fc_cache.exists():
        fc = pd.read_csv(fc_cache, index_col=0, parse_dates=True)
    else:
        fc = _get(FORECAST_URL, {"latitude": lat, "longitude": lon, "hourly": ",".join(VARIABLES),
                                 "forecast_days": cfg["live"]["forecast_days"], "timezone": "Asia/Colombo"})
        fc.to_csv(fc_cache)
    fc = fc[fc.index >= pd.Timestamp(today)]

    end = pd.Timestamp(today + timedelta(days=horizon_days)) + pd.Timedelta(hours=23)
    idx = pd.date_range(pd.Timestamp(start), end, freq="h")
    w = pd.DataFrame(index=idx, columns=VARIABLES, dtype=float)
    w.loc[hist.index.intersection(idx)] = hist.loc[hist.index.intersection(idx), VARIABLES].values
    w.loc[fc.index.intersection(idx)] = fc.loc[fc.index.intersection(idx), VARIABLES].values
    src = src.reindex(idx).fillna("")
    src[fc.index.intersection(idx)] = "forecast"

    clim = climatology(w.dropna())
    miss = w.isna().any(axis=1)
    w.loc[miss] = clim[w.index[miss].dayofyear, w.index[miss].hour]
    src[miss & (src == "")] = "typical"
    src[src == ""] = "typical"
    return w.astype(float), src


def dwc_totals(cfg) -> pd.DataFrame | None:
    """Optional real daily totals (date, trail, visitors). Missing file -> None."""
    p = ROOT / cfg["live"]["dwc_totals_csv"]
    if not p.exists():
        return None
    df = pd.read_csv(p, parse_dates=["date"])
    return df.pivot_table(index="date", columns="trail", values="visitors", aggfunc="sum")


def research_meta():
    d = np.load(PROCESSED / "dataset.npz", allow_pickle=True)
    return d, json.loads((PROCESSED / "dataset_summary.json").read_text(encoding="utf-8"))
