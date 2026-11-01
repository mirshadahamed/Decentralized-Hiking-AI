"""NFR4: calibrated ranges (src.eval.conformal) and the cautious quota in the published forecast."""
import numpy as np
import pytest

from src.config import PROCESSED


def test_ranges_cover_new_data_at_the_level_and_grow_with_the_forecast():
    from src.eval.conformal import bounds, calibrate
    rng = np.random.default_rng(0)

    def draw(n):
        pred = rng.gamma(1.0, 20.0, n)
        return pred, np.clip(pred * rng.lognormal(0, 0.4, n), 0, None)      # errors grow with the forecast
    table = calibrate(*draw(50_000))
    pred, y = draw(50_000)
    lo, hi = bounds(pred, table, 0.9)
    assert abs(((y >= lo) & (y <= hi)).mean() - 0.9) < 0.02
    assert (lo >= 0).all() and (hi - lo)[pred > 50].mean() > 3 * (hi - lo)[pred < 5].mean()


def test_rare_large_forecasts_borrow_a_scaled_range():
    from src.eval.conformal import MIN_N, calibrate
    pred = np.r_[np.full(MIN_N, 120.0), np.full(5, 300.0)]
    y = pred + np.r_[np.linspace(-20, 20, MIN_N), np.zeros(5)]
    t = calibrate(pred, y, levels=(0.9,))
    k100, k200 = t["edges"].index(100.0), t["edges"].index(200.0)
    assert np.allclose(t["0.9"][k200], np.array(t["0.9"][k100]) * 2)


@pytest.mark.skipif(not (PROCESSED / "dataset.npz").exists(), reason="run src.data.build_dataset first")
def test_published_forecast_has_ranges_and_a_cautious_quota():
    import geopandas as gpd

    from src.config import load_config
    from src.eval.conformal import calibrate
    from src.eval.data import TrailData
    from src.serve.predict import build_forecast, with_range
    cfg = load_config()
    data = TrailData(cfg)
    seg = gpd.read_file(PROCESSED / "segments.geojson")
    out = build_forecast(data, cfg, seg, "2025-05-12")                       # historical average, no range
    assert "range" not in out
    rng = np.random.default_rng(1)
    p = rng.gamma(1.0, 20.0, 20_000)
    table = calibrate(p, p * rng.lognormal(0, 0.3, len(p)))
    fc = np.array([s["forecast_hourly"] for s in out["segments"]]).T
    out = with_range(out, seg, fc, np.zeros(24), {t: v["expected_visitors"] for t, v in out["trails"].items()},
                     cfg, table)
    assert out["range"]["cautious_daily_quota"] <= out["recommended_daily_quota"]   # a bigger crowd -> a lower limit
    for s in out["segments"]:
        assert s["peak_range"][0] <= s["peak_occupancy"] <= s["peak_range"][1]
    for t in out["trails"].values():
        assert t["cautious_daily_quota"] <= t["recommended_daily_quota"]
