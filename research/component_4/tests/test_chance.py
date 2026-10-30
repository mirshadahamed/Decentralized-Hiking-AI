"""RQ15: the chance-constrained cap keeps P(real > C) at eps under the fitted spread; bigger buffer when it is wider."""
import numpy as np
from scipy import stats

from src.control import chance


def test_fit_recovers_bias_and_spread():
    rng = np.random.default_rng(0)
    pred = rng.uniform(20, 200, 20000)
    real = 1.1 * pred + rng.normal(0, np.sqrt(2.0 * pred + (0.1 * pred) ** 2))
    f = chance.fit(pred, real)
    assert abs(f["bias"] - 1.1) < 0.01 and abs(f["sigma"] - 0.1) < 0.02 and 1.0 < f["disp"] < 3.0


def test_safe_cap_meets_eps_and_shrinks_with_spread():
    C = np.array([50.0, 400.0, np.inf])
    m = chance.safe_cap(C, 0.05, 1.0, 2.0, 0.1)
    assert np.isinf(m[2]) and (m[:2] < C[:2]).all()
    sd = np.sqrt(2.0 * m[:2] + (0.1 * m[:2]) ** 2)
    assert np.allclose(stats.norm.sf((C[:2] - m[:2]) / sd), 0.05, atol=1e-6)     # P(over) = eps exactly
    assert m[0] / C[0] < m[1] / C[1]                                                # small sections: larger buffer
    wider = chance.safe_cap(C, 0.05, 1.0, 2.0, 0.2)
    assert (wider[:2] < m[:2]).all() and (chance.safe_cap(C, 0.2, 1.0, 2.0, 0.1)[:2] > m[:2]).all()
    assert chance.kind(0.5) == "wet" and chance.kind(0.0) == "dry"


def test_rain_replan_uses_the_rain_so_far_and_the_nowcast():
    from datetime import date

    from src.control.mpc import blend_rain_share
    from src.live.nowcast import rain_today
    cap = {"open_from_h": 6, "open_hours": 10, "rain_mm": 0.5}
    rain = np.zeros(24)
    rain[7:10] = 2.0                                          # 07-10 wet, planned dry
    assert blend_rain_share(0.0, rain, 6 * 60, cap) == 0.1   # 06:00: known 06-07 dry, 07 wet (nowcast 2 h)
    assert blend_rain_share(0.0, rain, 10 * 60, cap) == 0.3
    assert blend_rain_share(0.5, np.zeros(24), 6 * 60, cap) == 0.5   # drier than planned: keep the plan
    js = {"hourly": {"time": [f"2026-11-02T{h:02d}:00" for h in range(24)], "precipitation": list(rain)}}
    cfg = {"area": {"weather_point": [7.0, 80.0]}}
    got = rain_today(cfg, date(2026, 11, 2), fetch=lambda p: js)
    assert got[8] == 2.0 and got.sum() == 6.0
    assert rain_today(cfg, date(2026, 11, 3), fetch=lambda p: 1 / 0) is None   # error -> keep the plan


def test_gate_decision_in_one_line():
    from src.control.mpc import why_line
    names = {"main": "World's End loop"}
    assert why_line(1.2, 0.5, 0.2, {"main": 0.3}, names) == (
        "Fewer places now: rain (50 % of the open hours); 20 % more people than expected so far; "
        "World's End loop 30 % less room.")
    assert why_line(0.8, 0.0, 0.2, {}, names).startswith("More places now: drier than usual")
    assert why_line(1.0, 0.2, 0.2, {}, names).startswith("As planned")
