"""§6.1.2 remedy: start times by SMS for visitors without the app (any phone, no data connection).

    START                      the next start time today on the main ticketed trail, 2 people
    START 2 4 SAT 08:00        trail 2 of the HELP list, 4 people, Saturday, at or after 08:00
    CHECK K7Q2MX               on the morning: is the held start still fine?
    HELP                       the trail numbers and these commands

Words may come in any order: a time (HH:MM), a day (TODAY, TOMORROW, MON..SUN, YYYY-MM-DD), a trail (its
number, its key or a word of its name) and a group size (1-20). POST /sms receives the text from the SMS gateway
(provider-neutral JSON) and returns the reply. The phone number is not stored (docs/privacy.md).
"""
import re
from datetime import date, datetime, timedelta

from src.control import modes, start_times

DAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
MAX_LEN = 306                                                   # two SMS parts


def trails(cfg) -> list:
    return modes.trails_with(cfg, *modes.TICKETED)


def _help(cfg) -> str:
    ts = trails(cfg)
    if not ts:
        return f"{cfg['area']['name']} needs no start time: just come."
    names = ", ".join(f"{i} {cfg['area']['trail_names'][t]}" for i, t in enumerate(ts, 1))
    return f"{cfg['area']['name']} start times. Send START [trail] [people] [day] [time], e.g. START 1 4 SAT 08:00. " \
           f"Trails: {names}. CHECK <code> on the day."


def parse(text: str, cfg, today: date) -> dict:
    """The words of a START message; raises ValueError with a reply-sized reason."""
    ts = trails(cfg)
    main = cfg["area"].get("main_trail")
    out = {"trail": main if main in ts else (ts[0] if ts else None), "size": 2, "day": today, "wanted": None}
    for w in text.upper().split()[1:]:
        if re.fullmatch(r"\d{1,2}[:.]\d{2}", w):
            h, m = (int(x) for x in re.split(r"[:.]", w))
            if not (0 <= h < 24 and 0 <= m < 60):
                raise ValueError(f"{w} is not a time")
            out["wanted"] = f"{h:02d}:{m:02d}"
        elif w in ("TODAY", "TOMORROW") or w[:3] in DAYS:
            out["day"] = today + timedelta(days=1 if w == "TOMORROW" else 0) if w in ("TODAY", "TOMORROW") else \
                today + timedelta(days=(DAYS.index(w[:3]) - today.weekday()) % 7)
        elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", w):
            out["day"] = date.fromisoformat(w)
        elif w.isdigit() and int(w) <= len(ts) and "trail_set" not in out:
            out["trail"], out["trail_set"] = ts[int(w) - 1], True
        elif w.isdigit():
            out["size"] = int(w)
        else:
            hit = [t for t in ts if w == t.upper() or w in cfg["area"]["trail_names"][t].upper().replace("'", "").split()]
            if len(hit) != 1:
                raise ValueError(f"Did not understand '{w}'.")
            out["trail"] = hit[0]
    out.pop("trail_set", None)
    if out["trail"] is None:
        raise ValueError("No trail here needs a start time.")
    if not 1 <= out["size"] <= 20:
        raise ValueError("A group is 1-20 people.")
    if not today <= out["day"] <= today + timedelta(days=14):
        raise ValueError("Choose a day in the next two weeks.")
    return out


def handle(text: str, cfg, now: datetime, expect, db=None) -> str:
    """The reply to one SMS. expect(day) -> (rain share, expected visitors), as the API plans the day."""
    words = text.strip().upper().split()
    cmd = words[0] if words else "HELP"
    try:
        if cmd == "CHECK" and len(words) == 2:
            h = start_times.held(words[1], db)
            if h is None:
                return "Unknown code. Send HELP for the commands."
            r = start_times.recheck(words[1], now, *expect(date.fromisoformat(h["day"])), db=db)
            reply = f"{r['code']} {r['day']} {r['slot']}: {r['note']}"
        elif cmd == "START":
            q = parse(text, cfg, now.date())
            wanted = q["wanted"] or (f"{now.hour:02d}:{now.minute:02d}" if q["day"] == now.date() else "07:00")
            rain, expected = expect(q["day"])
            s = start_times.suggest(q["day"].isoformat(), q["trail"], wanted, q["size"], rain, expected, db)
            name = cfg["area"]["trail_names"][q["trail"]]
            if s["suggested"] is None:
                return f"{name} is full for the next 3 hours from {s['wanted']} on {q['day']:%a %d %b}. " \
                       f"Try another trail or day. Send HELP for the trails."
            h = start_times.hold(q["day"].isoformat(), q["trail"], s["suggested"], q["size"], rain, expected, db)
            reply = f"{cfg['area']['name']}, {q['day']:%a %d %b}: start {h['slot']} on {name}, {q['size']} " \
                    f"{'person' if q['size'] == 1 else 'people'}. Code {h['code']}: show it at the gate and you go in " \
                    f"first. On the day send CHECK {h['code']}."
        else:
            reply = _help(cfg)
    except ValueError as e:
        reply = f"{e} {_help(cfg)}"
    return reply[:MAX_LEN]
