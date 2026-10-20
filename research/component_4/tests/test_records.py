"""Officer records (GET /admin/records): daily visitors per trail for past, today and future days."""
import csv
import io
from datetime import date, timedelta

import pytest

from src.live.refresh import PUBLISHED

pytestmark = pytest.mark.skipif(not (PUBLISHED / "status.json").exists(), reason="run python -m src.live.refresh first")


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    from fastapi.testclient import TestClient
    from src.api import app as api, auth
    from src.control import booking
    tmp = tmp_path_factory.mktemp("rec")
    old = booking.DB, auth.DB
    booking.DB, auth.DB = tmp / "b.sqlite", tmp / "a.sqlite"           # never touch the real bookings / accounts
    auth.create_user("off", "a-long-password-1", "officer")
    auth.create_user("rng", "a-long-password-1", "ranger")
    c = TestClient(api.app)

    def tok(u):
        return {"Authorization": "Bearer " + c.post("/auth/login", json={"username": u, "password": "a-long-password-1"}).json()["token"]}
    yield c, tok("off"), tok("rng"), api.ctx()
    booking.DB, auth.DB = old


def test_officers_only(client):
    c, _, ranger, _ = client
    assert c.get("/admin/records", params={"start": "2026-01-01", "end": "2026-01-02"}).status_code == 401
    assert c.get("/admin/records", params={"start": "2026-01-01", "end": "2026-01-02"}, headers=ranger).status_code == 403


def test_past_today_future_per_trail(client):
    c, officer, _, ctx = client
    t0 = ctx.today
    r = c.get("/admin/records", params={"start": (t0 - timedelta(days=3)).isoformat(),
                                        "end": (t0 + timedelta(days=3)).isoformat()}, headers=officer)
    assert r.status_code == 200
    rows = r.json()["rows"]
    trails = list(r.json()["trails"])
    assert len(rows) == 7 * len(trails)                                     # one row per day and trail
    periods = {(x["date"], x["period"]) for x in rows}
    assert (t0.isoformat(), "today") in periods
    assert ((t0 - timedelta(days=1)).isoformat(), "past") in periods
    assert ((t0 + timedelta(days=1)).isoformat(), "future") in periods
    for x in rows:
        assert x["visitors"] is not None and x["visitors"] >= 0
        if x["period"] == "future":
            assert x["low"] <= x["visitors"] <= x["high"]                    # forecast with a range
        else:
            assert x["low"] is None
        assert x["gate_total"] == x["checked_in"] + x["walk_ins"]
    # past counts are the live dataset's daily visitors (the estimate, until DWC / gate data)
    k = (t0 - timedelta(days=1) - ctx.data.times[0].date()).days
    main = next(x for x in rows if x["date"] == (t0 - timedelta(days=1)).isoformat() and x["trail"] == trails[0])
    assert main["visitors"] == round(float(ctx.data.daily_visitors_by_trail[k, 0]))


def test_filter_by_trail_and_csv(client):
    c, officer, _, ctx = client
    trail = str(ctx.data.trails[0])
    p = {"start": (ctx.today - timedelta(days=10)).isoformat(), "end": ctx.today.isoformat(), "trail": trail}
    rows = c.get("/admin/records", params=p, headers=officer).json()["rows"]
    assert len(rows) == 11 and {x["trail"] for x in rows} == {trail}
    r = c.get("/admin/records", params=p | {"format": "csv"}, headers=officer)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    table = list(csv.DictReader(io.StringIO(r.text)))
    assert len(table) == 11 and table[0]["trail"] == trail


def test_bad_requests(client):
    c, officer, _, _ = client
    assert c.get("/admin/records", params={"start": "2026-02-01", "end": "2026-01-01"}, headers=officer).status_code == 400
    assert c.get("/admin/records", params={"start": "2024-01-01", "end": "2026-01-01"}, headers=officer).status_code == 400
    assert c.get("/admin/records", params={"start": "2026-01-01", "end": "2026-01-02", "trail": "nowhere"},
                 headers=officer).status_code == 400


def test_gate_counts_show_up(client):
    from src.control import booking
    c, officer, _, ctx = client
    day = (ctx.today + timedelta(days=2)).isoformat()
    trail = str(ctx.data.trails[0])
    slot = booking.availability(day).index[2]
    booking.book(day, trail, slot, 3, today=ctx.today.isoformat())
    row = next(x for x in c.get("/admin/records", params={"start": day, "end": day, "trail": trail},
                                headers=officer).json()["rows"])
    assert row["booked"] == 3                                            # this system's own record of the day
    assert row["safe_limit"] is None or row["safe_limit"] >= row["booked"]
    assert date.fromisoformat(row["date"]) > ctx.today and row["period"] == "future"
