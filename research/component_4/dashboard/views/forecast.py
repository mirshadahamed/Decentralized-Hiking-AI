import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import altair as alt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from common import (STATUS_COLOR, calendar, deck, default_run, forecast, get_data, get_model,  # noqa: E402
                    get_segments, poi_layer, require_dataset, road_link_layer, segment_layer, walk_order)

require_dataset()
st.title("Daily forecast")
st.caption("What a park officer would see the evening before: tomorrow's crowding on every trail segment "
           "and a recommended quota per trail. For dates further ahead, use *Plan a visit*.")

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
    st.warning("No ST-GNN trained on the current trail network on this machine. Showing the historical-average "
               "fallback. Run `python -m src.run_benchmark --protocol temporal` to train one.")

fc = forecast(day.isoformat(), use_weather and model_ok, run or "")
cal = calendar().loc[pd.Timestamp(day)]
tags = [n for n, f in [("Weekend", cal.is_weekend), ("Poya day", cal.is_poya), ("Public holiday", cal.is_holiday),
                       ("Long weekend", cal.is_long_weekend), ("School holidays", cal.is_school_holiday)] if f]
name = cal.holiday_name if isinstance(cal.holiday_name, str) and cal.holiday_name else ""
st.markdown(f"**{day:%A %d %B %Y}** · {', '.join(tags) or 'Ordinary weekday'}"
            f"{' · ' + name if name else ''} · rain in {fc['rain_share_open_hours']:.0%} of open hours"
            f" · source: `{fc['source']['model']}`")

k = st.columns(3)
k[0].metric("Expected visitors (park)", f"{fc['expected_visitors']:,}",
            help="From the calendar: same day type and month in 2022–23")
k[1].metric("Recommended quota (park)", f"{fc['recommended_daily_quota']:,}",
            f"{fc['recommended_daily_quota'] - fc['expected_visitors']:+,} vs expected")
k[2].metric("Classic Cifuentes quota (park)", f"{fc['classic_cifuentes_quota']:,}", help="Same method without the forecast")

labels = seg.set_index("seg_id").label
rows = []
for v in fc["trails"].values():
    rows.append({"trail": v["name"], "expected": v["expected_visitors"], "quota": v["recommended_daily_quota"],
                 "room left": v["headroom"], "bottleneck segments": v["bottleneck_segments"],
                 "busiest segment peak": v["peak_occupancy"], "limiting segment": labels[v["limiting_segment"]]})
tr = pd.DataFrame(rows)
st.dataframe(tr, hide_index=True, width="stretch")
main = fc["trails"]["main"]
if main["headroom"] < 0:
    spare = [f"{v['name']} ({v['headroom']:,} places)" for t, v in fc["trails"].items() if t != "main" and v["headroom"] > 0]
    st.warning(f"The World's End loop is {-main['headroom']:,} visitors over its quota. "
               + (f"Room left on: {', '.join(spare)}: offer these at the ticket counter." if spare else ""),
               icon=":material/warning:")

segs = pd.DataFrame(fc["segments"])
left, right = st.columns([1.1, 1])
with left:
    st.subheader("Where it gets crowded")
    colors = [STATUS_COLOR[s] for s in segs.status]
    extra = [{"status": s.status, "peak": s.peak_occupancy, "hour": f"{s.peak_hour:02d}:00",
              "holds": s.capacity_at_once} for s in segs.itertuples()]
    layers = [road_link_layer(seg), segment_layer(seg, colors, extra), poi_layer(seg)]
    st.pydeck_chart(deck(layers, "<b>{name}</b><br/>{status}<br/>peak {peak} people at {hour}<br/>"
                                 "holds {holds} at social spacing"), height=480)
    st.caption("Green = fine · amber = busy (≥ 80 % of what the segment holds) · red = bottleneck "
               "(over the limit for at least one hour) · grey line = road link to the Thotupola trailhead")

with right:
    st.subheader("Hour by hour")
    order = walk_order()
    hours = list(range(6, 19))
    heat = pd.DataFrame([{"segment": labels[r["seg_id"]], "hour": h, "people": r["forecast_hourly"][h],
                          "pos": order.index(r["seg_id"])} for r in fc["segments"] for h in hours])
    chart = alt.Chart(heat).mark_rect().encode(
        x=alt.X("hour:O", title="Hour"),
        y=alt.Y("segment:N", sort=alt.EncodingSortField("pos"), title=None,
                axis=alt.Axis(labelFontSize=9)),
        color=alt.Color("people:Q", scale=alt.Scale(scheme="orangered"), title="People"),
        tooltip=["segment", "hour", alt.Tooltip("people:Q", format=".0f")]).properties(height=620)
    st.altair_chart(chart, width="stretch")

st.subheader("One segment in detail")
names = [labels[i] for i in order]
pick = st.selectbox("Segment", names, index=next(i for i, n in enumerate(names) if n.endswith("· World's End")))
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
if len(busy):
    busy["segment"] = busy.seg_id.map(labels)
    busy["peak hour"] = busy.peak_hour.map(lambda h: f"{h:02d}:00")
    st.dataframe(busy.sort_values("utilisation", ascending=False)[
        ["segment", "status", "peak_occupancy", "peak hour", "capacity_at_once", "utilisation", "crowded_hours_share",
         "ecc_per_day"]], hide_index=True, width="stretch")
else:
    st.success("No busy segments forecast for this day.")

st.info(fc["disclaimer"], icon=":material/info:")
st.download_button("Download forecast JSON (format read by Module 3 and the dashboard)",
                   json.dumps(fc, indent=2), file_name=f"forecast_{day.isoformat()}.json", mime="application/json")
