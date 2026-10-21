"""A4: rangers' spot counts and the forecast checked against them."""
from datetime import timedelta

import numpy as np
import pytest

from src.live.refresh import PUBLISHED

pytestmark = pytest.mark.skipif(not (PUBLISHED / "status.json").exists(), reason="run python -m src.live.refresh first")


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    from fastapi.testclient import TestClient
    from src.api import app as api, auth
    from src.control import booking
    tmp = tmp_path_factory.mktemp("cnt")
    old = booking.DB, auth.DB
    booking.DB, auth.DB = tmp / "b.sqlite", tmp / "a.sqlite"
    auth.create_user("off", "a-long-password-1", "officer")
    auth.create_user("rng", "a-long-password-1", "ranger")
    c = TestClient(api.app)

    def tok(u):
        return {"Authorization": "Bearer " + c.post("/auth/login", json={"username": u, "password": "a-long-password-1"}).json()["token"]}
    yield c, tok("off"), tok("rng"), api.ctx()
    booking.DB, auth.DB = old


def test_segments_listed(client):
    c, *_ = client
    s = c.get("/segments").json()
    assert len(s) > 10 and {"seg_id", "name", "trail", "trail_name"} <= set(s[0])


def test_count_once_and_checked_against_forecast(client):
    from src.control import booking
    from src.control.slots import build_control
    c, officer, ranger, ctx = client
    day = (ctx.today - timedelta(days=1)).isoformat()
    ec = build_control()
    seg = int(ec.seg.seg_id.iloc[5])
    fc = np.zeros((24, len(ec.seg)))
    fc[10, 5] = 40.0
    booking.save_forecast(day, fc, "test forecast")
    body = {"day": day, "seg_id": seg, "time": "10:20", "count": 30, "client_id": "phone-1-abc"}
    assert c.post("/counts", json=body).status_code == 401
    assert c.post("/counts", json=body, headers=ranger).status_code == 201
    assert c.post("/counts", json=body, headers=ranger).status_code == 201           # offline re-send: stored once
    assert len(c.get(f"/counts/{day}", headers=ranger).json()["counts"]) == 1
    assert c.post("/counts", json=body | {"seg_id": 99999, "client_id": None}, headers=ranger).status_code == 400
    r = c.get("/admin/forecast-check", params={"start": day, "end": day}, headers=officer).json()
    row = r["rows"][0]
    assert row["forecast"] == 40.0 and row["count"] == 30 and row["forecast_basis"] == "test forecast"
    assert r["summary"]["mae"] == 10.0 and r["summary"]["bias"] == 10.0
    assert c.get("/admin/forecast-check", params={"start": day, "end": day}, headers=ranger).status_code == 403
