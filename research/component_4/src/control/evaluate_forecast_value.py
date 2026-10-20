"""RQ3: do better crowd forecasts give better crowd control?  (pilgrim site, recommended start times)
    $env:C4_PARK = "adams_peak"; python -m src.control.evaluate_forecast_value

Every night of the 2025 pilgrimage season, the advice (which start times to avoid, where to move) is computed
BEFORE the night from a forecast of climbers per route; the night then happens as it really did (the simulated
2025 total). Only the forecast behind the advice changes:
  none          no advice (everyone starts when they like)
  hist_avg      calendar average: same day type and month in 2022-23 (no model)
  plan_lead30   planning model, issued 30 days before (P50)
  plan_lead1    planning model, issued the day before (P50)
  plan_lead1_p90  the same forecast's high case (P90): cautious advice
  perfect       the real number of climbers (upper bound: what a perfect forecast could give)
`compliance` of the pilgrims told to move do so; movers are spread over windows with the forecast (Advisory.spread).
Measures: person-hours waiting on the final steps, people moved (inconvenience), most people on the final steps.
Outputs results/adams_peak/<timestamp>_forecast_value/: nightly.csv, summary.csv, tests.json, forecast_value.png
"""
import argparse
import json

import matplotlib
import numpy as np
import pandas as pd
from scipy import stats

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from src.config import PROCESSED, RESULTS, load_config  # noqa: E402
from src.control.advisory import build_advisory  # noqa: E402
from src.eval.data import TrailData  # noqa: E402
from src.planning.model import PlanningModel  # noqa: E402
from src.serve.predict import expected_visitors  # noqa: E402
from src.utils import new_run_dir, set_seed  # noqa: E402

SOURCES = ["none", "hist_avg", "plan_lead30", "plan_lead1", "plan_lead1_p90", "perfect"]
LABELS = {"none": "No advice", "hist_avg": "Calendar average", "plan_lead30": "Forecast 30 days ahead",
          "plan_lead1": "Forecast 1 day ahead", "plan_lead1_p90": "Forecast 1 day ahead (P90)",
          "perfect": "Perfect knowledge"}


def advise(adv, D_plan, compliance):
    """Advice published before the night: which [route, start slot] to avoid and where movers should go."""
    over = adv.wait_by_start(D_plan) > adv.limit
    _, moves = adv.spread(D_plan, D_plan * over * compliance)
    return over, moves


def follow(adv, advice, size, gate, option, compliance, rng):
    """The night: groups starting in an advised-against slot move with probability `compliance`."""
    over, moves = advice
    gate = gate.copy()
    slot = np.clip(np.searchsorted(adv.slots, gate, side="right") - 1, 0, len(adv.slots) - 1)
    r_of = np.array([adv.trails.index(adv.sim.options[o][0]) for o in option])
    moved = 0.0
    for g in np.where(over[r_of, slot])[0]:
        targets = moves[r_of[g], slot[g]]
        if targets.sum() <= 0 or rng.random() >= compliance:
            continue
        k = int(rng.choice(len(adv.slots), p=targets / targets.sum()))
        gate[g] = adv.slots[k] + rng.uniform(0, adv.c["slot_minutes"])
        moved += size[g]
    return gate, moved


def run(year: str = "2025", seed: int = 11, compliance: float = 0.5):
    adv = build_advisory()
    cfg, sim = adv.cfg, adv.sim
    set_seed(seed)
    data = TrailData(cfg)
    cal = pd.read_csv(PROCESSED / "calendar.csv", index_col=0, parse_dates=True)
    pm = PlanningModel(data, cal, cfg["seed"])
    hi = np.exp(pm.log_band[1])
    walk = sim.options[sim.option_of_trail(cfg["area"]["main_trail"])][1]
    final_steps = walk[sim._turnaround(walk) - 2][0]                 # the last segment before the summit
    days = pm.table.days
    nights = [i for i in range(len(days)) if days[i].year == int(year) and cal.is_season.iloc[i] == 1]
    trails = adv.trails
    rows = []
    for di in nights:
        actual = float(data.daily_visitors[di])
        rng = np.random.default_rng([seed, di])
        size, gate, option = sim.sample_day(int(round(actual)), rng)
        trail_of = np.array([sim.options[o][0] for o in option])
        fc = {"perfect": {t: float(size[trail_of == t].sum()) for t in trails},
              "hist_avg": expected_visitors(data, di)}
        for lead, name in ((1, "plan_lead1"), (30, "plan_lead30")):
            p = pm.daily.predict(pm.table, di - lead, np.array([di])).iloc[0]
            fc[name] = {t: float(p[f"{t}_p50"]) for t in trails}
            if lead == 1:
                fc["plan_lead1_p90"] = {t: v * hi for t, v in fc[name].items()}
        for src in SOURCES:
            prng = np.random.default_rng([seed, di, SOURCES.index(src)])
            if src == "none":
                g, moved = gate, 0.0
            else:
                advice = advise(adv, adv.demand(fc[src]), compliance)
                g, moved = follow(adv, advice, size, gate, option, compliance, prng)
            # same walking speeds every source (rain is not part of this test)
            _, per_min, _ = sim.simulate_groups(size, g, option, np.zeros(24), np.random.default_rng([seed, di]),
                                                hold=False)
            w = sim.last_wait
            final = per_min[final_steps]
            rows.append({"date": days[di].date(), "source": src, "actual": float(size.sum()),
                         "forecast": float(sum(fc[src].values())) if src != "none" else np.nan,
                         "is_poya": int(cal.is_poya.iloc[di]),
                         "person_hours_waiting": float((size * w).sum() / 60),
                         "moved": moved, "max_on_final_steps": float(final.max())})
    df = pd.DataFrame(rows)
    df["abs_error"] = (df.forecast - df.actual).abs()
    return summarise(df, cfg, compliance, seed)


def summarise(df, cfg, compliance, seed):
    g = df.groupby("source")
    summ = pd.DataFrame({
        "advice from": [LABELS[s] for s in SOURCES],
        "forecast_MAE_climbers": [g.get_group(s).abs_error.mean() for s in SOURCES],
        "person_hours_waiting": [g.get_group(s).person_hours_waiting.sum() for s in SOURCES],
        "poya_nights_person_hours": [g.get_group(s)[g.get_group(s).is_poya == 1].person_hours_waiting.sum()
                                     for s in SOURCES],
        "moved_pct": [100 * g.get_group(s).moved.sum() / g.get_group(s).actual.sum() for s in SOURCES],
        "mean_max_on_final_steps": [g.get_group(s).max_on_final_steps.mean() for s in SOURCES],
    })
    base = summ.person_hours_waiting.iloc[0]
    best = summ.person_hours_waiting.iloc[-1]
    summ["waiting_cut_pct"] = 100 * (1 - summ.person_hours_waiting / max(base, 1e-9))
    # share of the perfect-knowledge benefit that each forecast achieves (value of the forecast)
    summ["share_of_perfect_benefit_pct"] = 100 * (base - summ.person_hours_waiting) / max(base - best, 1e-9)

    w = {s: g.get_group(s).sort_values("date").person_hours_waiting.values for s in SOURCES}
    tests, boot = {}, np.random.default_rng(seed)
    for s in SOURCES[1:]:
        for ref in ("none", "plan_lead1", "perfect"):
            if s == ref:
                continue
            d = w[s] - w[ref]
            nz = d[np.abs(d) > 1e-6]                      # most nights have no queue: identical under every source
            # paired bootstrap over nights: 95 % interval of the season total difference
            idx = boot.integers(0, len(d), (10000, len(d)))
            lo, hi = np.percentile(d[idx].sum(1), [2.5, 97.5])
            tests[f"{s}_vs_{ref}"] = {"season_diff_person_hours": float(d.sum()), "ci95": [float(lo), float(hi)],
                                      "nights_that_differ": int(len(nz)),
                                      "wilcoxon_p": float(stats.wilcoxon(nz).pvalue) if len(nz) >= 6 else None,
                                      "nights": int(len(d))}

    run_dir = new_run_dir("forecast_value", cfg)
    df.to_csv(run_dir / "nightly.csv", index=False)
    summ.to_csv(run_dir / "summary.csv", index=False)
    (run_dir / "tests.json").write_text(json.dumps({"compliance": compliance, "seed": seed, "tests": tests},
                                                   indent=2), encoding="utf-8")
    (RESULTS / "LATEST_FORECAST_VALUE").write_text(run_dir.name, encoding="utf-8")

    fig, ax = plt.subplots(1, 2, figsize=(11, 3.8))
    colors = ["#9e9e9e", "#c07a2c", "#d9b44a", "#5b8bd0", "#3b5fa0", "#1b7f5a"]
    ax[0].bar([LABELS[s] for s in SOURCES], summ.person_hours_waiting, color=colors)
    ax[0].set_ylabel("Person-hours waiting on the final steps")
    ax[1].scatter(summ.forecast_MAE_climbers[1:], summ.waiting_cut_pct[1:], c=colors[1:], s=60)
    for _, r in summ.iloc[1:].iterrows():
        ax[1].annotate(r["advice from"], (r.forecast_MAE_climbers, r.waiting_cut_pct), fontsize=7,
                       xytext=(4, 4), textcoords="offset points")
    ax[1].set_xlabel("Forecast error (MAE, climbers per night)")
    ax[1].set_ylabel("Waiting cut vs no advice (%)")
    for a in ax:
        a.grid(alpha=0.3)
    ax[0].tick_params(axis="x", rotation=25, labelsize=7)
    fig.suptitle(f"Value of the forecast for start-time advice, 2025 season (simulation, compliance {compliance:.0%})")
    fig.tight_layout()
    fig.savefig(run_dir / "forecast_value.png", dpi=160)
    return summ, tests, run_dir


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--compliance", type=float, default=0.5)
    a = ap.parse_args()
    if load_config()["control"].get("booking_mode") != "advisory":
        raise SystemExit("Run for a pilgrim site:  $env:C4_PARK = 'adams_peak'")
    s, t, d = run(compliance=a.compliance)
    print(s.round(1).to_string(index=False))
    print(json.dumps(t, indent=1))
    print(d)
