"""RQ13: does closed-loop control at the gate (MPC) beat the day-ahead plans?
    python -m src.control.evaluate_mpc [--world s1] [--max-days N]

2025 test year (simulation). Every day the same groups want to come; only the gate policy changes:
  A        no control
  B        one daily quota per trail all year, first come first served (static)
  D        day-ahead slot tickets + moving to a later slot / another trail (the booking system)
  MPC(c)   closed loop: caps re-planned every slot from the gate counts so far (src/control/mpc.py); c = share of
           groups who accept another trail when theirs is full after waiting
  MPC-nf   MPC without the feedback (forecast never corrected by the arrivals so far): what feedback adds
--world s1: the realistic world - persistent busy spells, tour-bus bursts, a shifting morning peak, incidents
(simulator.realism) - where the day differs from what the calendar says. The controllers only know the calendar +
weather expectation of the day; the gate counts are their only live input.
Metrics: over-capacity person-hours, people admitted / turned away / sent to another trail / held, mean wait.
Outputs results/<timestamp>_mpc[_s1]/: daily.csv, summary.csv, tests.json
"""
import argparse
import copy
import json

import numpy as np
import pandas as pd
from scipy import stats

from src.config import RESULTS
from src.control.evaluate import admit
from src.control.mpc import MPCController
from src.control.slots import build_control
from src.data.calendar_features import build_calendar
from src.data.weather import load_weather
from src.sim.simulator import day_events, daily_demand
from src.utils import new_run_dir

COMPLIANCE = (0.25, 0.5, 0.75)
APP_SHARE = (0.3, 0.6, 0.9)        # N3: share of groups with the app who get a start time the evening before
FOLLOW = 0.8                       # ... of whom this share come at that time


def run(world="default", year="2025", seed=11, max_days=None, write=True, log=print):
    ec = build_control()
    cfg, sim = ec.cfg, ec.sim
    p = sim.p
    p_world = copy.deepcopy(p)
    if world == "s1":
        p_world["realism"]["enabled"] = True
    weather, cal = load_weather(cfg), build_calendar(cfg)
    precip = weather.precipitation.values.reshape(len(cal), 24)
    rng = np.random.default_rng(seed)
    demand = daily_demand(cal, precip, p_world, rng)                       # what really comes
    expected = daily_demand(cal, precip, p | {"daily_noise_sd": 0.0, "realism": {"enabled": False}},
                            np.random.default_rng(0))                       # what the calendar + weather say
    open_h = (cfg["capacity"].get("open_from_h", 6) + np.arange(cfg["capacity"]["open_hours"])) % 24
    rain_share_all = (precip[:, open_h] >= cfg["capacity"]["rain_mm"]).mean(1)
    train = cal.index <= pd.Timestamp(cfg["dates"]["train_end"])
    static = ec.daily_quota(float(rain_share_all[train].mean()))
    policies = (["A", "B", "D"] + [f"MPC{c}" for c in COMPLIANCE] + ["MPC-nf"] + [f"N3_{a}" for a in APP_SHARE]
                + [f"N3p_{a}" for a in APP_SHARE])
    ctrl = {f"MPC{c}": MPCController(ec, compliance=c) for c in COMPLIANCE}
    ctrl["MPC-nf"] = MPCController(ec, compliance=0.5, feedback=False)
    rows = []
    days = np.where(cal.index.year == int(year))[0][:max_days]
    for n, di in enumerate(days):
        ev = day_events(p_world, rng, sim.S, sim.trails[0]) if world == "s1" else {}
        size, gate, option = sim.sample_day(int(round(demand[di])), rng, events=ev)
        r = float(rain_share_all[di])
        C = ec.capacity(r)
        fin = np.isfinite(C)
        quota = ec.daily_quota(r)
        plan = ec.plan(r, quota)
        for k, pol in enumerate(policies):
            prng = np.random.default_rng([seed, int(di), k])
            st = {"refused": 0.0, "redirected": 0.0, "held": 0.0, "wait_sum": 0.0, "wait_n": 0.0}
            if pol == "A":
                s, g, o = size, gate, option
            elif pol == "B":
                s, g, o, m = admit("B", ec, size, gate, option, static, None, prng)
                st["refused"] = m["refused"]
            elif pol == "D":
                s, g, o, m = admit("D", ec, size, gate, option, quota, plan, prng)
                st.update(refused=m["refused"], redirected=m["moved_trail"], held=m["moved_slot"])
            elif pol.startswith("N3"):                                       # start times + gate control
                m = ctrl["MPC0.5"]
                share = float(pol.split("_")[1])
                g2, adv = m.advise_starts(size, gate, option, r, float(expected[di]), share, FOLLOW, prng)
                prio = adv["on_plan"] if pol.startswith("N3p") else None    # N3p: on-plan groups go first
                s, g, o, st = m.run_day(size, g2, option, r, float(expected[di]), prng, priority=prio)
                st["moved_by_advice"] = adv["moved_by_advice"]
                st["on_plan"] = float(size[adv["on_plan"]].sum())
            else:
                s, g, o, st = ctrl[pol].run_day(size, gate, option, r, float(expected[di]), prng)
            _, per_min, _ = sim.simulate_groups(s, g, o, precip[di], prng, slow=ev.get("slow"))
            occ = per_min.reshape(sim.S, ec.n_bins, -1).mean(-1)
            over = np.clip(occ[fin] - C[fin, None], 0, None)
            rows.append({"date": cal.index[di].date(), "policy": pol, "wanted": float(size.sum()),
                         "admitted": float(s.sum()), "refused": st["refused"], "redirected": st["redirected"],
                         "held": st["held"], "wait_min": st["wait_sum"] / max(st["wait_n"], 1e-9),
                         "moved_by_advice": st.get("moved_by_advice", 0.0),
                         "on_plan": st.get("on_plan", 0.0), "on_plan_entered": st.get("plan_people", 0.0),
                         "on_plan_wait_h": st.get("plan_wait_sum", 0.0) / 60,
                         "person_hours_over": float(over.sum() * ec.c["bin_minutes"] / 60),
                         "overcrowded": bool((over > 0).any())})
        if n % 50 == 0:
            log(f"{n}/{len(days)} days")
    df = pd.DataFrame(rows)
    g = df.groupby("policy")
    none_over = g.get_group("A").person_hours_over.sum()
    summary = pd.DataFrame([{
        "policy": pol,
        "person_hours_over": g.get_group(pol).person_hours_over.sum(),
        "cut_vs_no_control_pct": 100 * (1 - g.get_group(pol).person_hours_over.sum() / none_over),
        "admitted_pct": 100 * g.get_group(pol).admitted.sum() / g.get_group(pol).wanted.sum(),
        "refused_pct": 100 * g.get_group(pol).refused.sum() / g.get_group(pol).wanted.sum(),
        "redirected_pct": 100 * g.get_group(pol).redirected.sum() / g.get_group(pol).wanted.sum(),
        "held_pct": 100 * g.get_group(pol).held.sum() / g.get_group(pol).wanted.sum(),
        "mean_wait_min_of_held": float(np.average(g.get_group(pol).wait_min, weights=g.get_group(pol).held + 1e-9)),
        "gate_wait_person_hours": float((g.get_group(pol).wait_min * g.get_group(pol).held).sum() / 60),
        "moved_by_advice_pct": 100 * g.get_group(pol).moved_by_advice.sum() / g.get_group(pol).wanted.sum(),
        # those who came at their advised time: mean gate wait (min) - the incentive to follow the advice
        "on_plan_wait_min": float(60 * g.get_group(pol).on_plan_wait_h.sum() / max(g.get_group(pol).on_plan_entered.sum(), 1e-9)),
        "others_wait_min": float(60 * ((g.get_group(pol).wait_min * g.get_group(pol).held / 60).sum()
                                       - g.get_group(pol).on_plan_wait_h.sum())
                                 / max(g.get_group(pol).admitted.sum() - g.get_group(pol).on_plan_entered.sum(), 1e-9)),
        "days_overcrowded": int(g.get_group(pol).overcrowded.sum()),
    } for pol in policies])
    by = {pol: g.get_group(pol).sort_values("date") for pol in policies}
    tests = {}
    for d in by.values():
        d["gate_wait_h"] = d.wait_min * d.held / 60
    for a, b in (("MPC0.5", "D"), ("MPC0.5", "B"), ("MPC0.5", "MPC-nf"), ("MPC0.75", "D"), ("N3_0.6", "MPC0.5"),
                 ("N3_0.6", "D"), ("N3_0.9", "D"), ("N3p_0.6", "N3_0.6"), ("N3p_0.6", "D")):
        for metric in ("person_hours_over", "admitted", "gate_wait_h"):
            x, y = by[a][metric].values, by[b][metric].values
            d = x - y
            tests[f"{a}_vs_{b}_{metric}"] = {"mean_diff_per_day": float(d.mean()),
                                             "wilcoxon_p": float(stats.wilcoxon(x, y).pvalue) if np.any(d) else 1.0}
    if not write:
        return summary, tests, None
    run_dir = new_run_dir("mpc" + ("_s1" if world == "s1" else ""), cfg)
    df.to_csv(run_dir / "daily.csv", index=False)
    summary.to_csv(run_dir / "summary.csv", index=False)
    (run_dir / "tests.json").write_text(json.dumps(tests, indent=2), encoding="utf-8")
    (RESULTS / ("LATEST_MPC_S1" if world == "s1" else "LATEST_MPC")).write_text(run_dir.name, encoding="utf-8")
    return summary, tests, run_dir


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--world", choices=["default", "s1"], default="default")
    ap.add_argument("--max-days", type=int)
    a = ap.parse_args()
    s, t, d = run(a.world, max_days=a.max_days)
    print(s.round(2).to_string(index=False))
    print(json.dumps(t, indent=1))
    print(d)
