"""Plan a visit: crowd outlook for one target day and ranked suggestions to avoid the crowd.

Suggestions (roadmap.md, section 4), all park-specific names come from the config:
  date       a nearby day (+-7 days, inside the outlook) with clearly fewer people on the main trail
  later      the earliest start time at which you meet at most half of the peak at the focus place
  reverse    walking a loop the other way round (only for loops in simulator.reversible_routes)
  trail      another trail, on busy days when the main trail is over its quota and the other one has room left
Each suggestion carries the expected reduction in the number of people you share the trail with
(date / trail: whole day; later / reverse: at the focus place when you arrive), so they can be ranked.
Never suggest a trail without room under its own Cifuentes quota (do not just move the damage).
"""
import numpy as np
import pandas as pd

from src.capacity.cifuentes import capacity


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
        area, p = cfg["area"], cfg.get("planning", {})
        self.main = area.get("main_trail", next(iter(walks)))
        self.names = area["trail_names"]
        self.info = area.get("trail_info", {})
        self.focus_label = area.get("poi_labels", {}).get(area.get("focus_poi"), "the busiest place")
        self.access_note = p.get("access_note", "Check with DWC that the trail is open and whether a guide is needed.")
        self.later_note = p.get("later_note", "")
        self.start_h = p.get("typical_start_h", 7)
        self.reversible = self.main in cfg["simulator"].get("reversible_routes", [])
        focus = self.seg.index[self.seg.poi == area.get("focus_poi")]
        self.focus = int(focus[0]) if len(focus) else None
        lf = cfg["simulator"]["leisure_speed_factor"]
        main = walks[self.main]
        rev = [(s, -d) for s, d in reversed(main)]
        self.t_focus = {"standard": _minutes_to(self.seg, main, self.focus, lf) if self.focus is not None else 0.0,
                        "reverse": _minutes_to(self.seg, rev, self.focus, lf) if self.focus is not None else 0.0}

    # ---------- one day ----------
    def day(self, issue_date, target_date, horizon=90, rain_share: float | None = None, wetness: float = 0.0,
            conditions: dict | None = None) -> dict:
        """rain_share / wetness / conditions: the live service passes the weather forecast (when it reaches that
        day), the ground wetness from earlier rain and officer-reported trail conditions; without them the rain
        comes from the planning model's typical weather and the ground is assumed dry."""
        ol = self.m.outlook(issue_date, horizon)
        target = pd.Timestamp(target_date)
        if target not in ol.index:
            raise ValueError(f"{target_date:%Y-%m-%d} is not within {horizon} days after {issue_date}")
        row = ol.loc[target]
        occ = {q: self.m.hourly(row, q) for q in ("p10", "p50", "p90")}
        expected = {t: float(row[f"{t}_p50"]) for t in self.m.daily.trails}
        if rain_share is None:
            rain_share = float(row.p_wet) * 0.5      # wet mornings: about half the open hours have rain (approx.)
        cap = capacity(self.seg.reset_index(drop=True), occ["p50"], None, expected,
                       self.cfg["capacity"] | {"main_trail": self.main}, self.cfg["simulator"], self.names,
                       rain_share=rain_share, wetness=wetness, conditions=conditions)
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
        main_name = self.names.get(self.main, self.main)
        main_p50 = ol[f"{self.main}_p50"]
        here = float(main_p50.loc[target])

        # 1. another date nearby
        near = main_p50[(main_p50.index != target) & (abs(main_p50.index - target) <= pd.Timedelta(days=7))]
        for d, v in near.nsmallest(2).items():
            red = 1 - v / max(here, 1)
            if red >= 0.2:
                out.append({"kind": "date", "date": str(d.date()), "reduction_pct": round(100 * red),
                            "title": f"Go on {d:%a %d %b} instead",
                            "detail": f"about {v:,.0f} people on the {main_name} instead of {here:,.0f}"})

        # 2. start later (meet at most half of the peak at the focus place)
        if self.focus is not None:
            fo = occ[:, self.focus]
            peak = fo.max()
            if peak >= 20:
                met = lambda start_h, mins: fo[min(23, int(start_h + mins / 60))]
                usual = met(self.start_h, self.t_focus["standard"])
                for h in np.arange(self.start_h + 0.5, self.start_h + 5.5, 0.5):
                    m = met(h, self.t_focus["standard"])
                    if m <= 0.5 * peak and usual > 0:
                        hh = f"{int(h) % 24:02d}:{int(h % 1 * 60):02d}"
                        out.append({"kind": "later", "start": hh, "reduction_pct": round(100 * (1 - m / usual)),
                                    "title": f"Start after {hh}",
                                    "detail": f"about {m:.0f} people at {self.focus_label} when you arrive instead "
                                              f"of {usual:.0f}. {self.later_note}".strip()})
                        break

                # 3. reverse direction (loops only), usual start
                if self.reversible:
                    std, rev = met(self.start_h, self.t_focus["standard"]), met(self.start_h, self.t_focus["reverse"])
                    if std > 0 and rev < 0.8 * std:
                        out.append({"kind": "reverse", "reduction_pct": round(100 * (1 - rev / std)),
                                    "title": "Walk the loop the other way",
                                    "detail": f"you reach {self.focus_label} about {self.t_focus['reverse'] / 60:.1f} h "
                                              f"after starting, when about {rev:.0f} people are there instead of {std:.0f}"})

        # 4. another trail: only on busy days (crowd level >= 3) when the main trail is over its quota,
        #    and only if the alternative still has room under its own quota
        main_cap = cap["trails"][self.main]
        busy = int(ol.crowd_level.loc[target]) >= 3
        if busy and main_cap["expected_visitors"] > main_cap["recommended_daily_quota"]:
            others = sorted((t for t in cap["trails"] if t != self.main), key=lambda t: cap["trails"][t]["expected_visitors"])
            for t in others:
                tc = cap["trails"][t]
                if tc["headroom"] > 0:
                    fewer = 1 - tc["expected_visitors"] / max(main_cap["expected_visitors"], 1)
                    out.append({"kind": "trail", "trail": t, "reduction_pct": round(100 * fewer),
                                "room_left": tc["headroom"],
                                "title": f"Take {self.names[t]} instead",
                                "detail": f"about {tc['expected_visitors']} people expected, room for "
                                          f"{tc['headroom']} more under its capacity. {self.info.get(t, '')}. "
                                          f"{self.access_note}"})
        effort = {"date": 1, "later": 0, "reverse": 0, "trail": 2}
        return sorted(out, key=lambda s: (-s["reduction_pct"], effort[s["kind"]]))[:5]
