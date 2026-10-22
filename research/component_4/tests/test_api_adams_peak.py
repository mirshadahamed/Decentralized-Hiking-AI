"""Adam's Peak API (advisory mode: no tickets) and the parks gateway.
The app reads C4_PARK on import, so the Adam's Peak tests run in their own pytest process
(test_adams_peak_api_in_its_own_process); run directly with:
    $env:C4_PARK = "adams_peak"; python -m pytest tests/test_api_adams_peak.py
"""
import os
import subprocess
import sys

import pytest

from src.config import PARK, ROOT

PW = "correct-horse-battery"
AP_LIVE = ROOT / "data" / "adams_peak" / "live" / "published" / "advisory.json"
in_ap = pytest.mark.skipif(PARK != "adams_peak", reason="runs in the Adam's Peak process")


# ---------- runs in the normal (Horton Plains) process ----------
@pytest.mark.skipif(PARK == "adams_peak" or not AP_LIVE.exists(),
                    reason="needs the Adam's Peak refresh: $env:C4_PARK='adams_peak'; python -m src.live.refresh")
def test_adams_peak_api_in_its_own_process():
    out = subprocess.run([sys.executable, "-m", "pytest", "-q", "-W", "ignore", "-p", "no:cacheprovider", __file__],
                         capture_output=True, text=True, cwd=ROOT, env=dict(os.environ, C4_PARK="adams_peak"))
    assert out.returncode == 0, out.stdout[-3000:]
    assert "6 passed" in out.stdout, out.stdout[-3000:]                    # the 6 Adam's Peak tests really ran


def test_gateway_lists_parks_and_forwards():
    from fastapi.testclient import TestClient
    from src.api import gateway
    c = TestClient(gateway.app)
    parks = {p["id"]: p for p in c.get("/parks").json()}
    assert {"horton_plains", "adams_peak"} <= set(parks)
    assert parks["adams_peak"]["booking_mode"] == "advisory"
    assert parks["horton_plains"]["booking_mode"] != "advisory"
    for p in parks.values():                                    # what the trip planner needs for every destination
        assert p["kind"] and p["summary"] and p["best_time"] and p["getting_there"] and p["trails"]
    assert (parks["adams_peak"]["kind"], parks["horton_plains"]["kind"]) == ("pilgrimage", "national_park")
    if "yala" in parks:
        assert parks["yala"]["kind"] == "safari" and parks["yala"]["booking_mode"] == "required"
    assert "nallathanniya" in parks["adams_peak"]["trails"]
    assert c.get("/parks/nowhere/health").status_code == 404
    gateway.PORTS["adams_peak"] = 1                           # nothing listens there
    try:
        assert c.get("/parks/adams_peak/health").status_code == 503
    finally:
        gateway.PORTS["adams_peak"] = 8101 + gateway.PARKS.index("adams_peak")


# ---------- runs in the Adam's Peak process ----------
@pytest.fixture()
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from src.api import app as api, auth
    from src.control import booking
    monkeypatch.setattr(booking, "DB", tmp_path / "bookings.sqlite")
    monkeypatch.setattr(auth, "DB", tmp_path / "auth.sqlite")
    auth.create_user("ranger1", PW, "ranger")
    auth.create_user("officer1", PW, "officer")
    return TestClient(api.app)


def ranger(client, user="ranger1"):
    r = client.post("/auth/login", json={"username": user, "password": PW})
    return {"Authorization": f"Bearer {r.json()['token']}"}


@in_ap
def test_status_and_advisory(client):
    s = client.get("/status").json()
    assert s["park"] == "adams_peak" and s["booking_mode"] == "advisory"
    day = client.get("/outlook").json()["days"][5]["date"]
    a = client.get(f"/advisory/{day}")
    assert a.status_code == 200, a.text
    a = a.json()
    assert set(a["routes"]) == {"nallathanniya", "palabaddala", "erathna", "dikelikanda"}
    for r in a["routes"].values():
        assert all(w["expected_wait_min"] <= a["limit_min"] for w in r["windows"] if w["recommended"])
    assert client.get("/advisory/2030-01-01").status_code == 400


@in_ap
def test_no_tickets_at_a_pilgrim_site(client):
    day = client.get("/outlook").json()["days"][5]["date"]
    assert client.get(f"/slots/{day}").status_code == 400
    r = client.post("/bookings", json={"day": day, "trail": "nallathanniya", "slot": "02:00", "group_size": 2})
    assert r.status_code == 400


@in_ap
def test_halfway_checks(client):
    day = client.get("/outlook").json()["days"][5]["date"]
    assert client.get(f"/checkpoints/{day}").status_code == 401             # rangers only
    h = ranger(client)
    quiet = client.get(f"/checkpoints/{day}", params={"at": "02:00"}, headers=h).json()
    assert quiet["hold"] is False and all(c["release_per_10_min"] is None for c in quiet["checkpoints"])
    for m in range(0, 60, 10):                                              # a rush: 6 x 900 people in an hour
        r = client.post("/checkpoints", json={"route": "nallathanniya", "count": 900,
                                              "at": f"{day}T02:{m:02d}:00"}, headers=h)
        assert r.status_code == 200, r.text
    busy = r.json()
    assert busy["hold"] is True and busy["wait_ahead_max_min"] > 20
    cp = {c["route"]: c for c in busy["checkpoints"]}
    assert cp["nallathanniya"]["counted_today"] == 5400
    assert cp["nallathanniya"]["last_count_at"] == "02:50"
    assert all(c["release_per_10_min"] is not None for c in cp.values())
    assert [x["time"] for x in busy["log"][:2]] == ["02:50", "02:40"] and busy["log"][0]["by"] == "ranger1"


@in_ap
def test_evening_counts_belong_to_the_next_night(client):
    h = ranger(client)
    r = client.post("/checkpoints", json={"route": "nallathanniya", "count": 120, "at": "2026-12-24T22:00:00"},
                    headers=h).json()
    assert r["day"] == "2026-12-25"                         # 22:00 on 24 Dec climbs for the sunrise of 25 Dec
    night = client.get("/checkpoints/2026-12-25", params={"at": "01:00"}, headers=h).json()
    assert [x["time"] for x in night["log"]] == ["22:00"]
    assert next(c for c in night["checkpoints"] if c["route"] == "nallathanniya")["counted_today"] == 120
    assert client.get("/checkpoints/2026-12-24", params={"at": "03:00"}, headers=h).json()["log"] == []


@in_ap
def test_destination_and_season_plan(client):
    d = client.get("/destination").json()
    assert d["id"] == "adams_peak" and d["kind"] == "pilgrimage" and len(d["trails"]) == 4
    assert client.get("/admin/season", headers=ranger(client)).status_code == 403          # officers only
    s = client.get("/admin/season", headers=ranger(client, "officer1")).json()
    assert len(s["days"]) >= 80 and s["limit_min"] == 20
    for n in s["days"]:
        assert n["checks"] in ("needed", "standby", "none")
        assert (n["checks"] == "needed") == bool(n["hold_windows"])
        assert n["high_peak_wait_min"] >= n["peak_wait_min"]                     # the high case is never quieter
    a = client.get(f"/advisory/{s['days'][5]['date']}").json()
    s = a["summit"]                                       # the night runs from 18:00 the evening before to midnight
    assert len(s["wait_by_time"]) == (1440 - s["first_bin_min"]) // s["bin_min"] and "high_case" in a
    assert s["first_bin"] == "18:00" and a["sunrise"] < "06:30"
