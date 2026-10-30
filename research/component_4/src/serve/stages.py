"""P4/P5: stage advice for a long open-access trail (the Pekoe Trail) instead of tickets.

    GET /stages/{day}     every stage: walkers expected on it at the busiest hour, the busiest place (km from the
                          stage start) and how full it gets, a level (quiet / busy / crowded) and when to start

Nobody is turned away on an open trail, so the control is advice. On a busy stage each walker gets a different start
time in spread_window (the app picks one per visitor): RQ14b, spreading cut the person-hours over capacity at the
viewpoints by 53-74 %, while "start early" for everyone made it worse. A quieter neighbouring stage is also named; or walk a quieter
neighbouring stage that day. The crowd forecast is the planning model's likely case per ~6 km section (RQ1 Pekoe:
2 km sections were too sparse to forecast); "full" = people at once / the section's capacity at once.
"""
import numpy as np

LEVELS = ((1.0, "crowded"), (0.5, "busy"), (0.0, "quiet"))
OPEN_FROM_H, LAST_START_H = 6, 11


def _level(full: float) -> str:
    return next(name for lo, name in LEVELS if full >= lo)


def stage_outlook(cfg, seg, hourly: np.ndarray, day: str, weather: dict | None = None) -> dict:
    """seg: segments (seg_id, trail, length_m[, poi]) in the column order of hourly [24 h, segments] (people at once).
    weather: {stage: {"rain_mm", "rain_hours", "temp_max_c"}} for the day (per-stage forecast), if known."""
    c = cfg["capacity"]
    names = cfg["area"]["trail_names"]
    cap = seg.length_m.values / (c["group_gap_m"] + c["group_size"] * c["space_per_person_m"]) * c["group_size"]
    hot = cfg["control"].get("hotspot_at_once")                   # R5: a viewpoint holds far fewer than 6 km of path
    if hot and "poi" in seg:
        views = set(cfg["area"].get("poi_roles", {}).get("viewpoint", []))
        cap = np.where(seg.poi.fillna("").isin(views).values, np.minimum(cap, hot), cap)
    full = hourly / np.maximum(cap, 1e-9)[None, :]
    stages = []
    for t in sorted(seg.trail.unique()):
        idx = np.where(seg.trail.values == t)[0]
        idx = idx[np.argsort(seg.seg_id.values[idx])]                      # walking order
        km = np.concatenate([[0.0], np.cumsum(seg.length_m.values[idx])[:-1]]) / 1000
        f = full[:, idx]
        h, j = np.unravel_index(int(np.argmax(f)), f.shape)
        worst = float(f[h, j])
        level = _level(worst)
        busy_h = np.where(f.max(1) >= 0.5)[0]
        if level == "quiet":
            advice = "Quiet all day: start when you like (before 08:00 to finish in daylight with time to spare)."
        else:                                    # R6: spread starts (telling everyone "start early" moves the peak)
            first, last = int(busy_h.min()), int(busy_h.max())
            advice = (f"{'Crowded' if level == 'crowded' else 'Busy'} from about {first:02d}:00 to {last + 1:02d}:00, "
                      f"most around km {km[j]:.0f} at {h:02d}:00. Walkers who spread their starts over the morning keep "
                      f"it under the limit: start at the time suggested for you.")
        stages.append({"stage": t, "name": names.get(t, t), "length_km": round(float(seg.length_m.values[idx].sum()) / 1000, 1),
                       "walkers_at_busiest_hour": round(float(hourly[:, idx].sum(1).max()), 1),
                       "busiest_hour": f"{h:02d}:00", "busiest_km": round(float(km[j]), 1),
                       "fullness": round(worst, 2), "level": level, "advice": advice,
                       "hourly_walkers": [round(float(x), 1) for x in hourly[:, idx].sum(1)],
                       "weather": (weather or {}).get(t),
                       "spread_window": None if level == "quiet" else [f"{OPEN_FROM_H:02d}:00", f"{LAST_START_H:02d}:00"]})
        w = (weather or {}).get(t)
        if w and w["rain_hours"] >= 3:
            stages[-1]["advice"] += f" Rain expected on this stage ({w['rain_mm']} mm): start early and carry rain gear."
    order = [s["stage"] for s in stages]
    for i, s in enumerate(stages):                                         # a quieter neighbour to walk instead
        if s["level"] != "quiet":
            nb = [stages[k] for k in (i - 1, i + 1) if 0 <= k < len(order) and stages[k]["fullness"] < 0.5]
            s["quieter_neighbour"] = nb[0]["stage"] if nb else None
    return {"day": day, "stages": stages,
            "basis": "Planning model's likely case per section of ~6 km; a section is full when the people on it at "
                     "once reach its capacity (groups of 4 with walking gaps). Advice only: nobody is turned away."}
