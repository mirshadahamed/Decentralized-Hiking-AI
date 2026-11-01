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
    r = realism(p)
    if r:                                                    # S1: persistent swings (AR(1) on log demand)
        phi, sd = r["demand_ar_phi"], r["demand_sd"]
        z, e = rng.normal(0.0, 1.0, len(cal)), np.zeros(len(cal))
        for i in range(len(cal)):
            e[i] = (phi * e[i - 1] if i else 0.0) + np.sqrt(1 - phi ** 2) * sd * z[i]
        noise = np.exp(e - sd ** 2 / 2)
    else:
        noise = rng.lognormal(0.0, p["daily_noise_sd"], len(cal))
    return p["base_daily_visitors"] * mult * rain * noise * (1 - closed_days(cal, p))


def closed_days(cal: pd.DataFrame, p: dict) -> np.ndarray:
    """1 on days the park is closed every year (Yala: drought closure), from simulator.closed [["MM-DD", "MM-DD"]]."""
    md = cal.index.strftime("%m-%d")
    out = np.zeros(len(cal))
    for a, b in p.get("closed", []):
        out[(md >= a) & (md <= b)] = 1.0
    return out


def day_sightings(p: dict, rng, hotspot_weight: np.ndarray) -> list:
    """Wildlife sightings that stop jeeps (safari parks, simulator.sightings): (segment, start min, end min).
    A leopard by the road holds every passing jeep for a while; where and when is not in any calendar."""
    c = p.get("sightings")
    if not c:
        return []
    w = hotspot_weight / hotspot_weight.sum()
    out = []
    for _ in range(rng.poisson(c["per_day"])):
        lo, hi = c["windows_h"][int(rng.integers(len(c["windows_h"])))]
        start = rng.uniform(lo, hi) * 60
        out.append((int(rng.choice(len(w), p=w)), start, start + rng.lognormal(np.log(c["duration_min"][0]),
                                                                              c["duration_min"][1])))
    return out


def realism(p: dict) -> dict | None:
    """The S1 'realistic world' parameters if switched on (configs: simulator.realism.enabled), else None."""
    r = p.get("realism") or {}
    return r if r.get("enabled") else None


def day_events(p: dict, rng, n_segments: int, main_trail: str) -> dict:
    """What makes one day different from what the calendar and weather say (S1), drawn once per day:
    shift of the arrival peak, route shares, tour-bus bursts and an incident slowing one segment."""
    r = realism(p)
    if not r:
        return {}
    share = dict(p["route_share"])
    keys = list(share)
    w = rng.dirichlet(np.array([share[k] for k in keys]) * r["route_share_concentration"])
    ev = {"arrival_shift_min": float(rng.normal(0.0, r["arrival_shift_sd_min"])),
          "route_share": dict(zip(keys, w)), "bursts": [], "slow": None}
    for _ in range(rng.poisson(r["bursts_per_day"])):
        ev["bursts"].append({"people": int(rng.integers(*r["burst_people"])),
                             "time_min": float(rng.uniform(*r["burst_window_h"]) * 60),
                             "trail": main_trail if rng.random() < r["burst_main_share"] else
                             str(rng.choice([k for k in keys if k != main_trail] or [main_trail]))})
    if rng.random() < r["incident_prob"]:
        slow = np.ones((n_segments, 24))
        s, h = int(rng.integers(n_segments)), int(rng.integers(*r["incident_start_h"]))
        slow[s, h:h + int(rng.integers(*r["incident_hours"]))] = r["incident_speed"]
        ev["slow"] = slow
    return ev


def sample_groups(n_visitors: int, p: dict, rng) -> np.ndarray:
    if n_visitors <= 0:                               # closed day (no draws, so other parks' streams are unchanged)
        return np.zeros(0, dtype=int)
    mean = 1 + p["group_size_poisson_mean"]
    sizes = 1 + rng.poisson(p["group_size_poisson_mean"], int(n_visitors / mean * 1.3) + 5)
    keep = np.searchsorted(np.cumsum(sizes), n_visitors) + 1
    return sizes[:keep]


def guided_regroup(size, arrive, option, trail_of_option, p: dict, rng):
    """K3: walkers on guided treks go as guided groups (simulator.guided_groups: trails, size [lo, hi], start_h, start_sd_h).
    The people on each guided trail are kept; they are regrouped into groups of lo..hi that leave the entry together
    around start_h. Parks without guided_groups are unchanged (no draws)."""
    g = p.get("guided_groups")
    if not g or len(size) == 0:
        return size, arrive, option
    lo, hi = g["size"]
    keep = ~np.isin(trail_of_option[option], g["trails"])
    out = [(size[keep], arrive[keep], option[keep])]
    for k in np.unique(option[~keep]):
        people = int(size[option == k].sum())
        sizes = []
        while people > 0:
            n = min(int(rng.integers(lo, hi + 1)), people)
            sizes.append(n)
            people -= n
        t = np.clip(rng.normal(g["start_h"], g["start_sd_h"], len(sizes)), p["gate_open_h"], p["gate_last_entry_h"])
        out.append((np.array(sizes, float), t * 60, np.full(len(sizes), k)))
    return tuple(np.concatenate(x) for x in zip(*out))


def rain_closed(trails: list, precip_h: np.ndarray, p: dict) -> list:
    """K3: trails with river crossings close for the day when the rain from 06:00 to 12:00 reaches the threshold
    (simulator.rain_closures: {trail: mm}). Their walkers stay away (no trek that day)."""
    morning = float(np.asarray(precip_h)[6:12].sum())
    return [t for t, mm in (p.get("rain_closures") or {}).items() if t in trails and morning >= mm]


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
        # where sightings happen: segments near the listed hotspots weigh more (safari parks only)
        hot = set((params.get("sightings") or {}).get("hotspots", []))
        self.hotspot_weight = np.where(segments.poi.fillna("").isin(hot), (params.get("sightings") or {}).get(
            "hotspot_weight", 1.0), 1.0).astype(float)
        self.sightings = []          # set per day by simulate_day
        # sighting management (None = every passing jeep stops): {"cap_jeeps": K, "rotation_min": R}
        self.sighting_policy = (params.get("sightings") or {}).get("policy")
        self.last_sighting_stats = {}

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

    def _walk(self, walk, arrive, size, speed, dwell, precip_h, crowd, diff, visited=None, hold=None, stops=None,
              record=None):
        """Walk the steps of `walk` from times `arrive`. diff=None: only compute times (no occupancy recorded).
        hold: {segment: minutes per group} extra waiting on that segment (halfway checks).
        stops: {segment: [(start, end, minutes per group)]} sightings that hold groups arriving in [start, end).
        record: {segment: array} filled with each group's first arrival time on that segment."""
        p, t = self.p, arrive.copy()
        visited = set() if visited is None else visited
        stops = stops or {}
        for s, d in walk:
            hour = np.clip((t // 60).astype(int), 0, 23)
            rain = np.where(precip_h[hour] >= p["rain_heavy_mm"], p["rain_heavy_speed"],
                            np.where(precip_h[hour] >= p["rain_light_mm"], p["rain_light_speed"], 1.0))
            dur = self.base_time[d][s] / (speed * rain * crowd[s, hour])
            if s in dwell and s not in visited:      # stop once at each viewpoint
                dur = dur + dwell[s]
            if hold is not None and s in hold and s not in visited:
                dur = dur + hold[s]
            for a, b, stop in stops.get(s, ()):
                dur = dur + np.where((t >= a) & (t < b), stop, 0.0)
            if record is not None and s in record and s not in visited:
                record[s] = t.copy()
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

    def sample_day(self, n_visitors: int, rng, route_share=None, events: dict | None = None):
        """The groups that *want* to come: size, gate time (minutes) and route option of each group.
        events (S1, day_events): the day's arrival shift, route shares and tour-bus bursts."""
        p, ev = self.p, events or {}
        size = sample_groups(n_visitors, p, rng).astype(float)
        arrive = arrival_minutes(len(size), p, rng)
        if ev:
            arrive = np.clip(arrive + ev["arrival_shift_min"], p["gate_open_h"] * 60, p["gate_last_entry_h"] * 60)
        option = rng.choice(len(self.options), size=len(size), p=self.option_probs(route_share or ev.get("route_share")))
        for b in ev.get("bursts", []):                     # a bus: groups of ~10 through the gate within 15 min
            g = sample_groups(b["people"], p | {"group_size_poisson_mean": 9.0}, rng).astype(float)
            size = np.concatenate([size, g])
            arrive = np.concatenate([arrive, b["time_min"] + rng.uniform(0, 15, len(g))])
            option = np.concatenate([option, np.full(len(g), self.option_of_trail(b["trail"]))])
        return guided_regroup(size, arrive, option, np.array([t for t, _ in self.options]), p, rng)

    def _manage_sightings(self, stops, size, arrive, option, speed, dwell, precip_h):
        """Ranger at the sighting: first come, first served, at most `cap_jeeps` stopped at once, each for at most
        `rotation_min`; a jeep that finds it full is moved on (no stop). Arrival times come from a dry run of the day
        without sighting stops (an approximation: earlier stops are not in it)."""
        pol = self.sighting_policy
        cap, rot = int(pol.get("cap_jeeps") or 10 ** 9), float(pol.get("rotation_min") or np.inf)
        G = len(size)
        arr = {s: np.full(G, np.inf) for s in stops}
        ones = np.ones((self.S, 24))
        for k, (_, walk) in enumerate(self.options):
            m = option == k
            if not m.any():
                continue
            rec = {s: np.full(int(m.sum()), np.inf) for s in stops}
            self._walk(walk, arrive[m], size[m], speed[m], {s: v[m] for s, v in dwell.items()}, precip_h, ones, None,
                       record=rec)
            for s in stops:
                arr[s][m] = rec[s]
        out, viewed, moved = {}, 0, 0
        for s, items in stops.items():
            out[s] = []
            for a, b, stop in items:
                new = np.zeros(G)
                busy_until = []                                      # end times of the jeeps stopped now
                for g in np.argsort(arr[s], kind="stable"):
                    t = arr[s][g]
                    if not (a <= t < b):
                        continue
                    busy_until = [e for e in busy_until if e > t]
                    if len(busy_until) < cap:
                        new[g] = min(stop[g], rot)
                        busy_until.append(t + new[g])
                        viewed += 1
                    else:
                        moved += 1
                out[s].append((a, b, new))
        self.last_sighting_stats = {"viewed": viewed, "moved_on": moved}
        return out

    def option_of_trail(self, trail: str, reverse: bool = False) -> int:
        return next(k for k, ((t, _), rev) in enumerate(zip(self.options, self.reverse))
                    if t == trail and rev == (reverse and trail in self.p.get("reversible_routes", [])))

    def simulate_groups(self, size, gate_min, option, precip_h, rng, hold: bool | None = None, slow=None):
        """Walk the given groups. Returns hourly occupancy [24, S], per-minute occupancy [S, 1440],
        and the time each group spent (minutes).
        hold: halfway checks on/off (parks with a bottleneck; default from config `bottleneck.hold`).
        slow: [S, 24] speed factor of an incident (S1), e.g. 0.3 on one segment for two hours."""
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
        stops = {}
        if self.sightings:
            med, sd = p["sightings"]["stop_min"]
            for s, a, b in self.sightings:
                stops.setdefault(s, []).append((a, b, rng.lognormal(np.log(med), sd, G)))

        if stops and self.sighting_policy is not None:      # {} = count only, every passing jeep stops
            stops = self._manage_sightings(stops, size, arrive, option, speed, dwell, precip_h)

        if hold is None:
            hold = bool((p.get("bottleneck") or {}).get("hold", False))
        stay_seed = int(rng.integers(2 ** 31)) if getattr(self, "bottleneck", None) else 0   # same stays in both passes
        crowd = np.ones((self.S, 24)) if slow is None else np.array(slow, float)
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
                                               {s: v[m] for s, v in dwell.items()}, precip_h, crowd, diff,
                                               stops={s: [(a, b, v[m]) for a, b, v in x] for s, x in stops.items()})
            per_min = np.cumsum(diff, axis=1)[:, :MIN_PER_DAY]
            hourly = per_min.reshape(self.S, 24, 60).mean(axis=2)
            density = hourly / self.length[:, None]
            crowd = np.maximum(p["crowd_min_speed"], 1.0 / (1.0 + (density / p["crowd_rho0_per_m"]) ** 2))
            if slow is not None:
                crowd = crowd * slow
        return hourly.T, per_min, finish - arrive

    def simulate_day(self, n_visitors: int, precip_h: np.ndarray, rng, route_share=None):
        """One day. Returns hourly occupancy [24, S], main-loop durations (min), visitors per trail (dict).
        route_share overrides the config split (used for what-if diversion experiments).
        With simulator.realism on (S1), the day also gets its own events (day_events)."""
        ev = day_events(self.p, rng, self.S, self.trails[0]) if realism(self.p) else {}
        self.sightings = day_sightings(self.p, rng, self.hotspot_weight)
        size, gate, option = self.sample_day(n_visitors, rng, route_share, ev)
        closed = rain_closed(self.trails, precip_h, self.p)
        if closed:
            open_ = ~np.isin(np.array([t for t, _ in self.options])[option], closed)
            size, gate, option = size[open_], gate[open_], option[open_]
        hourly, _, duration = self.simulate_groups(size, gate, option, precip_h, rng, slow=ev.get("slow"))
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
