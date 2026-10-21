"""A3: advice for the gate during the day - hold entries to a trail, or send the next groups elsewhere - when a
section is expected over capacity in the next two hours. The segment-level carrying capacity, in real time.

Where people will be comes from the gate only (no trail sensors):
  already inside  every group scanned / sold at the gate so far, walked forward with the entry-control response
                  table K[trail, slot, segment, half hour] (src/control/slots.py)
  still to come   the tickets of the coming slots of the published plan (worst case: they all come)
For each trail the smallest hold (0, 30, 60, 90 min) of its coming entrants that keeps every section within
capacity over the horizon is advised; trails with room are offered as alternatives.
"""
import numpy as np
import pandas as pd

from src.control.slots import EntryControl

HOLDS_MIN = (0, 30, 60, 90)


def _label(ec: EntryControl, i: int) -> str:
    s = ec.seg.iloc[i]
    labels = ec.cfg["area"].get("poi_labels", {})
    trail = ec.cfg["area"]["trail_names"].get(s.trail, s.trail)
    return labels.get(s.poi, f"{trail}, section {int(s.seg_id)}") if s.poi else f"{trail}, section {int(s.seg_id)}"


def gate_advice(ec: EntryControl, admitted: pd.DataFrame, now_min: int, rain_share: float,
                plan: pd.DataFrame | None, horizon_min: int = 120) -> dict:
    """admitted: trail, gate_min, size of everyone through the gate today; plan: tickets per slot (rows 'HH:MM')
    and trail (columns), or None (only the people already inside)."""
    K = ec.response(rain_share)                                  # [trail, slot, segment, bin]
    bm = ec.c["bin_minutes"]
    b0 = min(now_min // bm, ec.n_bins - 1)
    bins = np.arange(b0, min(b0 + max(1, horizon_min // bm) + 1, ec.n_bins))
    C = ec.capacity(rain_share)
    fin = np.isfinite(C)

    inside = np.zeros((ec.sim.S, len(bins)))
    seen = admitted[admitted.gate_min <= now_min]
    for (trail, k), g in seen.groupby([seen.trail, ec.slot_of(seen.gate_min.values)]):
        if trail in ec.trails:
            inside += K[ec.trails.index(trail), k][:, bins] * g["size"].sum()

    coming = np.zeros((len(ec.trails), len(ec.slots)))           # tickets of the slots that have not started
    if plan is not None:
        for k, s in enumerate(ec.slots):
            if s >= now_min - ec.c["slot_minutes"] + 1:
                lbl = f"{s // 60:02d}:{s % 60:02d}"
                if lbl in plan.index:
                    coming[:, k] = [float(plan.loc[lbl, t]) if t in plan.columns else 0.0 for t in ec.trails]

    def load(shift: dict) -> np.ndarray:
        """Occupancy over the horizon if the coming entrants of trail r are held `shift[r]` slots."""
        occ = inside.copy()
        for r in range(len(ec.trails)):
            d = shift.get(r, 0)
            for k in np.nonzero(coming[r])[0]:
                kk = min(k + d, len(ec.slots) - 1)
                occ += K[r, kk][:, bins] * coming[r, k]
        return occ

    base = load({})
    over_mask = (base > C[:, None]) & fin[:, None]
    over = []
    for i in np.unique(np.nonzero(over_mask)[0]):
        j = int(np.argmax(np.where(over_mask[i], base[i] / C[i], -1)))
        t = int(bins[j] * bm)
        over.append({"seg_id": int(ec.seg.seg_id.iloc[i]), "name": _label(ec, i), "trail": ec.seg.trail.iloc[i],
                     "at": f"{t // 60:02d}:{t % 60:02d}", "people": round(float(base[i, j]), 1),
                     "capacity": round(float(C[i]), 1)})

    names = ec.cfg["area"]["trail_names"]
    util_trail = {}
    for t in ec.trails:
        m = (ec.seg.trail == t).values & fin
        util_trail[t] = float((base[m] / C[m, None]).max()) if m.any() else 0.0
    room = [t for t, u in util_trail.items() if u < 0.6]
    advice = []
    for r, t in enumerate(ec.trails):
        uses = (K[r][:, :, bins].sum(axis=(0, 2)) > 1e-6)           # sections this trail's walkers reach
        if not (over_mask.any(axis=1) & uses).any() or coming[r].sum() == 0:
            continue
        hold = next((h for h in HOLDS_MIN[1:]
                     if not ((load({r: h // ec.c["slot_minutes"]}) > C[:, None]) & fin[:, None] & uses[:, None]).any()),
                    None)
        alt = [names.get(x, x) for x in room if x != t]
        text = (f"Hold new entries to the {names.get(t, t)} for {hold} min" if hold else
                f"Pause new entries to the {names.get(t, t)}: holding 90 min is not enough")
        if alt:
            text += f", or send the next groups to {' / '.join(alt)}"
        advice.append({"trail": t, "trail_name": names.get(t, t), "hold_min": hold, "send_to": alt, "text": text})
    t = now_min
    return {"time": f"{t // 60:02d}:{t % 60:02d}", "horizon_min": horizon_min, "over": over, "advice": advice,
            "inside": int(round(float(seen["size"].sum()))) if len(seen) else 0,
            "basis": f"From the {len(seen)} groups through the gate so far and the coming slots' tickets "
                     "(walked forward at usual speeds). No sensors on the trail."}
