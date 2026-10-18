import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import altair as alt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from common import (control_day, deck, get_control, get_segments, latest_control_eval, poi_layer,  # noqa: E402
                    require_dataset, road_link_layer, segment_layer, trail_names, walk_order)

require_dataset()
st.title("Entry control")
st.caption("How overcrowding is *prevented*: tickets per trail and 30-minute entry slot, so that no segment is "
           "ever planned above its safe capacity. For park officers and the ticket counter.")

with st.expander("The logic in one paragraph", expanded=True):
    st.markdown(
        "We do not count people on the trail; we control **how many enter and when**. A ticket is a trail plus an "
        "entry time, so we know where its holder will be over the next hours (measured with the simulator). "
        "A linear programme sets the number of tickets per slot so that, for **every segment and every half hour**, "
        "the expected number of people stays under the segment's safe capacity (Cifuentes social spacing × "
        "management capacity × rain), with a 10 % safety margin, and the trail's daily Cifuentes quota is respected. "
        "When a slot is full, visitors are offered a later slot, another trail with room, or another day "
        "(*Book a slot* does this weeks in advance). During the day, scanned tickets give a live estimate per "
        "segment (traffic lights) without any trail sensors.")

names = trail_names()
ec = get_control()
c1, c2 = st.columns(2)
day = c1.date_input("Day (test year 2025)", value=st.session_state.get("chosen_date", date(2025, 5, 12)),
                    min_value=date(2025, 1, 1), max_value=date(2025, 12, 31))
st.session_state["chosen_date"] = day
scale = c2.select_slider("Capacity standard (× Cifuentes)", options=[1.0, 1.5, 2.0, 3.0, 4.0], value=1.0,
                         help="DWC's choice. 1 = strict Cifuentes spacing (groups of 10, 50 m apart, MC 0.7). "
                              "Higher = more people allowed at once.")
res = control_day(day.isoformat(), scale)
plan = res["plan"]

# ---------- ticket table ----------
st.subheader("Tickets per entry slot")
k = st.columns(4)
k[0].metric("Visitors who want to come", f"{res['wanted']:,.0f}")
k[1].metric("Tickets issued", f"{int(plan.values.sum()):,}")
k[2].metric("Rain in open hours", f"{res['rain_share']:.0%}", help="Fewer tickets on wet days (slower, slippery)")
k[3].metric("Bookable / walk-in", f"{1 - ec.c['walk_in_share']:.0%} / {ec.c['walk_in_share']:.0%}")
t = plan.rename(columns=names).reset_index(names="slot").melt("slot", var_name="trail", value_name="tickets")
st.altair_chart(alt.Chart(t).mark_rect().encode(
    x=alt.X("slot:O", title="Entry slot"), y=alt.Y("trail:N", title=None),
    color=alt.Color("tickets:Q", scale=alt.Scale(scheme="greens"), title="Tickets"),
    tooltip=["trail", "slot", "tickets"]).properties(height=150)
    + alt.Chart(t).mark_text(fontSize=11).encode(x="slot:O", y="trail:N", text="tickets:Q"), width="stretch")
st.caption("Daily totals: " + " · ".join(f"{names[c]} {int(plan[c].sum())} (Cifuentes quota {res['quota'][c]:.0f})"
                                         for c in plan.columns))

# ---------- before / after ----------
st.subheader("The same visitors, without and with slot tickets")
seg = get_segments()
labels = seg.set_index("seg_id").label
names_order = [labels[i] for i in walk_order()]
pick = st.selectbox("Segment", names_order, index=next(i for i, n in enumerate(names_order) if n.endswith("· World's End")))
sid = int(pick[:2])
bins = np.arange(ec.n_bins) * ec.c["bin_minutes"] / 60
df = pd.DataFrame({"hour": bins, "No limit": res["A"]["occ"][sid], "Slot tickets + moving": res["D"]["occ"][sid]})
long = df.melt("hour", var_name="policy", value_name="people")
cap = res["capacity"][sid]
lines = alt.Chart(long).mark_line(point=True).encode(
    x=alt.X("hour:Q", scale=alt.Scale(domain=[5.5, 18]), title="Hour"), y=alt.Y("people:Q", title="People on segment"),
    color=alt.Color("policy:N", scale=alt.Scale(range=["#c0392b", "#1b7f5a"]), title=None))
chart = lines + (alt.Chart(pd.DataFrame({"y": [cap]})).mark_rule(strokeDash=[6, 4]).encode(y="y")
                 if np.isfinite(cap) else lines)
st.altair_chart(chart.properties(height=280), width="stretch")
fin = np.isfinite(res["capacity"])
over = {p: float(np.clip(res[p]["occ"][fin] - res["capacity"][fin, None], 0, None).sum() * ec.c["bin_minutes"] / 60)
        for p in ("A", "D")}
d = res["D"]
k = st.columns(4)
k[0].metric("Person-hours over capacity", f"{over['D']:,.0f}", f"{over['D'] - over['A']:+,.0f} vs no limit",
            delta_color="inverse")
k[1].metric("Admitted", f"{d['admitted']:,.0f}", f"{d['admitted'] / res['wanted']:.0%} of demand", delta_color="off")
k[2].metric("Moved to a later slot / other trail", f"{d['moved_slot']:,.0f} / {d['moved_trail']:,.0f}")
k[3].metric("Offered another day", f"{d['refused']:,.0f}")
st.caption("Dashed line: safe capacity of the segment at this standard. Red: everyone walks when they like.")

# ---------- live gate view ----------
st.subheader("At the gate: live estimate from scanned tickets")
now_h = st.slider("Time now", 6.0, 16.0, 8.5, 0.5, format="%.1f h")
now = int(now_h * 60)
occ_now = ec.nowcast(res["D"]["groups"], now, res["rain_share"])
C = res["capacity"]
util = np.where(np.isfinite(C), occ_now / np.where(np.isfinite(C), C, 1), 0)
status = np.where(util > 1, "red", np.where(util >= 0.8, "amber", "green"))
col = {"green": [46, 139, 87], "amber": [224, 161, 0], "red": [192, 57, 43]}
extra = [{"status": s, "people": f"{o:.0f}", "cap": "—" if not np.isfinite(c) else f"{c:.0f}"}
         for s, o, c in zip(status, occ_now, C)]
left, right = st.columns([1.2, 1])
with left:
    st.pydeck_chart(deck([road_link_layer(seg), segment_layer(seg, [col[s] for s in status], extra), poi_layer(seg)],
                         "<b>{name}</b><br/>{status}: ~{people} people (capacity {cap})"), height=420)
with right:
    scanned = res["D"]["groups"]
    scanned = scanned[scanned.gate_min <= now]
    st.metric(f"Scanned in by {now_h:04.1f} h", f"{scanned['size'].sum():,.0f} people")
    act = pd.DataFrame({"segment": [labels[i] for i in range(len(seg))], "status": status,
                        "people now": occ_now.round(0), "capacity": np.round(C, 0)})
    act = act[act.status != "green"].sort_values("people now", ascending=False)
    if len(act):
        act["action"] = act.status.map({"amber": "offer later slot / other trail at the gate",
                                        "red": "pause entries to this trail for the next slot; ranger to the platform"})
        st.dataframe(act, hide_index=True, width="stretch")
    else:
        st.success("All segments green: no action needed.")
st.caption("Estimated from scan times and trails only. In production: corrected by exit scans and ranger counts.")

# ---------- whole year ----------
st.subheader("Does it work? The whole test year (simulation)")
ev = latest_control_eval()
if ev is None:
    st.info("Run `python -m src.control.evaluate --sweep` to fill this section.")
else:
    s = pd.read_csv(ev / "summary.csv")
    st.dataframe(s.round(1).rename(columns={
        "person_hours_over_capacity": "person-hours over capacity", "days_overcrowded": "days with any overcrowding",
        "mean_peak_worlds_end": "avg World's End peak", "mean_peak_focus": "avg peak at the busiest place",
        "admitted_pct": "admitted %", "moved_slot_pct": "moved slot %",
        "moved_trail_pct": "moved trail %", "refused_pct": "another day %"}), hide_index=True, width="stretch")
    a = s.person_hours_over_capacity.iloc[0]
    tests = json.loads((ev / "tests.json").read_text(encoding="utf-8"))
    st.markdown(f"Slot tickets with moving remove **{1 - s.person_hours_over_capacity.iloc[-1] / a:.1%}** of the "
                f"person-hours over capacity compared with no limit (Wilcoxon p = {tests['D']['wilcoxon_p_vs_A']:.0e}); "
                f"a daily quota alone removes {1 - s.person_hours_over_capacity.iloc[1] / a:.0%} but leaves the morning peak.")
    if (ev / "capacity_sweep.csv").exists():
        sw = pd.read_csv(ev / "capacity_sweep.csv")
        st.markdown("**Choosing the capacity standard** (trade-off for DWC):")
        st.altair_chart(alt.Chart(sw).mark_line(point=True, color="#1b7f5a").encode(
            x=alt.X("capacity_scale:Q", title="Capacity standard (× strict Cifuentes)"),
            y=alt.Y("admitted_pct_D:Q", title="% of visitors admitted", scale=alt.Scale(domain=[50, 100])),
            tooltip=["capacity_scale", alt.Tooltip("admitted_pct_D:Q", format=".1f"),
                     alt.Tooltip("reduction_pct:Q", format=".1f", title="overcrowding prevented %")])
            .properties(height=220), width="stretch")
        st.caption("At every standard, slot tickets prevent "
                   f"{sw.reduction_pct.min():.0f}–{sw.reduction_pct.max():.0f} % of the overcrowding (measured against "
                   "that standard). The standard only decides how many people get in.")

st.info("All numbers come from the simulator and placeholder capacity parameters. Confirm the capacity standard, "
        "viewpoint platform sizes and management capacity with DWC.", icon=":material/info:")
