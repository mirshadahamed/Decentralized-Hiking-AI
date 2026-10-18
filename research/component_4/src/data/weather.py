"""Hourly weather for the park from the Open-Meteo historical archive (ERA5-based)."""
import json

import pandas as pd
import requests

from src.config import RAW

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
VARIABLES = ["precipitation", "temperature_2m", "relative_humidity_2m", "cloud_cover", "wind_speed_10m"]


def load_weather(cfg) -> pd.DataFrame:
    start, end = cfg["dates"]["start"], cfg["dates"]["end"]
    cache = RAW / f"weather_{start}_{end}.json"
    if not cache.exists():
        lat, lon = cfg["area"]["weather_point"]
        r = requests.get(ARCHIVE_URL, timeout=120, params={
            "latitude": lat, "longitude": lon, "start_date": start, "end_date": end,
            "hourly": ",".join(VARIABLES), "timezone": "Asia/Colombo"})
        r.raise_for_status()
        cache.write_text(r.text, encoding="utf-8")
    js = json.loads(cache.read_text(encoding="utf-8"))
    df = pd.DataFrame(js["hourly"])
    df["time"] = pd.to_datetime(df["time"])
    df = df.set_index("time").astype(float)
    return df.interpolate(limit_direction="both")


if __name__ == "__main__":
    from src.config import load_config
    w = load_weather(load_config())
    print(w.shape, w.index.min(), w.index.max())
    print(w.describe().round(2).to_string())
    print("monthly rain (mm):", w.precipitation.resample("MS").sum().groupby(lambda t: t.month).mean().round(0).to_dict())
