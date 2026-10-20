"""RQ7 / objective O2: how close are the synthetic target and the ST-GNN forecast to REAL counts?

    python -m src.eval.field_validation data/field/horton_plains/2026-12-12_worlds_end.csv [more.csv ...]
    (refresh the live data first: the visit days must be inside the live dataset)

Counting sheet (CSV, one row per headcount; template in docs/field_validation_protocol.md):
    date,time,place,count,counter,notes
    2026-12-12,08:15,worlds_end,64,JV,clear
  place = a POI key (worlds_end, mini_worlds_end, bakers_falls, entrance, summit, half_nallathanniya, ...)
          or a segment number ("seg:12")
  count = people PRESENT on that place at that moment (a snapshot headcount, the same quantity the model gives)

Compared per count, at the hour of the count:
  simulated   the synthetic target for that day (simulated history driven by that day's real weather)
  forecast    the ST-GNN day-ahead forecast made the evening before (or the historical average fallback)
AGREEMENT CRITERIA – fixed BEFORE the visits (docs/field_validation_protocol.md):
  A1  MAE / mean observed peak <= 0.25            (typical error within a quarter of a busy moment)
  A2  Spearman rank correlation >= 0.6             (busier moments are ranked busier)
  A3  peak hour within +-1 h, per place and day    (the bottleneck is predicted at the right time)
Outputs results/<park>/<timestamp>_field_validation/: pairs.csv, report.json
"""
import argparse
import json

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy import stats

from src.config import PROCESSED, RESULTS, load_config
from src.live.dataset import load_live
from src.eval.data import TrailData
from src.serve.predict import build_forecast, load_model
from src.utils import new_run_dir

CRITERIA = {"A1_mae_over_peak_max": 0.25, "A2_spearman_min": 0.6, "A3_peak_hour_tolerance_h": 1}


def read_counts(paths) -> pd.DataFrame:
    df = pd.concat([pd.read_csv(p, dtype={"place": str}) for p in paths], ignore_index=True)
    need = {"date", "time", "place", "count"}
    if not need <= set(df.columns):
        raise ValueError(f"counting sheet needs columns {sorted(need)}")
    df["hour"] = pd.to_datetime(df["time"], format="%H:%M").dt.hour
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    return df


def segment_of(place: str, seg: pd.DataFrame) -> int:
    if place.startswith("seg:"):
        return int(place[4:])
    hit = seg.index[seg.poi == place]
    if not len(hit):
        raise ValueError(f"unknown place '{place}': use a POI key ({sorted(set(seg.poi) - {''})}) or seg:<n>")
    return int(hit[0])


def compare(counts: pd.DataFrame, cfg, data, seg, model=None, scale=None, run=None) -> tuple[pd.DataFrame, dict]:
    rows, forecasts = [], {}
    for r in counts.itertuples():
        s = segment_of(r.place, seg)
        if r.date not in forecasts:
            forecasts[r.date] = build_forecast(data, cfg, seg, r.date, model, scale, run)
        f = forecasts[r.date]
        t = int(np.searchsorted(data.times, pd.Timestamp(r.date))) + r.hour
        rows.append({"date": r.date, "hour": r.hour, "place": r.place, "segment": s, "observed": float(r.count),
                     "simulated": float(data.y_true[t, s]),
                     "forecast": float(f["segments"][s]["forecast_hourly"][r.hour]),
                     "forecast_source": f["source"]["model"]})
    pairs = pd.DataFrame(rows)
    report = {"criteria": CRITERIA, "counts": int(len(pairs)), "days": sorted(pairs.date.unique().tolist()),
              "places": sorted(pairs.place.unique().tolist())}
    peak = pairs.groupby(["date", "place"])["observed"].max().mean()
    for what in ("simulated", "forecast"):
        err = (pairs[what] - pairs.observed).abs()
        rho = stats.spearmanr(pairs[what], pairs.observed).statistic if len(pairs) > 2 else float("nan")
        hits = []
        for _, g in pairs.groupby(["date", "place"]):
            if len(g) >= 3:
                hits.append(abs(int(g.loc[g.observed.idxmax(), "hour"]) - int(g.loc[g[what].idxmax(), "hour"]))
                            <= CRITERIA["A3_peak_hour_tolerance_h"])
        a1 = float(err.mean() / max(peak, 1e-9))
        report[what] = {"MAE_people": round(float(err.mean()), 2), "mean_observed_peak": round(float(peak), 1),
                        "A1_mae_over_peak": round(a1, 3), "A1_pass": bool(a1 <= CRITERIA["A1_mae_over_peak_max"]),
                        "A2_spearman": round(float(rho), 3), "A2_pass": bool(rho >= CRITERIA["A2_spearman_min"]),
                        "A3_peak_hour_hits": f"{sum(hits)}/{len(hits)}",
                        "A3_pass": bool(hits and sum(hits) / len(hits) >= 0.5),
                        "bias_people": round(float((pairs[what] - pairs.observed).mean()), 2)}
    return pairs, report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sheets", nargs="+")
    a = ap.parse_args()
    cfg = load_config()
    _, path, _, _, _ = load_live()
    data = TrailData(cfg, path)
    seg = gpd.read_file(PROCESSED / "segments.geojson")
    seg["poi"] = seg["poi"].fillna("")
    try:
        model, scale, run = load_model(data, cfg)
    except (FileNotFoundError, RuntimeError):
        model, scale, run = None, None, None
    pairs, report = compare(read_counts(a.sheets), cfg, data, seg, model, scale, run)
    out = new_run_dir("field_validation", cfg)
    pairs.to_csv(out / "pairs.csv", index=False)
    (out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (RESULTS / "LATEST_FIELD_VALIDATION").write_text(out.name, encoding="utf-8")
    print(json.dumps(report, indent=1))
    print(out)


if __name__ == "__main__":
    main()
