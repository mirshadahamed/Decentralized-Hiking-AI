"""Trail graph of a long-distance trail from its OpenStreetMap route relations, one route per stage (Pekoe Trail).

    $env:C4_PARK = "pekoe_trail"; python -m src.data.graph

Each stage relation (config area.stage_relations: {stage id: OSM relation id}) is assembled into one line in member
order (ways flipped to join end to end), cut into sections of about graph.target_segment_m, and walked start -> end.
Consecutive stages meet where one ends and the next starts, so their end sections are linked; the graph is the
whole trail. Access points: the first section of every stage (where walkers start; the last stage also at its end).
Hotspots (config area.hotspots: {key: OSM name}) are named places within graph.poi_snap_m of the trail (viewpoints,
towns with day visitors). Writes the same files as src.data.graph (segments.geojson, edge_index / edge_weight,
route.json), so the rest of the pipeline is unchanged. The raw OSM answers are cached in data/<park>/raw/osm_stages/.
"""
import json
import time

import geopandas as gpd
import numpy as np
import requests
from pyproj import Transformer
from shapely.geometry import LineString, Point
from shapely.ops import substring, transform

from src.config import PROCESSED, RAW

URLS = ("https://overpass-api.de/api/interpreter", "https://overpass.private.coffee/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter")
HEADERS = {"User-Agent": "SLIIT-research-component4 (trail crowd forecasting)"}


def overpass(query: str, cache_name: str, tries: int = 12) -> list:
    cache = RAW / "osm_stages" / cache_name
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    cache.parent.mkdir(parents=True, exist_ok=True)
    last = None
    for k in range(tries):
        url = URLS[k % len(URLS)]
        try:
            r = requests.post(url, data={"data": query}, timeout=120, headers=HEADERS)
            if r.ok:
                els = r.json()["elements"]
                cache.write_text(json.dumps(els), encoding="utf-8")
                return els
            last = f"{url}: HTTP {r.status_code}"
        except (requests.RequestException, ValueError) as e:
            last = f"{url}: {e}"
        print(f"  overpass busy ({last}); retrying", flush=True)
        time.sleep(min(120, 5 * 2 ** (k // len(URLS))))  # Overpass asks clients to back off when busy
    raise RuntimeError(f"Overpass failed after {tries} tries ({last})")


def stage_line(rel: dict) -> list:
    """[(lon, lat), ...] of a route relation, ways in member order, each flipped to continue from the last point."""
    coords: list = []
    for m in rel.get("members", []):
        if m["type"] != "way" or not m.get("geometry"):
            continue
        pts = [(p["lon"], p["lat"]) for p in m["geometry"]]
        if coords:
            end = coords[-1]
            d_fwd = (pts[0][0] - end[0]) ** 2 + (pts[0][1] - end[1]) ** 2
            d_rev = (pts[-1][0] - end[0]) ** 2 + (pts[-1][1] - end[1]) ** 2
            if d_rev < d_fwd:
                pts = pts[::-1]
            if pts[0] == end:
                pts = pts[1:]
        elif len(rel["members"]) > 1:                    # first way: orient towards the second
            nxt = next((x for x in rel["members"][1:] if x["type"] == "way" and x.get("geometry")), None)
            if nxt is not None:
                q = [(p["lon"], p["lat"]) for p in nxt["geometry"]]
                ends = [q[0], q[-1]]
                if min((pts[0][0] - e[0]) ** 2 + (pts[0][1] - e[1]) ** 2 for e in ends) < \
                        min((pts[-1][0] - e[0]) ** 2 + (pts[-1][1] - e[1]) ** 2 for e in ends):
                    pts = pts[::-1]
        coords += pts
    return coords


def build_stage_graph(cfg):
    area, g = cfg["area"], cfg["graph"]
    to_m = Transformer.from_crs("EPSG:4326", area["crs_metric"], always_xy=True).transform
    to_ll = Transformer.from_crs(area["crs_metric"], "EPSG:4326", always_xy=True).transform
    target = g["target_segment_m"]
    stages = list(area["stage_relations"])

    segs, walks = [], {}
    for k, (stage, rel_id) in enumerate(area["stage_relations"].items()):
        rel = overpass(f"[out:json][timeout:180];rel({int(rel_id)});out geom;", f"rel_{rel_id}.json")[0]
        line_m = transform(to_m, LineString(stage_line(rel)))
        n = max(1, round(line_m.length / target))
        walks[stage] = []
        for i in range(n):
            piece = substring(line_m, i * line_m.length / n, (i + 1) * line_m.length / n)
            walks[stage].append((len(segs), 1))
            segs.append({"stage": stage, "k": k, "piece": i, "n": n, "geom_m": piece, "length_m": piece.length,
                         "geometry": transform(to_ll, piece), "poi": ""})

    # access points: every stage start (and the trail's end)
    for stage, walk in walks.items():
        segs[walk[0][0]]["poi"] = f"start_{stage}"
    segs[walks[stages[-1]][-1][0]]["poi"] = segs[walks[stages[-1]][-1][0]]["poi"] or "trail_end"

    # hotspots: named places near the trail
    names = {}
    for stage, rel_id in area["stage_relations"].items():
        for e in overpass(f"[out:json][timeout:180];rel({int(rel_id)});way(r);node(around:{int(g['poi_snap_m'])})[name];out;",
                          f"names_{rel_id}.json"):
            names.setdefault(e["tags"]["name"].strip().lower(), (e["lon"], e["lat"]))
    missing = []
    for key, osm_name in (area.get("hotspots") or {}).items():
        p = names.get(osm_name.strip().lower())
        if p is None:
            missing.append(osm_name)
            continue
        pm = transform(to_m, Point(p))
        d = [s["geom_m"].distance(pm) for s in segs]
        i = int(np.argmin(d))
        if not segs[i]["poi"]:
            segs[i]["poi"] = key
        else:                                             # the start section is taken: use the next one
            j = i + 1 if i + 1 < len(segs) and segs[i + 1]["stage"] == segs[i]["stage"] else i - 1
            segs[j]["poi"] = segs[j]["poi"] or key

    # edges: consecutive sections of a stage, and a stage's last section with the next stage's first
    w = {}
    for stage, walk in walks.items():
        for (a, _), (b, _) in zip(walk[:-1], walk[1:]):
            w[(a, b)] = w[(b, a)] = 1.0
    gap_max = g.get("stage_join_m", 2000)
    for s1, s2 in zip(stages[:-1], stages[1:]):
        a, b = walks[s1][-1][0], walks[s2][0][0]
        if segs[a]["geom_m"].distance(segs[b]["geom_m"]) <= gap_max:
            w[(a, b)] = w[(b, a)] = 1.0
    keys = sorted(w)
    edge_index, edge_weight = np.array(keys).T, np.array([w[x] for x in keys], dtype=np.float32)

    gdf = gpd.GeoDataFrame(
        {"seg_id": range(len(segs)), "chain": [s["k"] for s in segs], "trail": [s["stage"] for s in segs],
         "walk_position": [round(s["piece"] / s["n"], 4) for s in segs],
         "length_m": [round(s["length_m"], 1) for s in segs], "poi": [s["poi"] for s in segs],
         "frac_steps": [0.0] * len(segs)},
        geometry=[s["geometry"] for s in segs], crs="EPSG:4326")
    gdf.to_file(PROCESSED / "segments.geojson", driver="GeoJSON")
    np.save(PROCESSED / "edge_index.npy", edge_index)
    np.save(PROCESSED / "edge_weight.npy", edge_weight)
    (PROCESSED / "route.json").write_text(json.dumps({"walks": walks, "road_links": []}), encoding="utf-8")
    if missing:
        print("hotspots not found near the trail (check the OSM name):", missing)
    return gdf, edge_index, walks
