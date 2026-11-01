"""§6.1.2: start times by SMS for visitors without the app."""
from datetime import date, datetime

import pytest

from src.config import PROCESSED, load_config
from src.control import sms

CFG = load_config(park="horton_plains")
FRI = date(2026, 10, 30)
needs_data = pytest.mark.skipif(not (PROCESSED / "segments.geojson").exists(), reason="run src.data.build_dataset first")


def test_parse_takes_words_in_any_order():
    q = sms.parse("start 4 sat 08.30 kirigalpotta", CFG, FRI)
    assert q == {"trail": "kirigalpotta", "size": 4, "day": date(2026, 10, 31), "wanted": "08:30"}
    q = sms.parse("START 3 6 TOMORROW", CFG, FRI)                  # trail 3 of the HELP list, then 6 people
    assert q["trail"] == sms.trails(CFG)[2] and q["size"] == 6 and q["day"] == date(2026, 10, 31)
    assert sms.parse("START", CFG, FRI) == {"trail": "main", "size": 2, "day": FRI, "wanted": None}
    for bad in ("START 2030-01-01", "START 25:00", "START moon", "START 1 30"):
        with pytest.raises(ValueError):
            sms.parse(bad, CFG, FRI)


@needs_data
def test_start_holds_a_code_and_check_finds_it(tmp_path, monkeypatch):
    from src.control import booking
    monkeypatch.setattr(booking, "DB", tmp_path / "bookings.sqlite")
    now = datetime(2026, 10, 30, 6, 0)
    expect = lambda day: (0.0, 800.0)                                # dry day, 800 visitors
    r = sms.handle("START 1 3 SAT 07:00", CFG, now, expect)
    assert "Sat 31 Oct" in r and "3 people" in r and len(r) <= sms.MAX_LEN, r
    code = r.split("Code ")[1][:6]
    from src.control.start_times import held
    h = held(code)
    assert h["day"] == "2026-10-31" and h["group_size"] == 3 and h["slot"] >= "07:00"
    assert "Check again on the morning" in sms.handle(f"check {code}", CFG, now, expect)
    assert sms.handle("CHECK NOPE00", CFG, now, expect).startswith("Unknown code")
    assert "START 1 4 SAT 08:00" in sms.handle("hello", CFG, now, expect)
    assert "needs no start time" in sms.handle("START", load_config(park="adams_peak"), now, expect)
