"""Adam's Peak and the multi-park setup. Runs in the normal test process (Horton Plains is the default park):
the Adam's Peak objects are built from data/adams_peak/ explicitly."""
import json
import os
import subprocess
import sys

import geopandas as gpd
import numpy as np
import pytest

from src.config import ROOT, load_config

AP = ROOT / "data" / "adams_peak" / "processed"
pytestmark = pytest.mark.skipif(not (AP / "segments.geojson").exists(),
                                reason="build Adam's Peak first: $env:C4_PARK='adams_peak'; python -m src.data.build_dataset")


@pytest.fixture(scope="module")
def ap():
    from src.sim.simulator import TrailSimulator
    cfg = load_config(park="adams_peak")
    seg = gpd.read_file(AP / "segments.geojson")
    seg["poi"] = seg["poi"].fillna("")
    walks = {r: [tuple(x) for x in w] for r, w in json.loads((AP / "route.json").read_text())["walks"].items()}
    return cfg, seg, walks, TrailSimulator(seg, walks, cfg["simulator"])


def test_park_config_replaces_horton_values():
    hp, cfg = load_config(park="horton_plains"), load_config(park="adams_peak")
    assert set(cfg["area"]["routes"]) == {"nallathanniya", "palabaddala", "erathna", "dikelikanda"}
    assert "worlds_end" not in cfg["area"]["poi_labels"] and not cfg["area"]["pois"]
    assert set(cfg["simulator"]["route_share"]) == set(cfg["area"]["routes"])
    assert cfg["simulator"]["dwell_minutes"] == {}
    assert hp["area"]["main_trail"] == "main" and cfg["area"]["main_trail"] == "nallathanniya"
    assert cfg["dates"] == hp["dates"]                                      # inherited unchanged


def test_every_route_goes_up_to_the_summit_and_back(ap):
    cfg, seg, walks, sim = ap
    summit = int(seg.index[seg.poi == "summit"][0])
    for r, w in walks.items():
        i = sim._turnaround(w)
        assert i is not None, r                                           # out and back
        ups = [s for s, _ in w[:i]]
        assert summit in ups or seg.loc[ups[-1]].geometry.distance(seg.loc[summit].geometry) < 1e-3, r
        assert (seg.poi == f"half_{r}").sum() == 1                        # one halfway checkpoint per route
        assert seg.loc[seg.poi == f"half_{r}"].index[0] in ups[:-2]       # never on the final steps


def test_queue_forms_on_busy_nights_and_halfway_checks_move_it(ap):
    cfg, seg, walks, sim = ap
    rng = np.random.default_rng(1)
    size, gate, option = sim.sample_day(12000, rng)
    _, _, _ = sim.simulate_groups(size, gate, option, np.zeros(24), np.random.default_rng(2), hold=False)
    w_free = sim.last_wait.copy()
    assert np.percentile(w_free, 90) > 30                                  # Poya night: long waits
    walk = sim.options[sim.option_of_trail("nallathanniya")][1]
    final = walk[sim._turnaround(walk) - 2][0]
    _, pm_free, _ = sim.simulate_groups(size, gate, option, np.zeros(24), np.random.default_rng(2), hold=False)
    _, pm_hold, _ = sim.simulate_groups(size, gate, option, np.zeros(24), np.random.default_rng(2), hold=True)
    assert pm_hold[final].max() < pm_free[final].max()                    # fewer people on the final steps
    small = sim.sample_day(800, np.random.default_rng(3))
    sim.simulate_groups(*small, np.zeros(24), np.random.default_rng(4))
    assert np.percentile(sim.last_wait, 90) < 1                            # quiet night: no real queue


def test_season_flag_and_estimated_poya():
    import pandas as pd
    from src.data.calendar_features import lk_holidays, season_flag
    days = pd.date_range("2026-12-01", "2027-06-30")
    flag = dict(zip(days.date, season_flag(days, "Unduvap", "Vesak")))
    assert flag[pd.Timestamp("2026-12-22").date()] == 0 and flag[pd.Timestamp("2026-12-23").date()] == 1
    assert flag[pd.Timestamp("2027-03-01").date()] == 1
    est = {d: n for d, n in lk_holidays([2027]).items() if "Poya" in n}
    assert len(est) in (12, 13) and all("estimated" in n for n in est.values())


def test_advisory_never_recommends_a_long_wait(ap):
    from src.control.advisory import Advisory
    cfg, seg, walks, sim = ap
    adv = Advisory(sim, seg, cfg)
    for total in (1500, 12000):
        vis = {t: total * s for t, s in cfg["simulator"]["route_share"].items()}
        rec = adv.recommend(vis)
        for r in rec["routes"].values():
            for w in r["windows"]:
                if w["recommended"]:
                    assert w["expected_wait_min"] <= adv.limit
    rates = rec["halfway"]
    assert abs(sum(r["release_per_10_min"] for r in rates.values()) - adv.flow * 10) <= len(rates)


def test_horton_plains_is_unchanged_by_the_park_switch():
    out = subprocess.run([sys.executable, "-c", "from src.config import PARK, DATA; print(PARK, DATA.name)"],
                         capture_output=True, text=True, cwd=ROOT, env=dict(os.environ, C4_PARK="horton_plains"))
    assert out.stdout.split() == ["horton_plains", "data"]
