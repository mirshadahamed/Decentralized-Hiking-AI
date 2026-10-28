"""N2: the rangers' counts correct the saved forecast; the backtest uses earlier days only; counts export to a sheet."""
import numpy as np
import pytest

from src.config import PROCESSED, load_config

pytestmark = pytest.mark.skipif(not (PROCESSED / "segments.geojson").exists(), reason="run src.data.build_dataset first")


@pytest.fixture()
def setup(tmp_path):
    from src.control import booking
    from src.control.slots import build_control
    from src.serve.field_counts import add_count
    db = tmp_path / "b.sqlite"
    seg = build_control().seg.seg_id.astype(int).tolist()
    for d in ("2026-12-01", "2026-12-02", "2026-12-03"):
        booking.save_forecast(d, np.full((24, len(seg)), 10.0), "test", db)
    s = seg[0]
    for d in ("2026-12-01", "2026-12-02"):
        add_count(d, s, 9 * 60, 20, "r1", db=db)                  # the forecast says 10, the ranger counts 20
    return load_config(), db, seg, s


def test_factors_shrink_towards_the_park_factor(setup):
    from src.live.recalibrate import PRIOR, factors
    cfg, db, seg, s = setup
    f = factors(cfg, "2026-12-03", db=db)
    park = (40 + PRIOR) / (20 + PRIOR)
    assert f["counts"] == 2 and f["park_factor"] == pytest.approx(park, abs=1e-3)
    assert f["sections"][s]["factor"] == pytest.approx((40 + PRIOR * park) / (20 + PRIOR), abs=1e-3)
    assert factors(cfg, "2026-12-01", db=db)["counts"] == 0       # nothing counted before the first day


def test_corrected_forecast_is_used_and_raw_kept(setup):
    from src.control import booking
    from src.live.recalibrate import correct_saved
    cfg, db, seg, s = setup
    fac = correct_saved(cfg, "2026-12-03", db)
    j = seg.index(s)
    fc, basis = booking.day_forecast("2026-12-03", db)
    raw, _ = booking.day_forecast("2026-12-03", db, raw=True)
    assert raw[9, j] == 10.0 and fc[9, j] == pytest.approx(10 * fac["sections"][s]["factor"], abs=0.01)
    assert fc[9, seg.index(seg[1])] == pytest.approx(10 * fac["park_factor"], abs=0.01)
    assert "counts" in basis


def test_backtest_improves_on_a_biased_forecast_without_leakage(setup):
    from src.live.recalibrate import backtest
    cfg, db, seg, s = setup
    b = backtest(cfg, "2026-12-01", "2026-12-03", db=db)
    assert [d["day"] for d in b["days"]] == ["2026-12-02"]       # day 1 has no earlier counts to learn from
    assert b["mae_raw"] == 10 and b["mae_corrected"] < b["mae_raw"]


def test_counts_export_to_a_field_validation_sheet(setup, tmp_path):
    from src.eval.field_validation import read_counts
    from src.live.recalibrate import export_sheet
    cfg, db, seg, s = setup
    p = tmp_path / "sheet.csv"
    assert export_sheet(cfg, "2026-12-01", "2026-12-31", p, db) == 2
    df = read_counts([p])
    assert df["count"].tolist() == [20, 20] and df["hour"].tolist() == [9, 9]
