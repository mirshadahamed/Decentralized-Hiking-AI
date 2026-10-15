"""Slot booking: reserve an entry slot on a trail up to 90 days ahead, so no one is disappointed at the gate.

- Tickets per slot come from the entry-control plan (src/control/slots.py) for that day; for days further
  ahead than the weather forecast, the rain share is the typical one for that time of year.
- A share of every slot (walk_in_share, 20 %) is never bookable: kept for visitors without internet.
- When the chosen slot is full, alternatives are offered: a nearby slot, another trail, another day.
- At the gate a booking code is valid from 15 min before to 15 min after its slot start.
- No personal data is stored (NFR5): only a random code, date, trail, slot and group size.
Storage: data/bookings.sqlite (local; in production this would sit on the park's server / ticket system).
"""
import secrets
import sqlite3
from contextlib import closing
from datetime import date, datetime, timedelta
from functools import lru_cache

import numpy as np
import pandas as pd

from src.config import DATA, PROCESSED, load_config
from src.control.slots import build_control

DB = DATA / "bookings.sqlite"
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"        # no 0/O, 1/I


class SlotFull(Exception):
    def __init__(self, message, alternatives):
        super().__init__(message)
        self.alternatives = alternatives


def _connect(db=None):
    con = sqlite3.connect(db or DB)                      # DB looked up at call time (tests can redirect it)
    con.execute("""CREATE TABLE IF NOT EXISTS bookings (
        code TEXT PRIMARY KEY, day TEXT NOT NULL, trail TEXT NOT NULL, slot TEXT NOT NULL,
        group_size INTEGER NOT NULL CHECK (group_size BETWEEN 1 AND 20),
        created TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'booked')""")
    return con


@lru_cache(maxsize=1)
def _climatology_rain_share() -> pd.Series:
    """Typical share of rainy open hours per day of year (2022-23 = training years, +-15 days)."""
    from src.data.weather import load_weather
    cfg = load_config()
    w = load_weather(cfg)
    open_h = (w.index.hour >= 6) & (w.index.hour < 6 + cfg["capacity"]["open_hours"])
    daily = (w.precipitation[open_h] >= cfg["capacity"]["rain_mm"]).groupby(w.index[open_h].normalize()).mean()
    train = daily[daily.index <= pd.Timestamp(cfg["dates"]["train_end"])]
    doy = train.index.dayofyear.values
    out = {}
    for d in range(1, 367):
        dist = np.minimum(np.abs(doy - d), 365 - np.abs(doy - d))
        out[d] = float(train.values[dist <= 15].mean())
    return pd.Series(out)


@lru_cache(maxsize=256)
def supply(day: str, rain_share: float | None = None) -> pd.DataFrame:
    """Bookable tickets per slot and trail for a day (after keeping the walk-in share)."""
    ec = build_control()
    if rain_share is None:
        rain_share = _climatology_rain_share()[pd.Timestamp(day).dayofyear]
    plan = ec.plan(rain_share, ec.daily_quota(rain_share))
    return np.floor(plan * (1 - ec.c["walk_in_share"])).astype(int)


def booked(day: str, db=None) -> pd.DataFrame:
    with closing(_connect(db)) as con:
        rows = con.execute("SELECT slot, trail, SUM(group_size) FROM bookings WHERE day=? AND status!='cancelled' "
                           "GROUP BY slot, trail", (day,)).fetchall()
    sup = supply(day)
    out = pd.DataFrame(0, index=sup.index, columns=sup.columns)
    for slot, trail, n in rows:
        out.loc[slot, trail] = n
    return out


def availability(day: str, db=None) -> pd.DataFrame:
    """Places left per slot (rows) and trail (columns)."""
    return (supply(day) - booked(day, db)).clip(lower=0)


def alternatives(day: str, trail: str, slot: str, size: int, db=None, max_items=6) -> list:
    """Nearest options with room: same trail other slots, other trails around the same time, nearby days."""
    out = []
    av = availability(day, db)
    slots = list(av.index)
    k = slots.index(slot)
    for kk in sorted(range(len(slots)), key=lambda j: (abs(j - k), j < k)):
        if kk != k and av.iloc[kk][trail] >= size:
            out.append({"day": day, "trail": trail, "slot": slots[kk], "left": int(av.iloc[kk][trail]), "kind": "slot"})
            if len([o for o in out if o["kind"] == "slot"]) >= 2:
                break
    for t in av.columns:
        if t == trail:
            continue
        for kk in sorted(range(len(slots)), key=lambda j: abs(j - k)):
            if av.iloc[kk][t] >= size:
                out.append({"day": day, "trail": t, "slot": slots[kk], "left": int(av.iloc[kk][t]), "kind": "trail"})
                break
    d0 = date.fromisoformat(day)
    for delta in (1, -1, 2, -2, 3, -3):
        d = (d0 + timedelta(days=delta)).isoformat()
        try:
            avd = availability(d, db)
        except (ValueError, KeyError):
            continue
        if avd.loc[slot, trail] >= size:
            out.append({"day": d, "trail": trail, "slot": slot, "left": int(avd.loc[slot, trail]), "kind": "day"})
            break
    return out[:max_items]


def book(day: str, trail: str, slot: str, size: int, today: str | None = None, db=None) -> str:
    """Reserve places; returns the booking code. Raises SlotFull (with alternatives) or ValueError."""
    cfg = load_config()["control"]
    today_d = date.fromisoformat(today) if today else date.today()
    d = date.fromisoformat(day)
    if not today_d < d <= today_d + timedelta(days=cfg["booking_horizon_days"]):
        raise ValueError(f"Bookings open from tomorrow up to {cfg['booking_horizon_days']} days ahead.")
    if not 1 <= size <= 20:
        raise ValueError("Group size must be 1-20.")
    sup = supply(day)
    if slot not in sup.index or trail not in sup.columns or sup.loc[slot, trail] == 0:
        raise SlotFull("No tickets are issued for this slot and trail.", alternatives(day, trail, slot, size, db))
    with closing(_connect(db)) as con:
        con.execute("BEGIN IMMEDIATE")                      # one booking at a time: no overbooking
        used = con.execute("SELECT COALESCE(SUM(group_size), 0) FROM bookings WHERE day=? AND trail=? AND slot=? "
                           "AND status!='cancelled'", (day, trail, slot)).fetchone()[0]
        if used + size > sup.loc[slot, trail]:
            con.rollback()
            raise SlotFull(f"Only {max(0, sup.loc[slot, trail] - used)} places left in this slot.",
                           alternatives(day, trail, slot, size, db))
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
        con.execute("INSERT INTO bookings (code, day, trail, slot, group_size, created) VALUES (?,?,?,?,?,?)",
                    (code, day, trail, slot, size, datetime.now().isoformat(timespec="seconds")))
        con.commit()
    return code


def cancel(code: str, db=None) -> bool:
    with closing(_connect(db)) as con:
        n = con.execute("UPDATE bookings SET status='cancelled' WHERE code=? AND status='booked'", (code,)).rowcount
        con.commit()
    return n > 0


def check_in(code: str, now: datetime, db=None) -> dict:
    """Gate check: valid only on the booked day, from 15 min before to 15 min after the slot start."""
    win = load_config()["control"]["slot_window_min"]
    with closing(_connect(db)) as con:
        row = con.execute("SELECT day, trail, slot, group_size, status FROM bookings WHERE code=?",
                          (code.strip().upper(),)).fetchone()
        if row is None:
            return {"ok": False, "reason": "Unknown code"}
        day, trail, slot, size, status = row
        info = {"day": day, "trail": trail, "slot": slot, "group_size": size}
        if status != "booked":
            return {"ok": False, "reason": f"Booking is {status}", **info}
        start = datetime.fromisoformat(f"{day}T{slot}")
        if now < start - timedelta(minutes=win):
            return {"ok": False, "reason": f"Too early: gate opens for this ticket at "
                                           f"{(start - timedelta(minutes=win)):%H:%M} on {day}", **info}
        if now > start + timedelta(minutes=win):
            return {"ok": False, "reason": "Too late for this slot: ask at the counter for a walk-in place", **info}
        con.execute("UPDATE bookings SET status='checked_in' WHERE code=?", (code.strip().upper(),))
        con.commit()
    return {"ok": True, "reason": "Welcome", **info}


def bookings_for_code(code: str, db=None) -> dict | None:
    with closing(_connect(db)) as con:
        row = con.execute("SELECT day, trail, slot, group_size, status FROM bookings WHERE code=?",
                          (code.strip().upper(),)).fetchone()
    return dict(zip(["day", "trail", "slot", "group_size", "status"], row)) if row else None


def bookings_for(day: str, db=None) -> pd.DataFrame:
    with closing(_connect(db)) as con:
        return pd.read_sql_query("SELECT code, trail, slot, group_size, status, created FROM bookings WHERE day=? "
                                 "ORDER BY slot", con, params=(day,))

