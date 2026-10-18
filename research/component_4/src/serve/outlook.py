"""90-day crowd outlook + plan for one target day, as versioned JSON (roadmap.md, sections 2-4).

    python -m src.serve.outlook --issue 2025-03-01                       # 90-day outlook
    python -m src.serve.outlook --issue 2025-03-01 --target 2025-05-12   # + detail and suggestions for that day

Written to results/forecasts/outlook_<issue>.json and plan_<issue>_<target>.json. The outlook is small and is
meant to be cached on the device, so planning works offline until the next refresh.
"""
import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import joblib
import pandas as pd

from src.config import PROCESSED, RESULTS, load_config
from src.data.graph import load_walks
from src.eval.data import TrailData
from src.planning.model import PlanningModel
from src.planning.planner import Planner

SCHEMA_VERSION = "1.1-outlook"
DISCLAIMER = ("Long-range estimate from the calendar, typical weather for the time of year and recent visitor "
              "numbers, trained on a SYNTHETIC occupancy target. The range (P10-P90) should contain the real "
              "number on about 8 of 10 days. Check again closer to the date.")


def build_planner(cfg=None):
    """Planner with a fitted PlanningModel. The fitted model is cached in data/processed and only refitted
    when the dataset or the config changes."""
    cfg = cfg or load_config()
    data = TrailData(cfg)
    cal = pd.read_csv(PROCESSED / "calendar.csv", index_col=0, parse_dates=True)
    seg = gpd.read_file(PROCESSED / "segments.geojson")
    seg["poi"] = seg["poi"].fillna("")
    import src.planning.model as model_code                   # a code change also refits (old pickles break)
    key = hashlib.sha1(json.dumps(cfg, sort_keys=True, default=str).encode()
                       + str((PROCESSED / "dataset.npz").stat().st_mtime_ns).encode()
                       + Path(model_code.__file__).read_bytes()).hexdigest()
    cache = PROCESSED / "planning_model.joblib"
    model = None
    if cache.exists():
        saved = joblib.load(cache)
        if saved.get("key") == key:
            model = saved["model"]
            model.data = data
    if model is None:
        model = PlanningModel(data, cal, cfg["seed"])
        model.data = None                       # do not pickle the big arrays
        joblib.dump({"key": key, "model": model}, cache)
        model.data = data
    return Planner(model, seg, load_walks(), cfg)


def outlook_json(planner, issue: str, horizon: int = 90) -> dict:
    ol = planner.m.outlook(issue, horizon)
    trails = planner.m.daily.trails
    days = [{"date": str(d.date()), "lead_days": int(r.lead), "crowd_level": int(r.crowd_level),
             "visitors": {q: round(float(r[q])) for q in ("p10", "p50", "p90")},
             "visitors_by_trail_p50": {t: round(float(r[f"{t}_p50"])) for t in trails},
             "chance_wet_morning": round(float(r.p_wet), 2)} for d, r in ol.iterrows()]
    return {"schema_version": SCHEMA_VERSION, "component": 4, "site": planner.cfg["area"]["name"],
            "generated_at": datetime.now().isoformat(timespec="seconds"), "issue_date": issue,
            "horizon_days": horizon, "crowd_levels": "1 = quietest 20 % of days ... 5 = busiest 20 %",
            "trails": planner.cfg["area"]["trail_names"], "disclaimer": DISCLAIMER, "days": days}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--issue", default="2025-03-01")
    ap.add_argument("--target", default=None)
    a = ap.parse_args()
    pl = build_planner()
    out_dir = RESULTS / "forecasts"
    out_dir.mkdir(exist_ok=True)
    ol = outlook_json(pl, a.issue)
    (out_dir / f"outlook_{a.issue}.json").write_text(json.dumps(ol, indent=2), encoding="utf-8")
    print(out_dir / f"outlook_{a.issue}.json", f"({len(ol['days'])} days)")
    if a.target:
        plan = {"schema_version": SCHEMA_VERSION, "disclaimer": DISCLAIMER, **pl.day(a.issue, a.target)}
        path = out_dir / f"plan_{a.issue}_{a.target}.json"
        path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
        print(path)
        print(f"visitors {plan['visitors']} crowd level {plan['crowd_level']}")
        for s in plan["suggestions"]:
            print(f"  {s['reduction_pct']:>3}% {s['title']}: {s['detail']}")


if __name__ == "__main__":
    main()
