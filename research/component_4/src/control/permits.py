"""K4 / K5: guided-trek permits and the overdue check (control mode guided_permit; Knuckles).

A guided trek can take as many groups a day as both the trail and the guides allow:
    people on trail t       <= daily cap[t]          (the trail's Cifuentes daily quota, from the forecast day)
    groups from entry e     <= guides on duty at e   (one guide leads one group a day on a long trek)
    groups on trail t       <= expected requests[t]  (do not give a trail more guides than it will use)
plan_permits solves this as a small LP (HiGHS) that serves the most people: the suggested guide roster per trek.
Permits are given first come first served while the trek's cap and a guide at its entry are free (RQ14: better than
admitting by the evening-before LP allocation); a full trek offers another trek from the same entry, or another day.

Out and back: the ranger checks a group out at the trailhead (expected return = now + the trek's walking time for
that group size, slower in rain) and back in. A group not back by expected return + margin is OVERDUE and shows on
the ranger's and officer's screens. The margin grows with the trek's length (walking times vary) and rain shortens
it (river crossings, mist).

    GET  /permits/{day}                 places per trek (allocation, issued, left), guides per entry
    POST /permits                       {day, trail, group_size} -> code (or 409 with alternatives)
    POST /permits/{code}/out            ranger: the group starts (at)
    POST /permits/{code}/back           ranger: the group is back (at)
    GET  /overdue/{day}                 ranger / officer: groups out past their expected return
No personal data: a random code, day, trek, group size and times.
"""
import secrets
from contextlib import closing
from datetime import datetime, timedelta

import numpy as np
from scipy.optimize import linprog

from src.control import booking


class PermitFull(Exception):
    def __init__(self, msg, alternatives):
        super().__init__(msg)
        self.alternatives = alternatives


def _con(db=None):
    con = booking._connect(db)
    con.execute("CREATE TABLE IF NOT EXISTS permits (code TEXT PRIMARY KEY, day TEXT NOT NULL, trail TEXT NOT NULL, "
                "group_size INTEGER NOT NULL, created TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'issued', "
                "out_at TEXT, expected_back TEXT, back_at TEXT)")
    return con


def settings(cfg) -> dict:
    return cfg["control"]["permits"]


def plan_permits(cap_people: dict, requests_groups: dict, entry_of: dict, guides: dict, mean_group: float) -> dict:
    """Groups per trek for a day: max people served s.t. trail caps, guides per entry, expected requests.
    Returns {trail: groups (whole numbers, rounded down)}."""
    trails = list(cap_people)
    n = len(trails)
    req = np.array([requests_groups.get(t, 0.0) for t in trails])
    # variables: x (groups per trek), y (the smallest share of a trek's requests served). Maximise people; among
    # equally good plans, the one that serves every trek's requests most evenly (a tiny weight on y).
    c = np.concatenate([-np.full(n, mean_group), [-0.01]])
    A, b = [], []
    for e, g in guides.items():
        A.append([1.0 if entry_of[t] == e else 0.0 for t in trails] + [0.0])
        b.append(float(g))
    for i in np.where(req > 0)[0]:                                      # y <= x_i / requests_i
        row = [0.0] * (n + 1)
        row[i], row[n] = -1.0, req[i]
        A.append(row)
        b.append(0.0)
    ub = np.array([max(0.0, min(cap_people[t] / mean_group, req[i])) for i, t in enumerate(trails)])
    r = linprog(c, A_ub=np.array(A), b_ub=np.array(b), bounds=[(0.0, u) for u in ub] + [(0.0, 1.0)], method="highs")
    x = r.x[:n] if r.success else np.zeros(n)
    out = np.floor(x + 1e-6)
    left = {e: g - sum(out[i] for i, t in enumerate(trails) if entry_of[t] == e) for e, g in guides.items()}
    for i in np.argsort(-(x - out)):                                    # whole groups: hand back rounded-off guides
        e = entry_of[trails[i]]
        if left.get(e, 0) >= 1 and out[i] + 1 <= ub[i] + 1e-6:
            out[i] += 1
            left[e] -= 1
    return {t: int(out[i]) for i, t in enumerate(trails)}


def walk_minutes(cfg, trail: str, group_size: int, rain_share: float = 0.0) -> float:
    """Expected trek time: the configured walking time, slower for big groups and in rain (assumed factors)."""
    s = settings(cfg)
    base = s["treks"][trail]["walk_h"] * 60
    return base * (1 + s.get("big_group_slowdown", 0.02) * max(0, group_size - 4)) * (1 + s.get("rain_slowdown", 0.25) * rain_share)


def day_plan(cfg, day: str, cap_people: dict, requests_groups: dict, db=None) -> dict:
    """Places per trek for a day. Permits are given first come first served while the trek's daily cap (people)
    and a guide at its entry are free (RQ14: this beat a plan made the evening before from expected requests, which
    left guides idle when the day differed). The LP gives the guide roster suggestion per trek."""
    s = settings(cfg)
    entry_of = {t: v["entry"] for t, v in s["treks"].items()}
    roster = plan_permits({t: cap_people.get(t, 0.0) for t in s["treks"]}, requests_groups, entry_of,
                          s["guides_on_duty"], s.get("mean_group", 6))
    with closing(_con(db)) as con:
        rows = con.execute("SELECT trail, COUNT(*), SUM(group_size) FROM permits WHERE day=? AND status!='cancelled' "
                           "GROUP BY trail", (day,)).fetchall()
    issued = {t: (n, int(p or 0)) for t, n, p in rows}
    used = {}
    for t, (n, _) in issued.items():
        if t in entry_of:
            used[entry_of[t]] = used.get(entry_of[t], 0) + n
    guides_left = {e: max(0, g - used.get(e, 0)) for e, g in s["guides_on_duty"].items()}
    names = cfg["area"]["trail_names"]
    treks = []
    for t in s["treks"]:
        n, people = issued.get(t, (0, 0))
        cap = int(cap_people.get(t, 0.0))
        left_people = max(0, cap - people)
        treks.append({"trail": t, "name": names.get(t, t), "entry": entry_of[t], "cap_people": cap,
                      "people_issued": people, "people_left": left_people, "groups_issued": n,
                      "groups_left": guides_left[entry_of[t]] if left_people > 0 else 0,
                      "groups_allowed": n + (guides_left[entry_of[t]] if left_people > 0 else 0),
                      "guides_suggested": roster[t], "walk_h": s["treks"][t]["walk_h"], "max_group": s["max_group"]})
    return {"day": day, "treks": treks,
            "guides": [{"entry": e, "on_duty": g, "assigned": used.get(e, 0), "left": guides_left[e]}
                       for e, g in s["guides_on_duty"].items()]}


def request(cfg, day: str, trail: str, size: int, plan: dict, db=None, other_days: list | None = None) -> dict:
    s = settings(cfg)
    if trail not in s["treks"]:
        raise ValueError(f"'{trail}' is not a guided trek")
    if not 1 <= size <= s["max_group"]:
        raise ValueError(f"A guided group is 1-{s['max_group']} people")
    row = next(x for x in plan["treks"] if x["trail"] == trail)
    if row["groups_left"] <= 0 or row["people_left"] < size:
        entry = s["treks"][trail]["entry"]
        why = "no guide" if row["groups_left"] <= 0 else f"only {row['people_left']} places"
        alts = [{"trail": x["trail"], "name": x["name"], "day": day, "slot": "", "left": x["people_left"], "kind": "trail"}
                for x in plan["treks"]
                if x["trail"] != trail and x["entry"] == entry and x["groups_left"] > 0 and x["people_left"] >= size]
        alts += [{"trail": trail, "name": row["name"], "day": d, "slot": "", "left": 0, "kind": "day"}
                 for d in (other_days or [])]
        raise PermitFull(f"{row['name']} has {why} left on {day}", alts[:4])
    code = "".join(secrets.choice(booking.CODE_ALPHABET) for _ in range(7))
    with closing(_con(db)) as con:
        con.execute("INSERT INTO permits (code, day, trail, group_size, created) VALUES (?,?,?,?,?)",
                    (code, day, trail, size, datetime.now().isoformat(timespec="seconds")))
        con.commit()
    return {"code": code, "day": day, "trail": trail, "name": row["name"], "group_size": size,
            "entry": s["treks"][trail]["entry"], "walk_h": row["walk_h"]}


def _get(con, code):
    r = con.execute("SELECT code, day, trail, group_size, status, out_at, expected_back, back_at FROM permits "
                    "WHERE code=?", (code.strip().upper(),)).fetchone()
    if r is None:
        raise KeyError("Unknown permit")
    return dict(zip(["code", "day", "trail", "group_size", "status", "out_at", "expected_back", "back_at"], r))


def check_out(cfg, code: str, now: datetime, rain_share: float = 0.0, db=None) -> dict:
    with closing(_con(db)) as con:
        p = _get(con, code)
        if p["day"] != now.date().isoformat():
            raise ValueError(f"This permit is for {p['day']}")
        if p["status"] != "issued":
            raise ValueError(f"Permit already {p['status']}")
        back = now + timedelta(minutes=walk_minutes(cfg, p["trail"], p["group_size"], rain_share))
        con.execute("UPDATE permits SET status='out', out_at=?, expected_back=? WHERE code=?",
                    (now.isoformat(timespec="seconds"), back.isoformat(timespec="seconds"), p["code"]))
        con.commit()
    return p | {"status": "out", "out_at": now.isoformat(timespec="seconds"),
                "expected_back": back.isoformat(timespec="seconds")}


def check_back(code: str, now: datetime, db=None) -> dict:
    with closing(_con(db)) as con:
        p = _get(con, code)
        if p["status"] != "out":
            raise ValueError(f"Permit is {p['status']}, not out")
        con.execute("UPDATE permits SET status='back', back_at=? WHERE code=?", (now.isoformat(timespec="seconds"), p["code"]))
        con.commit()
    return p | {"status": "back", "back_at": now.isoformat(timespec="seconds")}


def margin_minutes(cfg, expected_min: float, rain_share: float = 0.0) -> float:
    """How late a group may be before the alarm: z standard deviations of the trek time (walking times vary by
    about overdue_cv), at least overdue_margin_min, and up to rain_margin_cut_min sooner on a rainy day (rivers
    rise, mist): z = 2.3 gives ~1 % false alarms for groups that are fine."""
    s = settings(cfg)
    m = max(s["overdue_margin_min"], s.get("overdue_z", 2.3) * s.get("overdue_cv", 0.15) * expected_min)
    return max(15.0, m - s.get("rain_margin_cut_min", 30) * rain_share)


def overdue(cfg, day: str, now: datetime, rain_share: float = 0.0, db=None) -> dict:
    """Groups still out past expected return + margin (shorter in rain), most overdue first."""
    names = cfg["area"]["trail_names"]
    with closing(_con(db)) as con:
        rows = con.execute("SELECT code, trail, group_size, out_at, expected_back FROM permits WHERE day=? AND "
                           "status='out'", (day,)).fetchall()
    out, late = [], []
    for code, t, n, o, e in rows:
        late_min = (now - datetime.fromisoformat(e)).total_seconds() / 60
        trek_min = (datetime.fromisoformat(e) - datetime.fromisoformat(o)).total_seconds() / 60
        margin = margin_minutes(cfg, trek_min, rain_share)
        item = {"code": code, "trail": t, "name": names.get(t, t), "group_size": n, "out_at": o[11:16],
                "expected_back": e[11:16], "late_min": round(late_min), "alarm_after_min": round(margin)}
        (late if late_min > margin else out).append(item)
    late.sort(key=lambda x: -x["late_min"])
    return {"day": day, "time": now.strftime("%H:%M"), "overdue": late, "still_out": out,
            "note": "Overdue = not back by the expected return time plus the margin (shorter in rain). Call the "
                    "guide first; send a search party if there is no answer."}
