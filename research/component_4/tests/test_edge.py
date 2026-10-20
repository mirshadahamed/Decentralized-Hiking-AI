"""Edge (objective O6): the pack carries exactly the model inputs the server uses, and the API serves it."""
import json

import numpy as np
import pytest
import torch

from src.config import PROCESSED, RESULTS, load_config

pytestmark = pytest.mark.skipif(not (PROCESSED / "dataset.npz").exists() or not (RESULTS / "LATEST").exists(),
                                reason="needs the dataset and a trained benchmark run")


@pytest.fixture(scope="module")
def trained():
    from src.eval.data import TrailData
    from src.serve.predict import load_model
    cfg = load_config()
    data = TrailData(cfg)
    model, scale, run = load_model(data, cfg)
    return cfg, data, model.eval(), scale, run


def test_pack_rebuilds_the_exact_model_inputs(trained):
    from src.edge.pack import SCHEMA, build_pack, torch_forecast
    cfg, data, model, scale, run = trained
    origin = int(data.origins("test")[5])
    pack = json.loads(json.dumps(build_pack(data, model, scale, origin, cfg, run=run)))   # as the phone sees it
    assert pack["schema"] == SCHEMA and pack["model"]["rnn"] in ("gru", "lstm")
    i = pack["inputs"]
    occ, cp, cf, st = (np.array(i[k]) for k in ("occupancy_past", "covariates_past", "covariates_future", "static"))
    L, N = occ.shape
    x_past = np.concatenate([occ[..., None], np.ones((L, N, 1)), np.broadcast_to(cp[:, None], (L, N, cp.shape[1])),
                             np.broadcast_to(st[None], (L, N, st.shape[1]))], -1)
    x_fut = np.concatenate([np.broadcast_to(cf[:, None], (cf.shape[0], N, cf.shape[1])),
                            np.broadcast_to(st[None], (cf.shape[0], N, st.shape[1]))], -1)
    xp, xf, _, _ = data.batch(np.array([origin]), np.ones(data.N, bool), scale)
    assert np.allclose(x_past, xp.numpy()[0], atol=1e-5) and np.allclose(x_fut, xf.numpy()[0], atol=1e-5)
    # the rounded weights in the pack still give the same forecast (to a hundredth of a person)
    w = {k: torch.tensor(v["data"], dtype=torch.float32).reshape(v["shape"]) for k, v in pack["model"]["weights"].items()}
    clone = type(model)(model.inp.in_features, model.fut.in_features, data.edge_index, data.edge_weight,
                        hidden=pack["model"]["hidden"], use_graph=True,
                        rnn=pack["model"]["rnn"])
    clone.load_state_dict(w, strict=False)
    assert np.abs(torch_forecast(clone.eval(), data, origin, scale) - torch_forecast(model, data, origin, scale)).max() < 0.01


def test_pack_map_has_every_segment_with_its_line_and_capacity(trained):
    """The bottleneck map on the phone: one line + the server's Cifuentes numbers per segment, same order as the
    model's output, and each trail's safe number = its most limiting segment."""
    import geopandas as gpd
    from src.edge.pack import map_extras
    from src.serve.predict import build_forecast
    cfg, data, model, scale, run = trained
    seg = gpd.read_file(PROCESSED / "segments.geojson")
    seg["poi"] = seg["poi"].fillna("")
    day = str(data.times[int(data.origins("test")[5])].date())
    f = build_forecast(data, cfg, seg, day, model, scale, run)
    m = json.loads(json.dumps(map_extras(f, seg, cfg)))
    assert [s["id"] for s in m["segments"]] == list(range(data.N))
    assert all(s["lines"] and len(s["lines"][0]) >= 2 for s in m["segments"])
    by_id = {s["seg_id"]: s for s in f["segments"]}
    assert all(s["ecc_per_day"] == by_id[s["id"]]["ecc_per_day"] for s in m["segments"])
    for t, v in m["trails"].items():
        assert v["recommended_daily_quota"] == min(s["ecc_per_day"] for s in m["segments"]
                                                   if by_id[s["id"]]["trail"] == t)
    assert m["open_hours"] == list(range(6, 18))
    assert len(json.dumps(m)) < 40_000                     # keeps the daily pack small


def test_api_serves_the_pack(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from src.api import app as api
    from src.live.refresh import PUBLISHED
    if not (PUBLISHED / "edge_pack.json").exists():
        pytest.skip("run python -m src.live.refresh first")
    r = TestClient(api.app).get("/edge/pack")
    assert r.status_code == 200 and r.json()["schema"] == "c4-edge-1"
    assert len(r.content) < 400_000                        # small enough for a daily phone download
