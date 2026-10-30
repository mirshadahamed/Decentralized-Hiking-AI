"""One address for all parks. Each park runs its own API worker (src/api/app.py with C4_PARK set), so data,
bookings and staff accounts stay separate per park. The gateway lists the parks and forwards
/parks/{park}/... to that park's worker. Start everything with:  python -m src.api.serve_all
"""
import time
from datetime import date, timedelta

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from src.config import destination_info, load_config, parks

PARKS = parks()
PORTS = {p: 8101 + i for i, p in enumerate(PARKS)}

app = FastAPI(title="Component 4 – parks gateway", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=load_config()["api"]["cors_origins"], allow_methods=["*"],
                   allow_headers=["*"])


@app.get("/")
def root():
    """Opening http://localhost:8000 in a browser: say what is here instead of 404."""
    return {"service": "Component 4 parks gateway", "parks": "/parks",
            "per_park": "/parks/{park}/... e.g. /parks/adams_peak/status", "docs": "/docs"}


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/parks")
def list_parks():
    """Every destination with what the trip planner shows (from configs/parks/*.yaml: adding a park = adding a file)."""
    return [destination_info(load_config(park=p)) for p in PARKS]


# §6.3.12: public forecasts change at most a few times a day; on a Poya morning many phones ask the same thing.
# Unauthenticated GETs of these paths are kept CACHE_S seconds (per park, path and query).
CACHE_S = 60
CACHED = ("capacity/", "plan/", "outlook", "status", "destination", "stages/", "viewpoints/", "segments")
_cache: dict = {}


def _cached(key):
    hit = _cache.get(key)
    return hit[1] if hit and time.monotonic() - hit[0] < CACHE_S else None


def _store(key, value):
    if len(_cache) > 5000:                                       # bounded: drop everything rather than grow
        _cache.clear()
    _cache[key] = (time.monotonic(), value)


async def _capacity(client: httpx.AsyncClient, park: str, day: str) -> dict | None:
    key = (park, f"capacity/{day}", "")
    if (hit := _cached(key)) is not None:
        return hit[0]
    try:
        r = await client.get(f"http://127.0.0.1:{PORTS[park]}/capacity/{day}")
        out = r.json() if r.status_code == 200 else None
    except httpx.HTTPError:
        return None                                              # a park that is down is listed as unknown
    if out is not None:
        _store(key, (out,))
    return out


@app.get("/network/{day}")
async def network(day: date, park: str | None = None, around: int = 3):
    """N4: every park's expected load that day (expected visitors / safe limit) and, for `park`, other parks with
    room and quieter days within `around` days."""
    import asyncio
    from src.api.network import advice, park_row
    if park is not None and park not in PORTS:
        raise HTTPException(404, f"Unknown park '{park}'")
    info = {p: destination_info(load_config(park=p)) for p in PARKS}
    near = [day + timedelta(days=k) for k in range(-around, around + 1) if k] if park else []
    async with httpx.AsyncClient(timeout=120) as client:
        caps = await asyncio.gather(*[_capacity(client, p, day.isoformat()) for p in PARKS],
                                    *[_capacity(client, park, d.isoformat()) for d in near])
    rows = [park_row(p, info[p], c) for p, c in zip(PARKS, caps)]
    days = [(d.isoformat(), park_row(park, info[park], c)) for d, c in zip(near, caps[len(PARKS):])]
    return advice(day.isoformat(), rows, park, days)


@app.get("/trip")
async def trip(parks: str, start: date, days: int = 3):
    """§6.2.5 trip planner: parks=horton_plains,knuckles,pekoe_trail; one quiet day for each within `days` days from
    `start` (each park's expected load per day from its /capacity)."""
    import asyncio
    from src.api.network import park_row, plan_trip
    chosen = [p for p in parks.split(",") if p]
    bad = [p for p in chosen if p not in PORTS]
    if bad or not chosen:
        raise HTTPException(404, f"Unknown park(s): {', '.join(bad) or '-'}")
    if not 1 <= days <= 14:
        raise HTTPException(400, "days must be 1-14")
    span = [(start + timedelta(days=k)).isoformat() for k in range(days)]
    info = {p: destination_info(load_config(park=p)) for p in chosen}
    keys = [(p, d) for p in chosen for d in span]
    async with httpx.AsyncClient(timeout=120) as client:
        caps = await asyncio.gather(*[_capacity(client, p, d) for p, d in keys])
    try:
        return plan_trip(chosen, span, {k: park_row(k[0], info[k[0]], c) for k, c in zip(keys, caps)})
    except ValueError as e:
        raise HTTPException(400, str(e)) from None


@app.api_route("/parks/{park}/{path:path}", methods=["GET", "POST", "DELETE"])
async def forward(park: str, path: str, request: Request):
    if park not in PORTS:
        raise HTTPException(404, f"Unknown park '{park}'")
    url = f"http://127.0.0.1:{PORTS[park]}/{path}"
    headers = {k: v for k, v in request.headers.items() if k.lower() in ("authorization", "content-type")}
    cache = (request.method == "GET" and "authorization" not in headers and path.startswith(CACHED))
    key = (park, path, str(request.query_params))
    if cache and (hit := _cached(key)) is not None:
        return Response(content=hit[0], status_code=200, media_type=hit[1], headers={"X-Cache": "hit"})
    async with httpx.AsyncClient(timeout=180) as client:
        try:
            r = await client.request(request.method, url, params=request.query_params, headers=headers,
                                     content=await request.body())
        except httpx.ConnectError:
            raise HTTPException(503, f"The {park} service is not running") from None
    media = r.headers.get("content-type", "application/json")
    if cache and r.status_code == 200:
        _store(key, (r.content, media))
    return Response(content=r.content, status_code=r.status_code, media_type=media)
