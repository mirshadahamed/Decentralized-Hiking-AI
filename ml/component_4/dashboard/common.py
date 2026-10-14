"""Shared, cached loaders and map helpers for the dashboard pages."""
import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pydeck as pdk
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]            # ml/component_4
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import PROCESSED, RESULTS, load_config  # noqa: E402

DOCS = ROOT / "docs"
POI_LABEL = {"entrance": "Visitor Center", "mini_worlds_end": "Mini World's End",
             "worlds_end": "World's End", "bakers_falls": "Baker's Falls"}
MODEL_LABEL = {"HA": "Historical average", "ARIMA": "SARIMA", "lstm": "LSTM",
               "gru_nograph": "GRU (no graph)", "stgnn": "ST-GNN (GCN + GRU)"}
MODEL_ORDER = ["HA", "ARIMA", "lstm", "gru_nograph", "stgnn"]
STATUS_COLOR = {"ok": [46, 139, 87], "busy": [224, 161, 0], "bottleneck": [192, 57, 43]}
VIEW = pdk.ViewState(latitude=6.792, longitude=80.798, zoom=13.2)


def require_dataset():
    if not (PROCESSED / "dataset.npz").exists():
        st.error("No dataset yet. From `ml/component_4` run: `.venv\\Scripts\\python.exe -m src.data.build_dataset`")
        st.stop()


@st.cache_resource
def get_cfg():
    return load_config()


@st.cache_resource
def get_data():
    from src.eval.data import TrailData
    return TrailData(get_cfg())


@st.cache_resource
def get_segments() -> gpd.GeoDataFrame:
    seg = gpd.read_file(PROCESSED / "segments.geojson")
    seg["poi"] = seg["poi"].fillna("")
    data = get_data()
    seg["walk_position"] = data.static[:, data.static_names.index("walk_position")]
    seg["label"] = [f"{i:02d} {POI_LABEL.get(p, '')}".strip() for i, p in zip(seg.seg_id, seg.poi)]
    return seg


@st.cache_resource
def get_extension():
    p = PROCESSED / "extension_trails.geojson"
    return gpd.read_file(p) if p.exists() else None


def walk_order() -> list:
    """Segment ids in the order a hiker meets them (standard direction)."""
    seg = get_segments()
    return seg.sort_values("walk_position").seg_id.tolist()


@st.cache_data
def summary() -> dict:
    p = PROCESSED / "dataset_summary.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


@st.cache_data
def calendar() -> pd.DataFrame:
    return pd.read_csv(PROCESSED / "calendar.csv", index_col=0, parse_dates=True)


def benchmark_runs(include_quick=False) -> list:
    runs = [p for p in RESULTS.glob("*_benchmark*") if (p / "metrics_temporal.csv").exists()]
    if not include_quick:
        runs = [p for p in runs if not p.name.endswith("_quick")]
    return sorted((p.name for p in runs), reverse=True)


@st.cache_data
def run_results(run_name: str) -> dict:
    run = RESULTS / run_name
    out = {"temporal": pd.read_csv(run / "metrics_temporal.csv")}
    if (run / "metrics_spatial_folds.csv").exists():
        out["spatial_folds"] = pd.read_csv(run / "metrics_spatial_folds.csv")
    if (run / "stats.json").exists():
        out["stats"] = json.loads((run / "stats.json").read_text(encoding="utf-8"))
    out["has_predictions"] = (run / "predictions_temporal.npz").exists()
    out["has_models"] = (run / "models" / "temporal_stgnn_s42.pt").exists()
    return out


@st.cache_data
def run_predictions(run_name: str) -> dict:
    z = np.load(RESULTS / run_name / "predictions_temporal.npz")
    return {k: z[k] for k in z.files}


@st.cache_resource
def get_model(run_name: str):
    """(model, scale) of the temporal ST-GNN, or None when the checkpoint is not on this machine."""
    from src.serve.predict import load_model
    try:
        model, scale, _ = load_model(get_data(), get_cfg(), run_name)
        return model, scale
    except FileNotFoundError:
        return None


@st.cache_data
def forecast(date: str, use_model: bool, run_name: str) -> dict:
    from src.serve.predict import build_forecast
    m = get_model(run_name) if use_model else None
    model, scale = m if m else (None, None)
    return build_forecast(get_data(), get_cfg(), get_segments(), date, model, scale, run_name)


def default_run() -> str | None:
    runs = benchmark_runs()
    latest = (RESULTS / "LATEST").read_text(encoding="utf-8").strip() if (RESULTS / "LATEST").exists() else None
    return latest if latest in runs else (runs[0] if runs else None)


# ---------- maps ----------
def _paths(geom):
    if geom.geom_type == "MultiLineString":
        return [list(map(list, g.coords)) for g in geom.geoms]
    return [list(map(list, geom.coords))]


def segment_layer(seg: gpd.GeoDataFrame, colors: list, extra: list | None = None, width=7):
    rows = []
    for i, r in enumerate(seg.itertuples()):
        for path in _paths(r.geometry):
            row = {"path": path, "color": colors[i], "name": r.label}
            for k, v in (extra[i] if extra else {}).items():
                row[k] = v
            rows.append(row)
    return pdk.Layer("PathLayer", rows, get_path="path", get_color="color", width_min_pixels=width,
                     pickable=True, cap_rounded=True, joint_rounded=True)


def poi_layer(seg: gpd.GeoDataFrame):
    rows = []
    for r in seg[seg.poi != ""].itertuples():
        p = r.geometry.interpolate(0.5, normalized=True)
        rows.append({"pos": [p.x, p.y], "text": POI_LABEL[r.poi]})
    return pdk.Layer("TextLayer", rows, get_position="pos", get_text="text", get_size=14,
                     get_color=[20, 20, 20], get_alignment_baseline="'bottom'", get_pixel_offset=[0, -10])


def extension_layers():
    ext = get_extension()
    if ext is None:
        return []
    trails = ext[ext.kind == "trail"]
    peaks = ext[ext.kind == "peak"]
    rows = [{"path": p, "name": f"{r.trail} trail (planned diversion, {r.length_m:.0f} m)", "color": [70, 110, 200]}
            for r in trails.itertuples() for p in _paths(r.geometry)]
    pts = [{"pos": [r.geometry.x, r.geometry.y], "name": f"{r.trail} peak", "text": r.trail} for r in peaks.itertuples()]
    return [pdk.Layer("PathLayer", rows, get_path="path", get_color="color", width_min_pixels=3,
                      pickable=True, opacity=0.7),
            pdk.Layer("ScatterplotLayer", pts, get_position="pos", get_fill_color=[70, 110, 200],
                      get_radius=60, pickable=True),
            pdk.Layer("TextLayer", pts, get_position="pos", get_text="text", get_size=13,
                      get_color=[40, 70, 160], get_pixel_offset=[0, -14])]


def deck(layers: list, tooltip_html: str, view=VIEW):
    return pdk.Deck(layers=layers, initial_view_state=view, map_provider="carto", map_style="light",
                    tooltip={"html": tooltip_html})


def gradient(values, lo=None, hi=None):
    """Light yellow -> dark red colours for a numeric array."""
    v = np.asarray(values, dtype=float)
    lo = np.nanmin(v) if lo is None else lo
    hi = np.nanmax(v) if hi is None else hi
    t = np.clip((v - lo) / (hi - lo + 1e-9), 0, 1)
    a, b, c = np.array([255, 237, 160]), np.array([240, 120, 40]), np.array([128, 0, 38])
    out = np.where(t[:, None] < 0.5, a + (b - a) * (t[:, None] / 0.5), b + (c - b) * ((t[:, None] - 0.5) / 0.5))
    return out.astype(int).tolist()
