"""Yala: does managing wildlife sightings stop the jeep jams, and what does it cost visitors?
    $env:C4_PARK = "yala"; python -m src.control.evaluate_sightings

A leopard by the track holds every passing jeep; dozens gather on one stretch within minutes. Replays the 2025
season in the simulator (open days only). Every day the same jeeps come and the same sightings happen; only the
ranger's rule at a sighting changes:
  none        every passing jeep stops as long as it likes (today)
  cap K / R   at most K jeeps stopped at a sighting at once, each for at most R minutes; a jeep that finds it full
              is moved on (first come, first served)
Measures: over-capacity person-hours (people above what a section holds at Cifuentes spacing) on the sighting
sections while the animal is there and in the whole park; share of jeeps passing a sighting that got to stop; mean
safari length. Paired Wilcoxon over days vs "none".
Outputs results/yala/<timestamp>_sightings/: daily.csv, summary.csv, tests.json
"""
import json

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.stats import wilcoxon

from src.config import PROCESSED, RESULTS, load_config
from src.data.calendar_features import build_calendar
from src.data.graph import load_walks
from src.data.weather import load_weather
from src.sim.simulator import TrailSimulator, daily_demand, day_sightings
from src.utils import new_run_dir

POLICIES = {"none": {}, "cap 15 / 15 min": {"cap_jeeps": 15, "rotation_min": 15},
            "cap 10 / 10 min": {"cap_jeeps": 10, "rotation_min": 10},
            "cap 5 / 10 min": {"cap_jeeps": 5, "rotation_min": 10}}


def at_once(seg, c) -> np.ndarray:
    return seg.length_m.values / (c["group_gap_m"] + c["group_size"] * c["space_per_person_m"]) * c["group_size"]


def run(year: str = "2025", seed: int = 11):
    cfg = load_config()
    p = cfg["simulator"]
    seg = gpd.read_file(PROCESSED / "segments.geojson").sort_values("seg_id")
    seg["poi"] = seg["poi"].fillna("")
    sim = TrailSimulator(seg, load_walks(), p)
    cap = at_once(seg, cfg["capacity"])[:, None]
    weather, cal = load_weather(cfg), build_calendar(cfg)
    precip = weather.precipitation.values.reshape(len(cal), 24)
    demand = daily_demand(cal, precip, p, np.random.default_rng(seed))
    days = np.where((cal.index.year == int(year)) & (demand > 0))[0]
    rows = []
    for i in days:
        sim.sightings = day_sightings(p, np.random.default_rng(seed * 100_000 + i), sim.hotspot_weight)
        size, gate, option = sim.sample_day(int(round(demand[i])), np.random.default_rng(seed * 100_000 + i + 1))
        win = np.zeros_like(cap, dtype=bool).repeat(1440, axis=1)            # sighting section x minute
        for s, a, b in sim.sightings:
            win[s, int(a):min(int(b) + 30, 1440)] = True                     # while it lasts + 30 min to clear
        for name, pol in POLICIES.items():
            sim.sighting_policy = pol
            _, per_min, dur = sim.simulate_groups(size, gate, option, precip[i], np.random.default_rng(seed + i))
            over = np.clip(per_min - cap, 0, None)
            st = sim.last_sighting_stats or {"viewed": 0, "moved_on": 0}
            passing = st.get("viewed", 0) + st.get("moved_on", 0)
            rows.append({"date": str(cal.index[i].date()), "policy": name, "visitors": float(size.sum()),
                         "jeeps": len(size), "sightings": len(sim.sightings),
                         "over_ph_at_sightings": float(over[win].sum() / 60), "over_ph_park": float(over.sum() / 60),
                         "max_people_on_a_section": float(per_min.max()),
                         "jeeps_passing_sightings": passing, "jeeps_stopped": st.get("viewed", 0),
                         "mean_safari_min": float(np.mean(dur))})
    df = pd.DataFrame(rows)
    g = df.groupby("policy", sort=False)
    summary = pd.DataFrame({
        "over_capacity_person_h_at_sightings": g.over_ph_at_sightings.sum(),
        "over_capacity_person_h_park": g.over_ph_park.sum(),
        "share_passing_jeeps_that_stopped_pct": 100 * g.jeeps_stopped.sum() / g.jeeps_passing_sightings.sum().clip(lower=1),
        "mean_safari_min": g.mean_safari_min.mean(),
        "p95_max_people_on_a_section": g.max_people_on_a_section.quantile(0.95),
    }).reindex(list(POLICIES))
    base = summary.loc["none"]
    summary["cut_at_sightings_pct"] = 100 * (1 - summary.over_capacity_person_h_at_sightings / base.over_capacity_person_h_at_sightings)
    summary["cut_park_pct"] = 100 * (1 - summary.over_capacity_person_h_park / base.over_capacity_person_h_park)
    a = df[df.policy == "none"].set_index("date")
    tests = {}
    for name in list(POLICIES)[1:]:
        b = df[df.policy == name].set_index("date")
        for col in ("over_ph_at_sightings", "over_ph_park"):
            d = (b[col] - a[col]).values
            tests[f"{name} vs none: {col}"] = {"mean_diff_per_day": float(d.mean()),
                                              "wilcoxon_p": float(wilcoxon(d).pvalue) if np.any(d != 0) else None}
    run_dir = new_run_dir("sightings", cfg)
    df.to_csv(run_dir / "daily.csv", index=False)
    summary.reset_index(names="policy").to_csv(run_dir / "summary.csv", index=False)
    (run_dir / "tests.json").write_text(json.dumps(tests, indent=2), encoding="utf-8")
    (RESULTS / "LATEST_SIGHTINGS").write_text(run_dir.name, encoding="utf-8")
    return summary, tests, run_dir


if __name__ == "__main__":
    s, t, d = run()
    print(s.round(1).to_string())
    print(json.dumps(t, indent=1))
    print(d)
