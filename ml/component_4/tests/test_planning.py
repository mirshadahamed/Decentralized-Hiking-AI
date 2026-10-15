"""Planning model: no look-ahead, sensible ranges, suggestions respect capacity."""
import numpy as np
import pandas as pd
import pytest

from src.config import PROCESSED, load_config

pytestmark = pytest.mark.skipif(not (PROCESSED / "dataset.npz").exists(),
                                reason="run python -m src.data.build_dataset first")


@pytest.fixture(scope="module")
def planner():
    from src.serve.outlook import build_planner
    return build_planner(load_config())


def test_outlook_shape_and_order(planner):
    ol = planner.m.outlook("2025-03-01")
    assert len(ol) == 90 and ol.lead.min() == 1 and ol.lead.max() == 90
    assert (ol.p10 <= ol.p50).all() and (ol.p50 <= ol.p90).all()
    assert ol.crowd_level.between(1, 5).all()
    trails = planner.m.daily.trails
    assert np.allclose(sum(ol[f"{t}_p50"] for t in trails), ol.p50)


def test_no_information_from_after_the_issue_date(planner):
    """Changing visitor numbers on or after the issue date must not change the outlook."""
    tab = planner.m.table
    issue = planner.m.day_index("2025-03-01")
    before = planner.m.outlook("2025-03-01").p50.copy()
    saved = tab.df.visitors.copy(), tab.df.level.copy()
    try:
        tab.df.loc[tab.df.index[issue:], "visitors"] *= 10
        tab.df["level"] = tab.df.visitors.shift(1).rolling(28, min_periods=28).mean()
        after = planner.m.outlook("2025-03-01").p50
    finally:
        tab.df["visitors"], tab.df["level"] = saved
    pd.testing.assert_series_equal(before, after)


def test_models_fitted_on_training_period_only(planner):
    assert planner.m.table.train_days == planner.m.data.train_end // 24
    assert planner.m.profiles.prof.shape[2:] == (24, planner.m.data.N)


def test_suggestions_never_exceed_alternative_capacity(planner):
    plan = planner.day("2025-03-01", "2025-05-12")         # Vesak Poya: busy
    kinds = {s["kind"] for s in plan["suggestions"]}
    assert "trail" in kinds and "date" in kinds
    for s in plan["suggestions"]:
        if s["kind"] == "trail":
            assert plan["capacity"]["trails"][s["trail"]]["headroom"] > 0


def test_quiet_day_gets_no_trail_swap(planner):
    plan = planner.day("2025-05-20", "2025-06-18")         # ordinary June Wednesday
    assert plan["crowd_level"] <= 2
    assert all(s["kind"] != "trail" for s in plan["suggestions"])
