"""§6.2.9 without push: the day's notices for visitors (closures, conditions, heavy rain)."""
from datetime import date, datetime

import numpy as np
import pandas as pd
import pytest

from src.config import PROCESSED, load_config
from src.control import booking
from src.serve.notices import HEAVY_MM, notices

CFG = load_config(park="horton_plains")
DAY = date(2026, 11, 2)
needs_data = pytest.mark.skipif(not (PROCESSED / "segments.geojson").exists(), reason="run src.data.build_dataset first")


def _weather(mm_at_14: float, source: str = "forecast"):
    idx = pd.date_range("2026-11-02", periods=24, freq="h")
    w = pd.DataFrame({"precipitation": np.where(idx.hour == 14, mm_at_14, 0.0)}, index=idx)
    return w, pd.Series(source, index=idx)


@needs_data
def test_conditions_closures_and_forecast_rain(tmp_path, monkeypatch):
    monkeypatch.setattr(booking, "DB", tmp_path / "bookings.sqlite")
    now = datetime(2026, 11, 1, 18, 0)
    assert notices(CFG, DAY, now, *_weather(1.0)) == []
    booking.set_condition("2026-11-02", "2026-11-02", "kirigalpotta", "closed", "landslide", "officer1")
    booking.close("2026-11-02", "main", "09:00", "10:00", "rescue", "officer1")
    n = notices(CFG, DAY, now, *_weather(HEAVY_MM + 2))
    assert [x["kind"] for x in n] == ["condition", "closure", "rain"]
    assert n[0]["level"] == "danger" and n[0]["text"] == "Kirigalpotta is closed (landslide)."
    assert "no entry 09:00-10:00 (rescue)" in n[1]["text"] and "14:00" in n[2]["text"]
    assert [x["id"] for x in n] == [x["id"] for x in notices(CFG, DAY, now, *_weather(HEAVY_MM + 2))]   # stable
    assert [x["kind"] for x in notices(CFG, DAY, now, *_weather(20, "typical"))] == ["condition", "closure"]


def test_nowcast_for_today_is_a_danger(tmp_path, monkeypatch):
    monkeypatch.setattr(booking, "DB", tmp_path / "bookings.sqlite")
    rain = np.zeros(24)
    rain[11] = 12.0
    n = notices(CFG, DAY, datetime(2026, 11, 2, 10, 0), nowcast=rain)
    assert len(n) == 1 and n[0]["level"] == "danger" and "11:00" in n[0]["text"]
    assert notices(CFG, DAY, datetime(2026, 11, 2, 13, 0), nowcast=rain) == []     # already past
