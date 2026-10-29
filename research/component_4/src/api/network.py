"""N4: network-level advice - when the chosen park is busy that day, which other parks have room, and which nearby
days are quieter at the chosen park.

    GET /network/{day}?park=horton_plains        (gateway; reads each park's /capacity/{day})

Load = expected visitors / safe limit (the day's Cifuentes carrying capacity, all trails). A park counts as busy at
LOAD_BUSY and full at 1.0. Other parks are suggested only when quieter; the same kind of place first (a national
park for a national park), then the quietest.
"""
LOAD_BUSY = 0.8


def level(load: float | None) -> str:
    if load is None:
        return "unknown"
    return "full" if load >= 1.0 else "busy" if load >= LOAD_BUSY else "room"


def park_row(park: str, info: dict, cap: dict | None) -> dict:
    exp = cap.get("total_expected") if cap else None
    lim = cap.get("total_safe_limit") if cap else None
    load = None if not exp or not lim else round(float(exp) / float(lim), 2)
    return {"park": park, "name": info.get("name", park), "kind": info.get("kind"), "expected": exp,
            "safe_limit": lim, "load": load, "level": level(load)}


def advice(day: str, rows: list, park: str | None, days: list | None = None) -> dict:
    """rows: park_row for every park on `day`; days: [(iso day, park_row)] for the chosen park around `day`."""
    out = {"day": day, "parks": sorted(rows, key=lambda r: (r["load"] is None, r["load"] or 0))}
    me = next((r for r in rows if r["park"] == park), None)
    if me is None:
        return out
    others = [r for r in rows if r["park"] != park and r["load"] is not None
              and (me["load"] is None or r["load"] < me["load"]) and r["level"] == "room"]
    others.sort(key=lambda r: (r["kind"] != me["kind"], r["load"]))
    quieter_days = sorted(({"day": d, "load": r["load"], "level": r["level"]} for d, r in (days or [])
                           if r["load"] is not None and (me["load"] is None or r["load"] < me["load"])),
                          key=lambda x: x["load"])
    if me["level"] in ("busy", "full"):
        note = (f"{me['name']} is expected to be {'over' if me['level'] == 'full' else 'close to'} its safe limit "
                f"on {day}.")
        if quieter_days:
            note += f" Quieter: {quieter_days[0]['day']}."
        if others:
            note += f" With room that day: {', '.join(o['name'] for o in others[:2])}."
    else:
        note = f"{me['name']} has room on {day}."
    out["for_park"] = me | {"other_parks": others[:3], "other_days": quieter_days[:3], "note": note}
    return out
