"""Entry control: how many tickets each trail can sell for each entry slot (docs/archive/upgrade_plan.md, section 2).

Logic in one line: a ticket = a trail + an entry time, so we know where its holder will be over the day;
only sell tickets while every segment stays under its safe capacity in every half hour.

1. Response table K[trail, slot, segment, bin]: people on a segment in a half-hour bin per ticket sold for that
   trail and slot. Measured with the simulator (tiny cohorts, so no crowd effect), for a dry and a wet day.
2. Capacity C[segment]: people it can hold at once at Cifuentes social spacing (groups of 10, 50 m apart)
   x management capacity x (1 - rain share). Viewpoints get at least a platform-sized minimum; access points
   (Visitor Center, trailhead) are facilities and are not limited here.
3. Linear programme: maximise tickets (popular slots first) subject to
       sum_{trail,slot} K * tickets <= margin * C   for every segment and half hour
       sum_slot tickets[trail] <= Cifuentes daily quota of the trail
   then round down (rounding down can only lower occupancy, so the plan stays safe).
"""
from functools import lru_cache

import numpy as np
import pandas as pd
from scipy.optimize import linprog

from src.data.build_dataset import access_points, viewpoints
from src.sim.simulator import MIN_PER_DAY, arrival_minutes


class EntryControl:
    def __init__(self, sim, seg: pd.DataFrame, cfg: dict, seed: int = 42):
        self.sim, self.cfg, self.c = sim, cfg, cfg["control"]
        self.seg = seg.reset_index(drop=True)
        self.trails = list(sim.trails)
        c = self.c
        self.slots = np.arange(c["first_slot_h"] * 60, c["last_slot_h"] * 60 + 1, c["slot_minutes"]).astype(int)
        self.n_bins = MIN_PER_DAY // c["bin_minutes"]
        last = cfg["simulator"].get("route_last_entry_h", {})
        self.allowed = np.array([[s < last.get(t, 24) * 60 for s in self.slots] for t in self.trails])
        self.K = self._response(seed)                     # [wet, trail, slot, segment, bin]
        self.slot_share = self._slot_share(seed)          # share of visitors who want each slot

    # ---------- 1. response table ----------
    def _response(self, seed):
        rng = np.random.default_rng(seed)
        p, c = self.cfg["simulator"], self.c
        n = c["response_walkers"]
        K = np.zeros((2, len(self.trails), len(self.slots), self.sim.S, self.n_bins))
        for w, mm in enumerate([0.0, p["rain_light_mm"] + 0.1]):
            precip = np.full(24, mm)
            for r, t in enumerate(self.trails):
                for k, start in enumerate(self.slots):
                    gate = start + rng.uniform(0, c["slot_minutes"], n)
                    if t in p.get("reversible_routes", []):
                        option = np.where(rng.random(n) < p["standard_direction_share"],
                                          self.sim.option_of_trail(t), self.sim.option_of_trail(t, reverse=True))
                    else:
                        option = np.full(n, self.sim.option_of_trail(t))
                    _, per_min, _ = self.sim.simulate_groups(np.full(n, 1.0 / n), gate, option, precip, rng)
                    K[w, r, k] = per_min.reshape(self.sim.S, self.n_bins, c["bin_minutes"]).mean(-1)
        return K

    def _slot_share(self, seed):
        gate = arrival_minutes(20000, self.cfg["simulator"], np.random.default_rng(seed))
        idx = np.clip(np.searchsorted(self.slots, gate, side="right") - 1, 0, len(self.slots) - 1)
        return np.bincount(idx, minlength=len(self.slots)) / len(gate)

    def slot_of(self, gate_min) -> np.ndarray:
        return np.clip(np.searchsorted(self.slots, gate_min, side="right") - 1, 0, len(self.slots) - 1)

    # ---------- 2. capacity ----------
    def capacity(self, rain_share: float = 0.0) -> np.ndarray:
        cap = self.cfg["capacity"]
        L = self.seg.length_m.values
        at_once = L / (cap["group_gap_m"] + cap["group_size"] * cap["space_per_person_m"]) * cap["group_size"]
        poi = self.seg.poi.fillna("").values
        at_once = np.where(np.isin(poi, list(viewpoints(self.cfg))),
                           np.maximum(at_once, self.c["viewpoint_min_at_once"]), at_once)
        C = at_once * cap["management_capacity"] * (1 - rain_share) * self.c.get("capacity_scale", 1.0)
        if self.c["exempt_access_points"]:
            C = np.where(np.isin(poi, list(access_points(self.cfg))), np.inf, C)
        return C

    def daily_quota(self, rain_share: float = 0.0, wetness: float = 0.0, conditions: dict | None = None,
                    forecast: np.ndarray | None = None) -> dict:
        """Cifuentes daily quota per trail for this day's rain, ground wetness and reported trail conditions,
        scaled by the same capacity standard as the half-hour limits.
        forecast: [24, segments] people; adds FCcrowd (share of open hours over capacity). None = classic."""
        from src.capacity.cifuentes import capacity
        fc = np.zeros((24, len(self.seg))) if forecast is None else np.asarray(forecast)
        cap = capacity(self.seg, fc, None, {}, self.cfg["capacity"],
                       self.cfg["simulator"], rain_share=rain_share, wetness=wetness, conditions=conditions)
        scale = self.c.get("capacity_scale", 1.0)
        return {t: v["recommended_daily_quota"] * scale for t, v in cap["trails"].items()}

    def response(self, rain_share: float) -> np.ndarray:
        """Expected response for a day with this share of rainy open hours: [trail, slot, segment, bin]."""
        return (1 - rain_share) * self.K[0] + rain_share * self.K[1]

    # ---------- 3. slot plan ----------
    def plan(self, rain_share: float = 0.0, daily_quota: dict | None = None, closed: set | None = None) -> pd.DataFrame:
        """Tickets per trail and slot (DataFrame: rows = slot 'HH:MM', columns = trails).
        closed: (trail, 'HH:MM') pairs an officer has closed; they get no tickets.

        maximise  sum (1 + popularity of slot) * tickets  -  smooth * sum |tickets[k] - tickets[k+1]|
        subject to the capacity rows (every segment, every half hour) and the daily quota per trail.
        The smoothness term (auxiliary variables u >= |difference|) gives a table a ticket counter can use.
        """
        R, S_ = len(self.trails), len(self.slots)
        K, C = self.response(rain_share), self.capacity(rain_share) * self.c["safety_margin"]
        labels = [f"{s // 60:02d}:{s % 60:02d}" for s in self.slots]
        allowed = self.allowed.copy()
        for t, s in closed or ():
            allowed[self.trails.index(t), labels.index(s)] = False
        xs = [(r, k) for r in range(R) for k in range(S_) if allowed[r, k]]
        if not xs:                                            # everything closed
            return pd.DataFrame(0, index=labels, columns=self.trails)
        idx = {v: i for i, v in enumerate(xs)}
        pairs = [(idx[(r, k)], idx[(r, k + 1)]) for r, k in xs if (r, k + 1) in idx]
        nx, n = len(xs), len(xs) + len(pairs)

        A, b = [], []
        for s in np.where(np.isfinite(C))[0]:
            for t in range(self.n_bins):
                row = np.zeros(n)
                row[:nx] = [K[r, k, s, t] for r, k in xs]
                if row.max() > 1e-6:
                    A.append(row)
                    b.append(C[s])
        if self.c["use_daily_quota"] and daily_quota:
            for r, t in enumerate(self.trails):
                if t in daily_quota:
                    row = np.zeros(n)
                    row[:nx] = [1.0 if rr == r else 0.0 for rr, _ in xs]
                    A.append(row)
                    b.append(daily_quota[t])
        for j, (a, c) in enumerate(pairs):                    # u_j >= x_a - x_c and u_j >= x_c - x_a
            for sign in (1, -1):
                row = np.zeros(n)
                row[a], row[c], row[nx + j] = sign, -sign, -1
                A.append(row)
                b.append(0.0)
        pop = self.slot_share / self.slot_share.max()
        w = np.concatenate([[1 + pop[k] for _, k in xs], np.full(len(pairs), -0.3)])
        res = linprog(-w, A_ub=np.array(A), b_ub=np.array(b), bounds=[(0, None)] * n, method="highs")
        if not res.success:
            raise RuntimeError(res.message)
        x = np.zeros((R, S_))
        for (r, k), v in zip(xs, res.x[:nx]):
            x[r, k] = np.floor(v + 1e-9)
        return pd.DataFrame(x.T.astype(int), index=[f"{s // 60:02d}:{s % 60:02d}" for s in self.slots],
                            columns=self.trails)

    def expected_occupancy(self, tickets: pd.DataFrame, rain_share: float) -> np.ndarray:
        """Occupancy [segment, bin] if every ticket is used (linear prediction)."""
        x = tickets.values.T                                   # [trail, slot]
        return np.einsum("rk,rksb->sb", x, self.response(rain_share))

    def nowcast(self, admitted: pd.DataFrame, now_min: int, rain_share: float = 0.0) -> np.ndarray:
        """Expected people on each segment now, from the tickets scanned so far (no trail sensors).
        admitted: rows with columns trail, gate_min, size."""
        K = self.response(rain_share)
        b = min(now_min // self.c["bin_minutes"], self.n_bins - 1)
        occ = np.zeros(self.sim.S)
        seen = admitted[admitted.gate_min <= now_min]
        for (trail, k), g in seen.groupby([seen.trail, self.slot_of(seen.gate_min.values)]):
            occ += K[self.trails.index(trail), k, :, b] * g["size"].sum()
        return occ


@lru_cache(maxsize=1)
def build_control():
    """EntryControl for the current dataset (cached)."""
    import geopandas as gpd

    from src.config import PROCESSED, load_config
    from src.data.graph import load_walks
    from src.sim.simulator import TrailSimulator
    cfg = load_config()
    seg = gpd.read_file(PROCESSED / "segments.geojson")
    seg["poi"] = seg["poi"].fillna("")
    sim = TrailSimulator(seg, load_walks(), cfg["simulator"])
    return EntryControl(sim, seg, cfg, cfg["seed"])
