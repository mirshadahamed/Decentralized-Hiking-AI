"""N3 in the live service: a start time for visitors without a ticket, from the controller's day plan.

    GET  /start-time/{day}?trail=main&wanted=08:00&size=3     the earliest slot at or after `wanted` with room
    POST /start-time   {day, trail, slot, size}               hold that start time: returns a short code

The day plan is the MPC's caps per trail and slot from the day's expected visitors (src/control/mpc.py,
day_plan). Every start time given out is counted against the plan, so later visitors are spread to later slots.
Visitors who come at their start time are let in first at the gate (RQ13b: they wait ~0.5 min instead of ~70).
No personal data: a random code, day, trail, slot and group size. At the gate the ranger's normal check-in
accepts the code (booking.check_in): on time means let in first, and the group counts as an entry.
"""
import secrets
from contextlib import closing
from datetime import datetime
from functools import lru_cache

import numpy as np

from src.control import booking
from src.control.mpc import MPCController
from src.control.slots import build_control

MAX_SHIFT_MIN = 180


def _con(db=None):
    return booking._connect(db)                     # the start_advice table lives with the bookings


@lru_cache(maxsize=64)
def _plan(day: str, rain_share: float, expected: float) -> np.ndarray:
    return MPCController(build_control()).day_plan(rain_share, expected)


def _given(day: str, db=None) -> dict:
    with closing(_con(db)) as con:
        rows = con.execute("SELECT trail, slot, SUM(group_size) FROM start_advice WHERE day=? GROUP BY trail, slot",
                           (day,)).fetchall()
    return {(t, s): n for t, s, n in rows}


def suggest(day: str, trail: str, wanted: str, size: int, rain_share: float, expected: float, db=None) -> dict:
    ec = build_control()
    if trail not in ec.trails:
        raise ValueError(f"Unknown trail '{trail}'")
    h, m = (int(x) for x in wanted.split(":"))
    labels = [f"{s // 60:02d}:{s % 60:02d}" for s in ec.slots]
    r = ec.trails.index(trail)
    k0 = int(ec.slot_of(np.array([h * 60 + m]))[0])
    caps = _plan(day, round(rain_share, 3), round(expected))
    given = _given(day, db)
    options = []
    for k in range(k0, len(ec.slots)):
        if ec.slots[k] - ec.slots[k0] > MAX_SHIFT_MIN:
            break
        if not ec.allowed[r, k]:
            continue
        left = int(np.floor(caps[r, k] - float(given.get((trail, labels[k]), 0))))
        options.append({"slot": labels[k], "places_left": max(left, 0)})
    best = next((o for o in options if o["places_left"] >= size), None)
    return {"day": day, "trail": trail, "wanted": labels[k0], "suggested": best["slot"] if best else None,
            "later_than_wanted_min": int(ec.slots[labels.index(best["slot"])] - ec.slots[k0]) if best else None,
            "options": options,
            "note": ("Come at this time and you go in first at the gate. " if best else
                     "This trail is expected to be full for the next 3 hours: try another trail or day. ")
                    + "Planned from the day's crowd forecast so that no section gets over capacity."}


def hold(day: str, trail: str, slot: str, size: int, rain_share: float, expected: float, db=None) -> dict:
    s = suggest(day, trail, slot, size, rain_share, expected, db)
    opt = next((o for o in s["options"] if o["slot"] == slot), None)
    if opt is None or opt["places_left"] < size:
        raise ValueError(f"{slot} on this trail is full: try {s['suggested'] or 'another trail or day'}")
    code = "".join(secrets.choice(booking.CODE_ALPHABET) for _ in range(6))
    with closing(_con(db)) as con:
        con.execute("INSERT INTO start_advice (code, day, trail, slot, group_size, created) VALUES (?,?,?,?,?,?)",
                    (code, day, trail, slot, size, datetime.now().isoformat(timespec="seconds")))
        con.commit()
    return {"code": code, "day": day, "trail": trail, "slot": slot, "group_size": size}
