import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import altair as alt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from common import DOCS, calendar, get_cfg, get_data, get_segments, require_dataset, summary, walk_order  # noqa: E402

require_dataset()
st.title("Occupancy simulator")
st.caption("No one counts hikers per trail segment, so the training target is simulated from documented assumptions.")

data, seg, cal, s, p = get_data(), get_segments(), calendar(), summary(), get_cfg()["simulator"]

st.markdown(
    "**How a simulated day works.** (1) Expected visitors = base × day type (weekday / weekend / holiday / **Poya**) "
    "× season × morning rain. (2) Visitors form small groups and arrive mostly 06:00–08:00. (3) Each group walks the "
    "loop segment by segment at **Tobler's hiking speed** for that slope, slower in rain and in crowds, and stops at "
    "Mini World's End, World's End and Baker's Falls. (4) People on each segment are averaged per hour, plus "
    "counting noise.")

k = st.columns(4)
k[0].metric("Visitors per year", f"{s.get('visitors_per_year', 0):,.0f}")
k[1].metric("Average day", f"{s.get('visitors_daily_mean', 0):,.0f}")
k[2].metric("Busiest day", f"{s.get('visitors_daily_max', 0):,}")
k[3].metric("Median loop time", f"{s.get('median_loop_hours', 0):.1f} h")

st.subheader("A day on one segment")
labels = seg.set_index("seg_id").label
names = [labels[i] for i in walk_order()]
c1, c2 = st.columns([1, 2])
pick = c1.selectbox("Segment", names, index=next(i for i, n in enumerate(names) if "World's End" in n and "Mini" not in n))
sid = int(pick[:2])
rain_day = pd.Series(np.expm1(data.cov[:, data.cov_names.index("precip_log1p")]).reshape(-1, 24)[:, 5:10].sum(1),
                     index=data.times[::24])
year = c2.select_slider("Year", options=["2022", "2023", "2024", "2025"], value="2023")
cy = cal.loc[year]
presets = {
    "Ordinary weekday": cy[(cy.dow == 2) & (cy.is_holiday == 0) & (cy.is_school_holiday == 0)].index[10],
    "Saturday": cy[(cy.dow == 5) & (cy.is_holiday == 0)].index[10],
    "Poya day": cy[cy.is_poya == 1].index[3],
    "Rainiest weekday morning": rain_day.loc[year][cy.dow.values < 5].idxmax(),
}
rows = []
for name, d in presets.items():
    i = int(np.searchsorted(data.times, d))
    rows += [{"day": f"{name} ({d:%d %b})", "hour": h, "people": float(data.y_true[i + h, sid])} for h in range(24)]
chart = alt.Chart(pd.DataFrame(rows)).mark_line(point=True).encode(
    x=alt.X("hour:Q", scale=alt.Scale(domain=[5, 19]), title="Hour"), y=alt.Y("people:Q", title="People on segment"),
    color=alt.Color("day:N", title=None), tooltip=["day", "hour", alt.Tooltip("people:Q", format=".0f")])
st.altair_chart(chart.properties(height=300), width="stretch")

st.subheader("Visitors per day, 2022–2025")
days = data.times[::24]
dt = np.where(cal.is_poya | cal.is_long_weekend, "Poya / long weekend",
              np.where(cal.is_weekend | cal.is_holiday, "Weekend / holiday", "Weekday"))
vd = pd.DataFrame({"day": days, "visitors": data.daily_visitors, "day type": dt})
vd["30-day mean"] = vd.visitors.rolling(30, center=True, min_periods=1).mean()
c1, c2 = st.columns([2, 1])
base = alt.Chart(vd).encode(x=alt.X("day:T", title=None))
c1.altair_chart((base.mark_point(size=8, opacity=0.35, color="#888").encode(y=alt.Y("visitors:Q", title="Visitors"))
                 + base.mark_line(color="#1b7f5a").encode(y="30-day mean:Q")).properties(height=280), width="stretch")
c2.altair_chart(alt.Chart(vd).mark_boxplot().encode(
    x=alt.X("day type:N", title=None, sort=["Weekday", "Weekend / holiday", "Poya / long weekend"]),
    y=alt.Y("visitors:Q", title="Visitors per day"), color=alt.Color("day type:N", legend=None)).properties(height=280),
    width="stretch")

st.subheader("Key parameters (configs/default.yaml)")
params = pd.DataFrame([
    ("Base visitors, ordinary weekday", p["base_daily_visitors"]),
    ("Poya / holiday multiplier", f"×{p['poya_multiplier']} / ×{p['holiday_multiplier']}"),
    ("Arrival peak", f"{p['arrival_early_share']:.0%} around {p['arrival_early_mean_h']:.1f} h"),
    ("Leisure walking factor (× Tobler)", p["leisure_speed_factor"]),
    ("Rain slowdown (light / heavy)", f"×{p['rain_light_speed']} / ×{p['rain_heavy_speed']}"),
    ("Crowd: density that halves speed", f"{p['crowd_rho0_per_m']} persons/m"),
    ("Dwell, World's End (median)", f"{p['dwell_minutes']['worlds_end'][0]} min"),
], columns=["Parameter", "Value"])
st.dataframe(params.astype(str), hide_index=True, width="stretch")

with st.expander("All assumptions, with reasons (docs/assumptions.md)"):
    st.markdown((DOCS / "assumptions.md").read_text(encoding="utf-8"))
st.warning("Known limitation: the forecasting models learn from this simulator, so they partly learn its rules. "
           "Field headcounts (after PP1) will be used to calibrate and check it.", icon=":material/warning:")
