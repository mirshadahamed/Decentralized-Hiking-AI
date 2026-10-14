"""Synthetic hourly occupancy simulator for the Horton Plains loop (D2).

Every hiker group is simulated individually, one day at a time:
  daily demand (calendar x season x morning rain) -> groups -> gate arrival time ->
  walk the loop segment by segment (Tobler speed x rain slowdown x crowd slowdown) + dwell at viewpoints.
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
    def __init__(self, segments: pd.DataFrame, walk: list, params: dict):
        self.p = params
        self.S = len(segments)
        self.length = segments.length_m.values
        lf = params["leisure_speed_factor"]
        self.base_time = {+1: segments.tobler_fwd_min.values / lf, -1: segments.tobler_bwd_min.values / lf}
        self.walks = [list(walk), [(s, -d) for s, d in reversed(walk)]]   # standard, reverse
        self.dwell = {int(i): params["dwell_minutes"][poi]
                      for i, poi in segments.poi.items() if poi in params["dwell_minutes"]}

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

    def simulate_day(self, n_visitors: int, precip_h: np.ndarray, rng):
        """Hourly occupancy [24, S] for one day, plus loop durations (minutes) of every group."""
        p = self.p
        size = sample_groups(n_visitors, p, rng).astype(float)
        G = len(size)
        arrive = arrival_minutes(G, p, rng)
        standard = rng.random(G) < p["standard_direction_share"]
        speed = rng.lognormal(0.0, p["walker_speed_sd"], G)
        dwell = {s: rng.lognormal(np.log(med), sd, G) for s, (med, sd) in self.dwell.items()}

        crowd = np.ones((self.S, 24))
        for _ in range(2):
            diff = np.zeros((self.S, MIN_PER_DAY + 1))
            finish = np.empty(G)
            for walk, m in zip(self.walks, (standard, ~standard)):
                if m.any():
                    finish[m] = self._walk(walk, arrive[m], size[m], speed[m],
                                           {s: v[m] for s, v in dwell.items()}, precip_h, crowd, diff)
            per_min = np.cumsum(diff, axis=1)[:, :MIN_PER_DAY]
            hourly = per_min.reshape(self.S, 24, 60).mean(axis=2)
            density = hourly / self.length[:, None]
            crowd = np.maximum(p["crowd_min_speed"], 1.0 / (1.0 + (density / p["crowd_rho0_per_m"]) ** 2))
        return hourly.T, finish - arrive, int(size.sum())


def simulate(segments, walk, weather: pd.DataFrame, cal: pd.DataFrame, params: dict, seed: int):
    """Run the whole period. Returns dict of arrays (true and observed occupancy, daily visitors)."""
    rng = np.random.default_rng(seed)
    precip = weather.precipitation.values.reshape(len(cal), 24)
    demand = daily_demand(cal, precip, params, rng)
    sim = TrailSimulator(segments, walk, params)

    occ = np.zeros((len(cal) * 24, sim.S))
    visitors = np.zeros(len(cal), dtype=int)
    durations = []
    for i in range(len(cal)):
        h, dur, v = sim.simulate_day(int(round(demand[i])), precip[i], rng)
        occ[i * 24:(i + 1) * 24] = h
        visitors[i] = v
        durations.append(np.median(dur))

    # Observation model: a headcount with multiplicative error.
    observed = rng.poisson(occ * rng.lognormal(0.0, params["obs_noise_sd"], occ.shape)).astype(float)
    return {"occ_true": occ, "occ_obs": observed, "daily_visitors": visitors,
            "median_loop_min": np.array(durations)}
