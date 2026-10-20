"""Edge pack: everything a phone needs to run tomorrow's ST-GNN forecast itself, offline (objective O6).

The phone downloads one small JSON file while it has a connection (published by the daily refresh, served at
GET /edge/pack). It then builds the model inputs and runs the model in plain Dart
(lib/features/component_4/domain/edge_forecaster.dart) - no server, no internet needed afterwards.

Contents (schema "c4-edge-1"):
  model    : kind, rnn ("gru" | "lstm"), hidden size, every weight as {shape, data}, dense adjacency [N, N]
  inputs   : the raw ingredients, not the big tensors - scaled occupancy of the last L hours [L, N], scaled
             covariates of the last L and the next H hours [L, Fc] / [H, Fc], scaled segment descriptions [N, Fs],
             and which segments have counts [N]; the phone assembles x_past [L, N, 2+Fc+Fs] and
             x_fut [H, N, Fc+Fs] exactly like TrailData.batch
  scale    : people per model unit (output x scale = people)
  segments : id, trail, POI of each segment (for display)
  map      : (optional) segment lines + Cifuentes capacity + trail summaries, so the phone can draw the bottleneck
             map and the capacity table offline (map_extras)

    python -m src.edge.pack --fixture ../../test/component_4/fixtures/edge_pack.json
writes a pack for the first test day plus PyTorch's own output for it (the Dart parity test).
"""
import argparse
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import torch

SCHEMA = "c4-edge-1"


def _w(t: torch.Tensor) -> dict:
    a = t.detach().cpu().numpy().astype(np.float64)
    return {"shape": list(a.shape), "data": [round(float(x), 7) for x in a.ravel()]}


def build_pack(data, model, scale: float, origin: int, cfg: dict, seg=None, run: str | None = None,
               sensed: np.ndarray | None = None) -> dict:
    """Pack for the day starting at hour index `origin` of `data` (TrailData)."""
    sensed = np.ones(data.N, bool) if sensed is None else sensed
    L, H = data.L, data.H
    past, fut = np.arange(origin - L, origin), np.arange(origin, origin + H)
    state = {k: v for k, v in model.state_dict().items() if k != "adj"}
    rnn = "lstm" if isinstance(model.rnn, torch.nn.LSTM) else "gru"
    poi = [str(p) for p in data.segment_poi]
    return {
        "schema": SCHEMA, "park": cfg["park"], "model_run": run, "created": datetime.now().isoformat(timespec="seconds"),
        "day": str(data.times[origin].date()), "scale": float(scale),
        "model": {"rnn": rnn, "hidden": int(model.inp.out_features), "use_graph": bool(model.use_graph),
                  "adjacency": _w(model.adj), "weights": {k: _w(v) for k, v in state.items()}},
        "inputs": {
            "occupancy_past": [[round(float(x), 6) for x in row] for row in (data.y[past] / scale)],
            "covariates_past": [[round(float(x), 6) for x in row] for row in data.cov_s[past]],
            "covariates_future": [[round(float(x), 6) for x in row] for row in data.cov_s[fut]],
            "static": [[round(float(x), 6) for x in row] for row in data.static_s],
            "sensed": [bool(x) for x in sensed],
            "covariate_names": list(data.cov_names), "static_names": list(data.static_names),
        },
        "segments": [{"id": int(i), "trail": str(t), "poi": p} for i, (t, p) in
                     enumerate(zip(data.segment_trail, poi))],
        "note": "Occupancy is forecast from a model trained on a SYNTHETIC occupancy target (see the server's "
                "forecast note).",
    }


def map_extras(forecast: dict, seg, cfg: dict, data=None) -> dict:
    """What the phone needs to draw the bottleneck map and the capacity table offline (optional "map" key):
    each segment's line (simplified, lon/lat), Cifuentes capacity (people at once, PCC / RCC / ECC per day),
    the trail summaries (recommended daily number, limiting segment) and the open hours.
    With `data` (TrailData) also the walking minutes from the trail start to each segment, so the phone can work
    out where a hiker will be at each hour (offline walk advice).
    `forecast` is build_forecast()'s output for the pack's day (the server's capacity answer)."""
    by_id = {s["seg_id"]: s for s in forecast["segments"]}
    c, sim = cfg["capacity"], cfg["simulator"]
    minutes = walk = None
    if data is not None:
        names = list(data.static_names)
        minutes = data.static[:, names.index("minutes_from_trailhead")]
        # minutes spent on the segment itself: walking at leisure speed + the stop at a viewpoint
        walk = data.static[:, names.index("tobler_fwd_min")] / sim["leisure_speed_factor"] + \
            data.static[:, names.index("dwell_min")]
    lines = []
    for _, r in seg.sort_values("seg_id").iterrows():
        g = r.geometry.simplify(0.00002)                       # ~2 m: invisible on a phone map, 3x smaller
        parts = list(g.geoms) if g.geom_type == "MultiLineString" else [g]
        s = by_id[int(r.seg_id)]
        lines.append({
            "id": int(r.seg_id), "lines": [[[round(x, 5), round(y, 5)] for x, y in p.coords] for p in parts],
            "length_m": round(float(r.length_m)), "capacity_at_once": s["capacity_at_once"],
            "pcc_per_day": s["pcc_per_day"], "rcc_per_day": s["rcc_per_day"], "ecc_per_day": s["ecc_per_day"],
            "status": s["status"],
        })
        if minutes is not None:
            lines[-1]["minutes_from_start"] = round(float(minutes[int(r.seg_id)]), 1)
            lines[-1]["minutes_on_segment"] = round(float(walk[int(r.seg_id)]), 1)
    return {
        "open_hours": [int((c.get("open_from_h", 6) + k) % 24) for k in range(c["open_hours"])],
        "last_entry_hour": sim.get("gate_last_entry_h"),
        "reversible_trails": list(sim.get("reversible_routes", [])),
        "main_trail": cfg["area"].get("main_trail", "main"),
        "busy_utilisation": c["busy_utilisation"],
        "segments": lines,
        "trails": {t: {k: v[k] for k in ("name", "expected_visitors", "recommended_daily_quota",
                                         "classic_cifuentes_quota", "limiting_segment", "factors")}
                   for t, v in forecast["trails"].items()},
        "expected_visitors": forecast.get("expected_visitors"),
        "recommended_daily_quota": forecast.get("recommended_daily_quota"),
        "classic_cifuentes_quota": forecast.get("classic_cifuentes_quota"),
        "rain_share_open_hours": forecast.get("rain_share_open_hours"),
        "disclaimer": forecast.get("disclaimer", ""),
    }


def torch_forecast(model, data, origin: int, scale: float) -> np.ndarray:
    """[H, N] people from PyTorch (the reference the Dart engine must match)."""
    xp, xf, _, _ = data.batch(np.array([origin]), np.ones(data.N, bool), scale)
    with torch.no_grad():
        return np.clip(model(xp, xf).numpy()[0] * scale, 0, None)


if __name__ == "__main__":
    import geopandas as gpd

    from src.config import PROCESSED, load_config
    from src.eval.data import TrailData
    from src.serve.predict import build_forecast, load_model
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", required=True, help="where to write the pack + PyTorch output for the Dart test")
    a = ap.parse_args()
    cfg = load_config()
    data = TrailData(cfg)
    model, scale, run = load_model(data, cfg)
    model.eval()
    origin = int(data.origins("test")[100])
    pack = build_pack(data, model, scale, origin, cfg, run=run)
    seg = gpd.read_file(PROCESSED / "segments.geojson")
    seg["poi"] = seg["poi"].fillna("")
    pack["map"] = map_extras(build_forecast(data, cfg, seg, pack["day"], model, scale, run), seg, cfg, data)
    pack["expected_people"] = [[round(float(x), 5) for x in row] for row in torch_forecast(model, data, origin, scale)]
    Path(a.fixture).parent.mkdir(parents=True, exist_ok=True)
    Path(a.fixture).write_text(json.dumps(pack, separators=(",", ":")), encoding="utf-8")
    print(a.fixture, f"{Path(a.fixture).stat().st_size / 1024:.0f} KB")
