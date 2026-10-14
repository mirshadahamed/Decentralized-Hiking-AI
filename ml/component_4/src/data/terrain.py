"""Terrain features per segment from the Copernicus GLO-30 DEM (slope, TWI, Tobler time)."""
import math

import geopandas as gpd
import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.windows import from_bounds
from shapely.ops import transform

from src.config import PROCESSED, RAW

DEM_URL = ("https://copernicus-dem-30m.s3.amazonaws.com/"
           "Copernicus_DSM_COG_10_N06_00_E080_00_DEM/Copernicus_DSM_COG_10_N06_00_E080_00_DEM.tif")
PROFILE_STEP_M = 30.0
MAX_GRADE = 0.25
WET_TWI = 8.0   # cells at or above this TWI are treated as waterlogging-prone (erodible when wet)


def load_dem(cfg):
    """Read the DEM window over the park (cached as data/raw/dem.tif)."""
    path = RAW / "dem.tif"
    if not path.exists():
        with rasterio.open(DEM_URL) as src:
            win = from_bounds(*cfg["area"]["dem_bbox"], src.transform)
            z = src.read(1, window=win)
            profile = src.profile | {"height": z.shape[0], "width": z.shape[1],
                                     "transform": src.window_transform(win), "driver": "GTiff"}
        with rasterio.open(path, "w", **profile) as dst:
            dst.write(z, 1)
    with rasterio.open(path) as src:
        return src.read(1).astype(float), src.transform


def cell_size_m(transform_, lat):
    dx = transform_.a * 111_320 * math.cos(math.radians(lat))
    dy = -transform_.e * 110_574
    return dx, dy


def flow_accumulation(z):
    """D8 flow accumulation (number of upslope cells, including itself)."""
    H, W = z.shape
    acc = np.ones(H * W)
    zf = z.ravel().tolist()
    nbrs = [(-1, -1, math.sqrt(2)), (-1, 0, 1), (-1, 1, math.sqrt(2)), (0, -1, 1),
            (0, 1, 1), (1, -1, math.sqrt(2)), (1, 0, 1), (1, 1, math.sqrt(2))]
    for idx in np.argsort(z, axis=None)[::-1].tolist():
        r, c = divmod(idx, W)
        best, target = 0.0, -1
        for dr, dc, d in nbrs:
            rr, cc = r + dr, c + dc
            if 0 <= rr < H and 0 <= cc < W:
                s = (zf[idx] - zf[rr * W + cc]) / d
                if s > best:
                    best, target = s, rr * W + cc
        if target >= 0:
            acc[target] += acc[idx]
    return acc.reshape(H, W)


def twi_raster(z, transform_, lat):
    """Topographic Wetness Index = ln(a / tan(beta))."""
    dx, dy = cell_size_m(transform_, lat)
    gy, gx = np.gradient(z, dy, dx)
    tan_b = np.maximum(np.hypot(gx, gy), 1e-3)
    a = flow_accumulation(z) * dx  # specific catchment area (m^2 per m of contour)
    return np.log(a / tan_b), np.degrees(np.arctan(tan_b))


def tobler_kmh(grade):
    """Tobler's hiking function; grade = dh/dx (signed, in walking direction)."""
    return 6.0 * np.exp(-3.5 * np.abs(grade + 0.05))


def sample(raster, transform_, lon, lat):
    rows, cols = rasterio.transform.rowcol(transform_, lon, lat)
    rows = np.clip(rows, 0, raster.shape[0] - 1)
    cols = np.clip(cols, 0, raster.shape[1] - 1)
    return raster[rows, cols]


def segment_terrain(cfg):
    gdf = gpd.read_file(PROCESSED / "segments.geojson")
    z, tf = load_dem(cfg)
    lat0 = cfg["area"]["weather_point"][0]
    twi, slope_deg = twi_raster(z, tf, lat0)
    to_m = Transformer.from_crs("EPSG:4326", cfg["area"]["crs_metric"], always_xy=True).transform
    to_ll = Transformer.from_crs(cfg["area"]["crs_metric"], "EPSG:4326", always_xy=True).transform

    rows = []
    for geom in gdf.geometry:
        line = transform(to_m, geom)
        n = max(2, int(line.length // PROFILE_STEP_M) + 1)
        dists = np.linspace(0, line.length, n)
        pts = [transform(to_ll, line.interpolate(d)) for d in dists]
        lon, lat = np.array([p.x for p in pts]), np.array([p.y for p in pts])
        elev = sample(z, tf, lon, lat)
        # Smooth over 5 samples (~150 m) and cap the grade: next to the World's End escarpment
        # the 30 m DEM cells mix in the cliff drop, which is not the trail's real gradient.
        elev_s = np.convolve(np.pad(elev, 2, mode="edge"), np.ones(5) / 5, mode="valid")
        dx = np.diff(dists)
        grade = np.clip(np.diff(elev_s) / dx, -MAX_GRADE, MAX_GRADE)
        dh = grade * dx
        fwd_min = float(np.sum(dx / 1000 / tobler_kmh(grade)) * 60)
        bwd_min = float(np.sum(dx / 1000 / tobler_kmh(-grade)) * 60)
        twi_pts = sample(twi, tf, lon, lat)
        rows.append({
            # length fractions used by the Cifuentes correction factors
            "frac_grade_med": float(dx[(np.abs(grade) >= 0.10) & (np.abs(grade) < 0.20)].sum() / dx.sum()),
            "frac_grade_high": float(dx[np.abs(grade) >= 0.20].sum() / dx.sum()),
            "frac_wet": float((twi_pts >= WET_TWI).mean()),
            "elev_mean": float(elev.mean()),
            "elev_gain_fwd": float(np.clip(dh, 0, None).sum()),
            "grade_abs_mean": float(np.abs(grade).mean()),
            "slope_deg_mean": float(sample(slope_deg, tf, lon, lat).mean()),
            "twi_mean": float(twi_pts.mean()),
            "tobler_fwd_min": fwd_min,
            "tobler_bwd_min": bwd_min,
        })
    for k in rows[0]:
        gdf[k] = [round(r[k], 4) for r in rows]
    gdf.to_file(PROCESSED / "segments.geojson", driver="GeoJSON")
    return gdf


if __name__ == "__main__":
    from src.config import load_config
    g = segment_terrain(load_config())
    print(g.drop(columns="geometry").round(2).to_string(index=False))
    print(f"loop walking time (Tobler, one way per segment): {g.tobler_fwd_min.sum():.0f} min")
