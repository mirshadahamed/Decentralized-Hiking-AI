"""Yala National Park (Block 1): jeep safaris on the same pipeline. Config, closures, sighting jams, DEM tile, graph."""
import numpy as np
import pandas as pd
import pytest

from src.config import load_config, processed_dir


@pytest.fixture(scope="module")
def cfg():
    return load_config(park="yala")


def test_config_is_a_safari_park_with_tickets(cfg):
    assert cfg["destination"]["kind"] == "safari"
    assert cfg["control"]["booking_mode"] == "required"
    assert set(cfg["area"]["routes"]) == set(cfg["simulator"]["route_share"]) == set(cfg["area"]["trail_names"])
    assert abs(sum(cfg["simulator"]["route_share"].values()) - 1) < 1e-9
    assert cfg["terrain"]["vehicle_kmh"] > 0
    for r in cfg["area"]["routes"].values():                     # every circuit starts and ends at an entrance
        assert r[0] == r[-1] and r[0] in cfg["area"]["poi_roles"]["access"]


def _calendar(days):
    idx = pd.date_range("2025-08-25", periods=days, freq="D")
    z = np.zeros(days, int)
    return pd.DataFrame({"dow": idx.dayofweek, "is_holiday": z, "is_poya": z, "is_long_weekend": z,
                         "is_school_holiday": z}, index=idx)


def test_annual_closure_gives_no_visitors(cfg):
    from src.sim.simulator import closed_days, daily_demand, sample_groups
    cal = _calendar(60)                                           # 25 Aug - 23 Oct
    shut = closed_days(cal, cfg["simulator"]).astype(bool)
    assert shut[cal.index.strftime("%m-%d") == "09-15"].all() and not shut[cal.index.strftime("%m-%d") == "08-31"].any()
    demand = daily_demand(cal, np.zeros((60, 24)), cfg["simulator"], np.random.default_rng(0))
    assert (demand[shut] == 0).all() and (demand[~shut] > 0).all()
    assert len(sample_groups(0, cfg["simulator"], np.random.default_rng(0))) == 0


def test_other_parks_have_no_closure():
    from src.sim.simulator import closed_days
    for park in ("horton_plains", "adams_peak"):
        assert closed_days(_calendar(30), load_config(park=park)["simulator"]).sum() == 0


def _line_sim(cfg, sightings):
    from src.sim.simulator import TrailSimulator
    seg = pd.DataFrame({"length_m": [1000.0] * 3, "tobler_fwd_min": [4.0] * 3, "tobler_bwd_min": [4.0] * 3,
                        "poi": ["", "", ""]})
    p = cfg["simulator"] | {"route_share": {"a": 1.0}, "reversible_routes": [], "dwell_minutes": {},
                            "sightings": cfg["simulator"]["sightings"] | {"hotspots": []}}
    sim = TrailSimulator(seg, {"a": [(0, 1), (1, 1), (2, 1)]}, p)
    sim.sightings = sightings
    return sim


def test_a_sighting_holds_jeeps_on_its_section(cfg):
    size, gate, opt = np.full(60, 5.0), np.linspace(360, 420, 60), np.zeros(60, int)
    calm = _line_sim(cfg, []).simulate_groups(size, gate, opt, np.zeros(24), np.random.default_rng(1))[0]
    jam = _line_sim(cfg, [(1, 360.0, 480.0)]).simulate_groups(size, gate, opt, np.zeros(24), np.random.default_rng(1))[0]
    assert jam[6:9, 1].sum() > 2 * calm[6:9, 1].sum()           # people pile up on the section with the animal
    assert np.isclose(jam.sum(0)[0], calm.sum(0)[0], rtol=0.05)  # the section before is hardly affected


def test_sightings_are_drawn_per_day_and_only_in_safari_hours(cfg):
    from src.sim.simulator import day_sightings
    rng = np.random.default_rng(3)
    draws = [day_sightings(cfg["simulator"], rng, np.ones(35)) for _ in range(200)]
    starts = [a / 60 for d in draws for _, a, _ in d]
    assert 3 < np.mean([len(d) for d in draws]) < 7
    assert all(6 <= h <= 9.5 or 15 <= h <= 17.5 for h in starts)
    assert day_sightings(load_config(park="horton_plains")["simulator"], rng, np.ones(48)) == []


def test_dem_tile_follows_the_park():
    from src.data.terrain import dem_url
    assert "N06_00_E081" in dem_url(load_config(park="yala")["area"]["dem_bbox"])
    assert "N06_00_E080" in dem_url(load_config(park="horton_plains")["area"]["dem_bbox"])
    with pytest.raises(ValueError):
        dem_url([80.9, 6.2, 81.1, 6.4])


@pytest.mark.skipif(not (processed_dir("yala") / "dataset.npz").exists(),
                    reason="run $env:C4_PARK='yala'; python -m src.data.build_dataset first")
def test_built_graph_and_dataset(cfg):
    import geopandas as gpd
    p = processed_dir("yala")
    seg = gpd.read_file(p / "segments.geojson")
    assert 20 <= len(seg) <= 120
    assert set(seg.trail) == set(cfg["area"]["routes"])
    assert {"palatupana", "katagamuwa", "patanangala"} <= set(seg.poi)
    d = np.load(p / "dataset.npz", allow_pickle=True)
    days = pd.DatetimeIndex(sorted(set(pd.to_datetime(d["times"].astype("datetime64[h]")).normalize())))
    v = pd.Series(d["daily_visitors"], index=days)
    assert v[(v.index.month == 9)].sum() == 0                      # closed in September
    assert v[v.index.month.isin([1, 2, 3])].mean() > 500


def test_ranger_cap_limits_jeeps_stopped_at_a_sighting(cfg):
    size, gate, opt = np.full(60, 5.0), np.linspace(360, 420, 60), np.zeros(60, int)
    out = {}
    for name, pol in (("none", {}), ("cap", {"cap_jeeps": 5, "rotation_min": 5})):
        sim = _line_sim(cfg, [(1, 360.0, 480.0)])
        sim.sighting_policy = pol
        h = sim.simulate_groups(size, gate, opt, np.zeros(24), np.random.default_rng(1))[0]
        out[name] = (h[6:9, 1].sum(), sim.last_sighting_stats)
    assert out["none"][1]["moved_on"] == 0 and out["none"][1]["viewed"] == 60
    assert out["cap"][1]["moved_on"] > 0 and out["cap"][1]["viewed"] + out["cap"][1]["moved_on"] == 60
    assert out["cap"][0] < 0.5 * out["none"][0]                  # far fewer people held on the section
