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
        # Route options: the main loop in both directions, plus every other trail (out and back).
        self.trails = list(walks)
        main = walks["main"]
        self.options = [("main", list(main)), ("main", [(s, -d) for s, d in reversed(main)])]
        self.options += [(t, list(w)) for t, w in walks.items() if t != "main"]
        self.dwell = {int(i): params["dwell_minutes"][poi]
                      for i, poi in segments.poi.items() if poi in params["dwell_minutes"]}

    def option_probs(self, route_share=None):
        share = dict(route_share or self.p["route_share"])
        std = self.p["standard_direction_share"]
        main = share.get("main", 0.0)
        probs = [main * std, main * (1 - std)] + [share.get(t, 0.0) for t, _ in self.options[2:]]
        probs = np.array(probs)
        return probs / probs.sum()

    def _walk(self, walk, arrive, size, speed, dwell, precip_h, crowd, diff):
        p, t = self.p, arrive.copy()
        visited = set()
        for s, d in walk:
            hour = np.clip((t // 60).astype(int), 0, 23)
            rain = np.where(precip_h[hour] >= p["rain_heavy_mm"], p["rain_heavy_speed"],
                            np.where(precip_h[hour] >= p["rain_light_mm"], p["rain_light_speed"], 1.0))
            dur = self.base_time[d][s] / (speed * rain * crowd[s, hour])
            if s in dwell and s not in visited:      # stop once at each viewpoint
                dur = dur + dwell[s]
            visited.add(s)
            start = np.clip(np.round(t).astype(int), 0, MIN_PER_DAY)
            end = np.clip(np.round(t + dur).astype(int), 0, MIN_PER_DAY)
            np.add.at(diff[s], start, size)
            np.add.at(diff[s], end, -size)
            t = t + dur
        return t

    def simulate_day(self, n_visitors: int, precip_h: np.ndarray, rng, route_share=None):
        """One day. Returns hourly occupancy [24, S], main-loop durations (min), visitors per trail (dict).
        route_share overrides the config split (used for what-if diversion experiments)."""
        p = self.p
        size = sample_groups(n_visitors, p, rng).astype(float)
        G = len(size)
        arrive = arrival_minutes(G, p, rng)
        option = rng.choice(len(self.options), size=G, p=self.option_probs(route_share))
        for k, (trail, _) in enumerate(self.options):
            m = option == k
            if trail in p.get("route_last_entry_h", {}):
                arrive[m] = np.minimum(arrive[m], p["route_last_entry_h"][trail] * 60)
            arrive[m] += p.get("route_start_offset_min", {}).get(trail, 0)
        speed = rng.lognormal(0.0, p["walker_speed_sd"], G)
        dwell = {s: rng.lognormal(np.log(med), sd, G) for s, (med, sd) in self.dwell.items()}

        crowd = np.ones((self.S, 24))
        for _ in range(2):
            diff = np.zeros((self.S, MIN_PER_DAY + 1))
            finish = np.empty(G)
            for k, (_, walk) in enumerate(self.options):
                m = option == k
                if m.any():
                    finish[m] = self._walk(walk, arrive[m], size[m], speed[m],
                                           {s: v[m] for s, v in dwell.items()}, precip_h, crowd, diff)
            per_min = np.cumsum(diff, axis=1)[:, :MIN_PER_DAY]
            hourly = per_min.reshape(self.S, 24, 60).mean(axis=2)
            density = hourly / self.length[:, None]
            crowd = np.maximum(p["crowd_min_speed"], 1.0 / (1.0 + (density / p["crowd_rho0_per_m"]) ** 2))
        trail_of = np.array([self.options[k][0] for k in option])
        per_trail = {t: int(size[trail_of == t].sum()) for t in self.trails}
        main = option < 2
        return hourly.T, (finish - arrive)[main], per_trail


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
