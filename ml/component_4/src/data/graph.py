"""Build the Horton Plains trail graph from OpenStreetMap (D1 / FR1).

Graph nodes are trail *segments* of about 300 m (occupancy is counted per segment,
like a traffic sensor covers a road stretch). Two segments are linked when they touch.
The main hiking loop is found as the shortest path through the key POIs in order.
"""
import json
import math

import geopandas as gpd
import networkx as nx
import numpy as np
import osmnx as ox
from pyproj import Transformer
from shapely.geometry import LineString
from shapely.ops import substring, transform

from src.config import PROCESSED, RAW

TRAIL_FILTER = '["highway"~"path|footway|track|steps"]'


def load_osm(cfg):
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(RAW / "osm_cache")
    bbox = tuple(cfg["area"]["bbox"])
    G = ox.graph_from_bbox(bbox, custom_filter=TRAIL_FILTER, simplify=True, retain_all=True)
    pois = ox.features_from_bbox(bbox, tags={"tourism": True, "waterway": "waterfall"})
    return ox.convert.to_undirected(G), pois


def _edge_coords(G, u, v):
    """Edge geometry as lon/lat coords, oriented from u to v."""
    data = min(G.get_edge_data(u, v).values(), key=lambda d: d["length"])
    pu, pv = (G.nodes[u]["x"], G.nodes[u]["y"]), (G.nodes[v]["x"], G.nodes[v]["y"])
    coords = list(data["geometry"].coords) if "geometry" in data else [pu, pv]
    if math.dist(coords[0], pu) > math.dist(coords[-1], pu):
        coords.reverse()
    return coords


def find_route(G, pois, cfg):
    """Shortest path through the configured POIs, as a list of OSM node ids."""
    names = cfg["area"]["pois"]
    poi_nodes, poi_points = {}, {}
    for key, name in names.items():
        p = pois[pois["name"] == name].iloc[0].geometry.centroid
        poi_nodes[key] = ox.distance.nearest_nodes(G, p.x, p.y)
        poi_points[key] = p
    route = []
    for a, b in zip(cfg["area"]["route"][:-1], cfg["area"]["route"][1:]):
        leg = nx.shortest_path(G, poi_nodes[a], poi_nodes[b], weight="length")
        route += leg if not route else leg[1:]
    return route, poi_points


def build_chains(G, route):
    """Merge the unique route edges into chains between junctions."""
    H = nx.Graph()
    H.add_edges_from(zip(route[:-1], route[1:]))
    junctions = {n for n in H if H.degree(n) != 2} | {route[0]}
    chains, edge_to_chain, seen = [], {}, set()
    for j in junctions:
        for nb in H.neighbors(j):
            if frozenset((j, nb)) in seen:
                continue
            path = [j, nb]
            while path[-1] not in junctions:
                nxt = [n for n in H.neighbors(path[-1]) if n != path[-2]][0]
                path.append(nxt)
            cid = len(chains)
            for i, (u, v) in enumerate(zip(path[:-1], path[1:])):
                seen.add(frozenset((u, v)))
                edge_to_chain[(u, v)] = (cid, +1)
                edge_to_chain[(v, u)] = (cid, -1)
            coords = []
            for u, v in zip(path[:-1], path[1:]):
                c = _edge_coords(G, u, v)
                coords += c if not coords else c[1:]
            chains.append({"nodes": path, "coords": coords})
    return chains, edge_to_chain


def split_chains(chains, cfg):
    """Cut every chain into pieces of about target_segment_m metres."""
    to_m = Transformer.from_crs("EPSG:4326", cfg["area"]["crs_metric"], always_xy=True).transform
    to_ll = Transformer.from_crs(cfg["area"]["crs_metric"], "EPSG:4326", always_xy=True).transform
    target = cfg["graph"]["target_segment_m"]
    segs = []
    for cid, ch in enumerate(chains):
        line_m = transform(to_m, LineString(ch["coords"]))
        k = max(1, round(line_m.length / target))
        ch["segments"] = []
        for i in range(k):
            piece = substring(line_m, i * line_m.length / k, (i + 1) * line_m.length / k)
            start = ("osm", ch["nodes"][0]) if i == 0 else ("cut", cid, i)
            end = ("osm", ch["nodes"][-1]) if i == k - 1 else ("cut", cid, i + 1)
            ch["segments"].append(len(segs))
            segs.append({"chain": cid, "piece": i, "length_m": piece.length,
                         "start": start, "end": end, "geom_m": piece,
                         "geometry": transform(to_ll, piece)})
    return segs


def route_to_segments(route, chains, edge_to_chain):
    """Walking order of the loop as (segment id, direction) pairs; direction +1 = chain order."""
    steps = []
    for u, v in zip(route[:-1], route[1:]):
        cid, d = edge_to_chain[(u, v)]
        if not steps or steps[-1] != (cid, d):
            steps.append((cid, d))
    out = []
    for cid, d in steps:
        ids = chains[cid]["segments"]
        out += [(s, d) for s in (ids if d > 0 else ids[::-1])]
    return out


def segment_edges(segs):
    """Undirected adjacency: segments that share an end point."""
    ends = {}
    for i, s in enumerate(segs):
        for key in (s["start"], s["end"]):
            ends.setdefault(key, []).append(i)
    edges = set()
    for ids in ends.values():
        for a in ids:
            for b in ids:
                if a != b:
                    edges.add((a, b))
    return np.array(sorted(edges)).T  # [2, E], both directions


def tag_pois(segs, poi_points, cfg):
    to_m = Transformer.from_crs("EPSG:4326", cfg["area"]["crs_metric"], always_xy=True).transform
    for s in segs:
        s["poi"] = ""
    for key, p in poi_points.items():
        pm = transform(to_m, p)
        d = [s["geom_m"].distance(pm) for s in segs]
        i = int(np.argmin(d))
        if d[i] <= cfg["graph"]["poi_snap_m"]:
            segs[i]["poi"] = key


def build_graph(cfg):
    G, pois = load_osm(cfg)
    route, poi_points = find_route(G, pois, cfg)
    chains, edge_to_chain = build_chains(G, route)
    segs = split_chains(chains, cfg)
    tag_pois(segs, poi_points, cfg)
    walk = route_to_segments(route, chains, edge_to_chain)
    edge_index = segment_edges(segs)

    gdf = gpd.GeoDataFrame(
        {"seg_id": range(len(segs)),
         "chain": [s["chain"] for s in segs],
         "length_m": [round(s["length_m"], 1) for s in segs],
         "poi": [s["poi"] for s in segs]},
        geometry=[s["geometry"] for s in segs], crs="EPSG:4326")
    gdf.to_file(PROCESSED / "segments.geojson", driver="GeoJSON")
    np.save(PROCESSED / "edge_index.npy", edge_index)
    (PROCESSED / "route.json").write_text(json.dumps({"walk": walk}), encoding="utf-8")
    return gdf, edge_index, walk


if __name__ == "__main__":
    from src.config import load_config
    gdf, ei, walk = build_graph(load_config())
    print(f"segments={len(gdf)} edges={ei.shape[1] // 2} loop_m={gdf.length_m.sum():.0f} walk_steps={len(walk)}")
    print(gdf[gdf.poi != ""][["seg_id", "poi", "length_m"]].to_string(index=False))
