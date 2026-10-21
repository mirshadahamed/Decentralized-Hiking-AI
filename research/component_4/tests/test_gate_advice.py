"""A3: gate advice during the day from the gate counts and the coming slots."""
import numpy as np
import pandas as pd
import pytest

from src.config import PROCESSED

pytestmark = pytest.mark.skipif(not (PROCESSED / "dataset.npz").exists(), reason="run python -m src.data.build_dataset first")


@pytest.fixture(scope="module")
def ec():
    from src.control.slots import build_control
    return build_control()


def _plan(ec, n):
    return pd.DataFrame(n, index=[f"{s // 60:02d}:{s % 60:02d}" for s in ec.slots], columns=ec.trails)


def test_quiet_day_needs_no_advice(ec):
    from src.control.gate_advice import gate_advice
    a = gate_advice(ec, pd.DataFrame(columns=["trail", "gate_min", "size"]), 8 * 60, 0.0, _plan(ec, 0))
    assert a["over"] == [] and a["advice"] == [] and a["inside"] == 0


def test_crowd_at_the_gate_gives_a_hold_for_that_trail(ec):
    from src.control.gate_advice import gate_advice
    main = ec.cfg["area"].get("main_trail", ec.trails[0])
    inside = pd.DataFrame({"trail": main, "gate_min": np.linspace(6 * 60, 7 * 60 + 50, 40), "size": 12.0})
    plan = _plan(ec, 0)
    plan[main] = 150                                                   # the coming slots are full too
    a = gate_advice(ec, inside, 8 * 60, 0.0, plan)
    assert a["over"], "a crowded main trail must show sections over capacity"
    adv = {x["trail"]: x for x in a["advice"]}
    assert main in adv
    assert adv[main]["text"].startswith(("Hold new entries", "Pause new entries"))
    assert a["inside"] == 480
    # holding the coming entrants can only lower what is ahead
    calm = gate_advice(ec, inside, 8 * 60, 0.0, _plan(ec, 0))
    assert sum(o["people"] for o in calm["over"]) <= sum(o["people"] for o in a["over"])
