"""Do recommended start times and halfway checks keep the queue off the summit steps?
    $env:C4_PARK = "adams_peak"; python -m src.control.evaluate_advisory

Replays the 2025 pilgrimage season in the simulator. Every night the same pilgrims want to climb; only the policy
changes:
  A  nothing                   everyone starts when they like; the queue forms on the final steps
  B  recommended start times   pilgrims whose start time is expected to wait more than the limit move to a
                               recommended start (still reaching the summit for sunrise); `compliance` of them follow
  C  halfway checks            officers hold groups at each route's halfway checkpoint so they reach the top when
                               there is room (the wait happens at the rest halt)
  D  both B and C
Main measure: person-hours of waiting ON THE FINAL STEPS (the safety risk), and the most people there at once.
The day's total is assumed forecast correctly (the forecast error is reported by the planning backtest).
Outputs results/adams_peak/<timestamp>_advisory/: daily.csv, summary.csv
"""
import json

import numpy as np
import pandas as pd

from src.config import RESULTS
from src.control.advisory import build_advisory
from src.data.calendar_features import build_calendar
from src.data.weather import load_weather
from src.sim.simulator import daily_demand
from src.utils import new_run_dir

POLICIES = {"A": "A. Nothing", "B": "B. Recommended start times", "C": "C. Halfway checks", "D": "D. Both"}


def shift_starts(adv, size, gate, option, rec, compliance, rng):
    """Policy B: pilgrims whose start time is expected to wait over the limit are advised to move; `compliance`
    of them do. Movers are spread over start windows batch by batch (Advisory.spread), so the advice does not
    create a new peak (herding)."""
    gate = gate.copy()
    sim = adv.sim
    slot_of = np.clip(np.searchsorted(adv.slots, gate, side="right") - 1, 0, len(adv.slots) - 1)
    r_of = np.array([adv.trails.index(sim.options[o][0]) for o in option])
    D = np.zeros((len(adv.trails), len(adv.slots)))
    np.add.at(D, (r_of, slot_of), size)
    W = adv.wait_by_start(D)
    movers_idx = [g for g in range(len(size)) if W[r_of[g], slot_of[g]] > adv.limit and rng.random() < compliance]
    M = np.zeros_like(D)
    for g in movers_idx:
        M[r_of[g], slot_of[g]] += size[g]
    _, moves = adv.spread(D, M)
    moved = 0.0
    for g in movers_idx:                                   # hand out the planned new windows group by group
        r, k = r_of[g], slot_of[g]
        targets = moves[r, k]
        if targets.sum() <= 0:
            continue
        k_to = int(rng.choice(len(adv.slots), p=targets / targets.sum()))
        gate[g] = adv.slots[k_to] + rng.uniform(0, adv.c["slot_minutes"])
        moved += size[g]
    return gate, moved


def run(year: str = "2025", seed: int = 7, compliance: float = 0.5):
    adv = build_advisory()
    cfg, sim = adv.cfg, adv.sim
    weather, cal = load_weather(cfg), build_calendar(cfg)
    precip = weather.precipitation.values.reshape(len(cal), 24)
    demand = daily_demand(cal, precip, cfg["simulator"], np.random.default_rng(seed))
    walk = sim.options[sim.option_of_trail(cfg["area"]["main_trail"])][1]
    i = sim._turnaround(walk)
    final_steps = walk[i - 2][0]
    days = np.where((cal.index.year == int(year)) & (cal.is_season == 1))[0]
    rows = []
    for di in days:
        rng = np.random.default_rng([seed, int(di)])
        size, gate, option = sim.sample_day(int(round(demand[di])), rng)
        trail_of = np.array([sim.options[o][0] for o in option])
        rec = adv.recommend({t: float(size[trail_of == t].sum()) for t in adv.trails})
        for pol in POLICIES:
            prng = np.random.default_rng([seed, int(di), list(POLICIES).index(pol)])
            g, moved = (shift_starts(adv, size, gate, option, rec, compliance, prng) if pol in "BD" else (gate, 0.0))
            hold = pol in "CD"
            _, per_min, _ = sim.simulate_groups(size, g, option, precip[di], prng, hold=hold)
            w = sim.last_wait
            ph = float((size * w).sum() / 60)
            rows.append({"date": cal.index[di].date(), "policy": pol, "climbers": float(size.sum()),
                         "moved_start": moved, "is_poya": int(cal.is_poya.iloc[di]),
                         "wait_p90_min": float(np.percentile(np.repeat(w, size.astype(int)), 90)) if size.sum() else 0,
                         "person_hours_waiting_final_steps": 0.0 if hold else ph,
                         "person_hours_waiting_halfway": ph if hold else 0.0,
                         "max_people_final_steps": float(per_min[final_steps].max())})
    df = pd.DataFrame(rows)
    g = df.groupby("policy")
    summary = pd.DataFrame({
        "policy": [POLICIES[p] for p in POLICIES],
        "person_hours_waiting_final_steps": [g.get_group(p).person_hours_waiting_final_steps.sum() for p in POLICIES],
        "person_hours_waiting_halfway": [g.get_group(p).person_hours_waiting_halfway.sum() for p in POLICIES],
        "mean_p90_wait_min": [g.get_group(p).wait_p90_min.mean() for p in POLICIES],
        "poya_nights_max_people_final_steps": [g.get_group(p)[g.get_group(p).is_poya == 1].max_people_final_steps.mean()
                                               for p in POLICIES],
        "moved_start_pct": [100 * g.get_group(p).moved_start.sum() / g.get_group(p).climbers.sum() for p in POLICIES],
    })
    run_dir = new_run_dir("advisory", cfg)
    df.to_csv(run_dir / "daily.csv", index=False)
    summary.to_csv(run_dir / "summary.csv", index=False)
    (run_dir / "settings.json").write_text(json.dumps({"compliance": compliance, "season_nights": int(len(days))}),
                                           encoding="utf-8")
    (RESULTS / "LATEST_ADVISORY").write_text(run_dir.name, encoding="utf-8")
    return summary, run_dir


def sweep(year: str = "2025", seed: int = 7, compliances=(0.25, 0.5, 0.75, 1.0), flows=(15, 20, 25, 30, 35)):
    """RQ4: do the policies still work when the assumptions are wrong? Final-steps flow (people/min, the most
    uncertain number, A/B1) x compliance (share who follow the advice, C3). Policies A and C do not depend on
    compliance, so they run once per flow. Outputs results/adams_peak/<timestamp>_advisory_sweep/."""
    adv = build_advisory()
    cfg, sim = adv.cfg, adv.sim
    weather, cal = load_weather(cfg), build_calendar(cfg)
    precip = weather.precipitation.values.reshape(len(cal), 24)
    demand = daily_demand(cal, precip, cfg["simulator"], np.random.default_rng(seed))
    nights = np.where((cal.index.year == int(year)) & (cal.is_season == 1))[0]
    old = sim.flow
    rows = []
    try:
        for flow in flows:
            sim.flow = adv.flow = float(flow)
            for pol, comp in [("A", None), ("C", None)] + [(p, c) for c in compliances for p in ("B", "D")]:
                ph_final = ph_half = moved = climbers = 0.0
                for di in nights:
                    rng = np.random.default_rng([seed, int(di)])
                    size, gate, option = sim.sample_day(int(round(demand[di])), rng)
                    trail_of = np.array([sim.options[o][0] for o in option])
                    prng = np.random.default_rng([seed, int(di), list(POLICIES).index(pol)])
                    g, m = gate, 0.0
                    if pol in "BD":
                        rec = adv.recommend({t: float(size[trail_of == t].sum()) for t in adv.trails})
                        g, m = shift_starts(adv, size, gate, option, rec, comp, prng)
                    hold = pol in "CD"
                    sim.simulate_groups(size, g, option, precip[di], prng, hold=hold)
                    ph = float((size * sim.last_wait).sum() / 60)
                    ph_half += ph if hold else 0.0
                    ph_final += 0.0 if hold else ph
                    moved, climbers = moved + m, climbers + float(size.sum())
                rows.append({"flow_per_min": flow, "policy": pol, "compliance": comp,
                             "person_hours_final_steps": ph_final, "person_hours_halfway": ph_half,
                             "moved_pct": 100 * moved / climbers})
                print(rows[-1], flush=True)
    finally:
        sim.flow = adv.flow = old
    df = pd.DataFrame(rows)
    base = df[df.policy == "A"].set_index("flow_per_min").person_hours_final_steps
    df["total_waiting"] = df.person_hours_final_steps + df.person_hours_halfway
    df["final_steps_cut_pct_vs_A"] = 100 * (1 - df.person_hours_final_steps / df.flow_per_min.map(base).clip(lower=1e-9))
    df["total_waiting_change_pct_vs_A"] = 100 * (df.total_waiting / df.flow_per_min.map(base).clip(lower=1e-9) - 1)
    run_dir = new_run_dir("advisory_sweep", cfg)
    df.to_csv(run_dir / "sweep.csv", index=False)
    (RESULTS / "LATEST_ADVISORY_SWEEP").write_text(run_dir.name, encoding="utf-8")
    _sweep_figure(df, run_dir)
    return df, run_dir


def _sweep_figure(df, run_dir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 2, figsize=(11, 3.8))
    for comp, g in df[df.policy == "B"].groupby("compliance"):
        ax[0].plot(g.flow_per_min, g.final_steps_cut_pct_vs_A, marker="o", label=f"{comp:.0%} follow")
    ax[0].set_title("B. Start times: waiting on the final steps cut (%)")
    a = df[df.policy == "A"].set_index("flow_per_min")
    for pol, lab in (("C", "C. Halfway checks"), ("D", "D. Both (50 % follow)")):
        g = df[(df.policy == pol) & ((df.compliance.isna()) | (df.compliance == 0.5))].set_index("flow_per_min")
        ax[1].plot(g.index, g.total_waiting, marker="o", label=lab)
    ax[1].plot(a.index, a.person_hours_final_steps, marker="o", color="#9e9e9e", label="A. Nothing")
    ax[1].set_title("Total person-hours waiting (final steps + halfway)")
    for x in ax:
        x.set_xlabel("Final-steps flow (people per minute)")
        x.grid(alpha=0.3)
        x.legend(fontsize=8)
    fig.suptitle("Sensitivity of the Adam's Peak policies, 2025 season (simulation)")
    fig.tight_layout()
    fig.savefig(run_dir / "sweep.png", dpi=160)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep", action="store_true", help="sensitivity to flow and compliance instead of one run")
    if ap.parse_args().sweep:
        d, r = sweep()
        print(d.round(1).to_string(index=False))
        print(r)
    else:
        s, d = run()
        print(s.round(1).to_string(index=False))
        print(d)
