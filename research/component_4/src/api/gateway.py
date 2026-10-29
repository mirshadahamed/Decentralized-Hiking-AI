"""One address for all parks. Each park runs its own API worker (src/api/app.py with C4_PARK set), so data,
bookings and staff accounts stay separate per park. The gateway lists the parks and forwards
/parks/{park}/... to that park's worker. Start everything with:  python -m src.api.serve_all
"""
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


async def _capacity(client: httpx.AsyncClient, park: str, day: str) -> dict | None:
    try:
        r = await client.get(f"http://127.0.0.1:{PORTS[park]}/capacity/{day}")
        return r.json() if r.status_code == 200 else None
    except httpx.HTTPError:
        return None                                              # a park that is down is listed as unknown


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


@app.api_route("/parks/{park}/{path:path}", methods=["GET", "POST", "DELETE"])
async def forward(park: str, path: str, request: Request):
    if park not in PORTS:
        raise HTTPException(404, f"Unknown park '{park}'")
    url = f"http://127.0.0.1:{PORTS[park]}/{path}"
    headers = {k: v for k, v in request.headers.items() if k.lower() in ("authorization", "content-type")}
    async with httpx.AsyncClient(timeout=180) as client:
        try:
            r = await client.request(request.method, url, params=request.query_params, headers=headers,
                                     content=await request.body())
        except httpx.ConnectError:
            raise HTTPException(503, f"The {park} service is not running") from None
    return Response(content=r.content, status_code=r.status_code,
                    media_type=r.headers.get("content-type", "application/json"))
