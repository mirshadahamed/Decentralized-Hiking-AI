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


def nominatim(wanted: list, bbox) -> dict:
    """{lower-case name: (lon, lat)} from the OSM place search (Nominatim), inside bbox; cached; 1 request/s as its
    usage policy asks. Names it cannot find are left out (the builder reports them)."""
    cache = RAW / "osm_stages" / "hotspots_nominatim.json"
    found = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {}
    left, bottom, right, top = bbox
    for name in wanted:
        if name.lower() in found:
            continue
        try:
            r = requests.get("https://nominatim.openstreetmap.org/search", headers=HEADERS, timeout=30, params={
                "q": name, "format": "json", "limit": 1, "countrycodes": "lk", "bounded": 1,
                "viewbox": f"{left},{top},{right},{bottom}"})
            hit = r.json()[0] if r.ok and r.json() else None
        except (requests.RequestException, ValueError, IndexError):
            hit = None
        if hit:
            found[name.lower()] = (float(hit["lon"]), float(hit["lat"]))
        time.sleep(1.1)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(found), encoding="utf-8")
    return {k: tuple(v) for k, v in found.items()}


def stage_chain(rel: dict, anchor=None) -> list:
    """[(lon, lat), ...] of a route relation whose ways may be listed out of order: merge the ways into pieces, then
    chain the pieces nearest end to nearest end, starting at the end closest to `anchor` (the previous stage's
    end) or, for the first stage, at a loose end of the network."""
    from shapely.ops import linemerge
    ways, seen = [], set()
    for m in rel.get("members", []):
        if m["type"] != "way" or len(m.get("geometry") or []) < 2:
            continue
        key = m.get("ref") or tuple((p["lon"], p["lat"]) for p in m["geometry"])
        if key in seen:                                   # some relations list a way more than once
            continue
        seen.add(key)
        ways.append(LineString([(p["lon"], p["lat"]) for p in m["geometry"]]))
    if not ways:
        return []
    merged = linemerge(ways)
    parts = [list(p.coords) for p in (merged.geoms if merged.geom_type == "MultiLineString" else [merged])]

    def d2(a, b):
        return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2

    ends = [(i, 0) for i in range(len(parts))] + [(i, -1) for i in range(len(parts))]
    if anchor is not None:
        i, e = min(ends, key=lambda x: d2(parts[x[0]][x[1]], anchor))
    else:                                                 # the end farthest from every other piece's ends
        def loneliness(x):
            others = [parts[j][k] for j, k in ends if j != x[0]]
            return min((d2(parts[x[0]][x[1]], o) for o in others), default=0.0)
        i, e = max(ends, key=lambda x: (loneliness(x), len(parts[x[0]])))
    coords = parts[i] if e == 0 else parts[i][::-1]
    left = [j for j in range(len(parts)) if j != i]
    while left:
        end = coords[-1]
        j, flip = min(((j, f) for j in left for f in (False, True)),
                      key=lambda x: d2(parts[x[0]][-1 if x[1] else 0], end))
        nxt = parts[j][::-1] if flip else parts[j]
        coords += nxt[1:] if nxt[0] == end else nxt
        left.remove(j)
    return coords


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

    rels = {s: overpass(f"[out:json][timeout:180];rel({int(r)});out geom;", f"rel_{r}.json")[0]
            for s, r in area["stage_relations"].items()}
    # the first stage has no previous end: start it at its end farthest from the second stage
    first = stage_chain(rels[stages[0]])
    if len(stages) > 1:
        nxt = [(p["lon"], p["lat"]) for m in rels[stages[1]]["members"] if m["type"] == "way"
               for p in (m.get("geometry") or [])]
        near = lambda q: min((q[0] - a) ** 2 + (q[1] - b) ** 2 for a, b in nxt)   # noqa: E731
        if near(first[0]) < near(first[-1]):
            first = stage_chain(rels[stages[0]], anchor=first[-1])
    segs, walks, anchor, lengths = [], {}, None, {}
    for k, (stage, rel_id) in enumerate(area["stage_relations"].items()):
        rel = rels[stage]
        coords = first if k == 0 else stage_chain(rel, anchor)
        anchor = coords[-1]
        line_m = transform(to_m, LineString(coords))
        lengths[stage] = (round(line_m.length / 1000, 1), rel["tags"].get("distance"))
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
    wanted = sorted({v for v in (area.get("hotspots") or {}).values()})
    if wanted:                                         # one light query: just these names, inside the trail's box
        left, bottom, right, top = area["bbox"]
        rx = "|".join(n.replace("'", ".").replace("(", ".").replace(")", ".") for n in wanted)
        q = f'[out:json][timeout:120];nwr["name"~"^({rx})$",i]({bottom},{left},{top},{right});out center;'
        try:
            for e in overpass(q, "hotspots.json", tries=4):
                ll = (e["lon"], e["lat"]) if "lon" in e else (e["center"]["lon"], e["center"]["lat"])
                names.setdefault(e["tags"]["name"].strip().lower(), ll)
        except RuntimeError:                           # Overpass busy: the OSM place search, one name a second
            names = nominatim(wanted, area["bbox"])
    for alias in list(names):                          # OSM may use a curly apostrophe
        names.setdefault(alias.replace("’", "'"), names[alias])
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
    print("stage km (built, OSM tag):", lengths)
    return gdf, edge_index, walks
