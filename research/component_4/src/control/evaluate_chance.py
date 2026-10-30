"""RQ15 (plan §6.1.1, §6.1.2): a chance constraint at the gate vs the fixed safety margin; and who pays for control.
    python -m src.control.evaluate_chance [--world s1] [--calib-days 60] [--max-days N]

1. Calibration (training year, src.control.chance): the gate controller with the fixed margin runs on
   --calib-days days; its predicted occupancy (inside + K·admitted) is compared with the simulated real occupancy
   per section and half hour (where the prediction is at least 20 % of capacity). Fit per dry / wet day.
2. Test year 2025, the same groups every day, only the gate policy changes:
     A            no control
     fixed_0.9    MPC with the configured margin (plan to 90 % of capacity) - the current system
     fixed_0.8    a more cautious fixed margin
     cc_<eps>     MPC with the chance constraint P(over) <= eps per section and half hour
     app_<pol>    the same with start times for 60 % of groups, on-plan groups first (N3p): fairness of the app
   All MPC policies: 50 % accept another trail when theirs is full.
Metrics: over-capacity person-hours, days over capacity, the share of section-half-hours over capacity among the
busy ones (is P(over) near eps?), admitted / refused %, mean gate wait.
Fairness (§6.1.2), per group: refused % and mean wait of early (before 08:00), mid (08-10) and late (after 10:00)
arrivals, small (1-3) and large (6+) groups, and with / without a start time from the app.
Outputs results/<timestamp>_chance[_s1]/: calibration.json, summary.csv, fairness.csv, daily.csv, tests.json
"""
import argparse
import copy
import json

import numpy as np
import pandas as pd
from scipy import stats

from src.config import RESULTS
from src.control import chance
from src.control.mpc import MPCController
from src.control.slots import build_control
from src.data.calendar_features import build_calendar
from src.data.weather import load_weather
from src.sim.simulator import daily_demand, day_events
from src.utils import new_run_dir

EPS = (0.05, 0.10, 0.20)
APP_SHARE, FOLLOW = 0.6, 0.8


def _world(world, seed):
    ec = build_control()
    cfg, sim = ec.cfg, ec.sim
    p_world = copy.deepcopy(sim.p)
    if world == "s1":
        p_world["realism"]["enabled"] = True
    weather, cal = load_weather(cfg), build_calendar(cfg)
    precip = weather.precipitation.values.reshape(len(cal), 24)
    rng = np.random.default_rng(seed)
    demand = daily_demand(cal, precip, p_world, rng)
    expected = daily_demand(cal, precip, sim.p | {"daily_noise_sd": 0.0, "realism": {"enabled": False}},
                            np.random.default_rng(0))
    open_h = (cfg["capacity"].get("open_from_h", 6) + np.arange(cfg["capacity"]["open_hours"])) % 24
    rain = (precip[:, open_h] >= cfg["capacity"]["rain_mm"]).mean(1)
    return ec, p_world, cal, precip, demand, expected, rain, rng


def _predicted(ec, K, s, g, o):
    """inside + K·admitted: the controller's own occupancy prediction [segment, bin]."""
    inside = np.zeros((ec.sim.S, ec.n_bins))
    r_of = np.array([ec.trails.index(ec.sim.options[x][0]) for x in o], int) if len(o) else np.zeros(0, int)
    for r, k, n in zip(r_of, ec.slot_of(np.asarray(g, float)), s):
        inside += K[r, k] * n
    return inside


def calibrate(world="s1", seed=11, days=60, log=print) -> dict:
    ec, p_world, cal, precip, demand, expected, rain, rng = _world(world, seed)
    m = MPCController(ec, compliance=0.5)
    train = np.where(cal.index <= pd.Timestamp(ec.cfg["dates"]["train_end"]))[0]
    pick = np.random.default_rng(seed).choice(train, min(days, len(train)), replace=False)
    pairs = {"dry": ([], []), "wet": ([], [])}
    for n, di in enumerate(sorted(pick)):
        ev = day_events(p_world, rng, ec.sim.S, ec.sim.trails[0]) if world == "s1" else {}
        size, gate, option = ec.sim.sample_day(int(round(demand[di])), rng, events=ev)
        r = float(rain[di])
        s, g, o, _ = m.run_day(size, gate, option, r, float(expected[di]), np.random.default_rng([seed, int(di)]))
        _, per_min, _ = ec.sim.simulate_groups(s, g, o, precip[di], np.random.default_rng([seed, int(di), 1]),
                                               slow=ev.get("slow"))
        real = per_min.reshape(ec.sim.S, ec.n_bins, -1).mean(-1)
        pred = _predicted(ec, ec.response(r), s, g, o)
        C = ec.capacity(r)
        fin = np.isfinite(C)
        use = pred[fin] >= 0.2 * C[fin, None]
        pairs[chance.kind(r)][0].append(pred[fin][use])
        pairs[chance.kind(r)][1].append(real[fin][use])
        if n % 20 == 0:
            log(f"calibration {n}/{len(pick)} days")
    out = {}
    for k, (a, b) in pairs.items():
        if a and sum(len(x) for x in a) >= 30:
            out[k] = chance.fit(np.concatenate(a), np.concatenate(b))
    out.setdefault("wet", out.get("dry"))
    out.setdefault("dry", out.get("wet"))
    out["days"] = int(len(pick))
    return out


def run(world="s1", seed=11, calib_days=60, max_days=None, write=True, log=print):
    calib = calibrate(world, seed, calib_days, log)
    log(f"calibration: {calib}")
    ec, p_world, cal, precip, demand, expected, rain, rng = _world(world, seed + 1)
    sim = ec.sim
    ctrl = {"fixed_0.9": MPCController(ec, compliance=0.5),
            "fixed_0.8": MPCController(ec, compliance=0.5, margin=0.8)}
    for e in EPS:
        ctrl[f"cc_{e}"] = MPCController(ec, compliance=0.5, chance=calib | {"eps": e})
    app = ["fixed_0.9", "cc_0.1"]
    policies = ["A"] + list(ctrl) + [f"app_{a}" for a in app]
    rows, groups = [], []
    days = np.where(cal.index.year == 2025)[0][:max_days]
    for n, di in enumerate(days):
        ev = day_events(p_world, rng, sim.S, sim.trails[0]) if world == "s1" else {}
        size, gate, option = sim.sample_day(int(round(demand[di])), rng, events=ev)
        r = float(rain[di])
        C = ec.capacity(r)
        fin = np.isfinite(C)
        hour = gate / 60
        band = np.where(hour < 8, "early", np.where(hour < 10, "mid", "late"))
        for k, pol in enumerate(policies):
            prng = np.random.default_rng([seed, int(di), k])
            st = {"refused": 0.0, "redirected": 0.0, "held": 0.0, "wait_sum": 0.0, "wait_n": 0.0}
            on_plan = np.zeros(len(size), bool)
            if pol == "A":
                s, g, o = size, gate, option
                outcome, wait = np.zeros(len(size), int), np.zeros(len(size))
            else:
                m = ctrl[pol.removeprefix("app_")]
                g0 = gate
                if pol.startswith("app_"):
                    g0, adv = m.advise_starts(size, gate, option, r, float(expected[di]), APP_SHARE, FOLLOW, prng)
                    on_plan = adv["on_plan"]
                s, g, o, st = m.run_day(size, g0, option, r, float(expected[di]), prng,
                                        priority=on_plan if pol.startswith("app_") else None)
                outcome, wait = m.outcome.copy(), m.wait_min.copy()
            _, per_min, _ = sim.simulate_groups(s, g, o, precip[di], prng, slow=ev.get("slow"))
            occ = per_min.reshape(sim.S, ec.n_bins, -1).mean(-1)
            over = np.clip(occ[fin] - C[fin, None], 0, None)
            busy = occ[fin] >= 0.5 * C[fin, None]
            rows.append({"date": cal.index[di].date(), "policy": pol, "wet": chance.kind(r) == "wet",
                         "wanted": float(size.sum()), "admitted": float(s.sum()), "refused": st["refused"],
                         "redirected": st["redirected"], "wait_person_min": float((wait * size).sum()),
                         "person_hours_over": float(over.sum() * ec.c["bin_minutes"] / 60),
                         "busy_bins": int(busy.sum()), "busy_bins_over": int((busy & (over > 0)).sum()),
                         "overcrowded": bool((over > 0).any())})
            if pol != "A":
                groups.append(pd.DataFrame({"policy": pol, "size": size, "band": band, "app": on_plan,
                                            "refused": outcome == 2, "wait": wait}))
        if n % 25 == 0:
            log(f"{n}/{len(days)} days")
    df = pd.DataFrame(rows)
    gr = pd.concat(groups, ignore_index=True)
    g = df.groupby("policy")
    none_over = g.get_group("A").person_hours_over.sum()
    summary = pd.DataFrame([{
        "policy": pol,
        "person_hours_over": g.get_group(pol).person_hours_over.sum(),
        "cut_vs_no_control_pct": 100 * (1 - g.get_group(pol).person_hours_over.sum() / max(none_over, 1e-9)),
        "days_overcrowded": int(g.get_group(pol).overcrowded.sum()),
        "busy_halfhours_over_pct": 100 * g.get_group(pol).busy_bins_over.sum() / max(g.get_group(pol).busy_bins.sum(), 1),
        "wet_day_person_hours_over": g.get_group(pol)[g.get_group(pol).wet].person_hours_over.sum(),
        "admitted_pct": 100 * g.get_group(pol).admitted.sum() / g.get_group(pol).wanted.sum(),
        "refused_pct": 100 * g.get_group(pol).refused.sum() / g.get_group(pol).wanted.sum(),
        "mean_wait_min": g.get_group(pol).wait_person_min.sum() / g.get_group(pol).admitted.sum(),
    } for pol in policies])
    fair = []
    for pol, d in gr.groupby("policy"):
        cuts = {"early": d.band == "early", "mid": d.band == "mid", "late": d.band == "late",
                "small_1_3": d["size"] <= 3, "large_6plus": d["size"] >= 6}
        if d.app.any():
            cuts |= {"with_start_time": d.app, "without": ~d.app}
        for name, m in cuts.items():
            x = d[m]
            fair.append({"policy": pol, "group": name, "people": float(x["size"].sum()),
                         "refused_pct": 100 * float((x["size"] * x.refused).sum() / max(x["size"].sum(), 1e-9)),
                         "mean_wait_min": float((x["size"] * x.wait).sum() / max(x["size"].sum(), 1e-9))})
    fair = pd.DataFrame(fair)
    by = {pol: g.get_group(pol).sort_values("date") for pol in policies}
    tests = {}
    for a, b in (("cc_0.05", "fixed_0.9"), ("cc_0.1", "fixed_0.9"), ("cc_0.2", "fixed_0.9"), ("cc_0.1", "fixed_0.8")):
        for metric in ("person_hours_over", "admitted"):
            x, y = by[a][metric].values, by[b][metric].values
            tests[f"{a}_vs_{b}_{metric}"] = {"mean_diff_per_day": float((x - y).mean()),
                                             "wilcoxon_p": float(stats.wilcoxon(x, y).pvalue) if np.any(x - y) else 1.0}
    if not write:
        return summary, fair, tests, calib
    run_dir = new_run_dir("chance" + ("_s1" if world == "s1" else ""), ec.cfg)
    (run_dir / "calibration.json").write_text(json.dumps(calib, indent=2), encoding="utf-8")
    chance.CALIBRATION.write_text(json.dumps(calib, indent=2), encoding="utf-8")   # for live use (control.chance_eps)
    df.to_csv(run_dir / "daily.csv", index=False)
    summary.to_csv(run_dir / "summary.csv", index=False)
    fair.to_csv(run_dir / "fairness.csv", index=False)
    (run_dir / "tests.json").write_text(json.dumps(tests, indent=2), encoding="utf-8")
    (RESULTS / "LATEST_CHANCE").write_text(run_dir.name, encoding="utf-8")
    return summary, fair, tests, run_dir


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--world", choices=["default", "s1"], default="s1")
    ap.add_argument("--calib-days", type=int, default=60)
    ap.add_argument("--max-days", type=int)
    a = ap.parse_args()
    s, f, t, out = run(a.world, calib_days=a.calib_days, max_days=a.max_days)
    pd.set_option("display.width", 200)
    print(s.round(2).to_string(index=False))
    print(f.round(1).to_string(index=False))
    print(json.dumps(t, indent=1))
    print("->", out)
