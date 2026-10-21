"""Daily crowd records for officers: past, today and future visitors per trail, to keep and export.

    GET /admin/records?start=2026-10-01&end=2026-10-28&trail=main            (officer; &format=csv to download)

One row per day and trail:
  period      past | today | future
  visitors    past / today: the day's visitor count (DWC total when connected, otherwise the estimate simulated
              with that day's real weather - `source` says which); future: the planning model's expected visitors
  low, high   future only: the likely range (P10-P90 of the park total, split by the trail's share)
  booked      tickets booked for the day (not cancelled)            - this system's own records
  checked_in  booked visitors who went through the gate
  walk_ins    places sold at the gate
  gate_total  checked_in + walk_ins: people counted at the gate (the real count once gates use the app)
  halfway     people counted at the trail's halfway checkpoint (pilgrim sites)
  safe_limit  places the published plan allows that day (Cifuentes, after weather and conditions); null if no plan
"""
import csv
import io
from contextlib import closing
from datetime import date, timedelta

import numpy as np
import pandas as pd

from src.control import booking

SOURCES = {"simulated": "estimate (simulated with real weather)",
           "simulated (research years)": "estimate (simulated, research years)",
           "dwc": "DWC daily total", "future": "forecast (planning model)"}
FIELDS = ["date", "trail", "trail_name", "period", "visitors", "low", "high", "source", "booked", "checked_in",
          "walk_ins", "gate_total", "halfway", "safe_limit"]


def _db_counts(start: str, end: str, db=None) -> dict:
    """{(day, trail): {booked, checked_in, walk_ins, halfway, safe_limit}} from the booking database."""
    out: dict = {}

    def add(key, field, v):
        out.setdefault(key, {})[field] = int(v or 0)

    with closing(booking._connect(db)) as con:
        for d, t, b, c in con.execute(
                "SELECT day, trail, SUM(CASE WHEN status!='cancelled' THEN group_size ELSE 0 END), "
                "SUM(CASE WHEN status='checked_in' THEN group_size ELSE 0 END) FROM bookings "
                "WHERE day BETWEEN ? AND ? GROUP BY day, trail", (start, end)):
            add((d, t), "booked", b)
            add((d, t), "checked_in", c)
        for d, t, n in con.execute("SELECT day, trail, SUM(group_size) FROM walkins WHERE day BETWEEN ? AND ? "
                                   "GROUP BY day, trail", (start, end)):
            add((d, t), "walk_ins", n)
        for d, t, n in con.execute("SELECT day, route, SUM(count) FROM checkpoint_counts WHERE day BETWEEN ? AND ? "
                                   "GROUP BY day, route", (start, end)):
            add((d, t), "halfway", n)
        for d, t, n in con.execute("SELECT day, trail, SUM(tickets) FROM published_slots WHERE day BETWEEN ? AND ? "
                                   "GROUP BY day, trail", (start, end)):
            add((d, t), "safe_limit", n)
    return out


def daily_records(ctx, start: date, end: date, trail: str | None = None, outlook: dict | None = None,
                  db=None) -> dict:
    """ctx: LiveContext (past and today from the live dataset); outlook: the published 90-day outlook."""
    cfg, data = ctx.cfg, ctx.data
    names = cfg["area"]["trail_names"]
    trails = [str(t) for t in data.trails if trail in (None, "", "all", str(t))]
    first = data.times[0].date()
    start, end = max(start, first), min(end, ctx.today + timedelta(days=cfg["live"]["horizon_days"]))
    future = {d["date"]: d for d in (outlook or {}).get("days", [])}
    counts = _db_counts(start.isoformat(), end.isoformat(), db)
    ti = {t: [str(x) for x in data.trails].index(t) for t in trails}
    rows = []
    d = start
    while d <= end:
        iso = d.isoformat()
        period = "past" if d < ctx.today else "today" if d == ctx.today else "future"
        k = (d - first).days
        for t in trails:
            row = {"date": iso, "trail": t, "trail_name": names.get(t, t), "period": period,
                   "visitors": None, "low": None, "high": None, "source": None}
            if period == "future":
                f = future.get(iso)
                if f:
                    p50 = float(f["visitors_by_trail_p50"].get(t, 0))
                    share = p50 / max(float(f["visitors"]["p50"]), 1e-9)
                    row.update(visitors=round(p50), low=round(f["visitors"]["p10"] * share),
                               high=round(f["visitors"]["p90"] * share), source=SOURCES["future"])
            elif 0 <= k < len(ctx.day_source):
                row.update(visitors=int(round(float(data.daily_visitors_by_trail[k, ti[t]]))),
                           source=SOURCES.get(str(ctx.day_source[k]), str(ctx.day_source[k])))
            c = counts.get((iso, t), {})
            row.update(booked=c.get("booked", 0), checked_in=c.get("checked_in", 0), walk_ins=c.get("walk_ins", 0),
                       halfway=c.get("halfway", 0), safe_limit=c.get("safe_limit"))
            row["gate_total"] = row["checked_in"] + row["walk_ins"]
            rows.append(row)
        d += timedelta(days=1)
    return {"site": cfg["area"]["name"], "today": ctx.today.isoformat(), "start": start.isoformat(),
            "end": end.isoformat(), "trails": {t: names.get(t, t) for t in trails}, "rows": rows,
            "summary": summary(rows),
            "note": "Past counts are estimates simulated with the real weather until DWC totals or gate counts are "
                    "connected (see 'source'). gate_total is what this system counted at the gate."}


def summary(rows: list) -> dict:
    df = pd.DataFrame(rows)
    if df.empty:
        return {}
    per_day = df.groupby(["date", "period"], as_index=False)[["visitors", "safe_limit"]].sum(min_count=1)
    out = {}
    for p in ("past", "today", "future"):
        g = per_day[per_day.period == p].dropna(subset=["visitors"])
        if len(g):
            top = g.loc[g.visitors.idxmax()]
            out[p] = {"days": int(len(g)), "visitors": int(g.visitors.sum()), "per_day": round(float(g.visitors.mean())),
                      "busiest_day": top.date, "busiest_visitors": int(top.visitors)}
    over = per_day.dropna(subset=["visitors", "safe_limit"])
    out["days_over_safe_limit"] = int((over.visitors > over.safe_limit).sum())
    out["gate_total"] = int(np.nansum(df.gate_total))
    return out


def to_csv(rows: list) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=FIELDS, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({k: ("" if r.get(k) is None else r[k]) for k in FIELDS})
    return buf.getvalue()
