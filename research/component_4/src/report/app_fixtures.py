"""Saved API responses for the staff-screen screenshots (officer quota panel, gate advice, spot counts, forecast
check), so `test/component_4/screenshots_test.dart` can render them without a server.
    .venv\\Scripts\\python.exe -m src.report.app_fixtures --out <folder>
Uses temporary copies of the booking / account databases (the real ones are not touched). The gate-advice and spot-count
situations are demo data (a crowded morning, a ranger's counts), labelled as such on the slides.
"""
import argparse
import json
import shutil
import tempfile
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

PW = "fixture-password-123"


def dump(out: Path):
    from fastapi.testclient import TestClient
    from src.api import app as api, auth
    from src.control import booking
    from src.control.gate_advice import gate_advice
    from src.control.slots import build_control

    tmp = Path(tempfile.mkdtemp())
    if booking.DB.exists():                                    # a copy keeps the saved day-ahead forecasts
        shutil.copy(booking.DB, tmp / "bookings.sqlite")
    booking.DB, auth.DB = tmp / "bookings.sqlite", tmp / "auth.sqlite"
    auth.create_user("officer1", PW, "officer")
    client = TestClient(api.app)
    tok = client.post("/auth/login", json={"username": "officer1", "password": PW}).json()["token"]
    hdr = {"Authorization": f"Bearer {tok}"}
    park = out / "horton_plains"
    park.mkdir(parents=True, exist_ok=True)

    def save(name, obj):
        (park / f"{name}.json").write_text(json.dumps(obj, indent=1), encoding="utf-8")

    today = api.ctx().today
    busy = max((today + timedelta(days=i) for i in range(2, 16)),           # the busiest day of the next fortnight
               key=lambda d: client.get(f"/plan/{d}").json()["visitors"]["p50"])
    save("capacity_panel", client.get(f"/admin/capacity/{busy}", headers=hdr).json())
    save("segments", client.get("/segments").json())

    # gate advice on a crowded morning (demo): 40 groups of 12 through the gate since 06:00, coming slots full
    ec = build_control()
    main = ec.cfg["area"].get("main_trail", ec.trails[0])
    inside = pd.DataFrame({"trail": main, "gate_min": np.linspace(6 * 60, 7 * 60 + 50, 40), "size": 12.0})
    plan = pd.DataFrame(0, index=[f"{s // 60:02d}:{s % 60:02d}" for s in ec.slots], columns=ec.trails)
    plan[main] = 150
    save("gate_advice", gate_advice(ec, inside, 8 * 60, 0.0, plan))

    # a ranger's spot counts (demo): on the day of the latest saved day-ahead forecast, at the named places,
    # forecast x lognormal noise, so the check screen has something to compare
    rng = np.random.default_rng(7)
    day = client.get("/forecast/tomorrow").json()["forecast_date"]
    fc, _ = booking.day_forecast(day)
    col = {int(sid): k for k, sid in enumerate(ec.seg.seg_id)}
    named = [x for x in client.get("/segments").json() if "section" not in x["name"]][:5]
    for x in named:
        for h in (8, 9, 10, 11):
            f = 20.0 if fc is None else float(fc[h, col[x["seg_id"]]])
            client.post("/counts", headers=hdr, json={
                "day": day, "seg_id": x["seg_id"], "time": f"{h:02d}:30",
                "count": int(round(f * rng.lognormal(0, 0.3))), "client_id": f"fx-{x['seg_id']}-{h}"})
    save("forecast_check", client.get("/admin/forecast-check", headers=hdr,
                                      params={"start": str(today - timedelta(days=7)), "end": day}).json())
    return park


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    print(dump(ap.parse_args().out))
