"""Saved API responses of every park, so `test/component_4/screenshots_test.dart` can render every screen without a
server (slides, reports, before/after UI reviews).
    .venv\\Scripts\\python.exe -m src.report.app_fixtures --out <folder>
Writes <folder>/parks.json and <folder>/<park>/<name>.json. Each park is dumped in its own process (the API reads
C4_PARK on import), from temporary copies of its booking / account databases (the real ones are not touched).
The gate-advice, spot-count and halfway-count situations are demo data (a crowded morning, a ranger's counts, a busy
Poya night), labelled as such on the slides.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

PW = "fixture-password-123"
DAY = "2026-11-24"                  # Horton Plains day screen (Il Poya)
NIGHT = "2026-12-25"                # Adam's Peak: a busy season night


def dump(out: Path, park_id: str) -> Path:
    from fastapi.testclient import TestClient
    from src.api import app as api, auth
    from src.config import load_config
    from src.control import booking

    cfg = load_config()
    tmp = Path(tempfile.mkdtemp())
    if booking.DB.exists():                                    # a copy keeps the saved day-ahead forecasts
        shutil.copy(booking.DB, tmp / "bookings.sqlite")
    booking.DB, auth.DB = tmp / "bookings.sqlite", tmp / "auth.sqlite"
    auth.create_user("officer1", PW, "officer")
    client = TestClient(api.app)
    tok = client.post("/auth/login", json={"username": "officer1", "password": PW}).json()["token"]
    hdr = {"Authorization": f"Bearer {tok}"}
    park = out / park_id
    park.mkdir(parents=True, exist_ok=True)

    def get(path, **params):
        r = client.get(path, headers=hdr, params=params or None)
        r.raise_for_status()
        return r.json()

    def save(name, obj):
        (park / f"{name}.json").write_text(json.dumps(obj, indent=1), encoding="utf-8")

    today = api.ctx().today
    tomorrow = get("/forecast/tomorrow")
    for name, path in (("status", "/status"), ("destination", "/destination"), ("outlook", "/outlook"),
                       ("trails", "/trails"), ("geometry", "/trails/geometry"), ("edge_pack", "/edge/pack"),
                       ("segments", "/segments"), ("plan", f"/plan/{DAY}")):
        save(name, get(path))
    save("tomorrow", tomorrow)

    if cfg["control"].get("booking_mode", "required") == "advisory":
        save("advisory", get(f"/advisory/{NIGHT}"))
        save("season", get("/admin/season"))
        route = cfg["area"]["main_trail"]
        for hh in ("01:45", "01:55", "02:05", "02:15"):        # a busy Poya night at the halfway checkpoint (demo)
            client.post("/checkpoints", headers=hdr, json={"route": route, "count": 500, "at": f"{NIGHT}T{hh}:00"})
        save("checkpoints", get(f"/checkpoints/{NIGHT}", at="02:15"))
        return park

    for suffix, d in (("", DAY), ("_tomorrow", tomorrow["forecast_date"])):
        save(f"slots{suffix}", get(f"/slots/{d}"))
        save(f"capacity{suffix}", get(f"/capacity/{d}"))
    save("records", get("/admin/records", start=str(today - timedelta(days=14)), end=str(today + timedelta(days=7))))
    busy = max((today + timedelta(days=i) for i in range(2, 16)),           # the busiest day of the next fortnight
               key=lambda d: get(f"/plan/{d}")["visitors"]["p50"])
    save("capacity_panel", get(f"/admin/capacity/{busy}"))
    _staff_demo(client, hdr, today, tomorrow["forecast_date"], save)
    return park


def _staff_demo(client, hdr, today: date, day: str, save):
    """Gate advice on a crowded morning and a ranger's spot counts (demo data)."""
    from src.control import booking
    from src.control.gate_advice import gate_advice
    from src.control.slots import build_control

    # gate advice: 40 groups of 12 through the gate since 06:00, the coming slots full
    ec = build_control()
    main = ec.cfg["area"].get("main_trail", ec.trails[0])
    inside = pd.DataFrame({"trail": main, "gate_min": np.linspace(6 * 60, 7 * 60 + 50, 40), "size": 12.0})
    plan = pd.DataFrame(0, index=[f"{s // 60:02d}:{s % 60:02d}" for s in ec.slots], columns=ec.trails)
    plan[main] = 150
    save("gate_advice", gate_advice(ec, inside, 8 * 60, 0.0, plan))

    # spot counts at the named places on the day of the saved day-ahead forecast: forecast x lognormal noise
    rng = np.random.default_rng(7)
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--park", default=None, help="dump one park in this process (used internally)")
    a = ap.parse_args()
    if a.park:
        print(dump(a.out, a.park))
        return
    from src.api.gateway import list_parks
    from src.config import parks
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "parks.json").write_text(json.dumps(list_parks(), indent=1), encoding="utf-8")
    for p in parks():
        r = subprocess.run([sys.executable, "-m", "src.report.app_fixtures", "--out", str(a.out), "--park", p],
                           env=dict(os.environ, C4_PARK=p), capture_output=True, text=True)
        print(p, "ok" if r.returncode == 0 else r.stderr[-2000:])


if __name__ == "__main__":
    main()
