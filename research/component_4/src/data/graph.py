"""Build the Horton Plains trail network from OpenStreetMap (D1 / FR1).

Three trails share one park entrance:
  main         World's End loop (Visitor Center -> Mini World's End -> World's End -> Baker's Falls -> back)
  kirigalpotta out and back from the Visitor Center to Kirigalpotta peak
  thotupola    out and back from the Thotupola trailhead (4.2 km up the road) to Thotupola Kanda

Graph nodes are trail *segments* of about 300 m (occupancy is counted per segment, like a traffic
sensor covers a road stretch). Segments that touch are linked with weight 1. Trails that are only
connected by road (Thotupola) are linked to the entrance with a weaker edge (config: area.road_links).
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

TRAIL_FILTER = '["highway"~"path|footway|track|steps"]'
POI_TAGS = {"tourism": True, "waterway": "waterfall", "natural": "peak"}


def load_osm(cfg):
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(RAW / "osm_cache")
    bbox = tuple(cfg["area"]["bbox"])
    osm_filter = cfg["graph"].get("osm_filter", TRAIL_FILTER)      # safari parks: jeep tracks, not footpaths
    G = ox.graph_from_bbox(bbox, custom_filter=osm_filter, simplify=True, retain_all=True)
    pois = None
    if cfg["area"].get("pois"):                       # named landmarks (Horton Plains); named-path parks need none
        pois = ox.features_from_bbox(bbox, tags=cfg["area"].get("poi_tags", POI_TAGS))
    G = ox.convert.to_undirected(G)
    if cfg["graph"].get("largest_component"):     # safari tracks: drop OSM fragments a jeep cannot reach
        G = G.subgraph(max(nx.connected_components(G), key=len)).copy()
    if cfg["area"].get("summit_link"):
        add_summit_link(G, cfg)
    return G, pois


SUMMIT_NODE = -1


def add_summit_link(G, cfg):
    """OSM paths at Adam's Peak stop ~350 m below the summit (16 Oct 2026). Add the final stairway as a straight
    link from the nearest mapped trail point to the summit, tagged as steps. APPROXIMATE: replace with a GPS track."""
    lon, lat = cfg["area"]["summit_point"]
    near = ox.distance.nearest_nodes(G, lon, lat)
    length = math.dist((G.nodes[near]["x"], G.nodes[near]["y"]), (lon, lat)) * 111_000
    G.add_node(SUMMIT_NODE, x=lon, y=lat)
    G.add_edge(near, SUMMIT_NODE, length=length, highway="steps", name="Final steps to the summit (approximate)",
               geometry=LineString([(G.nodes[near]["x"], G.nodes[near]["y"]), (lon, lat)]))


def _edge_coords(G, u, v):
    """Edge geometry as lon/lat coords, oriented from u to v."""
    data = min(G.get_edge_data(u, v).values(), key=lambda d: d["length"])
    pu, pv = (G.nodes[u]["x"], G.nodes[u]["y"]), (G.nodes[v]["x"], G.nodes[v]["y"])
    coords = list(data["geometry"].coords) if "geometry" in data else [pu, pv]
    if math.dist(coords[0], pu) > math.dist(coords[-1], pu):
        coords.reverse()
    return coords


def _named_route(G, osm_name: str, summit: int):
    """Trailhead -> summit along an OSM path name. The trailhead is the end of the named path farthest from the
    summit; the path prefers the named edges (other edges cost 5x) so it follows the real route."""
    def is_named(d):
        return osm_name in str(d.get("name", ""))
    nodes = {n for u, v, d in G.edges(data=True) if is_named(d) for n in (u, v)}
    if not nodes:
        raise ValueError(f"No OSM path named '{osm_name}' in the bounding box")
    sx, sy = G.nodes[summit]["x"], G.nodes[summit]["y"]
    head = max(nodes, key=lambda n: math.dist((G.nodes[n]["x"], G.nodes[n]["y"]), (sx, sy)))

    def weight(u, v, data):
        return min(d["length"] * (1 if is_named(d) else 1.5) for d in data.values())
    try:
        return nx.shortest_path(G, head, summit, weight=weight)
    except nx.NetworkXNoPath:
        raise ValueError(f"'{osm_name}' is not connected to the summit in OSM (add a GPS track)") from None


def find_routes(G, pois, cfg):
    """Every configured route as a list of OSM node ids.
    - list of POI keys (Horton Plains): shortest path through the POIs in order
    - {osm_name: ...} (Adam's Peak): trailhead -> summit along the named path, then back down the same way"""
    area = cfg["area"]
    poi_nodes, poi_points = {}, {}
    for key, name in (area.get("pois") or {}).items():
        p = pois[pois["name"] == name].iloc[0].geometry.centroid
        poi_nodes[key] = ox.distance.nearest_nodes(G, p.x, p.y)
        poi_points[key] = p
    if "summit_point" in area:
        lon, lat = area["summit_point"]
        poi_nodes["summit"] = SUMMIT_NODE if SUMMIT_NODE in G else ox.distance.nearest_nodes(G, lon, lat)
        poi_points["summit"] = Point(lon, lat)
    routes = {}
    for rname, spec in area["routes"].items():
        if isinstance(spec, dict):
            up = _named_route(G, spec["osm_name"], poi_nodes["summit"])
            routes[rname] = up + up[::-1][1:]
            head = up[0]
            poi_points[f"head_{rname}"] = Point(G.nodes[head]["x"], G.nodes[head]["y"])
            continue
        route = []
        for a, b in zip(spec[:-1], spec[1:]):
            leg = nx.shortest_path(G, poi_nodes[a], poi_nodes[b], weight="length")
            route += leg if not route else leg[1:]
        routes[rname] = route
    return routes, poi_points


def build_chains(G, routes: dict):
    """Merge the unique edges of all routes into chains between junctions."""
    H = nx.Graph()
    for r in routes.values():
        H.add_edges_from(zip(r[:-1], r[1:]))
    junctions = {n for n in H if H.degree(n) != 2} | {r[0] for r in routes.values()}
    chains, edge_to_chain, seen = [], {}, set()
    for j in sorted(junctions):
        for nb in sorted(H.neighbors(j)):
            if frozenset((j, nb)) in seen:
                continue
            path = [j, nb]
            while path[-1] not in junctions:
                path.append([n for n in H.neighbors(path[-1]) if n != path[-2]][0])
            cid = len(chains)
            for u, v in zip(path[:-1], path[1:]):
                seen.add(frozenset((u, v)))
                edge_to_chain[(u, v)] = (cid, +1)
                edge_to_chain[(v, u)] = (cid, -1)
            coords, edges = [], []
            for u, v in zip(path[:-1], path[1:]):
                c = _edge_coords(G, u, v)
                coords += c if not coords else c[1:]
                data = min(G.get_edge_data(u, v).values(), key=lambda d: d["length"])
                edges.append((float(data["length"]), "steps" in str(data.get("highway", ""))))
            chains.append({"nodes": path, "coords": coords, "edges": edges})
    return chains, edge_to_chain


def _steps_share(edges, a: float, b: float) -> float:
    """Share of the stretch [a, b] (fractions 0..1 of the chain length) that is OSM highway=steps."""
    total = sum(length for length, _ in edges) or 1.0
    pos, steps = 0.0, 0.0
    for length, is_steps in edges:
        lo, hi = pos / total, (pos + length) / total
        if is_steps:
            steps += max(0.0, min(hi, b) - max(lo, a))
        pos += length
    return steps / max(b - a, 1e-9)


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
                         "frac_steps": _steps_share(ch["edges"], i / k, (i + 1) / k),
                         "geometry": transform(to_ll, piece)})
    return segs


def route_to_segments(route, chains, edge_to_chain):
    """Walking order of one route as (segment id, direction) pairs; direction +1 = chain order."""
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


def segment_edges(segs, extra_links=()):
    """Undirected weighted adjacency: touching segments (weight 1) + road links. Returns edge_index, weight."""
    ends = {}
    for i, s in enumerate(segs):
        for key in (s["start"], s["end"]):
            ends.setdefault(key, []).append(i)
    w = {}
    for ids in ends.values():
        for a in ids:
            for b in ids:
                if a != b:
                    w[(a, b)] = 1.0
    for a, b, weight in extra_links:
        w.setdefault((a, b), weight)
        w.setdefault((b, a), weight)
    keys = sorted(w)
    return np.array(keys).T, np.array([w[k] for k in keys], dtype=np.float32)


def tag_pois(segs, poi_points, cfg):
    to_m = Transformer.from_crs("EPSG:4326", cfg["area"]["crs_metric"], always_xy=True).transform
    for s in segs:
        s["poi"] = ""
    for key, p in poi_points.items():
        pm = transform(to_m, p)
        d = [s["geom_m"].distance(pm) for s in segs]
        i = int(np.argmin(d))
        if d[i] <= cfg["graph"]["poi_snap_m"] and not segs[i]["poi"]:
            segs[i]["poi"] = key


def tag_halfway(segs, walks, cfg):
    """Halfway checkpoint of each named route (out and back to a summit): the first untagged segment at or after
    half of the way up. Officers hold groups there when the summit is full (docs/archive/adams_peak_plan.md)."""
    for r, spec in cfg["area"]["routes"].items():
        if not isinstance(spec, dict):
            continue
        up = walks[r][:len(walks[r]) // 2]
        cum = np.cumsum([segs[s]["length_m"] for s, _ in up])
        start = int(np.searchsorted(cum, cum[-1] * spec.get("checkpoint_at", 0.5)))
        for s, _ in up[start:-2]:                     # never the final steps or the summit itself
            if not segs[s]["poi"]:
                segs[s]["poi"] = f"half_{r}"
                break


def build_graph(cfg):
    G, pois = load_osm(cfg)
    routes, poi_points = find_routes(G, pois, cfg)
    chains, edge_to_chain = build_chains(G, routes)
    segs = split_chains(chains, cfg)
    tag_pois(segs, poi_points, cfg)
    walks = {r: route_to_segments(nodes, chains, edge_to_chain) for r, nodes in routes.items()}
    tag_halfway(segs, walks, cfg)

    # each segment belongs to the first route (config order) that walks it; position = order along that route
    trail, pos = [""] * len(segs), [0.0] * len(segs)
    for r, walk in walks.items():
        for k, (s, _) in enumerate(walk):
            if not trail[s]:
                trail[s], pos[s] = r, k / len(walk)

    poi_seg = {s["poi"]: i for i, s in enumerate(segs) if s["poi"]}
    links = [(poi_seg[a], poi_seg[b], float(wt)) for a, b, wt in cfg["area"].get("road_links", [])]
    edge_index, edge_weight = segment_edges(segs, links)

    gdf = gpd.GeoDataFrame(
        {"seg_id": range(len(segs)), "chain": [s["chain"] for s in segs],
         "trail": trail, "walk_position": [round(p, 4) for p in pos],
         "length_m": [round(s["length_m"], 1) for s in segs], "poi": [s["poi"] for s in segs],
         "frac_steps": [round(s["frac_steps"], 3) for s in segs]},
        geometry=[s["geometry"] for s in segs], crs="EPSG:4326")
    gdf.to_file(PROCESSED / "segments.geojson", driver="GeoJSON")
    np.save(PROCESSED / "edge_index.npy", edge_index)
    np.save(PROCESSED / "edge_weight.npy", edge_weight)
    (PROCESSED / "route.json").write_text(json.dumps({"walks": walks, "road_links": links}), encoding="utf-8")
    return gdf, edge_index, walks


def load_walks():
    js = json.loads((PROCESSED / "route.json").read_text(encoding="utf-8"))
    return {r: [tuple(x) for x in w] for r, w in js["walks"].items()}


if __name__ == "__main__":
    from src.config import load_config
    gdf, ei, walks = build_graph(load_config())
    print(f"segments={len(gdf)} edges={ei.shape[1] // 2}")
    print(gdf.groupby("trail").agg(segments=("seg_id", "count"), length_m=("length_m", "sum")).to_string())
    print({r: len(w) for r, w in walks.items()})
    print(gdf[gdf.poi != ""][["seg_id", "trail", "poi", "length_m"]].to_string(index=False))
