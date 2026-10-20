import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import altair as alt  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from common import get_control, plan_outlook, require_dataset, trail_names  # noqa: E402
from src.control import booking as bk  # noqa: E402

require_dataset()
st.title("Book a slot")
st.caption("Reserve an entry time on a trail up to 90 days ahead, so you know you will get in before you travel.")

names = trail_names()
ec = get_control()
H = ec.c["booking_horizon_days"]

c1, c2, c3, c4 = st.columns([1, 1, 1, 0.7])
today = c1.date_input("Today is", value=st.session_state.get("plan_issue", date(2025, 3, 1)),
                      help="Demo: pick a 'today' in 2025 to see the crowd forecast next to availability.")
day = c2.date_input("Day of your visit", value=max(today + timedelta(days=1),
                                                   st.session_state.get("book_day", today + timedelta(days=14))),
                    min_value=today + timedelta(days=1), max_value=today + timedelta(days=H))
st.session_state["book_day"] = day
trail = c3.selectbox("Trail", list(names), format_func=names.get)
size = c4.number_input("Group size", 1, 20, 2)

avail = bk.availability(day.isoformat())
supply = bk.supply(day.isoformat())
expected = None
try:                                                      # crowd forecast, if the day is inside the demo data
    ol = plan_outlook(today.isoformat())
    if pd.Timestamp(day) in ol.index:
        row = ol.loc[pd.Timestamp(day)]
        expected = {t: float(row[f"{t}_p90"]) for t in names}
except (ValueError, KeyError):
    pass

st.subheader(f"Places left on {day:%A %d %B %Y}")
grid = avail.rename(columns=names).reset_index(names="slot").melt("slot", var_name="trail", value_name="left")
grid["status"] = pd.cut(grid.left, [-1, 0, size - 1, 5, 10_000], labels=["full", "too few", "few left", "available"])
st.altair_chart(alt.Chart(grid).mark_rect().encode(
    x=alt.X("slot:O", title="Entry slot"), y=alt.Y("trail:N", title=None),
    color=alt.Color("status:N", scale=alt.Scale(domain=["full", "too few", "few left", "available"],
                                                range=["#c0392b", "#e08a2c", "#e0c341", "#2e8b57"]), title=None),
    tooltip=["trail", "slot", "left"]).properties(height=150)
    + alt.Chart(grid).mark_text(fontSize=11, color="white").encode(x="slot:O", y="trail:N", text="left:Q"),
    width="stretch")
if expected:
    risk = []
    for t in names:
        bookable = supply[t].sum()
        wanted = expected[t] * (1 - ec.c["walk_in_share"])
        if wanted > bookable:
            risk.append(f"**{names[t]}**: up to ~{wanted:,.0f} people may want to book {bookable:,} places")
    if risk:
        st.warning("Likely to sell out: " + "; ".join(risk) + ". Book early.", icon=":material/schedule:")
st.caption(f"{ec.c['walk_in_share']:.0%} of every slot is kept for visitors without a booking.")

open_slots = [s for s in avail.index if avail.loc[s, trail] >= size]
if not open_slots:
    st.error(f"No slot on {names[trail]} has room for {size} on this day.")
slot = st.selectbox("Entry slot", list(avail.index),
                    index=list(avail.index).index(open_slots[0]) if open_slots else 0,
                    format_func=lambda s: f"{s}  ({avail.loc[s, trail]} left)")


def show_alternatives(alts):
    st.markdown("**Other options with room:**")
    cols = st.columns(min(3, max(1, len(alts))))
    for i, a in enumerate(alts):
        with cols[i % len(cols)].container(border=True):
            st.markdown(f"**{names[a['trail']]}**, {pd.Timestamp(a['day']):%a %d %b} at {a['slot']}")
            st.caption(f"{a['left']} places left · {dict(slot='another time', trail='another trail', day='another day')[a['kind']]}")
            if st.button("Book this", key=f"alt{i}"):
                try:
                    st.session_state["last_code"] = bk.book(a["day"], a["trail"], a["slot"], size, today.isoformat())
                    st.rerun()
                except (bk.SlotFull, ValueError) as e:
                    st.error(str(e))


if st.button(f"Book {size} place(s) on {names[trail]} at {slot}", type="primary"):
    try:
        st.session_state["last_code"] = bk.book(day.isoformat(), trail, slot, size, today.isoformat())
    except bk.SlotFull as e:
        st.error(str(e))
        show_alternatives(e.alternatives)
    except ValueError as e:
        st.error(str(e))

if "last_code" in st.session_state:
    code = st.session_state["last_code"]
    b = bk.bookings_for_code(code)
    if b:
        st.success(f"Booked. Your code: **{code}**. {names[b['trail']]}, {pd.Timestamp(b['day']):%A %d %B} at "
                   f"{b['slot']}, {b['group_size']} people. Show the code at the gate between "
                   f"{(datetime.fromisoformat(b['day'] + 'T' + b['slot']) - timedelta(minutes=ec.c['slot_window_min'])):%H:%M} "
                   f"and {(datetime.fromisoformat(b['day'] + 'T' + b['slot']) + timedelta(minutes=ec.c['slot_window_min'])):%H:%M}.",
                   icon=":material/confirmation_number:")

st.divider()
left, right = st.columns(2)
with left:
    st.subheader("My booking")
    code_in = st.text_input("Booking code", key="manage_code")
    if code_in:
        b = bk.bookings_for_code(code_in)
        if not b:
            st.error("Unknown code")
        else:
            st.write(f"{names[b['trail']]}, {b['day']} at {b['slot']}, {b['group_size']} people: **{b['status']}**")
            if b["status"] == "booked" and st.button("Cancel this booking"):
                bk.cancel(code_in.strip().upper())
                st.rerun()
with right:
    st.subheader("Gate check (ranger)")
    g_code = st.text_input("Code shown by the visitor", key="gate_code")
    g1, g2 = st.columns(2)
    g_day = g1.date_input("Date", value=day, key="gate_day")
    g_time = g2.time_input("Time", value=time(7, 0), key="gate_time", step=300)
    if g_code and st.button("Check in"):
        r = bk.check_in(g_code, datetime.combine(g_day, g_time))
        (st.success if r["ok"] else st.error)(r["reason"]
                                              + (f": {names[r['trail']]} {r['slot']}, {r['group_size']} people"
                                                 if "trail" in r else ""))

with st.expander("About this booking demo"):
    st.markdown("- Places per slot come from the entry-control plan for that day (see *Entry control*); days beyond "
                "the weather forecast use typical rain for the time of year.\n"
                "- No personal data is stored: only a random code, the day, trail, slot and group size (NFR5).\n"
                "- Bookings are kept in `data/bookings.sqlite` on this computer. In production this would be the "
                "park's ticket system, synced to the gate device for offline checking.")
    if st.button("Delete all demo bookings"):
        bk.DB.unlink(missing_ok=True)
        st.session_state.pop("last_code", None)
        st.rerun()
