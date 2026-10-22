"""A1: today's forecast updated from the rangers' spot counts (spot-trained ST-GNN, RQ11b)."""
import pytest

from src.config import RESULTS
from src.live.refresh import PUBLISHED

pytestmark = pytest.mark.skipif(not (PUBLISHED / "status.json").exists() or not (RESULTS / "LATEST_SPARSE_S1").exists(),
                                reason="needs the live refresh and a spot run (src.eval.sparse_sensors --settings spot)")


@pytest.fixture(scope="module")
def setup():
    from src.api import app as api
    from src.live.intraday import _load, model_sections
    c = api.ctx()
    if _load(c) is None:
        pytest.skip("no spot model for this park")
    return c, sorted(model_sections(c))


def test_counts_raise_the_forecast_where_they_are_high(setup):
    from src.live.intraday import update_today
    ctx, counted = setup
    day = ctx.today
    quiet = update_today(ctx, day, 10 * 60, [])
    seg = counted[len(counted) // 2]
    crowd = [{"seg_id": seg, "time_min": m, "count": 400} for m in (7 * 60 + 10, 8 * 60 + 20, 9 * 60 + 30)]
    busy = update_today(ctx, day, 10 * 60, crowd)
    assert quiet["counts_used"] == 0 and busy["counts_used"] == 3 and busy["from_hour"] == 11
    q = sum(sum(s["updated"]) for s in quiet["sections"])
    b = sum(sum(s["updated"]) for s in busy["sections"])
    assert b > q                                                     # many people counted -> more people expected
    s_q = next(s for s in quiet["sections"] if s["seg_id"] == seg)
    assert len(s_q["morning"]) == len(s_q["updated"]) == 24 - 11


def test_counts_elsewhere_are_not_model_input(setup):
    from src.live.intraday import update_today
    ctx, counted = setup
    other = next(int(i) for i in ctx.seg.seg_id if int(i) not in counted)
    r = update_today(ctx, ctx.today, 10 * 60, [{"seg_id": other, "time_min": 8 * 60, "count": 50}])
    assert r["counts_used"] == 0 and r["counts_not_used"] == 1


def test_segments_flag_the_model_sections(setup):
    from fastapi.testclient import TestClient
    from src.api import app as api
    _, counted = setup
    s = TestClient(api.app).get("/segments").json()
    assert {x["seg_id"] for x in s if x["model_input"]} == set(counted)
    assert s[0]["model_input"]                                       # listed first
