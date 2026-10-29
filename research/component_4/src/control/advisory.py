"""Advisory crowd control for a pilgrimage summit (Adam's Peak): nobody is refused (docs/archive/adams_peak_plan.md, section 4).

A "night" is named after its sunrise date and runs from `night_start_h` (18:00) the evening before; times before
midnight are negative minutes (e.g. 21:00 the evening before = -180).

1. Arrival response A[route, start slot, bin]: the share of pilgrims who start a route in a 30-min slot and reach
   the summit in each 15-min bin. Measured with the simulator UNDER THE NIGHT'S EXPECTED CROWD: a full night with
   that many climbers is simulated first, and its crowding slows the test walkers down (on a busy Poya night the
   Nallathanniya climb takes about twice as long as on a quiet night). Measured once per crowd level
   (`crowd_levels`) and reused.
2. Summit queue (fluid model): arrivals per bin minus what the final steps can take (flow people/min);
   the backlog divided by the flow is the wait.
3. Recommended start times: for each route, the start windows whose expected wait is under the limit
   (queue_limit_min) and that still reach the summit before SUNRISE OF THAT DATE (computed for the summit,
   including the earlier sunrise seen from its height). Includes starts the evening before.
4. Evening plan: start the evening before, rest at the route's halfway hall, and leave the hall at a recommended
   time to reach the summit before sunrise without a long wait.
5. Halfway checks: officers at each route's halfway checkpoint release at most their share of the summit flow
   (people per 10 min) whenever the summit queue is above the limit, so the queue waits at the rest halt,
   not on the steep final steps.
6. Live estimate: counts entered at the halfway checkpoints, shifted by the walking time to the summit,
   give the queue now and ahead (no sensors).
"""
import math
from datetime import date as Date
from functools import lru_cache

import numpy as np
import pandas as pd

from src.sim.simulator import arrival_minutes

BIN = 15                                                   # minutes
TZ_H = 5.5                                                 # Sri Lanka time


def _hhmm(minutes: float) -> str:
    m = int(round(minutes)) % (24 * 60)
    return f"{m // 60:02d}:{m % 60:02d}"


def sunrise_minutes(day, lat: float, lon: float, elevation_m: float = 0.0, tz_h: float = TZ_H) -> float:
    """Local sunrise (minutes after midnight) on `day` (NOAA solar position equations, about +-2 min).
    Seen from a summit the sun appears earlier: the horizon dips by 1.76 arc-minutes x sqrt(height in m)."""
    day = pd.Timestamp(day).date() if not isinstance(day, Date) else day
    g = 2 * math.pi / 365 * (day.timetuple().tm_yday - 1 + 0.5)
    eqtime = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g)
                       - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g) - 0.006758 * math.cos(2 * g)
            + 0.000907 * math.sin(2 * g) - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    zenith = math.radians(90.833 + 1.76 * math.sqrt(max(elevation_m, 0.0)) / 60)
    la = math.radians(lat)
    ha = math.degrees(math.acos(math.cos(zenith) / (math.cos(la) * math.cos(decl)) - math.tan(la) * math.tan(decl)))
    return 720 - 4 * (lon + ha) - eqtime + tz_h * 60


class Advisory:
    def __init__(self, sim, seg: pd.DataFrame, cfg: dict, seed: int = 42):
        self.sim, self.cfg, self.seed = sim, cfg, seed
        self.c, self.p = cfg["control"], cfg["simulator"]
        self.flow = float(self.p["bottleneck"]["flow_per_min"])
        self.limit = float(self.c.get("queue_limit_min", 20))
        self.sunrise_min = float(self.c.get("sunrise_h", 6.0)) * 60          # used when no date is given
        self.trails = list(sim.trails)
        c = self.c
        self.slots = np.arange(c["first_slot_h"] * 60, c["last_slot_h"] * 60 + 1, c["slot_minutes"]).astype(int)
        self.labels = [_hhmm(s) for s in self.slots]
        self.t0 = int(min(0, self.slots.min()))                           # first minute of the night (<= 0)
        self.n_bins = (24 * 60 - self.t0) // BIN
        self.levels = sorted(c.get("crowd_levels", [0]))
        self._cache = {}
        self.slot_share = self._slot_share(seed)
        self.use_crowd(0)

    # ---------- the night's crowd ----------
    def _slot_share(self, seed):
        """Share of pilgrims who start in each slot when nobody is advised: the usual night-time starts, plus
        `evening_share` starting the evening before (night_start .. 23:30) and resting on the way."""
        g = arrival_minutes(20000, self.p, np.random.default_rng(seed))
        idx = np.clip(np.searchsorted(self.slots, g, side="right") - 1, 0, len(self.slots) - 1)
        usual = np.bincount(idx, minlength=len(self.slots)) / len(g)
        ev = self.c.get("evening_share", 0.0)
        evening = ((self.slots >= self.c.get("night_start_h", 18) * 60 - 1440) & (self.slots < 0)).astype(float)
        if ev <= 0 or evening.sum() == 0:
            return usual
        return (1 - ev) * usual + ev * evening / evening.sum()

    def level_of(self, climbers: float) -> int:
        """The measured crowd level closest to a night with this many climbers."""
        return min(self.levels, key=lambda lv: abs(lv - climbers))

    def use_crowd(self, climbers: float):
        """Set the arrival response for a night with this many climbers (cached per crowd level)."""
        lv = self.level_of(climbers)
        if lv not in self._cache:
            self._cache[lv] = self._response(self.seed, self._crowd_field(lv))
        self.level = lv
        self.A, self.median_arrival, self.cp_to_top, self.head_to_cp, self.hall_up = self._cache[lv]
        return self

    def _crowd_field(self, climbers: int) -> np.ndarray:
        """Walking-speed factor per segment and hour on a night with `climbers` pilgrims (simulated)."""
        sim, p = self.sim, self.p
        if climbers <= 0:
            return np.ones((sim.S, 24))
        rng = np.random.default_rng([self.seed, climbers])
        size, gate, option = sim.sample_day(int(climbers), rng)
        hourly, _, _ = sim.simulate_groups(size, gate, option, np.zeros(24), np.random.default_rng(self.seed),
                                           hold=False)
        density = hourly.T / sim.length[:, None]
        return np.maximum(p["crowd_min_speed"], 1.0 / (1.0 + (density / p["crowd_rho0_per_m"]) ** 2))

    def _bin(self, t):
        return np.clip(((np.asarray(t) - self.t0) // BIN).astype(int), 0, self.n_bins - 1)

    def bin_time(self, b) -> float:
        return self.t0 + b * BIN

    # ---------- 1. where a starter is when they reach the top ----------
    def _response(self, seed, crowd):
        rng = np.random.default_rng(seed)
        n = 200
        sim = self.sim
        A = np.zeros((len(self.trails), len(self.slots), self.n_bins))
        med = np.zeros((len(self.trails), len(self.slots)))
        cp_to_top, head_to_cp = {}, {}
        hall_up = np.full((len(self.trails), len(self.slots)), np.nan)   # summit arrival when leaving the hall at slot k
        for r, t in enumerate(self.trails):
            walk = sim.options[sim.option_of_trail(t)][1]
            i = sim._turnaround(walk)
            for k, start in enumerate(self.slots):
                t0 = start + rng.uniform(0, self.c["slot_minutes"], n)
                speed = rng.lognormal(0.0, self.p["walker_speed_sd"], n)
                arr = sim._walk(walk[:i], t0, np.ones(n), speed, {}, np.zeros(24), crowd, None)
                A[r, k] = np.bincount(self._bin(arr), minlength=self.n_bins) / n
                med[r, k] = np.median(arr)
            cp = sim.checkpoint.get(t)
            if cp is not None:
                j = [s for s, _ in walk[:i]].index(cp)
                ones = np.ones(n)
                for k, start in enumerate(self.slots):    # leaving the halfway hall at each slot time
                    hall_up[r, k] = np.median(sim._walk(walk[j:i], np.full(n, float(start)), ones, ones, {},
                                                        np.zeros(24), crowd, None))
                # typical walking times around the hall at the busiest hour (live estimate, release advice)
                busy_h = 60.0 * int(np.argmin(crowd[[s for s, _ in walk[:i]]].mean(0)))
                cp_to_top[t] = float(np.median(sim._walk(walk[j:i], np.full(n, busy_h), ones, ones, {},
                                                         np.zeros(24), crowd, None)) - busy_h)
                head_to_cp[t] = float(np.median(sim._walk(walk[:j], np.full(n, busy_h), ones, ones, {},
                                                          np.zeros(24), crowd, None)) - busy_h)
        return A, med, cp_to_top, head_to_cp, hall_up

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
    def recommend(self, visitors_by_trail: dict, day=None) -> dict:
        """Advice for one night. day: the sunrise date (sets the sunrise time); visitors: expected climbers."""
        total = float(sum(visitors_by_trail.values()))
        self.use_crowd(total)
        sunrise = self.sunrise_for(day)
        D = self.demand(visitors_by_trail)
        W = self.wait_by_start(D)
        a, q, w = self.queue(D)
        early = sunrise - 60 * self.c.get("max_early_h", 2.0)      # earlier than this = hours in the cold at the top
        out = {"limit_min": self.limit, "flow_per_min": self.flow, "sunrise": _hhmm(sunrise),
               "crowd_level": self.level, "routes": {}}
        for r, t in enumerate(self.trails):
            rows = []
            for k, lab in enumerate(self.labels):
                reach = float(self.median_arrival[r, k])
                rows.append({"start": lab, "start_min": int(self.slots[k]), "evening_before": bool(self.slots[k] < 0),
                             "expected_wait_min": round(float(W[r, k])), "reach_summit": _hhmm(reach),
                             "climb_h": round((reach - self.slots[k] - self.c["slot_minutes"] / 2) / 60, 1),
                             "before_sunrise": bool(reach <= sunrise), "too_early": bool(reach < early),
                             "recommended": bool(W[r, k] <= self.limit and reach >= early)})
            good = [x for x in rows if x["recommended"] and x["before_sunrise"]]
            early_needed = False
            if not good:                 # busy night: only starts ahead of the crowd make sunrise -> arrive early
                ok = [x for x in rows if x["before_sunrise"] and x["expected_wait_min"] <= self.limit]
                good, early_needed = ok[-3:], bool(ok)
                for x in good:
                    x["recommended"] = True
            # best: reaches before sunrise (not hours early), least waiting, then the latest start
            best = min(rows, key=lambda x: (not x["before_sunrise"], x["too_early"], x["expected_wait_min"],
                                            -x["start_min"]))
            short_wait = min(rows, key=lambda x: (x["expected_wait_min"], x["start_min"]))
            usual = rows[int(np.argmin(np.abs(self.slots - self.p.get("arrival_early_mean_h", 1.5) * 60)))]
            out["routes"][t] = {"windows": rows, "best_for_sunrise": best["start"],
                                "recommended_for_sunrise": [x["start"] for x in good],
                                "early_arrival_needed": early_needed,
                                "shortest_wait": short_wait["start"], "climb_h": best["climb_h"],
                                "usual_start": usual["start"], "usual_start_climb_h": usual["climb_h"],
                                "usual_start_reaches": usual["reach_summit"],
                                "evening_plan": self.evening_plan(r, t, w, sunrise, visitors_by_trail.get(t, 0.0))}
        peak_b = int(np.argmax(q))
        windows = self.hold_windows(w)
        out["summit"] = {"peak_queue_people": round(float(q.max())), "peak_wait_min": round(float(w.max())),
                         "peak_at": _hhmm(self.bin_time(peak_b)), "bin_min": BIN, "first_bin": _hhmm(self.t0),
                         "first_bin_min": self.t0,
                         "wait_by_time": [round(float(x)) for x in w],
                         "hold_windows": [[_hhmm(a), _hhmm(b)] for a, b in windows]}
        out["halfway"] = self.release_rates(D)
        for t, r in out["halfway"].items():           # when each checkpoint must hold: earlier by the walk to the top
            walk = self.cp_to_top.get(t, 0.0)
            r["hold_windows"] = [[_hhmm(a - walk), _hhmm(b - walk)] for a, b in windows]
        return out

    def sunrise_for(self, day) -> float:
        if day is None:
            return self.sunrise_min
        lon, lat = self.cfg["area"].get("summit_point", [None, None])
        if lat is None:
            lat, lon = self.cfg["area"]["weather_point"]
        return sunrise_minutes(day, lat, lon, self.c.get("summit_elevation_m", 0.0))

    def evening_plan(self, r: int, trail: str, w: np.ndarray, sunrise: float, climbers: float) -> dict | None:
        """Start the evening before, rest at the halfway hall, leave it at a recommended time.
        Leave time: the latest one (shortest rest in the cold at the top) whose summit arrival is before sunrise
        with a wait under the limit; start window: from `night_start_h` until there is at least an hour to rest."""
        if trail not in self.cp_to_top:
            return None
        up = self.hall_up[r]                                            # summit arrival per hall-leaving slot
        leave_k = None
        for k in range(len(self.slots) - 1, -1, -1):                    # latest first
            arr = up[k]
            if np.isfinite(arr) and arr <= sunrise and w[int(self._bin(arr))] <= self.limit:
                leave_k = k
                break
        if leave_k is None:
            return None
        leave, arr = float(self.slots[leave_k]), float(up[leave_k])
        first = self.c.get("night_start_h", 18) * 60 - 1440
        last = leave - self.head_to_cp[trail] - 60                     # at least an hour's rest at the hall
        if last < first:
            return None
        resting = climbers * self.c.get("evening_share", 0.0)
        cap = self.c.get("rest_hall_capacity")
        cap = cap.get(trail) if isinstance(cap, dict) else cap
        return {"start_from": _hhmm(first), "start_to": _hhmm(last), "reach_hall_by": _hhmm(leave - 60),
                "leave_hall_at": _hhmm(leave), "reach_summit": _hhmm(arr),
                "hall_people_expected": round(resting), "hall_capacity": cap,
                "hall_may_be_full": bool(cap is not None and resting > cap)}

    def hold_windows(self, wait: np.ndarray) -> list:
        """Summit-arrival times (minutes, negative = evening before) when the expected wait is over the limit."""
        over, out, b = wait > self.limit, [], 0
        while b < len(over):
            if over[b]:
                s = b
                while b < len(over) and over[b]:
                    b += 1
                out.append((self.bin_time(s), self.bin_time(b)))
            else:
                b += 1
        return out

    def spread(self, D: np.ndarray, movers: np.ndarray, batch: float = 25.0, sunrise_penalty_min: float = 30.0,
               sunrise: float | None = None):
        """Assign pilgrims who agree to move (movers[route, from_slot]) to start windows one batch at a time,
        always to the window of the same route with the lowest expected wait *after* the earlier batches
        (+ a penalty for missing sunrise). Accounts for the effect of the advice itself: sending everyone to the
        same 'quiet' time just moves the queue (herding). Returns the new demand matrix and moves[r, from, to]."""
        D = D - movers
        moves = np.zeros((len(self.trails), len(self.slots), len(self.slots)))
        late = self.median_arrival > (self.sunrise_min if sunrise is None else sunrise)
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

    # ---------- 5. halfway checks ----------
    def release_rates(self, D: np.ndarray) -> dict:
        """People per 10 min each halfway checkpoint should let through while the summit queue is over the limit:
        the route's share of the summit flow."""
        share = D.sum(1) / max(D.sum(), 1e-9)
        return {t: {"release_per_10_min": round(float(self.flow * 10 * share[r])),
                    "walk_to_summit_min": round(self.cp_to_top.get(t, 0.0))} for r, t in enumerate(self.trails)}

    # ---------- 6. live estimate from checkpoint counts ----------
    def nowcast(self, passes: pd.DataFrame, now_min: int) -> dict:
        """passes: route, time_min (minutes after midnight of the night; negative = evening before), count.
        Returns the summit queue now and over the time it takes someone passing a checkpoint now to reach the top
        (at least an hour), and what officers should do."""
        arr = np.zeros(self.n_bins)
        for row in passes.itertuples():
            arr[int(self._bin(row.time_min + self.cp_to_top.get(row.route, 0.0)))] += row.count
        q, prev = np.zeros(self.n_bins), 0.0
        for b in range(self.n_bins):
            prev = max(0.0, prev + arr[b] - self.flow * BIN)
            q[b] = prev
        b_now = int(self._bin(now_min))
        ahead = max(60.0, max(self.cp_to_top.values(), default=0.0) + BIN)   # minutes
        horizon = q[b_now:b_now + int(np.ceil(ahead / BIN)) + 1]
        wait_now, wait_next = q[b_now] / self.flow, horizon.max() / self.flow if len(horizon) else 0.0
        hold = wait_next > self.limit
        return {"time": _hhmm(now_min), "queue_now_people": round(float(q[b_now])),
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
