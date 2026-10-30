"""§6.3.11-12: nightly database copies (kept 14 days) and the gateway's short cache of public forecasts."""
import sqlite3
from contextlib import closing
from datetime import date

from src.api import backup


def test_backup_copies_each_park_and_drops_old_copies(tmp_path, monkeypatch):
    monkeypatch.setattr(backup, "parks", lambda: ["horton_plains", "knuckles"])
    for park in ("horton_plains", "knuckles"):
        (tmp_path / park).mkdir()
        with closing(sqlite3.connect(tmp_path / park / "bookings.sqlite")) as c:
            c.execute("CREATE TABLE t (x)")
            c.execute("INSERT INTO t VALUES (?)", (park,))
            c.commit()
    old = tmp_path / "backups" / "knuckles" / "2026-10-01"
    old.mkdir(parents=True)
    (old / "bookings.sqlite").write_bytes(b"")
    out = backup.backup_all(keep=14, today=date(2026, 11, 2), root=tmp_path)
    assert len(out) == 2 and not old.exists()
    with closing(sqlite3.connect(tmp_path / "backups" / "knuckles" / "2026-11-02" / "bookings.sqlite")) as c:
        assert c.execute("SELECT x FROM t").fetchone() == ("knuckles",)


def test_gateway_cache_expires(monkeypatch):
    from src.api import gateway
    gateway._cache.clear()
    t = [100.0]
    monkeypatch.setattr(gateway.time, "monotonic", lambda: t[0])
    gateway._store(("p", "capacity/2026-11-02", ""), ("x",))
    assert gateway._cached(("p", "capacity/2026-11-02", "")) == ("x",)
    t[0] += gateway.CACHE_S + 1
    assert gateway._cached(("p", "capacity/2026-11-02", "")) is None
    assert "capacity/2026-11-02".startswith(gateway.CACHED) and not "bookings/X".startswith(gateway.CACHED)
