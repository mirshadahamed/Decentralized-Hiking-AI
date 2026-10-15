import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import altair as alt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from common import (MODEL_LABEL, MODEL_ORDER, benchmark_runs, default_run, get_data, get_segments,  # noqa: E402
                    require_dataset, run_predictions, run_results, walk_order)

require_dataset()
st.title("Model comparison")
st.caption("Is the ST-GNN better than simpler forecasts? Test year 2025, day-ahead forecasts, open hours only.")

runs = benchmark_runs()
if not runs:
    st.error("No benchmark results yet. Run `python -m src.run_benchmark`.")
    st.stop()
run = st.selectbox("Benchmark run", runs, index=runs.index(default_run()) if default_run() in runs else 0)
res = run_results(run)
COLORS = alt.Scale(domain=[MODEL_LABEL[m] for m in MODEL_ORDER],
                   range=["#9e9e9e", "#c07a2c", "#5b8bd0", "#8e6cc0", "#1b7f5a"])


def tests_table(rows):
    df = pd.DataFrame(rows)
    df["compared with"] = df.baseline.map(MODEL_LABEL)
    df["ST-GNN error difference (persons/day)"] = df.mean_diff_MAE.round(3)
    df["verdict"] = np.where(df["significant_0.05"], "ST-GNN significantly better",
                             np.where(df.p_holm < 0.05, "ST-GNN significantly worse", "no significant difference"))
    df["p (Holm)"] = df.p_holm.map(lambda v: f"{v:.1e}")
    df["effect size d"] = df.cohens_dz.round(2)
    return df[["compared with", "ST-GNN error difference (persons/day)", "p (Holm)", "effect size d", "verdict", "n_days"]]


st.header("1. All segments have count history")
t = res["temporal"].copy()
t["model"] = t.model.map(MODEL_LABEL)
show = t[["model", "MAE", "RMSE", "MAE_peak", "MAE_poi"]].rename(columns={
    "MAE": "MAE", "RMSE": "RMSE", "MAE_peak": "MAE 07–11 h", "MAE_poi": "MAE viewpoints"})
c1, c2 = st.columns([1, 1])
c1.dataframe(show.round(3), hide_index=True, width="stretch")
bars = alt.Chart(t).mark_bar().encode(
    x=alt.X("model:N", sort=[MODEL_LABEL[m] for m in MODEL_ORDER], title=None),
    y=alt.Y("MAE:Q", title="MAE (persons)"), color=alt.Color("model:N", scale=COLORS, legend=None),
    tooltip=["model", alt.Tooltip("MAE:Q", format=".3f")])
if "MAE_sd" in t:
    err = alt.Chart(t.dropna(subset=["MAE_sd"])).mark_errorbar().encode(
        x=alt.X("model:N", sort=[MODEL_LABEL[m] for m in MODEL_ORDER]), y="lo:Q", y2="hi:Q").transform_calculate(
        lo="datum.MAE - datum.MAE_sd", hi="datum.MAE + datum.MAE_sd")
    bars = bars + err
c2.altair_chart(bars.properties(height=260), width="stretch")
st.caption("MAE = average error in people per segment-hour. Neural models: mean of 3 seeds (error bar = spread).")
if "stats" in res and "temporal" in res["stats"]:
    st.markdown("**Paired t-test per forecast day** (365 days, Holm-corrected):")
    st.dataframe(tests_table(res["stats"]["temporal"]["tests_vs_stgnn"]), hide_index=True, width="stretch")

st.header("2. Segments without counts (spatial block CV)")
if "spatial_folds" in res:
    f = res["spatial_folds"].copy()
    f["model"] = f.model.map(MODEL_LABEL)
    mean = f.groupby("model", as_index=False)[["MAE", "RMSE"]].mean()
    c1, c2 = st.columns([1, 1])
    c1.dataframe(mean.round(3), hide_index=True, width="stretch")
    c2.altair_chart(alt.Chart(f).mark_bar().encode(
        x=alt.X("fold:O", title="Held-out block"), xOffset="model:N", y=alt.Y("MAE:Q", title="MAE (persons)"),
        color=alt.Color("model:N", scale=COLORS, title=None)).properties(height=260), width="stretch")
    blocks = res["stats"]["spatial"]["blocks"]
    st.caption("Each fold hides one stretch of trail: segments " +
               "; ".join(f"{i}: {b}" for i, b in enumerate(blocks)) + ". 1 seed per fold.")
    st.dataframe(tests_table(res["stats"]["spatial"]["tests_vs_stgnn"]), hide_index=True, width="stretch")
else:
    st.info("This run has no spatial CV results.")

st.header("3. Forecast against what happened")
data = get_data()
pr = run_predictions(run) if res["has_predictions"] else None
same_graph = pr is not None and pr["HA"].shape[-1] == data.N
if pr is not None and not same_graph:
    st.info(f"This run was made on an earlier trail graph ({pr['HA'].shape[-1]} segments, now {data.N}). "
            "Pick a newer run to see forecasts against what happened.")
if same_graph:
    seg = get_segments()
    origins = pr["origins"]
    labels = seg.set_index("seg_id").label
    names = [labels[i] for i in walk_order()]
    c1, c2, c3 = st.columns([1.2, 1, 1.5])
    pick = c1.selectbox("Segment", names, index=next(i for i, n in enumerate(names) if "World's End" in n and "Mini" not in n))
    start = c2.date_input("Week starting", date(2025, 5, 9), min_value=date(2025, 1, 1), max_value=date(2025, 12, 24))
    models = c3.multiselect("Models", [m for m in MODEL_ORDER if m in pr], default=[m for m in ["HA", "stgnn"] if m in pr],
                            format_func=MODEL_LABEL.get)
    sid = int(pick[:2])
    d0 = int(np.where(data.times[origins] == pd.Timestamp(start))[0][0])
    days = slice(d0, d0 + 7)
    t_idx = np.concatenate([data.times[o:o + 24] for o in origins[days]])
    y, _ = data.targets(origins[days])
    rows = pd.DataFrame({"time": t_idx, "Simulated headcount": y[:, :, sid].ravel()})
    for m in models:
        rows[MODEL_LABEL[m]] = pr[m][days][:, :, sid].ravel()
    long = rows.melt("time", var_name="series", value_name="people")
    scale = alt.Scale(domain=["Simulated headcount"] + [MODEL_LABEL[m] for m in MODEL_ORDER],
                      range=["#222222", "#9e9e9e", "#c07a2c", "#5b8bd0", "#8e6cc0", "#1b7f5a"])
    st.altair_chart(alt.Chart(long).mark_line().encode(
        x=alt.X("time:T", title=None), y=alt.Y("people:Q", title="People"),
        color=alt.Color("series:N", scale=scale, title=None)).properties(height=300), width="stretch")
elif pr is None:
    st.info("Prediction files are not committed. Rerun the benchmark on this machine to see this chart.")

st.header("What this means")
tt = {r["baseline"]: r for r in res.get("stats", {}).get("temporal", {}).get("tests_vs_stgnn", [])}
sp = {r["baseline"]: r for r in res.get("stats", {}).get("spatial", {}).get("tests_vs_stgnn", [])}
msgs = []
if tt:
    beats = [MODEL_LABEL[b] for b, r in tt.items() if r["significant_0.05"]]
    ties = [MODEL_LABEL[b] for b, r in tt.items() if r["p_holm"] >= 0.05]
    msgs.append(f"- With count history on every segment, the ST-GNN significantly beats **{', '.join(beats) or 'none'}**"
                + (f", but is not significantly different from **{', '.join(ties)}**." if ties else "."))
if sp:
    worse = [MODEL_LABEL[b] for b, r in sp.items() if r["p_holm"] < 0.05 and r["mean_diff_MAE"] > 0]
    beats = [MODEL_LABEL[b] for b, r in sp.items() if r["significant_0.05"]]
    msgs.append(f"- On segments without counts it beats **{', '.join(beats) or 'none'}**"
                + (f" but loses to **{', '.join(worse)}**." if worse else "."))
if msgs:
    st.markdown("\n".join(msgs))
    graph_helps = all(sp.get(b, {}).get("significant_0.05", False) for b in ("lstm", "gru_nograph"))
    if graph_helps:
        st.success("**The graph helps where it matters for this park:** on segments without counts, the ST-GNN beats "
                   "the same network without the graph and the LSTM. With counts on every segment, the graph adds "
                   "nothing measurable: each segment's own history already says enough.")
    else:
        st.markdown("So far the **graph** part has not shown a clear benefit in this run.")
