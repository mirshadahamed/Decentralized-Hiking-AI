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

from src.config import DATA, load_config
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
        CREATE TABLE IF NOT EXISTS checkpoint_counts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, day TEXT NOT NULL, route TEXT NOT NULL, time_min INTEGER NOT NULL,
            count INTEGER NOT NULL CHECK (count >= 0), counted_by TEXT NOT NULL, recorded_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS trail_conditions (
            day TEXT NOT NULL, trail TEXT NOT NULL, level TEXT NOT NULL, note TEXT NOT NULL,
            set_by TEXT NOT NULL, set_at TEXT NOT NULL, PRIMARY KEY (day, trail));
        CREATE TABLE IF NOT EXISTS day_forecasts (
            day TEXT PRIMARY KEY, hourly TEXT NOT NULL, basis TEXT NOT NULL, saved_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS quota_decisions (
            day TEXT NOT NULL, trail TEXT NOT NULL, rule TEXT NOT NULL, quota REAL,
            decided_by TEXT NOT NULL, decided_at TEXT NOT NULL, PRIMARY KEY (day, trail));
        CREATE TABLE IF NOT EXISTS start_advice (
            code TEXT PRIMARY KEY, day TEXT NOT NULL, trail TEXT NOT NULL, slot TEXT NOT NULL,
            group_size INTEGER NOT NULL, created TEXT NOT NULL);
    """)
    cols = [r[1] for r in con.execute("PRAGMA table_info(bookings)")]
    if "checked_in_at" not in cols:                           # older databases
        con.execute("ALTER TABLE bookings ADD COLUMN checked_in_at TEXT")
    if "wetness" not in [r[1] for r in con.execute("PRAGMA table_info(published_slots)")]:
        con.execute("ALTER TABLE published_slots ADD COLUMN wetness REAL NOT NULL DEFAULT 0")
    if "correction" not in [r[1] for r in con.execute("PRAGMA table_info(day_forecasts)")]:
        con.execute("ALTER TABLE day_forecasts ADD COLUMN correction TEXT")    # N2: per-section factors from counts
    if "arrived_at" not in [r[1] for r in con.execute("PRAGMA table_info(start_advice)")]:
        con.execute("ALTER TABLE start_advice ADD COLUMN arrived_at TEXT")
    return con


# ---------- trail conditions (reported by officers) ----------
def condition_levels() -> dict:
    return load_config()["capacity"]["condition_levels"]


def conditions(day: str, db=None) -> dict:
    """{trail: {"level", "note", "factor", "set_by", "set_at"}} for trails with a reported condition that day."""
    levels = condition_levels()
    with closing(_connect(db)) as con:
        rows = con.execute("SELECT trail, level, note, set_by, set_at FROM trail_conditions WHERE day=?",
                           (day,)).fetchall()
    return {t: {"level": lv, "note": n, "factor": float(levels.get(lv, 0.0)), "set_by": by, "set_at": at}
            for t, lv, n, by, at in rows if lv != "good"}


def condition_factors(day: str, db=None) -> dict:
    return {t: v["factor"] for t, v in conditions(day, db).items()}


def set_condition(day_from: str, day_to: str, trail: str, level: str, note: str, by: str, db=None) -> list:
    """An officer reports a trail's condition for a range of days ('good' clears it). Every affected day that has
    a published plan is re-published at once (fewer tickets; the freeze rule keeps existing bookings and raises
    alerts). Returns the alerts."""
    if level not in condition_levels():
        raise ValueError(f"Unknown condition '{level}'")
    days = pd.date_range(day_from, day_to).strftime("%Y-%m-%d")
    now = datetime.now().isoformat(timespec="seconds")
    with closing(_connect(db)) as con:
        con.executemany("INSERT OR REPLACE INTO trail_conditions VALUES (?,?,?,?,?,?)",
                        [(d, trail, level, note, by, now) for d in days])
        con.commit()
    alerts = []
    for d in days:
        pub = _published(d, db)
        if pub is not None:
            alerts += publish_day(d, float(pub.rain_share.iloc[0]), pub.basis.iloc[0], db,
                                  wetness=float(pub.wetness.iloc[0]))
    return alerts


def record_checkpoint(day: str, route: str, count: int, by: str, at: datetime, db=None):
    """A ranger at a halfway checkpoint records how many people passed (e.g. in the last 10 minutes)."""
    with closing(_connect(db)) as con:
        con.execute("INSERT INTO checkpoint_counts (day, route, time_min, count, counted_by, recorded_at) "
                    "VALUES (?,?,?,?,?,?)", (day, route, at.hour * 60 + at.minute, int(count), by,
                                             datetime.now().isoformat(timespec="seconds")))
        con.commit()


def checkpoint_passes(day: str, db=None) -> pd.DataFrame:
    with closing(_connect(db)) as con:
        rows = con.execute("SELECT route, time_min, count, counted_by FROM checkpoint_counts WHERE day=? "
                           "ORDER BY time_min, id", (day,)).fetchall()
    return pd.DataFrame(rows, columns=["route", "time_min", "count", "counted_by"])


def entries(day: str, db=None) -> pd.DataFrame:
    """Everyone who actually went through the gate on a day (checked-in bookings + walk-ins + start-time holders):
    trail, gate_min (minutes after midnight), size. Input for the live estimate (nowcast)."""
    with closing(_connect(db)) as con:
        rows = con.execute("SELECT trail, checked_in_at, group_size FROM bookings WHERE day=? AND checked_in_at "
                           "IS NOT NULL UNION ALL SELECT trail, sold_at, group_size FROM walkins WHERE day=? "
                           "UNION ALL SELECT trail, arrived_at, group_size FROM start_advice WHERE day=? AND "
                           "arrived_at IS NOT NULL", (day, day, day)).fetchall()
    out = [{"trail": t, "gate_min": datetime.fromisoformat(at).hour * 60 + datetime.fromisoformat(at).minute,
            "size": n} for t, at, n in rows]
    return pd.DataFrame(out, columns=["trail", "gate_min", "size"])


@lru_cache(maxsize=1)
def _climatology_rain_share() -> pd.Series:
    """Typical share of rainy open hours per day of year (2022-23 = training years, +-15 days)."""
    from src.data.weather import load_weather
    cfg = load_config()
    w = load_weather(cfg)
    lo = cfg["capacity"].get("open_from_h", 6)
    open_h = ((w.index.hour - lo) % 24) < cfg["capacity"]["open_hours"]
    daily = (w.precipitation[open_h] >= cfg["capacity"]["rain_mm"]).groupby(w.index[open_h].normalize()).mean()
    train = daily[daily.index <= pd.Timestamp(cfg["dates"]["train_end"])]
    doy = train.index.dayofyear.values
    out = {}
    for d in range(1, 367):
        dist = np.minimum(np.abs(doy - d), 365 - np.abs(doy - d))
        out[d] = float(train.values[dist <= 15].mean())
    return pd.Series(out)


@lru_cache(maxsize=512)
def _planned(day: str, rain_share: float, closed: tuple = (), wetness: float = 0.0,
             cond: tuple = (), quota: tuple = ()) -> pd.DataFrame:
    """All tickets per slot and trail (bookable + walk-in) from the entry-control plan.
    cond: ((trail, share removed), ...) from reported trail conditions; a closed trail gets no tickets.
    quota: ((trail, daily quota), ...) chosen for the day (resolve_quota); default the classic Cifuentes quota."""
    ec = build_control()
    cond = dict(cond)
    closed = set(closed) | {(t, f"{s // 60:02d}:{s % 60:02d}") for t, f in cond.items() if f >= 1.0 for s in ec.slots}
    return ec.plan(rain_share, dict(quota) or ec.daily_quota(rain_share, wetness, cond), closed=closed)


# ---------- daily quota: forecast-driven (RQ9), classic, static or set by an officer ----------
QUOTA_RULES = {"forecast": "Cifuentes with the crowd forecast (recommended)",
               "classic": "Cifuentes with the day's weather only",
               "static": "one number all year (typical weather)",
               "manual": "set by an officer"}


def save_forecast(day: str, hourly: np.ndarray, basis: str, db=None, correction=None):
    """The crowd forecast [24 h, segments] the day's quota is computed from (written by the live refresh).
    correction: per-segment factors learned from the rangers' counts (N2, src/live/recalibrate.py); the raw
    forecast is kept, so the counts are always checked against what the model itself said."""
    import json
    with closing(_connect(db)) as con:
        con.execute("INSERT OR REPLACE INTO day_forecasts (day, hourly, basis, saved_at, correction) VALUES (?,?,?,?,?)",
                    (day, json.dumps(np.round(np.asarray(hourly, float), 2).tolist()), basis,
                     datetime.now().isoformat(timespec="seconds"),
                     None if correction is None else json.dumps(np.round(np.asarray(correction, float), 3).tolist())))
        con.commit()


def day_forecast(day: str, db=None, raw: bool = False) -> tuple[np.ndarray | None, str | None]:
    """The saved forecast, corrected by the count-based factors unless raw=True."""
    import json
    with closing(_connect(db)) as con:
        r = con.execute("SELECT hourly, basis, correction FROM day_forecasts WHERE day=?", (day,)).fetchone()
    if r is None:
        return None, None
    hourly = np.array(json.loads(r[0]))
    if r[2] is None or raw:
        return hourly, r[1]
    return hourly * np.array(json.loads(r[2]))[None, :], r[1] + ", corrected by the rangers' counts"


def quota_decisions(day: str, db=None) -> dict:
    with closing(_connect(db)) as con:
        rows = con.execute("SELECT trail, rule, quota, decided_by, decided_at FROM quota_decisions WHERE day=?",
                           (day,)).fetchall()
    return {t: {"rule": r, "quota": q, "by": by, "at": at} for t, r, q, by, at in rows}


def static_rain_share() -> float:
    """Typical share of rainy open hours over the training years: what a once-a-year quota is set for."""
    return float(_climatology_rain_share().mean())


def resolve_quota(day: str, rain_share: float, wetness: float = 0.0, cond: dict | None = None, db=None) -> dict:
    """Daily quota of every trail under each rule and the one applied:
    {trail: {"forecast", "classic", "static", "manual", "rule", "applied", "decided_by"}}.
    The rule is the officer's decision for that trail and day, otherwise control.default_quota_rule."""
    ec = build_control()
    cond = cond or {}
    fc, _ = day_forecast(day, db)
    classic = ec.daily_quota(rain_share, wetness, cond)
    forecast = ec.daily_quota(rain_share, wetness, cond, forecast=fc) if fc is not None else classic
    static = ec.daily_quota(static_rain_share())
    default = ec.c.get("default_quota_rule", "forecast")
    dec = quota_decisions(day, db)
    out = {}
    for t in ec.trails:
        d = dec.get(t, {})
        rule = d.get("rule", default)
        opts = {"forecast": forecast[t], "classic": classic[t], "static": static[t],
                "manual": d.get("quota") if rule == "manual" else None}
        applied = opts[rule] if opts.get(rule) is not None else forecast[t]
        if cond.get(t, 0.0) >= 1.0:                       # closed trail: nothing to sell, whatever the rule
            applied = 0.0
        out[t] = {k: (None if v is None else round(float(v))) for k, v in opts.items()} | {
            "rule": rule, "applied": round(float(applied)), "decided_by": d.get("by"), "decided_at": d.get("at")}
    return out


def set_quota(day: str, trail: str, rule: str, quota: float | None, by: str, db=None) -> list:
    """An officer chooses the quota rule (or a number) for a trail and day; the day is re-published at once
    (freeze rule: existing bookings are kept, alerts returned)."""
    if rule not in QUOTA_RULES:
        raise ValueError(f"Unknown rule '{rule}'")
    if rule == "manual" and (quota is None or quota < 0):
        raise ValueError("A manual quota needs a number of people (0 or more)")
    with closing(_connect(db)) as con:
        con.execute("INSERT OR REPLACE INTO quota_decisions VALUES (?,?,?,?,?,?)",
                    (day, trail, rule, quota if rule == "manual" else None, by,
                     datetime.now().isoformat(timespec="seconds")))
        con.commit()
    pub = _published(day, db)
    if pub is None:
        return []
    return publish_day(day, float(pub.rain_share.iloc[0]), pub.basis.iloc[0], db, wetness=float(pub.wetness.iloc[0]))


def typical_rain_share(day: str) -> float:
    return float(_climatology_rain_share()[pd.Timestamp(day).dayofyear])


def _published(day: str, db=None) -> pd.DataFrame | None:
    with closing(_connect(db)) as con:
        rows = con.execute("SELECT slot, trail, tickets, bookable, walk_in, rain_share, basis, published_at, wetness "
                           "FROM published_slots WHERE day=?", (day,)).fetchall()
    if not rows:
        return None
    return pd.DataFrame(rows, columns=["slot", "trail", "tickets", "bookable", "walk_in", "rain_share", "basis",
                                       "published_at", "wetness"])


def supply(day: str, db=None) -> pd.DataFrame:
    """Bookable places per slot (rows) and trail (columns): the published plan if there is one,
    otherwise a provisional plan from typical weather (after keeping the walk-in share)."""
    pub = _published(day, db)
    if pub is not None:
        return pub.pivot(index="slot", columns="trail", values="bookable")[build_control().trails].astype(int)
    plan = _planned(day, typical_rain_share(day), cond=tuple(sorted(condition_factors(day, db).items())))
    return np.floor(plan * (1 - build_control().c["walk_in_share"])).astype(int)


def closed_slots(day: str, db=None) -> set:
    """(trail, slot) pairs closed by an officer for this day."""
    ec = build_control()
    labels = [f"{s // 60:02d}:{s % 60:02d}" for s in ec.slots]
    with closing(_connect(db)) as con:
        rows = con.execute("SELECT trail, slot_from, slot_to FROM closures WHERE day=? AND active=1", (day,)).fetchall()
    return {(t, s) for t, a, b in rows for s in labels if a <= s <= b}


def publish_day(day: str, rain_share: float, basis: str, db=None, wetness: float = 0.0) -> list:
    """Publish the slot plan for a day with the FREEZE RULE: a slot never offers fewer bookable places than are
    already booked. Walk-in places are cut first; if booked places exceed the safe plan (worse weather, wet ground,
    a reported trail condition or a closure), an alert is returned for the officer (bookings are never cancelled
    silently)."""
    ec = build_control()
    closed = tuple(sorted(closed_slots(day, db)))
    cond = condition_factors(day, db)
    quota = {t: v["applied"] for t, v in resolve_quota(day, rain_share, wetness, cond, db).items()}
    plan = _planned(day, round(rain_share, 3), closed, round(wetness, 3), tuple(sorted(cond.items())),
                    tuple(sorted(quota.items())))
    safe_bookable = np.floor(plan * (1 - ec.c["walk_in_share"])).astype(int)
    bk = booked(day, db, index=plan.index, columns=plan.columns)
    bookable = np.maximum(safe_bookable, bk)
    walk_in = (plan - bookable).clip(lower=0)
    alerts = []
    for slot in plan.index:
        for trail in plan.columns:
            if bk.loc[slot, trail] > safe_bookable.loc[slot, trail]:
                reason = ("closed" if (trail, slot) in closed or cond.get(trail, 0) >= 1 else
                          "trail condition" if trail in cond else "lower capacity (weather)")
                alerts.append({"day": day, "trail": trail, "slot": slot, "booked": int(bk.loc[slot, trail]),
                               "safe_places": int(safe_bookable.loc[slot, trail]), "reason": reason})
    now = datetime.now().isoformat(timespec="seconds")
    with closing(_connect(db)) as con:
        con.execute("DELETE FROM published_slots WHERE day=?", (day,))
        con.executemany("INSERT INTO published_slots (day, trail, slot, tickets, bookable, walk_in, rain_share, "
                        "basis, published_at, wetness) VALUES (?,?,?,?,?,?,?,?,?,?)",
                        [(day, t, s, int(plan.loc[s, t]), int(bookable.loc[s, t]), int(walk_in.loc[s, t]),
                          float(rain_share), basis, now, float(wetness)) for s in plan.index for t in plan.columns])
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
    wet = float(pub.wetness.iloc[0]) if pub is not None else 0.0
    return publish_day(day, rain, basis, db, wetness=wet)


def walk_in_left(day: str, db=None) -> pd.DataFrame:
    pub = _published(day, db)
    if pub is None:
        ec = build_control()
        plan = _planned(day, typical_rain_share(day), cond=tuple(sorted(condition_factors(day, db).items())))
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
            return _check_start_time(con, code.strip().upper(), now, win)
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


def _check_start_time(con, code: str, now: datetime, win: int) -> dict:
    """Gate check for a start-time code (N3, no ticket): on time = within the slot window, and then the group goes
    in first (RQ13b). Early: come back. Late: no priority, join the queue like everyone else."""
    row = con.execute("SELECT day, trail, slot, group_size, arrived_at FROM start_advice WHERE code=?",
                      (code,)).fetchone()
    if row is None:
        return {"ok": False, "reason": "Unknown code"}
    day, trail, slot, size, arrived = row
    info = {"day": day, "trail": trail, "slot": slot, "group_size": size, "kind": "start_time", "priority": False}
    if arrived:
        return {"ok": False, "reason": f"Already used at {arrived[11:16]}", **info}
    start = datetime.fromisoformat(f"{day}T{slot}")
    if now < start - timedelta(minutes=win):
        return {"ok": False, "reason": f"Too early: their start time is {slot} on {day}; let in first from "
                                       f"{(start - timedelta(minutes=win)):%H:%M}", **info}
    if now > start + timedelta(minutes=win):
        return {"ok": False, "reason": "Late for their start time: no priority, join the queue", **info}
    con.execute("UPDATE start_advice SET arrived_at=? WHERE code=?", (now.isoformat(timespec="seconds"), code))
    con.commit()
    return {"ok": True, "reason": "On time: let in first", **info | {"priority": True}}


def bookings_for_code(code: str, db=None) -> dict | None:
    with closing(_connect(db)) as con:
        row = con.execute("SELECT day, trail, slot, group_size, status FROM bookings WHERE code=?",
                          (code.strip().upper(),)).fetchone()
    return dict(zip(["day", "trail", "slot", "group_size", "status"], row)) if row else None


def bookings_for(day: str, db=None) -> pd.DataFrame:
    with closing(_connect(db)) as con:
        return pd.read_sql_query("SELECT code, trail, slot, group_size, status, created FROM bookings WHERE day=? "
                                 "ORDER BY slot", con, params=(day,))

