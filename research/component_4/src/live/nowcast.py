"""§6.1.4: today's hourly rain as known now - measured for the hours already past, nowcast for the next ones.

Open-Meteo's forecast for today (one request, `forecast_days=1`) holds the model analysis for past hours and the
latest run for the coming ones; it is refreshed every 15 minutes. The gate controller blends it with the evening
plan (mpc.blend_rain_share), so rain the plan did not expect lowers the caps during the day.
Offline or on error: None (the controller keeps the plan's rain).
"""
import os
import time
from datetime import date

import numpy as np

from src.live.inputs import FORECAST_URL, LIVE

TTL_S = 15 * 60
_mem: dict = {}


def rain_today(cfg, day: date, fetch=None) -> np.ndarray | None:
    """24 hourly rain values (mm) for `day`, or None. fetch(params) -> Open-Meteo JSON (tests pass a fake)."""
    if fetch is None and os.environ.get("C4_OFFLINE"):
        return None
    lat, lon = cfg["area"]["weather_point"]
    key = (lat, lon, day.isoformat())
    hit = _mem.get(key)
    if hit and time.time() - hit[0] < TTL_S:
        return hit[1]
    params = {"latitude": lat, "longitude": lon, "hourly": "precipitation", "forecast_days": 1,
              "timezone": "Asia/Colombo"}
    try:
        if fetch is None:
            import requests
            r = requests.get(FORECAST_URL, params=params, timeout=5)
            r.raise_for_status()
            js = r.json()
        else:
            js = fetch(params)
        h = js["hourly"]
        rain = np.zeros(24)
        for t, v in zip(h["time"], h["precipitation"]):
            if t.startswith(day.isoformat()) and v is not None:
                rain[int(t[11:13])] = float(v)
    except Exception:                                         # offline, timeout, unexpected answer
        return None
    _mem[key] = (time.time(), rain)
    (LIVE / f"nowcast_{day}.csv").write_text("hour,rain_mm\n" + "".join(f"{i},{v}\n" for i, v in enumerate(rain)),
                                            encoding="utf-8")
    return rain
