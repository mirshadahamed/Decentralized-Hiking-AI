import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import altair as alt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from common import (STATUS_COLOR, calendar, deck, default_run, extension_layers, forecast,  # noqa: E402
                    get_data, get_model, get_segments, poi_layer, require_dataset, segment_layer, walk_order)

require_dataset()
st.title("Daily forecast")
st.caption("What a park officer would see the evening before: tomorrow's crowding per trail segment and a recommended quota.")

data, seg, run = get_data(), get_segments(), default_run()
model_ok = run is not None and get_model(run) is not None

c1, c2, c3 = st.columns([1, 1, 1])
day = c1.date_input("Forecast date (test year 2025)", value=st.session_state.get("chosen_date", date(2025, 5, 12)),
                    min_value=date(2025, 1, 2), max_value=date(2025, 12, 31))
st.session_state["chosen_date"] = day          # shared with the Capacity page
use_weather = c2.toggle("Weather forecast available", value=model_ok, disabled=not model_ok,
                        help="Off = fallback mode (NFR2): no weather, historical average instead of the ST-GNN.")
show_actual = c3.toggle("Show what actually happened", value=True,
                        help="2025 is the test year, so the simulated headcount is known and can be compared.")
if not model_ok:
    st.warning("No trained ST-GNN on this machine (checkpoints are not committed). Showing the historical-average "
               "fallback. Run `python -m src.run_benchmark --protocol temporal` to create one.")

fc = forecast(day.isoformat(), use_weather and model_ok, run or "")
cal = calendar().loc[pd.Timestamp(day)]
tags = [n for n, f in [("Weekend", cal.is_weekend), ("Poya day", cal.is_poya), ("Public holiday", cal.is_holiday),
                       ("Long weekend", cal.is_long_weekend), ("School holidays", cal.is_school_holiday)] if f]
name = cal.holiday_name if isinstance(cal.holiday_name, str) and cal.holiday_name else ""
st.markdown(f"**{day:%A %d %B %Y}** · {', '.join(tags) or 'Ordinary weekday'}"
            f"{' · ' + name if name else ''} · rain in {fc['trail_correction_factors']['precipitation']:.0%} of open hours"
            f" · source: `{fc['source']['model']}`")

segs = pd.DataFrame(fc["segments"])
n_bottle = int((segs.status == "bottleneck").sum())
k = st.columns(5)
k[0].metric("Expected visitors", f"{fc['expected_visitors']:,}", help="From the calendar: same day type and month in 2022–23")
k[1].metric("Recommended quota", f"{fc['recommended_daily_quota']:,}",
            f"{fc['recommended_daily_quota'] - fc['expected_visitors']:+,} vs expected")
k[2].metric("Classic Cifuentes quota", f"{fc['classic_cifuentes_quota']:,}", help="Same method without the forecast")
lim = seg.set_index("seg_id").loc[fc["limiting_segment"], "label"]
k[3].metric("Limiting segment", lim)
k[4].metric("Bottleneck segments", n_bottle)
if fc["recommended_daily_quota"] < fc["expected_visitors"]:
    st.warning(f"Expected demand is above the recommended quota by "
               f"{fc['expected_visitors'] - fc['recommended_daily_quota']:,} visitors. Options: cap ticket sales, "
               f"spread entry times, or (planned) offer the Kirigalpotta / Thotupola trails.", icon=":material/warning:")

left, right = st.columns([1.1, 1])
with left:
    st.subheader("Where it gets crowded")
    colors = [STATUS_COLOR[s] for s in segs.status]
    extra = [{"status": s.status, "peak": s.peak_occupancy, "hour": f"{s.peak_hour:02d}:00",
              "holds": s.capacity_at_once} for s in segs.itertuples()]
    layers = [segment_layer(seg, colors, extra)] + extension_layers() + [poi_layer(seg)]
    st.pydeck_chart(deck(layers, "<b>{name}</b><br/>{status}<br/>peak {peak} people at {hour}<br/>"
                                 "holds {holds} at social spacing"), height=460)
    st.caption("Green = fine · amber = busy (≥ 80 % of what the segment holds) · red = bottleneck "
               "(over the limit for at least one hour) · blue = alternative trails (planned diversion)")

with right:
    st.subheader("Hour by hour")
    order = walk_order()
    labels = seg.set_index("seg_id").label
    hours = list(range(6, 19))
    heat = pd.DataFrame([{"segment": labels[r["seg_id"]], "hour": h, "people": r["forecast_hourly"][h],
                          "pos": order.index(r["seg_id"])} for r in fc["segments"] for h in hours])
    chart = alt.Chart(heat).mark_rect().encode(
        x=alt.X("hour:O", title="Hour"),
        y=alt.Y("segment:N", sort=alt.EncodingSortField("pos"), title="Segment (walking order)"),
        color=alt.Color("people:Q", scale=alt.Scale(scheme="orangered"), title="People"),
        tooltip=["segment", "hour", alt.Tooltip("people:Q", format=".0f")]).properties(height=460)
    st.altair_chart(chart, width="stretch")

st.subheader("One segment in detail")
names = [labels[i] for i in order]
default = names.index(next(n for n in names if "World's End" in n and "Mini" not in n))
pick = st.selectbox("Segment", names, index=default)
sid = int(pick[:2])
row = segs.set_index("seg_id").loc[sid]
origin = int(np.searchsorted(data.times, pd.Timestamp(day)))
df = pd.DataFrame({"hour": range(24), "Forecast": row.forecast_hourly})
if show_actual:
    df["Simulated headcount"] = data.y[origin:origin + 24, sid]
long = df.melt("hour", var_name="series", value_name="people")
line = alt.Chart(long).mark_line(point=True).encode(
    x=alt.X("hour:Q", scale=alt.Scale(domain=[5, 19]), title="Hour"), y=alt.Y("people:Q", title="People"),
    color=alt.Color("series:N", scale=alt.Scale(range=["#1b7f5a", "#222222"]), title=None))
rule = alt.Chart(pd.DataFrame({"y": [row.capacity_at_once]})).mark_rule(strokeDash=[6, 4], color="#c0392b").encode(y="y")
st.altair_chart((line + rule).properties(height=280), width="stretch")
st.caption(f"Dashed red line: {row.capacity_at_once:.0f} people, what this segment holds at Cifuentes social spacing.")

st.subheader("Busy and bottleneck segments")
busy = segs[segs.status != "ok"].copy()
busy["segment"] = busy.seg_id.map(labels)
busy["peak hour"] = busy.peak_hour.map(lambda h: f"{h:02d}:00")
st.dataframe(busy.sort_values("utilisation", ascending=False)[
    ["segment", "status", "peak_occupancy", "peak hour", "capacity_at_once", "utilisation", "crowded_hours_share",
     "ecc_per_day"]], hide_index=True, width="stretch")

st.info(fc["disclaimer"], icon=":material/info:")
st.download_button("Download forecast JSON (format read by Module 3 and the dashboard)",
                   json.dumps(fc, indent=2), file_name=f"forecast_{day.isoformat()}.json", mime="application/json")
