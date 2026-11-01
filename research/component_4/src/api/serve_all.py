"""Start the API for every park plus the gateway on one port.

    .venv\\Scripts\\python.exe -m src.api.serve_all              # gateway on http://localhost:8000
    App:  flutter run -d chrome --dart-define=C4_API=http://localhost:8000
    Phone on the same Wi-Fi:  serve_all --host 0.0.0.0, app with C4_API=http://<PC IP>:8000

Workers: one per park on ports 8101, 8102, ... (each with its own C4_PARK), local only: phones reach them
through the gateway. Ctrl+C stops all of them. Each worker's forecasts for the next two weeks are worked out once at
start and again each night at 02:30 (warm()), so the first phones of the morning do not wait for them (§6.3.12).
"""
import argparse
import os
import subprocess
import sys
import threading
import time
from datetime import date, datetime, timedelta

import httpx
import uvicorn

from src.api.gateway import PORTS


WARM_DAYS = 14


def warm(days: int = WARM_DAYS, wait_s: float = 300) -> int:
    """Ask every worker for /capacity of the next `days` days (fills its planner memo); returns how many answered."""
    ok, until = 0, time.time() + wait_s
    with httpx.Client(timeout=120, verify=False, trust_env=False) as client:
        for port in PORTS.values():
            while True:                                          # a worker that is still loading its models
                try:
                    client.get(f"http://127.0.0.1:{port}/health")
                    break
                except httpx.HTTPError:
                    if time.time() > until:
                        break
                    time.sleep(2)
            for k in range(1, days + 1):
                day = date.today() + timedelta(days=k)
                try:
                    ok += client.get(f"http://127.0.0.1:{port}/capacity/{day}").status_code == 200
                except httpx.HTTPError:
                    pass
    return ok


def warm_nightly(at: tuple = (2, 30)):
    def once():
        try:
            print(f"warm: {warm()} forecasts ready")
        except Exception as e:                                    # never stop the servers for this
            print(f"warm failed: {e}")

    def loop():
        once()
        while True:
            now = datetime.now()
            nxt = now.replace(hour=at[0], minute=at[1], second=0, microsecond=0)
            if nxt <= now:
                nxt += timedelta(days=1)
            time.sleep((nxt - now).total_seconds())
            once()
    threading.Thread(target=loop, daemon=True, name="c4-warm").start()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1", help="0.0.0.0 = reachable from phones on the same network")
    a = ap.parse_args()
    workers = []
    for park, port in PORTS.items():
        env = dict(os.environ, C4_PARK=park)
        workers.append(subprocess.Popen([sys.executable, "-m", "uvicorn", "src.api.app:app", "--port", str(port),
                                         "--log-level", "warning"], env=env))
        print(f"{park}: worker on port {port}")
    from src.api.backup import nightly
    nightly()                                                    # §6.3.11: copy the databases at 02:00
    warm_nightly()                                               # §6.3.12: forecasts of the next 2 weeks
    try:
        uvicorn.run("src.api.gateway:app", host=a.host, port=a.port)
    finally:
        for w in workers:
            w.terminate()


if __name__ == "__main__":
    main()
