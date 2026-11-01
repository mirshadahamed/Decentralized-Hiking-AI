"""§6.2.7 SOS: nearest section from GPS, one call per phone, rangers mark it seen / closed, position deleted later."""
from datetime import datetime

import geopandas as gpd
import pytest
from shapely.geometry import LineString

from src.control import sos


@pytest.fixture
def world():
    cfg = {"area": {"trail_names": {"main": "Main loop", "side": "Side path"}, "poi_labels": {"wf": "the waterfall"}}}
    seg = gpd.GeoDataFrame({"seg_id": [0, 1], "trail": ["main", "side"], "poi": ["wf", ""]},
                           geometry=[LineString([(80.0, 7.0), (80.01, 7.0)]), LineString([(80.0, 7.01), (80.01, 7.01)])])
    return cfg, seg


def test_sos_from_gps_and_from_the_last_place(world, tmp_path):
    cfg, seg = world
    db = tmp_path / "b.sqlite"
    now = datetime(2026, 11, 2, 10, 0)
    r = sos.raise_sos(cfg, seg, now, "phone-0001", "injury", 3, "twisted ankle", lat=7.003, lon=80.005, db=db)
    assert r["place"] == "Main loop, the waterfall (330 m off the trail)" and r["status"] == "open" and "1990" in r["note"]
    # re-sent with a newer fix: the same call, not a second alarm
    r2 = sos.raise_sos(cfg, seg, now, "phone-0001", "injury", 3, lat=7.0099, lon=80.005, db=db)
    assert r2["id"] == r["id"] and r2["place"].startswith("Side path, section 1")
    sos.raise_sos(cfg, seg, now, "phone-0002", "lost", 2, trail="main", db=db)
    day = sos.calls("2026-11-02", db)
    assert day["open"] == 2 and day["calls"][0]["note"] is None and day["calls"][1]["note"] == "twisted ankle"
    sos.set_status(r["id"], "seen", "ranger1", now, db)
    assert "on the way" in sos.check("phone-0001", db)["note"]
    sos.set_status(r["id"], "closed", "ranger1", now, db)
    assert sos.calls("2026-11-02", db)["open"] == 1 and sos.calls("2026-11-02", db)["calls"][-1]["status"] == "closed"
    with pytest.raises(ValueError):
        sos.raise_sos(cfg, seg, now, "phone-0003", "bored", 1, db=db)


def test_position_and_note_are_deleted_after_keep_days(world, tmp_path):
    cfg, seg = world
    db = tmp_path / "b.sqlite"
    sos.raise_sos(cfg, seg, datetime(2026, 9, 1, 9), "phone-0009", "unwell", 1, "dizzy", lat=7.0, lon=80.0, db=db)
    assert sos.purge(datetime(2026, 11, 2), db) == 1
    c = sos.calls("2026-09-01", db)["calls"][0]
    assert c["lat"] is None and c["note"] is None and c["kind"] == "unwell" and c["place"].startswith("Main loop")
