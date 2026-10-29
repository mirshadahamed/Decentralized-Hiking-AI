"""S1 realistic world: off by default (old results reproduce), and when on, days differ in ways the calendar
cannot predict (persistent demand, bursts, arrival shifts, incidents) and the model sees forecast weather."""
import copy

import numpy as np
import pandas as pd
import pytest

from src.config import PROCESSED, load_config
from src.sim.simulator import day_events, daily_demand, realism

pytestmark = pytest.mark.skipif(not (PROCESSED / "segments.geojson").exists(),
                                reason="run python -m src.data.build_dataset first")


@pytest.fixture(scope="module")
def setup():
    import geopandas as gpd
    from src.data.graph import load_walks
    from src.sim.simulator import TrailSimulator
    cfg = load_config()
    seg = gpd.read_file(PROCESSED / "segments.geojson")
    seg["poi"] = seg["poi"].fillna("")
    on = copy.deepcopy(cfg["simulator"])
    on["realism"]["enabled"] = True
    return cfg, seg, load_walks(), TrailSimulator, on


def _cal(n=400):
    idx = pd.date_range("2025-01-01", periods=n, freq="D")
    z = np.zeros(n, bool)
    return pd.DataFrame({"dow": idx.dayofweek, "is_holiday": z, "is_poya": z, "is_long_weekend": z,
                         "is_school_holiday": z}, index=idx)


def test_off_by_default_and_reproducible(setup):
    cfg, *_ = setup
    assert realism(cfg["simulator"]) is None
    assert day_events(cfg["simulator"], np.random.default_rng(0), 10, "main") == {}
    cal, rain = _cal(), np.zeros((400, 24))
    a = daily_demand(cal, rain, cfg["simulator"], np.random.default_rng(1))
    b = daily_demand(cal, rain, cfg["simulator"], np.random.default_rng(1))
    assert np.array_equal(a, b)


def test_demand_persists_when_on(setup):
    cfg, _, _, _, on = setup
    cal, rain = _cal(), np.zeros((400, 24))
    calm = np.log(daily_demand(cal, rain, cfg["simulator"] | {"daily_noise_sd": 0.0}, np.random.default_rng(1)))
    off = np.log(daily_demand(cal, rain, cfg["simulator"], np.random.default_rng(1))) - calm
    real = np.log(daily_demand(cal, rain, on, np.random.default_rng(1))) - calm

    def ac(r):                                                     # lag-1 autocorrelation of the day effect
        return np.corrcoef(r[:-1], r[1:])[0, 1]
    assert ac(real) > 0.45 and abs(ac(off)) < 0.2                # phi = 0.7 vs independent days


def test_events_change_the_day(setup):
    cfg, seg, walks, TrailSimulator, on = setup
    sim = TrailSimulator(seg, walks, on)
    rng = np.random.default_rng(3)
    evs = [day_events(on, rng, sim.S, sim.trails[0]) for _ in range(300)]
    assert any(e["bursts"] for e in evs) and any(e["slow"] is not None for e in evs)
    assert np.std([e["arrival_shift_min"] for e in evs]) > 20
    ev = next(e for e in evs if e["bursts"])
    size, gate, option = sim.sample_day(200, np.random.default_rng(4), events=ev)
    assert size.sum() >= 200 + sum(b["people"] for b in ev["bursts"]) - 1     # the bus groups come on top
    slow = next(e["slow"] for e in evs if e["slow"] is not None)
    s, h = np.argwhere(slow < 1)[0]
    base = sim.simulate_groups(size, gate, option, np.zeros(24), np.random.default_rng(5))[0]
    hit = sim.simulate_groups(size, gate, option, np.zeros(24), np.random.default_rng(5), slow=slow)[0]
    assert hit[h:h + 4, s].sum() >= base[h:h + 4, s].sum()                    # people back up on the slowed segment


def test_forecast_weather_differs_from_observed():
    from src.data.build_dataset import forecast_weather
    idx = pd.date_range("2025-01-01", periods=24 * 30, freq="h")
    rng = np.random.default_rng(0)
    w = pd.DataFrame({"precipitation": rng.gamma(0.3, 2.0, len(idx)), "temperature_2m": 15.0}, index=idx)
    r = load_config()["simulator"]["realism"]
    f = forecast_weather(w, r, np.random.default_rng(1))
    assert not np.allclose(f.precipitation, w.precipitation) and not np.allclose(f.temperature_2m, w.temperature_2m)
    assert (f.precipitation >= 0).all() and len(f) == len(w)
