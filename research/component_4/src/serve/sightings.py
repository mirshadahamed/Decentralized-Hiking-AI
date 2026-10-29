"""Safari parks (Yala): wildlife sightings reported by rangers / trackers, and what to do at each one.

    POST /sightings               (ranger)   {day, seg_id, time "HH:MM", species, client_id}
    POST /sightings/{id}/end      (ranger)   {time "HH:MM"}  the animal has gone
    GET  /sightings/{day}         (ranger)   ?at=HH:MM  active sightings with advice

A sighting holds every passing jeep, so the jam is where the animal is, not where any calendar says. The advice
applies the ranger's rule tested in src/control/evaluate_sightings.py (at most `cap_jeeps` stopped at once, each for
at most `rotation_min`; config control.sighting_rule) and estimates the jeeps on and next to that section from the
gate entries (no trail sensors), so the gate can send new jeeps on a circuit that does not pass it.
"""
from contextlib import closing
from datetime import datetime

import numpy as np

from src.config import PROCESSED
from src.control import booking
from src.control.slots import build_control
from src.data.graph import load_walks


def _con(db=None):
    con = booking._connect(db)
    con.execute("CREATE TABLE IF NOT EXISTS sightings (id INTEGER PRIMARY KEY AUTOINCREMENT, day TEXT NOT NULL, "
                "seg_id INTEGER NOT NULL, start_min INTEGER NOT NULL, end_min INTEGER, species TEXT NOT NULL, "
                "reported_by TEXT NOT NULL, recorded_at TEXT NOT NULL, client_id TEXT, UNIQUE (client_id))")
    return con


def add(day: str, seg_id: int, start_min: int, species: str, by: str, client_id: str | None = None, db=None) -> int:
    if seg_id not in set(build_control().seg.seg_id.astype(int)):
        raise ValueError(f"Unknown section {seg_id}")
    if not 0 <= start_min < 24 * 60:
        raise ValueError("Time must be between 00:00 and 23:59")
    with closing(_con(db)) as con:
        con.execute("INSERT OR IGNORE INTO sightings (day, seg_id, start_min, species, reported_by, recorded_at, "
                    "client_id) VALUES (?,?,?,?,?,?,?)", (day, seg_id, start_min, species.strip()[:40] or "animal", by,
                                                          datetime.now().isoformat(timespec="seconds"), client_id))
        con.commit()
        row = con.execute("SELECT id FROM sightings WHERE client_id IS ? AND day=? AND seg_id=? AND start_min=? "
                          "ORDER BY id DESC", (client_id, day, seg_id, start_min)).fetchone()
    return int(row[0])


def end(sighting_id: int, end_min: int, db=None) -> bool:
    with closing(_con(db)) as con:
        n = con.execute("UPDATE sightings SET end_min=? WHERE id=? AND end_min IS NULL", (end_min, sighting_id)).rowcount
        con.commit()
    return n > 0


def listed(day: str, db=None) -> list:
    with closing(_con(db)) as con:
        rows = con.execute("SELECT id, seg_id, start_min, end_min, species, reported_by FROM sightings WHERE day=? "
                           "ORDER BY start_min", (day,)).fetchall()
    return [{"id": i, "seg_id": s, "start_min": a, "end_min": b, "species": sp, "reported_by": by}
            for i, s, a, b, sp, by in rows]


def _hhmm(m: int) -> str:
    return f"{int(m) // 60:02d}:{int(m) % 60:02d}"


def advice(cfg, day: str, now_min: int, rain_share: float = 0.0, db=None) -> dict:
    """Active sightings (started, not ended, younger than `expire_min`) with the rule and what to do at the gate."""
    rule = cfg["control"].get("sighting_rule", {"cap_jeeps": 10, "rotation_min": 10, "expire_min": 90})
    ec = build_control()
    ids = ec.seg.seg_id.astype(int).tolist()
    pos = {s: i for i, s in enumerate(ids)}
    occ = ec.nowcast(booking.entries(day, db), now_min, rain_share)          # people per section, from the gate
    ei = np.load(PROCESSED / "edge_index.npy")
    walks = load_walks()
    names = cfg["area"]["trail_names"]
    labels = cfg["area"].get("poi_labels", {})
    per_jeep = 1 + cfg["simulator"]["group_size_poisson_mean"]
    out = []
    for r in listed(day, db):
        if r["start_min"] > now_min or (r["end_min"] is not None and r["end_min"] <= now_min) or \
                now_min - r["start_min"] > rule.get("expire_min", 90):
            continue
        s = r["seg_id"]
        near = [s] + sorted({int(b) for a, b in ei.T if int(a) == s})
        jeeps = int(round(sum(occ[pos[x]] for x in near if x in pos) / per_jeep))
        poi = ec.seg.poi.fillna("").values[pos[s]]
        place = labels.get(poi) or f"section {s}"
        avoid = [t for t, w in walks.items() if all(x != s for x, _ in w)]
        text = (f"{r['species'].capitalize()} at {place} since {_hhmm(r['start_min'])}: at most {rule['cap_jeeps']} "
                f"jeeps stopped at once, {rule['rotation_min']} min each; others move on.")
        if jeeps > rule["cap_jeeps"] and avoid:
            text += f" About {jeeps} jeeps near it: send new jeeps on {' / '.join(names[t] for t in avoid)}."
        out.append(r | {"place": place, "since": _hhmm(r["start_min"]), "jeeps_near": jeeps,
                        "cap_jeeps": rule["cap_jeeps"], "rotation_min": rule["rotation_min"],
                        "circuits_avoiding": [names[t] for t in avoid], "advice": text})
    return {"day": day, "time": _hhmm(now_min), "sightings": out,
            "note": "Jeeps near a sighting are estimated from the gate entries (no sensors on the tracks)."}
