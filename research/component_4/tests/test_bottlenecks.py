import numpy as np

from src.eval.bottlenecks import bootstrap_diff, counts, scores


def _toy():
    D, H, N = 4, 24, 3
    cap = np.full(N, 10.0)
    y = np.zeros((D, H, N))
    y[:, 9, 0] = 20                                         # one real event a day: 09:00 on segment 0
    open_ = np.zeros((D, H))
    open_[:, 6:16] = 1
    return y, open_, cap


def test_perfect_forecast():
    y, open_, cap = _toy()
    s = scores(counts(y, y, open_, cap, np.arange(3)))
    assert s["events"] == 4 and s["F1"] > 0.999 and s["segment_day_hit_rate"] > 0.999
    assert s["warning_hours_mean"] == 9


def test_one_hour_late_counts_as_segment_day_hit_but_not_hour_hit():
    y, open_, cap = _toy()
    late = np.roll(y, 1, axis=1)
    s = scores(counts(late, y, open_, cap, np.arange(3)))
    assert s["F1"] < 1e-6 and s["segment_day_hit_rate"] > 0.999


def test_closed_hours_and_other_nodes_ignored():
    y, open_, cap = _toy()
    p = y.copy()
    p[:, 2, 1] = 50                                         # night: park closed
    s = scores(counts(p, y, open_, cap, np.arange(3)))
    assert s["precision"] > 0.999
    assert scores(counts(y, y, open_, cap, np.array([1, 2])))["events"] == 0


def test_bootstrap_sign():
    y, open_, cap = _toy()
    good, bad = counts(y, y, open_, cap, np.arange(3)), counts(np.zeros_like(y), y, open_, cap, np.arange(3))
    r = bootstrap_diff(good, bad, n=200)
    assert r["F1_diff"] > 0.99 and r["ci95"][0] > 0.99
