"""Figures for the PP1 slides and the thesis.  python -m src.report.figures [--date 2025-05-12]"""
import argparse
import json

import geopandas as gpd
import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from src.config import FIGURES, PROCESSED, RESULTS, load_config  # noqa: E402
from src.eval.data import TrailData  # noqa: E402

COLORS = {"HA": "#9e9e9e", "ARIMA": "#c07a2c", "lstm": "#5b8bd0", "gru_nograph": "#8e6cc0", "stgnn": "#1b7f5a"}
LABELS = {"HA": "Historical avg", "ARIMA": "SARIMA", "lstm": "LSTM", "gru_nograph": "GRU (no graph)",
          "stgnn": "ST-GNN (GCN+GRU)"}
POI_LABEL = {"entrance": "Visitor Center", "mini_worlds_end": "Mini World's End",
             "worlds_end": "World's End", "bakers_falls": "Baker's Falls",
             "kirigalpotta_peak": "Kirigalpotta", "thotupola_head": "Thotupola trailhead",
             "thotupola_peak": "Thotupola Kanda"}


def _seg():
    return gpd.read_file(PROCESSED / "segments.geojson")


def _label_pois(ax, seg):
    for _, r in seg[seg.poi.fillna("") != ""].iterrows():
        p = r.geometry.interpolate(0.5, normalized=True)
        ax.annotate(POI_LABEL.get(r.poi, r.poi), (p.x, p.y), xytext=(6, 6), textcoords="offset points",
                    fontsize=8, weight="bold")


def trail_map(data):
    seg = _seg()
    seg["peak"] = data.y_true.max(0)
    fig, ax = plt.subplots(figsize=(7, 6))
    seg.plot(ax=ax, column="peak", cmap="viridis", linewidth=4, legend=True,
             legend_kwds={"label": "Highest simulated occupancy (persons)", "shrink": 0.7})
    for _, r in seg.iterrows():
        p = r.geometry.interpolate(0.5, normalized=True)
        ax.text(p.x, p.y, str(r.seg_id), fontsize=6, ha="center", va="center", color="white",
                bbox=dict(boxstyle="circle,pad=0.15", fc="black", lw=0))
    _label_pois(ax, seg)
    ax.set_title(f"Horton Plains trail graph: {len(seg)} segment nodes, {data.edge_index.shape[1] // 2} edges")
    ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(FIGURES / "trail_graph.png", dpi=180)


def simulated_days(data):
    seg = _seg()
    we = int(seg.index[seg.poi == "worlds_end"][0])
    cal = pd.read_csv(PROCESSED / "calendar.csv", index_col=0, parse_dates=True).loc["2023"]
    day_rain = pd.Series(np.expm1(data.cov[:, data.cov_names.index("precip_log1p")]).reshape(-1, 24)[:, 5:10].sum(1),
                         index=data.times[::24])
    picks = {
        "Ordinary weekday": cal[(cal.dow == 2) & (cal.is_holiday == 0) & (cal.is_school_holiday == 0)].index[10],
        "Saturday": cal[(cal.dow == 5) & (cal.is_holiday == 0)].index[10],
        "Poya day": cal[cal.is_poya == 1].index[3],
        "Rainy weekday": day_rain.loc["2023"][cal.dow.values < 5].idxmax(),
    }
    fig, ax = plt.subplots(figsize=(7, 4))
    for name, d in picks.items():
        i = int(np.searchsorted(data.times, d))
        ax.plot(range(24), data.y_true[i:i + 24, we], marker="o", ms=3, label=f"{name} ({d:%d %b %Y})")
    ax.set_xlim(5, 19)
    ax.set_xlabel("Hour of day")
    ax.set_ylabel("Persons on segment")
    ax.set_title("Simulated occupancy at World's End")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIGURES / "simulated_days.png", dpi=180)


def forecast_week(data, run, date):
    preds = np.load(run / "predictions_temporal.npz")
    origins = preds["origins"]
    seg = _seg()
    we = int(seg.index[seg.poi == "worlds_end"][0])
    start = int(np.where(data.times[origins] == pd.Timestamp(date) - pd.Timedelta(days=3))[0][0])
    days = slice(start, start + 7)
    o = origins[days]
    y, _ = data.targets(o)
    t = np.concatenate([data.times[x:x + 24] for x in o])
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(t, y[:, :, we].ravel(), color="black", lw=1.6, label="Simulated headcount")
    for k in ["HA", "ARIMA", "lstm", "stgnn"]:
        if k in preds:
            ax.plot(t, preds[k][days][:, :, we].ravel(), color=COLORS[k], lw=1.1, label=LABELS[k])
    ax.set_title(f"Day-ahead forecasts at World's End, week around {date} (test year)")
    ax.set_ylabel("Persons on segment")
    ax.legend(fontsize=8, ncol=5)
    ax.grid(alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(FIGURES / "forecast_week.png", dpi=180)


def metrics_bar(run):
    df = pd.read_csv(run / "metrics_temporal.csv").set_index("model")
    order = [m for m in ["HA", "ARIMA", "lstm", "gru_nograph", "stgnn"] if m in df.index]
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.6))
    for ax, col in zip(axes, ["MAE", "RMSE", "MAE_poi"]):
        vals = df.loc[order, col]
        err = df.loc[order, col + "_sd"].fillna(0) if col + "_sd" in df else None
        ax.bar([LABELS[m] for m in order], vals, yerr=err, color=[COLORS[m] for m in order], capsize=3)
        ax.set_title({"MAE": "MAE (all segments)", "RMSE": "RMSE (all segments)",
                      "MAE_poi": "MAE (viewpoint segments)"}[col])
        ax.tick_params(axis="x", rotation=35, labelsize=8)
        ax.grid(axis="y", alpha=0.3)
    fig.suptitle("Test year 2025, day-ahead, open hours (persons)")
    fig.tight_layout()
    fig.savefig(FIGURES / "metrics_temporal.png", dpi=180)


def capacity_map(date):
    path = RESULTS / "forecasts" / f"forecast_{date}.json"
    if not path.exists():
        return
    js = json.loads(path.read_text(encoding="utf-8"))
    seg = _seg()
    seg["util"] = [s["utilisation"] for s in js["segments"]]
    fig, ax = plt.subplots(figsize=(7, 6))
    seg.plot(ax=ax, column="util", cmap="RdYlGn_r", vmin=0, vmax=1.5, linewidth=5, legend=True,
             legend_kwds={"label": "Forecast peak / effective capacity", "shrink": 0.7})
    _label_pois(ax, seg)
    lines = [f"{v['name']}: expected {v['expected_visitors']}, quota {v['recommended_daily_quota']}"
             for v in js.get("trails", {}).values()]
    ax.set_title(f"{date}\n" + " · ".join(lines), fontsize=9)
    ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(FIGURES / f"capacity_{date}.png", dpi=180)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="2025-05-12")
    a = ap.parse_args()
    cfg = load_config()
    data = TrailData(cfg)
    trail_map(data)
    simulated_days(data)
    latest = RESULTS / (RESULTS / "LATEST").read_text(encoding="utf-8").strip()
    if (latest / "predictions_temporal.npz").exists():
        forecast_week(data, latest, a.date)
        metrics_bar(latest)
    capacity_map(a.date)
    print(f"figures -> {FIGURES}")
