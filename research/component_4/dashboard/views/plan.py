import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import altair as alt  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from common import (STATUS_COLOR, deck, get_data, get_segments, latest_planning_backtest, plan_day,  # noqa: E402
                    plan_outlook, poi_layer, require_dataset, road_link_layer, segment_layer, trail_names,
                    walk_order)

require_dataset()
st.title("Plan a visit")
st.caption("Expected crowd for any day up to 90 days ahead, with suggestions to avoid it. "
           "Uses the calendar, typical weather for the time of year and recent visitor numbers.")

LEVEL = {1: "Very quiet", 2: "Quiet", 3: "Moderate", 4: "Busy", 5: "Very busy"}
LEVEL_COLOR = ["#2e8b57", "#8bbf5a", "#e0c341", "#e08a2c", "#c0392b"]
ICON = {"date": ":material/event:", "later": ":material/schedule:", "reverse": ":material/u_turn_left:",
        "trail": ":material/hiking:"}

c1, c2 = st.columns(2)
issue = c1.date_input("Pretend today is", value=st.session_state.get("plan_issue", date(2025, 3, 1)),
                      min_value=date(2025, 1, 1), max_value=date(2025, 12, 29),
                      help="2025 is the test year: the model never saw it, and what really happened is known, "
                           "so the plan can be checked.")
st.session_state["plan_issue"] = issue
last = min(issue + timedelta(days=90), date(2025, 12, 31))
default_target = st.session_state.get("plan_target", date(2025, 5, 12))
if not issue + timedelta(days=2) <= default_target <= last:
    default_target = issue + timedelta(days=14)
target = c2.date_input("Day you want to visit", value=default_target,
                       min_value=issue + timedelta(days=2), max_value=last,
                       help="For tomorrow, use the Daily forecast page (it uses yesterday's counts and the weather forecast).")
st.session_state["plan_target"] = target

ol = plan_outlook(issue.isoformat())
plan = plan_day(issue.isoformat(), target.isoformat())
data = get_data()

# ---------- outlook strip ----------
st.subheader(f"Next 90 days from {issue:%d %b %Y}")
o = ol.reset_index(names="day")
o["level"] = o.crowd_level.map(LEVEL)
o["selected"] = o.day == pd.Timestamp(target)
base = alt.Chart(o).encode(x=alt.X("day:T", title=None))
bars = base.mark_bar().encode(
    y=alt.Y("p50:Q", title="Expected visitors (park)"),
    color=alt.Color("crowd_level:O", scale=alt.Scale(domain=[1, 2, 3, 4, 5], range=LEVEL_COLOR),
                    legend=alt.Legend(title="Crowd level", labelExpr="['','Very quiet','Quiet','Moderate','Busy','Very busy'][datum.value]")),
    opacity=alt.condition("datum.selected", alt.value(1.0), alt.value(0.75)),
    tooltip=[alt.Tooltip("day:T", format="%a %d %b"), "level",
             alt.Tooltip("p50:Q", format=",.0f", title="likely"), alt.Tooltip("p10:Q", format=",.0f", title="low"),
             alt.Tooltip("p90:Q", format=",.0f", title="high")])
band = base.mark_rule(color="#555", opacity=0.5).encode(y="p10:Q", y2="p90:Q")
mark = alt.Chart(o[o.selected]).mark_point(shape="triangle-down", size=120, color="black", filled=True).encode(
    x="day:T", y=alt.Y("p90:Q"))
st.altair_chart((bars + band + mark).properties(height=230), width="stretch")
st.caption("Bars = likely number of visitors; grey lines = range (P10–P90, should contain the real number on about "
           "8 of 10 days); ▼ = the day you picked.")

# ---------- the chosen day ----------
st.subheader(f"{target:%A %d %B %Y} · {plan['lead_days']} days ahead")
v = plan["visitors"]
k = st.columns(4)
k[0].metric("Expected visitors", f"~{v['p50']:,}", help=f"Range {v['p10']:,} – {v['p90']:,}")
k[1].metric("Range", f"{v['p10']:,} – {v['p90']:,}")
k[2].metric("Crowd level", f"{plan['crowd_level']} / 5 · {LEVEL[plan['crowd_level']]}")
k[3].metric("Chance of a wet morning", f"{plan['chance_wet_morning']:.0%}")
st.caption(f"Confidence: {plan['confidence']}.")

names = trail_names()
cap = plan["capacity"]["trails"]
st.dataframe(pd.DataFrame([{
    "trail": names[t], "likely visitors": plan["visitors_by_trail"][t]["p50"],
    "range": f"{plan['visitors_by_trail'][t]['p10']:,} – {plan['visitors_by_trail'][t]['p90']:,}",
    "recommended quota": cap[t]["recommended_daily_quota"], "room left": cap[t]["headroom"],
    "bottleneck segments": cap[t]["bottleneck_segments"]} for t in plan["visitors_by_trail"]]),
    hide_index=True, width="stretch")

st.subheader("Suggestions to avoid the crowd")
if plan["suggestions"]:
    cols = st.columns(min(3, len(plan["suggestions"])))
    for i, s in enumerate(plan["suggestions"]):
        with cols[i % len(cols)].container(border=True):
            st.markdown(f"**{s['title']}**")
            st.markdown(f":green[**{s['reduction_pct']} % fewer people**]")
            st.caption(s["detail"])
            st.caption(f"{ICON[s['kind']]} {s['kind']}")
else:
    st.success("A quiet day: no changes needed.")

# ---------- where and when ----------
seg = get_segments()
labels = seg.set_index("seg_id").label
left, right = st.columns([1.1, 1])
with left:
    st.markdown("**Where it gets crowded (likely case)**")
    segs = pd.DataFrame(plan["capacity"]["segments"])
    extra = [{"status": s.status, "peak": s.peak_occupancy, "hour": f"{s.peak_hour:02d}:00",
              "holds": s.capacity_at_once} for s in segs.itertuples()]
    layers = [road_link_layer(seg), segment_layer(seg, [STATUS_COLOR[s] for s in segs.status], extra), poi_layer(seg)]
    st.pydeck_chart(deck(layers, "<b>{name}</b><br/>{status}<br/>peak {peak} people at {hour}"), height=430)
with right:
    q = st.radio("Case", ["p10", "p50", "p90"], index=1, horizontal=True,
                 format_func={"p10": "Low", "p50": "Likely", "p90": "High"}.get)
    order = walk_order()
    occ = plan["hourly"][q]
    heat = pd.DataFrame([{"segment": labels[s], "hour": h, "people": occ[h][s], "pos": order.index(s)}
                         for s in order for h in range(6, 19)])
    st.altair_chart(alt.Chart(heat).mark_rect().encode(
        x=alt.X("hour:O", title="Hour"),
        y=alt.Y("segment:N", sort=alt.EncodingSortField("pos"), title=None, axis=alt.Axis(labelFontSize=9)),
        color=alt.Color("people:Q", scale=alt.Scale(scheme="orangered"), title="People"),
        tooltip=["segment", "hour", alt.Tooltip("people:Q", format=".0f")]).properties(height=430), width="stretch")

# ---------- check against what happened ----------
with st.expander("Check: what actually happened that day (test year)"):
    ti = int((pd.Timestamp(target) - data.times[0]).days)
    actual = int(data.daily_visitors[ti])
    inside = v["p10"] <= actual <= v["p90"]
    st.markdown(f"Simulated visitors that day: **{actual:,}**. Forecast {plan['lead_days']} days earlier: "
                f"~{v['p50']:,} (range {v['p10']:,} – {v['p90']:,}): "
                + ("inside the range ✅" if inside else "outside the range ❌"))
    bt = latest_planning_backtest()
    if bt is not None:
        m = pd.read_csv(bt / "metrics_by_lead.csv")
        st.markdown("**Accuracy over the whole test year, by how far ahead** (planning model vs historical average):")
        st.dataframe(m.rename(columns={
            "lead_days": "days ahead", "visitors_MAE_planning": "visitors MAE (planning)",
            "visitors_MAE_hist_avg": "visitors MAE (hist. avg)", "coverage_P10_P90": "inside range",
            "occupancy_MAE_planning": "crowd per segment-hour MAE (planning)",
            "occupancy_MAE_hist_avg": "crowd per segment-hour MAE (hist. avg)"}).round(3),
            hide_index=True, width="stretch")
        occ_gain = 1 - m.occupancy_MAE_planning.mean() / m.occupancy_MAE_hist_avg.mean()
        vis_gain = 1 - m.visitors_MAE_planning.mean() / m.visitors_MAE_hist_avg.mean()
        tests = json.loads((bt / "tests.json").read_text(encoding="utf-8"))
        p_occ = max(t["occupancy"]["p"] for t in tests.values())
        p_vis = min(t["visitors"]["p"] for t in tests.values())
        st.caption(f"Daily totals: {-vis_gain:+.0%} error vs historical average (smallest p = {p_vis:.2f}: not significant; "
                   f"the calendar explains most of it). Where and when people are: {occ_gain:.0%} lower error on "
                   f"average (p ≤ {p_occ:.1e} at every lead time).")

st.info("Estimates come from a model trained on a **simulated** visitor history. Real DWC ticket counts are "
        "needed before using this with the public.", icon=":material/info:")
st.download_button("Download plan JSON", json.dumps(plan, indent=2),
                   file_name=f"plan_{issue.isoformat()}_{target.isoformat()}.json", mime="application/json")
