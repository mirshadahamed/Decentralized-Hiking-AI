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
    assert first["places_left"] - 4 <= after["places_left"] <= first["places_left"] - 3   # 4 held x 0.8 expected


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


def test_gate_accepts_start_time_codes(tmp_path):
    """The ranger's normal check-in takes a start-time code: early -> come back, on time -> let in first (and it
    counts as an entry), a second time -> already used."""
    from datetime import datetime
    from src.control import booking
    db = tmp_path / "b.sqlite"
    with booking.closing(booking._connect(db)) as con:
        con.execute("INSERT INTO start_advice (code, day, trail, slot, group_size, created) VALUES "
                    "('ABC234','2026-11-02','main','08:30',3,'2026-11-01T10:00:00')")
        con.commit()
    early = booking.check_in("abc234", datetime(2026, 11, 2, 7, 50), db)
    assert not early["ok"] and early["kind"] == "start_time" and "Too early" in early["reason"]
    on_time = booking.check_in("ABC234", datetime(2026, 11, 2, 8, 25), db)
    assert on_time["ok"] and on_time["priority"]
    assert booking.entries("2026-11-02", db).to_dict("records") == [{"trail": "main", "gate_min": 505, "size": 3}]
    assert "Already used" in booking.check_in("ABC234", datetime(2026, 11, 2, 8, 30), db)["reason"]
    late = tmp_path / "c.sqlite"
    with booking.closing(booking._connect(late)) as con:
        con.execute("INSERT INTO start_advice (code, day, trail, slot, group_size, created) VALUES "
                    "('XYZ234','2026-11-02','main','08:30',2,'2026-11-01T10:00:00')")
        con.commit()
    r = booking.check_in("XYZ234", datetime(2026, 11, 2, 9, 0), late)
    assert not r["ok"] and not r["priority"] and "queue" in r["reason"]
    assert booking.check_in("NOPE22", datetime(2026, 11, 2, 9, 0), late)["reason"] == "Unknown code"


def test_morning_recheck_moves_a_hold_when_the_trail_is_closed(tmp_path):
    """An incident closes the trail on the day: the re-check says no room (or later) instead of 'still fine'."""
    from datetime import datetime
    from src.control import booking
    from src.control.slots import build_control
    from src.control.start_times import held, move, recheck
    db = tmp_path / "b.sqlite"
    trail = build_control().trails[0]
    with booking.closing(booking._connect(db)) as con:
        con.execute("INSERT INTO start_advice (code, day, trail, slot, group_size, created) VALUES "
                    "('QWE234','2026-11-02',?,'09:00',2,'2026-11-01T10:00:00')", (trail,))
        con.commit()
    now = datetime(2026, 11, 2, 7, 0)
    assert recheck("QWE234", now, 0.0, 600.0, db)["status"] == "ok"
    assert recheck("QWE234", datetime(2026, 11, 1, 20, 0), 0.0, 600.0, db)["status"] == "ok"   # not the day yet
    booking.set_condition("2026-11-02", "2026-11-02", trail, "closed", "fallen tree", "r1", db)
    r = recheck("QWE234", now, 0.0, 600.0, db)
    assert r["status"] == "full" and "closed" in r["note"]
    assert move("QWE234", "10:00", db)["slot"] == "10:00" and held("qwe234", db)["slot"] == "10:00"


def test_on_time_share_learns_from_arrivals_and_discounts_holds(tmp_path):
    from src.control import booking
    from src.control.start_times import _given, on_time_share
    db = tmp_path / "b.sqlite"
    with booking.closing(booking._connect(db)) as con:
        rows = [(f"C{i:05d}", "2026-11-01", "main", "08:00", 2, "x", "2026-11-01T08:05:00" if i < 5 else None)
                for i in range(20)]                                   # 5 of 20 came on time
        rows.append(("TODAY1", "2026-11-05", "main", "09:00", 10, "x", None))
        con.executemany("INSERT INTO start_advice (code, day, trail, slot, group_size, created, arrived_at) "
                        "VALUES (?,?,?,?,?,?,?)", rows)
        con.commit()
    s = on_time_share("2026-11-05", db)
    assert (s["holders"], s["came_on_time"]) == (20, 5) and s["share"] == round((5 + 8) / 30, 3)
    assert _given("2026-11-05", db)[("main", "09:00")] == pytest.approx(10 * s["share"])
    assert on_time_share("2026-11-01", db)["share"] == 0.8                # nothing before: the prior
