"""§6.3.11: nightly copies of every park's databases (bookings, permits, campsites, counts, staff accounts).

    python -m src.api.backup                 # copy now, keep the last 14 per park
    python -m src.api.backup --keep 30

serve_all also runs it once a night (02:00) while it is up. SQLite's online backup copies a consistent database
even while a worker writes to it. Copies go to data/backups/<park>/<YYYY-MM-DD>/ (data/ is not in git).
If several gates write at the same time, move to Postgres; until then one file per park is enough.
"""
import argparse
import sqlite3
import threading
import time
from contextlib import closing
from datetime import date, datetime, timedelta

from src.config import DEFAULT_PARK, ROOT, parks

BACKUPS = ROOT / "data" / "backups"
FILES = ("bookings.sqlite", "auth.sqlite")


def park_dir(park: str):
    return ROOT / "data" if park == DEFAULT_PARK else ROOT / "data" / park


def backup_all(keep: int = 14, today: date | None = None, root=None) -> list:
    """Copy each park's databases; remove copies older than `keep` days. Returns the files written."""
    today = today or date.today()
    base = BACKUPS if root is None else root / "backups"
    out = []
    for park in parks():
        src_dir = park_dir(park) if root is None else root / park
        dest = base / park / today.isoformat()
        for name in FILES:
            f = src_dir / name
            if not f.exists():
                continue
            dest.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(f)) as a, closing(sqlite3.connect(dest / name)) as b:
                a.backup(b)
            out.append(dest / name)
        old = today - timedelta(days=keep)
        for d in (base / park).glob("*") if (base / park).exists() else []:
            try:
                if date.fromisoformat(d.name) <= old:
                    for x in d.iterdir():
                        x.unlink()
                    d.rmdir()
            except ValueError:
                continue
    return out


def nightly(at_hour: int = 2, keep: int = 14):
    """A daemon thread that backs up once a night at `at_hour` (used by serve_all)."""
    def loop():
        while True:
            now = datetime.now()
            nxt = now.replace(hour=at_hour, minute=0, second=0, microsecond=0)
            if nxt <= now:
                nxt += timedelta(days=1)
            time.sleep((nxt - now).total_seconds())
            try:
                backup_all(keep)
            except Exception as e:                                    # never stop the servers for a backup
                print(f"backup failed: {e}")
    threading.Thread(target=loop, daemon=True, name="c4-backup").start()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", type=int, default=14)
    for f in backup_all(ap.parse_args().keep):
        print(f)
