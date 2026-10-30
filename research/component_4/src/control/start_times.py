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
def _plan(day: str, rain_share: float, expected: float, cond: tuple = ()) -> np.ndarray:
    return MPCController(build_control()).day_plan(rain_share, expected, dict(cond))


PRIOR_ON_TIME, PRIOR_WEIGHT, WINDOW_DAYS = 0.8, 10.0, 30


def on_time_share(day: str, db=None) -> dict:
    """R4 (N2 with compliance): the share of start-time holders who came through the gate at their time, over the
    WINDOW_DAYS before `day`, pulled towards PRIOR_ON_TIME (RQ13b's follow rate) when there are few holders."""
    from datetime import date, timedelta
    d = date.fromisoformat(day)
    with closing(_con(db)) as con:
        n, came = con.execute("SELECT COUNT(*), SUM(arrived_at IS NOT NULL) FROM start_advice WHERE day>=? AND day<?",
                              ((d - timedelta(days=WINDOW_DAYS)).isoformat(), day)).fetchone()
    n, came = int(n or 0), int(came or 0)
    return {"holders": n, "came_on_time": came,
            "share": round((came + PRIOR_ON_TIME * PRIOR_WEIGHT) / (n + PRIOR_WEIGHT), 3)}


def _given(day: str, db=None) -> dict:
    """People expected at each held start time: held x the recent on-time share (not everyone who holds comes),
    so later visitors are not sent later for places that will stay empty."""
    share = on_time_share(day, db)["share"]
    with closing(_con(db)) as con:
        rows = con.execute("SELECT trail, slot, SUM(group_size) FROM start_advice WHERE day=? GROUP BY trail, slot",
                           (day,)).fetchall()
    return {(t, s): n * share for t, s, n in rows}


def suggest(day: str, trail: str, wanted: str, size: int, rain_share: float, expected: float, db=None) -> dict:
    ec = build_control()
    if trail not in ec.trails:
        raise ValueError(f"Unknown trail '{trail}'")
    h, m = (int(x) for x in wanted.split(":"))
    labels = [f"{s // 60:02d}:{s % 60:02d}" for s in ec.slots]
    r = ec.trails.index(trail)
    k0 = int(ec.slot_of(np.array([h * 60 + m]))[0])
    caps = _plan(day, round(rain_share, 3), round(expected), tuple(sorted(booking.condition_factors(day, db).items())))
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


def held(code: str, db=None) -> dict | None:
    with closing(_con(db)) as con:
        r = con.execute("SELECT code, day, trail, slot, group_size, arrived_at FROM start_advice WHERE code=?",
                        (code.strip().upper(),)).fetchone()
    return dict(zip(["code", "day", "trail", "slot", "group_size", "arrived_at"], r)) if r else None


def recheck(code: str, now: datetime, rain_share: float, expected: float, db=None) -> dict:
    """Morning re-check before leaving: re-plan from the gate counts so far, the day's forecast (corrected by how
    many came so far) and any trail condition reported today. If the held slot no longer has room for the group,
    suggest the earliest later slot that has (move() changes the hold)."""
    h = held(code, db)
    if h is None:
        raise KeyError("Unknown code")
    out = {k: h[k] for k in ("code", "day", "trail", "slot", "group_size")}
    if h["arrived_at"]:
        return out | {"status": "used", "note": "Already through the gate."}
    if h["day"] != now.date().isoformat():
        return out | {"status": "ok", "note": "Check again on the morning of your walk: the plan is updated from "
                                               "the gate counts during the day."}
    cond = booking.condition_factors(h["day"], db)
    from src.control.chance import live_kwargs
    ec = build_control()
    live = MPCController(ec, **live_kwargs(ec.cfg)).caps_now(booking.entries(h["day"], db), now.hour * 60 + now.minute,
                                                   rain_share, expected, cond)
    t = next(x for x in live["trails"] if x["trail"] == h["trail"])
    caps = {live["slot"]: t["can_enter_now"]} | {x["slot"]: x["cap"] for x in t["next_slots"]}
    if caps.get(h["slot"], h["group_size"]) >= h["group_size"] or h["slot"] < live["slot"]:
        return out | {"status": "ok", "note": f"Your start at {h['slot']} still has room. Come on time and you go in first."}
    later = next((s for s, c in sorted(caps.items()) if s > h["slot"] and c >= h["group_size"]), None)
    why = "the trail is closed today" if cond.get(h["trail"], 0) >= 1 else "more people came than expected"
    return out | {"status": "later" if later else "full", "suggested": later,
                  "note": (f"Busier than planned ({why}): start at {later} instead and you still go in first."
                           if later else f"No room on this trail in the next hours ({why}): choose another trail.")}


def move(code: str, slot: str, db=None) -> dict:
    with closing(_con(db)) as con:
        n = con.execute("UPDATE start_advice SET slot=? WHERE code=? AND arrived_at IS NULL",
                        (slot, code.strip().upper())).rowcount
        con.commit()
    if not n:
        raise KeyError("Unknown or already used code")
    return held(code, db)
