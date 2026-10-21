"""A2: forecast-driven daily quota in the ticket plan, officer capacity panel and quota decisions."""
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
    if api.ADVISORY:
        pytest.skip("booking parks only")
    tmp = tmp_path_factory.mktemp("cap")
    old = booking.DB, auth.DB
    booking.DB, auth.DB = tmp / "b.sqlite", tmp / "a.sqlite"           # never touch the real bookings / accounts
    auth.create_user("off", "a-long-password-1", "officer")
    auth.create_user("rng", "a-long-password-1", "ranger")
    c = TestClient(api.app)

    def tok(u):
        return {"Authorization": "Bearer " + c.post("/auth/login", json={"username": u, "password": "a-long-password-1"}).json()["token"]}
    yield c, tok("off"), tok("rng"), api.ctx()
    booking.DB, auth.DB = old


def test_forecast_lowers_quota_and_is_the_default(client):
    from src.control import booking
    from src.control.slots import build_control
    _, _, _, ctx = client
    day = (ctx.today + timedelta(days=3)).isoformat()
    ec = build_control()
    booking.save_forecast(day, np.full((24, len(ec.seg)), 1e4), "test: everything crowded")
    q = booking.resolve_quota(day, 0.2)
    main = ec.cfg["area"].get("main_trail", ec.trails[0])
    assert q[main]["rule"] == "forecast" and q[main]["applied"] == q[main]["forecast"]
    assert q[main]["forecast"] < q[main]["classic"]


def test_panel_officers_only_and_shape(client):
    c, officer, ranger, ctx = client
    day = (ctx.today + timedelta(days=2)).isoformat()
    assert c.get(f"/admin/capacity/{day}", headers=ranger).status_code == 403
    r = c.get(f"/admin/capacity/{day}", headers=officer)
    assert r.status_code == 200
    p = r.json()
    assert set(p["rules"]) == {"forecast", "classic", "static", "manual"}
    assert {"crowd", "weather", "sensors", "evidence"} <= set(p["basis"])
    for t in p["trails"]:
        q = t["quota"]
        assert q["applied"] >= 0 and q["static"] > 0 and q["forecast"] <= q["classic"]
        assert t["limiting_section"] and t["reason"]
    assert c.get(f"/admin/capacity/{ctx.today.isoformat()}", headers=officer).status_code == 400


def test_manual_quota_limits_the_ticket_plan(client):
    from src.control import booking
    c, officer, _, ctx = client
    day = (ctx.today + timedelta(days=4)).isoformat()
    trail = str(ctx.data.trails[0])
    booking.publish_day(day, 0.1, "test", wetness=0.0)
    before = int(booking._published(day).query("trail == @trail").tickets.sum())
    r = c.post("/admin/quota", json={"day": day, "trail": trail, "rule": "manual", "quota": 12}, headers=officer)
    assert r.status_code == 200
    after = booking._published(day).query("trail == @trail")
    assert after.tickets.sum() <= 12 < before
    q = c.get(f"/admin/capacity/{day}", headers=officer).json()
    row = next(t for t in q["trails"] if t["trail"] == trail)
    assert row["quota"]["rule"] == "manual" and row["quota"]["applied"] == 12
    assert c.post("/admin/quota", json={"day": day, "trail": trail, "rule": "manual"}, headers=officer).status_code == 400
    assert c.post("/admin/quota", json={"day": day, "trail": trail, "rule": "forecast"}, headers=officer).status_code == 200
