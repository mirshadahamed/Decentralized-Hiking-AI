"""Live mode: freeze rule, closures, walk-ins, and the live dataset (if a refresh has been run)."""
from datetime import date

import numpy as np
import pandas as pd
import pytest

from src.config import PROCESSED

pytestmark = pytest.mark.skipif(not (PROCESSED / "dataset.npz").exists(),
                                reason="run python -m src.data.build_dataset first")
DAY = "2026-11-24"


@pytest.fixture()
def db(tmp_path):
    return tmp_path / "b.sqlite"


def test_freeze_rule_never_drops_below_booked(db):
    from src.control import booking as b
    b.publish_day(DAY, 0.0, "test", db)                      # dry day: generous plan
    left = int(b.availability(DAY, db).loc["07:00", "main"])
    n = 0
    while n + 5 <= left:
        b.book(DAY, "main", "07:00", 5, today="2026-10-15", db=db)
        n += 5
    alerts = b.publish_day(DAY, 0.9, "test", db)             # forecast turns very wet: capacity drops
    sup = b.supply(DAY, db)
    assert sup.loc["07:00", "main"] >= n                     # booked places kept
    assert any(a["slot"] == "07:00" and a["trail"] == "main" for a in alerts)
    assert b.walk_in_left(DAY, db).loc["07:00", "main"] == 0  # walk-ins cut first


def test_closure_removes_tickets_and_alerts(db):
    from src.control import booking as b
    b.publish_day(DAY, 0.0, "test", db)
    code = b.book(DAY, "thotupola", "09:00", 3, today="2026-10-15", db=db)
    alerts = b.close(DAY, "thotupola", "08:30", "10:00", "landslide", "officer1", db)
    sup = b.supply(DAY, db)
    assert sup.loc["10:00", "thotupola"] == 0 and sup.loc["08:30", "thotupola"] == 0
    assert sup.loc["09:00", "thotupola"] == 3                # the existing booking is kept, never silently cancelled
    assert [a for a in alerts if a["slot"] == "09:00" and a["reason"] == "closed"]
    assert b.bookings_for_code(code, db)["status"] == "booked"


def test_trail_condition_lowers_tickets_and_keeps_bookings(db):
    from src.control import booking as b
    b.publish_day(DAY, 0.0, "test", db)
    good = b.supply(DAY, db)["main"].sum()
    b.set_condition(DAY, DAY, "main", "muddy", "wet boardwalk", "officer1", db)
    muddy = b.supply(DAY, db)["main"].sum()
    assert muddy < good                                       # fewer tickets on a muddy trail
    assert b.conditions(DAY, db)["main"]["level"] == "muddy"
    code = b.book(DAY, "thotupola", "09:00", 3, today="2026-10-15", db=db)
    alerts = b.set_condition(DAY, DAY, "thotupola", "closed", "landslide", "officer1", db)
    sup = b.supply(DAY, db)
    assert sup["thotupola"].sum() == 3                        # closed: only the existing booking stays
    assert [a for a in alerts if a["trail"] == "thotupola" and a["reason"] == "closed"]
    assert b.bookings_for_code(code, db)["status"] == "booked"
    b.set_condition(DAY, DAY, "main", "good", "", "officer1", db)          # 'good' clears the report
    assert "main" not in b.conditions(DAY, db) and b.supply(DAY, db)["main"].sum() == good


def test_wet_ground_lowers_the_daily_quota():
    from src.control.slots import build_control
    ec = build_control()
    dry, wet = ec.daily_quota(0.0), ec.daily_quota(0.0, wetness=1.0)
    assert wet["main"] < dry["main"]                          # the loop has waterlogging-prone ground
    assert all(wet[t] <= dry[t] for t in dry)
    assert ec.daily_quota(0.0, conditions={"main": 1.0})["main"] == 0
    assert ec.daily_quota(0.0, wetness=0.0, conditions={}) == dry          # defaults: research results unchanged


def test_walk_in_sales_are_limited(db):
    from src.control import booking as b
    b.publish_day(DAY, 0.0, "test", db)
    left = int(b.walk_in_left(DAY, db).loc["07:00", "main"])
    assert left > 0
    assert b.sell_walk_in(DAY, "main", "07:00", left, "ranger1", db) == 0
    with pytest.raises(b.SlotFull):
        b.sell_walk_in(DAY, "main", "07:00", 1, "ranger1", db)


def test_booking_a_real_future_date(db):
    from src.control import booking as b
    code = b.book(DAY, "main", "07:00", 2, today="2026-10-15", db=db)
    assert len(code) == 8


def test_live_dataset_if_built():
    from src.live.dataset import LIVE_NPZ
    if not LIVE_NPZ.exists():
        pytest.skip("no live refresh yet")
    d = np.load(LIVE_NPZ, allow_pickle=True)
    times = pd.to_datetime(d["times"].astype("datetime64[h]"))
    today = date.fromisoformat(str(d["live_today"]))
    t_idx = (pd.Timestamp(today) - times[0]).days
    assert times[-1] >= pd.Timestamp(today) + pd.Timedelta(days=89)
    assert (d["day_source"][t_idx + 1:] == "future").all()     # no invented history after today
    assert d["daily_visitors"][t_idx + 1:].sum() == 0
    assert d["occ_obs"].shape[1] == d["static"].shape[0]
