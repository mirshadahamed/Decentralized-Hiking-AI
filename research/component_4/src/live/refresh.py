"""Daily live refresh: real dates in, published forecasts and slot plans out.

    python -m src.live.refresh                     # today (run every evening, e.g. Windows Task Scheduler 18:00)
    python -m src.live.refresh --today 2026-10-15  # a chosen 'today' (testing / demos)

Steps (live_and_ux_plan.md, section 2.1):
  1-5 inputs: calendar, weather (observed / forecast / typical), visitor history (DWC / simulated)
  6   forecasts: 90-day outlook from today (planning model), tomorrow hour by hour (ST-GNN, or the
      historical-average fallback if no trained model is available)
  7   slot plans for the next 90 days with the freeze rule (never fewer places than already booked)
  8   publish small JSON files to data/live/published/ (cached by gate devices and phones; read by the API)
"""
import argparse
import json
from datetime import date, datetime, timedelta

import geopandas as gpd
import numpy as np
import pandas as pd

from src.config import PROCESSED, load_config
from src.control import booking
from src.eval.data import TrailData
from src.live.dataset import build_live, load_live
from src.live.inputs import LIVE
from src.planning.model import DailyTable
from src.serve.outlook import build_planner, outlook_json
from src.serve.predict import build_forecast, load_model

PUBLISHED = LIVE / "published"


class LiveContext:
    """Everything the API needs for live answers, built once per refresh."""

    def __init__(self, today: date | None = None, cfg=None, rebuild: bool = True):
        """rebuild=False: reuse the last refresh's live dataset (fast; used by the API)."""
        self.cfg = cfg = cfg or load_config()
        if rebuild:
            self.today = today or date.today()
            path, self.calendar, self.weather, self.weather_source = build_live(self.today, cfg)
        else:
            self.today, path, self.calendar, self.weather, self.weather_source = load_live()
        self.data = TrailData(cfg, path)
        self.day_source = np.load(path, allow_pickle=True)["day_source"]
        self.planner = build_planner(cfg)                      # fitted on the research years
        self.planner.m.table = DailyTable(self.data, self.calendar)   # same model, live inputs
        self.planner.m.data = self.data
        self.seg = gpd.read_file(PROCESSED / "segments.geojson")
        self.seg["poi"] = self.seg["poi"].fillna("")
        try:
            self.model, self.scale, self.run = load_model(self.data, cfg)
        except (FileNotFoundError, RuntimeError):
            self.model, self.scale, self.run = None, None, None

    def rain_share(self, day: date) -> tuple[float, str]:
        """Share of rainy open hours: from the weather forecast within its horizon, else typical."""
        lo = pd.Timestamp(day) + pd.Timedelta(hours=self.cfg["capacity"].get("open_from_h", 6))
        hi = lo + pd.Timedelta(hours=self.cfg["capacity"]["open_hours"] - 1)
        src = self.weather_source[(self.weather_source.index >= lo) & (self.weather_source.index <= hi)]
        if len(src) and (src == "forecast").all():
            w = self.weather.precipitation[lo:hi]
            return float((w >= self.cfg["capacity"]["rain_mm"]).mean()), "weather forecast"
        return booking.typical_rain_share(day.isoformat()), "typical weather"

    def ground_wetness(self, day: date) -> dict:
        """How wet the ground is when the trail opens on `day`: rain of the previous `wet_ground.days` days
        (observed, forecast or typical weather, whichever the live weather has for those hours)."""
        from src.capacity.cifuentes import wetness_from_rain
        c = self.cfg["capacity"]
        n = c.get("wet_ground", {}).get("days", 3)
        hi = pd.Timestamp(day) + pd.Timedelta(hours=c.get("open_from_h", 6))
        lo = hi - pd.Timedelta(days=n)
        rain = float(self.weather.precipitation[(self.weather.index >= lo) & (self.weather.index < hi)].sum())
        kinds = set(self.weather_source[(self.weather_source.index >= lo) & (self.weather_source.index < hi)])
        basis = "measured rain" if kinds <= {"observed"} else "forecast rain" if "typical" not in kinds else "typical rain"
        return {"rain_mm": round(rain, 1), "days": n, "wetness": round(wetness_from_rain(rain, c), 3), "basis": basis}

    def forecast_tomorrow(self) -> dict:
        tomorrow = (self.today + timedelta(days=1)).isoformat()
        out = build_forecast(self.data, self.cfg, self.seg, tomorrow, self.model, self.scale, self.run)
        out["history_basis"] = str(self.day_source[int((pd.Timestamp(self.today) - self.data.times[0]).days)])
        return out


def publish_slots(ctx: LiveContext, db=None) -> list:
    alerts = []
    for k in range(1, ctx.cfg["live"]["horizon_days"] + 1):
        d = ctx.today + timedelta(days=k)
        rain, basis = ctx.rain_share(d)
        alerts += booking.publish_day(d.isoformat(), rain, basis, db, wetness=ctx.ground_wetness(d)["wetness"])
    return alerts


def publish_edge_pack(ctx: LiveContext, forecast: dict | None = None) -> bool:
    """Model + inputs for tomorrow, so phones can run the forecast themselves offline (src/edge/pack.py), plus
    the segment lines and capacities for the bottleneck map (from tomorrow's server forecast, if given).
    Not published when only the historical-average fallback is available (no trained model)."""
    from src.edge.pack import build_pack, map_extras
    if ctx.model is None:
        return False
    tomorrow = pd.Timestamp(ctx.today + timedelta(days=1))
    origin = int(np.searchsorted(ctx.data.times, tomorrow))
    if origin >= ctx.data.T or origin < ctx.data.L:
        return False
    ctx.model.eval()
    pack = build_pack(ctx.data, ctx.model, ctx.scale, origin, ctx.cfg, run=ctx.run)
    if forecast is not None:
        pack["map"] = map_extras(forecast, ctx.seg, ctx.cfg)
    (PUBLISHED / "edge_pack.json").write_text(json.dumps(pack, separators=(",", ":")), encoding="utf-8")
    return True


def publish_advisory(outlook: dict) -> dict:
    """Recommended start times for every day of the outlook, from the expected climbers per route (likely case).
    Officers also get a high case (P90 climbers: 1 night in 10 is busier) to plan the halfway checks for."""
    from src.control.advisory import build_advisory
    adv = build_advisory()
    out = {"generated_at": datetime.now().isoformat(timespec="seconds"), "days": {}}
    for day in outlook["days"]:
        by_trail = {t: float(v) for t, v in day["visitors_by_trail_p50"].items()}
        rec = adv.recommend(by_trail, day=day["date"])           # sunrise of that date, climb times at that crowd
        k = day["visitors"]["p90"] / max(day["visitors"]["p50"], 1)
        high = adv.recommend({t: v * k for t, v in by_trail.items()}, day=day["date"])
        rec["high_case"] = {"visitors": day["visitors"]["p90"], "summit": high["summit"], "halfway": high["halfway"]}
        out["days"][day["date"]] = rec
    (PUBLISHED / "advisory.json").write_text(json.dumps(out), encoding="utf-8")
    return out


def refresh(today: date | None = None, db=None) -> dict:
    today = today or date.today()
    ctx = LiveContext(today)
    PUBLISHED.mkdir(parents=True, exist_ok=True)

    outlook = outlook_json(ctx.planner, today.isoformat(), ctx.cfg["live"]["horizon_days"])
    for day in outlook["days"]:
        day["weather_basis"] = ctx.rain_share(date.fromisoformat(day["date"]))[1]
    tomorrow = ctx.forecast_tomorrow()
    advisory_mode = ctx.cfg["control"].get("booking_mode", "required") == "advisory"
    alerts = [] if advisory_mode else publish_slots(ctx, db)
    if advisory_mode:                                       # pilgrimage site: recommended start times, no tickets
        publish_advisory(outlook)
    edge = publish_edge_pack(ctx, tomorrow)

    last30 = ctx.day_source[max(0, int((pd.Timestamp(today) - ctx.data.times[0]).days) - 29):
                            int((pd.Timestamp(today) - ctx.data.times[0]).days) + 1]
    status = {
        "park": ctx.cfg["park"], "site": ctx.cfg["area"]["name"],
        "booking_mode": ctx.cfg["control"].get("booking_mode", "required"),
        "today": today.isoformat(), "refreshed_at": datetime.now().isoformat(timespec="seconds"),
        "forecast_model": tomorrow["source"]["model"], "model_run": ctx.run, "edge_pack": edge,
        "visitor_history_last_30_days": pd.Series(last30).value_counts().to_dict(),
        "weather_next_90_days": pd.Series(
            [ctx.rain_share(today + timedelta(days=k))[1] for k in range(1, ctx.cfg["live"]["horizon_days"] + 1)]
        ).value_counts().to_dict(),
        "alerts": alerts,
        "note": "Visitor history after 2025 is simulated with real weather until DWC / gate data are connected.",
    }
    for name, obj in (("outlook.json", outlook), ("forecast_tomorrow.json", tomorrow), ("status.json", status)):
        (PUBLISHED / name).write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")
    return status


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--today", default=None)
    a = ap.parse_args()
    s = refresh(date.fromisoformat(a.today) if a.today else None)
    print(json.dumps({k: v for k, v in s.items() if k != "alerts"}, indent=2))
    print(f"alerts: {len(s['alerts'])}")
