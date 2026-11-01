"""RQ14 (K9): do the Knuckles mechanisms work? Simulated 2025, C4_PARK=knuckles.

    python -m src.control.evaluate_knuckles [--max-days N]

1. Guided-trek permits. Each day guided groups ask for treks (the day's simulated demand x the trek's share,
   Poisson); requests arrive in random order. Policies:
     none        a group goes if a guide is free at its entry (today: no daily cap)
     fcfs_cap    ... and the trek's daily cap is not reached (first come first served)
     lp_plan     the guide-aware LP plan made the evening before from the EXPECTED requests (permits.plan_permits),
                 then first come first served within each trek's allocation
   Metrics: groups served, people over the treks' daily caps, guides idle, the trek served least (fairness).
   (Result, 30 Oct: fcfs_cap is best; the live system uses it and keeps the LP as the guide roster suggestion.)
2. Overdue alarm for groups out on a trek. Walking time = planned x lognormal(0, 0.15), slower in rain; 1 % of
   groups get into trouble (lost / injured: +Exp(4 h)). Rules:
     fixed_2h    alarm at start + the trek's walking time + 2 h, whatever the weather or group
     model       alarm at the expected return for that group size and rain + a margin that grows with the trek
                 (2.3 x 15 % of its time, at least 45 min; up to 30 min sooner in rain; permits.margin_minutes)
   Metrics: minutes from "should be back" to the alarm for groups in trouble; false alarms per 1,000 groups.
3. Open-viewpoint advice on weekends: a share of the visitors with the app (30 / 60 / 90 %) who would arrive in the
   busy window come in one of the quiet hours instead. Metric: Pitawala Pathana's peak people at once and car-hours
   over the parking spaces, vs no advice.
Outputs results/knuckles/<timestamp>_knuckles/: permits.csv, overdue.csv, viewpoints.csv, summary.json
"""
import argparse
import json

import numpy as np
import pandas as pd

from src.config import load_config
from src.control import permits
from src.control.slots import build_control
from src.data.calendar_features import build_calendar
from src.data.weather import load_weather
from src.sim.simulator import daily_demand
from src.utils import new_run_dir


def _caps(ec, rain):
    q = ec.daily_quota(rain)
    return {t: float(q.get(t, 0.0)) for t in ec.trails}


def overdue_eval(cfg, rains, rng, n_groups=20000):
    s = permits.settings(cfg)
    treks = list(s["treks"])
    rows = []
    for _ in range(n_groups):
        t = treks[rng.integers(len(treks))]
        size = int(np.clip(rng.poisson(5) + 1, 1, s["max_group"]))
        rain = float(rains[rng.integers(len(rains))])
        expected = permits.walk_minutes(cfg, t, size, rain)
        actual = s["treks"][t]["walk_h"] * 60 * (1 + 0.02 * max(0, size - 4)) * (1 + 0.25 * rain * rng.uniform(0.6, 1.4)) \
            * rng.lognormal(0, 0.15)
        trouble = rng.random() < 0.01
        if trouble:
            actual += rng.exponential(240)
        fixed = s["treks"][t]["walk_h"] * 60 + 120
        model = expected + permits.margin_minutes(cfg, expected, rain)
        for rule, at in (("fixed_2h", fixed), ("model", model)):
            rows.append({"rule": rule, "trouble": trouble, "alarm": actual > at,
                         "delay_min": at - expected if trouble else np.nan})
    df = pd.DataFrame(rows)
    out = {}
    for rule, g in df.groupby("rule"):
        tr, ok = g[g.trouble], g[~g.trouble]
        out[rule] = {"troubled_groups": int(len(tr)), "caught": float(tr.alarm.mean()),
                     "minutes_after_due_to_alarm": float(tr.delay_min.mean()),
                     "false_alarms_per_1000": float(1000 * ok.alarm.mean())}
    return out


def viewpoint_day(cfg, ec, n, precip, rng, follow):
    sim = ec.sim
    vp = cfg["control"].get("viewpoints", {})
    size, gate, option = sim.sample_day(n, rng)
    trail_of = np.array([sim.options[k][0] for k in option])
    idx = {t: np.where(ec.seg.trail.values == t)[0] for t in vp}
    res = {}
    base = None
    for share in (0.0,) + tuple(follow):
        g2 = gate.copy()
        if share > 0 and base is not None:
            for t in vp:
                busy = base[t]["busy"]
                if not busy:
                    continue
                lo, hi = min(busy) * 60, (max(busy) + 1) * 60
                m = np.where((trail_of == t) & (g2 >= lo - 30) & (g2 < hi) & (rng.random(len(g2)) < share))[0]
                quiet = [h for h in range(6, 16) if h not in busy and not (lo - 30 <= h * 60 < hi)]
                if quiet:                                             # spread over the quiet hours, not one window
                    g2[m] = rng.choice(quiet, len(m)) * 60 + rng.uniform(0, 60, len(m))
        _, per_min, _ = sim.simulate_groups(size, g2, option, precip, np.random.default_rng(int(rng.integers(1 << 30))))
        hourly = per_min.reshape(sim.S, 24, 60).mean(-1)
        out = {}
        for t, p in vp.items():
            people = hourly[idx[t]].sum(0)
            cars = people / p.get("people_per_vehicle", 4.0)
            out[t] = {"peak_people": float(people.max()),
                      "car_hours_over": float(np.clip(cars - p["parking_spaces"], 0, None).sum()),
                      "busy": [int(h) for h in np.where(people >= 0.5 * people.max())[0]] if people.max() > 0 else []}
        if base is None:
            base = out
        res[share] = out
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-days", type=int)
    ap.add_argument("--seed", type=int, default=14)
    a = ap.parse_args()
    cfg = load_config()
    if cfg["park"] != "knuckles":
        raise SystemExit("Set $env:C4_PARK = 'knuckles' first")
    rng = np.random.default_rng(a.seed)
    ec = build_control()
    p = ec.sim.p
    weather, cal = load_weather(cfg), build_calendar(cfg)
    precip = weather.precipitation.values.reshape(len(cal), 24)
    demand = daily_demand(cal, precip, p, rng)
    expected = daily_demand(cal, precip, p | {"daily_noise_sd": 0.0}, np.random.default_rng(0))
    open_h = (cfg["capacity"].get("open_from_h", 6) + np.arange(cfg["capacity"]["open_hours"])) % 24
    rain_all = (precip[:, open_h] >= cfg["capacity"]["rain_mm"]).mean(1)
    days = np.where(cal.index.year == 2025)[0][:a.max_days]
    share = p["route_share"]
    g_mean = permits.settings(cfg).get("mean_group", 6)
    prow, vrow = [], []
    for n, di in enumerate(days):
        caps = _caps(ec, float(rain_all[di]))
        exp_req = {t: expected[di] * share[t] / g_mean for t in permits.settings(cfg)["treks"]}
        real_scale = demand[di] / max(expected[di], 1e-9)          # the plan uses the expectation; the day is real
        res = permit_day(cfg, caps, exp_req, {t: v * real_scale for t, v in exp_req.items()}, rng)
        for pol, m in res.items():
            prow.append({"date": cal.index[di].date(), "policy": pol, **m})
        if cal.index[di].dayofweek >= 5:
            v = viewpoint_day(cfg, ec, int(round(demand[di])), precip[di], rng, (0.3, 0.6, 0.9))
            for f, out in v.items():
                for t, m in out.items():
                    vrow.append({"date": cal.index[di].date(), "follow": f, "trail": t,
                                 "peak_people": m["peak_people"], "car_hours_over": m["car_hours_over"]})
        if n % 50 == 0:
            print(f"{n}/{len(days)} days", flush=True)
    pdf, vdf = pd.DataFrame(prow), pd.DataFrame(vrow)
    od = overdue_eval(cfg, rain_all[days], rng)
    summary = {
        "permits": pdf.groupby("policy")[["requests", "groups", "people", "people_over_cap", "guides_idle",
                                          "least_served_share"]].mean().round(3).to_dict(orient="index"),
        "permit_days_over_cap": pdf.assign(over=pdf.people_over_cap > 0).groupby("policy").over.sum().to_dict(),
        "overdue": od,
        "viewpoints": vdf.groupby(["trail", "follow"])[["peak_people", "car_hours_over"]].mean().round(2)
                         .reset_index().to_dict(orient="records"),
    }
    run = new_run_dir("knuckles", cfg)
    pdf.to_csv(run / "permits.csv", index=False)
    vdf.to_csv(run / "viewpoints.csv", index=False)
    pd.DataFrame([{"rule": k, **v} for k, v in od.items()]).to_csv(run / "overdue.csv", index=False)
    (run / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=1, default=str))
    print(run)


def permit_day(cfg, caps, expected_req, real_req, rng):
    """One day of permit requests under each policy; the LP is planned on the expected requests, the day brings the
    real ones."""
    s = permits.settings(cfg)
    treks, guides = s["treks"], dict(s["guides_on_duty"])
    g_mean = s.get("mean_group", 6)
    real = {t: int(rng.poisson(real_req[t])) for t in treks}
    queue = [t for t, k in real.items() for _ in range(k)]
    rng.shuffle(queue)
    sizes = np.clip(rng.poisson(g_mean - 1, len(queue)) + 1, 1, s["max_group"])
    alloc = permits.plan_permits({t: caps[t] for t in treks}, expected_req, {t: v["entry"] for t, v in treks.items()},
                                 guides, g_mean)
    out = {}
    for pol in ("none", "fcfs_cap", "lp_plan"):
        free = dict(guides)
        people = {t: 0.0 for t in treks}
        groups = {t: 0 for t in treks}
        for t, k in zip(queue, sizes):
            e = treks[t]["entry"]
            if free[e] < 1 or (pol == "fcfs_cap" and people[t] + k > caps[t]) or (pol == "lp_plan" and groups[t] >= alloc[t]):
                continue
            free[e] -= 1
            people[t] += k
            groups[t] += 1
        served = [groups[t] / real[t] for t in treks if real[t]]
        out[pol] = {"requests": len(queue), "groups": sum(groups.values()), "people": sum(people.values()),
                    "people_over_cap": sum(max(0.0, people[t] - caps[t]) for t in treks),
                    "guides_idle": sum(free.values()), "least_served_share": min(served) if served else 1.0}
    return out


if __name__ == "__main__":
    main()
