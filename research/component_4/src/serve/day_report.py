"""Item 12: the end-of-day report for the park office - who came, how the gate control did, what the rangers saw.

    GET /admin/day-report/{day}                 (officer) JSON
    GET /admin/day-report/{day}?format=html     a printable page (print -> PDF from the browser)

Everything comes from what the system already recorded that day: ticket check-ins, walk-ins, start-time codes,
spot counts next to the forecast, and reported trail conditions. No personal data.
"""
from contextlib import closing
from html import escape

from src.control import booking
from src.serve.field_counts import forecast_check


def day_report(cfg, day: str, db=None) -> dict:
    names = cfg["area"]["trail_names"]
    with closing(booking._connect(db)) as con:
        tickets = con.execute("SELECT trail, status, SUM(group_size) FROM bookings WHERE day=? GROUP BY trail, status",
                              (day,)).fetchall()
        walkins = con.execute("SELECT trail, SUM(group_size) FROM walkins WHERE day=? GROUP BY trail", (day,)).fetchall()
        starts = con.execute("SELECT trail, arrived_at IS NOT NULL, SUM(group_size) FROM start_advice WHERE day=? "
                             "GROUP BY trail, arrived_at IS NOT NULL", (day,)).fetchall()
    pub = booking._published(day, db)
    planned = {} if pub is None else pub.groupby("trail").tickets.sum().to_dict()
    entries = booking.entries(day, db)
    trails = sorted(set(cfg["area"]["trail_names"]) | set(entries.trail) | set(planned))
    rows = []
    for t in trails:
        came = int(entries.loc[entries.trail == t, "size"].sum()) if len(entries) else 0
        rows.append({
            "trail": t, "name": names.get(t, t), "entered": came, "planned_tickets": int(planned.get(t, 0)),
            "tickets_checked_in": int(sum(n for tt, s, n in tickets if tt == t and s == "checked_in")),
            "tickets_no_show": int(sum(n for tt, s, n in tickets if tt == t and s == "booked")),
            "walk_ins": int(sum(n for tt, n in walkins if tt == t)),
            "start_time_on_time": int(sum(n for tt, a, n in starts if tt == t and a)),
            "start_time_not_used": int(sum(n for tt, a, n in starts if tt == t and not a)),
        })
    busiest = None
    if len(entries):
        hour = entries.assign(h=entries.gate_min // 60).groupby("h")["size"].sum()
        busiest = {"hour": f"{int(hour.idxmax()):02d}:00", "people": int(hour.max())}
    check = forecast_check(cfg, day, day, db)["summary"]
    cond = booking.conditions(day, db)
    total = sum(r["entered"] for r in rows)
    lines = [f"{total} people entered" + (f"; busiest hour at the gate {busiest['hour']} ({busiest['people']} people)"
                                          if busiest else "") + "."]
    for r in rows:
        if r["entered"] or r["planned_tickets"]:
            lines.append(f"{r['name']}: {r['entered']} entered of {r['planned_tickets']} planned "
                         f"({r['tickets_checked_in']} tickets, {r['walk_ins']} walk-ins, {r['start_time_on_time']} on "
                         f"their start time); {r['tickets_no_show']} ticket no-shows.")
    held = sum(r["start_time_on_time"] + r["start_time_not_used"] for r in rows)
    if held:                                         # R7: the live counterpart of RQ13b's follow rate
        came = sum(r["start_time_on_time"] for r in rows)
        lines.append(f"Start times: {held} people held one, {came} came on time ({round(100 * came / held)} %) and "
                     f"went in first.")
    for t, v in cond.items():
        lines.append(f"{names.get(t, t)}: {v['level'].replace('_', ' ')}" + (f" - {v['note']}" if v["note"] else "")
                     + f" (reported by {v['set_by']} at {v['set_at'][11:16]}).")
    waits = booking.gate_waits(day, db)
    a, b = waits["start_time_first"], waits["others"]
    if a["groups"] and b["groups"]:                  # R7: measured, groups scanned when they joined the queue
        lines.append(f"Gate wait (measured, {waits['groups_timed']} groups timed): start-time holders "
                     f"{a['median_min']} min, others {b['median_min']} min (medians).")
    elif waits["groups_let_in"]:
        lines.append("Gate wait not measured: scan codes at the back of the queue (\"Joined the queue\") to time it.")
    if check.get("counts"):
        lines.append(f"{check['counts']} spot counts; forecast error {check.get('mae', '-')} people, bias "
                     f"{check.get('bias', '-')}; over capacity counted {check.get('counted_over_capacity', 0)}, called "
                     f"{check.get('over_capacity_called', 0)}, false alarms {check.get('false_alarms', 0)}.")
    else:
        lines.append("No spot counts today: count at the viewpoints so the forecast can be checked and corrected.")
    return {"day": day, "park": cfg["area"]["name"], "entered": total, "busiest_gate_hour": busiest, "trails": rows,
            "conditions": cond, "forecast_check": check, "gate_waits": waits, "lines": lines}


def trends(cfg, end: str, days: int = 28, db=None) -> dict:
    """§6.2.10: the day reports of the last `days` days, per day and per week (Monday start): people entered,
    ticket no-shows, start-time holders on time, forecast error raw / corrected, over capacity counted, gate waits."""
    import pandas as pd
    rows = []
    for d in pd.date_range(end=pd.Timestamp(end), periods=days):
        r = day_report(cfg, d.date().isoformat(), db)
        t = r["trails"]
        fc, w = r["forecast_check"], r["gate_waits"]
        rows.append({"day": r["day"], "entered": r["entered"],
                     "tickets": sum(x["tickets_checked_in"] + x["tickets_no_show"] for x in t),
                     "no_shows": sum(x["tickets_no_show"] for x in t),
                     "start_held": sum(x["start_time_on_time"] + x["start_time_not_used"] for x in t),
                     "start_on_time": sum(x["start_time_on_time"] for x in t),
                     "counts": fc.get("counts", 0), "mae": fc.get("mae"), "mae_corrected": fc.get("mae_corrected"),
                     "counted_over": fc.get("counted_over_capacity", 0),
                     "wait_start_time_min": w["start_time_first"]["median_min"], "wait_others_min": w["others"]["median_min"]})
    df = pd.DataFrame(rows)
    df["week"] = (pd.to_datetime(df.day) - pd.to_timedelta(pd.to_datetime(df.day).dt.weekday, unit="D")).dt.date.astype(str)

    def pct(a, b):
        return None if b == 0 else round(100 * a / b)
    weeks = []
    for wk, g in df.groupby("week"):
        mae = g.mae.dropna()
        cor = g.mae_corrected.dropna()
        weeks.append({"week": wk, "days": len(g), "entered": int(g.entered.sum()),
                      "no_show_pct": pct(g.no_shows.sum(), g.tickets.sum()),
                      "on_time_pct": pct(g.start_on_time.sum(), g.start_held.sum()),
                      "counts": int(g.counts.sum()),
                      "mae": round(float(mae.mean()), 2) if len(mae) else None,
                      "mae_corrected": round(float(cor.mean()), 2) if len(cor) else None,
                      "counted_over": int(g.counted_over.sum())})
    lines = []
    for w in weeks:
        bits = [f"{w['entered']:,} entered"]
        if w["no_show_pct"] is not None:
            bits.append(f"no-shows {w['no_show_pct']} %")
        if w["on_time_pct"] is not None:
            bits.append(f"start times kept {w['on_time_pct']} %")
        if w["mae"] is not None:
            bits.append(f"forecast error {w['mae']}" + (f" ({w['mae_corrected']} corrected)" if w["mae_corrected"] else ""))
        bits.append(f"over capacity counted {w['counted_over']}" if w["counts"] else "no spot counts")
        lines.append(f"Week of {w['week']}: " + " · ".join(bits))
    return {"end": end, "days": days, "daily": df.drop(columns="week").to_dict("records"), "weeks": weeks,
            "lines": lines}


def to_html(r: dict) -> str:
    head = ["Trail", "Entered", "Planned", "Tickets", "No-shows", "Walk-ins", "On start time"]
    keys = ["name", "entered", "planned_tickets", "tickets_checked_in", "tickets_no_show", "walk_ins", "start_time_on_time"]
    table = "".join("<tr>" + "".join(f"<td>{escape(str(t[k]))}</td>" for k in keys) + "</tr>" for t in r["trails"])
    return (f"<!doctype html><html><head><meta charset='utf-8'><title>Day report {r['day']}</title>"
            "<style>body{font-family:sans-serif;margin:24px;color:#222}table{border-collapse:collapse}"
            "td,th{border:1px solid #bbb;padding:4px 8px;text-align:right}td:first-child,th:first-child{text-align:left}"
            "</style></head><body>"
            f"<h1>{escape(r['park'])} - day report {r['day']}</h1>"
            "<ul>" + "".join(f"<li>{escape(x)}</li>" for x in r["lines"]) + "</ul>"
            "<table><tr>" + "".join(f"<th>{h}</th>" for h in head) + f"</tr>{table}</table>"
            "<p><small>From the gate check-ins, walk-ins, start-time codes, rangers' spot counts and reported trail "
            "conditions. No personal data.</small></p></body></html>")
