import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import altair as alt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from common import (TRAIL_COLOR, calendar, deck, get_data, get_segments, gradient, poi_layer,  # noqa: E402
                    require_dataset, road_link_layer, segment_layer, summary, trail_names)

require_dataset()
st.title("Trail and data")
st.caption("The graph the model learns on: three trails that share the park entrance, and the open data behind it.")

seg, data, names = get_segments(), get_data(), trail_names()
ATTR = {"Trail": "trail", "Elevation (m)": "elev_mean", "Mean |grade|": "grade_abs_mean",
        "DEM slope (°)": "slope_deg_mean", "Wetness index (TWI)": "twi_mean",
        "Walking time, standard direction (min)": "tobler_fwd_min", "Length (m)": "length_m"}
attr = st.selectbox("Colour segments by", list(ATTR))
col = ATTR[attr]
if col == "trail":
    colors = [TRAIL_COLOR[t] for t in seg.trail]
    extra = [{"value": names[t], "length": f"{m:.0f}"} for t, m in zip(seg.trail, seg.length_m)]
else:
    colors = gradient(seg[col])
    extra = [{"value": f"{v:.2f}", "length": f"{m:.0f}"} for v, m in zip(seg[col], seg.length_m)]
layers = [road_link_layer(seg), segment_layer(seg, colors, extra), poi_layer(seg)]
st.pydeck_chart(deck(layers, "<b>{name}</b><br/>" + attr + ": {value}<br/>length {length} m"), height=500)
s = summary().get("segments_by_trail", {})
st.caption(f"{data.N} segment nodes and {data.edge_index.shape[1] // 2} edges (segments that touch, plus the road link "
           f"to the Thotupola trailhead with half weight). "
           + " · ".join(f"{names[t]}: {n} segments" for t, n in s.items())
           + (". Trail colours: green = World's End loop, blue = Kirigalpotta, orange = Thotupola."
              if col == "trail" else ". Light = low, dark red = high."))

st.subheader("Segment features (model inputs that never change)")
table = seg.drop(columns="geometry").iloc[data.walk_order()]
cols = ["label", "length_m", "elev_mean", "grade_abs_mean", "slope_deg_mean", "twi_mean", "tobler_fwd_min",
        "tobler_bwd_min", "frac_grade_med", "frac_grade_high", "frac_wet"]
st.dataframe(table[cols].round(2), hide_index=True, width="stretch")

st.subheader("Weather and calendar")
cal = calendar()
months = pd.period_range(cal.index.min(), cal.index.max(), freq="M")
m = st.select_slider("Month", options=[str(p) for p in months], value="2025-05")
idx = pd.Series(range(data.T), index=data.times)
sel = idx[str(m)].values
names = data.cov_names
daily = pd.DataFrame({
    "day": data.times[sel][::24],
    "rain (mm)": np.expm1(data.cov[sel, names.index("precip_log1p")]).reshape(-1, 24).sum(1),
    "mean temperature (°C)": data.cov[sel, names.index("temperature_2m")].reshape(-1, 24).mean(1),
})
base = alt.Chart(daily).encode(x=alt.X("day:T", title=None))
rain = base.mark_bar(color="#5b8bd0").encode(y=alt.Y("rain (mm):Q"))
temp = base.mark_line(color="#c0392b", point=True).encode(y=alt.Y("mean temperature (°C):Q"))
st.altair_chart(alt.layer(rain, temp).resolve_scale(y="independent").properties(height=260), width="stretch")
mc = cal.loc[str(m)]
special = mc[(mc.is_poya + mc.is_holiday + mc.is_long_weekend + mc.is_school_holiday) > 0]
if len(special):
    show = special.assign(day=special.index.strftime("%a %d %b"))[
        ["day", "holiday_name", "is_poya", "is_holiday", "is_long_weekend", "is_school_holiday"]]
    st.dataframe(show.fillna(""), hide_index=True, width="stretch")
st.caption("Weather: Open-Meteo archive (ERA5-based), one grid point for the park. Holidays and Poya days: "
           "`holidays` package (LK). School holidays are approximate.")
