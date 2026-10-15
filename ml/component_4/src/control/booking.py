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
    con.executescript("""
        CREATE TABLE IF NOT EXISTS bookings (
            code TEXT PRIMARY KEY, day TEXT NOT NULL, trail TEXT NOT NULL, slot TEXT NOT NULL,
            group_size INTEGER NOT NULL CHECK (group_size BETWEEN 1 AND 20),
            created TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'booked');
        CREATE TABLE IF NOT EXISTS published_slots (
            day TEXT NOT NULL, trail TEXT NOT NULL, slot TEXT NOT NULL,
            tickets INTEGER NOT NULL, bookable INTEGER NOT NULL, walk_in INTEGER NOT NULL,
            rain_share REAL NOT NULL, basis TEXT NOT NULL, published_at TEXT NOT NULL,
            PRIMARY KEY (day, trail, slot));
        CREATE TABLE IF NOT EXISTS closures (
            id INTEGER PRIMARY KEY AUTOINCREMENT, day TEXT NOT NULL, trail TEXT NOT NULL,
            slot_from TEXT NOT NULL, slot_to TEXT NOT NULL, reason TEXT NOT NULL,
            created_by TEXT NOT NULL, created TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS walkins (
            id INTEGER PRIMARY KEY AUTOINCREMENT, day TEXT NOT NULL, trail TEXT NOT NULL, slot TEXT NOT NULL,
            group_size INTEGER NOT NULL, sold_by TEXT NOT NULL, sold_at TEXT NOT NULL);
    """)
    cols = [r[1] for r in con.execute("PRAGMA table_info(bookings)")]
    if "checked_in_at" not in cols:                           # older databases
        con.execute("ALTER TABLE bookings ADD COLUMN checked_in_at TEXT")
    return con


def entries(day: str, db=None) -> pd.DataFrame:
    """Everyone who actually went through the gate on a day (checked-in bookings + walk-ins):
    trail, gate_min (minutes after midnight), size. Input for the live estimate (nowcast)."""
    with closing(_connect(db)) as con:
        rows = con.execute("SELECT trail, checked_in_at, group_size FROM bookings WHERE day=? AND checked_in_at "
                           "IS NOT NULL UNION ALL SELECT trail, sold_at, group_size FROM walkins WHERE day=?",
                           (day, day)).fetchall()
    out = [{"trail": t, "gate_min": datetime.fromisoformat(at).hour * 60 + datetime.fromisoformat(at).minute,
            "size": n} for t, at, n in rows]
    return pd.DataFrame(out, columns=["trail", "gate_min", "size"])


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


@lru_cache(maxsize=512)
def _planned(day: str, rain_share: float, closed: tuple = ()) -> pd.DataFrame:
    """All tickets per slot and trail (bookable + walk-in) from the entry-control plan."""
    ec = build_control()
    return ec.plan(rain_share, ec.daily_quota(rain_share), closed=set(closed))


def typical_rain_share(day: str) -> float:
    return float(_climatology_rain_share()[pd.Timestamp(day).dayofyear])


def _published(day: str, db=None) -> pd.DataFrame | None:
    with closing(_connect(db)) as con:
        rows = con.execute("SELECT slot, trail, tickets, bookable, walk_in, rain_share, basis, published_at "
                           "FROM published_slots WHERE day=?", (day,)).fetchall()
    if not rows:
        return None
    return pd.DataFrame(rows, columns=["slot", "trail", "tickets", "bookable", "walk_in", "rain_share", "basis",
                                       "published_at"])


def supply(day: str, db=None) -> pd.DataFrame:
    """Bookable places per slot (rows) and trail (columns): the published plan if there is one,
    otherwise a provisional plan from typical weather (after keeping the walk-in share)."""
    pub = _published(day, db)
    if pub is not None:
        return pub.pivot(index="slot", columns="trail", values="bookable")[build_control().trails].astype(int)
    plan = _planned(day, typical_rain_share(day))
    return np.floor(plan * (1 - build_control().c["walk_in_share"])).astype(int)


def closed_slots(day: str, db=None) -> set:
    """(trail, slot) pairs closed by an officer for this day."""
    ec = build_control()
    labels = [f"{s // 60:02d}:{s % 60:02d}" for s in ec.slots]
    with closing(_connect(db)) as con:
        rows = con.execute("SELECT trail, slot_from, slot_to FROM closures WHERE day=? AND active=1", (day,)).fetchall()
    return {(t, s) for t, a, b in rows for s in labels if a <= s <= b}


def publish_day(day: str, rain_share: float, basis: str, db=None) -> list:
    """Publish the slot plan for a day with the FREEZE RULE: a slot never offers fewer bookable places than are
    already booked. Walk-in places are cut first; if booked places exceed the safe plan (worse weather or a
    closure), an alert is returned for the officer (bookings are never cancelled silently)."""
    ec = build_control()
    closed = tuple(sorted(closed_slots(day, db)))
    plan = _planned(day, round(rain_share, 3), closed)
    safe_bookable = np.floor(plan * (1 - ec.c["walk_in_share"])).astype(int)
    bk = booked(day, db, index=plan.index, columns=plan.columns)
    bookable = np.maximum(safe_bookable, bk)
    walk_in = (plan - bookable).clip(lower=0)
    alerts = []
    for slot in plan.index:
        for trail in plan.columns:
            if bk.loc[slot, trail] > safe_bookable.loc[slot, trail]:
                alerts.append({"day": day, "trail": trail, "slot": slot, "booked": int(bk.loc[slot, trail]),
                               "safe_places": int(safe_bookable.loc[slot, trail]),
                               "reason": "closed" if (trail, slot) in closed else "lower capacity (weather)"})
    now = datetime.now().isoformat(timespec="seconds")
    with closing(_connect(db)) as con:
        con.execute("DELETE FROM published_slots WHERE day=?", (day,))
        con.executemany("INSERT INTO published_slots VALUES (?,?,?,?,?,?,?,?,?)",
                        [(day, t, s, int(plan.loc[s, t]), int(bookable.loc[s, t]), int(walk_in.loc[s, t]),
                          float(rain_share), basis, now) for s in plan.index for t in plan.columns])
        con.commit()
    return alerts


def close(day: str, trail: str, slot_from: str, slot_to: str, reason: str, by: str, db=None) -> list:
    """Officer closes a trail for a time window; the day is re-published at once. Returns freeze-rule alerts."""
    with closing(_connect(db)) as con:
        con.execute("INSERT INTO closures (day, trail, slot_from, slot_to, reason, created_by, created) "
                    "VALUES (?,?,?,?,?,?,?)", (day, trail, slot_from, slot_to, reason, by,
                                               datetime.now().isoformat(timespec="seconds")))
        con.commit()
    pub = _published(day, db)
    rain = float(pub.rain_share.iloc[0]) if pub is not None else typical_rain_share(day)
    basis = pub.basis.iloc[0] if pub is not None else "typical weather"
    return publish_day(day, rain, basis, db)


def walk_in_left(day: str, db=None) -> pd.DataFrame:
    pub = _published(day, db)
    if pub is None:
        ec = build_control()
        plan = _planned(day, typical_rain_share(day))
        cap = plan - np.floor(plan * (1 - ec.c["walk_in_share"])).astype(int)
    else:
        cap = pub.pivot(index="slot", columns="trail", values="walk_in")[build_control().trails]
    with closing(_connect(db)) as con:
        rows = con.execute("SELECT slot, trail, SUM(group_size) FROM walkins WHERE day=? GROUP BY slot, trail",
                           (day,)).fetchall()
    sold = pd.DataFrame(0, index=cap.index, columns=cap.columns)
    for s, t, n in rows:
        sold.loc[s, t] = n
    return (cap - sold).clip(lower=0).astype(int)


def sell_walk_in(day: str, trail: str, slot: str, size: int, by: str, db=None, now: datetime | None = None) -> int:
    """Ranger sells walk-in places at the gate. Returns places left in that slot; raises SlotFull if none.
    now: time of sale (defaults to the clock; demos may pass a time)."""
    now = now or datetime.now()
    with closing(_connect(db)) as con:
        con.execute("BEGIN IMMEDIATE")
        left = int(walk_in_left(day, db).loc[slot, trail])
        if size > left:
            con.rollback()
            raise SlotFull(f"Only {left} walk-in places left in this slot.", alternatives(day, trail, slot, size, db))
        con.execute("INSERT INTO walkins (day, trail, slot, group_size, sold_by, sold_at) VALUES (?,?,?,?,?,?)",
                    (day, trail, slot, size, by, now.isoformat(timespec="seconds")))
        con.commit()
    return left - size


def booked(day: str, db=None, index=None, columns=None) -> pd.DataFrame:
    with closing(_connect(db)) as con:
        rows = con.execute("SELECT slot, trail, SUM(group_size) FROM bookings WHERE day=? AND status!='cancelled' "
                           "GROUP BY slot, trail", (day,)).fetchall()
    if index is None:
        sup = supply(day, db)
        index, columns = sup.index, sup.columns
    out = pd.DataFrame(0, index=index, columns=columns)
    for slot, trail, n in rows:
        out.loc[slot, trail] = n
    return out


def availability(day: str, db=None) -> pd.DataFrame:
    """Places left per slot (rows) and trail (columns)."""
    return (supply(day, db) - booked(day, db)).clip(lower=0)


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
    sup = supply(day, db)
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
        con.execute("UPDATE bookings SET status='checked_in', checked_in_at=? WHERE code=?",
                    (now.isoformat(timespec="seconds"), code.strip().upper()))
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

