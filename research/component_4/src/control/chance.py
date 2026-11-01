"""Plan §6.1.1: a chance constraint at the gate instead of a fixed safety margin.

The controller (mpc.py) predicts each section's occupancy as inside + K·caps (the linear response table). The real
occupancy differs: walking speeds and stays vary, groups move together, and crowds slow walkers (not in K). On the
training year we compare the prediction with the simulated real occupancy and fit, per weather kind (dry / wet):

    real ≈ bias · pred,     Var(real | pred) ≈ disp · pred + (sigma · pred)²

The plan then keeps P(real > C) ≤ eps under a normal approximation, i.e. per section

    bias · m + z · sqrt(disp · m + sigma² · m²) ≤ C,     z = Φ⁻¹(1 − eps)

so the cap on the prediction is the smaller root m*(C) of a quadratic. Small sections and wet days (more spread)
get a larger buffer; large dry sections less than the fixed 10 %. RQ15 (evaluate_chance.py) compares the two.
"""
import json

import numpy as np
from scipy import stats

from src.config import PROCESSED

CALIBRATION = PROCESSED / "chance_calibration.json"
WET = 0.3                     # rain share of the open hours from which a day counts as wet


def kind(rain_share: float) -> str:
    return "wet" if rain_share >= WET else "dry"


def fit(pred: np.ndarray, real: np.ndarray) -> dict:
    """bias by least squares through the origin; disp and sigma² by non-negative least squares on the squared
    residuals (method of moments)."""
    from scipy.optimize import nnls
    pred, real = np.asarray(pred, float), np.asarray(real, float)
    bias = float((pred * real).sum() / max((pred * pred).sum(), 1e-9))
    r2 = (real - bias * pred) ** 2
    (disp, s2), _ = nnls(np.c_[pred, pred ** 2], r2)
    return {"bias": round(bias, 4), "disp": round(float(disp), 4), "sigma": round(float(np.sqrt(s2)), 4),
            "n": int(len(pred))}


def safe_cap(C: np.ndarray, eps: float, bias: float, disp: float, sigma: float) -> np.ndarray:
    """Largest predicted occupancy m with P(real > C) ≤ eps (normal approximation); inf stays inf."""
    C = np.asarray(C, float)
    z = float(stats.norm.ppf(1 - eps))
    a = bias ** 2 - (z * sigma) ** 2
    out = np.full_like(C, np.inf)
    fin = np.isfinite(C)
    c = C[fin]
    b = 2 * bias * c + z * z * disp
    if a <= 1e-9:                                 # spread too large for any load: fall back to a tight cap
        out[fin] = c ** 2 / b
        return out
    out[fin] = (b - np.sqrt(np.maximum(b * b - 4 * a * c * c, 0.0))) / (2 * a)
    return out


def load() -> dict | None:
    return json.loads(CALIBRATION.read_text(encoding="utf-8")) if CALIBRATION.exists() else None


def live_kwargs(cfg) -> dict:
    """MPCController arguments for live use: the chance constraint when control.chance_eps is set and a calibration
    exists (python -m src.control.evaluate_chance writes it), otherwise {} (the fixed safety margin)."""
    eps = cfg["control"].get("chance_eps")
    cal = load() if eps else None
    return {"chance": cal | {"eps": float(eps)}} if cal else {}
