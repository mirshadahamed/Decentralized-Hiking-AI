"""P4: stage advice on an open-access trail - levels, where and when it is busiest, a quieter neighbour."""
import numpy as np
import pandas as pd

from src.config import load_config
from src.serve.stages import stage_outlook


def test_stage_levels_busiest_place_and_neighbour():
    cfg = load_config()
    cfg["area"]["trail_names"] = {"s01": "Stage 1", "s02": "Stage 2", "s03": "Stage 3"}
    seg = pd.DataFrame({"seg_id": range(6), "trail": ["s01"] * 2 + ["s02"] * 2 + ["s03"] * 2, "length_m": 6000.0})
    c = cfg["capacity"]
    cap = 6000 / (c["group_gap_m"] + c["group_size"] * c["space_per_person_m"]) * c["group_size"]
    hourly = np.zeros((24, 6))
    hourly[10, 3] = 1.5 * cap              # stage 2, second section (km 6), 10:00: over capacity
    hourly[9:12, 2] = 0.6 * cap
    hourly[8, 0] = 0.1 * cap               # stage 1 quiet
    out = stage_outlook(cfg, seg, hourly, "2027-01-10")
    s = {x["stage"]: x for x in out["stages"]}
    assert s["s01"]["level"] == "quiet" and s["s03"]["level"] == "quiet"
    assert s["s02"]["level"] == "crowded" and s["s02"]["busiest_hour"] == "10:00" and s["s02"]["busiest_km"] == 6.0
    assert s["s02"]["quieter_neighbour"] == "s01" and s["s02"]["spread_window"] == ["06:00", "11:00"]
    assert "spread their starts" in s["s02"]["advice"] and s["s01"]["spread_window"] is None
    assert s["s02"]["length_km"] == 12.0 and len(s["s02"]["hourly_walkers"]) == 24


def test_viewpoint_section_fills_sooner_and_stage_weather_adds_rain_advice():
    from src.live.stage_weather import summarise
    cfg = load_config()
    cfg["area"]["trail_names"] = {"s01": "Stage 1"}
    cfg["area"]["poi_roles"] = {"viewpoint": ["liptons_seat"]}
    cfg["control"]["hotspot_at_once"] = 30
    seg = pd.DataFrame({"seg_id": [0, 1], "trail": ["s01", "s01"], "length_m": 6000.0, "poi": ["", "liptons_seat"]})
    hourly = np.zeros((24, 2))
    hourly[9, 1] = 36                                     # 36 people at the viewpoint: over its 30
    times = [f"2027-01-10T{h:02d}:00" for h in range(24)]
    rain = [0.0] * 13 + [2.0] * 4 + [0.0] * 7             # 13:00-16:00 rain
    w = summarise(times, rain, [18.0] * 24, cfg)["2027-01-10"]
    assert w == {"rain_mm": 8.0, "rain_hours": 4, "temp_max_c": 18.0}
    s = stage_outlook(cfg, seg, hourly, "2027-01-10", {"s01": w})["stages"][0]
    assert s["level"] == "crowded" and s["fullness"] == 1.2 and "Rain expected" in s["advice"]
