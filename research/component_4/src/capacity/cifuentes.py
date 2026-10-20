"""Cifuentes (1992) carrying-capacity cascade per trail, driven by the forecast (D6 / FR3).

Per segment s (visits per day):
    PCC_s = (L_s / sp) * (open_minutes / visit_minutes_s)                    physical capacity
    RCC_s = PCC_s * (1-FCsoc)(1-FCero)(1-FCacc)(1-FCpre) * (1-FCcrowd_s)       real capacity
    ECC_s = RCC_s * MC                                                         effective capacity
Quota of a trail = min over its segments of ECC_s (the most limiting segment sets it).
Park quota = sum of the trail quotas (each visitor hikes one trail).

Trail-level factors, as in Cifuentes (limiting length or hours / total length or hours), computed per trail:
    FCsoc  social: trail length that must stay empty between groups
    FCero  erodibility: length-weighted share of waterlogging-prone ground (TWI)
    FCacc  accessibility: length-weighted share of 10-20 % (x1) and > 20 % (x1.5) grades
    FCpre  precipitation: share of open hours with rain in the FORECAST          -> changes daily
Segment-level factor added by this project (same form as FCpre):
    FCcrowd_s = share of open hours in which the FORECAST occupancy of segment s exceeds the
                number of people the segment holds at the social spacing      -> changes daily
Trail-level factors added for the live service (both 0 unless given, so research results are unchanged):
    FCwet     wet ground: waterlogging-prone share of the trail x how wet the ground is from the last days' rain
              (wetness 0..1 = rain of the last `wet_ground.days` / `saturation_mm`)      -> changes daily
    FCcond    trail condition set by an officer (good / muddy / partly closed / closed)  -> changes when reported
"""
import numpy as np
import pandas as pd

FACTOR_LABELS = {"social": "space between groups", "erodibility": "erosion-prone ground",
                 "accessibility": "steep sections", "precipitation": "rain during opening hours",
                 "wet_ground": "ground still wet from earlier rain", "condition": "trail condition"}


def trail_factors(seg: pd.DataFrame, rain_share: float, c: dict, wetness: float = 0.0,
                  condition: float = 0.0) -> dict:
    sp, g, gap = c["space_per_person_m"], c["group_size"], c["group_gap_m"]
    w = seg.length_m.values / seg.length_m.sum()
    wet_prone = float(np.sum(w * seg.frac_wet.values))
    return {
        "social": 1 - g * sp / (gap + g * sp),
        "erodibility": float(min(0.9, wet_prone * 1.5)),
        "accessibility": float(min(0.9, np.sum(w * (seg.frac_grade_med.values + 1.5 * seg.frac_grade_high.values)))),
        "precipitation": rain_share,
        "wet_ground": float(min(0.9, wet_prone * 1.5 * min(1.0, max(0.0, wetness)))),
        "condition": float(min(1.0, max(0.0, condition))),
    }


def wetness_from_rain(rain_mm: float, c: dict) -> float:
    """0 = dry ground ... 1 = fully wet, from the rain of the last few days."""
    return float(min(1.0, max(0.0, rain_mm) / c.get("wet_ground", {}).get("saturation_mm", 60)))


def capacity(seg: pd.DataFrame, forecast: np.ndarray, rain_mm_hourly: np.ndarray | None,
             expected_by_trail: dict, c: dict, sim: dict, trail_names: dict | None = None,
             rain_share: float | None = None, wetness: float = 0.0, conditions: dict | None = None) -> dict:
    """seg: segment table (with a `trail` column); forecast: [24, N] persons; rain_mm_hourly: [24] forecast rain,
    or rain_share directly (e.g. from climatology for long-range planning);
    expected_by_trail: expected visitors per trail; sim: simulator parameters (walking speed, dwell);
    wetness: 0..1 ground wetness from earlier rain; conditions: {trail: share removed by its reported condition}."""
    conditions = conditions or {}
    sp, L = c["space_per_person_m"], seg.length_m.values
    open_h = (c.get("open_from_h", 6) + np.arange(c["open_hours"])) % 24
    if rain_share is None:
        rain_share = float((rain_mm_hourly[open_h] >= c["rain_mm"]).mean())

    fc_open = forecast[open_h]                                           # [open hours, N]
    at_once = L / (c["group_gap_m"] + c["group_size"] * sp) * c["group_size"]   # people at social spacing
    fc_crowd = (fc_open > at_once).mean(0)
    dwell = np.array([sim["dwell_minutes"].get(p, [0])[0] if p else 0 for p in seg.poi])
    visit_min = seg.tobler_fwd_min.values / sim["leisure_speed_factor"] + dwell
    pcc = (L / sp) * (c["open_hours"] * 60 / visit_min)

    keep = np.ones(len(seg))
    trails = {}
    for t in seg.trail.unique():
        m = (seg.trail == t).values
        fc = trail_factors(seg[m], rain_share, c, wetness, conditions.get(t, 0.0))
        keep[m] = np.prod([1 - v for v in fc.values()])
        trails[t] = {"factors": fc}
    rcc_classic = pcc * keep
    rcc = rcc_classic * (1 - fc_crowd)
    ecc, ecc_classic = rcc * c["management_capacity"], rcc_classic * c["management_capacity"]

    peak, peak_hour = fc_open.max(0), open_h[fc_open.argmax(0)]
    util = peak / at_once
    status = np.where(fc_crowd > 0, "bottleneck", np.where(util >= c["busy_utilisation"], "busy", "ok"))

    for t, info in trails.items():
        idx = np.where((seg.trail == t).values)[0]
        lim = idx[np.argmin(ecc[idx])]
        exp = float(expected_by_trail.get(t, 0.0))
        quota = float(ecc[lim])
        info.update({
            "name": (trail_names or {}).get(t, t),
            "expected_visitors": round(exp), "recommended_daily_quota": round(quota),
            "classic_cifuentes_quota": round(float(ecc_classic[idx].min())),
            "limiting_segment": int(seg.seg_id.iloc[lim]),
            "headroom": round(quota - exp),
            "bottleneck_segments": int((status[idx] == "bottleneck").sum()),
            "peak_occupancy": round(float(peak[idx].max()), 1),
            "factors": {k: round(float(v), 3) for k, v in info["factors"].items()},
        })

    segments = [{
        "seg_id": int(seg.seg_id.iloc[i]), "trail": seg.trail.iloc[i], "poi": seg.poi.iloc[i] or None,
        "length_m": float(L[i]),
        "forecast_hourly": [round(float(v), 1) for v in forecast[:, i]],
        "peak_occupancy": round(float(peak[i]), 1), "peak_hour": int(peak_hour[i]),
        "capacity_at_once": round(float(at_once[i]), 1), "utilisation": round(float(util[i]), 2),
        "crowded_hours_share": round(float(fc_crowd[i]), 3), "status": str(status[i]),
        "pcc_per_day": round(float(pcc[i])), "rcc_per_day": round(float(rcc[i])), "ecc_per_day": round(float(ecc[i])),
    } for i in range(len(seg))]
    main = trails.get(c.get("main_trail", "main"), next(iter(trails.values())))
    return {
        "rain_share_open_hours": round(rain_share, 3),
        "ground_wetness": round(float(wetness), 3),
        "management_capacity": c["management_capacity"],
        "expected_visitors": round(sum(t["expected_visitors"] for t in trails.values())),
        "recommended_daily_quota": round(sum(t["recommended_daily_quota"] for t in trails.values())),
        "classic_cifuentes_quota": round(sum(t["classic_cifuentes_quota"] for t in trails.values())),
        "limiting_segment": main["limiting_segment"],
        "trails": trails,
        "segments": segments,
    }
