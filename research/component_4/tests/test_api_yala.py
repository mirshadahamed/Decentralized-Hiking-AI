"""Yala API: tickets per circuit and sighting management. The app reads C4_PARK on import, so these tests run in
their own pytest process (test_yala_api_in_its_own_process); run directly with:
    $env:C4_PARK = "yala"; python -m pytest tests/test_api_yala.py
"""
import os
import subprocess
import sys

import pytest

from src.config import PARK, ROOT

PW = "correct-horse-battery"
YALA_LIVE = ROOT / "data" / "yala" / "live" / "published" / "status.json"
in_yala = pytest.mark.skipif(PARK != "yala", reason="runs in the Yala process")


@pytest.mark.skipif(PARK == "yala" or not YALA_LIVE.exists(),
                    reason="needs the Yala refresh: $env:C4_PARK='yala'; python -m src.live.refresh")
def test_yala_api_in_its_own_process():
    out = subprocess.run([sys.executable, "-m", "pytest", "-q", "-W", "ignore", "-p", "no:cacheprovider", __file__],
                         capture_output=True, text=True, cwd=ROOT, env=dict(os.environ, C4_PARK="yala"))
    assert out.returncode == 0, out.stdout[-3000:]
    assert "3 passed" in out.stdout, out.stdout[-3000:]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from src.api import app as api, auth
    from src.control import booking
    monkeypatch.setattr(booking, "DB", tmp_path / "bookings.sqlite")
    monkeypatch.setattr(auth, "DB", tmp_path / "auth.sqlite")
    auth.create_user("ranger1", PW, "ranger")
    c = TestClient(api.app)
    tok = c.post("/auth/login", json={"username": "ranger1", "password": PW}).json()["token"]
    c.headers.update({"Authorization": f"Bearer {tok}"})
    return c


@in_yala
def test_safari_destination_and_circuits(client):
    d = client.get("/destination").json()
    assert d["kind"] == "safari" and d["booking_mode"] == "required"
    assert set(d["trails"]) == {"patanangala", "southern", "katagamuwa"}
    assert client.get("/status").json()["sightings"] is True


@in_yala
def test_sighting_gives_the_rule_and_ends(client):
    from src.control import booking
    seg = next(s["seg_id"] for s in client.get("/segments").json() if "Heenwewa" in s["name"])
    day = "2026-11-10"
    con = booking._connect()                            # 30 jeeps through Palatupana from 06:00 to 06:30
    for k in range(30):
        con.execute("INSERT INTO walkins (day, trail, slot, group_size, sold_at, sold_by) VALUES (?,?,?,?,?,?)",
                    (day, "patanangala", "06:00", 5, f"{day}T06:{k:02d}:00", "ranger1"))
    con.commit()
    con.close()
    r = client.post("/sightings", json={"day": day, "seg_id": seg, "time": "07:10", "species": "leopard",
                                        "client_id": "abc"})
    assert r.status_code == 201
    s = r.json()["sightings"]
    assert len(s) == 1 and s[0]["place"] == "Heenwewa Tank" and s[0]["cap_jeeps"] == 10
    assert "at most 10 jeeps" in s[0]["advice"]
    again = client.post("/sightings", json={"day": day, "seg_id": seg, "time": "07:10", "client_id": "abc"})
    assert len(again.json()["sightings"]) == 1                           # sent twice from an offline phone: one
    assert client.get(f"/sightings/{day}", params={"at": "06:00"}).json()["sightings"] == []   # not yet
    assert client.post(f"/sightings/{s[0]['id']}/end", json={"time": "07:40"}).status_code == 200
    assert client.get(f"/sightings/{day}", params={"at": "07:45"}).json()["sightings"] == []


@in_yala
def test_rangers_only_and_bad_section(client):
    r = client.post("/sightings", json={"day": "2026-11-10", "seg_id": 9999, "time": "07:10"})
    assert r.status_code == 400
    client.headers.pop("Authorization")
    assert client.get("/sightings/2026-11-10").status_code == 401
