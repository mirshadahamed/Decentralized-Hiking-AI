"""API: public booking flow, roles enforced on the server, lockout. Uses temporary databases."""
import pytest

from src.live.dataset import LIVE_NPZ

pytestmark = pytest.mark.skipif(not LIVE_NPZ.exists(), reason="run python -m src.live.refresh first")
PW = "correct-horse-battery"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from src.api import app as api, auth
    from src.control import booking
    monkeypatch.setattr(booking, "DB", tmp_path / "bookings.sqlite")
    monkeypatch.setattr(auth, "DB", tmp_path / "auth.sqlite")
    for name, role in (("ranger1", "ranger"), ("officer1", "officer"), ("admin1", "admin")):
        auth.create_user(name, PW, role)
    return TestClient(api.app)


def token(client, user):
    r = client.post("/auth/login", json={"username": user, "password": PW})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_public_endpoints(client):
    for path in ("/health", "/status", "/trails", "/outlook", "/forecast/tomorrow", "/slots/2026-11-24"):
        assert client.get(path).status_code == 200, path
    p = client.get("/plan/2026-11-24").json()
    assert {"visitors", "crowd_level", "suggestions"} <= set(p)
    assert client.get("/plan/2030-01-01").status_code == 400


def test_booking_flow(client):
    r = client.post("/bookings", json={"day": "2026-11-24", "trail": "main", "slot": "07:00", "group_size": 3})
    assert r.status_code == 201
    code = r.json()["code"]
    assert client.get(f"/bookings/{code}").json()["status"] == "booked"
    assert client.delete(f"/bookings/{code}").status_code == 200
    assert client.get(f"/bookings/{code}").json()["status"] == "cancelled"
    bad = client.post("/bookings", json={"day": "2026-11-24", "trail": "nowhere", "slot": "07:00", "group_size": 3})
    assert bad.status_code == 422


def test_full_slot_returns_alternatives(client):
    left = next(s["places_left"] for s in client.get("/slots/2026-11-24").json()["slots"]
                if s["slot"] == "07:00" and s["trail"] == "main")
    while left >= 20:
        client.post("/bookings", json={"day": "2026-11-24", "trail": "main", "slot": "07:00", "group_size": 20})
        left -= 20
    r = client.post("/bookings", json={"day": "2026-11-24", "trail": "main", "slot": "07:00", "group_size": 20})
    assert r.status_code == 409 and r.json()["alternatives"]


def test_roles_are_enforced(client):
    assert client.post("/checkin", json={"code": "X"}).status_code == 401
    ranger, officer, admin = token(client, "ranger1"), token(client, "officer1"), token(client, "admin1")
    closure = {"day": "2026-11-24", "trail": "thotupola", "slot_from": "10:00", "slot_to": "11:00", "reason": "storm"}
    assert client.post("/admin/closures", json=closure, headers=ranger).status_code == 403
    assert client.post("/admin/closures", json=closure, headers=officer).status_code == 200
    assert client.get("/admin/users", headers=officer).status_code == 403
    assert client.get("/admin/users", headers=admin).status_code == 200
    audit = client.get("/admin/audit", headers=admin).json()
    assert any(a["action"] == "closure" and a["username"] == "officer1" for a in audit)


def test_gate_flow_and_live_lights(client):
    code = client.post("/bookings", json={"day": "2026-11-24", "trail": "main", "slot": "07:00",
                                          "group_size": 4}).json()["code"]
    ranger = token(client, "ranger1")
    r = client.post("/checkin", json={"code": code, "at": "2026-11-24T07:05:00"}, headers=ranger).json()
    assert r["ok"]
    assert client.post("/walkins", json={"day": "2026-11-24", "trail": "main", "slot": "07:00", "group_size": 2,
                                         "at": "2026-11-24T07:10:00"}, headers=ranger).status_code == 200
    live = client.get("/live/2026-11-24", params={"at": "08:00"}, headers=ranger).json()
    assert sum(s["people"] for s in live["segments"]) > 0
    assert {s["light"] for s in live["segments"]} <= {"green", "amber", "red"}


def test_lockout_after_five_failures(client):
    for _ in range(5):
        assert client.post("/auth/login", json={"username": "ranger1", "password": "wrong-password"}).status_code == 401
    assert client.post("/auth/login", json={"username": "ranger1", "password": PW}).status_code == 401


def test_passwords_are_not_stored_in_plain_text(tmp_path):
    import sqlite3
    from src.api import auth
    db = tmp_path / "a.sqlite"
    auth.create_user("ranger9", PW, "ranger", db)
    raw = sqlite3.connect(db).execute("SELECT * FROM users").fetchone()
    assert PW.encode() not in b"".join(x if isinstance(x, bytes) else str(x).encode() for x in raw)
