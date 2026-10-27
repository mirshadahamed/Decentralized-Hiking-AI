"""W-a: the weather of a chosen date - observed, forecast or typical - and its effect on the crowd and safe limit."""
from datetime import timedelta

import pytest

from src.live.refresh import PUBLISHED

pytestmark = pytest.mark.skipif(not (PUBLISHED / "status.json").exists(), reason="run python -m src.live.refresh first")


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from src.api import app as api
    return TestClient(api.app), api.ctx()


@pytest.mark.parametrize("offset, basis", [(-30, "observed"), (3, "forecast"), (60, "typical")])
def test_basis_follows_the_date(client, offset, basis):
    c, ctx = client
    r = c.get(f"/weather/{(ctx.today + timedelta(days=offset)).isoformat()}")
    assert r.status_code == 200
    w = r.json()
    assert w["basis"] == basis and len(w["hourly"]) == 24
    s = w["summary"]
    assert 0 <= s["rain_share_open_hours"] <= 1 and s["temp_min"] <= s["temp_max"]
    assert s["rainy_open_hours"] + sum(x["to"] - x["from"] for x in s["dry_windows"]) <= len(w["open_hours"])
    assert 35 <= w["effect"]["visitors_kept_pct"] <= 100 and w["effect"]["text"]
    if basis == "typical":
        # the rainy share shown is the one the safe limit uses (not the smeared mean of many years)
        assert s["rain_share_open_hours"] == pytest.approx(w["effect"]["capacity_rain_factor_pct"] / 100, abs=0.05)
        t = w["typical_range"]
        assert t["rain_mm_p10"] <= t["rain_mm_p50"] <= t["rain_mm_p90"] and 0 <= t["chance_wet_day"] <= 1
    else:
        assert "typical_range" not in w


def test_effect_matches_the_safe_limit(client):
    c, ctx = client
    day = ctx.today + timedelta(days=2)
    w = c.get(f"/weather/{day.isoformat()}").json()
    cap = c.get(f"/capacity/{day.isoformat()}").json()
    assert w["effect"]["capacity_rain_factor_pct"] == round(100 * cap["rain_share_open_hours"])


def test_outside_the_data(client):
    c, ctx = client
    assert c.get(f"/weather/{(ctx.today + timedelta(days=4000)).isoformat()}").status_code == 400
