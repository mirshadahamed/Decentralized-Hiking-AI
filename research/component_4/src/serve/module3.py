"""Data contract with Module 3 (safety assistant) and the shared authority dashboard (FR4, proposal 4.3, WBS 10).

Module 4 publishes ONE small, versioned, read-only JSON per park and day; Module 3 reads it to steer hikers away
from forecast bottlenecks. Nothing else is shared, so the modules stay loosely coupled.

    GET /module3/feed                               (live: tomorrow's forecast for this park)
    python -m src.serve.module3                     (writes docs/schema/sample_module3_feed.json)

Contract: docs/schema/c4_module3_feed.schema.json (JSON Schema 2020-12), schema id "c4-module3-feed-1".
A new field is a minor change; renaming / removing a field or changing a meaning needs a new schema id.

Per segment Module 3 gets: where it is (trail, place), how many people are expected each hour, how many the segment
holds safely at once (Cifuentes social spacing), a status, the hours to avoid, and the safe visits per day (ECC).
Per trail: the safe number of visitors for the day and the segment that sets it.
"""
import json
from datetime import datetime

from src.config import ROOT

SCHEMA_ID = "c4-module3-feed-1"
SCHEMA_PATH = ROOT / "docs" / "schema" / "c4_module3_feed.schema.json"
SAMPLE_PATH = ROOT / "docs" / "schema" / "sample_module3_feed.json"


def module3_feed(forecast: dict, cfg: dict) -> dict:
    """forecast: build_forecast() output (published as forecast_tomorrow.json)."""
    c = cfg["capacity"]
    busy = float(c["busy_utilisation"])
    open_h = [int((c.get("open_from_h", 6) + k) % 24) for k in range(c["open_hours"])]
    labels = cfg["area"].get("poi_labels", {})
    segments = []
    for s in forecast["segments"]:
        cap = float(s["capacity_at_once"])
        hourly = [float(v) for v in s["forecast_hourly"]]
        segments.append({
            "segment_id": int(s["seg_id"]),
            "trail": s["trail"],
            "place": labels.get(s["poi"], s["poi"]) if s["poi"] else None,
            "length_m": round(float(s["length_m"])),
            "people_hourly": [round(v, 1) for v in hourly],
            "capacity_at_once": cap,
            "status": s["status"],
            "peak_hour": int(s["peak_hour"]),
            "avoid_hours": [h for h in open_h if cap > 0 and hourly[h] / cap >= busy],
            "safe_visits_per_day": int(s["ecc_per_day"]),
        })
    trails = [{
        "trail_id": t, "name": v["name"],
        "safe_visitors_per_day": int(v["recommended_daily_quota"]),
        "expected_visitors": int(v["expected_visitors"]),
        "limiting_segment_id": int(v["limiting_segment"]),
        "bottleneck_segments": int(v["bottleneck_segments"]),
    } for t, v in forecast["trails"].items()]
    return {
        "schema": SCHEMA_ID,
        "producer": "Component 4 - crowd and capacity forecasting (ST-GNN + Cifuentes)",
        "park": cfg["park"],
        "site": cfg["area"]["name"],
        "forecast_date": forecast["forecast_date"],
        "generated_at": forecast.get("generated_at") or datetime.now().isoformat(timespec="seconds"),
        "model": forecast["source"]["model"],
        "open_hours": open_h,
        "busy_utilisation": busy,
        "safe_visitors_per_day": int(forecast["recommended_daily_quota"]),
        "expected_visitors": int(forecast["expected_visitors"]),
        "segments": segments,
        "trails": trails,
        "disclaimer": forecast["disclaimer"],
    }


def schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


if __name__ == "__main__":
    from src.config import load_config
    from src.live.refresh import PUBLISHED
    cfg = load_config()
    feed = module3_feed(json.loads((PUBLISHED / "forecast_tomorrow.json").read_text(encoding="utf-8")), cfg)
    SAMPLE_PATH.write_text(json.dumps(feed, indent=1), encoding="utf-8")
    print(SAMPLE_PATH, f"{SAMPLE_PATH.stat().st_size / 1024:.0f} KB")
