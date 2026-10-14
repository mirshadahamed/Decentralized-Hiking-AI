"""Cifuentes (1992) carrying-capacity cascade, driven by the day-ahead forecast (D6 / FR3).

Per segment s (visits per day):
    PCC_s = (L_s / sp) * (open_minutes / visit_minutes_s)                    physical capacity
    RCC_s = PCC_s * (1-FCsoc)(1-FCero)(1-FCacc)(1-FCpre) * (1-FCcrowd_s)       real capacity
    ECC_s = RCC_s * MC                                                         effective capacity
Park quota for the day = min_s ECC_s (the most limiting segment sets the quota).

Trail-level factors, as in Cifuentes (limiting length or hours / total length or hours):
    FCsoc  social: trail length that must stay empty between groups
    FCero  erodibility: length-weighted share of waterlogging-prone ground (TWI)
    FCacc  accessibility: length-weighted share of 10-20 % (x1) and > 20 % (x1.5) grades
    FCpre  precipitation: share of open hours with rain in the FORECAST          -> changes daily
Segment-level factor added by this project (same form as FCpre):
    FCcrowd_s = share of open hours in which the FORECAST occupancy of segment s exceeds the
                number of people the segment holds at the social spacing      -> changes daily
"""
import numpy as np
import pandas as pd


def trail_factors(seg: pd.DataFrame, rain_share: float, c: dict) -> dict:
    sp, g, gap = c["space_per_person_m"], c["group_size"], c["group_gap_m"]
    w = seg.length_m.values / seg.length_m.sum()
    return {
        "social": 1 - g * sp / (gap + g * sp),
        "erodibility": float(min(0.9, np.sum(w * seg.frac_wet.values) * 1.5)),
        "accessibility": float(min(0.9, np.sum(w * (seg.frac_grade_med.values + 1.5 * seg.frac_grade_high.values)))),
        "precipitation": rain_share,
    }


def capacity(seg: pd.DataFrame, forecast: np.ndarray, rain_mm_hourly: np.ndarray,
             expected_visitors: float, c: dict, sim: dict) -> dict:
    """seg: segment table; forecast: [24, N] persons; rain_mm_hourly: [24] forecast rain;
    sim: simulator parameters (walking speed factor and viewpoint dwell times give the visit time)."""
    sp, L = c["space_per_person_m"], seg.length_m.values
    open_h = np.arange(6, 6 + c["open_hours"])
    rain_share = float((rain_mm_hourly[open_h] >= c["rain_mm"]).mean())
    fc = trail_factors(seg, rain_share, c)
    keep_trail = np.prod([1 - v for v in fc.values()])

    fc_open = forecast[open_h]                                           # [open hours, N]
    at_once = L / (c["group_gap_m"] + c["group_size"] * sp) * c["group_size"]   # people at social spacing
    fc_crowd = (fc_open > at_once).mean(0)                               # [N]

    dwell = np.array([sim["dwell_minutes"].get(p, [0])[0] if p else 0 for p in seg.poi])
    visit_min = seg.tobler_fwd_min.values / sim["leisure_speed_factor"] + dwell
    pcc = (L / sp) * (c["open_hours"] * 60 / visit_min)
    rcc_classic = pcc * keep_trail
    rcc = rcc_classic * (1 - fc_crowd)
    ecc, ecc_classic = rcc * c["management_capacity"], rcc_classic * c["management_capacity"]

    peak, peak_hour = fc_open.max(0), open_h[fc_open.argmax(0)]
    util = peak / at_once
    status = np.where(fc_crowd > 0, "bottleneck", np.where(util >= c["busy_utilisation"], "busy", "ok"))
    limiting = int(np.argmin(ecc))
    segments = [{
        "seg_id": int(seg.seg_id.iloc[i]), "poi": seg.poi.iloc[i] or None, "length_m": float(L[i]),
        "forecast_hourly": [round(float(v), 1) for v in forecast[:, i]],
        "peak_occupancy": round(float(peak[i]), 1), "peak_hour": int(peak_hour[i]),
        "capacity_at_once": round(float(at_once[i]), 1), "utilisation": round(float(util[i]), 2),
        "crowded_hours_share": round(float(fc_crowd[i]), 3), "status": str(status[i]),
        "pcc_per_day": round(float(pcc[i])), "rcc_per_day": round(float(rcc[i])), "ecc_per_day": round(float(ecc[i])),
    } for i in range(len(seg))]
    return {
        "trail_correction_factors": {k: round(float(v), 3) for k, v in fc.items()},
        "management_capacity": c["management_capacity"],
        "expected_visitors": round(float(expected_visitors)),
        "recommended_daily_quota": round(float(ecc[limiting])),
        "classic_cifuentes_quota": round(float(ecc_classic.min())),
        "limiting_segment": int(seg.seg_id.iloc[limiting]),
        "segments": segments,
    }
