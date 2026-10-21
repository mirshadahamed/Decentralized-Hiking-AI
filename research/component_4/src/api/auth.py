"""Staff accounts, sessions and audit log (docs/archive/live_and_ux_plan.md, section 3).

- Roles: ranger < officer < admin (a higher role can do everything a lower one can). Visitors need no account.
- Passwords: salted scrypt hashes only (never stored or logged in plain text); at least 10 characters.
- Sessions: random bearer tokens (revocable), valid for 12 hours.
- Lockout: 5 failed logins -> locked for 15 minutes.
- Audit: every staff action is written with who, when and what.
Accounts are created from the command line (no default passwords):
    python -m src.api.users add --username ranger1 --role ranger
"""
import hashlib
import hmac
import secrets
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta

from src.config import DATA

DB = DATA / "auth.sqlite"
ROLES = {"ranger": 1, "officer": 2, "admin": 3}
SESSION_HOURS = 12
MAX_FAILS, LOCK_MINUTES = 5, 15


def _connect(db=None):
    con = sqlite3.connect(db or DB)
    con.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY, role TEXT NOT NULL, salt BLOB NOT NULL, pw_hash BLOB NOT NULL,
            failed INTEGER NOT NULL DEFAULT 0, locked_until TEXT, created TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, username TEXT NOT NULL, expires TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, username TEXT NOT NULL,
            action TEXT NOT NULL, detail TEXT NOT NULL);
    """)
    return con


def _hash(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)


def create_user(username: str, password: str, role: str, db=None):
    if role not in ROLES:
        raise ValueError(f"role must be one of {list(ROLES)}")
    if len(password) < 10:
        raise ValueError("password must have at least 10 characters")
    if not username.isidentifier():
        raise ValueError("username: letters, digits and _ only")
    salt = secrets.token_bytes(16)
    with closing(_connect(db)) as con:
        con.execute("INSERT INTO users (username, role, salt, pw_hash, created) VALUES (?,?,?,?,?)",
                    (username, role, salt, _hash(password, salt), datetime.now().isoformat(timespec="seconds")))
        con.commit()


def login(username: str, password: str, db=None) -> dict | None:
    """Returns {'token', 'username', 'role', 'expires'} or None. Locked accounts always fail."""
    now = datetime.now()
    with closing(_connect(db)) as con:
        row = con.execute("SELECT role, salt, pw_hash, failed, locked_until, active FROM users WHERE username=?",
                          (username,)).fetchone()
        if row is None:
            _hash(password, b"0" * 16)                       # same work either way (no user enumeration by timing)
            return None
        role, salt, pw_hash, failed, locked_until, active = row
        if not active or (locked_until and datetime.fromisoformat(locked_until) > now):
            return None
        if not hmac.compare_digest(_hash(password, salt), pw_hash):
            failed += 1
            lock = (now + timedelta(minutes=LOCK_MINUTES)).isoformat() if failed >= MAX_FAILS else None
            con.execute("UPDATE users SET failed=?, locked_until=? WHERE username=?",
                        (0 if lock else failed, lock, username))
            con.commit()
            audit(username, "login_failed", "locked" if lock else f"attempt {failed}", db, con)
            return None
        token = secrets.token_urlsafe(32)
        expires = (now + timedelta(hours=SESSION_HOURS)).isoformat(timespec="seconds")
        con.execute("UPDATE users SET failed=0, locked_until=NULL WHERE username=?", (username,))
        con.execute("INSERT INTO sessions VALUES (?,?,?)", (token, username, expires))
        con.commit()
        audit(username, "login", "", db, con)
    return {"token": token, "username": username, "role": role, "expires": expires}


def verify(token: str, db=None) -> dict | None:
    with closing(_connect(db)) as con:
        row = con.execute("SELECT s.username, u.role, s.expires FROM sessions s JOIN users u USING (username) "
                          "WHERE s.token=? AND u.active=1", (token,)).fetchone()
    if row is None or datetime.fromisoformat(row[2]) < datetime.now():
        return None
    return {"username": row[0], "role": row[1]}


def logout(token: str, db=None):
    with closing(_connect(db)) as con:
        con.execute("DELETE FROM sessions WHERE token=?", (token,))
        con.commit()


def has_role(user: dict, minimum: str) -> bool:
    return ROLES.get(user["role"], 0) >= ROLES[minimum]


def audit(username: str, action: str, detail: str, db=None, con=None):
    own = con is None
    con = con or _connect(db)
    try:
        con.execute("INSERT INTO audit (at, username, action, detail) VALUES (?,?,?,?)",
                    (datetime.now().isoformat(timespec="seconds"), username, action, detail))
        con.commit()
    finally:
        if own:
            con.close()


def users(db=None) -> list:
    with closing(_connect(db)) as con:
        return [dict(zip(["username", "role", "created", "active"], r))
                for r in con.execute("SELECT username, role, created, active FROM users ORDER BY username")]


def audit_log(limit: int = 200, db=None) -> list:
    with closing(_connect(db)) as con:
        return [dict(zip(["at", "username", "action", "detail"], r)) for r in
                con.execute("SELECT at, username, action, detail FROM audit ORDER BY id DESC LIMIT ?", (limit,))]
