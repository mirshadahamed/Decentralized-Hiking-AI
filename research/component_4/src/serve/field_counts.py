"""A4: spot counts by rangers - the park's first sensor record - and the forecast checked against them.

    POST /counts                  (ranger)   {day, seg_id, time "HH:MM", count}
    GET  /counts/{day}            (ranger)
    GET  /segments                (public)   sections a ranger can count on (id, name, trail)
    GET  /admin/forecast-check    (officer)  ?start=&end=  every count next to the day-ahead forecast of that
                                              section and hour: error, bias, bottleneck hits

The forecast a count is compared with is the one saved for that day before it happened (booking.day_forecasts:
the ST-GNN day-ahead forecast, written by the daily refresh). Counts are kept as the park's own record and are
the input for field validation (docs/field_validation_protocol.md) and for recalibrating the simulator.
"""
from contextlib import closing
from datetime import datetime

import numpy as np

from src.control import booking
from src.control.slots import build_control


def _con(db=None):
    con = booking._connect(db)
    con.execute("CREATE TABLE IF NOT EXISTS spot_counts (id INTEGER PRIMARY KEY AUTOINCREMENT, day TEXT NOT NULL, "
                "seg_id INTEGER NOT NULL, time_min INTEGER NOT NULL, count INTEGER NOT NULL CHECK (count >= 0), "
                "counted_by TEXT NOT NULL, recorded_at TEXT NOT NULL, client_id TEXT, UNIQUE (client_id))")
    return con


def segments(cfg, model_input: set | None = None) -> list:
    """model_input: seg_ids whose counts update today's forecast (A1); listed first."""
    ec = build_control()
    labels = cfg["area"].get("poi_labels", {})
    names = cfg["area"]["trail_names"]
    out = []
    for _, s in ec.seg.iterrows():
        trail = names.get(s.trail, s.trail)
        out.append({"seg_id": int(s.seg_id), "trail": s.trail, "trail_name": trail,
                    "name": labels.get(s.poi, f"{trail}, section {int(s.seg_id)}") if s.poi else f"{trail}, section {int(s.seg_id)}",
                    "length_m": round(float(s.length_m)), "model_input": int(s.seg_id) in (model_input or set())})
    return sorted(out, key=lambda x: not x["model_input"])


def add_count(day: str, seg_id: int, time_min: int, count: int, by: str, client_id: str | None = None, db=None) -> dict:
    """Store a count. client_id (from the phone) makes a re-sent offline count harmless (stored once)."""
    if seg_id not in set(build_control().seg.seg_id.astype(int)):
        raise ValueError(f"Unknown section {seg_id}")
    if not 0 <= time_min < 24 * 60:
        raise ValueError("Time must be between 00:00 and 23:59")
    with closing(_con(db)) as con:
        con.execute("INSERT OR IGNORE INTO spot_counts (day, seg_id, time_min, count, counted_by, recorded_at, "
                    "client_id) VALUES (?,?,?,?,?,?,?)", (day, seg_id, time_min, count, by,
                                                         datetime.now().isoformat(timespec="seconds"), client_id))
        con.commit()
    return {"day": day, "seg_id": seg_id, "time_min": time_min, "count": count}


def counts(start: str, end: str, db=None) -> list:
    with closing(_con(db)) as con:
        rows = con.execute("SELECT day, seg_id, time_min, count, counted_by, recorded_at FROM spot_counts "
                           "WHERE day BETWEEN ? AND ? ORDER BY day, time_min", (start, end)).fetchall()
    return [{"day": d, "seg_id": s, "time_min": t, "count": c, "counted_by": by, "recorded_at": at}
            for d, s, t, c, by, at in rows]


def forecast_check(cfg, start: str, end: str, db=None) -> dict:
    """Every count next to the forecast of its section and hour, and the summary an officer needs to trust (or
    not) the forecast: mean error, bias, share within +-30 %, and whether over-capacity was called right."""
    ec = build_control()
    col = {int(i): j for j, i in enumerate(ec.seg.seg_id)}
    c = cfg["capacity"]
    at_once = ec.seg.length_m.values / (c["group_gap_m"] + c["group_size"] * c["space_per_person_m"]) * c["group_size"]
    names = {s["seg_id"]: s["name"] for s in segments(cfg)}
    rows, cache = [], {}
    for r in counts(start, end, db):
        if r["day"] not in cache:
            cache[r["day"]] = booking.day_forecast(r["day"], db, raw=True), booking.day_forecast(r["day"], db)[0]
        (fc, basis), fcc = cache[r["day"]]
        j = col[r["seg_id"]]
        f = None if fc is None else round(float(fc[r["time_min"] // 60, j]), 1)
        fcor = None if fcc is None else round(float(fcc[r["time_min"] // 60, j]), 1)
        cap = float(at_once[j])
        rows.append(r | {"name": names.get(r["seg_id"]), "forecast": f, "forecast_corrected": fcor,
                         "forecast_basis": basis,
                         "capacity_at_once": round(cap, 1),
                         "counted_over": r["count"] > cap, "forecast_over": None if f is None else f > cap})
    known = [x for x in rows if x["forecast"] is not None]
    summary = {"counts": len(rows), "with_forecast": len(known)}
    if known:
        e = np.array([x["forecast"] - x["count"] for x in known], float)
        cnt = np.array([x["count"] for x in known], float)
        co = np.array([x["counted_over"] for x in known])
        fo = np.array([x["forecast_over"] for x in known])
        summary |= {"mae": round(float(np.abs(e).mean()), 2), "bias": round(float(e.mean()), 2),
                    "within_30pct": round(float((np.abs(e) <= np.maximum(0.3 * cnt, 2)).mean()), 3),
                    "counted_over_capacity": int(co.sum()), "over_capacity_called": int((co & fo).sum()),
                    "false_alarms": int((~co & fo).sum())}
        ec_ = np.array([x["forecast_corrected"] - x["count"] for x in known], float)
        if not np.allclose(ec_, e):                             # N2: some days had a count-based correction
            summary |= {"mae_corrected": round(float(np.abs(ec_).mean()), 2),
                        "bias_corrected": round(float(ec_.mean()), 2)}
    return {"start": start, "end": end, "summary": summary, "rows": rows,
            "note": "Forecast = the day-ahead forecast saved before the day. Spot counts are the park's own sensor "
                    "record; they are also used to check and recalibrate the simulator the model learned from."}
