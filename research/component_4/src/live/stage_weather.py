"""R5: weather per stage of a long trail (Pekoe): the stages span 600-2,100 m and two monsoons, so the park's one
weather point is not enough. One Open-Meteo forecast request with every stage's midpoint (the API takes several
coordinates at once), cached per day. Only within the forecast horizon (16 days); later days use the park's
typical weather.

    stage_weather(cfg, seg, today) -> {stage: {date: {"rain_mm", "rain_hours", "temp_max_c"}}}
"""
import json
from datetime import date

import numpy as np
import pandas as pd

from src.live.inputs import FORECAST_URL, LIVE


def midpoints(seg) -> dict:
    """{stage: (lat, lon)} of the middle section of each stage (walking order)."""
    out = {}
    for t, g in seg.groupby("trail"):
        mid = g.sort_values("seg_id").iloc[len(g) // 2].geometry.interpolate(0.5, normalized=True)
        out[t] = (round(mid.y, 4), round(mid.x, 4))
    return out


def summarise(times: list, rain: list, temp: list, cfg) -> dict:
    """Daily rain (open hours), rainy open hours and max temperature from hourly values."""
    c = cfg["capacity"]
    lo = c.get("open_from_h", 6)
    df = pd.DataFrame({"t": pd.to_datetime(times), "rain": rain, "temp": temp})
    df = df[(df.t.dt.hour >= lo) & (df.t.dt.hour < lo + c["open_hours"])]
    out = {}
    for d, g in df.groupby(df.t.dt.date):
        out[d.isoformat()] = {"rain_mm": round(float(np.nansum(g.rain)), 1),
                              "rain_hours": int((g.rain >= c["rain_mm"]).sum()),
                              "temp_max_c": round(float(np.nanmax(g.temp)), 1)}
    return out


def stage_weather(cfg, seg, today: date, fetch=None) -> dict:
    cache = LIVE / f"stage_weather_{today}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    mids = midpoints(seg)
    stages = list(mids)
    if fetch is None:
        import requests
        r = requests.get(FORECAST_URL, timeout=60, params={
            "latitude": ",".join(str(mids[s][0]) for s in stages), "longitude": ",".join(str(mids[s][1]) for s in stages),
            "hourly": "precipitation,temperature_2m", "forecast_days": cfg["live"]["forecast_days"],
            "timezone": "Asia/Colombo"})
        r.raise_for_status()
        fetch = r.json()
    rows = fetch if isinstance(fetch, list) else [fetch]                # one location: a dict, several: a list
    out = {s: summarise(x["hourly"]["time"], x["hourly"]["precipitation"], x["hourly"]["temperature_2m"], cfg)
           for s, x in zip(stages, rows)}
    LIVE.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(out), encoding="utf-8")
    return out
