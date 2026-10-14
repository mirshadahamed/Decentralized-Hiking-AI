import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import altair as alt  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from common import default_run, forecast, get_cfg, get_model, get_segments, require_dataset, walk_order  # noqa: E402

require_dataset()
st.title("Capacity method (Cifuentes)")
st.caption("How a forecast becomes a daily quota. The method is from Cifuentes (1992); the two forecast-driven "
           "factors are this project's v1 design and still need supervisor agreement.")

c = get_cfg()["capacity"]
st.subheader("1. The cascade, per trail segment")
st.latex(r"PCC_s = \frac{L_s}{sp}\cdot\frac{\text{open minutes}}{\text{visit minutes}_s}"
         r"\qquad RCC_s = PCC_s \prod_i (1 - FC_i)\,(1 - FC_{crowd,s})\qquad ECC_s = RCC_s \cdot MC")
st.latex(r"\text{daily quota} = \min_s ECC_s")
st.markdown(
    "- **PCC**: physical capacity, how many visits fit if the segment were full all day.\n"
    "- **RCC**: real capacity after the correction factors **FC** (each a share of length or of hours that is limiting).\n"
    "- **ECC**: effective capacity after management capacity **MC** (staff and facilities).\n"
    "- The quota is set by the **most limiting** segment.")

st.subheader("2. Correction factors")
f = pd.DataFrame([
    ("Social", "Trail-wide", f"groups of {c['group_size']}, {c['group_gap_m']} m apart; the space between groups must stay empty", "fixed"),
    ("Erodibility", "Trail-wide", "share of wet, easily eroded ground (TWI ≥ 8) × 1.5", "fixed"),
    ("Accessibility", "Trail-wide", "share of 10–20 % grades × 1 + share > 20 % × 1.5", "fixed"),
    ("Precipitation", "Trail-wide", f"share of open hours with forecast rain ≥ {c['rain_mm']} mm", "daily (weather forecast)"),
    ("Crowding (new)", "Per segment", "share of open hours in which the forecast occupancy exceeds what the segment holds at social spacing",
     "daily (ST-GNN forecast)"),
    ("Management capacity", "Trail-wide", f"MC = {c['management_capacity']} (placeholder until DWC data)", "fixed"),
], columns=["Factor", "Scope", "How it is computed", "Changes"])
st.dataframe(f, hide_index=True, width="stretch")

st.subheader("3. Worked example")
run = default_run()
day = st.date_input("Date", value=st.session_state.get("chosen_date", date(2025, 5, 12)),
                    min_value=date(2025, 1, 2), max_value=date(2025, 12, 31))
st.session_state["chosen_date"] = day
use_model = run is not None and get_model(run) is not None
fc = forecast(day.isoformat(), use_model, run or "")
tf = fc["trail_correction_factors"]
k = st.columns(len(tf) + 1)
for col, (name, v) in zip(k, tf.items()):
    col.metric(f"FC {name}", f"{v:.3f}")
k[-1].metric("MC", fc["management_capacity"])

seg = get_segments()
labels = seg.set_index("seg_id").label
order = walk_order()
s = pd.DataFrame(fc["segments"])
s["segment"] = s.seg_id.map(labels)
s["pos"] = s.seg_id.map(order.index)
s["limiting"] = s.seg_id == fc["limiting_segment"]
chart = alt.Chart(s).mark_bar().encode(
    x=alt.X("segment:N", sort=alt.EncodingSortField("pos"), title="Segment (walking order)"),
    y=alt.Y("ecc_per_day:Q", title="ECC (visits per day)"),
    color=alt.condition("datum.limiting", alt.value("#c0392b"), alt.value("#7aa6c2")),
    tooltip=["segment", "pcc_per_day", "rcc_per_day", "ecc_per_day", "crowded_hours_share"])
quota = alt.Chart(pd.DataFrame({"y": [fc["expected_visitors"]]})).mark_rule(strokeDash=[6, 4]).encode(y="y")
st.altair_chart((chart + quota).properties(height=320), width="stretch")
st.caption(f"Red bar = limiting segment → quota {fc['recommended_daily_quota']:,} visits. "
           f"Dashed line = expected demand ({fc['expected_visitors']:,}). "
           f"Without the forecast factors (classic Cifuentes) the quota would be {fc['classic_cifuentes_quota']:,}.")
st.dataframe(s.sort_values("pos")[["segment", "length_m", "pcc_per_day", "rcc_per_day", "ecc_per_day",
                                   "crowded_hours_share", "capacity_at_once", "peak_occupancy"]],
             hide_index=True, width="stretch")

st.warning("The quota is sensitive to parameters that are placeholders: group size, gap between groups, "
           "management capacity, and treating viewpoints as trail length rather than platform area. "
           "Confirm these with the supervisor / DWC before using the numbers.", icon=":material/warning:")
