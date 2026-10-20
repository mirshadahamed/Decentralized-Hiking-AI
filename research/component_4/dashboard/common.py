"""Shared, cached loaders and map helpers for the dashboard pages."""
import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pydeck as pdk
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]            # research/component_4
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import PROCESSED, RESULTS, load_config  # noqa: E402

DOCS = ROOT / "docs"
POI_LABEL = {"entrance": "Visitor Center", "mini_worlds_end": "Mini World's End",
             "worlds_end": "World's End", "bakers_falls": "Baker's Falls",
             "kirigalpotta_peak": "Kirigalpotta peak", "thotupola_head": "Thotupola trailhead",
             "thotupola_peak": "Thotupola Kanda"}
TRAIL_SHORT = {"main": "Loop", "kirigalpotta": "Kirigalpotta", "thotupola": "Thotupola"}
TRAIL_COLOR = {"main": [27, 127, 90], "kirigalpotta": [91, 139, 208], "thotupola": [192, 122, 44]}
MODEL_LABEL = {"HA": "Historical average", "ARIMA": "SARIMA", "lstm": "LSTM",
               "gru_nograph": "GRU (no graph)", "stgnn": "ST-GNN (GCN + GRU)"}
MODEL_ORDER = ["HA", "ARIMA", "lstm", "gru_nograph", "stgnn"]
STATUS_COLOR = {"ok": [46, 139, 87], "busy": [224, 161, 0], "bottleneck": [192, 57, 43]}
VIEW = pdk.ViewState(latitude=6.807, longitude=80.792, zoom=12.4)


def require_dataset():
    if not (PROCESSED / "dataset.npz").exists():
        st.error("No dataset yet. From `research/component_4` run: `.venv\\Scripts\\python.exe -m src.data.build_dataset`")
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
    seg["label"] = [f"{i:02d} {TRAIL_SHORT[t]}" + (f" · {POI_LABEL[p]}" if p else "")
                    for i, t, p in zip(seg.seg_id, seg.trail, seg.poi)]
    return seg


def walk_order() -> list:
    """Segment ids trail by trail, each in the order a hiker meets them."""
    return [int(i) for i in get_data().walk_order()]


def trail_names() -> dict:
    return get_cfg()["area"]["trail_names"]


@st.cache_resource
def get_planner():
    from src.serve.outlook import build_planner
    return build_planner(get_cfg())


@st.cache_data
def plan_outlook(issue: str) -> pd.DataFrame:
    return get_planner().m.outlook(issue)


@st.cache_data
def plan_day(issue: str, target: str) -> dict:
    return get_planner().day(issue, target)


@st.cache_resource
def get_control():
    from src.control.slots import build_control
    return build_control()


class capacity_standard:
    """Temporarily use another capacity standard (the control object is shared and cached)."""
    def __init__(self, scale):
        self.ec, self.scale = get_control(), scale

    def __enter__(self):
        self.old = self.ec.c.get("capacity_scale", 1.0)
        self.ec.c["capacity_scale"] = self.scale
        return self.ec

    def __exit__(self, *a):
        self.ec.c["capacity_scale"] = self.old


@st.cache_data
def day_rain_share(day: str) -> float:
    data, cfg = get_data(), get_cfg()
    i = int(np.searchsorted(data.times, pd.Timestamp(day)))
    rain = np.expm1(data.cov[i + 6:i + 6 + cfg["capacity"]["open_hours"], data.cov_names.index("precip_log1p")])
    return float((rain >= cfg["capacity"]["rain_mm"]).mean())


@st.cache_data
def control_day(day: str, scale: float, seed: int = 3) -> dict:
    """One day: ticket plan, and the same visitors with no limit (A) vs slot tickets + moving (D)."""
    from src.control.evaluate import admit
    from src.sim.simulator import daily_demand
    with capacity_standard(scale) as ec:
        rain = day_rain_share(day)
        quota = ec.daily_quota(rain)
        plan = ec.plan(rain, quota)
        C = ec.capacity(rain)
        cal = calendar()
        i = int(np.searchsorted(cal.index, pd.Timestamp(day)))
        precip = np.expm1(get_data().cov[i * 24:(i + 1) * 24, get_data().cov_names.index("precip_log1p")])
        n = daily_demand(cal.iloc[[i]], precip[None, :], get_cfg()["simulator"], np.random.default_rng(seed))[0]
        size, gate, option = ec.sim.sample_day(int(round(n)), np.random.default_rng(seed))
        out = {"plan": plan, "capacity": C, "quota": quota, "rain_share": rain, "wanted": float(size.sum())}
        for pol in ("A", "D"):
            s, g, o, moved = admit(pol, ec, size, gate, option, quota, plan, np.random.default_rng(seed + 1))
            _, per_min, _ = ec.sim.simulate_groups(s, g, o, precip, np.random.default_rng(seed + 2))
            out[pol] = {"occ": per_min.reshape(ec.sim.S, ec.n_bins, -1).mean(-1), "admitted": float(s.sum()), **moved,
                        "groups": pd.DataFrame({"trail": [ec.sim.options[x][0] for x in o], "gate_min": g, "size": s})}
        return out


def latest_control_eval():
    p = RESULTS / "LATEST_CONTROL"
    run = RESULTS / p.read_text(encoding="utf-8").strip() if p.exists() else None
    return run if run is not None and (run / "summary.csv").exists() else None


def latest_planning_backtest():
    p = RESULTS / "LATEST_PLANNING"
    run = RESULTS / p.read_text(encoding="utf-8").strip() if p.exists() else None
    return run if run is not None and (run / "metrics_by_lead.csv").exists() else None


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
    """(model, scale) of the temporal ST-GNN, or None when the checkpoint is missing or was trained
    on a different graph (e.g. before the three-trail network)."""
    from src.serve.predict import load_model
    try:
        model, scale, _ = load_model(get_data(), get_cfg(), run_name)
        return model, scale
    except (FileNotFoundError, RuntimeError):
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
        rows.append({"pos": [p.x, p.y], "text": POI_LABEL.get(r.poi, r.poi)})
    return pdk.Layer("TextLayer", rows, get_position="pos", get_text="text", get_size=14,
                     get_color=[20, 20, 20], get_alignment_baseline="'bottom'", get_pixel_offset=[0, -10])


def road_link_layer(seg: gpd.GeoDataFrame):
    """Dashed-look thin line for trails joined only by road (e.g. Visitor Center -> Thotupola trailhead)."""
    js = json.loads((PROCESSED / "route.json").read_text(encoding="utf-8"))
    s = seg.set_index("seg_id")
    rows = []
    for a, b, _ in js.get("road_links", []):
        pa, pb = s.loc[a].geometry.centroid, s.loc[b].geometry.centroid
        rows.append({"path": [[pa.x, pa.y], [pb.x, pb.y]], "name": "Road link (4.2 km drive)", "color": [120, 120, 120]})
    return pdk.Layer("PathLayer", rows, get_path="path", get_color="color", width_min_pixels=2,
                     pickable=True, opacity=0.6)


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
