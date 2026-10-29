"""Closed-loop gate control (MPC): admits everyone on a quiet day, holds back a crowd, never invents people."""
import numpy as np
import pytest

from src.config import PROCESSED

pytestmark = pytest.mark.skipif(not (PROCESSED / "dataset.npz").exists(), reason="run python -m src.data.build_dataset first")


@pytest.fixture(scope="module")
def ec():
    from src.control.slots import build_control
    return build_control()


def _day(ec, n, seed=0):
    return ec.sim.sample_day(n, np.random.default_rng(seed))


def test_quiet_day_lets_everyone_in(ec):
    from src.control.mpc import MPCController
    size, gate, option = _day(ec, 60)
    m = MPCController(ec)
    s, g, o, st = m.run_day(size, gate, option, 0.0, 60.0, np.random.default_rng(1))
    # only groups that come after their trail's last entry time can be turned away on a quiet day
    late = ~ec.allowed[m.trail_of_option[option], ec.slot_of(gate)]
    assert st["refused"] <= size[late].sum()
    assert s.sum() + st["refused"] == pytest.approx(size.sum())


def test_crowd_is_held_and_planned_occupancy_stays_near_capacity(ec):
    from src.control.mpc import MPCController
    size, gate, option = _day(ec, 4000)
    m = MPCController(ec, compliance=0.5)
    s, g, o, st = m.run_day(size, gate, option, 0.0, 2000.0, np.random.default_rng(1))
    # everyone is accounted for: admitted + turned away = who came
    assert s.sum() + st["refused"] == pytest.approx(size.sum())
    assert st["refused"] > 0 and st["held"] > 0
    # the linear model's occupancy of who was let in stays within capacity (small slack for people inside)
    K, C = ec.response(0.0), ec.capacity(0.0)
    occ = np.zeros((ec.sim.S, ec.n_bins))
    tr = m.trail_of_option[o]
    for r, k, n in zip(tr, ec.slot_of(g), s):
        occ += K[r, k] * n
    fin = np.isfinite(C)
    assert (occ[fin] <= C[fin, None] * 1.05).all()


def test_live_caps_shrink_as_the_gate_fills(ec):
    import pandas as pd
    from src.control.mpc import MPCController
    m = MPCController(ec)
    main = ec.trails[0]
    empty = m.caps_now(pd.DataFrame(columns=["trail", "gate_min", "size"]), 7 * 60 + 5, 0.0, 600.0)
    crowd = pd.DataFrame({"trail": main, "gate_min": np.linspace(6 * 60, 7 * 60, 60), "size": 10.0})
    busy = m.caps_now(crowd, 7 * 60 + 5, 0.0, 600.0)
    cap = {t["trail"]: t["can_enter_now"] for t in empty["trails"]}
    cap_busy = {t["trail"]: t["can_enter_now"] for t in busy["trails"]}
    assert cap_busy[main] < cap[main]                                   # people already inside take the room
    assert busy["arrivals_vs_expected"] > 1.0                           # more came than expected: feedback
    assert all(len(t["next_slots"]) > 0 for t in busy["trails"] if not t["closed_for_entry"])


def test_start_times_only_move_people_later_and_within_the_limit(ec):
    from src.control.mpc import MPCController
    size, gate, option = _day(ec, 3000, seed=3)
    m = MPCController(ec)
    g2, adv = m.advise_starts(size, gate, option, 0.0, 1500.0, app_share=1.0, follow=1.0,
                              rng=np.random.default_rng(4))
    shift = g2 - gate
    assert (shift >= -ec.c["slot_minutes"]).all()                 # never earlier than the slot they wanted
    assert shift.max() <= 180 + ec.c["slot_minutes"]
    assert adv["moved_by_advice"] > 0 and adv["advised"] <= size.sum()
    none, _ = m.advise_starts(size, gate, option, 0.0, 1500.0, app_share=0.0, follow=1.0, rng=np.random.default_rng(4))
    assert np.array_equal(none, gate)                             # nobody with the app: nothing changes


def test_feedback_raises_the_forecast_when_more_come_than_expected(ec):
    from src.control.mpc import MPCController
    size, gate, option = _day(ec, 3000)
    with_fb = MPCController(ec, feedback=True).run_day(size, gate, option, 0.0, 800.0, np.random.default_rng(2))
    no_fb = MPCController(ec, feedback=False).run_day(size, gate, option, 0.0, 800.0, np.random.default_rng(2))
    # knowing the day is busier, the controller saves less room for people it no longer expects to be few:
    # both stay within the same people, and feedback changes the decisions
    assert with_fb[0].sum() + with_fb[3]["refused"] == pytest.approx(size.sum())
    assert not np.isclose(with_fb[0].sum(), no_fb[0].sum()) or not np.allclose(np.sort(with_fb[1]), np.sort(no_fb[1]))


def test_reported_condition_lowers_live_caps_and_closure_stops_entry(ec):
    import pandas as pd
    from src.control.mpc import MPCController
    m = MPCController(ec)
    main = ec.trails[0]
    none = pd.DataFrame(columns=["trail", "gate_min", "size"])
    k = int(np.argmax(ec.allowed[0]))
    at = int(ec.slots[k]) + 5
    def caps(cond):
        t = next(x for x in m.caps_now(none, at, 0.0, 900.0, cond)["trails"] if x["trail"] == main)
        return t["can_enter_now"] + sum(s["cap"] for s in t["next_slots"]), t
    full, _ = caps({})
    muddy, _ = caps({main: 0.5})
    closed, t = caps({main: 1.0})
    assert closed == 0 and t["closed_for_entry"] and t["capacity_removed"] == 1.0
    assert muddy < full
    assert np.all(m.day_plan(0.0, 900.0, {main: 1.0})[0] == 0)
