"""Item 12: the end-of-day report adds up check-ins, walk-ins, start times, no-shows and reported conditions."""
import pytest

from src.config import PROCESSED, load_config

pytestmark = pytest.mark.skipif(not (PROCESSED / "segments.geojson").exists(), reason="run src.data.build_dataset first")


def test_day_report_counts_every_way_in(tmp_path):
    from src.control import booking
    from src.serve.day_report import day_report, to_html
    cfg = load_config()
    t = next(iter(cfg["area"]["trail_names"]))
    db = tmp_path / "b.sqlite"
    d = "2026-11-02"
    with booking.closing(booking._connect(db)) as con:
        con.executemany("INSERT INTO bookings (code, day, trail, slot, group_size, created, status, checked_in_at) "
                        "VALUES (?,?,?,?,?,?,?,?)",
                        [("AAAA2222", d, t, "07:00", 4, "x", "checked_in", f"{d}T07:05:00"),
                         ("BBBB2222", d, t, "07:30", 2, "x", "booked", None)])
        con.execute("INSERT INTO walkins (day, trail, slot, group_size, sold_by, sold_at) VALUES (?,?,?,?,?,?)",
                    (d, t, "08:00", 3, "r1", f"{d}T08:02:00"))
        con.execute("INSERT INTO start_advice (code, day, trail, slot, group_size, created, arrived_at) VALUES "
                    "('CCC222',?,?,'08:30',5,'x',?)", (d, t, f"{d}T08:31:00"))
        con.commit()
    booking.set_condition(d, d, t, "muddy", "after rain", "r1", db)
    r = day_report(cfg, d, db)
    row = next(x for x in r["trails"] if x["trail"] == t)
    assert r["entered"] == 12 and row["entered"] == 12
    assert (row["tickets_checked_in"], row["tickets_no_show"], row["walk_ins"], row["start_time_on_time"]) == (4, 2, 3, 5)
    assert r["busiest_gate_hour"] == {"hour": "08:00", "people": 8}
    assert any("muddy - after rain" in x for x in r["lines"]) and any("No spot counts" in x for x in r["lines"])
    assert any("5 people held one, 5 came on time (100 %)" in x for x in r["lines"])
    assert "<table>" in to_html(r) and d in to_html(r)


def test_trends_add_up_the_day_reports_per_week(tmp_path):
    from src.control import booking
    from src.serve.day_report import trends
    cfg = load_config()
    t = next(iter(cfg["area"]["trail_names"]))
    db = tmp_path / "b.sqlite"
    with booking.closing(booking._connect(db)) as con:
        con.executemany("INSERT INTO bookings (code, day, trail, slot, group_size, created, status, checked_in_at) "
                        "VALUES (?,?,?,?,?,?,?,?)",
                        [("AAAA2222", "2026-11-02", t, "07:00", 4, "x", "checked_in", "2026-11-02T07:05:00"),
                         ("BBBB2222", "2026-11-03", t, "07:30", 4, "x", "booked", None),
                         ("CCCC2222", "2026-11-10", t, "07:30", 3, "x", "checked_in", "2026-11-10T07:31:00")])
        con.commit()
    r = trends(cfg, "2026-11-15", 14, db)
    assert [w["week"] for w in r["weeks"]] == ["2026-11-02", "2026-11-09"]
    assert (r["weeks"][0]["entered"], r["weeks"][0]["no_show_pct"]) == (4, 50)
    assert r["lines"][1].startswith("Week of 2026-11-09: 3 entered · no-shows 0 %")
