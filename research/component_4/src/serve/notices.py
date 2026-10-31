"""§6.2.9 without Firebase: notices for visitors of one day, which the app polls while it is open.

    GET /notices/{day}     public: [{id, level, kind, trail, text}], most serious first

From what the park already knows: trail conditions reported by rangers / officers (closed, partly closed, muddy),
slots an officer closed, and heavy rain in the weather forecast (for today also the nowcast for the next 2
hours, src/live/nowcast.py). `id` stays the same while a notice does not change, so the app shows each one once.
When the team adds push (a Firebase project), the same list is what gets sent.
"""
import hashlib
from contextlib import closing
from datetime import date, datetime

import pandas as pd

from src.control import booking

HEAVY_MM = 7.6                       # mm per hour: "heavy rain" (WMO); slippery rock, streams rise fast
LEVELS = {"danger": 0, "warning": 1, "info": 2}
CONDITION = {"closed": ("danger", "{trail} is closed{note}."),
             "partly_closed": ("warning", "{trail} is partly closed{note}."),
             "muddy": ("info", "{trail} is muddy{note}: wear shoes with grip.")}


def _notice(level: str, kind: str, text: str, trail: str | None = None) -> dict:
    nid = hashlib.sha1(f"{kind}|{trail}|{text}".encode()).hexdigest()[:12]
    return {"id": nid, "level": level, "kind": kind, "trail": trail, "text": text}


def _heavy(hourly: pd.Series, open_from: int, open_to: int) -> tuple[float, int] | None:
    """(largest mm in an open hour, that hour) when it reaches HEAVY_MM."""
    h = hourly[(hourly.index.hour >= open_from) & (hourly.index.hour < open_to)]
    if not len(h) or float(h.max()) < HEAVY_MM:
        return None
    return float(h.max()), int(h.idxmax().hour)


def notices(cfg, day: date, now: datetime, weather: pd.DataFrame | None = None, weather_source: pd.Series | None = None,
            nowcast=None, db=None) -> list:
    """weather / weather_source: the live hourly weather and where each hour comes from (LiveContext);
    nowcast: 24 hourly mm for today, or None."""
    names = cfg["area"]["trail_names"]
    d = day.isoformat()
    out = []
    for t, v in booking.conditions(d, db).items():
        if v["level"] in CONDITION:
            level, text = CONDITION[v["level"]]
            out.append(_notice(level, "condition", text.format(trail=names.get(t, t),
                                                                note=f" ({v['note']})" if v["note"] else ""), t))
    with closing(booking._connect(db)) as con:
        rows = con.execute("SELECT trail, slot_from, slot_to, reason FROM closures WHERE day=? AND active=1 "
                           "ORDER BY slot_from", (d,)).fetchall()
    for t, a, b, why in rows:
        out.append(_notice("warning", "closure", f"{names.get(t, t)}: no entry {a}-{b} ({why}).", t))

    open_from = int(cfg["capacity"].get("open_from_h", 6))
    open_to = open_from + int(cfg["capacity"]["open_hours"])
    heavy = None
    if nowcast is not None and day == now.date():
        nc = pd.Series(nowcast, index=pd.date_range(pd.Timestamp(day), periods=24, freq="h"))
        nc = nc[(nc.index.hour >= now.hour) & (nc.index.hour < now.hour + 3)]
        if (hit := _heavy(nc, open_from, open_to)) is not None:
            heavy = ("danger", f"Heavy rain expected around {hit[1]:02d}:00 (about {hit[0]:.0f} mm in the hour). "
                               f"Rock gets slippery and streams rise fast: stay off exposed places and do not cross "
                               f"rising water.")
    if heavy is None and weather is not None and "precipitation" in weather:
        lo, hi = pd.Timestamp(day), pd.Timestamp(day) + pd.Timedelta(hours=23)
        w = weather.precipitation[lo:hi]
        if weather_source is not None:
            w = w[weather_source.reindex(w.index) == "forecast"]          # only real forecasts, not typical weather
        if (hit := _heavy(w, open_from, open_to)) is not None:
            heavy = ("warning", f"Heavy rain forecast around {hit[1]:02d}:00 (about {hit[0]:.0f} mm in the hour). "
                                f"Start early, bring rain gear, and turn back if streams rise.")
    if heavy:
        out.append(_notice(heavy[0], "rain", heavy[1]))
    return sorted(out, key=lambda n: LEVELS[n["level"]])
