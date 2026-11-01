"""W-a / W-b (PP1 panel): the weather of a chosen date, what kind of weather it is, and what it does to the crowd
and the safe limit.

    GET /weather/{day}                       (public; any day of the live data: past, forecast or typical)

basis   observed  past hours (Open-Meteo archive, ERA5)
        forecast  up to 16 days ahead (Open-Meteo forecast)
        typical   further ahead: the hourly climatology of the research years; a range is given as well
                  (P10-P90 of the same dates +-7 days in the observed years), because one typical day hides the spread
effect  the share of rainy open hours removes the same share of the Cifuentes capacity (FCpre); rain between
        05:00 and 10:00 keeps visitors away (simulator demand model); earlier rain leaves the ground wet (FCwet)
"""
from datetime import date

import numpy as np
import pandas as pd

LABELS = {"observed": "measured weather", "forecast": "weather forecast", "typical": "typical weather for the date"}


def _open_hours(cfg) -> list:
    c = cfg["capacity"]
    return [int((c.get("open_from_h", 6) + k) % 24) for k in range(c["open_hours"])]


def _runs(hours: list) -> list:
    """[6, 7, 8, 12, 13] -> [(6, 9), (12, 14)] (end exclusive)."""
    out = []
    for h in hours:
        if out and out[-1][1] == h:
            out[-1] = (out[-1][0], h + 1)
        else:
            out.append((h, h + 1))
    return out


def typical_range(ctx, day: date) -> dict:
    """Spread of the observed years around this date (+-7 days): open-hours rain total, wet-day chance, temps."""
    cfg, w, src = ctx.cfg, ctx.weather, ctx.weather_source
    obs = w[(src == "observed").values]
    oh = _open_hours(cfg)
    obs = obs[np.isin(obs.index.hour, oh)]
    doy = pd.Timestamp(day).dayofyear
    d = obs.index.dayofyear.values
    near = np.minimum(np.abs(d - doy), 366 - np.abs(d - doy)) <= 7
    days = obs[near].groupby(obs.index[near].normalize())
    rain = days.precipitation.sum()
    wet = days.precipitation.apply(lambda x: (x >= cfg["capacity"]["rain_mm"]).any())
    tmin, tmax = days.temperature_2m.min(), days.temperature_2m.max()
    if not len(rain):
        return {}
    return {"days_used": int(len(rain)), "rain_mm_p10": round(float(rain.quantile(0.1)), 1),
            "rain_mm_p50": round(float(rain.quantile(0.5)), 1), "rain_mm_p90": round(float(rain.quantile(0.9)), 1),
            "chance_wet_day": round(float(wet.mean()), 2),
            "temp_low": round(float(tmin.quantile(0.1)), 1), "temp_high": round(float(tmax.quantile(0.9)), 1)}


def day_weather(ctx, day: date) -> dict:
    cfg, w, src = ctx.cfg, ctx.weather, ctx.weather_source
    lo = pd.Timestamp(day)
    rows = w[(w.index >= lo) & (w.index < lo + pd.Timedelta(days=1))]
    if len(rows) < 24 or rows.precipitation.isna().all():
        raise ValueError(f"No weather for {day}: choose a day from {w.index[0].date()} to {w.index[-1].date()}")
    kinds = src[rows.index]
    oh = _open_hours(cfg)
    thr = cfg["capacity"]["rain_mm"]
    hourly = [{"hour": int(t.hour), "rain_mm": round(float(r.precipitation), 1), "temp_c": round(float(r.temperature_2m), 1),
               "wind_kmh": round(float(r.wind_speed_10m), 1), "cloud_pct": round(float(r.cloud_cover)),
               "humidity_pct": round(float(r.relative_humidity_2m)), "basis": str(kinds[t])}
              for t, r in rows.iterrows()]
    op = rows[np.isin(rows.index.hour, oh)]
    basis = sorted(set(kinds[op.index]))
    main = "typical" if "typical" in basis else "forecast" if "forecast" in basis else "observed"
    rain_share, rain_basis = ctx.rain_share(day)
    if main == "typical":
        # a mean over years smears rain over every hour: take the rainy share the safe limit uses, and the hours
        # that are usually driest (lowest mean rain) instead of "dry" hours
        n_wet = int(round(rain_share * len(oh)))
        order = op.precipitation.sort_values(kind="stable")
        dry = sorted(int(t.hour) for t in order.index[:len(oh) - n_wet])
        wet_h = [h for h in oh if h not in dry]
    else:
        wet_h = [int(h) for h, v in zip(op.index.hour, op.precipitation) if v >= thr]
        dry = [int(h) for h in op.index.hour if h not in wet_h]
    windows = sorted(_runs(dry), key=lambda r: r[0] - r[1])

    # effects on the day's decisions (the same numbers the safe limit and the crowd model use)
    p = cfg["simulator"]
    morning = float(rows.precipitation[(rows.index.hour >= 5) & (rows.index.hour < 10)].sum())
    keep = max(p["min_rain_multiplier"], float(np.exp(-p["morning_rain_k"] * morning)))
    wet = ctx.ground_wetness(day)
    out = {
        "day": day.isoformat(), "site": cfg["area"]["name"], "basis": main, "basis_label": LABELS[main],
        "mixed_basis": basis if len(basis) > 1 else None,
        "open_hours": oh, "hourly": hourly,
        "summary": {"rain_mm_open_hours": round(float(op.precipitation.sum()), 1), "rainy_open_hours": len(wet_h),
                    "rain_share_open_hours": round(len(wet_h) / max(len(oh), 1), 2),
                    "temp_min": round(float(op.temperature_2m.min()), 1), "temp_max": round(float(op.temperature_2m.max()), 1),
                    "wind_max_kmh": round(float(op.wind_speed_10m.max()), 1),
                    "dry_windows": [{"from": a, "to": b} for a, b in windows[:3]],
                    "dry_windows_basis": "usually driest hours" if main == "typical" else "hours without rain",
                    "best_start": windows[0][0] if windows else None},
        "effect": {
            "capacity_rain_factor_pct": round(100 * float(rain_share)),
            "capacity_rain_basis": rain_basis,
            "visitors_kept_pct": round(100 * keep),
            "morning_rain_mm": round(morning, 1),
            "ground": wet,
            "text": _effect_text(rain_share, keep, wet),
        },
    }
    if main == "typical":
        out["typical_range"] = typical_range(ctx, day)
    return out


class ResearchWeather:
    """Stand-in for the live context on the research years (all weather observed): used to build test fixtures."""

    def __init__(self, cfg):
        from src.data.weather import load_weather
        self.cfg, self.weather = cfg, load_weather(cfg)
        self.weather_source = pd.Series("observed", index=self.weather.index)

    def rain_share(self, day: date):
        c = self.cfg["capacity"]
        lo = pd.Timestamp(day) + pd.Timedelta(hours=c.get("open_from_h", 6))
        w = self.weather.precipitation[lo:lo + pd.Timedelta(hours=c["open_hours"] - 1)]
        return float((w >= c["rain_mm"]).mean()), "measured weather"

    def ground_wetness(self, day: date) -> dict:
        from src.capacity.cifuentes import wetness_from_rain
        c = self.cfg["capacity"]
        n = c.get("wet_ground", {}).get("days", 3)
        hi = pd.Timestamp(day) + pd.Timedelta(hours=c.get("open_from_h", 6))
        rain = float(self.weather.precipitation[(self.weather.index >= hi - pd.Timedelta(days=n)) &
                                                (self.weather.index < hi)].sum())
        return {"rain_mm": round(rain, 1), "days": n, "wetness": round(wetness_from_rain(rain, c), 3),
                "basis": "measured rain"}


def _effect_text(rain_share: float, keep: float, wet: dict) -> str:
    parts = []
    if rain_share >= 0.05:
        parts.append(f"rain in {round(100 * rain_share)} % of the open hours lowers the safe limit by the same share")
    if keep < 0.97:
        parts.append(f"morning rain keeps about {round(100 * (1 - keep))} % of visitors away")
    if wet.get("wetness", 0) >= 0.2:
        parts.append(f"the ground is still wet from {wet['rain_mm']} mm in the last {wet['days']} days")
    return ("; ".join(parts) + ".").capitalize() if parts else "Dry: the weather does not lower the safe limit."
