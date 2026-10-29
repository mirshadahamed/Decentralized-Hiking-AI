"""P4/P5: stage advice for a long open-access trail (the Pekoe Trail) instead of tickets.

    GET /stages/{day}     every stage: walkers expected on it at the busiest hour, the busiest place (km from the
                          stage start) and how full it gets, a level (quiet / busy / crowded) and when to start

Nobody is turned away on an open trail, so the control is advice: start earlier or later, or walk a quieter
neighbouring stage that day. The crowd forecast is the planning model's likely case per ~6 km section (RQ1 Pekoe:
2 km sections were too sparse to forecast); "full" = people at once / the section's capacity at once.
"""
import numpy as np

LEVELS = ((1.0, "crowded"), (0.5, "busy"), (0.0, "quiet"))
OPEN_FROM_H, LAST_START_H = 6, 11


def _level(full: float) -> str:
    return next(name for lo, name in LEVELS if full >= lo)


def stage_outlook(cfg, seg, hourly: np.ndarray, day: str) -> dict:
    """seg: segments (seg_id, trail, length_m) in the column order of hourly [24 h, segments] (people at once)."""
    c = cfg["capacity"]
    names = cfg["area"]["trail_names"]
    cap = seg.length_m.values / (c["group_gap_m"] + c["group_size"] * c["space_per_person_m"]) * c["group_size"]
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
        else:
            first, last = int(busy_h.min()), int(busy_h.max())
            early = max(OPEN_FROM_H, first - 2)
            advice = (f"{'Crowded' if level == 'crowded' else 'Busy'} from about {first:02d}:00 to {last + 1:02d}:00, "
                      f"most around km {km[j]:.0f} at {h:02d}:00. Start by {early:02d}:00 to be ahead of it"
                      + (f", or after {last - 1:02d}:00 if the stage is short enough to finish in daylight."
                         if last - 1 <= LAST_START_H else "."))
        stages.append({"stage": t, "name": names.get(t, t), "length_km": round(float(seg.length_m.values[idx].sum()) / 1000, 1),
                       "walkers_at_busiest_hour": round(float(hourly[:, idx].sum(1).max()), 1),
                       "busiest_hour": f"{h:02d}:00", "busiest_km": round(float(km[j]), 1),
                       "fullness": round(worst, 2), "level": level, "advice": advice,
                       "hourly_walkers": [round(float(x), 1) for x in hourly[:, idx].sum(1)]})
    order = [s["stage"] for s in stages]
    for i, s in enumerate(stages):                                         # a quieter neighbour to walk instead
        if s["level"] != "quiet":
            nb = [stages[k] for k in (i - 1, i + 1) if 0 <= k < len(order) and stages[k]["fullness"] < 0.5]
            s["quieter_neighbour"] = nb[0]["stage"] if nb else None
    return {"day": day, "stages": stages,
            "basis": "Planning model's likely case per section of ~6 km; a section is full when the people on it at "
                     "once reach its capacity (groups of 4 with walking gaps). Advice only: nobody is turned away."}
