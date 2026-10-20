"""Entry control and booking: never over capacity, never overbooked, valid gate windows."""
from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from src.config import PROCESSED

pytestmark = pytest.mark.skipif(not (PROCESSED / "dataset.npz").exists(),
                                reason="run python -m src.data.build_dataset first")


@pytest.fixture(scope="module")
def ec():
    from src.control.slots import build_control
    return build_control()


@pytest.mark.parametrize("rain", [0.0, 0.5])
def test_plan_never_exceeds_planned_capacity(ec, rain):
    quota = ec.daily_quota(rain)
    plan = ec.plan(rain, quota)
    occ = ec.expected_occupancy(plan, rain)
    C = ec.capacity(rain) * ec.c["safety_margin"]
    fin = np.isfinite(C)
    assert (occ[fin] <= C[fin, None] + 1e-6).all()
    assert (plan.values >= 0).all() and plan.values.dtype.kind == "i"
    for t, q in quota.items():
        assert plan[t].sum() <= q + 1e-6


def test_no_tickets_after_last_entry(ec):
    plan = ec.plan(0.0, ec.daily_quota(0.0))
    last = ec.cfg["simulator"]["route_last_entry_h"]["kirigalpotta"] * 60
    late = [s for s in plan.index if int(s[:2]) * 60 + int(s[3:]) >= last]
    assert plan.loc[late, "kirigalpotta"].sum() == 0


def test_rain_lowers_tickets(ec):
    dry = ec.plan(0.0, ec.daily_quota(0.0)).values.sum()
    wet = ec.plan(0.5, ec.daily_quota(0.5)).values.sum()
    assert wet < dry


def test_nowcast_counts_only_people_already_in(ec):
    admitted = pd.DataFrame({"trail": ["main", "main"], "gate_min": [400, 500], "size": [10, 10]})
    early = ec.nowcast(admitted, 420)
    later = ec.nowcast(admitted, 520)
    assert early.sum() > 0 and later.sum() >= early.sum() * 0.5
    assert ec.nowcast(admitted, 300).sum() == 0              # nobody in before the first scan


def test_slot_control_beats_no_limit_on_a_busy_day(ec):
    from src.control.evaluate import admit
    rng = np.random.default_rng(0)
    size, gate, option = ec.sim.sample_day(1200, rng)
    quota, plan = ec.daily_quota(0.0), ec.plan(0.0, ec.daily_quota(0.0))
    C = ec.capacity(0.0)
    fin = np.isfinite(C)
    over = {}
    for pol in ("A", "D"):
        s, g, o, moved = admit(pol, ec, size, gate, option, quota, plan, np.random.default_rng(1))
        _, per_min, _ = ec.sim.simulate_groups(s, g, o, np.zeros(24), np.random.default_rng(2))
        occ = per_min.reshape(ec.sim.S, ec.n_bins, -1).mean(-1)
        over[pol] = np.clip(occ[fin] - C[fin, None], 0, None).sum()
    assert over["D"] < 0.05 * over["A"]


# ---------- booking ----------
@pytest.fixture()
def db(tmp_path):
    return tmp_path / "bookings.sqlite"


def test_cannot_overbook(db):
    from src.control import booking as b
    left = int(b.supply("2025-05-12").loc["07:00", "main"])
    n = 0
    with pytest.raises(b.SlotFull) as e:
        for _ in range(100):
            b.book("2025-05-12", "main", "07:00", 5, today="2025-03-01", db=db)
            n += 5
    assert n <= left and b.booked("2025-05-12", db).loc["07:00", "main"] <= left
    assert e.value.alternatives                                # alternatives are offered


def test_walk_in_share_is_kept(ec):
    from src.control import booking as b
    rain = b._climatology_rain_share()[pd.Timestamp("2025-05-12").dayofyear]
    full = ec.plan(rain, ec.daily_quota(rain))
    assert (b.supply("2025-05-12") <= full * (1 - ec.c["walk_in_share"]) + 1e-9).all().all()


def test_booking_window_and_horizon(db):
    from src.control import booking as b
    with pytest.raises(ValueError):
        b.book("2025-08-01", "main", "07:00", 2, today="2025-03-01", db=db)    # > 90 days ahead
    with pytest.raises(ValueError):
        b.book("2025-03-01", "main", "07:00", 2, today="2025-03-01", db=db)    # same day
    code = b.book("2025-05-12", "thotupola", "08:00", 2, today="2025-03-01", db=db)
    assert not b.check_in(code, datetime(2025, 5, 12, 7, 40), db)["ok"]        # too early
    assert b.check_in(code, datetime(2025, 5, 12, 8, 10), db)["ok"]
    assert not b.check_in(code, datetime(2025, 5, 12, 8, 11), db)["ok"]        # already used
    code2 = b.book("2025-05-12", "thotupola", "08:00", 2, today="2025-03-01", db=db)
    assert b.cancel(code2, db) and not b.check_in(code2, datetime(2025, 5, 12, 8, 0), db)["ok"]
