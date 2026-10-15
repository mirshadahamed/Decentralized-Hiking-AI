"""Does entry control prevent overcrowding?  python -m src.control.evaluate

Replays the 2025 test year in the simulator. Every day, the same groups want to come (same size, time and trail);
only the admission policy changes:
  A  no limit                 everyone walks when and where they want
  B  daily quota              Cifuentes daily quota per trail, first come first served; no time slots
  C  slot tickets             tickets per trail and 30-min slot (linear programme); a full slot = turned away
  D  slot tickets + moving    if the slot is full: a later slot on the same trail (up to 2 h), else (30 % accept)
                              another trail with room, else another day (a booking would offer that in advance)
Metric: person-hours over capacity (people above a segment's safe capacity, summed over segments and half hours),
plus peak at World's End, days with any overcrowded half hour, visitors admitted / moved / turned away.
Outputs results/<timestamp>_entry_control/: daily.csv, summary.csv, policy_comparison.png
"""
import json

import matplotlib
import numpy as np
import pandas as pd
from scipy import stats

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from src.config import RESULTS  # noqa: E402
from src.control.slots import build_control  # noqa: E402
from src.data.calendar_features import build_calendar  # noqa: E402
from src.data.weather import load_weather  # noqa: E402
from src.sim.simulator import daily_demand  # noqa: E402
from src.utils import new_run_dir  # noqa: E402

POLICIES = ["A", "B", "C", "D"]
NAMES = {"A": "A. No limit", "B": "B. Daily quota", "C": "C. Slot tickets", "D": "D. Slot tickets + moving"}


def admit(policy, ec, size, gate, option, quota, plan, rng):
    """Returns admitted (size, gate, option) and counts of moved / refused people."""
    trails, sim = ec.trails, ec.sim
    trail_idx = np.array([trails.index(sim.options[o][0]) for o in option])
    out = {"moved_slot": 0, "moved_trail": 0, "refused": 0}
    if policy == "A":
        return size, gate, option, out
    keep = np.zeros(len(size), bool)
    gate, option = gate.copy(), option.copy()
    order = np.argsort(gate)                                     # first come, first served
    if policy == "B":
        used = dict.fromkeys(trails, 0.0)
        for g in order:
            t = trails[trail_idx[g]]
            if used[t] + size[g] <= quota[t]:
                used[t] += size[g]
                keep[g] = True
            else:
                out["refused"] += size[g]
        return size[keep], gate[keep], option[keep], out

    left = plan.values.T.astype(float).copy()                    # [trail, slot] tickets left
    slot = ec.slot_of(gate)
    max_shift = int(ec.c["max_slot_shift_h"] * 60 / ec.c["slot_minutes"])
    for g in order:
        r, k = trail_idx[g], slot[g]
        if left[r, k] >= size[g]:
            left[r, k] -= size[g]
            keep[g] = True
            continue
        if policy == "C":
            out["refused"] += size[g]
            continue
        later = [kk for kk in range(k + 1, min(k + max_shift + 1, left.shape[1])) if left[r, kk] >= size[g]]
        if later:
            kk = later[0]
            left[r, kk] -= size[g]
            gate[g] = ec.slots[kk] + rng.uniform(0, ec.c["slot_minutes"])
            keep[g] = True
            out["moved_slot"] += size[g]
            continue
        if rng.random() < ec.c["accept_trail_swap"]:
            done = False
            for alt in ("thotupola", "kirigalpotta", "main"):
                ra = trails.index(alt)
                if ra == r:
                    continue
                for kk in range(k, min(k + max_shift + 1, left.shape[1])):
                    if left[ra, kk] >= size[g]:
                        left[ra, kk] -= size[g]
                        gate[g] = ec.slots[kk] + rng.uniform(0, ec.c["slot_minutes"])
                        option[g] = sim.option_of_trail(alt)
                        keep[g] = done = True
                        out["moved_trail"] += size[g]
                        break
                if done:
                    break
            if done:
                continue
        out["refused"] += size[g]                                 # offered another day
    return size[keep], gate[keep], option[keep], out


def run(year: str = "2025", seed: int = 7, policies=None, capacity_scale: float | None = None, write=True):
    ec = build_control()
    cfg, sim = ec.cfg, ec.sim
    old_scale = ec.c.get("capacity_scale", 1.0)
    if capacity_scale is not None:
        ec.c["capacity_scale"] = capacity_scale
    try:
        return _run(ec, cfg, sim, year, seed, policies or POLICIES, write)
    finally:
        ec.c["capacity_scale"] = old_scale


def _run(ec, cfg, sim, year, seed, policies, write):
    weather, cal = load_weather(cfg), build_calendar(cfg)
    precip = weather.precipitation.values.reshape(len(cal), 24)
    rng = np.random.default_rng(seed)
    demand = daily_demand(cal, precip, cfg["simulator"], rng)
    open_h = np.arange(6, 6 + cfg["capacity"]["open_hours"])
    we = int(np.where(ec.seg.poi == "worlds_end")[0][0])
    bins = ec.n_bins
    rows = []
    for di in np.where(cal.index.year == int(year))[0]:
        rain_share = float((precip[di, open_h] >= cfg["capacity"]["rain_mm"]).mean())
        size, gate, option = sim.sample_day(int(round(demand[di])), rng)
        quota = ec.daily_quota(rain_share)
        plan = ec.plan(rain_share, quota)
        C = ec.capacity(rain_share)
        fin = np.isfinite(C)
        for pol in policies:
            prng = np.random.default_rng([seed, int(di), POLICIES.index(pol)])
            s, g, o, moved = admit(pol, ec, size, gate, option, quota, plan, prng)
            _, per_min, _ = sim.simulate_groups(s, g, o, precip[di], prng)
            occ = per_min.reshape(sim.S, bins, -1).mean(-1)         # [segment, half hour]
            over = np.clip(occ[fin] - C[fin, None], 0, None)
            rows.append({"date": cal.index[di].date(), "policy": pol, "wanted": float(size.sum()),
                         "admitted": float(s.sum()), **moved,
                         "person_hours_over": float(over.sum() * ec.c["bin_minutes"] / 60),
                         "overcrowded": bool((over > 0).any()),
                         "peak_worlds_end": float(occ[we].max()), "cap_worlds_end": float(C[we]),
                         "is_poya": int(cal.is_poya.iloc[di]), "is_weekend": int(cal.is_weekend.iloc[di])})
    df = pd.DataFrame(rows)
    g = df.groupby("policy")
    summary = pd.DataFrame({
        "policy": [NAMES[p] for p in policies],
        "person_hours_over_capacity": [g.get_group(p).person_hours_over.sum() for p in policies],
        "days_overcrowded": [int(g.get_group(p).overcrowded.sum()) for p in policies],
        "mean_peak_worlds_end": [g.get_group(p).peak_worlds_end.mean() for p in policies],
        "admitted_pct": [100 * g.get_group(p).admitted.sum() / g.get_group(p).wanted.sum() for p in policies],
        "moved_slot_pct": [100 * g.get_group(p).moved_slot.sum() / g.get_group(p).wanted.sum() for p in policies],
        "moved_trail_pct": [100 * g.get_group(p).moved_trail.sum() / g.get_group(p).wanted.sum() for p in policies],
        "refused_pct": [100 * g.get_group(p).refused.sum() / g.get_group(p).wanted.sum() for p in policies],
    })
    tests = {}
    if "A" in policies:
        a = g.get_group("A").person_hours_over.values
        tests = {p: {"wilcoxon_p_vs_A": float(stats.wilcoxon(a, g.get_group(p).person_hours_over.values).pvalue)}
                 for p in policies if p != "A"}
    if not write:
        return summary, tests, None

    run_dir = new_run_dir("entry_control", cfg)
    df.to_csv(run_dir / "daily.csv", index=False)
    summary.to_csv(run_dir / "summary.csv", index=False)
    (run_dir / "tests.json").write_text(json.dumps(tests, indent=2), encoding="utf-8")
    (RESULTS / "LATEST_CONTROL").write_text(run_dir.name, encoding="utf-8")

    fig, ax = plt.subplots(1, 2, figsize=(11, 3.8))
    colors = ["#9e9e9e", "#c07a2c", "#5b8bd0", "#1b7f5a"]
    ax[0].bar([NAMES[p] for p in policies], summary.person_hours_over_capacity, color=colors[:len(policies)])
    ax[0].set_ylabel("Person-hours over capacity (2025)")
    ax[1].bar([NAMES[p] for p in policies], summary.admitted_pct, color=colors[:len(policies)], label="admitted")
    ax[1].set_ylabel("% of visitors admitted that day")
    for a_ in ax:
        a_.tick_params(axis="x", rotation=20, labelsize=8)
        a_.grid(axis="y", alpha=0.3)
    fig.suptitle("Entry control, test year 2025 (simulation)")
    fig.tight_layout()
    fig.savefig(run_dir / "policy_comparison.png", dpi=160)
    return summary, tests, run_dir


def sweep(run_dir, scales=(1.0, 1.5, 2.0, 3.0, 4.0)):
    """Trade-off for DWC: how strict a capacity standard -> how many visitors admitted vs overcrowding left.
    Over-capacity is always measured against the *chosen* standard."""
    rows = []
    for sc in scales:
        s, _, _ = run(policies=["A", "D"], capacity_scale=sc, write=False)
        a, d = s.iloc[0], s.iloc[1]
        rows.append({"capacity_scale": sc, "admitted_pct_D": d.admitted_pct, "refused_pct_D": d.refused_pct,
                     "over_A": a.person_hours_over_capacity, "over_D": d.person_hours_over_capacity,
                     "reduction_pct": 100 * (1 - d.person_hours_over_capacity / max(a.person_hours_over_capacity, 1e-9))})
    df = pd.DataFrame(rows)
    df.to_csv(run_dir / "capacity_sweep.csv", index=False)
    return df


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep", action="store_true", help="also run the capacity-standard trade-off")
    args = ap.parse_args()
    s, t, d = run()
    print(s.round(2).to_string(index=False))
    print(json.dumps(t))
    if args.sweep:
        print(sweep(d).round(2).to_string(index=False))
    print(d)
