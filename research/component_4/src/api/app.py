"""Component 4 API: live forecasts, slot booking and staff operations (docs/archive/live_and_ux_plan.md, phase 2).

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
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from src.api import auth
from src.config import destination_info, load_config
from src.control import booking, modes
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
                raise HTTPException(503, "No live data yet: run python -m src.live.refresh") from None
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
        "park": CFG["park"], "site": CFG["area"]["name"], "booking_mode": "advisory" if ADVISORY else "required",
        "sightings": bool(CFG["simulator"].get("sightings")),
        "walk_register": bool(CFG["control"].get("walk_register", False)),
        "trail_modes": modes.trail_modes(CFG), "modes": modes.park_modes(CFG)}


@app.get("/destination", tags=["public"])
def destination():
    """What the trip planner shows for this park (summary, best time, getting there, trails)."""
    return destination_info(CFG)


def require_ticketed(trail: str):
    """Slot tickets and start times are only for trails in a ticketed mode (src/control/modes.py)."""
    if not modes.ticketed(CFG, trail):
        m = modes.trail_modes(CFG).get(trail)
        raise HTTPException(400, f"{CFG['area']['trail_names'].get(trail, trail)} needs no slot ticket ({m})")


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


@app.get("/edge/pack", tags=["public"])
def edge_pack():
    """Trained model + inputs for tomorrow (schema c4-edge-1): phones download it once and run the ST-GNN
    themselves, offline (src/edge/pack.py)."""
    return published("edge_pack.json")


@app.get("/module3/feed", tags=["public"])
def module3_feed():
    """Data contract for Module 3 and the authority dashboard (schema c4-module3-feed-1,
    docs/schema/c4_module3_feed.schema.json): tomorrow's people per segment and hour, safe capacity, hours to avoid."""
    from src.serve.module3 import module3_feed as feed
    return feed(published("forecast_tomorrow.json"), CFG)


def live_inputs(c: LiveContext, day: date) -> dict:
    """What the safe limit of a day depends on, today: rain (forecast or typical), ground wetness, conditions."""
    rain, rain_basis = c.rain_share(day)
    return {"rain_share": rain, "rain_basis": rain_basis, "wet": c.ground_wetness(day),
            "conditions": booking.conditions(day.isoformat())}


def _plan(c: LiveContext, day: date, inputs: dict) -> dict:
    return c.planner.day(c.today.isoformat(), day.isoformat(), rain_share=inputs["rain_share"],
                         wetness=inputs["wet"]["wetness"],
                         conditions={t: v["factor"] for t, v in inputs["conditions"].items()})


@app.get("/weather/{day}", tags=["public"])
def weather_day(day: date):
    """The weather of a date (hourly and for the open hours) and what it does to the crowd and the safe limit.
    basis: observed (past), forecast (up to 16 days ahead) or typical (later; with the range of past years)."""
    from src.serve.weather_day import day_weather
    try:
        return day_weather(ctx(), day)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None


@app.get("/stages/{day}", tags=["public"])
def stages(day: date):
    """P4: stage advice on a long open-access trail (Pekoe): how busy each stage gets, where and when, and when to
    start. Only for parks built from stages (area.stage_relations)."""
    from src.serve.stages import stage_outlook
    if not modes.trails_with(CFG, "open_stages"):
        raise HTTPException(404, "This site has no stages")
    c = ctx()
    if not c.today + timedelta(days=1) <= day <= c.today + timedelta(days=CFG["live"]["horizon_days"]):
        raise HTTPException(400, "Choose a day from tomorrow up to 90 days ahead")
    hourly = np.array(_plan(c, day, live_inputs(c, day))["hourly"]["p50"])
    weather = None
    if (day - c.today).days < CFG["live"]["forecast_days"]:
        try:
            from src.live.stage_weather import stage_weather
            weather = {t: v.get(day.isoformat()) for t, v in stage_weather(CFG, c.seg, c.today).items()}
        except Exception:                                    # no connection: the park's weather still applies
            weather = None
    out = stage_outlook(CFG, c.seg, hourly, day.isoformat(), weather)
    keep = set(modes.trails_with(CFG, "open_stages"))
    return out | {"stages": [x for x in out["stages"] if x["stage"] in keep]}


# ---------- Knuckles mechanisms: guided permits (K4/K5), open viewpoints (K6), campsites (K7) ----------
def _require_mode(mode: str):
    if not modes.trails_with(CFG, mode) and not (mode == "campsite" and CFG["control"].get("campsites")):
        raise HTTPException(404, f"This site has no {mode.replace('_', ' ')} trails")


def _permit_plan(day: date) -> dict:
    from src.control.permits import day_plan, settings
    c = ctx()
    inputs = live_inputs(c, day)
    trails = _plan(c, day, inputs)["capacity"]["trails"]
    g = settings(CFG).get("mean_group", 6)
    cap = {t: float(trails[t]["recommended_daily_quota"]) for t in settings(CFG)["treks"] if t in trails}
    req = {t: float(trails[t]["expected_visitors"]) / g for t in settings(CFG)["treks"] if t in trails}
    return day_plan(CFG, day.isoformat(), cap, req) | {"rain_share_open_hours": round(inputs["rain_share"], 3)}


@app.get("/permits/{day}", tags=["public"])
def permits_day(day: date):
    """Guided treks: groups allowed per trek (LP over the trail caps and the guides on duty), issued and left."""
    _require_mode("guided_permit")
    c = ctx()
    if not c.today <= day <= c.today + timedelta(days=CFG["live"]["horizon_days"]):
        raise HTTPException(400, "Choose a day from today up to 90 days ahead")
    return _permit_plan(day)


class PermitIn(BaseModel):
    day: date
    trail: TrailName
    group_size: int = Field(ge=1, le=20)


@app.post("/permits", tags=["public"], status_code=201)
def request_permit(body: PermitIn):
    from src.control.permits import PermitFull, request
    _require_mode("guided_permit")
    plan = _permit_plan(body.day)
    near = [body.day + timedelta(days=k) for k in (1, 2, -1) if body.day + timedelta(days=k) >= ctx().today]
    free = [d.isoformat() for d in near
            if next((x for x in _permit_plan(d)["treks"] if x["trail"] == body.trail), {}).get("groups_left", 0) > 0]
    try:
        return request(CFG, body.day.isoformat(), body.trail, body.group_size, plan, other_days=free)
    except PermitFull as e:
        return JSONResponse(status_code=409, content={"detail": str(e), "alternatives": e.alternatives})
    except ValueError as e:
        raise HTTPException(400, str(e)) from None


class PermitTimeIn(BaseModel):
    at: datetime | None = None


@app.post("/permits/{code}/out", tags=["ranger"])
def permit_out(code: str, body: PermitTimeIn, user: dict = Depends(role("ranger"))):
    from src.control.permits import check_out
    now = when(body.at)
    rain = _day_expectation(now.date())[0]
    try:
        r = check_out(CFG, code, now, rain)
    except KeyError as e:
        raise HTTPException(404, str(e)) from None
    except ValueError as e:
        raise HTTPException(409, str(e)) from None
    auth.audit(user["username"], "permit_out", code.upper())
    return r


@app.post("/permits/{code}/back", tags=["ranger"])
def permit_back(code: str, body: PermitTimeIn, user: dict = Depends(role("ranger"))):
    from src.control.permits import check_back
    try:
        r = check_back(code, when(body.at))
    except KeyError as e:
        raise HTTPException(404, str(e)) from None
    except ValueError as e:
        raise HTTPException(409, str(e)) from None
    auth.audit(user["username"], "permit_back", code.upper())
    return r


class WalkOutIn(BaseModel):
    trail: TrailName
    group_size: int = Field(ge=1, le=40)
    at: datetime | None = None


@app.post("/walks/out", tags=["ranger"])
def walk_out(body: WalkOutIn, user: dict = Depends(role("ranger"))):
    """§6.2.7 safety, any park with control.walk_register: a group starts a long walk; it is due back after the
    trail's walking time and shows as overdue like a guided trek."""
    from src.control.permits import register_walk
    if not CFG["control"].get("walk_register"):
        raise HTTPException(404, "This site has no walk register")
    now = when(body.at)
    try:
        r = register_walk(CFG, body.trail, body.group_size, now, _day_expectation(now.date())[0])
    except KeyError as e:
        raise HTTPException(404, str(e)) from None
    auth.audit(user["username"], "walk_out", f"{r['code']} {body.trail} x{body.group_size}")
    return r


@app.get("/overdue/{day}", tags=["ranger"])
def overdue_groups(day: date, at: time | None = None, user: dict = Depends(role("ranger"))):
    """K5: guided groups still out past their expected return + margin (shorter in rain)."""
    from src.control.permits import overdue
    if not (modes.trails_with(CFG, "guided_permit") or CFG["control"].get("walk_register")):
        raise HTTPException(404, "This site has no guided treks or walk register")
    now = when(datetime.combine(day, at) if at else None)
    return overdue(CFG, day.isoformat(), now, _day_expectation(day)[0])


@app.get("/viewpoints/{day}", tags=["public"])
def viewpoints(day: date):
    """K6: open viewpoints - busy hours, parking, when to come instead (advice; nobody is turned away)."""
    from src.serve.viewpoints import viewpoint_outlook
    _require_mode("open_viewpoint")
    c = ctx()
    if not c.today + timedelta(days=1) <= day <= c.today + timedelta(days=CFG["live"]["horizon_days"]):
        raise HTTPException(400, "Choose a day from tomorrow up to 90 days ahead")
    inputs = live_inputs(c, day)
    hourly = np.array(_plan(c, day, inputs)["hourly"]["p50"])
    return viewpoint_outlook(CFG, c.seg, hourly, modes.trails_with(CFG, "open_viewpoint"), day.isoformat(),
                             booking.conditions(day.isoformat()))


@app.get("/campsites/{night}", tags=["public"])
def campsites_night(night: date):
    from src.serve.viewpoints import campsites
    _require_mode("campsite")
    return campsites(CFG, night.isoformat())


class CampIn(BaseModel):
    night: date
    site: str = Field(max_length=40)
    pitches: int = Field(ge=1, le=10)
    people: int = Field(ge=1, le=40)


@app.post("/campsites", tags=["public"], status_code=201)
def book_campsite(body: CampIn):
    from src.serve.viewpoints import book_campsite as book
    _require_mode("campsite")
    try:
        return book(CFG, body.night.isoformat(), body.site, body.pitches, body.people)
    except KeyError as e:
        raise HTTPException(404, str(e)) from None
    except ValueError as e:
        raise HTTPException(409, str(e)) from None


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
                       "closed": (t, s) in closed or t in shut} for s in av.index for t in av.columns
                      if modes.ticketed(CFG, t)]}                    # other modes need no slot ticket


class BookingIn(BaseModel):
    day: date
    trail: TrailName
    slot: str = Slot
    group_size: int = Field(ge=1, le=20)


@app.post("/bookings", tags=["public"], status_code=201)
def create_booking(body: BookingIn):
    require_booking()
    require_ticketed(body.trail)
    try:
        code = booking.book(body.day.isoformat(), body.trail, body.slot, body.group_size, today=ctx().today.isoformat())
    except booking.SlotFull as e:
        return JSONResponse(status_code=409, content={"detail": str(e), "alternatives": e.alternatives})
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"code": code, **with_trail_name(booking.bookings_for_code(code)),
            "window_minutes": build_control().c["slot_window_min"]}


@app.get("/bookings/{code}", tags=["public"])
def get_booking(code: str):
    b = booking.bookings_for_code(code)
    if b is None:
        raise HTTPException(404, "Unknown code")
    return {"code": code.strip().upper(), **with_trail_name(b)}


def with_trail_name(b: dict) -> dict:
    """A booking with its trail's name, so a ticket kept on the phone shows the right park's trail offline."""
    return b | {"trail_name": CFG["area"]["trail_names"].get(b["trail"], b["trail"])}


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


@app.post("/gate/queue", tags=["ranger"])
def gate_queue(body: CheckInIn, user: dict = Depends(role("ranger"))):
    """R7: scan a code at the back of the queue; the wait is measured at check-in."""
    return booking.queue_join(body.code, when(body.at))


@app.get("/admin/gate-waits/{day}", tags=["officer"])
def gate_waits(day: date, user: dict = Depends(role("officer"))):
    return booking.gate_waits(day.isoformat())


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


@app.get("/segments", tags=["public"])
def segment_list():
    """Sections of the trails (id, name, trail): what a ranger can count on."""
    from src.live.intraday import model_sections
    from src.serve.field_counts import segments
    try:
        used = model_sections(ctx())
    except HTTPException:
        used = set()
    return segments(CFG, used)


class SpotCountIn(BaseModel):
    day: date
    seg_id: int
    time: str = Slot
    count: int = Field(ge=0, le=5000)
    client_id: str | None = Field(default=None, max_length=64)


@app.post("/counts", tags=["ranger"], status_code=201)
def add_spot_count(body: SpotCountIn, user: dict = Depends(role("ranger"))):
    """A ranger's headcount on a section (the park's own sensor record, A4). Re-sending the same client_id
    (a count saved offline and synced later) stores it once."""
    from src.serve.field_counts import add_count
    h, m = (int(x) for x in body.time.split(":"))
    try:
        r = add_count(body.day.isoformat(), body.seg_id, h * 60 + m, body.count, user["username"], body.client_id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    auth.audit(user["username"], "spot_count", f"{body.day} seg {body.seg_id} {body.time} {body.count}")
    return r


@app.get("/counts/{day}", tags=["ranger"])
def day_counts(day: date, user: dict = Depends(role("ranger"))):
    from src.serve.field_counts import counts
    return {"day": day.isoformat(), "counts": counts(day.isoformat(), day.isoformat())}


class SightingIn(BaseModel):
    day: date
    seg_id: int
    time: str = Slot
    species: str = Field(default="leopard", max_length=40)
    client_id: str | None = Field(default=None, max_length=64)


class SightingEndIn(BaseModel):
    time: str = Slot


def require_sightings():
    if not CFG["simulator"].get("sightings"):
        raise HTTPException(400, "Sighting management is used at safari parks")


@app.post("/sightings", tags=["ranger"], status_code=201)
def report_sighting(body: SightingIn, user: dict = Depends(role("ranger"))):
    """A ranger / tracker reports an animal by the track (safari parks). Re-sending the same client_id stores it once."""
    from src.serve.sightings import add
    require_sightings()
    h, m = (int(x) for x in body.time.split(":"))
    try:
        sid = add(body.day.isoformat(), body.seg_id, h * 60 + m, body.species, user["username"], body.client_id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    auth.audit(user["username"], "sighting", f"{body.day} seg {body.seg_id} {body.time} {body.species}")
    return sighting_status(body.day, time(h, m), user) | {"id": sid}


@app.post("/sightings/{sighting_id}/end", tags=["ranger"])
def end_sighting(sighting_id: int, body: SightingEndIn, user: dict = Depends(role("ranger"))):
    from src.serve.sightings import end
    require_sightings()
    h, m = (int(x) for x in body.time.split(":"))
    if not end(sighting_id, h * 60 + m):
        raise HTTPException(404, "No open sighting with that id")
    auth.audit(user["username"], "sighting_end", f"{sighting_id} {body.time}")
    return {"ended": sighting_id}


@app.get("/sightings/{day}", tags=["ranger"])
def sighting_status(day: date, at: time | None = None, user: dict = Depends(role("ranger"))):
    """Active sightings with the rule (at most N jeeps stopped, M minutes each) and the jeeps near each one,
    estimated from the gate entries; when it is crowded, which circuits avoid it."""
    from src.serve.sightings import advice
    require_sightings()
    now = when(datetime.combine(day, at) if at else None)
    d = day.isoformat()
    pub = booking._published(d)
    rain = float(pub.rain_share.iloc[0]) if pub is not None else booking.typical_rain_share(d)
    return advice(CFG, d, now.hour * 60 + now.minute, rain)


@app.get("/admin/forecast-check", tags=["officer"])
def forecast_check(start: date, end: date, user: dict = Depends(role("officer"))):
    """Rangers' spot counts next to the day-ahead forecast of that section and hour: error, bias, share within
    30 %, over-capacity called right / false alarms (A4, field validation)."""
    from src.serve.field_counts import forecast_check as check
    if end < start or (end - start).days > 400:
        raise HTTPException(400, "Choose an end date after the start date, at most 400 days apart")
    return check(CFG, start.isoformat(), end.isoformat())


@app.get("/admin/day-report/{day}", tags=["officer"])
def day_report(day: date, format: Literal["json", "html"] = "json", user: dict = Depends(role("officer"))):
    """End-of-day report: entries per trail (tickets, walk-ins, start times, no-shows), the busiest gate hour,
    trail conditions reported and the forecast checked against the spot counts. format=html: printable page."""
    from src.serve.day_report import day_report as report, to_html
    r = report(CFG, day.isoformat())
    return Response(to_html(r), media_type="text/html") if format == "html" else r


@app.get("/admin/trends", tags=["officer"])
def trends(end: date | None = None, days: int = 28, user: dict = Depends(role("officer"))):
    """§6.2.10: week by week from the day reports - entries, no-shows, start times kept, forecast error (raw and
    corrected by counts), over capacity counted."""
    from src.serve.day_report import trends as t
    if not 7 <= days <= 120:
        raise HTTPException(400, "days must be 7-120")
    return t(CFG, (end or when(None).date()).isoformat(), days)


@app.get("/admin/recalibration", tags=["officer"])
def recalibration(day: date | None = None, user: dict = Depends(role("officer"))):
    """N2: how the rangers' counts correct the forecast - the factors for `day` (default tomorrow) and, for the 60
    days before it, the error of the raw and of the corrected forecast (factors from earlier days only)."""
    from src.live.recalibrate import backtest, factors
    d = day or ctx().today + timedelta(days=1)
    from src.control.start_times import on_time_share
    return {"factors": factors(CFG, d.isoformat()), "start_time_on_time": on_time_share(d.isoformat()),
            "backtest": backtest(CFG, (d - timedelta(days=60)).isoformat(), (d - timedelta(days=1)).isoformat())}


@app.get("/live/forecast/{day}", tags=["ranger"])
def live_forecast(day: date, at: time | None = None, user: dict = Depends(role("ranger"))):
    """A1: the rest of today per section - the morning forecast and the forecast updated with the rangers' spot
    counts so far (ST-GNN of the spot setting, RQ11b) - and the sections now expected over capacity."""
    from src.live.intraday import update_today
    from src.serve.field_counts import counts
    now = when(datetime.combine(day, at) if at else None)
    try:
        return update_today(ctx(), day, now.hour * 60 + now.minute, counts(day.isoformat(), day.isoformat()))
    except LookupError as e:
        raise HTTPException(503, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


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


@app.get("/gate/advice/{day}", tags=["ranger"])
def gate_advice(day: date, at: time | None = None, user: dict = Depends(role("ranger"))):
    """A3: sections expected over capacity in the next 2 hours (from the gate counts and the coming slots) and what
    to do at the gate: hold entries to a trail for N minutes, or send the next groups to a trail with room."""
    from src.control.gate_advice import gate_advice as advise
    require_booking()
    ec = build_control()
    now = when(datetime.combine(day, at) if at else None)
    d = day.isoformat()
    pub = booking._published(d)
    rain = float(pub.rain_share.iloc[0]) if pub is not None else booking.typical_rain_share(d)
    plan = None if pub is None else pub.pivot(index="slot", columns="trail", values="tickets")
    return advise(ec, booking.entries(d), now.hour * 60 + now.minute, rain, plan)


def _day_expectation(day: date) -> tuple[float, float]:
    """(rain share, expected visitors) the controller plans a day with."""
    d = day.isoformat()
    pub = booking._published(d)
    rain = float(pub.rain_share.iloc[0]) if pub is not None else booking.typical_rain_share(d)
    try:
        expected = float(ctx().planner.day((day - timedelta(days=1)).isoformat(), d)["visitors"]["p50"])
    except (ValueError, KeyError):
        expected = float(pub.tickets.sum()) if pub is not None else 0.0
    return rain, expected


@app.get("/start-time/{day}", tags=["public"])
def start_time(day: date, trail: TrailName, wanted: str = "07:00", size: int = 2):
    """N3: the earliest start at or after `wanted` that still has room in the controller's plan for the day, for
    visitors without a ticket. Coming at that time means going in first at the gate (RQ13b)."""
    from src.control.start_times import suggest
    if not 1 <= size <= 20:
        raise HTTPException(400, "Group size must be 1-20")
    require_ticketed(trail)
    try:
        return suggest(day.isoformat(), trail, wanted, size, *_day_expectation(day))
    except ValueError as e:
        raise HTTPException(400, str(e)) from None


class StartTimeIn(BaseModel):
    day: date
    trail: TrailName
    slot: str = Slot
    group_size: int = Field(ge=1, le=20)


@app.post("/start-time", tags=["public"], status_code=201)
def hold_start_time(body: StartTimeIn):
    """Hold a start time (counted against the plan); returns a short code to show at the gate."""
    from src.control.start_times import hold
    require_ticketed(body.trail)
    try:
        return hold(body.day.isoformat(), body.trail, body.slot, body.group_size, *_day_expectation(body.day))
    except ValueError as e:
        raise HTTPException(409, str(e)) from None


@app.get("/start-time/check/{code}", tags=["public"])
def recheck_start_time(code: str, at: datetime | None = None):
    """Before leaving on the day: is the held start still fine, given the gate counts so far and any incident?"""
    from src.control.start_times import held, recheck
    h = held(code)
    if h is None:
        raise HTTPException(404, "Unknown code")
    return recheck(code, when(at), *_day_expectation(date.fromisoformat(h["day"])))


class MoveIn(BaseModel):
    slot: str = Slot


@app.post("/start-time/{code}/move", tags=["public"])
def move_start_time(code: str, body: MoveIn):
    from src.control.start_times import move
    try:
        return move(code, body.slot)
    except KeyError as e:
        raise HTTPException(404, str(e)) from None


class IncidentIn(BaseModel):
    trail: TrailName
    level: Literal["good", "muddy", "partly_closed", "closed"]
    note: str = Field(default="", max_length=200)


@app.post("/incident", tags=["ranger"])
def report_incident(body: IncidentIn, user: dict = Depends(role("ranger"))):
    """A ranger reports what they see on a trail now (fallen tree, flooding, an injured walker...) for today.
    Gate control, start times and today's tickets use the lower capacity at once; 'good' clears it."""
    d = when(None).date().isoformat()
    alerts = booking.set_condition(d, d, body.trail, body.level, body.note, user["username"])
    auth.audit(user["username"], "incident", f"{body.trail} {body.level}: {body.note}")
    return {"day": d, "trail": body.trail, "level": body.level, "alerts": alerts}


@app.get("/gate/control/{day}", tags=["ranger"])
def gate_control(day: date, at: time | None = None, user: dict = Depends(role("ranger"))):
    """Closed-loop gate control (MPC, RQ13): how many more people each trail can take in the current slot, and the
    caps planned for the next slots - re-planned on every call from the gate counts so far and the day's forecast
    (corrected by how many came so far compared with what was expected)."""
    from src.control.mpc import MPCController
    ec = build_control()
    now = when(datetime.combine(day, at) if at else None)
    d = day.isoformat()
    pub = booking._published(d)
    rain = float(pub.rain_share.iloc[0]) if pub is not None else booking.typical_rain_share(d)
    rain_basis = ""
    if day == date.today():                                    # §6.1.4: the rain so far and the next 2 hours
        from src.control.mpc import blend_rain_share
        from src.live.nowcast import rain_today
        hourly = rain_today(CFG, day)
        if hourly is not None:
            planned, rain = rain, blend_rain_share(rain, hourly, now.hour * 60 + now.minute, CFG["capacity"])
            if abs(rain - planned) >= 0.05:
                rain_basis = (f" Rain today so far and in the next 2 hours: rainy share {round(100 * rain)} % of the "
                              f"open hours (planned {round(100 * planned)} %).")
    try:                                                       # the day-ahead expectation, made the day before
        expected = float(ctx().planner.day((day - timedelta(days=1)).isoformat(), d)["visitors"]["p50"])
        basis = "the day-ahead visitor forecast"
    except (ValueError, KeyError):
        expected = float(pub.tickets.sum()) if pub is not None else 0.0
        basis = "the day's ticket plan"
    cond = booking.conditions(d)
    from src.control.chance import live_kwargs
    cc = live_kwargs(CFG)
    out = MPCController(ec, **cc).caps_now(booking.entries(d), now.hour * 60 + now.minute, rain, expected,
                                     {t: v["factor"] for t, v in cond.items()})
    names = CFG["area"]["trail_names"]
    alerts = [f"{names.get(t, t)}: {v['level'].replace('_', ' ')}" + (f" ({v['note']})" if v["note"] else "")
              + (" - no entry" if v["factor"] >= 1 else f" - {round(100 * v['factor'])} % less room")
              for t, v in cond.items()]
    from src.control.mpc import why_line
    why = why_line(out["arrivals_vs_expected"], rain, booking.typical_rain_share(d),
                   {t: v["factor"] for t, v in cond.items() if v["factor"] > 0}, names)
    return out | {"day": d, "time": now.strftime("%H:%M"), "expected_visitors": round(expected), "alerts": alerts,
                  "why": why,
                  "basis": f"Re-planned now from the gate counts, {basis} and any reported trail conditions; keeps "
                           + (f"the chance of any section going over capacity under "
                              f"{round(100 * cc['chance']['eps'])} % (RQ15). " if cc else
                              f"every section under {round(100 * ec.c['safety_margin'])} % of its capacity. ")
                           + f"No sensors on the trail.{rain_basis}"}


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


def night_passes(night: date):
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


@app.get("/admin/records", tags=["officer"])
def records(start: date, end: date, trail: str | None = None, format: Literal["json", "csv"] = "json",
            user: dict = Depends(role("officer"))):
    """Daily visitors per trail for past, today and future days (records to keep): estimate / DWC total for the
    past, the forecast with a range for the future, and this system's own counts (bookings, gate, halfway).
    Filter by trail; up to 400 days per request; format=csv to download."""
    from src.serve.records import daily_records, to_csv
    if end < start or (end - start).days > 400:
        raise HTTPException(400, "Choose an end date after the start date, at most 400 days apart")
    if trail not in (None, "", "all") and trail not in TRAILS:
        raise HTTPException(400, f"Unknown trail '{trail}'")
    out = daily_records(ctx(), start, end, trail, published("outlook.json"))
    if format == "csv":
        name = f"crowd_records_{CFG['park']}_{out['start']}_{out['end']}{'_' + trail if trail else ''}.csv"
        return Response(to_csv(out["rows"]), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})
    return out


@app.get("/admin/capacity/{day}", tags=["officer"])
def capacity_panel(day: date, user: dict = Depends(role("officer"))):
    """The day's quota per trail under each rule (forecast-driven Cifuentes, weather only, one fixed number, an
    officer's number), the rule the ticket plan uses, and the sections expected over capacity with their hours."""
    from src.serve.capacity_panel import day_panel
    require_booking()
    c = ctx()
    if not c.today + timedelta(days=1) <= day <= c.today + timedelta(days=CFG["live"]["horizon_days"]):
        raise HTTPException(400, "Choose a day from tomorrow up to 90 days ahead")
    return day_panel(c, day, live_inputs(c, day))


class QuotaIn(BaseModel):
    day: date
    trail: TrailName
    rule: Literal["forecast", "classic", "static", "manual"]
    quota: int | None = Field(default=None, ge=0, le=100000)


@app.post("/admin/quota", tags=["officer"])
def set_quota(body: QuotaIn, user: dict = Depends(role("officer"))):
    """Choose the quota rule (or a number) for a trail and day. The day's tickets are re-published at once;
    existing bookings are never cancelled (alerts list the slots now over the safe plan)."""
    require_booking()
    c = ctx()
    if not c.today + timedelta(days=1) <= body.day <= c.today + timedelta(days=CFG["live"]["horizon_days"]):
        raise HTTPException(400, "Choose a day from tomorrow up to 90 days ahead")
    try:
        alerts = booking.set_quota(body.day.isoformat(), body.trail, body.rule, body.quota, user["username"])
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    auth.audit(user["username"], "quota", f"{body.day} {body.trail} {body.rule} {body.quota}")
    return {"alerts": alerts}


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
