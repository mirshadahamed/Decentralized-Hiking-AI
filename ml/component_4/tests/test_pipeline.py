"""Shape, leakage and reproducibility checks. Run from ml/component_4:  python -m pytest -q"""
import numpy as np
import pytest
import torch

from src.config import PROCESSED, load_config

pytestmark = pytest.mark.skipif(not (PROCESSED / "dataset.npz").exists(),
                                reason="run python -m src.data.build_dataset first")


@pytest.fixture(scope="module")
def data():
    from src.eval.data import TrailData
    return TrailData(load_config())


def test_graph_size_and_connectivity(data):
    import networkx as nx
    assert 25 <= data.N <= 60
    g = nx.Graph(data.edge_index.T.tolist())
    assert nx.is_connected(g) and g.number_of_nodes() == data.N
    assert set(data.trails) == {"main", "kirigalpotta", "thotupola"}
    assert set(data.segment_trail) == set(data.trails)


def test_out_and_back_trails_turn_at_the_peak():
    import geopandas as gpd
    from src.data.graph import load_walks
    seg = gpd.read_file(PROCESSED / "segments.geojson").set_index("seg_id")
    walks = load_walks()
    for trail, peak in [("kirigalpotta", "kirigalpotta_peak"), ("thotupola", "thotupola_peak")]:
        w = walks[trail]
        turn = [s for (s, d), (s2, d2) in zip(w[:-1], w[1:]) if s == s2 and d != d2]
        assert turn and seg.loc[turn[0], "poi"] == peak
        assert w[0][0] == w[-1][0]                               # back where it started


def test_visitors_by_trail_add_up(data):
    assert np.array_equal(data.daily_visitors_by_trail.sum(1), data.daily_visitors)


def test_no_negative_or_nan(data):
    assert np.isfinite(data.y).all() and (data.y >= 0).all()
    assert np.isfinite(data.cov_s).all() and np.isfinite(data.static_s).all()


def test_people_only_on_trail_when_open(data):
    hours = np.asarray(data.times.hour)
    assert data.y_true[(hours < 5) | (hours > 22)].sum() == 0


def test_splits_do_not_overlap_in_targets(data):
    H = data.H
    tr, va, te = data.origins("train", 1), data.origins("val"), data.origins("test")
    assert tr.max() + H <= data.train_end                     # train targets end before validation
    assert va.min() >= data.train_end and va.max() + H <= data.val_end
    assert te.min() >= data.val_end and te.max() + H <= data.T


def test_unsensed_nodes_give_no_history(data):
    sensed = np.ones(data.N, bool)
    sensed[:5] = False
    xp, xf, y, om = data.batch(data.origins("test")[:4], sensed, 10.0)
    assert xp.shape == (4, data.L, data.N, 2 + data.cov.shape[1] + data.static.shape[1])
    assert xf.shape == (4, data.H, data.N, data.cov.shape[1] + data.static.shape[1])
    assert y.shape == (4, data.H, data.N) and om.shape == (4, data.H)
    assert torch.all(xp[:, :, :5, 0] == 0) and torch.all(xp[:, :, :5, 1] == 0)


def test_scaler_uses_train_period_only(data):
    y_scale = data.y_scale(np.ones(data.N, bool))
    assert np.isclose(y_scale, data.y[:data.train_end].std())


def test_model_output_shape_and_seed(data):
    from src.train.trainer import build_model
    from src.utils import set_seed
    xp, xf, _, _ = data.batch(data.origins("test")[:2], np.ones(data.N, bool), 10.0)
    outs = []
    for _ in range(2):
        set_seed(0)
        outs.append(build_model(data, "stgnn", 16)(xp, xf))
    assert outs[0].shape == (2, data.H, data.N)
    assert torch.allclose(outs[0], outs[1])                   # same seed -> same weights -> same output


def test_simulator_is_reproducible():
    import geopandas as gpd
    from src.data.graph import load_walks
    from src.sim.simulator import TrailSimulator
    cfg = load_config()
    seg = gpd.read_file(PROCESSED / "segments.geojson")
    seg["poi"] = seg["poi"].fillna("")
    sim = TrailSimulator(seg, load_walks(), cfg["simulator"])
    a, _, va = sim.simulate_day(800, np.zeros(24), np.random.default_rng(1))
    b, _, vb = sim.simulate_day(800, np.zeros(24), np.random.default_rng(1))
    assert np.array_equal(a, b) and a.shape == (24, len(seg)) and va == vb
    assert a.sum() > 0 and sum(va.values()) >= 800
    # diversion what-if: sending everyone to Thotupola leaves the World's End loop empty
    c, _, vc = sim.simulate_day(800, np.zeros(24), np.random.default_rng(1), route_share={"thotupola": 1.0})
    assert vc["main"] == 0 and c[:, (seg.trail == "main").values].sum() == 0
