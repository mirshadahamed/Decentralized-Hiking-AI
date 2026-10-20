"""How good is the planning model at each lead time?  python -m src.planning.backtest

Test year 2025: issue a 90-day outlook every 7 days; compare with what happened (simulated headcount).
Baseline: historical average (same day type and month in 2022-23; per segment and hour for occupancy).
Outputs results/<timestamp>_planning_backtest/: metrics_by_lead.csv, tests.json, lead_time.png
"""
import json

import matplotlib
import numpy as np
import pandas as pd
from scipy import stats

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from src.config import PROCESSED, RESULTS, load_config  # noqa: E402
from src.eval.data import TrailData  # noqa: E402
from src.models.baselines import HistoricalAverage  # noqa: E402
from src.planning.model import PlanningModel  # noqa: E402
from src.serve.predict import expected_visitors  # noqa: E402
from src.utils import new_run_dir, set_seed  # noqa: E402

BUCKETS = [(2, 7), (8, 16), (17, 30), (31, 60), (61, 90)]


def run(step_days: int = 7):
    cfg = load_config()
    set_seed(cfg["seed"])
    data = TrailData(cfg)
    cal = pd.read_csv(PROCESSED / "calendar.csv", index_col=0, parse_dates=True)
    pm = PlanningModel(data, cal, cfg["seed"])
    ha = HistoricalAverage().fit(data, np.ones(data.N, bool))
    lo, hi = cfg["task"]["open_hours"]
    days = pm.table.days
    first_test = data.val_end // 24
    rows = []
    for issue in range(first_test, len(days) - 2, step_days):
        ol = pm.outlook(days[issue])
        ol = ol[ol.lead >= 2]
        for target, r in ol.iterrows():
            ti = pm.day_index(target)
            actual = float(data.daily_visitors[ti])
            ha_day = sum(expected_visitors(data, ti).values())
            occ_plan = pm.hourly(r)[lo:hi + 1]
            occ_ha = ha.predict(data, np.array([ti * 24]))[0][lo:hi + 1]
            occ_true = data.y[ti * 24 + lo: ti * 24 + hi + 1]
            rows.append({"issue": days[issue], "target": target, "lead": int(r.lead), "actual": actual,
                         "p10": r.p10, "p50": r.p50, "p90": r.p90, "ha": ha_day,
                         "err_plan": abs(r.p50 - actual), "err_ha": abs(ha_day - actual),
                         "inside": r.p10 <= actual <= r.p90,
                         "occ_err_plan": float(np.abs(occ_plan - occ_true).mean()),
                         "occ_err_ha": float(np.abs(occ_ha - occ_true).mean())})
    df = pd.DataFrame(rows)
    df["bucket"] = pd.cut(df.lead, [b[0] - 1 for b in BUCKETS] + [BUCKETS[-1][1]],
                          labels=[f"{a}-{b}" for a, b in BUCKETS])

    out, tests = [], {}
    for b, g in df.groupby("bucket", observed=True):
        # pair by target day (average over the issues that cover it) so pairs are independent days
        per_day = g.groupby("target")[["err_plan", "err_ha", "occ_err_plan", "occ_err_ha"]].mean()
        t_d = stats.ttest_rel(per_day.err_plan, per_day.err_ha)
        t_o = stats.ttest_rel(per_day.occ_err_plan, per_day.occ_err_ha)
        out.append({"lead_days": str(b), "n_forecasts": len(g), "n_days": len(per_day),
                    "visitors_MAE_planning": g.err_plan.mean(), "visitors_MAE_hist_avg": g.err_ha.mean(),
                    "coverage_P10_P90": g.inside.mean(),
                    "occupancy_MAE_planning": g.occ_err_plan.mean(), "occupancy_MAE_hist_avg": g.occ_err_ha.mean()})
        tests[str(b)] = {"visitors": {"t": t_d.statistic, "p": t_d.pvalue},
                         "occupancy": {"t": t_o.statistic, "p": t_o.pvalue}}
    met = pd.DataFrame(out)

    run_dir = new_run_dir("planning_backtest", cfg)
    met.to_csv(run_dir / "metrics_by_lead.csv", index=False)
    (run_dir / "tests.json").write_text(json.dumps(tests, indent=2, default=float), encoding="utf-8")
    df.drop(columns=["bucket"]).to_csv(run_dir / "forecasts.csv", index=False)
    (RESULTS / "LATEST_PLANNING").write_text(run_dir.name, encoding="utf-8")

    by_lead = df.groupby("lead")[["err_plan", "err_ha", "inside"]].mean()
    fig, ax = plt.subplots(1, 2, figsize=(11, 3.8))
    ax[0].plot(by_lead.index, by_lead.err_plan, color="#1b7f5a", label="Planning model (P50)")
    ax[0].plot(by_lead.index, by_lead.err_ha, color="#9e9e9e", label="Historical average")
    ax[0].set_xlabel("Days ahead")
    ax[0].set_ylabel("MAE, visitors per day")
    ax[0].legend()
    ax[0].grid(alpha=0.3)
    ax[1].plot(by_lead.index, 100 * by_lead.inside, color="#5b8bd0")
    ax[1].axhline(80, ls="--", color="k", lw=1)
    ax[1].set_ylim(0, 100)
    ax[1].set_xlabel("Days ahead")
    ax[1].set_ylabel("% of days inside P10-P90")
    ax[1].grid(alpha=0.3)
    fig.suptitle("Long-range planning forecast, test year 2025")
    fig.tight_layout()
    fig.savefig(run_dir / "lead_time.png", dpi=160)
    return met, tests, run_dir


if __name__ == "__main__":
    met, tests, run_dir = run()
    print(met.round(3).to_string(index=False))
    print(json.dumps({b: {k: round(v["p"], 4) for k, v in t.items()} for b, t in tests.items()}))
    print(run_dir)
