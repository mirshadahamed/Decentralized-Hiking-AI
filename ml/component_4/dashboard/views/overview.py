import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from common import (MODEL_LABEL, default_run, get_data, require_dataset, run_results,  # noqa: E402
                    summary)

require_dataset()
st.title("Trail crowd forecasting and dynamic carrying capacity")
st.caption("Component 4 · Horton Plains National Park · Weerasekera J.V (IT23343948)")

st.markdown(
    "**The problem.** Park access is managed with one fixed daily permit number. It ignores weather, season and "
    "*where* on the trail people bunch up. **This component** forecasts how many people will be on each ~300 m "
    "piece of the World's End loop for every hour of the next day, and turns that forecast into a daily quota "
    "with the Cifuentes carrying-capacity method. It uses open data only: OpenStreetMap, satellite elevation, "
    "weather and the holiday/Poya calendar.")

s, data = summary(), get_data()
run = default_run()
res = run_results(run) if run else None

c = st.columns(4)
c[0].metric("Trail segments (graph nodes)", data.N, help="~300 m pieces of the 8.3 km loop")
c[1].metric("Simulated visitors / year", f"{s.get('visitors_per_year', 0):,.0f}",
            help="Synthetic target, 2022–2025. Calibration against field counts is still to do.")
c[2].metric("Median loop time", f"{s.get('median_loop_hours', 0):.1f} h", help="Commonly quoted: 3–4 h")
if res is not None:
    t = res["temporal"].set_index("model")
    ha, st_mae = t.loc["HA", "MAE"], t.loc["stgnn", "MAE"]
    c[3].metric("ST-GNN error (MAE)", f"{st_mae:.2f} persons", f"{(st_mae - ha) / ha:+.0%} vs historical average",
                delta_color="inverse")

st.subheader("Pipeline")
steps = pd.DataFrame([
    ("1. Trail graph", "OSM loop cut into ~300 m segments", "Done"),
    ("2. Terrain", "Slope, wetness (TWI), Tobler walking time from the Copernicus DEM", "Done"),
    ("3. Weather and calendar", "Open-Meteo hourly weather; holidays, Poya days, school holidays", "Done"),
    ("4. Occupancy simulator", "Synthetic hourly headcounts per segment (no real counts exist yet)",
     "Done (v1, field calibration after PP1)"),
    ("5. Forecasting models", "Historical average, SARIMA, LSTM, GRU, ST-GNN",
     "Done (from scratch; traffic pretraining after PP1)"),
    ("6. Evaluation", "Test year 2025 + spatial block CV; RMSE/MAE; paired t-test", "Done"),
    ("7. Capacity and output", "Cifuentes PCC → RCC → ECC, daily quota, JSON for Module 3 / dashboard",
     "Done (v1, parameters to confirm)"),
    ("8. Alternative-trail diversion", "Offer Kirigalpotta / Thotupola when World's End is crowded", "Planned"),
    ("9. On-device model", "Quantise, measure phone latency", "Planned"),
], columns=["Step", "What it does", "Status"])
st.dataframe(steps, hide_index=True, width="stretch")

if res is not None:
    st.subheader("Headline result")
    tests = {r["baseline"]: r for r in res.get("stats", {}).get("temporal", {}).get("tests_vs_stgnn", [])}
    lines = []
    for b, r in tests.items():
        better = r["mean_diff_MAE"] < 0
        verdict = "significantly better" if r["significant_0.05"] else ("not significantly different" if r["p_holm"] >= 0.05
                                                                      else "significantly worse")
        lines.append(f"- vs **{MODEL_LABEL[b]}**: ST-GNN is {verdict} "
                     f"({'−' if better else '+'}{abs(r['mean_diff_MAE']):.2f} persons per day, p = {r['p_holm']:.1e})")
    st.markdown("\n".join(lines))
    st.caption(f"Benchmark run: `{run}`. Details on the *Model comparison* page.")

st.info("All occupancy numbers come from a calibrated **simulation**, not sensor counts. "
        "Every assumption is listed on the *Simulator* page.", icon=":material/info:")
