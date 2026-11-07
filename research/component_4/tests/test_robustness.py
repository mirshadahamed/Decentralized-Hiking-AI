"""G5: each robustness world changes exactly the one assumption it names (src.eval.robustness)."""
import copy

from src.config import load_config
from src.eval.robustness import worlds


def test_each_world_changes_only_its_assumption():
    p0 = load_config(park="horton_plains")["simulator"]
    ws = worlds(p0)
    assert "summit_-30" not in ws                                   # no summit steps at Horton Plains
    changed = {}
    for name, (_, change) in ws.items():
        p = copy.deepcopy(p0)
        change(p)
        changed[name] = {k for k in p0 if p[k] != p0[k]}
    assert changed["assumed"] == set()
    assert changed["demand_+30"] == {"base_daily_visitors"}
    assert changed["arrive_-1h"] == {"arrival_early_mean_h", "arrival_late_range_h"}
    assert changed["routes_flat"] == {"route_share"}
    assert changed["crowd_slow"] == {"crowd_rho0_per_m"}
    p = copy.deepcopy(p0)
    ws["routes_flat"][1](p)
    assert abs(sum(p["route_share"].values()) - 1) < 1e-9


def test_adams_peak_gets_summit_worlds():
    p0 = load_config(park="adams_peak")["simulator"]
    ws = worlds(p0)
    p = copy.deepcopy(p0)
    ws["summit_-30"][1](p)
    assert p["bottleneck"]["flow_per_min"] == 0.7 * p0["bottleneck"]["flow_per_min"]
    assert p0["bottleneck"]["flow_per_min"] == load_config(park="adams_peak")["simulator"]["bottleneck"]["flow_per_min"]
