"""Field validation (RQ7): the comparison works on a counting sheet and the agreement criteria behave."""
import geopandas as gpd
import numpy as np
import pandas as pd
import pytest

from src.config import PROCESSED, load_config

pytestmark = pytest.mark.skipif(not (PROCESSED / "dataset.npz").exists(), reason="run src.data.build_dataset first")


@pytest.fixture(scope="module")
def setup():
    from src.eval.data import TrailData
    cfg = load_config()
    data = TrailData(cfg)
    seg = gpd.read_file(PROCESSED / "segments.geojson")
    seg["poi"] = seg["poi"].fillna("")
    return cfg, data, seg


def sheet(data, seg, day, noise, rng):
    s = int(seg.index[seg.poi == "worlds_end"][0])
    t0 = int(np.searchsorted(data.times, pd.Timestamp(day)))
    rows = [{"date": day, "time": f"{h:02d}:{m:02d}", "place": "worlds_end",
             "count": max(0, round(data.y_true[t0 + h, s] * (1 + noise * rng.standard_normal()))), "counter": "T"}
            for h in range(7, 14) for m in (0, 30)]
    return pd.DataFrame(rows)


def test_counts_like_the_target_pass_all_criteria(setup, tmp_path):
    from src.eval.field_validation import compare, read_counts
    cfg, data, seg = setup
    p = tmp_path / "count.csv"
    sheet(data, seg, "2025-04-13", 0.05, np.random.default_rng(1)).to_csv(p, index=False)
    pairs, rep = compare(read_counts([p]), cfg, data, seg)          # fallback forecast (no model needed)
    assert len(pairs) == 14 and rep["places"] == ["worlds_end"]
    sim = rep["simulated"]
    assert sim["A1_pass"] and sim["A2_pass"] and sim["A3_pass"]
    assert set(rep["forecast"]) >= {"MAE_people", "A1_pass", "A2_spearman", "A3_peak_hour_hits"}


def test_unknown_place_is_explained(setup, tmp_path):
    from src.eval.field_validation import compare, read_counts
    cfg, data, seg = setup
    p = tmp_path / "bad.csv"
    pd.DataFrame([{"date": "2025-04-13", "time": "08:00", "place": "nowhere", "count": 3}]).to_csv(p, index=False)
    with pytest.raises(ValueError, match="unknown place"):
        compare(read_counts([p]), cfg, data, seg)
