"""R7: the wait at the gate, measured from a queue-join scan to check-in; start-time holders vs tickets."""
from datetime import datetime

from src.control import booking


def test_gate_wait_is_measured_from_the_queue_scan(tmp_path):
    db = tmp_path / "b.sqlite"
    d = "2026-11-02"
    with booking.closing(booking._connect(db)) as con:
        con.executemany("INSERT INTO bookings (code, day, trail, slot, group_size, created) VALUES (?,?,?,?,?,?)",
                        [("TICK0001", d, "t", "07:00", 4, "x"), ("TICK0002", d, "t", "07:00", 2, "x")])
        con.execute("INSERT INTO start_advice (code, day, trail, slot, group_size, created) VALUES "
                    "('STRT01', ?, 't', '07:00', 3, 'x')", (d,))
        con.commit()
    at = lambda hm: datetime.fromisoformat(f"{d}T{hm}")   # noqa: E731
    assert booking.queue_join("nope", at("06:50"), db)["ok"] is False
    assert booking.queue_join("tick0001", at("06:50"), db)["queued_at"].endswith("06:50:00")
    assert booking.queue_join("TICK0001", at("06:55"), db)["queued_at"].endswith("06:50:00")   # first scan counts
    booking.queue_join("STRT01", at("06:56"), db)
    assert booking.check_in("TICK0001", at("07:08"), db)["ok"]
    assert booking.check_in("STRT01", at("06:58"), db)["priority"]
    assert booking.check_in("TICK0002", at("07:10"), db)["ok"]          # not timed (no queue scan)
    w = booking.gate_waits(d, db)
    assert (w["groups_let_in"], w["groups_timed"]) == (3, 2)
    assert w["start_time_first"]["median_min"] == 2.0 and w["others"]["median_min"] == 18.0
