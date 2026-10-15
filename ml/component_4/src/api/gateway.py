"""One address for all parks. Each park runs its own API worker (src/api/app.py with C4_PARK set), so data,
bookings and staff accounts stay separate per park. The gateway lists the parks and forwards
/parks/{park}/... to that park's worker. Start everything with:  python -m src.api.serve_all
"""
import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from src.config import destination_info, load_config, parks

PARKS = parks()
PORTS = {p: 8101 + i for i, p in enumerate(PARKS)}

app = FastAPI(title="Component 4 – parks gateway", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=load_config()["api"]["cors_origins"], allow_methods=["*"],
                   allow_headers=["*"])


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/parks")
def list_parks():
    """Every destination with what the trip planner shows (from configs/parks/*.yaml: adding a park = adding a file)."""
    return [destination_info(load_config(park=p)) for p in PARKS]


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
            raise HTTPException(503, f"The {park} service is not running")
    return Response(content=r.content, status_code=r.status_code,
                    media_type=r.headers.get("content-type", "application/json"))
