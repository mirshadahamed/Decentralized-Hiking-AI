"""Start the API for every park plus the gateway on one port.

    .venv\\Scripts\\python.exe -m src.api.serve_all              # gateway on http://localhost:8000
    App:  flutter run -d chrome --dart-define=C4_API=http://localhost:8000
    Phone on the same Wi-Fi:  serve_all --host 0.0.0.0, app with C4_API=http://<PC IP>:8000

Workers: one per park on ports 8101, 8102, ... (each with its own C4_PARK), local only: phones reach them
through the gateway. Ctrl+C stops all of them.
"""
import argparse
import os
import subprocess
import sys

import uvicorn

from src.api.gateway import PORTS


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
    try:
        uvicorn.run("src.api.gateway:app", host=a.host, port=a.port)
    finally:
        for w in workers:
            w.terminate()


if __name__ == "__main__":
    main()
