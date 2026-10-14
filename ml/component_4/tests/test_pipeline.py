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
    assert 25 <= data.N <= 40
    g = nx.Graph(data.edge_index.T.tolist())
    assert nx.is_connected(g) and g.number_of_nodes() == data.N


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
    import json

    import geopandas as gpd
    from src.sim.simulator import TrailSimulator
    cfg = load_config()
    seg = gpd.read_file(PROCESSED / "segments.geojson")
    walk = [tuple(x) for x in json.loads((PROCESSED / "route.json").read_text())["walk"]]
    sim = TrailSimulator(seg, walk, cfg["simulator"])
    a = sim.simulate_day(800, np.zeros(24), np.random.default_rng(1))[0]
    b = sim.simulate_day(800, np.zeros(24), np.random.default_rng(1))[0]
    assert np.array_equal(a, b) and a.shape == (24, len(seg))
    assert a.sum() > 0
