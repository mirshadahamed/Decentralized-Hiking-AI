"""§6.3.12 load test: how many visitors' phones the gateway and park workers serve at once (a Poya morning).

    python -m src.api.load_test --start                      # start serve_all on a spare port, test, stop it
    python -m src.api.load_test --url http://127.0.0.1:8000  # test a server that is already running
    python -m src.api.load_test --start --users 10 50 200 --seconds 30

Each simulated user repeats what the app does when opened: status, outlook, the day's capacity and slots, the
trails, the network advice; at a random park, for the busy day being asked about (70 %, e.g. the coming Poya)
or another day in the next two weeks. Read-only: no bookings are made,
so the park databases are not touched. Per level of concurrent users: requests / s, latency p50 / p95 / p99,
errors (5xx or no answer; a 400 such as Adam's Peak /slots, which has no bookings, is a
correct answer), and the share served from the gateway cache (§6.3.12).
Outputs results/<timestamp>_load/: summary.csv, summary.json; results/LATEST_LOAD.
"""
import argparse
import asyncio
import json
import os
import random
import subprocess
import sys
import time
from datetime import date, timedelta

import httpx
import numpy as np
import pandas as pd

from src.config import RESULTS, load_config, parks
from src.utils import new_run_dir

SEED = 7
HOT = 0.7                     # share of users asking about the same (busy) day


def _paths(park: str, day: str) -> list[str]:
    p = f"/parks/{park}"
    return [f"{p}/status", f"{p}/outlook", f"{p}/capacity/{day}", f"{p}/slots/{day}", f"{p}/trails",
            f"/network/{day}?park={park}"]


async def _user(client, url, names, days, rng, until, out):
    while time.perf_counter() < until:
        day = days[0] if rng.random() < HOT else rng.choice(days[1:])
        for path in _paths(rng.choice(names), day):
            t0 = time.perf_counter()
            try:
                r = await client.get(url + path)
                out.append((time.perf_counter() - t0, r.status_code, r.headers.get("x-cache") == "hit", path))
            except httpx.HTTPError:
                out.append((time.perf_counter() - t0, 0, False, path))
            if time.perf_counter() >= until:
                return


async def level(url: str, users: int, seconds: float, names: list, days: list, seed: int) -> dict:
    out: list = []
    limits = httpx.Limits(max_connections=users, max_keepalive_connections=users)
    async with httpx.AsyncClient(timeout=120, limits=limits) as client:
        t0 = time.perf_counter()
        until = t0 + seconds
        await asyncio.gather(*[_user(client, url, names, days, random.Random(seed * 1000 + i), until, out)
                               for i in range(users)])
        took = time.perf_counter() - t0
    lat = np.array([x[0] for x in out]) * 1000
    ok = np.array([0 < x[1] < 500 for x in out])
    return {"users": users, "seconds": round(took, 1), "requests": len(out),
            "requests_per_s": round(len(out) / took, 1),
            "p50_ms": round(float(np.percentile(lat, 50)), 1), "p95_ms": round(float(np.percentile(lat, 95)), 1),
            "p99_ms": round(float(np.percentile(lat, 99)), 1),
            "error_pct": round(100 * float((~ok).mean()), 2),
            "cache_hit_pct": round(100 * float(np.mean([x[2] for x in out])), 1),
            "network_p95_ms": round(float(np.percentile([x[0] * 1000 for x in out if x[3].startswith("/network")]
                                                         or [0], 95)), 1)}


def _wait(url: str, timeout_s: float = 300):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        try:
            if all(httpx.get(f"{url}/parks/{p}/health", timeout=5).status_code == 200 for p in parks()):
                return
        except httpx.HTTPError:
            pass
        time.sleep(2)
    raise RuntimeError(f"{url} did not come up in {timeout_s} s")


def run(url: str, users: list, seconds: float, warm: bool = True, log=print):
    names = parks()
    days = [(date.today() + timedelta(days=k)).isoformat() for k in range(2, 16)]
    if warm:                                                  # first request per park loads its models: not a load
        asyncio.run(level(url, 1, 5, names, days, SEED))
    rows = []
    for n in users:
        r = asyncio.run(level(url, n, seconds, names, days, SEED + n))
        log(r)
        rows.append(r)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--start", action="store_true", help="start serve_all on --port first (stopped afterwards)")
    ap.add_argument("--port", type=int, default=8090)
    ap.add_argument("--users", type=int, nargs="+", default=[1, 10, 50, 100, 200])
    ap.add_argument("--seconds", type=float, default=30)
    a = ap.parse_args()
    random.seed(SEED)
    np.random.seed(SEED)
    proc = None
    url = a.url
    if a.start:
        url = f"http://127.0.0.1:{a.port}"
        proc = subprocess.Popen([sys.executable, "-m", "src.api.serve_all", "--port", str(a.port)],
                                env=dict(os.environ, C4_OFFLINE="1"))
    try:
        _wait(url)
        df = run(url, a.users, a.seconds)
    finally:
        if proc is not None:                                  # stop serve_all and its park workers
            if os.name == "nt":
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
            else:
                proc.terminate()
            proc.wait(30)
    out = new_run_dir("load", load_config())
    df.to_csv(out / "summary.csv", index=False)
    (out / "summary.json").write_text(json.dumps({"url": url, "parks": parks(), "seed": SEED,
                                                  "cpu_count": os.cpu_count(), "levels": df.to_dict("records")},
                                                 indent=2), encoding="utf-8")
    (RESULTS / "LATEST_LOAD").write_text(out.name, encoding="utf-8")
    print(df.to_string(index=False))
    print("->", out)
