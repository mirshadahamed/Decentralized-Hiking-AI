"""RQ9 (G2, claim C5): does the forecast make the daily quota better than a static one?
    python -m src.control.evaluate_quota            ($env:C4_PARK = "adams_peak" for the other park)

2025 test year (simulation), the same groups every day for every rule, first come first served at the gate
(policy B of src.control.evaluate). Five ways to set each trail's daily quota:
  static    one number per trail all year: Cifuentes with the training years' mean rain share (DWC-style)
  weather   classic Cifuentes with the day's rain (what slots.daily_quota did before)
  ha        + FCcrowd from the historical-average forecast
  stgnn     + FCcrowd from the ST-GNN day-ahead forecast (benchmark predictions, seed 42)
  oracle    + FCcrowd from the occupancy the day really has without control (a perfect forecast)
A quota rule trades visitors for crowding, so each rule is run at quota multipliers MULT and compared at EQUAL
visitors: over-capacity person-hours interpolated at the share admitted by the static quota (x1). Then each rule
is re-run at the multiplier that admits that many visitors, for paired Wilcoxon tests over days.
Outputs results/<park>/<timestamp>_quota/: sweep.csv, matched_daily.csv, summary.csv, tests.json, quota.png
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

RULES = ["static", "weather", "ha", "stgnn", "oracle"]
MULT = (0.5, 0.75, 1.0, 1.5, 2.0, 3.0)
COLORS = {"static": "#555555", "weather": "#1565C0", "ha": "#EF6C00", "stgnn": "#2F6B4F", "oracle": "#8E24AA"}


def benchmark_forecasts(cfg):
    """Day-ahead predictions of the base benchmark run (HA and ST-GNN), by date: {date: {kind: [24, N]}}."""
    from src.eval.data import TrailData
    bench = RESULTS / (RESULTS / "LATEST").read_text(encoding="utf-8").strip()
    pred = np.load(bench / "predictions_temporal.npz")
    times = TrailData(cfg).times
    return {pd.Timestamp(times[o]).date(): {"ha": pred["HA"][i], "stgnn": pred["stgnn"][i]}
            for i, o in enumerate(pred["origins"])}


def scale_quota(q: dict, m: float) -> dict:
    return {t: v * m for t, v in q.items()}


def setup(year="2025", seed=7, max_days=None):
    ec = build_control()
    cfg, sim = ec.cfg, ec.sim
    weather, cal = load_weather(cfg), build_calendar(cfg)
    precip = weather.precipitation.values.reshape(len(cal), 24)
    rng = np.random.default_rng(seed)
    demand = daily_demand(cal, precip, cfg["simulator"], rng)
    open_h = (cfg["capacity"].get("open_from_h", 6) + np.arange(cfg["capacity"]["open_hours"])) % 24
    rain_share = (precip[:, open_h] >= cfg["capacity"]["rain_mm"]).mean(1)
    train = cal.index <= pd.Timestamp(cfg["dates"]["train_end"])
    static = ec.daily_quota(float(rain_share[train].mean()))
    fc = benchmark_forecasts(cfg)
    C = ec.capacity(0.0)
    fin = np.isfinite(C)
    days = []
    for di in np.where(cal.index.year == int(year))[0][:max_days]:
        day = cal.index[di].date()
        if day not in fc:
            continue
        size, gate, option = sim.sample_day(int(round(demand[di])), rng)
        hourly, per_min, _ = sim.simulate_groups(size, gate, option, precip[di], np.random.default_rng([seed, int(di)]))
        r = float(rain_share[di])
        days.append({
            "date": day, "di": int(di), "rain_share": r, "groups": (size, gate, option),
            "quota": {"static": static, "weather": ec.daily_quota(r),
                      "ha": ec.daily_quota(r, forecast=fc[day]["ha"]),
                      "stgnn": ec.daily_quota(r, forecast=fc[day]["stgnn"]),
                      "oracle": ec.daily_quota(r, forecast=hourly)},
            "C": ec.capacity(r)})
    return ec, precip, days, fin, seed


def replay(ec, precip, d, quota, seed, k):
    size, gate, option = d["groups"]
    prng = np.random.default_rng([seed, d["di"], k])
    s, g, o, moved = admit("B", ec, size, gate, option, quota, None, prng)
    _, per_min, _ = ec.sim.simulate_groups(s, g, o, precip[d["di"]], prng)
    C = d["C"]
    fin = np.isfinite(C)
    occ = per_min.reshape(ec.sim.S, ec.n_bins, -1).mean(-1)
    over = np.clip(occ[fin] - C[fin, None], 0, None)
    return {"wanted": float(size.sum()), "admitted": float(s.sum()),
            "person_hours_over": float(over.sum() * ec.c["bin_minutes"] / 60), "overcrowded": bool((over > 0).any())}


def totals(df):
    g = df.groupby(["rule", "mult"])
    out = g.agg(admitted=("admitted", "sum"), wanted=("wanted", "sum"), person_hours_over=("person_hours_over", "sum"),
                days_overcrowded=("overcrowded", "sum")).reset_index()
    out["admitted_pct"] = 100 * out.admitted / out.wanted
    return out


def interp(curve: pd.DataFrame, x: float, col: str, by="admitted_pct"):
    c = curve.sort_values(by)
    return float(np.interp(x, c[by].values, c[col].values))


def run(year="2025", seed=7, write=True, max_days=None, log=print):
    ec, precip, days, fin, seed = setup(year, seed, max_days)
    log(f"{len(days)} days")
    rows = []
    base = {"rule": "none", "mult": 1.0}
    for d in days:                                                    # no control, for reference
        rows.append(base | {"date": d["date"]} | replay(ec, precip, d, {t: np.inf for t in ec.trails}, seed, 99))
    for i, rule in enumerate(RULES):
        for j, m in enumerate(MULT):
            for d in days:
                rows.append({"rule": rule, "mult": m, "date": d["date"]} |
                            replay(ec, precip, d, scale_quota(d["quota"][rule], m), seed, 10 * i + j))
        log(f"{rule} done")
    sweep = pd.DataFrame(rows)
    tot = totals(sweep)
    none_over = tot[tot.rule == "none"].person_hours_over.iloc[0]
    target = tot[(tot.rule == "static") & (tot.mult == 1.0)].admitted_pct.iloc[0]

    # matched: the multiplier at which each rule admits as many visitors as the static quota, then re-run
    matched, summary = [], []
    for i, rule in enumerate(RULES):
        curve = tot[tot.rule == rule]
        m = interp(curve, target, "mult")
        for d in days:
            matched.append({"rule": rule, "mult": m, "date": d["date"]} |
                           replay(ec, precip, d, scale_quota(d["quota"][rule], m), seed, 100 + i))
        r = pd.DataFrame([x for x in matched if x["rule"] == rule])
        summary.append({"rule": rule, "mult_matched": round(m, 3),
                        "admitted_pct": 100 * r.admitted.sum() / r.wanted.sum(),
                        "person_hours_over": r.person_hours_over.sum(),
                        "cut_vs_no_control_pct": 100 * (1 - r.person_hours_over.sum() / none_over),
                        "days_overcrowded": int(r.overcrowded.sum()),
                        "mean_quota_x1": float(np.mean([sum(d["quota"][rule].values()) for d in days]))})
    md = pd.DataFrame(matched)
    summary = pd.DataFrame(summary)
    st = summary.set_index("rule")
    gap = st.loc["static", "person_hours_over"] - st.loc["oracle", "person_hours_over"]
    summary["share_of_oracle_gain_pct"] = [100 * (st.loc["static", "person_hours_over"] - st.loc[r, "person_hours_over"])
                                           / gap if gap > 0 else np.nan for r in summary.rule]
    by = {r: md[md.rule == r].sort_values("date").person_hours_over.values for r in RULES}
    tests = {}
    for a, b in (("stgnn", "static"), ("stgnn", "weather"), ("stgnn", "ha"), ("oracle", "stgnn"),
                 ("weather", "static"), ("ha", "static")):
        diff = by[a] - by[b]
        tests[f"{a}_vs_{b}"] = {"mean_diff_person_h_per_day": float(diff.mean()),
                                "wilcoxon_p": float(stats.wilcoxon(by[a], by[b]).pvalue) if np.any(diff) else 1.0}
    tests["matched_admitted_pct"] = float(target)
    tests["no_control_person_hours_over"] = float(none_over)
    if not write:
        return summary, tests, None
    run_dir = new_run_dir("quota", ec.cfg)
    sweep.to_csv(run_dir / "sweep.csv", index=False)
    md.to_csv(run_dir / "matched_daily.csv", index=False)
    summary.to_csv(run_dir / "summary.csv", index=False)
    (run_dir / "tests.json").write_text(json.dumps(tests, indent=2), encoding="utf-8")
    (RESULTS / "LATEST_QUOTA").write_text(run_dir.name, encoding="utf-8")
    fig, ax = plt.subplots(figsize=(7, 3.8))
    for rule in RULES:
        c = tot[tot.rule == rule].sort_values("admitted_pct")
        ax.plot(c.admitted_pct, c.person_hours_over, marker="o", ms=3.5, color=COLORS[rule], label=rule)
    ax.axvline(target, color="#999", ls=":", lw=1)
    ax.set_xlabel("Visitors admitted (% of those who came)")
    ax.set_ylabel("Over-capacity person-hours (year)")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8, frameon=False)
    fig.tight_layout()
    fig.savefig(run_dir / "quota.png", dpi=180)
    return summary, tests, run_dir


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-days", type=int)
    a = ap.parse_args()
    s, t, d = run(max_days=a.max_days)
    print(s.round(3).to_string(index=False))
    print(json.dumps(t, indent=1))
    print(d)
