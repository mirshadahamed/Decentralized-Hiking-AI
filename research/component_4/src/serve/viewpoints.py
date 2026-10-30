"""K6 / K7: open viewpoints with parking, and campsites (control modes open_viewpoint and campsite; Knuckles).

    GET /viewpoints/{day}        per open viewpoint: people at the busiest hour vs what the place holds, cars
                                 needed vs parking spaces, and when to come instead (advice only: open access)
    GET /campsites/{night}       pitches left per campsite
    POST /campsites              {night, site, pitches, people} -> code (409 when full)

A viewpoint is full when the people on its sections at once reach their capacity (the viewpoint's own section
uses control.viewpoint_min_at_once). Parking: the people on the walk at once came by car, so cars parked at once =
people / people per vehicle; a ranger's "parking full" report (POST /incident, level partly_closed with a note)
shows as an alert. No personal data.
"""
import secrets
from contextlib import closing
from datetime import datetime

import numpy as np

from src.control import booking


def viewpoint_outlook(cfg, seg, hourly: np.ndarray, trails: list, day: str, conditions: dict | None = None) -> dict:
    """seg: segments in the column order of hourly [24 h, segments] (people at once)."""
    c, ctl = cfg["capacity"], cfg["control"]
    names = cfg["area"]["trail_names"]
    views = set(cfg["area"].get("poi_roles", {}).get("viewpoint", []))
    cap = seg.length_m.values / (c["group_gap_m"] + c["group_size"] * c["space_per_person_m"]) * c["group_size"]
    cap = np.where(seg.poi.fillna("").isin(views).values, np.maximum(cap, ctl.get("viewpoint_min_at_once", 0)), cap)
    out = []
    for t in trails:
        idx = np.where(seg.trail.values == t)[0]
        if not len(idx):
            continue
        p = cfg["control"].get("viewpoints", {}).get(t, {})
        people = hourly[:, idx].sum(1)                                   # on the walk at once
        full = (hourly[:, idx] / np.maximum(cap[idx], 1e-9)).max(1)
        h = int(np.argmax(full))
        cars = people / p.get("people_per_vehicle", 4.0)              # everyone on the walk left a car parked
        spaces = p.get("parking_spaces")
        park_full = [int(x) for x in np.where(cars >= spaces)[0]] if spaces else []
        busy = [int(x) for x in np.where(full >= 0.5)[0]]
        level = "crowded" if full.max() >= 1 else "busy" if full.max() >= 0.5 else "quiet"
        if level == "quiet" and not park_full:
            advice = "Quiet all day."
        else:
            first = min(busy + park_full)
            last = max(busy + park_full)
            advice = (f"{'Crowded' if level == 'crowded' else 'Busy'} {first:02d}:00–{last + 1:02d}:00"
                      + (f", car park full {park_full[0]:02d}:00–{park_full[-1] + 1:02d}:00" if park_full else "")
                      + f". Come before {max(6, first - 1):02d}:00 or after {min(17, last + 1):02d}:00.")
        cond = (conditions or {}).get(t)
        out.append({"trail": t, "name": names.get(t, t), "level": level, "fullness": round(float(full.max()), 2),
                    "busiest_hour": f"{h:02d}:00", "people_at_busiest_hour": round(float(people[h]), 1),
                    "cars_at_busiest_hour": round(float(cars.max()), 1), "parking_spaces": spaces,
                    "parking_full_hours": [f"{x:02d}:00" for x in park_full], "advice": advice,
                    "reported": None if cond is None else f"{cond['level'].replace('_', ' ')}"
                                                          + (f" - {cond['note']}" if cond.get("note") else ""),
                    "hourly_people": [round(float(x), 1) for x in people]})
    return {"day": day, "viewpoints": out,
            "basis": "Crowd forecast per section; parking = people there at once / people per car. Open access: "
                     "advice only, nobody is turned away."}


# ---------- campsites ----------
def _con(db=None):
    con = booking._connect(db)
    con.execute("CREATE TABLE IF NOT EXISTS campsite_bookings (code TEXT PRIMARY KEY, night TEXT NOT NULL, "
                "site TEXT NOT NULL, pitches INTEGER NOT NULL, people INTEGER NOT NULL, created TEXT NOT NULL)")
    return con


def campsites(cfg, night: str, db=None) -> dict:
    sites = cfg["control"].get("campsites", {})
    with closing(_con(db)) as con:
        used = dict(con.execute("SELECT site, SUM(pitches) FROM campsite_bookings WHERE night=? GROUP BY site",
                                (night,)).fetchall())
    names = cfg["area"]["trail_names"]
    return {"night": night, "sites": [{"site": k, "name": v["name"], "trail": v.get("trail"),
                                       "trail_name": names.get(v.get("trail"), v.get("trail")), "pitches": v["pitches"],
                                       "left": max(0, v["pitches"] - int(used.get(k, 0) or 0))} for k, v in sites.items()]}


def book_campsite(cfg, night: str, site: str, pitches: int, people: int, db=None) -> dict:
    s = next((x for x in campsites(cfg, night, db)["sites"] if x["site"] == site), None)
    if s is None:
        raise KeyError(f"Unknown campsite '{site}'")
    if pitches > s["left"]:
        others = [x["name"] for x in campsites(cfg, night, db)["sites"] if x["left"] >= pitches and x["site"] != site]
        raise ValueError(f"{s['name']} has {s['left']} pitch(es) left on {night}"
                         + (f"; room at {', '.join(others)}" if others else ""))
    code = "".join(secrets.choice(booking.CODE_ALPHABET) for _ in range(7))
    with closing(_con(db)) as con:
        con.execute("INSERT INTO campsite_bookings VALUES (?,?,?,?,?,?)",
                    (code, night, site, pitches, people, datetime.now().isoformat(timespec="seconds")))
        con.commit()
    return {"code": code, "night": night, "site": site, "name": s["name"], "pitches": pitches, "people": people}
