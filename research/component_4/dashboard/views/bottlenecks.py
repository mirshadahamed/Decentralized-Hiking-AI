"""Authority dashboard: tomorrow's bottlenecks and safe numbers (proposal 4.3, Figure 2 'Authority dashboard -
dynamic permit capacity'). Reads exactly what Module 3 reads: the c4-module3-feed-1 JSON."""
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from common import (POI_LABEL, deck, default_run, forecast, get_cfg, get_model, get_segments,  # noqa: E402
                    poi_layer, require_dataset, segment_layer)

require_dataset()
from src.live.refresh import PUBLISHED  # noqa: E402
from src.serve.module3 import module3_feed  # noqa: E402

st.title("Bottlenecks and safe numbers")
st.caption("For park authorities: where and when each trail section is expected to be over what it holds safely, "
           "and the safe number of visitors per trail. Same data as the Module 3 feed (GET /module3/feed).")

cfg = get_cfg()
live = PUBLISHED / "forecast_tomorrow.json"
source = st.radio("Forecast", ["Tomorrow (live service)", "A day of the 2025 test year"], horizontal=True,
                  index=0 if live.exists() else 1)
if source.startswith("Tomorrow") and live.exists():
    fc = json.loads(live.read_text(encoding="utf-8"))
else:
    day = st.date_input("Date", value=st.session_state.get("chosen_date", date(2025, 5, 12)),
                        min_value=date(2025, 1, 2), max_value=date(2025, 12, 31))
    st.session_state["chosen_date"] = day
    run = default_run()
    fc = forecast(day.isoformat(), run is not None and get_model(run) is not None, run or "")
feed = module3_feed(fc, cfg)

c1, c2, c3 = st.columns(3)
c1.metric("Safe visitors", f"{feed['safe_visitors_per_day']:,}", help="Cifuentes ECC, sum over trails")
c2.metric("Expected visitors", f"{feed['expected_visitors']:,}")
c3.metric("Sections to avoid at some hour", sum(1 for s in feed["segments"] if s["avoid_hours"]))
st.caption(f"{feed['site']} · {feed['forecast_date']} · model: {feed['model']}")

hours = feed["open_hours"]
peak = max(hours, key=lambda h: sum(s["people_hourly"][h] / max(s["capacity_at_once"], 1e-9) for s in feed["segments"]))
hour = st.select_slider("Hour", options=hours, value=peak, format_func=lambda h: f"{h:02d}:00")

seg = get_segments().sort_values("seg_id").reset_index(drop=True)
by_id = {s["segment_id"]: s for s in feed["segments"]}
busy = feed["busy_utilisation"]


def colour(u):
    return [198, 40, 40] if u > 1 else [239, 108, 0] if u >= busy else [249, 168, 37] if u >= busy / 2 else [46, 125, 50]


util = [by_id[i]["people_hourly"][hour] / max(by_id[i]["capacity_at_once"], 1e-9) for i in seg.seg_id]
extra = [{"people": round(by_id[i]["people_hourly"][hour]), "holds": round(by_id[i]["capacity_at_once"]),
          "pct": f"{100 * u:.0f}"} for i, u in zip(seg.seg_id, util)]
st.pydeck_chart(deck([segment_layer(seg, [colour(u) for u in util], extra, width=8), poi_layer(seg)],
                     "<b>{name}</b><br/>{people} people / holds {holds} ({pct} %)"))
st.caption("Green quiet · yellow filling up · orange busy · red over what the section holds at Cifuentes spacing "
           "(groups of 10, 50 m apart).")

st.subheader("Safe number per trail")
st.dataframe(pd.DataFrame([{
    "Trail": t["name"], "Safe visitors": t["safe_visitors_per_day"], "Expected": t["expected_visitors"],
    "Headroom": t["safe_visitors_per_day"] - t["expected_visitors"],
    "Set by section": seg.set_index("seg_id").label.get(t["limiting_segment_id"], t["limiting_segment_id"]),
    "Bottleneck sections": t["bottleneck_segments"],
} for t in feed["trails"]]), hide_index=True, width="stretch")

st.subheader("Sections to avoid, and when")
rows = [{"Section": seg.set_index("seg_id").label[s["segment_id"]], "Place": s["place"] or "",
         "Avoid": ", ".join(f"{h:02d}:00" for h in s["avoid_hours"]), "Busiest": f"{s['peak_hour']:02d}:00",
         "Peak people": round(max(s["people_hourly"])), "Holds at once": round(s["capacity_at_once"]),
         "Safe visits/day (ECC)": s["safe_visits_per_day"], "Status": s["status"]}
        for s in feed["segments"] if s["avoid_hours"]]
if rows:
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
else:
    st.success("No section is expected to be busy.")

st.subheader("Crowded and damaged (Module 2)")
st.caption("Proposal 4.3: cross-reference with Module 2's trail-damage output to flag sections that are both "
           "high-traffic and high-damage. Upload Module 2's CSV (segment_id, damage 0-1) when it is available.")
up = st.file_uploader("Module 2 damage scores (CSV)", type="csv")
if up is not None:
    dmg = pd.read_csv(up)
    both = dmg.merge(pd.DataFrame([{"segment_id": s["segment_id"], "avoid_hours": len(s["avoid_hours"])}
                                   for s in feed["segments"]]), on="segment_id")
    flagged = both[(both.damage >= 0.5) & (both.avoid_hours > 0)]
    st.dataframe(flagged.assign(section=flagged.segment_id.map(seg.set_index("seg_id").label)), hide_index=True)

with st.expander("The Module 3 feed (JSON)"):
    st.json(feed, expanded=False)
st.caption(feed["disclaimer"])
st.caption("Places: " + ", ".join(sorted(set(POI_LABEL.values()))))
