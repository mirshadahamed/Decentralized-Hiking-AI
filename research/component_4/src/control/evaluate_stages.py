"""R6: does stage advice spread the peaks on an open long trail? Simulated 2025 weekends, C4_PARK=pekoe_trail.

    python -m src.control.evaluate_stages [--max-days N]

Every weekend day the same walkers come. Walkers on a stage that the stage outlook calls busy or crowded, starting
in its busy hours, follow the advice with probability 30 / 60 / 90 %. Three kinds of advice:
  early      start before the busy window (06:00 up to 2 h before it)
  spread     a random start between 06:00 and 11:00 (each walker told a different time)
  neighbour  walk the quieter neighbouring stage instead (fullness < 0.5 that day)
Metrics per day, at the viewpoint sections (capacity control.hotspot_at_once): peak fullness, person-hours over
capacity, and the number of busy stage-hours, vs no advice.
Outputs results/pekoe_trail/<timestamp>_stage_advice/: daily.csv, summary.json
"""
import argparse
import json

import numpy as np
import pandas as pd

from src.config import load_config
from src.control.slots import build_control
from src.data.calendar_features import build_calendar
from src.data.weather import load_weather
from src.sim.simulator import daily_demand
from src.utils import new_run_dir

FOLLOW = (0.3, 0.6, 0.9)
ADVICE = ("early", "spread", "neighbour")


def capacity(cfg, seg):
    c = cfg["capacity"]
    cap = seg.length_m.values / (c["group_gap_m"] + c["group_size"] * c["space_per_person_m"]) * c["group_size"]
    views = set(cfg["area"].get("poi_roles", {}).get("viewpoint", []))
    hot = seg.poi.fillna("").isin(views).values
    return np.where(hot, np.minimum(cap, cfg["control"].get("hotspot_at_once", 1e9)), cap), hot


def day_metrics(occ, cap, hot):
    full = occ / np.maximum(cap, 1e-9)[:, None]
    over = np.clip(occ[hot] - cap[hot, None], 0, None)
    return {"peak_fullness_hotspots": float(full[hot].max()) if hot.any() else 0.0,
            "person_hours_over_hotspots": float(over.sum()),
            "busy_section_hours": int((full >= 0.5).sum())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-days", type=int)
    ap.add_argument("--seed", type=int, default=6)
    a = ap.parse_args()
    cfg = load_config()
    if not cfg["area"].get("stage_relations"):
        raise SystemExit("Set $env:C4_PARK = 'pekoe_trail' first")
    rng = np.random.default_rng(a.seed)
    ec = build_control()
    sim, seg = ec.sim, ec.seg
    cap, hot = capacity(cfg, seg)
    weather, cal = load_weather(cfg), build_calendar(cfg)
    precip = weather.precipitation.values.reshape(len(cal), 24)
    demand = daily_demand(cal, precip, sim.p, rng)
    days = [d for d in np.where(cal.index.year == 2025)[0] if cal.index[d].dayofweek >= 5][:a.max_days]
    stage_of_seg = seg.trail.values
    rows = []
    for n, di in enumerate(days):
        size, gate, option = sim.sample_day(int(round(demand[di])), rng)
        trail_of = np.array([sim.options[k][0] for k in option])
        seed = int(rng.integers(1 << 30))
        _, per_min, _ = sim.simulate_groups(size, gate, option, precip[di], np.random.default_rng(seed))
        occ = per_min.reshape(sim.S, 24, 60).mean(-1)
        base = day_metrics(occ, cap, hot)
        rows.append({"date": cal.index[di].date(), "advice": "none", "follow": 0.0, **base})
        full = occ / np.maximum(cap, 1e-9)[:, None]
        busy_hours = {t: sorted({int(h) for h in np.where(full[stage_of_seg == t].max(0) >= 0.5)[0]})
                      for t in np.unique(stage_of_seg)}
        stages = sorted(busy_hours)
        load = {t: full[stage_of_seg == t].max() for t in stages}
        opt_of = {t: next(k for k, (tt, _) in enumerate(sim.options) if tt == t) for t in stages}
        for advice in ADVICE:
            for f in FOLLOW:
                g2, o2 = gate.copy(), option.copy()
                for t, hrs in busy_hours.items():
                    if not hrs:
                        continue
                    lo = min(hrs) * 60
                    m = np.where((trail_of == t) & (g2 >= lo - 180) & (g2 < (max(hrs) + 1) * 60)
                                 & (rng.random(len(g2)) < f))[0]
                    if advice == "early":                             # all: be past the busy place before it fills
                        g2[m] = rng.uniform(6 * 60, max(6 * 60 + 60, lo - 120), len(m))
                    elif advice == "spread":                          # a random start over the whole morning
                        g2[m] = rng.uniform(6 * 60, 11 * 60, len(m))
                    else:                                             # neighbour: walk the quieter next stage
                        i = stages.index(t)
                        nb = [stages[k] for k in (i - 1, i + 1) if 0 <= k < len(stages) and load[stages[k]] < 0.5]
                        if nb:
                            o2[m] = opt_of[min(nb, key=lambda x: load[x])]
                _, pm, _ = sim.simulate_groups(size, g2, o2, precip[di], np.random.default_rng(seed))
                rows.append({"date": cal.index[di].date(), "advice": advice, "follow": f,
                             **day_metrics(pm.reshape(sim.S, 24, 60).mean(-1), cap, hot)})
        if n % 20 == 0:
            print(f"{n}/{len(days)} weekend days", flush=True)
    df = pd.DataFrame(rows)
    summary = df.groupby(["advice", "follow"])[["peak_fullness_hotspots", "person_hours_over_hotspots", "busy_section_hours"]] \
        .mean().round(3).reset_index().to_dict(orient="records")
    run = new_run_dir("stage_advice", cfg)
    df.to_csv(run / "daily.csv", index=False)
    (run / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    print(run)


if __name__ == "__main__":
    main()
