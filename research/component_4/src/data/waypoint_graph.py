"""K2: a trail network from waypoints, for areas where OSM paths are incomplete (the Knuckles Range).

Each trail is a list of waypoints (area.poi_points: key -> [lon, lat], taken from OSM peaks, viewpoints, falls,
campsites and car parks). Between two waypoints the builder follows the OSM walk network (paths, tracks, minor
roads) when it gives a sensible route: both ends within graph.snap_max_m of the network and no longer than
graph.max_detour x the straight distance. Otherwise the leg is a straight line, marked APPROXIMATE (its length
is the straight line x graph.straight_factor, for the bends a real path has). Approximate legs are to be replaced
by GPS tracks from a field visit (docs/assumptions_knuckles.md); data/processed/graph_quality.json lists them.

Trails are cut into sections of about graph.target_segment_m and walked out and back (area.waypoint_trails.<t>.back).
Graph edges: consecutive sections of a trail; the first sections of trails sharing an entry (area.trail_entries);
sections of different trails closer than graph.share_m (shared paths, weaker edge).
"""
import json
import math

import geopandas as gpd
import networkx as nx
import numpy as np
import osmnx as ox
from pyproj import Transformer
from shapely.geometry import LineString, Point
from shapely.ops import substring, transform

from src.config import PROCESSED, RAW

WALK_FILTER = '["highway"~"path|footway|track|steps|unclassified|residential|service|tertiary|living_street|bridleway"]'


def _network(cfg):
    from src.data.graph import with_mirrors
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(RAW / "osm_cache")
    bbox = tuple(cfg["area"]["bbox"])
    G = with_mirrors(lambda: ox.graph_from_bbox(bbox, custom_filter=cfg["graph"].get("osm_filter", WALK_FILTER),
                                                simplify=True, retain_all=True))
    return ox.convert.to_undirected(G)


def _leg(G, a, b, g, to_m):
    """Coordinates (lon, lat) from waypoint a to b, and the metres of it that are approximate (straight): the whole
    leg when OSM gives no sensible route, else only the connectors from the waypoints to the OSM network."""
    m = lambda q: transform(to_m, Point(q)).coords[0]                      # noqa: E731
    straight = math.dist(m(a), m(b))
    na, nb = ox.distance.nearest_nodes(G, a[0], a[1]), ox.distance.nearest_nodes(G, b[0], b[1])
    pa, pb = (G.nodes[na]["x"], G.nodes[na]["y"]), (G.nodes[nb]["x"], G.nodes[nb]["y"])
    ca, cb = math.dist(m(a), m(pa)), math.dist(m(b), m(pb))
    if max(ca, cb) <= g.get("snap_max_m", 400) and na != nb:
        try:
            path = nx.shortest_path(G, na, nb, weight="length")
            length = nx.path_weight(G, path, weight="length") + ca + cb
            if length <= g.get("max_detour", 2.5) * max(straight, 1.0):
                from src.data.graph import _edge_coords
                coords = [a]
                for u, v in zip(path[:-1], path[1:]):
                    coords += _edge_coords(G, u, v)
                return coords + [b], ca + cb
        except nx.NetworkXNoPath:
            pass
    return [a, b], None


def build_waypoint_graph(cfg):
    area, g = cfg["area"], cfg["graph"]
    to_m = Transformer.from_crs("EPSG:4326", area["crs_metric"], always_xy=True).transform
    to_ll = Transformer.from_crs(area["crs_metric"], "EPSG:4326", always_xy=True).transform
    pts = {k: tuple(v) for k, v in area["poi_points"].items()}
    G = _network(cfg)
    target, factor = g["target_segment_m"], g.get("straight_factor", 1.3)
    segs, walks, quality = [], {}, {}
    for trail, spec in area["waypoint_trails"].items():
        coords, approx_m, total_m = [], 0.0, 0.0
        for a, b in zip(spec["points"][:-1], spec["points"][1:]):
            leg, conn = _leg(G, pts[a], pts[b], g, to_m)
            leg_m = transform(to_m, LineString(leg)).length
            if conn is None:                                       # all straight
                total_m += leg_m * factor
                approx_m += leg_m * factor
            else:                                                  # OSM route + straight connectors
                total_m += leg_m + conn * (factor - 1)
                approx_m += conn * factor
            coords += leg if not coords else leg[1:]
        coords = [q for k, q in enumerate(coords) if k == 0 or q != coords[k - 1]]
        line = LineString(coords)
        line_m = transform(to_m, line)
        stretch = total_m / max(line_m.length, 1.0)               # straight legs count as longer than drawn
        n = max(1, round(total_m / target))
        out = []
        for i in range(n):
            piece = substring(line_m, i * line_m.length / n, (i + 1) * line_m.length / n)
            out.append((len(segs), 1))
            segs.append({"trail": trail, "piece": i, "n": n, "geom_m": piece, "length_m": piece.length * stretch,
                         "geometry": transform(to_ll, piece), "poi": ""})
        walks[trail] = out + ([(s, -1) for s, _ in reversed(out)] if spec.get("back", True) else [])
        quality[trail] = {"km": round(total_m / 1000, 1), "approximate_share": round(approx_m / max(total_m, 1.0), 2),
                          "sections": n}
        segs[out[0][0]]["poi"] = f"head_{trail}"
        end_key = spec["points"][-1]
        if not segs[out[-1][0]]["poi"]:
            segs[out[-1][0]]["poi"] = end_key
    # other named waypoints on the way (falls, camps): nearest section of the trail that lists them
    for trail, spec in area["waypoint_trails"].items():
        for key in spec["points"][1:-1]:
            p = transform(to_m, Point(pts[key]))
            cand = [i for i, s in enumerate(segs) if s["trail"] == trail and not s["poi"]]
            if cand:
                segs[min(cand, key=lambda i: segs[i]["geom_m"].distance(p))]["poi"] = key

    w = {}
    for walk in walks.values():
        out = [s for s, d in walk if d == 1]
        for a, b in zip(out[:-1], out[1:]):
            w[(a, b)] = w[(b, a)] = 1.0
    entries = area.get("trail_entries", {})
    firsts = {t: walks[t][0][0] for t in walks}
    for t1 in walks:
        for t2 in walks:
            if t1 < t2 and entries.get(t1) and entries.get(t1) == entries.get(t2):
                a, b = firsts[t1], firsts[t2]
                w[(a, b)] = w[(b, a)] = 1.0
    share_m = g.get("share_m", 150)
    for i, si in enumerate(segs):
        for j in range(i + 1, len(segs)):
            if segs[j]["trail"] != si["trail"] and (i, j) not in w and si["geom_m"].distance(segs[j]["geom_m"]) <= share_m:
                w[(i, j)] = w[(j, i)] = 0.5
    keys = sorted(w)
    edge_index = np.array(keys).T if keys else np.zeros((2, 0), int)
    edge_weight = np.array([w[x] for x in keys], dtype=np.float32)

    gdf = gpd.GeoDataFrame(
        {"seg_id": range(len(segs)), "chain": [list(walks).index(s["trail"]) for s in segs],
         "trail": [s["trail"] for s in segs], "walk_position": [round(s["piece"] / s["n"], 4) for s in segs],
         "length_m": [round(s["length_m"], 1) for s in segs], "poi": [s["poi"] for s in segs],
         "frac_steps": [0.0] * len(segs)},
        geometry=[s["geometry"] for s in segs], crs="EPSG:4326")
    PROCESSED.mkdir(parents=True, exist_ok=True)
    gdf.to_file(PROCESSED / "segments.geojson", driver="GeoJSON")
    np.save(PROCESSED / "edge_index.npy", edge_index)
    np.save(PROCESSED / "edge_weight.npy", edge_weight)
    (PROCESSED / "route.json").write_text(json.dumps({"walks": walks, "road_links": []}), encoding="utf-8")
    (PROCESSED / "graph_quality.json").write_text(json.dumps(quality, indent=1), encoding="utf-8")
    print("trail km and approximate share:", quality)
    return gdf, edge_index, walks
