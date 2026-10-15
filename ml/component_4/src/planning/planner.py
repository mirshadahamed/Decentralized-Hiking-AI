"""Plan a visit: crowd outlook for one target day and ranked suggestions to avoid the crowd.

Suggestions (roadmap.md, section 4):
  date       a nearby day (+-7 days, inside the outlook) with clearly fewer people on the World's End loop
  later      the earliest start time at which you meet at most half of the World's End peak
  reverse    walking the loop the other way round (Baker's Falls first) reaches World's End at a quieter time
  trail      Thotupola Kanda or Kirigalpotta, on busy days when the main loop is over its quota and they have room left
Each suggestion carries the expected reduction in the number of people you share the trail with
(date / trail: whole day; later / reverse: at World's End when you arrive), so they can be ranked.
Never suggest a trail without room under its own Cifuentes quota (do not just move the damage).
"""
import numpy as np
import pandas as pd

from src.capacity.cifuentes import capacity

TRAIL_INFO = {
    "thotupola": "1.3 km each way to the 3rd-highest peak (2,357 m); trailhead is a 4.2 km drive up the Pattipola road",
    "kirigalpotta": "5.2 km each way to the 2nd-highest peak (2,388 m); long and exposed, last start 09:30",
}
CHECK_ACCESS = "Check with DWC that the trail is open and whether a guide is needed."


def _minutes_to(seg, walk, target_seg, leisure):
    """Walking minutes from the start of a walk until the hiker reaches target_seg."""
    t = 0.0
    for s, d in walk:
        if s == target_seg:
            return t
        col = "tobler_fwd_min" if d > 0 else "tobler_bwd_min"
        t += seg.loc[s, col] / leisure
    return t


class Planner:
    def __init__(self, model, seg: pd.DataFrame, walks: dict, cfg: dict):
        self.m, self.cfg = model, cfg
        self.seg = seg.set_index("seg_id", drop=False)
        self.walks = walks
        self.we = int(self.seg.index[self.seg.poi == "worlds_end"][0])
        lf = cfg["simulator"]["leisure_speed_factor"]
        main = walks["main"]
        rev = [(s, -d) for s, d in reversed(main)]
        self.t_we = {"standard": _minutes_to(self.seg, main, self.we, lf),
                     "reverse": _minutes_to(self.seg, rev, self.we, lf)}
        self.names = cfg["area"]["trail_names"]

    # ---------- one day ----------
    def day(self, issue_date, target_date, horizon=90) -> dict:
        ol = self.m.outlook(issue_date, horizon)
        target = pd.Timestamp(target_date)
        if target not in ol.index:
            raise ValueError(f"{target_date:%Y-%m-%d} is not within {horizon} days after {issue_date}")
        row = ol.loc[target]
        occ = {q: self.m.hourly(row, q) for q in ("p10", "p50", "p90")}
        expected = {t: float(row[f"{t}_p50"]) for t in self.m.daily.trails}
        rain_share = float(row.p_wet) * 0.5          # wet mornings: about half the open hours have rain (approx.)
        cap = capacity(self.seg.reset_index(drop=True), occ["p50"], None, expected, self.cfg["capacity"],
                       self.cfg["simulator"], self.names, rain_share=rain_share)
        sugg = self.suggestions(ol, target, occ["p50"], cap)
        return {"issue_date": str(pd.Timestamp(issue_date).date()), "target_date": str(target.date()),
                "lead_days": int(row.lead), "confidence": self.confidence(int(row.lead)),
                "visitors": {"p10": round(row.p10), "p50": round(row.p50), "p90": round(row.p90)},
                "visitors_by_trail": {t: {q: round(float(row[f"{t}_{q}"])) for q in ("p10", "p50", "p90")}
                                      for t in self.m.daily.trails},
                "crowd_level": int(row.crowd_level), "chance_wet_morning": round(float(row.p_wet), 2),
                "hourly": {q: v.round(1).tolist() for q, v in occ.items()},
                "capacity": cap, "suggestions": sugg}

    @staticmethod
    def confidence(lead: int) -> str:
        return "medium (weather forecast range)" if lead <= 16 else "low (calendar and typical weather only)"

    # ---------- suggestions ----------
    def suggestions(self, ol: pd.DataFrame, target, occ: np.ndarray, cap: dict) -> list:
        out = []
        main_p50 = ol.main_p50
        here = float(main_p50.loc[target])

        # 1. another date nearby
        near = main_p50[(main_p50.index != target) & (abs(main_p50.index - target) <= pd.Timedelta(days=7))]
        for d, v in near.nsmallest(2).items():
            red = 1 - v / max(here, 1)
            if red >= 0.2:
                out.append({"kind": "date", "date": str(d.date()), "reduction_pct": round(100 * red),
                            "title": f"Go on {d:%a %d %b} instead",
                            "detail": f"about {v:,.0f} people on the World's End loop instead of {here:,.0f}"})

        # 2. start later (meet at most half of the World's End peak)
        we = occ[:, self.we]
        peak = we.max()
        if peak >= 20:
            met = lambda start_h, mins: we[min(23, int(start_h + mins / 60))]
            usual = met(7, self.t_we["standard"])
            for h in np.arange(7.5, 12.5, 0.5):
                m = met(h, self.t_we["standard"])
                if m <= 0.5 * peak and usual > 0:
                    out.append({"kind": "later", "start": f"{int(h):02d}:{int(h % 1 * 60):02d}",
                                "reduction_pct": round(100 * (1 - m / usual)),
                                "title": f"Start after {int(h):02d}:{int(h % 1 * 60):02d}",
                                "detail": f"about {m:.0f} people at World's End when you arrive instead of {usual:.0f}. "
                                          "Views at World's End are often lost to mist later in the morning."})
                    break

            # 3. reverse direction, same 07:00 start
            std, rev = met(7, self.t_we["standard"]), met(7, self.t_we["reverse"])
            if std > 0 and rev < 0.8 * std:
                out.append({"kind": "reverse", "reduction_pct": round(100 * (1 - rev / std)),
                            "title": "Walk the loop the other way (Baker's Falls first)",
                            "detail": f"you reach World's End about {self.t_we['reverse'] / 60:.1f} h after starting, "
                                      f"when about {rev:.0f} people are there instead of {std:.0f}"})

        # 4. another trail: only on busy days (crowd level >= 3) when the main loop is over its quota,
        #    and only if the alternative still has room under its own quota
        main_cap = cap["trails"]["main"]
        busy = int(ol.crowd_level.loc[target]) >= 3
        if busy and main_cap["expected_visitors"] > main_cap["recommended_daily_quota"]:
            for t in ("thotupola", "kirigalpotta"):
                tc = cap["trails"].get(t)
                if tc and tc["headroom"] > 0:
                    fewer = 1 - tc["expected_visitors"] / max(main_cap["expected_visitors"], 1)
                    out.append({"kind": "trail", "trail": t, "reduction_pct": round(100 * fewer),
                                "room_left": tc["headroom"],
                                "title": f"Hike {self.names[t]} instead",
                                "detail": f"about {tc['expected_visitors']} people expected, room for "
                                          f"{tc['headroom']} more under its capacity. {TRAIL_INFO[t]}. {CHECK_ACCESS}"})
        effort = {"date": 1, "later": 0, "reverse": 0, "trail": 2}
        return sorted(out, key=lambda s: (-s["reduction_pct"], effort[s["kind"]]))[:5]
