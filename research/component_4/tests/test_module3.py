"""Contract with Module 3 (FR4): the feed always matches the published JSON Schema, and means what it says."""
import json

import pytest

jsonschema = pytest.importorskip("jsonschema")

from src.config import load_config  # noqa: E402
from src.live.refresh import PUBLISHED  # noqa: E402
from src.serve.module3 import SAMPLE_PATH, SCHEMA_ID, module3_feed, schema  # noqa: E402

pytestmark = pytest.mark.skipif(not (PUBLISHED / "forecast_tomorrow.json").exists(),
                                reason="run python -m src.live.refresh first")


@pytest.fixture(scope="module")
def feed():
    return module3_feed(json.loads((PUBLISHED / "forecast_tomorrow.json").read_text(encoding="utf-8")), load_config())


def test_feed_matches_the_schema(feed):
    jsonschema.validate(feed, schema())
    assert feed["schema"] == SCHEMA_ID == schema()["$id"]


def test_feed_means_what_it_says(feed):
    busy = feed["busy_utilisation"]
    for s in feed["segments"]:
        for h in feed["open_hours"]:
            over = s["people_hourly"][h] / s["capacity_at_once"] >= busy
            assert (h in s["avoid_hours"]) == over                  # avoid exactly the busy hours
    by_id = {s["segment_id"]: s for s in feed["segments"]}
    for t in feed["trails"]:
        own = [s for s in feed["segments"] if s["trail"] == t["trail_id"]]
        assert by_id[t["limiting_segment_id"]]["trail"] == t["trail_id"]
        assert t["safe_visitors_per_day"] == min(s["safe_visits_per_day"] for s in own)   # most limiting segment
    assert feed["safe_visitors_per_day"] == sum(t["safe_visitors_per_day"] for t in feed["trails"])
    assert "SYNTHETIC" in feed["disclaimer"].upper()                 # FR5 travels with the data


def test_a_renamed_field_breaks_the_contract(feed):
    bad = json.loads(json.dumps(feed))
    bad["segments"][0]["people"] = bad["segments"][0].pop("people_hourly")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema())


def test_api_serves_the_feed():
    from fastapi.testclient import TestClient
    from src.api import app as api
    r = TestClient(api.app).get("/module3/feed")
    assert r.status_code == 200
    jsonschema.validate(r.json(), schema())


def test_sample_file_for_module3_is_valid():
    if not SAMPLE_PATH.exists():
        pytest.skip("python -m src.serve.module3 writes the sample")
    jsonschema.validate(json.loads(SAMPLE_PATH.read_text(encoding="utf-8")), schema())
