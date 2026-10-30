"""Knuckles mechanisms: guide-aware permit LP, permits first come first served, out / back / overdue,
viewpoint and parking advice, campsite pitches."""
from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from src.config import load_config
from src.control import permits


@pytest.fixture()
def cfg():
    return load_config(park="knuckles")


def test_lp_sends_guides_where_the_demand_is_and_respects_caps():
    entry = {"a": "e1", "b": "e1", "c": "e2"}
    x = permits.plan_permits({"a": 60, "b": 600, "c": 30}, {"a": 10, "b": 3, "c": 10}, entry, {"e1": 6, "e2": 9}, 6)
    assert x["a"] + x["b"] <= 6 and x["c"] <= 5                       # guides at e1; cap 30 / 6 at c
    assert x["a"] + x["b"] == 6 and x["a"] >= 4 and x["b"] >= 1       # all guides used, spread by requests
    assert permits.plan_permits({"a": 0}, {"a": 5}, {"a": "e1"}, {"e1": 4}, 6) == {"a": 0}


def test_permits_full_offers_another_trek_or_day_then_out_back_and_overdue(cfg, tmp_path):
    db = tmp_path / "b.sqlite"
    caps = {t: 600.0 for t in cfg["control"]["permits"]["treks"]} | {"maningala": 8.0}
    req = {"maningala": 1, "gombaniya": 3, "five_peaks": 2, "duwili_ella": 2, "lakegala": 2}
    plan = permits.day_plan(cfg, "2027-01-09", caps, req, db)
    row = next(x for x in plan["treks"] if x["trail"] == "maningala")
    assert row["people_left"] == 8 and row["groups_left"] == 6 and row["guides_suggested"] == 1
    p = permits.request(cfg, "2027-01-09", "maningala", 5, plan, db)
    plan = permits.day_plan(cfg, "2027-01-09", caps, req, db)
    assert next(x for x in plan["treks"] if x["trail"] == "gombaniya")["groups_left"] == 5   # one Riverston guide out
    with pytest.raises(permits.PermitFull, match="only 3 places") as e:
        permits.request(cfg, "2027-01-09", "maningala", 4, plan, db, other_days=["2027-01-10"])
    assert {a["trail"] for a in e.value.alternatives} >= {"gombaniya", "maningala"}   # same entry, or another day
    out = permits.check_out(cfg, p["code"], datetime(2027, 1, 9, 7, 0), rain_share=0.0, db=db)
    assert out["expected_back"] == "2027-01-09T12:06:00"            # 5 h x (1 + 0.02 x 1 above 4 people)
    # margin: 2.3 x 0.15 x 306 min = 106 min (more than the 45 min floor); 30 min less in full rain
    assert permits.overdue(cfg, "2027-01-09", datetime(2027, 1, 9, 13, 50), db=db)["overdue"] == []
    late = permits.overdue(cfg, "2027-01-09", datetime(2027, 1, 9, 13, 55), db=db)
    assert [x["code"] for x in late["overdue"]] == [p["code"]] and late["overdue"][0]["late_min"] == 109
    assert late["overdue"][0]["alarm_after_min"] == 106
    rainy = permits.overdue(cfg, "2027-01-09", datetime(2027, 1, 9, 13, 25), rain_share=1.0, db=db)
    assert len(rainy["overdue"]) == 1 and rainy["overdue"][0]["alarm_after_min"] == 76   # sooner alarm in rain
    permits.check_back(p["code"], datetime(2027, 1, 9, 13, 40), db)
    assert permits.overdue(cfg, "2027-01-09", datetime(2027, 1, 9, 14, 0), db=db)["overdue"] == []


def test_viewpoint_busy_hours_and_parking(cfg):
    from src.serve.viewpoints import viewpoint_outlook
    seg = pd.DataFrame({"seg_id": [0, 1, 2], "trail": ["pitawala", "pitawala", "sera_ella"],
                        "length_m": [400.0, 400.0, 500.0], "poi": ["head_pitawala", "pitawala_vp", "sera_ella"]})
    hourly = np.zeros((24, 3))
    hourly[9:12, 1] = 80                                              # 80 people at the edge 09-12 (holds 40)
    hourly[9:12, 0] = 200                                             # ... plus 200 walking: 280 / 4 = 70 cars > 60
    out = viewpoint_outlook(cfg, seg, hourly, ["pitawala", "sera_ella"], "2027-01-09",
                            {"pitawala": {"level": "partly_closed", "note": "parking full"}})
    v = {x["trail"]: x for x in out["viewpoints"]}
    assert v["pitawala"]["level"] == "crowded" and v["pitawala"]["parking_full_hours"] == ["09:00", "10:00", "11:00"]
    assert "Come before 08:00" in v["pitawala"]["advice"] and "parking full" in v["pitawala"]["reported"]
    assert v["sera_ella"]["level"] == "quiet" and v["sera_ella"]["advice"] == "Quiet all day."


def test_campsite_pitches(cfg, tmp_path):
    from src.serve.viewpoints import book_campsite, campsites
    db = tmp_path / "b.sqlite"
    b = book_campsite(cfg, "2027-01-09", "duwili_cave", 4, 10, db)
    assert len(b["code"]) == 7
    left = {s["site"]: s["left"] for s in campsites(cfg, "2027-01-09", db)["sites"]}
    assert left["duwili_cave"] == 2 and left["nature_camp"] == 15
    with pytest.raises(ValueError, match="2 pitch"):
        book_campsite(cfg, "2027-01-09", "duwili_cave", 3, 8, db)


def test_guided_treks_go_as_guided_groups_and_river_treks_close_in_rain(cfg):
    from src.sim.simulator import guided_regroup, rain_closed
    p = cfg["simulator"]
    trails = np.array(["pitawala", "duwili_ella"])
    rng = np.random.default_rng(0)
    size = 1 + rng.poisson(3, 200).astype(float)
    arrive = rng.uniform(360, 780, 200)
    option = rng.integers(0, 2, 200)
    s2, a2, o2 = guided_regroup(size, arrive, option, trails, p, np.random.default_rng(1))
    for k in (0, 1):                                         # people per trail kept
        assert s2[o2 == k].sum() == size[option == k].sum()
    assert (s2[o2 == 0] == size[option == 0]).all()          # walk-ups unchanged
    g = s2[o2 == 1]
    assert (g[:-1] >= 4).all() and (g <= 12).all() and abs(a2[o2 == 1].mean() - 420) < 30
    dry, wet = np.zeros(24), np.zeros(24)
    wet[7:10] = 6.0                                          # 18 mm in the morning
    assert rain_closed(list(trails), dry, p) == []
    assert rain_closed(list(trails) + ["lakegala"], wet, p) == ["duwili_ella"]
    assert guided_regroup(size, arrive, option, trails, {}, rng)[0] is size   # other parks: no change


def test_walk_register_any_park_uses_the_graph_walking_time(tmp_path):
    from src.config import PROCESSED
    if not (PROCESSED / "segments.geojson").exists():
        pytest.skip("run src.data.build_dataset first")
    cfg = load_config()                                       # Horton Plains: no guided treks
    t = next(iter(cfg["area"]["trail_names"]))
    db = tmp_path / "b.sqlite"
    now = datetime(2026, 11, 2, 7, 0)
    w = permits.register_walk(cfg, t, 4, now, db=db)
    hours = (datetime.fromisoformat(w["expected_back"]) - now).total_seconds() / 3600
    assert w["code"].startswith("W") and 0.5 < hours < 8
    late = now + (datetime.fromisoformat(w["expected_back"]) - now) * 2
    assert [g["code"] for g in permits.overdue(cfg, "2026-11-02", late, db=db)["overdue"]] == [w["code"]]
    permits.check_back(w["code"], late, db=db)
    assert permits.overdue(cfg, "2026-11-02", late, db=db)["overdue"] == []
    with pytest.raises(KeyError):
        permits.register_walk(cfg, "nope", 2, now, db=db)
