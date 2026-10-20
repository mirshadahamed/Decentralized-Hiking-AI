"""Objective O1: cross-check the rain the model uses (Open-Meteo / ERA5) against NASA POWER, per park.

    python -m src.data.rain_check                 (C4_PARK picks the park; downloads once into data/external/)

NASA POWER (MERRA-2 based, satellite-corrected, PRECTOTCORR) daily rain at the park's weather point, 2022-2025,
compared with the daily sum of the hourly Open-Meteo rain used for training:
  - Pearson / Spearman correlation of daily totals, bias and MAE (mm/day)
  - wet-day agreement: both >= 1 mm or both < 1 mm (what the morning-rain demand factor and FCpre care about)
  - monthly totals side by side (season shape)
Decision rule (fixed here): if wet-day agreement >= 75 % and monthly correlation >= 0.8 the sources tell the same
story and NASA POWER is kept as a check; otherwise it is added as an extra rain feature (W5).
Outputs results/<park>/<timestamp>_rain_check/: metrics.json, daily.csv, monthly.png
"""
import json

import matplotlib
import numpy as np
import pandas as pd
import requests
from scipy import stats

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from src.config import DATA, RESULTS, load_config  # noqa: E402
from src.data.weather import load_weather  # noqa: E402
from src.utils import new_run_dir  # noqa: E402

API = "https://power.larc.nasa.gov/api/temporal/daily/point"


def nasa_power(lat: float, lon: float, start: str, end: str, park: str) -> pd.Series:
    cache = DATA / "external" / f"nasa_power_{park}_{start}_{end}.json"
    if not cache.exists():
        r = requests.get(API, params={"parameters": "PRECTOTCORR", "community": "AG", "latitude": lat,
                                      "longitude": lon, "start": start.replace("-", ""), "end": end.replace("-", ""),
                                      "format": "JSON"}, timeout=120)
        r.raise_for_status()
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(r.text, encoding="utf-8")
    js = json.loads(cache.read_text(encoding="utf-8"))
    s = pd.Series(js["properties"]["parameter"]["PRECTOTCORR"], dtype=float)
    s.index = pd.to_datetime(s.index, format="%Y%m%d")
    return s.where(s >= 0)                                    # -999 = missing


def compare(cfg) -> tuple[dict, pd.DataFrame]:
    lat, lon = cfg["area"]["weather_point"]
    start, end = cfg["dates"]["start"], cfg["dates"]["end"]
    om = load_weather(cfg).precipitation.resample("D").sum()
    om.index = om.index.normalize()
    npw = nasa_power(lat, lon, start, end, cfg["park"])
    df = pd.DataFrame({"open_meteo": om, "nasa_power": npw}).dropna()
    wet_om, wet_np = df.open_meteo >= 1, df.nasa_power >= 1
    m = df.resample("MS").sum()
    out = {
        "park": cfg["park"], "point": [lat, lon], "days": int(len(df)),
        "pearson_daily": round(float(stats.pearsonr(df.open_meteo, df.nasa_power).statistic), 3),
        "spearman_daily": round(float(stats.spearmanr(df.open_meteo, df.nasa_power).statistic), 3),
        "mean_mm_open_meteo": round(float(df.open_meteo.mean()), 2),
        "mean_mm_nasa_power": round(float(df.nasa_power.mean()), 2),
        "bias_mm_per_day": round(float((df.open_meteo - df.nasa_power).mean()), 2),
        "mae_mm_per_day": round(float((df.open_meteo - df.nasa_power).abs().mean()), 2),
        "wet_day_agreement": round(float((wet_om == wet_np).mean()), 3),
        "wet_days_open_meteo": int(wet_om.sum()), "wet_days_nasa_power": int(wet_np.sum()),
        "pearson_monthly": round(float(stats.pearsonr(m.open_meteo, m.nasa_power).statistic), 3),
    }
    out["same_story"] = bool(out["wet_day_agreement"] >= 0.75 and out["pearson_monthly"] >= 0.8)
    out["decision"] = ("keep NASA POWER as a check (sources agree)" if out["same_story"]
                       else "add NASA POWER as an extra rain feature and re-run RQ1 (sources disagree)")
    return out, df


def main():
    cfg = load_config()
    out, df = compare(cfg)
    run = new_run_dir("rain_check", cfg)
    (run / "metrics.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    df.to_csv(run / "daily.csv")
    m = df.resample("MS").sum()
    fig, ax = plt.subplots(figsize=(9, 3.2))
    ax.plot(m.index, m.open_meteo, label="Open-Meteo / ERA5 (used by the model)", color="#3B6FB6")
    ax.plot(m.index, m.nasa_power, label="NASA POWER (PRECTOTCORR)", color="#2F6B4F")
    ax.set_ylabel("Rain per month (mm)")
    ax.set_title(f"{cfg['area']['name']}: monthly rain, two sources (r = {out['pearson_monthly']})", fontsize=10)
    ax.legend(fontsize=8, frameon=False)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(run / "monthly.png", dpi=160)
    (RESULTS / "LATEST_RAIN_CHECK").write_text(run.name, encoding="utf-8") if cfg["park"] == "horton_plains" else None
    print(json.dumps(out, indent=1))
    print(run)


if __name__ == "__main__":
    main()
