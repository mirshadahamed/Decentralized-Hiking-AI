"""RMSE, MAE and the paired significance tests (D5)."""
import numpy as np
from scipy import stats


def masked_errors(pred, y, open_mask, nodes):
    """pred, y: [D, H, N]; open_mask: [D, H]. Returns abs and squared errors on open hours and chosen nodes."""
    e = (pred - y)[:, :, nodes]
    m = np.broadcast_to(open_mask[:, :, None], e.shape)
    return e, m


def summary(pred, y, open_mask, nodes, peak_mask=None, poi_nodes=None) -> dict:
    """Overall MAE/RMSE on open hours, plus MAE in the morning peak and on the POI (bottleneck) segments."""
    e, m = masked_errors(pred, y, open_mask, nodes)
    ev = e[m]
    out = {"MAE": float(np.abs(ev).mean()), "RMSE": float(np.sqrt((ev ** 2).mean()))}
    if peak_mask is not None:
        pm = np.broadcast_to(peak_mask[:, :, None], e.shape) & m
        out["MAE_peak"] = float(np.abs(e[pm]).mean())
    if poi_nodes is not None:
        sel = np.isin(nodes, poi_nodes)
        if sel.any():
            ep, mp = e[:, :, sel], m[:, :, sel]
            out["MAE_poi"] = float(np.abs(ep[mp]).mean())
            out["RMSE_poi"] = float(np.sqrt((ep[mp] ** 2).mean()))
    return out


def per_day_mae(pred, y, open_mask, nodes) -> np.ndarray:
    """One error per forecast day: the pairing unit for the t-test (hourly errors are autocorrelated)."""
    e, m = masked_errors(pred, y, open_mask, nodes)
    return np.array([np.abs(e[d][m[d]]).mean() for d in range(len(e))])


def paired_tests(errors: dict, proposed: str) -> list:
    """Paired t-test (and Wilcoxon) of `proposed` vs every other model, Holm-corrected."""
    rows = []
    for name, err in errors.items():
        if name == proposed:
            continue
        diff = errors[proposed] - err                       # negative = proposed is better
        t, p = stats.ttest_rel(errors[proposed], err)
        w_p = stats.wilcoxon(errors[proposed], err).pvalue
        rows.append({"baseline": name, "n_days": len(diff), "mean_diff_MAE": float(diff.mean()),
                     "t": float(t), "p": float(p), "wilcoxon_p": float(w_p),
                     "cohens_dz": float(diff.mean() / (diff.std(ddof=1) + 1e-12))})
    # Holm-Bonferroni across the comparisons
    order = np.argsort([r["p"] for r in rows])
    k, running = len(rows), 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (k - rank) * rows[i]["p"]))
        rows[i]["p_holm"] = running
        rows[i]["significant_0.05"] = bool(running < 0.05 and rows[i]["mean_diff_MAE"] < 0)
    return rows
