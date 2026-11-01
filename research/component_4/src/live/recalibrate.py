"""N2: the forecast learns from the rangers' spot counts, and the field trial reads the same counts.

    python -m src.live.recalibrate                        factors for tomorrow + backtest of the last 60 days
    python -m src.live.recalibrate --export 2026-12-01 2026-12-31   counts -> counting sheet for field_validation

Each evening the counts of the last `window_days` are compared with the raw forecasts saved for those days. Per
section the factor is (counted + PRIOR x park factor) / (forecast + PRIOR): a few counts move it a little, many
counts a lot; sections nobody counted get the park-wide factor. Factors are clipped to CLIP and saved next to the
raw forecast (booking.save_forecast), so quotas, the capacity panel and gate control use the corrected forecast
while the counts are still checked against what the model itself said.

Backtest: for every counted day, factors from the days BEFORE it only (no leakage), MAE of raw vs corrected.
"""
import argparse
import csv
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from src.config import load_config
from src.control import booking
from src.control.slots import build_control
from src.serve.field_counts import counts, forecast_check

PRIOR = 30.0          # people: weight of the prior (factor 1, or the park factor) against the counted people
CLIP = (0.5, 2.0)
WINDOW_DAYS = 14


def factors(cfg, day: str, window_days: int = WINDOW_DAYS, db=None) -> dict:
    """Factors for `day` from the counts of the `window_days` days before it."""
    d = date.fromisoformat(day)
    start, end = (d - timedelta(days=window_days)).isoformat(), (d - timedelta(days=1)).isoformat()
    rows = [r for r in forecast_check(cfg, start, end, db)["rows"] if r["forecast"] is not None]
    c = np.array([r["count"] for r in rows], float)
    f = np.array([r["forecast"] for r in rows], float)
    park = float(np.clip((c.sum() + PRIOR) / (f.sum() + PRIOR), *CLIP))
    sections = {}
    for s in sorted({r["seg_id"] for r in rows}):
        m = np.array([r["seg_id"] == s for r in rows])
        k = (c[m].sum() + PRIOR * park) / (f[m].sum() + PRIOR)
        sections[int(s)] = {"factor": round(float(np.clip(k, *CLIP)), 3), "counts": int(m.sum()),
                            "counted": int(c[m].sum()), "forecast": round(float(f[m].sum()), 1)}
    return {"day": day, "window": [start, end], "counts": len(rows), "park_factor": round(park, 3),
            "sections": sections}


def vector(fac: dict) -> np.ndarray:
    """Factors in entry-control segment order (the column order of the saved forecasts)."""
    order = build_control().seg.seg_id.astype(int).tolist()
    return np.array([fac["sections"].get(i, {}).get("factor", fac["park_factor"]) for i in order])


def correct_saved(cfg, day: str, db=None, fac: dict | None = None) -> dict | None:
    """Attach the factors (by default from the counts before `day`) to the forecast already saved for `day`.
    The live refresh passes tomorrow's factors for every later day too: they are the latest the counts tell."""
    hourly, basis = booking.day_forecast(day, db, raw=True)
    fac = fac or factors(cfg, day, cfg["live"].get("recalibrate_window_days", WINDOW_DAYS), db)
    if hourly is None or not fac["counts"]:
        return None
    booking.save_forecast(day, hourly, basis, db, correction=vector(fac))
    return fac


def backtest(cfg, start: str, end: str, window_days: int = WINDOW_DAYS, db=None) -> dict:
    """Per counted day: MAE of the raw forecast and of the forecast corrected with factors from earlier days only."""
    order = {i: j for j, i in enumerate(build_control().seg.seg_id.astype(int))}
    days, raw_e, cor_e = [], [], []
    for day in sorted({r["day"] for r in counts(start, end, db)}):
        rows = [r for r in forecast_check(cfg, day, day, db)["rows"] if r["forecast"] is not None]
        fac = factors(cfg, day, window_days, db)
        if not rows or not fac["counts"]:
            continue
        k = vector(fac)
        e_raw = [abs(r["forecast"] - r["count"]) for r in rows]
        e_cor = [abs(r["forecast"] * k[order[r["seg_id"]]] - r["count"]) for r in rows]
        days.append({"day": day, "counts": len(rows), "mae_raw": round(float(np.mean(e_raw)), 2),
                     "mae_corrected": round(float(np.mean(e_cor)), 2), "park_factor": fac["park_factor"]})
        raw_e += e_raw
        cor_e += e_cor
    out = {"start": start, "end": end, "days": days, "window_days": window_days}
    if raw_e:
        out |= {"mae_raw": round(float(np.mean(raw_e)), 2), "mae_corrected": round(float(np.mean(cor_e)), 2),
                "change_pct": round(100 * (np.mean(cor_e) / max(np.mean(raw_e), 1e-9) - 1), 1)}
    return out


def export_sheet(cfg, start: str, end: str, path: Path, db=None) -> int:
    """The app's spot counts as a field-validation counting sheet (src/eval/field_validation.py)."""
    poi = {int(s.seg_id): s.poi for _, s in build_control().seg.iterrows() if s.poi}
    rows = counts(start, end, db)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["date", "time", "place", "count", "counter", "notes"])
        for r in rows:
            w.writerow([r["day"], f"{r['time_min'] // 60:02d}:{r['time_min'] % 60:02d}",
                        poi.get(r["seg_id"], f"seg:{r['seg_id']}"), r["count"], r["counted_by"], "app"])
    return len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", nargs=2, metavar=("START", "END"))
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    cfg = load_config()
    if a.export:
        from src.config import ROOT
        out = Path(a.out or ROOT / "data" / "field" / cfg["park"] / f"app_counts_{a.export[0]}_{a.export[1]}.csv")
        print(f"{export_sheet(cfg, *a.export, out)} counts -> {out}")
        return
    today = date.today()
    print(factors(cfg, (today + timedelta(days=1)).isoformat()))
    print(backtest(cfg, (today - timedelta(days=60)).isoformat(), today.isoformat()))


if __name__ == "__main__":
    main()
