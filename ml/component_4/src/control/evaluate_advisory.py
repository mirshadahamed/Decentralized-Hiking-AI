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


if __name__ == "__main__":
    s, d = run()
    print(s.round(1).to_string(index=False))
    print(d)
