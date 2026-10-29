"""A1: today's forecast updated during the day from the rangers' spot counts (RQ11b).

    GET /live/forecast/{day}?at=HH:MM        (ranger)

The spot model is the ST-GNN of the "spot" setting (src.eval.sparse_sensors --world s1 --settings spot): it reads
counts only at the gates, viewpoints and halfway checkpoints - places a ranger can stand and count - and the graph
carries them to the sections nobody counts (RQ11b: only the graph model improves those).
Input for the hours of today before `at`, on the counted sections: the ranger's count where there is one (mean of
the counts in that hour), otherwise the morning's day-ahead forecast. Earlier days: the live history.
Counts at other sections are not model input; they stay a check (Forecast check).
"""
from functools import lru_cache

import numpy as np
import pandas as pd
import torch

from src.config import RESULTS
from src.train.trainer import build_model, predict


@lru_cache(maxsize=1)
def spot_model(n_nodes: int, hidden: int, kind: str = "stgnn", seed: int = 42):
    """(checkpoint, run name) of the latest spot run, or None if there is none."""
    ptr = RESULTS / "LATEST_SPARSE_S1"
    if not ptr.exists():
        return None
    run = RESULTS / ptr.read_text(encoding="utf-8").strip()
    path = run / "models" / f"spot_{kind}_s{seed}.pt"
    if not path.exists():
        return None
    ck = torch.load(path, weights_only=False)
    if len(ck["sensed"]) != n_nodes:
        return None
    return ck, run.name


def _load(ctx):
    found = spot_model(ctx.data.N, ctx.cfg["train"]["hidden"])
    if found is None:
        return None
    ck, run = found
    model = build_model(ctx.data, ck["kind"], ctx.cfg["train"]["hidden"])
    model.load_state_dict(ck["state_dict"])
    return model.eval(), float(ck["scale"]), np.asarray(ck["sensed"], bool), run


def _label(cfg, s) -> str:
    trail = cfg["area"]["trail_names"].get(s.trail, s.trail)
    return cfg["area"].get("poi_labels", {}).get(s.poi, f"{trail}, section {int(s.seg_id)}") if s.poi else \
        f"{trail}, section {int(s.seg_id)}"


def model_sections(ctx) -> set:
    """seg_ids the spot model reads (where a count changes today's forecast)."""
    m = _load(ctx)
    return set() if m is None else {int(i) for i in ctx.seg.sort_values("seg_id").seg_id.values[m[2]]}


def update_today(ctx, day, now_min: int, counts: list) -> dict:
    """counts: rows with seg_id, time_min, count (the day's spot counts). Returns the rest of today per section:
    the morning forecast and the forecast updated with the counts so far."""
    from src.serve.predict import model_inputs
    data, cfg = ctx.data, ctx.cfg
    m = _load(ctx)
    if m is None:
        raise LookupError("No spot model yet: run python -m src.eval.sparse_sensors --world s1 --settings spot")
    model, scale, sensed, run = m
    t0 = int(np.searchsorted(data.times, pd.Timestamp(day)))
    if t0 >= data.T or data.times[t0] != pd.Timestamp(day):
        raise ValueError(f"{day} is outside the live data")
    hour = min(now_min // 60 + 1, 23)                         # forecast from the next full hour
    origin = t0 + hour
    if origin + data.H > data.T:
        raise ValueError("Not enough live data after this time")
    base_model = ctx.model
    morning = (predict(base_model, data, np.array([t0]), model_inputs(base_model, data), ctx.scale)[0]
               if base_model is not None else np.zeros((data.H, data.N)))     # [24, N] day-ahead

    order = {int(i): j for j, i in enumerate(ctx.seg.sort_values("seg_id").seg_id)}
    occ = data.y[origin - data.L:origin].astype(np.float64).copy()            # [L, N]
    today_rows = np.arange(data.L) + origin - data.L >= t0
    hrs = (np.arange(data.L) + origin - data.L - t0)[today_rows]
    occ[np.ix_(today_rows, sensed)] = morning[hrs][:, sensed]
    used, ignored = 0, 0
    by_cell: dict = {}
    for c in counts:
        h, j = int(c["time_min"]) // 60, order.get(int(c["seg_id"]))
        if j is None or h >= hour:
            continue
        if not sensed[j]:
            ignored += 1
            continue
        by_cell.setdefault((h, j), []).append(float(c["count"]))
    for (h, j), v in by_cell.items():
        occ[data.L - (hour - h), j] = np.mean(v)
        used += len(v)

    xp, xf, _, _ = data.batch(np.array([origin]), sensed, scale)
    xp = xp.clone()
    xp[0, :, :, 0] = torch.from_numpy((occ / scale * sensed).astype(np.float32))
    with torch.no_grad():
        upd = np.clip(model(xp, xf).numpy()[0] * scale, 0, None)            # [H, N] from `hour`

    c = cfg["capacity"]
    seg = ctx.seg.sort_values("seg_id").reset_index(drop=True)
    at_once = seg.length_m.values / (c["group_gap_m"] + c["group_size"] * c["space_per_person_m"]) * c["group_size"]
    open_h = [h for h in ((c.get("open_from_h", 6) + np.arange(c["open_hours"])) % 24) if h >= hour]
    rest = list(range(hour, 24))
    sections = []
    for j, s in seg.iterrows():
        before = [round(float(morning[h, j]), 1) for h in rest]
        after = [round(float(upd[h - hour, j]), 1) for h in rest]
        over = [h for h in open_h if upd[h - hour, j] > at_once[j]]
        sections.append({"seg_id": int(s.seg_id), "name": _label(cfg, s), "trail": s.trail,
                         "counted": bool(sensed[j]), "capacity_at_once": round(float(at_once[j]), 1),
                         "morning": before, "updated": after, "over_hours": over,
                         "change": round(float(max(after) - max(before)), 1) if rest else 0.0})
    changed = sorted(sections, key=lambda x: -abs(x["change"]))[:6]
    return {"day": str(day), "from_hour": hour, "hours": rest, "counts_used": used, "counts_not_used": ignored,
            "model_run": run, "sections": sections,
            "biggest_changes": [{k: x[k] for k in ("seg_id", "name", "change", "over_hours")} for x in changed],
            "over_capacity": [{k: x[k] for k in ("seg_id", "name", "over_hours", "capacity_at_once")}
                              for x in sections if x["over_hours"]],
            "basis": (f"Updated from {used} ranger count{'s' if used != 1 else ''} at the counted places "
                      f"({int(sensed.sum())} of {data.N} sections); the graph model carries them to the sections "
                      "nobody counts. Without counts it is the morning forecast.")}
