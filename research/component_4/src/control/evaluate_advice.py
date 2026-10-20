"""RQ8: can offline, forecast-based walk advice prevent overcrowding?  python -m src.control.evaluate_advice

Horton Plains, 2025 test year (simulation), the same groups every day as src.control.evaluate. Each morning every
phone has tomorrow's ST-GNN forecast (the day-ahead predictions of the benchmark run) and works out, for each trail,
direction (the World's End loop can be walked either way) and start hour, how full the sections will be when the
walker is on them (people ÷ what a section holds at Cifuentes spacing). A plan that meets a busy section
(>= busy_utilisation) is "bad". Groups with a bad plan follow the advice with probability c (compliance).

Policies
  A      no control
  Q      daily Cifuentes limit per trail (first come, first served), no advice
  D      slot tickets + moving (the booking system, for reference)
  H(c)   advice, HERD: every complying group takes the single best option on the phone
  S(c)   advice, SPREAD: each complying group draws one of the good options, weight = room left (main trail x2),
         as the app does (lib/features/component_4/domain/walk_advice.dart)
  QS     daily limit + spread advice at 50 % compliance
Metric: person-hours over capacity (as RQ entry control), peak at World's End, visitors refused / who changed plan.
Outputs results/<timestamp>_advice/: daily.csv, summary.csv, tests.json, advice.png
"""
import json

import matplotlib
import numpy as np
import pandas as pd
from scipy import stats

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from src.config import RESULTS  # noqa: E402
from src.control.evaluate import admit  # noqa: E402
from src.control.slots import build_control  # noqa: E402
from src.data.calendar_features import build_calendar  # noqa: E402
from src.data.weather import load_weather  # noqa: E402
from src.sim.simulator import daily_demand  # noqa: E402
from src.utils import new_run_dir  # noqa: E402

COMPLIANCE = (0.25, 0.5, 0.75, 1.0)


def walk_profiles(sim, start_hours):
    """on[o, h, s, t]: share of hour t that a walker who starts option o at hour h spends on segment s (dry day,
    one walker, so no crowd effect)."""
    rng = np.random.default_rng(0)
    on = np.zeros((len(sim.options), len(start_hours), sim.S, 24))
    for o in range(len(sim.options)):
        for i, h in enumerate(start_hours):
            _, per_min, _ = sim.simulate_groups(np.array([1.0]), np.array([h * 60.0 + 30]), np.array([o]),
                                                np.zeros(24), rng)
            on[o, i] = per_min.reshape(sim.S, 24, 60).mean(-1)
    return on


def option_scores(on, forecast, cap):
    """worst[o, h]: highest fullness (forecast people / capacity) on the segments the walker uses, at that time."""
    full = forecast.T / np.maximum(cap[:, None], 1e-9)               # [segment, hour]
    used = on > 0.05
    return np.where(used, full[None, None], 0).max(axis=(2, 3))


def advise(size, gate, option, worst, start_hours, sim, mode, compliance, busy, main_trail, rng):
    """Returns new gate times and options, and the number of people who changed their plan."""
    gate, option = gate.copy(), option.copy()
    hrs = np.array(start_hours)
    h_idx = np.clip(np.searchsorted(hrs, gate / 60, side="right") - 1, 0, len(hrs) - 1)
    bad = worst[option, h_idx] >= busy
    follow = bad & (rng.random(len(size)) < compliance)
    good = np.argwhere(worst < busy)                                  # (option, start index)
    if not len(good):                                                 # nothing quiet: the least bad
        good = np.argwhere(worst <= worst.min() + 0.1)
    if mode == "herd":
        o_best, i_best = np.unravel_index(np.argmin(worst), worst.shape)
        option[follow], gate[follow] = o_best, hrs[i_best] * 60 + rng.uniform(0, 60, follow.sum())
    else:
        w = np.maximum(0.05, 1 - worst[good[:, 0], good[:, 1]])
        w *= np.array([1.0 if sim.options[o][0] == main_trail else 0.5 for o in good[:, 0]])
        pick = rng.choice(len(good), size=int(follow.sum()), p=w / w.sum())
        option[follow] = good[pick, 0]
        gate[follow] = hrs[good[pick, 1]] * 60 + rng.uniform(0, 60, follow.sum())
    return gate, option, float(size[follow].sum())


def run(year="2025", seed=7, write=True, max_days=None):
    ec = build_control()
    cfg, sim = ec.cfg, ec.sim
    busy = cfg["capacity"]["busy_utilisation"]
    main_trail = cfg["area"].get("main_trail", "main")
    weather, cal = load_weather(cfg), build_calendar(cfg)
    precip = weather.precipitation.values.reshape(len(cal), 24)
    rng = np.random.default_rng(seed)
    demand = daily_demand(cal, precip, cfg["simulator"], rng)
    open_h = (cfg["capacity"].get("open_from_h", 6) + np.arange(cfg["capacity"]["open_hours"])) % 24
    last = int(cfg["simulator"]["gate_last_entry_h"])
    start_hours = [h for h in open_h if h <= last]
    on = walk_profiles(sim, start_hours)
    we = int(np.where(ec.seg.poi == cfg["area"]["focus_poi"])[0][0])

    # the phone's forecast: the ST-GNN day-ahead predictions of the benchmark run (test year)
    bench = RESULTS / (RESULTS / "LATEST").read_text(encoding="utf-8").strip()
    pred = np.load(bench / "predictions_temporal.npz")
    from src.eval.data import TrailData
    times = TrailData(cfg).times
    fc_by_date = {pd.Timestamp(times[o]).date(): pred["stgnn"][i] for i, o in enumerate(pred["origins"])}

    policies = ["A", "Q", "D"] + [f"H{c}" for c in COMPLIANCE] + [f"S{c}" for c in COMPLIANCE] + ["QS"]
    rows = []
    for di in np.where(cal.index.year == int(year))[0][:max_days]:
        day = cal.index[di].date()
        if day not in fc_by_date:
            continue
        rain_share = float((precip[di, open_h] >= cfg["capacity"]["rain_mm"]).mean())
        size, gate, option = sim.sample_day(int(round(demand[di])), rng)
        quota, C = ec.daily_quota(rain_share), ec.capacity(rain_share)
        plan = ec.plan(rain_share, quota)
        fin = np.isfinite(C)
        cap = np.where(fin, C, np.inf)
        worst = option_scores(on, fc_by_date[day], cap)
        for k, pol in enumerate(policies):
            prng = np.random.default_rng([seed, int(di), k])
            s, g, o, changed = size, gate, option, 0.0
            moved = {"refused": 0}
            if pol in ("Q", "D", "QS"):
                s, g, o, moved = admit("B" if pol in ("Q", "QS") else "D", ec, size, gate, option, quota, plan, prng)
            if pol[0] in "HS" or pol == "QS":
                c = 0.5 if pol == "QS" else float(pol[1:])
                g, o, changed = advise(s, g, o, worst, start_hours, sim, "herd" if pol[0] == "H" else "spread",
                                       c, busy, main_trail, prng)
            _, per_min, _ = sim.simulate_groups(s, g, o, precip[di], prng)
            occ = per_min.reshape(sim.S, ec.n_bins, -1).mean(-1)
            over = np.clip(occ[fin] - C[fin, None], 0, None)
            rows.append({"date": day, "policy": pol, "wanted": float(size.sum()), "admitted": float(s.sum()),
                         "refused": float(moved.get("refused", 0)), "changed_plan": changed,
                         "person_hours_over": float(over.sum() * ec.c["bin_minutes"] / 60),
                         "overcrowded": bool((over > 0).any()), "peak_focus": float(occ[we].max())})
    df = pd.DataFrame(rows)
    g = df.groupby("policy")
    a = g.get_group("A").person_hours_over.sum()
    summary = pd.DataFrame([{
        "policy": p,
        "person_hours_over_capacity": g.get_group(p).person_hours_over.sum(),
        "cut_vs_no_control_pct": 100 * (1 - g.get_group(p).person_hours_over.sum() / a),
        "days_overcrowded": int(g.get_group(p).overcrowded.sum()),
        "mean_peak_worlds_end": g.get_group(p).peak_focus.mean(),
        "refused_pct": 100 * g.get_group(p).refused.sum() / g.get_group(p).wanted.sum(),
        "changed_plan_pct": 100 * g.get_group(p).changed_plan.sum() / g.get_group(p).wanted.sum(),
    } for p in policies])
    av = g.get_group("A").person_hours_over.values
    tests = {p: {"wilcoxon_p_vs_A": float(stats.wilcoxon(av, g.get_group(p).person_hours_over.values).pvalue)}
             for p in policies if p != "A"}
    for c in COMPLIANCE:                                              # spread vs herd at the same compliance
        h, s = g.get_group(f"H{c}").person_hours_over.values, g.get_group(f"S{c}").person_hours_over.values
        tests[f"S{c}_vs_H{c}"] = {"wilcoxon_p": float(stats.wilcoxon(s, h).pvalue),
                                  "mean_diff_person_h": float((s - h).mean())}
    if not write:
        return summary, tests, None
    run_dir = new_run_dir("advice", cfg)
    df.to_csv(run_dir / "daily.csv", index=False)
    summary.to_csv(run_dir / "summary.csv", index=False)
    (run_dir / "tests.json").write_text(json.dumps(tests, indent=2), encoding="utf-8")
    (RESULTS / "LATEST_ADVICE").write_text(run_dir.name, encoding="utf-8")
    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    for mode, color, lab in (("H", "#C62828", "Herd: everyone gets the best option"),
                             ("S", "#2F6B4F", "Spread: random among good options")):
        ax.plot([100 * c for c in COMPLIANCE],
                [summary.set_index("policy").loc[f"{mode}{c}", "cut_vs_no_control_pct"] for c in COMPLIANCE],
                marker="o", color=color, label=lab)
    for p, ls, lab in (("Q", "--", "Daily Cifuentes limit"), ("QS", ":", "Limit + spread advice (50 %)"),
                       ("D", "-.", "Slot tickets")):
        ax.axhline(summary.set_index("policy").loc[p, "cut_vs_no_control_pct"], color="#555", ls=ls, lw=1.2, label=lab)
    ax.set_xlabel("Groups with a crowded plan who follow the advice (%)")
    ax.set_ylabel("Over-capacity person-hours cut (%)")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=7.5, frameon=False)
    fig.tight_layout()
    fig.savefig(run_dir / "advice.png", dpi=180)
    return summary, tests, run_dir


if __name__ == "__main__":
    s, t, d = run()
    print(s.round(2).to_string(index=False))
    print(json.dumps(t, indent=1))
    print(d)
