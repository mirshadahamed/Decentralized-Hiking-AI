"""§6.2.7 SOS: a visitor on a trail asks for help; the rangers of that park see it at once.

    POST /sos                         public: kind, people, note, and where - GPS (lat, lon, accuracy) when the phone
                                      has it, otherwise the trail and the last place passed. Re-sent with the same
                                      client_id (no signal, a newer GPS fix) it updates the same call, never a new one
    GET  /sos/check/{client_id}       public: has a ranger seen it / is one on the way
    GET  /sos/{day}                   ranger: the day's calls, open ones first, with the nearest section
    POST /sos/{id}/status             ranger: seen (on the way) / closed

Privacy (docs/privacy.md): no name or phone number; the position and note are deleted KEEP_DAYS after the call,
only kind, day, trail and times stay for the yearly safety report.
"""
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta

from src.control import booking

KEEP_DAYS = 30
KINDS = ("injury", "lost", "unwell", "other")
CALL = "If you have no signal, call 1990 (ambulance) or 119 (police)."


def _con(db=None):
    con = booking._connect(db)
    con.execute("""CREATE TABLE IF NOT EXISTS sos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, client_id TEXT UNIQUE NOT NULL, day TEXT NOT NULL, created TEXT NOT NULL,
        updated TEXT NOT NULL, kind TEXT NOT NULL, people INTEGER NOT NULL, note TEXT,
        lat REAL, lon REAL, accuracy_m REAL, trail TEXT, seg_id INTEGER, place TEXT,
        status TEXT NOT NULL DEFAULT 'open', handled_by TEXT, handled_at TEXT)""")
    return con


def nearest(seg, lat: float, lon: float) -> tuple[int, str, float]:
    """The section nearest to a GPS fix: (seg_id, trail, metres away; equirectangular, fine within a park)."""
    import numpy as np
    from shapely.geometry import Point
    k = np.cos(np.radians(lat))
    d = seg.geometry.distance(Point(lon, lat)).values                         # degrees, for ranking only
    i = int(np.argmin(d))
    g = seg.geometry.iloc[i]
    p = g.interpolate(g.project(Point(lon, lat)))
    m = float(np.hypot((p.x - lon) * 111320 * k, (p.y - lat) * 110540))
    return int(seg.seg_id.iloc[i]), str(seg.trail.iloc[i]), m


def place_name(cfg, seg, seg_id: int) -> str:
    row = seg[seg.seg_id == seg_id].iloc[0]
    trail = cfg["area"]["trail_names"].get(row.trail, row.trail)
    label = cfg["area"].get("poi_labels", {}).get(row.poi) if row.poi else None
    return f"{trail}, {label}" if label else f"{trail}, section {seg_id}"


def raise_sos(cfg, seg, now: datetime, client_id: str, kind: str, people: int, note: str = "",
              lat: float | None = None, lon: float | None = None, accuracy_m: float | None = None,
              trail: str | None = None, seg_id: int | None = None, db=None) -> dict:
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    if trail is not None and trail not in cfg["area"]["trail_names"]:
        raise KeyError(f"Unknown trail '{trail}'")
    off_m = None
    if lat is not None and lon is not None:
        seg_id, trail, off_m = nearest(seg, lat, lon)
    elif seg_id is not None:
        if not (seg.seg_id == seg_id).any():
            raise KeyError(f"Unknown section {seg_id}")
        trail = str(seg[seg.seg_id == seg_id].trail.iloc[0])
    place = place_name(cfg, seg, seg_id) if seg_id is not None else (
        cfg["area"]["trail_names"].get(trail, trail) if trail else "unknown place")
    if off_m is not None and off_m > 200:
        place += f" ({off_m / 1000:.1f} km off the trail)" if off_m >= 1000 else f" ({round(off_m, -1):.0f} m off the trail)"
    t = now.isoformat(timespec="seconds")
    purge(now, db)
    with closing(_con(db)) as con:
        con.execute("""INSERT INTO sos (client_id, day, created, updated, kind, people, note, lat, lon, accuracy_m,
                       trail, seg_id, place) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(client_id) DO UPDATE SET updated=excluded.updated, people=excluded.people,
                       note=COALESCE(excluded.note, note), lat=COALESCE(excluded.lat, lat),
                       lon=COALESCE(excluded.lon, lon), accuracy_m=COALESCE(excluded.accuracy_m, accuracy_m),
                       trail=COALESCE(excluded.trail, trail), seg_id=COALESCE(excluded.seg_id, seg_id),
                       place=CASE WHEN excluded.seg_id IS NULL AND excluded.trail IS NULL THEN place
                                  ELSE excluded.place END""",
                    (client_id, now.date().isoformat(), t, t, kind, people, note or None, lat, lon, accuracy_m, trail,
                     seg_id, place))
        con.commit()
    return check(client_id, db)


def check(client_id: str, db=None) -> dict:
    with closing(_con(db)) as con:
        con.row_factory = sqlite3.Row
        r = con.execute("SELECT id, day, created, updated, kind, people, place, status, handled_at FROM sos "
                        "WHERE client_id=?", (client_id,)).fetchone()
    if r is None:
        raise KeyError("Unknown SOS call")
    r = dict(r)
    r["note"] = {"open": "Rangers have your call. Stay where you are if it is safe; keep the phone on. ",
                 "seen": "A ranger has seen your call and is on the way. Stay where you are. ",
                 "closed": "This call is closed. "}[r["status"]] + CALL
    return r


def calls(day: str, db=None) -> dict:
    with closing(_con(db)) as con:
        con.row_factory = sqlite3.Row
        rows = [dict(r) for r in con.execute(
            "SELECT id, created, updated, kind, people, note, lat, lon, accuracy_m, trail, seg_id, place, status, "
            "handled_by, handled_at FROM sos WHERE day=? ORDER BY status='closed', created DESC, id DESC", (day,))]
    return {"day": day, "open": sum(r["status"] != "closed" for r in rows), "calls": rows}


def set_status(call_id: int, status: str, by: str, now: datetime, db=None) -> dict:
    if status not in ("seen", "closed"):
        raise ValueError("status must be seen or closed")
    with closing(_con(db)) as con:
        n = con.execute("UPDATE sos SET status=?, handled_by=?, handled_at=? WHERE id=?",
                        (status, by, now.isoformat(timespec="seconds"), call_id)).rowcount
        con.commit()
    if not n:
        raise KeyError(f"No SOS call {call_id}")
    return {"id": call_id, "status": status}


def purge(now: datetime, db=None) -> int:
    """Delete the position and note of calls older than KEEP_DAYS (privacy)."""
    before = (now - timedelta(days=KEEP_DAYS)).date().isoformat()
    with closing(_con(db)) as con:
        n = con.execute("UPDATE sos SET lat=NULL, lon=NULL, accuracy_m=NULL, note=NULL WHERE day<? AND "
                        "(lat IS NOT NULL OR note IS NOT NULL)", (before,)).rowcount
        con.commit()
    return n
