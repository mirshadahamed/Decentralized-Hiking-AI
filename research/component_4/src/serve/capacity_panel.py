"""Officer capacity panel (A2): the day's quota per trail under each rule, why the forecast lowers it, and which
rule the ticket plan uses.

    GET  /admin/capacity/{day}                       (officer)
    POST /admin/quota  {day, trail, rule, quota?}    (officer: choose forecast | classic | static | manual)

Every number says what it is based on (A6): the crowd forecast (ST-GNN for tomorrow, planning model later), the
weather (forecast or typical) and the fact that no counts exist inside the trail.
"""
import numpy as np

from src.capacity.cifuentes import capacity
from src.control import booking
from src.control.slots import build_control

SENSOR_BASIS = ("No counters inside the trail: the crowd forecast comes from the calendar, the weather forecast and "
                "a model trained on a calibrated simulation of this park")
EVIDENCE = ("Replay of 2025 (RQ9): at equal visitor numbers a forecast-driven quota cut over-capacity time by 27 % "
            "(Horton Plains) and 24 % (Adam's Peak) compared with one fixed quota all year")


def _label(cfg, seg_row) -> str:
    poi = seg_row.poi or ""
    trail = cfg["area"]["trail_names"].get(seg_row.trail, seg_row.trail)
    return cfg["area"].get("poi_labels", {}).get(poi, f"{trail}, section {int(seg_row.seg_id)}")


def day_panel(ctx, day, inputs: dict, db=None) -> dict:
    """inputs: rain_share, rain_basis, wet, conditions (as api.app.live_inputs)."""
    ec = build_control()
    cfg, iso = ec.cfg, day.isoformat()
    cond = {t: v["factor"] for t, v in inputs["conditions"].items()}
    fc, fc_basis = booking.day_forecast(iso, db)
    plan = ctx.planner.day(ctx.today.isoformat(), iso, rain_share=inputs["rain_share"],
                           wetness=inputs["wet"]["wetness"], conditions=cond)
    if fc is None:                                         # not saved by a refresh yet: the planning model
        fc, fc_basis = np.array(plan["hourly"]["p50"]), "planning model (likely case)"
        order = {int(i): j for j, i in enumerate(ctx.seg.seg_id)}
        fc = fc[:, [order[int(i)] for i in ec.seg.seg_id]]
    expected = {t: v["p50"] for t, v in plan["visitors_by_trail"].items()}
    cap = capacity(ec.seg, fc, None, expected, cfg["capacity"], cfg["simulator"], cfg["area"]["trail_names"],
                   rain_share=inputs["rain_share"], wetness=inputs["wet"]["wetness"], conditions=cond)
    quotas = booking.resolve_quota(iso, inputs["rain_share"], inputs["wet"]["wetness"], cond, db)
    open_h = (cfg["capacity"].get("open_from_h", 6) + np.arange(cfg["capacity"]["open_hours"])) % 24

    over = []
    for i, s in enumerate(cap["segments"]):
        hours = [int(h) for h in open_h if s["forecast_hourly"][h] > s["capacity_at_once"]]
        if hours:
            over.append({"seg_id": s["seg_id"], "trail": s["trail"], "name": _label(cfg, ec.seg.iloc[i]),
                         "hours": hours, "peak_people": s["peak_occupancy"], "capacity_at_once": s["capacity_at_once"],
                         "peak_hour": s["peak_hour"]})
    over.sort(key=lambda o: (-len(o["hours"]), -o["peak_people"] / max(o["capacity_at_once"], 1e-9)))

    trails = []
    for t, v in cap["trails"].items():
        q = quotas[t]
        lim = int(v["limiting_segment"])
        lim_row = ec.seg[ec.seg.seg_id == lim].iloc[0]
        lim_over = next((o for o in over if o["seg_id"] == lim), None)
        reason = (f"{_label(cfg, lim_row)} is expected over capacity "
                  f"{_hours(lim_over['hours'])}" if lim_over and q["forecast"] < q["classic"]
                  else "no section is expected over capacity: weather and trail conditions set the limit")
        trails.append({"trail": t, "name": v["name"], "expected_visitors": round(expected.get(t, 0)),
                       "quota": q, "limiting_section": _label(cfg, lim_row), "reason": reason,
                       "sections_over_capacity": sum(o["trail"] == t for o in over),
                       "condition": inputs["conditions"].get(t)})
    return {"day": iso, "rules": booking.QUOTA_RULES, "default_rule": ec.c.get("default_quota_rule", "forecast"),
            "trails": trails, "over_capacity": over,
            "basis": {"crowd": fc_basis, "weather": inputs["rain_basis"], "sensors": SENSOR_BASIS,
                      "evidence": EVIDENCE},
            "rain_share_open_hours": round(inputs["rain_share"], 3), "ground": inputs["wet"]}


def _hours(hours: list) -> str:
    """[9, 10, 11, 14] -> '09-12 h, 14-15 h'"""
    runs, start = [], None
    for i, h in enumerate(hours):
        if start is None:
            start = h
        if i == len(hours) - 1 or hours[i + 1] != h + 1:
            runs.append(f"{start:02d}-{h + 1:02d} h")
            start = None
    return ", ".join(runs)
