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
from src.config import destination_info, load_config
from src.control import booking
from src.control.slots import build_control
from src.live.refresh import PUBLISHED, LiveContext, refresh

CFG = load_config()
TRAILS = list(CFG["area"]["trail_names"])
ADVISORY = CFG["control"].get("booking_mode", "required") == "advisory"   # pilgrimage site: no tickets
TrailName = Literal[tuple(TRAILS)]
Slot = Field(pattern=r"^\d{2}:\d{2}$")

app = FastAPI(title=f"{CFG['area']['name']} – Trail crowd forecasting and crowd control (Component 4)", version="1.0")
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
    return {k: v for k, v in s.items() if k != "alerts"} | {
        "park": CFG["park"], "site": CFG["area"]["name"], "booking_mode": "advisory" if ADVISORY else "required"}


@app.get("/destination", tags=["public"])
def destination():
    """What the trip planner shows for this park (summary, best time, getting there, trails)."""
    return destination_info(CFG)


def require_booking():
    if ADVISORY:
        raise HTTPException(400, "This site uses recommended start times, not bookings: see /advisory/{day}")


@app.get("/advisory/{day}", tags=["public"])
def advisory(day: date):
    """Recommended start times per route, expected wait at the summit and halfway release rates (pilgrim sites)."""
    if not ADVISORY:
        raise HTTPException(400, "This site uses bookings: see /slots/{day}")
    days = published("advisory.json")["days"]
    if day.isoformat() not in days:
        raise HTTPException(400, "Choose a day from tomorrow up to 90 days ahead")
    return {"day": day.isoformat()} | days[day.isoformat()]


@app.get("/trails", tags=["public"])
def trails():
    seg = ctx().seg
    out = []
    for t in TRAILS:
        s = seg[seg.trail == t]
        out.append({"id": t, "name": CFG["area"]["trail_names"][t], "segments": int(len(s)),
                    "length_km": round(float(s.length_m.sum()) / 1000, 1),
                    "about": CFG["area"].get("trail_info", {}).get(t, "")})
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


def live_inputs(c: LiveContext, day: date) -> dict:
    """What the safe limit of a day depends on, today: rain (forecast or typical), ground wetness, conditions."""
    rain, rain_basis = c.rain_share(day)
    return {"rain_share": rain, "rain_basis": rain_basis, "wet": c.ground_wetness(day),
            "conditions": booking.conditions(day.isoformat())}


def _plan(c: LiveContext, day: date, inputs: dict) -> dict:
    return c.planner.day(c.today.isoformat(), day.isoformat(), rain_share=inputs["rain_share"],
                         wetness=inputs["wet"]["wetness"],
                         conditions={t: v["factor"] for t, v in inputs["conditions"].items()})


@app.get("/plan/{day}", tags=["public"])
def plan_day(day: date):
    """Expected crowd for a day (2-90 days ahead) with suggestions to avoid it."""
    c = ctx()
    if not c.today + timedelta(days=2) <= day <= c.today + timedelta(days=CFG["live"]["horizon_days"]):
        raise HTTPException(400, "Choose a day from 2 to 90 days ahead (tomorrow: /forecast/tomorrow)")
    p = _plan(c, day, live_inputs(c, day))
    p.pop("hourly", None)
    p["capacity"] = {"trails": p["capacity"]["trails"]}
    return p


@app.get("/capacity/{day}", tags=["public"])
def day_capacity(day: date):
    """Safe limit per trail for a day (1-90 days ahead): the Cifuentes carrying capacity for that day's weather,
    ground wetness, forecast crowding and reported trail condition, with what lowered it."""
    c = ctx()
    if not c.today + timedelta(days=1) <= day <= c.today + timedelta(days=CFG["live"]["horizon_days"]):
        raise HTTPException(400, "Choose a day from tomorrow up to 90 days ahead")
    inputs = live_inputs(c, day)
    cap = _plan(c, day, inputs)["capacity"]
    from src.capacity.cifuentes import FACTOR_LABELS
    out = []
    for t, v in cap["trails"].items():
        f = v["factors"]
        out.append({
            "trail": t, "name": v["name"], "expected_visitors": v["expected_visitors"],
            "safe_limit": v["recommended_daily_quota"], "over_limit": v["expected_visitors"] > v["recommended_daily_quota"],
            "condition": inputs["conditions"].get(t, {"level": "good", "note": "", "factor": 0.0}),
            # what each factor removes from the capacity (the factors multiply); crowding is the forecast's effect
            "factors": [{"key": k, "label": FACTOR_LABELS.get(k, k), "pct": round(100 * float(f[k]))}
                        for k in ("precipitation", "wet_ground", "condition", "erodibility", "accessibility", "social")
                        if k in f] + [{
                            "key": "crowding", "label": "expected crowding at the busiest place",
                            "pct": round(100 * (1 - v["recommended_daily_quota"] / max(v["classic_cifuentes_quota"], 1)))}],
        })
    return {"day": day.isoformat(), "rain_share_open_hours": round(inputs["rain_share"], 3),
            "weather_basis": inputs["rain_basis"], "ground": inputs["wet"],
            "total_safe_limit": cap["recommended_daily_quota"], "total_expected": cap["expected_visitors"],
            "trails": out}


@app.get("/conditions/{day}", tags=["public"])
def trail_conditions(day: date):
    """Trail conditions reported by officers for a day (trails not listed are in good condition)."""
    return {"day": day.isoformat(), "levels": booking.condition_levels(), "trails": booking.conditions(day.isoformat())}


@app.get("/slots/{day}", tags=["public"])
def slots(day: date):
    require_booking()
    d = day.isoformat()
    av, sup = booking.availability(d), booking.supply(d)
    pub = booking._published(d)
    closed = booking.closed_slots(d)
    shut = {t for t, v in booking.conditions(d).items() if v["factor"] >= 1}      # reported closed
    return {"day": d, "basis": pub.basis.iloc[0] if pub is not None else "provisional (typical weather)",
            "walk_in_share": build_control().c["walk_in_share"],
            "slots": [{"slot": s, "trail": t, "places_left": int(av.loc[s, t]), "bookable": int(sup.loc[s, t]),
                       "closed": (t, s) in closed or t in shut} for s in av.index for t in av.columns]}


class BookingIn(BaseModel):
    day: date
    trail: TrailName
    slot: str = Slot
    group_size: int = Field(ge=1, le=20)


@app.post("/bookings", tags=["public"], status_code=201)
def create_booking(body: BookingIn):
    require_booking()
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


class CheckpointIn(BaseModel):
    route: TrailName
    count: int = Field(ge=0, le=5000)
    at: datetime | None = None


@app.post("/checkpoints", tags=["ranger"])
def record_checkpoint(body: CheckpointIn, user: dict = Depends(role("ranger"))):
    """Halfway check: people who passed the checkpoint (e.g. in the last 10 minutes)."""
    at = when(body.at)
    booking.record_checkpoint(at.date().isoformat(), body.route, body.count, user["username"], at)
    auth.audit(user["username"], "checkpoint", f"{body.route} {body.count} at {at:%H:%M}")
    return checkpoint_status(at.date(), at.time().replace(second=0, microsecond=0), user)


NIGHT_START_H = CFG["control"].get("night_start_h", 24)        # pilgrim sites: evenings belong to the next night


def night_of(at: datetime) -> tuple[date, int]:
    """The night (named after its sunrise date) a moment belongs to, and its minute in that night
    (negative = the evening before): 22:00 on 24 Dec is minute -120 of the night of 25 Dec."""
    m = at.hour * 60 + at.minute
    if at.hour >= NIGHT_START_H:
        return at.date() + timedelta(days=1), m - 1440
    return at.date(), m


def night_passes(night: date) -> "pd.DataFrame":
    """Halfway counts of one night: its own date before the evening, plus the evening before (shifted < 0)."""
    import pandas as pd
    cut = NIGHT_START_H * 60
    own = booking.checkpoint_passes(night.isoformat())
    eve = booking.checkpoint_passes((night - timedelta(days=1)).isoformat())
    eve = eve[eve.time_min >= cut].assign(time_min=lambda d: d.time_min - 1440)
    return pd.concat([eve, own[own.time_min < cut]], ignore_index=True).sort_values("time_min", kind="stable")


@app.get("/checkpoints/{day}", tags=["ranger"])
def checkpoint_status(day: date, at: time | None = None, user: dict = Depends(role("ranger"))):
    """Summit queue now and ahead from the halfway counts, and what to do at each checkpoint. Times from
    `night_start_h` (18:00) count for the next night (pilgrims climbing for the next sunrise)."""
    if not ADVISORY:
        raise HTTPException(400, "Halfway checks are used at pilgrimage sites")
    from src.control.advisory import build_advisory
    adv = build_advisory()
    night, now_min = night_of(when(datetime.combine(day, at) if at else None))
    outlook_days = {d["date"]: d for d in published("outlook.json")["days"]}
    if night.isoformat() in outlook_days:                       # walking times at tonight's expected crowd
        adv.use_crowd(outlook_days[night.isoformat()]["visitors"]["p50"])
    passes = night_passes(night)
    live = adv.nowcast(passes, now_min)
    days = published("advisory.json")["days"]
    rates = days.get(night.isoformat(), {}).get("halfway") or adv.release_rates(adv.demand(
        {t: 1.0 for t in adv.trails}))
    high = days.get(night.isoformat(), {}).get("high_case", {}).get("halfway", {})
    counted = passes.groupby("route")["count"].sum().to_dict() if len(passes) else {}
    last = passes.groupby("route")["time_min"].max().to_dict() if len(passes) else {}
    hhmm = lambda m: f"{int(m) % 1440 // 60:02d}:{int(m) % 60:02d}"
    log = [{"route": r.route, "name": CFG["area"]["trail_names"][r.route], "time": hhmm(r.time_min),
            "count": int(r.count), "by": r.counted_by} for r in passes.iloc[::-1].head(30).itertuples()]
    return {"day": night.isoformat(), **live, "log": log,
            "checkpoints": [{"route": t, "name": CFG["area"]["trail_names"][t],
                             "release_per_10_min": rates[t]["release_per_10_min"] if live["hold"] else None,
                             "walk_to_summit_min": rates[t]["walk_to_summit_min"],
                             "planned_hold": rates[t].get("hold_windows", []),
                             "planned_hold_if_busy": high.get(t, {}).get("hold_windows", []),
                             "last_count_at": hhmm(last[t]) if t in last else None,
                             "counted_today": int(counted.get(t, 0))} for t in TRAILS]}


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


class ConditionIn(BaseModel):
    trail: TrailName
    day_from: date
    day_to: date
    level: Literal["good", "muddy", "partly_closed", "closed"]
    note: str = Field(default="", max_length=200)


@app.post("/admin/conditions", tags=["officer"])
def set_condition(body: ConditionIn, user: dict = Depends(role("officer"))):
    """Report a trail's condition for a range of days ('good' clears it). The safe limit and the tickets of those
    days change at once; bookings already made are kept and listed as alerts if now over the limit."""
    if body.day_to < body.day_from or (body.day_to - body.day_from).days > 30:
        raise HTTPException(400, "Choose 1 to 31 days")
    alerts = booking.set_condition(body.day_from.isoformat(), body.day_to.isoformat(), body.trail, body.level,
                                   body.note, user["username"])
    auth.audit(user["username"], "condition", f"{body.trail} {body.level} {body.day_from}..{body.day_to}: {body.note}")
    return {"alerts": alerts}


@app.get("/admin/bookings/{day}", tags=["officer"])
def day_bookings(day: date, user: dict = Depends(role("officer"))):
    return booking.bookings_for(day.isoformat()).to_dict(orient="records")


@app.get("/admin/alerts", tags=["officer"])
def alerts(user: dict = Depends(role("officer"))):
    return published("status.json").get("alerts", [])


@app.get("/admin/season", tags=["officer"])
def season(user: dict = Depends(role("officer"))):
    """Pilgrim sites: every night of the outlook with the expected climbers, the summit queue and when the halfway
    checks will be needed (for planning staff). checks: needed (likely case) | standby (only if as busy as the
    P90 high case) | none."""
    if not ADVISORY:
        raise HTTPException(400, "The season plan is for pilgrimage sites")
    adv, out = published("advisory.json")["days"], []
    for d in published("outlook.json")["days"]:
        a = adv.get(d["date"])
        if a is None:
            continue
        s, h = a["summit"], a.get("high_case", {}).get("summit", {})
        out.append({"date": d["date"], "crowd_level": d["crowd_level"], "visitors": d["visitors"],
                    "peak_queue_people": s["peak_queue_people"], "peak_wait_min": s["peak_wait_min"],
                    "peak_at": s["peak_at"], "hold_windows": s.get("hold_windows", []),
                    "high_peak_wait_min": h.get("peak_wait_min", 0), "high_hold_windows": h.get("hold_windows", []),
                    "checks": "needed" if s.get("hold_windows") else "standby" if h.get("hold_windows") else "none"})
    return {"limit_min": CFG["control"].get("queue_limit_min", 20), "days": out}


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
