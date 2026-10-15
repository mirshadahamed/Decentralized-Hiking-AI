"""Component 4 API: live forecasts, slot booking and staff operations (live_and_ux_plan.md, phase 2).

    .venv\\Scripts\\python.exe -m uvicorn src.api.app:app --port 8000      (docs at http://localhost:8000/docs)

Public (visitors, Module 3): outlook, plan for a day with suggestions, slots, bookings by code.
Staff (bearer token, role checked on the server for every call):
  ranger  : check-in, walk-in sales, live traffic lights
  officer : + closures, bookings list, alerts, refresh
  admin   : + user list, audit log
Reads the files published by `python -m src.live.refresh`; no personal visitor data is stored (NFR5).
"""
import json
import threading
from datetime import date, datetime, time, timedelta
from typing import Literal

import numpy as np
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.api import auth
from src.config import load_config
from src.control import booking
from src.control.slots import build_control
from src.live.refresh import PUBLISHED, LiveContext, refresh

CFG = load_config()
TRAILS = list(CFG["area"]["trail_names"])
TrailName = Literal[tuple(TRAILS)]
Slot = Field(pattern=r"^\d{2}:\d{2}$")

app = FastAPI(title="Horton Plains – Trail crowd forecasting and entry control (Component 4)", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=CFG["api"]["cors_origins"], allow_methods=["*"], allow_headers=["*"])

_ctx, _lock = None, threading.Lock()


def ctx() -> LiveContext:
    """Live state from the last refresh (loaded once; reloaded after /admin/refresh)."""
    global _ctx
    with _lock:
        if _ctx is None:
            try:
                _ctx = LiveContext(rebuild=False)
            except FileNotFoundError:
                raise HTTPException(503, "No live data yet: run python -m src.live.refresh")
        return _ctx


def published(name: str) -> dict:
    p = PUBLISHED / name
    if not p.exists():
        raise HTTPException(503, "No live data yet: run python -m src.live.refresh")
    return json.loads(p.read_text(encoding="utf-8"))


# ---------- auth ----------
def current_user(authorization: str = Header(default="")) -> dict:
    token = authorization.removeprefix("Bearer ").strip()
    user = auth.verify(token) if token else None
    if user is None:
        raise HTTPException(401, "Login required", headers={"WWW-Authenticate": "Bearer"})
    user["token"] = token
    return user


def role(minimum: str):
    def dep(user: dict = Depends(current_user)) -> dict:
        if not auth.has_role(user, minimum):
            raise HTTPException(403, f"Needs role '{minimum}' or higher")
        return user
    return dep


def when(at: datetime | None) -> datetime:
    if at is not None and not CFG["api"]["allow_time_override"]:
        raise HTTPException(400, "Time override is disabled")
    return at or datetime.now()


class LoginIn(BaseModel):
    username: str
    password: str


@app.post("/auth/login", tags=["staff"])
def login(body: LoginIn):
    s = auth.login(body.username, body.password)
    if s is None:
        raise HTTPException(401, "Wrong username or password, or account locked")
    return s


@app.post("/auth/logout", tags=["staff"])
def logout(user: dict = Depends(current_user)):
    auth.logout(user["token"])
    return {"ok": True}


@app.get("/auth/me", tags=["staff"])
def me(user: dict = Depends(current_user)):
    return {"username": user["username"], "role": user["role"]}


# ---------- public ----------
@app.get("/health", tags=["public"])
def health():
    return {"ok": True}


@app.get("/status", tags=["public"])
def status():
    s = published("status.json")
    return {k: v for k, v in s.items() if k != "alerts"}


@app.get("/trails", tags=["public"])
def trails():
    from src.planning.planner import TRAIL_INFO
    seg = ctx().seg
    out = []
    for t in TRAILS:
        s = seg[seg.trail == t]
        out.append({"id": t, "name": CFG["area"]["trail_names"][t], "segments": int(len(s)),
                    "length_km": round(float(s.length_m.sum()) / 1000, 1), "about": TRAIL_INFO.get(t, "Main loop: "
                    "Mini World's End, World's End and Baker's Falls; about 3.5 hours")})
    return out


@app.get("/trails/geometry", tags=["public"])
def geometry():
    """Segments as GeoJSON (for maps)."""
    return json.loads(ctx().seg.to_json())


@app.get("/outlook", tags=["public"])
def outlook():
    return published("outlook.json")


@app.get("/forecast/tomorrow", tags=["public"])
def forecast_tomorrow():
    return published("forecast_tomorrow.json")


@app.get("/plan/{day}", tags=["public"])
def plan_day(day: date):
    """Expected crowd for a day (2-90 days ahead) with suggestions to avoid it."""
    c = ctx()
    if not c.today + timedelta(days=2) <= day <= c.today + timedelta(days=CFG["live"]["horizon_days"]):
        raise HTTPException(400, "Choose a day from 2 to 90 days ahead (tomorrow: /forecast/tomorrow)")
    p = c.planner.day(c.today.isoformat(), day.isoformat())
    p.pop("hourly", None)
    p["capacity"] = {"trails": p["capacity"]["trails"]}
    return p


@app.get("/slots/{day}", tags=["public"])
def slots(day: date):
    d = day.isoformat()
    av, sup = booking.availability(d), booking.supply(d)
    pub = booking._published(d)
    closed = booking.closed_slots(d)
    return {"day": d, "basis": pub.basis.iloc[0] if pub is not None else "provisional (typical weather)",
            "walk_in_share": build_control().c["walk_in_share"],
            "slots": [{"slot": s, "trail": t, "places_left": int(av.loc[s, t]), "bookable": int(sup.loc[s, t]),
                       "closed": (t, s) in closed} for s in av.index for t in av.columns]}


class BookingIn(BaseModel):
    day: date
    trail: TrailName
    slot: str = Slot
    group_size: int = Field(ge=1, le=20)


@app.post("/bookings", tags=["public"], status_code=201)
def create_booking(body: BookingIn):
    try:
        code = booking.book(body.day.isoformat(), body.trail, body.slot, body.group_size, today=ctx().today.isoformat())
    except booking.SlotFull as e:
        return JSONResponse(status_code=409, content={"detail": str(e), "alternatives": e.alternatives})
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"code": code, **booking.bookings_for_code(code), "window_minutes": build_control().c["slot_window_min"]}


@app.get("/bookings/{code}", tags=["public"])
def get_booking(code: str):
    b = booking.bookings_for_code(code)
    if b is None:
        raise HTTPException(404, "Unknown code")
    return {"code": code.strip().upper(), **b}


@app.delete("/bookings/{code}", tags=["public"])
def cancel_booking(code: str):
    if not booking.cancel(code.strip().upper()):
        raise HTTPException(404, "Unknown code or not cancellable")
    return {"ok": True}


# ---------- ranger ----------
class CheckInIn(BaseModel):
    code: str
    at: datetime | None = None


@app.post("/checkin", tags=["ranger"])
def checkin(body: CheckInIn, user: dict = Depends(role("ranger"))):
    r = booking.check_in(body.code, when(body.at))
    auth.audit(user["username"], "checkin", f"{body.code.upper()} {r['reason']}")
    return r


class WalkInIn(BaseModel):
    day: date
    trail: TrailName
    slot: str = Slot
    group_size: int = Field(ge=1, le=20)
    at: datetime | None = None


@app.get("/walkins/{day}", tags=["ranger"])
def walkins_left(day: date, user: dict = Depends(role("ranger"))):
    w = booking.walk_in_left(day.isoformat())
    return {"day": day.isoformat(), "slots": [{"slot": s, "trail": t, "left": int(w.loc[s, t])}
                                              for s in w.index for t in w.columns]}


@app.post("/walkins", tags=["ranger"])
def sell(body: WalkInIn, user: dict = Depends(role("ranger"))):
    try:
        left = booking.sell_walk_in(body.day.isoformat(), body.trail, body.slot, body.group_size,
                                    user["username"], now=when(body.at))
    except booking.SlotFull as e:
        return JSONResponse(status_code=409, content={"detail": str(e), "alternatives": e.alternatives})
    auth.audit(user["username"], "walk_in", f"{body.day} {body.trail} {body.slot} x{body.group_size}")
    return {"left": left}


@app.get("/live/{day}", tags=["ranger"])
def live_status(day: date, at: time | None = None, user: dict = Depends(role("ranger"))):
    """Traffic light per segment from the people who went through the gate (no trail sensors)."""
    ec = build_control()
    now = when(datetime.combine(day, at) if at else None)
    pub = booking._published(day.isoformat())
    rain = float(pub.rain_share.iloc[0]) if pub is not None else booking.typical_rain_share(day.isoformat())
    occ = ec.nowcast(booking.entries(day.isoformat()), now.hour * 60 + now.minute, rain)
    cap = ec.capacity(rain)
    seg = ctx().seg
    out = []
    for i, (o, c) in enumerate(zip(occ, cap)):
        util = o / c if np.isfinite(c) else 0.0
        light = "red" if util > 1 else "amber" if util >= 0.8 else "green"
        out.append({"seg_id": int(seg.seg_id.iloc[i]), "trail": seg.trail.iloc[i], "poi": seg.poi.iloc[i] or None,
                    "people": round(float(o), 1), "capacity": None if not np.isfinite(c) else round(float(c), 1),
                    "light": light,
                    "action": {"green": None, "amber": "Offer a later slot or another trail at the gate",
                               "red": "Pause entries to this trail for the next slot; send a ranger"}[light]})
    return {"day": day.isoformat(), "time": now.strftime("%H:%M"), "segments": out}


# ---------- officer ----------
class ClosureIn(BaseModel):
    day: date
    trail: TrailName
    slot_from: str = Slot
    slot_to: str = Slot
    reason: str = Field(min_length=3, max_length=200)


@app.post("/admin/closures", tags=["officer"])
def close(body: ClosureIn, user: dict = Depends(role("officer"))):
    alerts = booking.close(body.day.isoformat(), body.trail, body.slot_from, body.slot_to, body.reason,
                           user["username"])
    auth.audit(user["username"], "closure", f"{body.day} {body.trail} {body.slot_from}-{body.slot_to}: {body.reason}")
    return {"alerts": alerts}


@app.get("/admin/bookings/{day}", tags=["officer"])
def day_bookings(day: date, user: dict = Depends(role("officer"))):
    return booking.bookings_for(day.isoformat()).to_dict(orient="records")


@app.get("/admin/alerts", tags=["officer"])
def alerts(user: dict = Depends(role("officer"))):
    return published("status.json").get("alerts", [])


@app.post("/admin/refresh", tags=["officer"])
def admin_refresh(user: dict = Depends(role("officer"))):
    """Run the daily refresh now (about a minute) and reload the live state."""
    global _ctx
    s = refresh()
    with _lock:
        _ctx = None
    auth.audit(user["username"], "refresh", s["today"])
    return {k: v for k, v in s.items() if k != "alerts"} | {"alerts": len(s["alerts"])}


# ---------- admin ----------
@app.get("/admin/users", tags=["admin"])
def list_users(user: dict = Depends(role("admin"))):
    return auth.users()


@app.get("/admin/audit", tags=["admin"])
def audit_log(limit: int = 200, user: dict = Depends(role("admin"))):
    return auth.audit_log(limit)
