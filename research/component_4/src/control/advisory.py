"""Advisory crowd control for a pilgrimage summit (Adam's Peak): nobody is refused (adams_peak_plan.md, section 4).

1. Arrival response A[route, start slot, bin]: the share of pilgrims who start a route in a 30-min slot and reach
   the summit in each 15-min bin (measured with the simulator, tiny cohorts, no crowd effect).
2. Summit queue (fluid model): arrivals per bin minus what the final steps can take (flow people/min);
   the backlog divided by the flow is the wait.
3. Recommended start times: for each route, the start windows whose expected wait is under the limit
   (queue_limit_min) and that still reach the summit by sunrise.
4. Halfway checks: officers at each route's halfway checkpoint release at most their share of the summit flow
   (people per 10 min) whenever the summit queue is above the limit, so the queue waits at the rest halt,
   not on the steep final steps.
5. Live estimate: counts entered at the halfway checkpoints, shifted by the walking time to the summit,
   give the queue now and in the next hour (no sensors).
"""
from functools import lru_cache

import numpy as np
import pandas as pd

from src.sim.simulator import arrival_minutes

BIN = 15                                                   # minutes


def _hhmm(minutes: float) -> str:
    m = int(round(minutes)) % (24 * 60)
    return f"{m // 60:02d}:{m % 60:02d}"


class Advisory:
    def __init__(self, sim, seg: pd.DataFrame, cfg: dict, seed: int = 42):
        self.sim, self.cfg = sim, cfg
        self.c, self.p = cfg["control"], cfg["simulator"]
        self.flow = float(self.p["bottleneck"]["flow_per_min"])
        self.limit = float(self.c.get("queue_limit_min", 20))
        self.sunrise_min = float(self.c.get("sunrise_h", 6.0)) * 60
        self.trails = list(sim.trails)
        c = self.c
        self.slots = np.arange(c["first_slot_h"] * 60, c["last_slot_h"] * 60 + 1, c["slot_minutes"]).astype(int)
        self.labels = [f"{s // 60:02d}:{s % 60:02d}" for s in self.slots]
        self.n_bins = 24 * 60 // BIN
        self.A, self.median_arrival, self.cp_to_top = self._response(seed)
        g = arrival_minutes(20000, self.p, np.random.default_rng(seed))
        idx = np.clip(np.searchsorted(self.slots, g, side="right") - 1, 0, len(self.slots) - 1)
        self.slot_share = np.bincount(idx, minlength=len(self.slots)) / len(g)

    # ---------- 1. where a starter is when they reach the top ----------
    def _response(self, seed):
        rng = np.random.default_rng(seed)
        n = 200
        sim = self.sim
        A = np.zeros((len(self.trails), len(self.slots), self.n_bins))
        med = np.zeros((len(self.trails), len(self.slots)))
        cp_to_top = {}
        crowd = np.ones((sim.S, 24))
        for r, t in enumerate(self.trails):
            k_opt = sim.option_of_trail(t)
            walk = sim.options[k_opt][1]
            i = sim._turnaround(walk)
            for k, start in enumerate(self.slots):
                t0 = start + rng.uniform(0, self.c["slot_minutes"], n)
                speed = rng.lognormal(0.0, self.p["walker_speed_sd"], n)
                arr = sim._walk(walk[:i], t0, np.ones(n), speed, {}, np.zeros(24), crowd, None)
                b = np.clip((arr // BIN).astype(int), 0, self.n_bins - 1)
                A[r, k] = np.bincount(b, minlength=self.n_bins) / n
                med[r, k] = np.median(arr)
            cp = sim.checkpoint.get(t)
            if cp is not None:
                j = [s for s, _ in walk[:i]].index(cp)
                cp_to_top[t] = float(np.median(sim._walk(walk[j:i], np.zeros(n), np.ones(n), np.ones(n), {},
                                                         np.zeros(24), crowd, None)))
        return A, med, cp_to_top

    # ---------- 2. the summit queue ----------
    def demand(self, visitors_by_trail: dict) -> np.ndarray:
        """Expected starters per route and slot when people start when they usually do."""
        return np.array([visitors_by_trail.get(t, 0.0) for t in self.trails])[:, None] * self.slot_share[None, :]

    def queue(self, D: np.ndarray):
        """Fluid queue at the summit. Returns arrivals, backlog (people) and wait (min) per 15-min bin."""
        a = np.einsum("rk,rkb->b", D, self.A)
        q = np.zeros(self.n_bins)
        prev = 0.0
        for b in range(self.n_bins):
            prev = max(0.0, prev + a[b] - self.flow * BIN)
            q[b] = prev
        return a, q, q / self.flow

    def wait_by_start(self, D: np.ndarray) -> np.ndarray:
        """Expected wait at the top [route, slot] for someone starting then."""
        _, _, w = self.queue(D)
        return np.einsum("rkb,b->rk", self.A, w)

    # ---------- 3. recommended start times ----------
    def recommend(self, visitors_by_trail: dict) -> dict:
        D = self.demand(visitors_by_trail)
        W = self.wait_by_start(D)
        a, q, w = self.queue(D)
        out = {"limit_min": self.limit, "flow_per_min": self.flow, "routes": {}}
        for r, t in enumerate(self.trails):
            rows = []
            for k, lab in enumerate(self.labels):
                reach = float(self.median_arrival[r, k])
                rows.append({"start": lab, "expected_wait_min": round(float(W[r, k])),
                             "reach_summit": f"{int(reach // 60) % 24:02d}:{int(reach % 60):02d}",
                             "before_sunrise": bool(reach <= self.sunrise_min),
                             "recommended": bool(W[r, k] <= self.limit)})
            good = [x for x in rows if x["recommended"] and x["before_sunrise"]]
            best = min(rows, key=lambda x: (not x["before_sunrise"], x["expected_wait_min"], -int(x["start"][:2])))
            short_wait = min(rows, key=lambda x: (x["expected_wait_min"], int(x["start"][:2])))
            out["routes"][t] = {"windows": rows, "best_for_sunrise": best["start"],
                                "recommended_for_sunrise": [x["start"] for x in good],
                                "shortest_wait": short_wait["start"]}
        peak_b = int(np.argmax(q))
        windows = self.hold_windows(w)
        out["summit"] = {"peak_queue_people": round(float(q.max())), "peak_wait_min": round(float(w.max())),
                         "peak_at": _hhmm(peak_b * BIN), "bin_min": BIN,
                         "wait_by_time": [round(float(x)) for x in w],
                         "hold_windows": [[_hhmm(a), _hhmm(b)] for a, b in windows]}
        out["halfway"] = self.release_rates(D)
        for t, r in out["halfway"].items():           # when each checkpoint must hold: earlier by the walk to the top
            walk = self.cp_to_top.get(t, 0.0)
            r["hold_windows"] = [[_hhmm(a - walk), _hhmm(b - walk)] for a, b in windows]
        return out

    def hold_windows(self, wait: np.ndarray) -> list:
        """Summit-arrival times (minutes) when the expected wait is over the limit, as [from, to) pairs."""
        over, out, b = wait > self.limit, [], 0
        while b < len(over):
            if over[b]:
                s = b
                while b < len(over) and over[b]:
                    b += 1
                out.append((s * BIN, b * BIN))
            else:
                b += 1
        return out

    def spread(self, D: np.ndarray, movers: np.ndarray, batch: float = 25.0, sunrise_penalty_min: float = 30.0):
        """Assign pilgrims who agree to move (movers[route, from_slot]) to start windows one batch at a time,
        always to the window of the same route with the lowest expected wait *after* the earlier batches
        (+ a penalty for missing sunrise). Accounts for the effect of the advice itself: sending everyone to the
        same 'quiet' time just moves the queue (herding). Returns the new demand matrix and moves[r, from, to]."""
        D = D - movers
        moves = np.zeros((len(self.trails), len(self.slots), len(self.slots)))
        late = self.median_arrival > self.sunrise_min                     # [route, slot]
        for r in range(len(self.trails)):
            for k_from in np.argsort(-movers[r]):
                left = movers[r, k_from]
                while left > 1e-9:
                    n = min(batch, left)
                    W = self.wait_by_start(D)[r] + sunrise_penalty_min * late[r]
                    k_to = int(np.argmin(W))
                    D[r, k_to] += n
                    moves[r, k_from, k_to] += n
                    left -= n
        return D, moves

    # ---------- 4. halfway checks ----------
    def release_rates(self, D: np.ndarray) -> dict:
        """People per 10 min each halfway checkpoint should let through while the summit queue is over the limit:
        the route's share of the summit flow."""
        share = D.sum(1) / max(D.sum(), 1e-9)
        return {t: {"release_per_10_min": round(float(self.flow * 10 * share[r])),
                    "walk_to_summit_min": round(self.cp_to_top.get(t, 0.0))} for r, t in enumerate(self.trails)}

    # ---------- 5. live estimate from checkpoint counts ----------
    def nowcast(self, passes: pd.DataFrame, now_min: int) -> dict:
        """passes: route, time_min (when counted at the halfway checkpoint), count.
        Returns the summit queue now and over the time it takes someone passing a checkpoint now to reach the top
        (at least an hour), and what officers should do."""
        arr = np.zeros(self.n_bins)
        for row in passes.itertuples():
            t = row.time_min + self.cp_to_top.get(row.route, 0.0)
            arr[min(self.n_bins - 1, int(t // BIN))] += row.count
        q, prev = np.zeros(self.n_bins), 0.0
        for b in range(self.n_bins):
            prev = max(0.0, prev + arr[b] - self.flow * BIN)
            q[b] = prev
        b_now = min(self.n_bins - 1, now_min // BIN)
        ahead = max(60.0, max(self.cp_to_top.values(), default=0.0) + BIN)   # minutes
        horizon = q[b_now:b_now + int(np.ceil(ahead / BIN)) + 1]
        wait_now, wait_next = q[b_now] / self.flow, horizon.max() / self.flow if len(horizon) else 0.0
        hold = wait_next > self.limit
        return {"time": f"{now_min // 60:02d}:{now_min % 60:02d}", "queue_now_people": round(float(q[b_now])),
                "wait_now_min": round(float(wait_now)), "ahead_min": round(ahead),
                "wait_ahead_max_min": round(float(wait_next)),
                "action": ("HOLD at the halfway checks: release only the listed number per 10 minutes"
                           if hold else "Normal: let groups continue"),
                "hold": bool(hold)}


@lru_cache(maxsize=1)
def build_advisory():
    import geopandas as gpd

    from src.config import PROCESSED, load_config
    from src.data.graph import load_walks
    from src.sim.simulator import TrailSimulator
    cfg = load_config()
    seg = gpd.read_file(PROCESSED / "segments.geojson")
    seg["poi"] = seg["poi"].fillna("")
    sim = TrailSimulator(seg, load_walks(), cfg["simulator"])
    return Advisory(sim, seg, cfg, cfg["seed"])
