import numpy as np

from src.eval.uncertainty import calibrate, f1, prob_over


def test_calibration_is_monotone_and_matches_rates():
    rng = np.random.default_rng(0)
    u = rng.uniform(0, 2, 20000)
    truth = rng.random(20000) < np.clip(u - 0.5, 0, 1)            # really over more often when forecast fuller
    t = calibrate(u, truth)
    p = np.array(t["p_over"])
    assert np.all(np.diff(p) >= 0)
    assert prob_over(np.array([0.1]), t)[0] < 0.05 and prob_over(np.array([1.9]), t)[0] > 0.9
    assert abs(prob_over(np.array([1.0]), t)[0] - 0.55) < 0.1


def test_f1():
    a = np.array([1, 1, 0, 0], bool)
    t = np.array([1, 0, 1, 0], bool)
    assert f1(a, t) == (0.5, 0.5, 0.5)
