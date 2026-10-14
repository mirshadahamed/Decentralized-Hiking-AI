"""Kirigalpotta and Thotupola trails from OSM, for the planned diversion extension (map layer only for now)."""
import geopandas as gpd
import osmnx as ox
import pandas as pd
from shapely.ops import linemerge

from src.config import PROCESSED, RAW

TRAIL_FILTER = '["highway"~"path|footway|track|steps"]'


def build_extension_trails(cfg) -> gpd.GeoDataFrame:
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(RAW / "osm_cache")
    ext = cfg["extension"]
    bbox = tuple(ext["bbox"])
    G = ox.graph_from_bbox(bbox, custom_filter=TRAIL_FILTER, simplify=True, retain_all=True)
    edges = ox.graph_to_gdfs(ox.convert.to_undirected(G), nodes=False)
    edges["name"] = edges["name"].astype(str)
    rows = []
    for trail, osm_name in ext["trails"].items():
        sel = edges[edges["name"] == osm_name]
        geom = linemerge(list(sel.geometry))
        length_m = float(sel["length"].sum())
        rows.append({"trail": trail, "kind": "trail", "length_m": round(length_m), "geometry": geom})
    peaks = ox.features_from_bbox(bbox, tags={"natural": "peak"})
    for name in ext["peaks"]:
        p = peaks[peaks["name"] == name]
        if len(p):
            rows.append({"trail": name, "kind": "peak", "length_m": None,
                         "ele_m": pd.to_numeric(p.iloc[0].get("ele"), errors="coerce"),
                         "geometry": p.iloc[0].geometry.centroid})
    gdf = gpd.GeoDataFrame(rows, crs="EPSG:4326")
    gdf.to_file(PROCESSED / "extension_trails.geojson", driver="GeoJSON")
    return gdf


if __name__ == "__main__":
    from src.config import load_config
    g = build_extension_trails(load_config())
    print(g.drop(columns="geometry").to_string(index=False))
