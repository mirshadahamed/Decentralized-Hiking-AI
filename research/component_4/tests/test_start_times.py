"""N3 live: start times for visitors without a ticket, filled against the controller's day plan."""
from datetime import timedelta

import pytest

from src.live.refresh import PUBLISHED

pytestmark = pytest.mark.skipif(not (PUBLISHED / "status.json").exists(), reason="run python -m src.live.refresh first")


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    from fastapi.testclient import TestClient
    from src.api import app as api
    from src.control import booking
    old = booking.DB
    booking.DB = tmp_path_factory.mktemp("st") / "b.sqlite"
    yield TestClient(api.app), api.ctx()
    booking.DB = old


def test_suggestion_never_earlier_and_holding_fills_the_plan(client):
    c, ctx = client
    day = (ctx.today + timedelta(days=2)).isoformat()
    trail = str(ctx.data.trails[0])
    s = c.get(f"/start-time/{day}", params={"trail": trail, "wanted": "08:00", "size": 4}).json()
    assert s["wanted"] == "08:00" and s["options"]
    assert all(o["slot"] >= "08:00" for o in s["options"])
    if s["suggested"] is None:
        pytest.skip("the plan is full that day")
    first = next(o for o in s["options"] if o["slot"] == s["suggested"])
    h = c.post("/start-time", json={"day": day, "trail": trail, "slot": s["suggested"], "group_size": 4})
    assert h.status_code == 201 and len(h.json()["code"]) == 6
    again = c.get(f"/start-time/{day}", params={"trail": trail, "wanted": "08:00", "size": 4}).json()
    after = next(o for o in again["options"] if o["slot"] == s["suggested"])
    assert after["places_left"] == first["places_left"] - 4


def test_full_slot_is_refused(client):
    c, ctx = client
    day = (ctx.today + timedelta(days=3)).isoformat()
    trail = str(ctx.data.trails[0])
    s = c.get(f"/start-time/{day}", params={"trail": trail, "wanted": "07:00", "size": 1}).json()
    full = next((o for o in s["options"] if o["places_left"] < 20), None)
    if full is None:
        pytest.skip("no nearly full slot")
    r = c.post("/start-time", json={"day": day, "trail": trail, "slot": full["slot"], "group_size": 20})
    assert r.status_code == 409
