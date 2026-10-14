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
st.latex(r"\text{quota}_{trail} = \min_{s \in trail} ECC_s \qquad \text{park quota} = \sum_{trails} \text{quota}_{trail}")
st.markdown(
    "- **PCC**: physical capacity, how many visits fit if the segment were full all day.\n"
    "- **RCC**: real capacity after the correction factors **FC** (each a share of length or of hours that is limiting).\n"
    "- **ECC**: effective capacity after management capacity **MC** (staff and facilities).\n"
    "- Each trail's quota is set by its **most limiting** segment; each visitor hikes one trail, so the park "
    "quota is the sum. Trail-wide factors are computed separately for each trail.")

st.subheader("2. Correction factors")
f = pd.DataFrame([
    ("Social", "Per trail", f"groups of {c['group_size']}, {c['group_gap_m']} m apart; the space between groups must stay empty", "fixed"),
    ("Erodibility", "Per trail", "share of wet, easily eroded ground (TWI ≥ 8) × 1.5", "fixed"),
    ("Accessibility", "Per trail", "share of 10–20 % grades × 1 + share > 20 % × 1.5", "fixed"),
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
st.markdown(f"Rain forecast in **{fc['rain_share_open_hours']:.0%}** of open hours · "
            f"management capacity MC = **{fc['management_capacity']}** · source: `{fc['source']['model']}`")
st.dataframe(pd.DataFrame([{"trail": v["name"], **{f"FC {k}": f for k, f in v["factors"].items()},
                            "expected": v["expected_visitors"], "quota": v["recommended_daily_quota"],
                            "classic quota": v["classic_cifuentes_quota"]} for v in fc["trails"].values()]),
             hide_index=True, width="stretch")

seg = get_segments()
labels = seg.set_index("seg_id").label
order = walk_order()
trail_pick = st.radio("Trail", list(fc["trails"]), horizontal=True, format_func=lambda t: fc["trails"][t]["name"])
tinfo = fc["trails"][trail_pick]
s = pd.DataFrame(fc["segments"])
s = s[s.trail == trail_pick].copy()
s["segment"] = s.seg_id.map(labels)
s["pos"] = s.seg_id.map(order.index)
s["limiting"] = s.seg_id == tinfo["limiting_segment"]
chart = alt.Chart(s).mark_bar().encode(
    x=alt.X("segment:N", sort=alt.EncodingSortField("pos"), title="Segment (walking order)"),
    y=alt.Y("ecc_per_day:Q", title="ECC (visits per day)"),
    color=alt.condition("datum.limiting", alt.value("#c0392b"), alt.value("#7aa6c2")),
    tooltip=["segment", "pcc_per_day", "rcc_per_day", "ecc_per_day", "crowded_hours_share"])
demand = alt.Chart(pd.DataFrame({"y": [tinfo["expected_visitors"]]})).mark_rule(strokeDash=[6, 4]).encode(y="y")
st.altair_chart((chart + demand).properties(height=320), width="stretch")
st.caption(f"Red bar = limiting segment → quota {tinfo['recommended_daily_quota']:,} visits on {tinfo['name']}. "
           f"Dashed line = expected demand ({tinfo['expected_visitors']:,}). Without the forecast factors "
           f"(classic Cifuentes) the quota would be {tinfo['classic_cifuentes_quota']:,}. "
           f"Park quota = sum over trails = {fc['recommended_daily_quota']:,}.")
st.dataframe(s.sort_values("pos")[["segment", "length_m", "pcc_per_day", "rcc_per_day", "ecc_per_day",
                                   "crowded_hours_share", "capacity_at_once", "peak_occupancy"]],
             hide_index=True, width="stretch")

st.warning("The quota is sensitive to parameters that are placeholders: group size, gap between groups, "
           "management capacity, and treating viewpoints as trail length rather than platform area. "
           "Confirm these with the supervisor / DWC before using the numbers.", icon=":material/warning:")
