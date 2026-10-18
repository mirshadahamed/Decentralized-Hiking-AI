"""Synthetic hourly occupancy simulator for the Horton Plains trail network (D2).

Every hiker group is simulated individually, one day at a time:
  daily park demand (calendar x season x morning rain) -> groups -> gate arrival time ->
  choice of trail (World's End loop either way, Kirigalpotta, Thotupola) ->
  walk it segment by segment (Tobler speed x rain slowdown x crowd slowdown) + dwell at viewpoints and peaks.
Occupancy of a segment in an hour = average number of people on it during that hour.
The crowd slowdown needs occupancy, so each day is simulated twice (second pass uses the first pass's density).
All parameters live in configs/default.yaml and are justified in docs/assumptions.md.
"""
import numpy as np
import pandas as pd

MIN_PER_DAY = 24 * 60


def daily_demand(cal: pd.DataFrame, precip_day: np.ndarray, p: dict, rng) -> np.ndarray:
    """Expected number of visitors for every day."""
    dow = np.array(p["dow_multiplier"])[cal.dow.values]
    day_type = np.maximum.reduce([dow,
                                  np.where(cal.is_holiday, p["holiday_multiplier"], 1.0),
                                  np.where(cal.is_poya, p["poya_multiplier"], 1.0)])
    mult = (day_type
            * np.where(cal.is_long_weekend, p["long_weekend_multiplier"], 1.0)
            * np.where(cal.is_school_holiday, p["school_holiday_multiplier"], 1.0)
            * np.array(p["month_multiplier"])[cal.index.month.values - 1])
    if "is_season" in cal:                                   # pilgrimage season (Adam's Peak)
        mult = mult * np.where(cal.is_season, p.get("season_multiplier", 1.0), p.get("off_season_multiplier", 1.0))
    morning_rain = precip_day[:, 5:10].sum(axis=1)
    rain = np.maximum(p["min_rain_multiplier"], np.exp(-p["morning_rain_k"] * morning_rain))
    noise = rng.lognormal(0.0, p["daily_noise_sd"], len(cal))
    return p["base_daily_visitors"] * mult * rain * noise


def sample_groups(n_visitors: int, p: dict, rng) -> np.ndarray:
    mean = 1 + p["group_size_poisson_mean"]
    sizes = 1 + rng.poisson(p["group_size_poisson_mean"], int(n_visitors / mean * 1.3) + 5)
    keep = np.searchsorted(np.cumsum(sizes), n_visitors) + 1
    return sizes[:keep]


def arrival_minutes(n: int, p: dict, rng) -> np.ndarray:
    early = rng.random(n) < p["arrival_early_share"]
    t = np.where(early,
                 rng.normal(p["arrival_early_mean_h"], p["arrival_early_sd_h"], n),
                 rng.uniform(*p["arrival_late_range_h"], n))
    return np.clip(t, p["gate_open_h"], p["gate_last_entry_h"]) * 60


class TrailSimulator:
    def __init__(self, segments: pd.DataFrame, walks: dict, params: dict):
        self.p = params
        self.S = len(segments)
        self.length = segments.length_m.values
        lf = params["leisure_speed_factor"]
        self.base_time = {+1: segments.tobler_fwd_min.values / lf, -1: segments.tobler_bwd_min.values / lf}
        # Route options: every route as walked; loops listed in reversible_routes also in reverse.
        # (Horton Plains: main loop both ways, then Kirigalpotta, Thotupola.)
        self.trails = list(walks)
        reversible = set(params.get("reversible_routes", []))
        self.options, self.reverse = [], []
        for t, w in walks.items():
            self.options.append((t, list(w)))
            self.reverse.append(False)
            if t in reversible:
                self.options.append((t, [(s, -d) for s, d in reversed(w)]))
                self.reverse.append(True)
        self.dwell = {int(i): params["dwell_minutes"][poi]
                      for i, poi in segments.poi.items() if poi in params["dwell_minutes"]}
        self.setup_bottleneck(segments)

    def option_probs(self, route_share=None):
        share = dict(route_share or self.p["route_share"])
        std = self.p.get("standard_direction_share", 1.0)
        reversible = set(self.p.get("reversible_routes", []))
        probs = []
        for (t, _), rev in zip(self.options, self.reverse):
            split = (1 - std if rev else std) if t in reversible else 1.0
            probs.append(share.get(t, 0.0) * split)
        probs = np.array(probs)
        return probs / probs.sum()

    def _walk(self, walk, arrive, size, speed, dwell, precip_h, crowd, diff, visited=None, hold=None):
        """Walk the steps of `walk` from times `arrive`. diff=None: only compute times (no occupancy recorded).
        hold: {segment: minutes per group} extra waiting on that segment (halfway checks)."""
        p, t = self.p, arrive.copy()
        visited = set() if visited is None else visited
        for s, d in walk:
            hour = np.clip((t // 60).astype(int), 0, 23)
            rain = np.where(precip_h[hour] >= p["rain_heavy_mm"], p["rain_heavy_speed"],
                            np.where(precip_h[hour] >= p["rain_light_mm"], p["rain_light_speed"], 1.0))
            dur = self.base_time[d][s] / (speed * rain * crowd[s, hour])
            if s in dwell and s not in visited:      # stop once at each viewpoint
                dur = dur + dwell[s]
            if hold is not None and s in hold and s not in visited:
                dur = dur + hold[s]
            visited.add(s)
            if diff is not None:
                start = np.clip(np.round(t).astype(int), 0, MIN_PER_DAY)
                end = np.clip(np.round(t + dur).astype(int), 0, MIN_PER_DAY)
                np.add.at(diff[s], start, size)
                np.add.at(diff[s], end, -size)
            t = t + dur
        return t

    # ---------- summit queue (parks with a `bottleneck` in the simulator config) ----------
    def setup_bottleneck(self, segments: pd.DataFrame):
        """Summit queue for out-and-back routes that meet at one summit (Adam's Peak).
        The bottleneck is the turnaround of every route (the summit); each route's halfway checkpoint comes
        from the POI tag half_<route>."""
        b = self.p.get("bottleneck")
        self.bottleneck = None
        if not b:
            return
        self.bottleneck = "turnaround"
        self.flow = float(b["flow_per_min"])
        self.summit_dwell = b.get("summit_dwell_min", [45, 0.4])     # median minutes, log-sd
        poi = segments.poi.fillna("").values
        self.checkpoint = {t: int(np.where(poi == f"half_{t}")[0][0]) for t in self.trails
                           if (poi == f"half_{t}").any()}

    @staticmethod
    def _turnaround(walk) -> int | None:
        """Index of the first step down (out-and-back walks: second half reverses the first)."""
        n = len(walk)
        if n % 2 == 0 and all(walk[i][0] == walk[n - 1 - i][0] for i in range(n // 2)):
            return n // 2
        return None

    def _queue(self, t_arr, size):
        """First come, first served through the bottleneck at `flow` people per minute. Returns entry times."""
        order = np.argsort(t_arr, kind="stable")
        entry = np.empty_like(t_arr)
        free = -np.inf
        for g in order:
            entry[g] = max(t_arr[g], free)
            free = entry[g] + size[g] / self.flow
        return entry

    @staticmethod
    def _occupy(diff, s, t0, t1, size):
        a = np.clip(np.round(t0).astype(int), 0, MIN_PER_DAY)
        b = np.clip(np.round(t1).astype(int), 0, MIN_PER_DAY)
        np.add.at(diff[s], a, size)
        np.add.at(diff[s], b, -size)

    def _walk_with_queue(self, size, arrive, option, speed, dwell, precip_h, crowd, diff, hold_mode, rng=None):
        """Climb to the summit, queue to get onto it (first come, first served at `flow` people/min), stay for
        sunrise, then go down. The wait is on the final steps (segment below the top) or, with hold_mode, at the
        route's halfway checkpoint, where officers hold groups so they reach the top when there is room."""
        G = len(size)
        t_arr, split = np.full(G, np.inf), {}
        for k, (_, walk) in enumerate(self.options):
            m = option == k
            i = self._turnaround(walk)
            if not m.any() or i is None:
                continue
            split[k] = i
            t_arr[m] = self._walk(walk[:i], arrive[m], size[m], speed[m], {s: v[m] for s, v in dwell.items()},
                                  precip_h, crowd, None)
        has = np.isfinite(t_arr)
        entry = t_arr.copy()
        entry[has] = self._queue(t_arr[has], size[has])
        wait = np.where(has, entry - t_arr, 0.0)
        med, sd = self.summit_dwell
        stay = (rng.lognormal(np.log(med), sd, G) if rng is not None else np.full(G, float(med)))
        finish = np.empty(G)
        for k, (trail, walk) in enumerate(self.options):
            m = option == k
            if not m.any():
                continue
            dw = {s: v[m] for s, v in dwell.items()}
            if k not in split:                                   # route that does not reach the summit
                finish[m] = self._walk(walk, arrive[m], size[m], speed[m], dw, precip_h, crowd, diff)
                continue
            i, visited = split[k], set()
            cp = self.checkpoint.get(trail)
            hold = {cp: wait[m]} if hold_mode and cp is not None else None
            t = self._walk(walk[:i], arrive[m], size[m], speed[m], dw, precip_h, crowd, diff, visited, hold)
            top = walk[i - 1][0]
            queue_seg = walk[i - 2][0] if i >= 2 else top
            if hold is None:                                     # queue on the final steps below the top
                self._occupy(diff, queue_seg, t_arr[m], entry[m], size[m])
            start = np.maximum(t, entry[m])
            self._occupy(diff, top, start, start + stay[m], size[m])   # on the summit for sunrise
            finish[m] = self._walk(walk[i:], start + stay[m], size[m], speed[m], dw, precip_h, crowd, diff, visited)
        self.last_wait = wait
        return finish

    def sample_day(self, n_visitors: int, rng, route_share=None):
        """The groups that *want* to come: size, gate time (minutes) and route option of each group."""
        p = self.p
        size = sample_groups(n_visitors, p, rng).astype(float)
        arrive = arrival_minutes(len(size), p, rng)
        option = rng.choice(len(self.options), size=len(size), p=self.option_probs(route_share))
        return size, arrive, option

    def option_of_trail(self, trail: str, reverse: bool = False) -> int:
        return next(k for k, ((t, _), rev) in enumerate(zip(self.options, self.reverse))
                    if t == trail and rev == (reverse and trail in self.p.get("reversible_routes", [])))

    def simulate_groups(self, size, gate_min, option, precip_h, rng, hold: bool | None = None):
        """Walk the given groups. Returns hourly occupancy [24, S], per-minute occupancy [S, 1440],
        and the time each group spent (minutes).
        hold: halfway checks on/off (parks with a bottleneck; default from config `bottleneck.hold`)."""
        p = self.p
        size, option = np.asarray(size, float), np.asarray(option)
        arrive = np.array(gate_min, dtype=float)
        G = len(size)
        for k, (trail, _) in enumerate(self.options):
            m = option == k
            if trail in p.get("route_last_entry_h", {}):
                arrive[m] = np.minimum(arrive[m], p["route_last_entry_h"][trail] * 60)
            arrive[m] += p.get("route_start_offset_min", {}).get(trail, 0)
        speed = rng.lognormal(0.0, p["walker_speed_sd"], G)
        dwell = {s: rng.lognormal(np.log(med), sd, G) for s, (med, sd) in self.dwell.items()}

        if hold is None:
            hold = bool((p.get("bottleneck") or {}).get("hold", False))
        stay_seed = int(rng.integers(2 ** 31)) if getattr(self, "bottleneck", None) else 0   # same stays in both passes
        crowd = np.ones((self.S, 24))
        for _ in range(2):
            diff = np.zeros((self.S, MIN_PER_DAY + 1))
            finish = np.empty(G)
            if getattr(self, "bottleneck", None) is not None:
                finish = self._walk_with_queue(size, arrive, option, speed, dwell, precip_h, crowd, diff, hold,
                                               np.random.default_rng(stay_seed))
            else:
                for k, (_, walk) in enumerate(self.options):
                    m = option == k
                    if m.any():
                        finish[m] = self._walk(walk, arrive[m], size[m], speed[m],
                                               {s: v[m] for s, v in dwell.items()}, precip_h, crowd, diff)
            per_min = np.cumsum(diff, axis=1)[:, :MIN_PER_DAY]
            hourly = per_min.reshape(self.S, 24, 60).mean(axis=2)
            density = hourly / self.length[:, None]
            crowd = np.maximum(p["crowd_min_speed"], 1.0 / (1.0 + (density / p["crowd_rho0_per_m"]) ** 2))
        return hourly.T, per_min, finish - arrive

    def simulate_day(self, n_visitors: int, precip_h: np.ndarray, rng, route_share=None):
        """One day. Returns hourly occupancy [24, S], main-loop durations (min), visitors per trail (dict).
        route_share overrides the config split (used for what-if diversion experiments)."""
        size, gate, option = self.sample_day(n_visitors, rng, route_share)
        hourly, _, duration = self.simulate_groups(size, gate, option, precip_h, rng)
        trail_of = np.array([self.options[k][0] for k in option])
        per_trail = {t: int(size[trail_of == t].sum()) for t in self.trails}
        return hourly, duration[trail_of == self.trails[0]], per_trail   # durations on the first (main) trail


def simulate(segments, walks: dict, weather: pd.DataFrame, cal: pd.DataFrame, params: dict, seed: int):
    """Run the whole period. Returns dict of arrays (true and observed occupancy, visitors per day and trail)."""
    rng = np.random.default_rng(seed)
    precip = weather.precipitation.values.reshape(len(cal), 24)
    demand = daily_demand(cal, precip, params, rng)
    sim = TrailSimulator(segments, walks, params)

    occ = np.zeros((len(cal) * 24, sim.S))
    by_trail = np.zeros((len(cal), len(sim.trails)), dtype=int)
    durations = []
    for i in range(len(cal)):
        h, dur, v = sim.simulate_day(int(round(demand[i])), precip[i], rng)
        occ[i * 24:(i + 1) * 24] = h
        by_trail[i] = [v[t] for t in sim.trails]
        durations.append(np.median(dur) if len(dur) else np.nan)

    # Observation model: a headcount with multiplicative error.
    observed = rng.poisson(occ * rng.lognormal(0.0, params["obs_noise_sd"], occ.shape)).astype(float)
    return {"occ_true": occ, "occ_obs": observed, "daily_visitors": by_trail.sum(1),
            "daily_visitors_by_trail": by_trail, "trails": sim.trails,
            "median_loop_min": np.array(durations)}
