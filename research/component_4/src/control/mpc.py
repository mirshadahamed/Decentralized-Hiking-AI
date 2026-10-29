"""Closed-loop crowd control at the gate: model predictive control (MPC), re-planned every slot.

Every 30-minute slot during the day the controller
  1. measures   who went through the gate so far (trail, time, group size) - the only sensor it needs;
  2. estimates  where they are now and over the next hours (entry-control response table K, slots.py);
  3. forecasts  who is still to come per trail and slot: the day's expected visitors x the usual arrival pattern,
                corrected by feedback - the ratio of arrivals so far to arrivals expected so far;
  4. decides    entry caps per trail for the next `horizon` slots with a linear programme: admit as many people as
                possible (popular slots first) while every section stays under margin x its capacity in every half
                hour (soft: overload is allowed only at a high cost, if people already inside make it unavoidable);
  5. acts       on the current slot only: groups within the cap enter; the others wait (up to `max_hold_min`), and
                then are offered a trail with room - a share `compliance` accepts, the rest are turned away.
Then the next slot is planned again with the new gate counts (receding horizon).

Unlike the day-ahead slot plan (policy D), the caps follow what the day really brings: a bus group, a quiet
rainy morning, a late rush. src.control.evaluate_mpc compares it with the other policies.
"""
import numpy as np
from scipy.optimize import linprog

from src.control.slots import EntryControl


class MPCController:
    def __init__(self, ec: EntryControl, horizon: int = 6, margin: float | None = None, max_hold_min: int | None = None,
                 compliance: float = 0.5, feedback: bool = True, queue_priority: float = 3.0):
        """margin / max_hold_min: default the slot plan's safety margin and slot shift (a fair comparison with D).
        queue_priority: weight of people really waiting now vs forecast arrivals (do not hold back for guesses)."""
        self.ec, self.H = ec, horizon
        self.margin = ec.c["safety_margin"] if margin is None else margin
        self.max_hold = ec.c["max_slot_shift_h"] * 60 if max_hold_min is None else max_hold_min
        self.compliance, self.feedback, self.queue_priority = compliance, feedback, queue_priority
        self.trail_of_option = np.array([ec.trails.index(ec.sim.options[o][0]) for o in range(len(ec.sim.options))])
        # share of a day's visitors per trail and slot (the usual pattern)
        p = ec.sim.p
        share = np.array([p["route_share"].get(t, 0.0) for t in ec.trails])
        self.pattern = np.outer(share / share.sum(), ec.slot_share)            # [trail, slot]

    def _plan(self, k: int, inside: np.ndarray, demand: np.ndarray, K: np.ndarray, C: np.ndarray) -> np.ndarray:
        """Caps a[trail, slot] for slots k .. k+H-1. inside: [segment, bin] occupancy of those admitted so far;
        demand: [trail, slot] who would enter if allowed (now: real queue; later: forecast)."""
        ec = self.ec
        R, S_ = len(ec.trails), len(ec.slots)
        ks = [j for j in range(k, min(k + self.H, S_))]
        xs = [(r, j) for r in range(R) for j in ks if ec.allowed[r, j] and demand[r, j] > 0]
        if not xs:
            return np.zeros((R, S_))
        # bins the plan can affect: from now until the last horizon slot's walkers are out
        b0 = ec.slots[k] // ec.c["bin_minutes"]
        bins = np.arange(b0, ec.n_bins)
        fin = np.where(np.isfinite(C))[0]
        rows, b = [], []
        cap = self.margin * C
        for s in fin:
            coef = np.array([K[r, j, s][bins] for r, j in xs]).T                # [bins, vars]
            use = coef.max(axis=1) > 1e-6
            for i in np.nonzero(use)[0]:
                rows.append(coef[i])
                b.append(cap[s] - inside[s, bins[i]])
        nx = len(xs)
        nc = len(rows)
        pop = ec.slot_share / ec.slot_share.max()
        # variables: caps (nx), then one slack per constraint row (overload allowed at a high cost)
        c = np.concatenate([[-(self.queue_priority if j == k else 1 + pop[j]) for _, j in xs], np.full(nc, 1000.0)])
        A = np.hstack([np.array(rows), -np.eye(nc)]) if nc else np.zeros((0, nx))
        bounds = [(0, float(demand[r, j])) for r, j in xs] + [(0, None)] * nc
        res = linprog(c, A_ub=A if nc else None, b_ub=np.array(b) if nc else None, bounds=bounds, method="highs")
        a = np.zeros((R, S_))
        if res.success:
            for (r, j), v in zip(xs, res.x[:nx]):
                a[r, j] = v
        return a

    def run_day(self, size, gate, option, rain_share: float, expected_visitors: float, rng, priority=None) -> tuple:
        """One day at the gate. Returns admitted (size, gate_min, option) and counts (refused, redirected, held,
        mean wait in minutes of those who waited)."""
        ec = self.ec
        K, C = ec.response(rain_share), ec.capacity(rain_share)
        R, S_ = len(ec.trails), len(ec.slots)
        sm = ec.c["slot_minutes"]
        slot = ec.slot_of(gate)
        queue: list = []                                                       # (group, wanted gate time)
        inside = np.zeros((ec.sim.S, ec.n_bins))
        out_size, out_gate, out_opt = [], [], []
        stats = {"refused": 0.0, "redirected": 0.0, "held": 0.0, "wait_sum": 0.0, "wait_n": 0.0}
        self._prio = priority
        arrived_so_far, expected_so_far = 0.0, 0.0
        for k in range(S_):
            now = ec.slots[k]
            new = [(int(g), float(gate[g])) for g in np.where(slot == k)[0]]
            queue += new
            # groups that came at their advised start time go first (N3); otherwise first come, first served
            queue.sort(key=lambda x: (not (priority is not None and priority[x[0]]), x[1]))
            arrived_so_far += float(size[slot == k].sum())
            expected_so_far += expected_visitors * ec.slot_share[k]
            ratio = (np.clip(arrived_so_far / max(expected_so_far, 1.0), 0.5, 2.0)
                     if self.feedback and expected_so_far > 20 else 1.0)
            demand = self.pattern * expected_visitors * ratio                 # forecast for the coming slots
            demand[:, k] = 0.0
            for g, _ in queue:                                                 # the real queue for this slot
                demand[self.trail_of_option[option[g]], k] += size[g]
            caps = self._plan(k, inside, demand, K, C)[:, k]
            used = np.zeros(R)
            still = []
            for g, wanted in queue:
                r = self.trail_of_option[option[g]]
                if used[r] + size[g] <= caps[r] + 1e-6:
                    used[r] += size[g]
                    t = max(wanted, now) if wanted >= now else now + rng.uniform(0, sm)
                    self._enter(g, r, option[g], t, size, inside, K, out_size, out_gate, out_opt, stats, wanted)
                    continue
                if now + sm - wanted <= self.max_hold and k + 1 < S_:          # wait for the next slot
                    still.append((g, wanted))
                    continue
                spare = [rr for rr in range(R) if rr != r and caps[rr] - used[rr] >= size[g] and ec.allowed[rr, k]]
                if spare and rng.random() < self.compliance:                   # offered another trail with room
                    rr = max(spare, key=lambda x: caps[x] - used[x])
                    used[rr] += size[g]
                    stats["redirected"] += size[g]
                    self._enter(g, rr, ec.sim.option_of_trail(ec.trails[rr]), now + rng.uniform(0, sm), size,
                                inside, K, out_size, out_gate, out_opt, stats, wanted)
                else:
                    stats["refused"] += size[g]
            queue = still
        for g, _ in queue:
            stats["refused"] += size[g]
        return (np.array(out_size, float), np.array(out_gate, float), np.array(out_opt, int), stats)

    def _capacity(self, rain_share: float, conditions: dict | None = None) -> np.ndarray:
        """Section capacity for the day's rain, lowered on trails with a reported condition (share removed:
        capacity.condition_levels; 1.0 = closed). An incident reported now changes the next plan at once."""
        C = self.ec.capacity(rain_share)
        for t, f in (conditions or {}).items():
            on = self.ec.seg.trail.values == t
            C = np.where(on & np.isfinite(C), np.where(np.isfinite(C), C, 0.0) * max(0.0, 1.0 - f),
                         np.where(on & (f >= 1.0), 0.0, C))
        return C

    def day_plan(self, rain_share: float, expected_visitors: float, conditions: dict | None = None) -> np.ndarray:
        """Caps [trail, slot] for the whole day from the forecast alone (planned the evening before)."""
        ec = self.ec
        K, C = ec.response(rain_share), self._capacity(rain_share, conditions)
        H, self.H = self.H, len(ec.slots)
        try:
            return self._plan(0, np.zeros((ec.sim.S, ec.n_bins)), self.pattern * expected_visitors, K, C)
        finally:
            self.H = H

    def advise_starts(self, size, gate, option, rain_share: float, expected_visitors: float, app_share: float,
                      follow: float, rng, max_shift_min: int = 180) -> tuple:
        """N3: visitors with the app ask for a start time the evening before and get the earliest slot at or after
        the time they wanted that still has room in the day plan (up to max_shift_min later). A share `follow`
        of them come at that time; everyone else comes when they wanted. Returns new gate times and counts."""
        ec = self.ec
        left = self.day_plan(rain_share, expected_visitors).copy()
        gate = np.array(gate, float)
        k_of = ec.slot_of(gate)
        sm = ec.c["slot_minutes"]
        moved = advised = 0.0
        on_plan = np.zeros(len(size), bool)                                   # came at their advised time
        for g in np.argsort(gate, kind="stable"):
            if rng.random() >= app_share:
                continue
            r = self.trail_of_option[option[g]]
            k0 = int(k_of[g])
            ks = [k for k in range(k0, len(ec.slots)) if ec.slots[k] - ec.slots[k0] <= max_shift_min and ec.allowed[r, k]]
            k = next((k for k in ks if left[r, k] >= size[g]), None)
            if k is None:
                continue
            left[r, k] -= size[g]
            advised += size[g]
            if k == k0:
                on_plan[g] = True
            elif rng.random() < follow:
                gate[g] = ec.slots[k] + rng.uniform(0, sm)
                moved += size[g]
                on_plan[g] = True
        return gate, {"advised": advised, "moved_by_advice": moved, "on_plan": on_plan}

    def caps_now(self, admitted, now_min: int, rain_share: float, expected_visitors: float,
                 conditions: dict | None = None) -> dict:
        """Live use at the gate: from everyone through the gate so far (DataFrame trail, gate_min, size), the places
        each trail can still take in the current slot and the caps planned for the next slots.
        conditions: {trail: share of capacity removed} reported today (mud, incident, closure)."""
        ec = self.ec
        K, C = ec.response(rain_share), self._capacity(rain_share, conditions)
        conditions = conditions or {}
        R, S_ = len(ec.trails), len(ec.slots)
        k = int(ec.slot_of(np.array([now_min]))[0])
        inside = np.zeros((ec.sim.S, ec.n_bins))
        used = np.zeros(R)
        seen = admitted[admitted.gate_min <= now_min]
        for (trail, kk), g in seen.groupby([seen.trail, ec.slot_of(seen.gate_min.values)]):
            if trail in ec.trails:
                r = ec.trails.index(trail)
                inside += K[r, kk] * g["size"].sum()
                if kk == k:
                    used[r] += g["size"].sum()
        arrived = float(seen["size"].sum()) if len(seen) else 0.0
        expected_so_far = expected_visitors * float(ec.slot_share[:k + 1].sum())
        ratio = float(np.clip(arrived / max(expected_so_far, 1.0), 0.5, 2.0)) if self.feedback and expected_so_far > 20 else 1.0
        demand = self.pattern * expected_visitors * ratio
        demand[:, k] = np.maximum(demand[:, k], used + 1e3)            # the current slot: whoever is at the gate
        # those already through the gate in this slot are inside: plan only the rest of the slot
        inside_wo = inside.copy()
        for r in range(R):
            inside_wo -= K[r, k] * used[r]
        a = self._plan(k, inside_wo, demand, K, C)
        lbl = [f"{s // 60:02d}:{s % 60:02d}" for s in ec.slots]
        names = ec.cfg["area"]["trail_names"]
        return {"slot": lbl[k], "arrivals_vs_expected": round(ratio, 2),
                "trails": [{"trail": t, "trail_name": names.get(t, t), "entered_this_slot": int(used[r]),
                            "can_enter_now": int(max(0.0, np.floor(a[r, k] - used[r])))
                            if ec.allowed[r, k] and conditions.get(t, 0.0) < 1.0 else 0,
                            "closed_for_entry": not bool(ec.allowed[r, k]) or conditions.get(t, 0.0) >= 1.0,
                            "capacity_removed": conditions.get(t, 0.0),
                            "next_slots": [{"slot": lbl[j], "cap": int(np.floor(a[r, j])) if conditions.get(t, 0.0) < 1.0 else 0}
                                           for j in range(k + 1, min(k + self.H, S_))]}
                           for r, t in enumerate(ec.trails)]}

    def _enter(self, g, r, opt, t, size, inside, K, out_size, out_gate, out_opt, stats, wanted):
        ec = self.ec
        out_size.append(size[g])
        out_gate.append(t)
        out_opt.append(opt)
        inside += K[r, ec.slot_of(np.array([t]))[0]] * size[g]
        if t - wanted > 1:
            stats["held"] += size[g]
            stats["wait_sum"] += (t - wanted) * size[g]
            stats["wait_n"] += size[g]
        if getattr(self, "_prio", None) is not None and self._prio[g]:
            stats["plan_people"] = stats.get("plan_people", 0.0) + size[g]
            stats["plan_wait_sum"] = stats.get("plan_wait_sum", 0.0) + max(t - wanted, 0.0) * size[g]
