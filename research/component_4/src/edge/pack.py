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
import pandas as pd
import torch

SCHEMA = "c4-edge-1"


def _w(t: torch.Tensor) -> dict:
    a = t.detach().cpu().numpy().astype(np.float64)
    return {"shape": list(a.shape), "data": [round(float(x), 7) for x in a.ravel()]}


def _day_inputs(data, origin: int, scale: float, sensed: np.ndarray) -> dict:
    """The parts of the model input that change from day to day (scaled like TrailData.batch). Counts of segments
    the model does not read are sent as 0: the phone gets only what the park measures (the gates, G6)."""
    past, fut = np.arange(origin - data.L, origin), np.arange(origin, origin + data.H)
    return {
        "occupancy_past": [[round(float(x), 6) for x in row] for row in (data.y[past] / scale * sensed)],
        "covariates_past": [[round(float(x), 6) for x in row] for row in data.cov_s[past]],
        "covariates_future": [[round(float(x), 6) for x in row] for row in data.cov_s[fut]],
    }


def build_pack(data, model, scale: float, origin: int, cfg: dict, seg=None, run: str | None = None,
               sensed: np.ndarray | None = None, extra_origins=()) -> dict:
    """Pack for the day starting at hour index `origin` of `data` (TrailData). `extra_origins`: other days the
    phone should also forecast itself (e.g. today), stored as "extra_inputs" {date: day inputs}."""
    from src.serve.predict import model_inputs
    sensed = model_inputs(model, data) if sensed is None else sensed
    state = {k: v for k, v in model.state_dict().items() if k != "adj"}
    rnn = "lstm" if isinstance(model.rnn, torch.nn.LSTM) else "gru"
    poi = [str(p) for p in data.segment_poi]
    return {
        "schema": SCHEMA, "park": cfg["park"], "model_run": run, "created": datetime.now().isoformat(timespec="seconds"),
        "day": str(data.times[origin].date()), "scale": float(scale),
        "model": {"rnn": rnn, "hidden": int(model.inp.out_features), "use_graph": bool(model.use_graph),
                  "adjacency": _w(model.adj), "weights": {k: _w(v) for k, v in state.items()}},
        "extra_inputs": {str(data.times[o].date()): _day_inputs(data, int(o), scale, sensed) for o in extra_origins
                         if data.L <= o <= data.T - data.H},
        "inputs": {
            **_day_inputs(data, origin, scale, sensed),
            "static": [[round(float(x), 6) for x in row] for row in data.static_s],
            "sensed": [bool(x) for x in sensed],
            "covariate_names": list(data.cov_names), "static_names": list(data.static_names),
        },
        "segments": [{"id": int(i), "trail": str(t), "poi": p} for i, (t, p) in
                     enumerate(zip(data.segment_trail, poi))],
        "poi_labels": dict(cfg["area"].get("poi_labels", {})),       # "worlds_end" -> "World's End", per park
        "note": "Occupancy is forecast from a model trained on a SYNTHETIC occupancy target (see the server's "
                "forecast note).",
    }


def _day_block(date: str, source: str, fc: dict, people: bool) -> dict:
    """Capacity (and, for days the phone cannot forecast itself, the people per hour) of one day."""
    out = {
        "date": date, "source": source,
        "segments": [{"id": int(s["seg_id"]), "capacity_at_once": s["capacity_at_once"], "pcc_per_day": s["pcc_per_day"],
                      "rcc_per_day": s["rcc_per_day"], "ecc_per_day": s["ecc_per_day"], "status": s["status"]}
                     for s in fc["segments"]],
        "trails": {t: {k: v[k] for k in ("name", "expected_visitors", "recommended_daily_quota",
                                         "classic_cifuentes_quota", "limiting_segment", "factors")}
                   for t, v in fc["trails"].items()},
        "expected_visitors": fc.get("expected_visitors"),
        "recommended_daily_quota": fc.get("recommended_daily_quota"),
        "classic_cifuentes_quota": fc.get("classic_cifuentes_quota"),
        "rain_share_open_hours": fc.get("rain_share_open_hours"),
    }
    if people:                                                   # [hour][segment], same layout as the phone's output
        hourly = np.array([s["forecast_hourly"] for s in sorted(fc["segments"], key=lambda s: s["seg_id"])]).T
        out["people"] = [[round(float(v), 1) for v in row] for row in hourly]
    return out


def week_forecasts(data, cfg, seg, model, scale, run, today: str, planner, days: int = 7, plan_kwargs=None):
    """Today and tomorrow from the ST-GNN (the phone repeats these itself), later days from the planning model.
    plan_kwargs(date) -> rain_share / wetness / conditions for planner.day (the live service's inputs).
    Returns [(date, source, forecast dict)]."""
    from src.serve.predict import build_forecast
    out = []
    t0 = pd.Timestamp(today)
    for k in range(days):
        d = (t0 + pd.Timedelta(days=k)).date().isoformat()
        try:
            if k <= 1:
                out.append((d, "stgnn", build_forecast(data, cfg, seg, d, model, scale, run)))
            else:
                p = planner.day(today, d, **(plan_kwargs(d) if plan_kwargs else {}))
                out.append((d, "planning", p["capacity"]))
        except ValueError:                                       # outside the data / the outlook
            continue
    return out


def crowd_calibration(model, data, scale: float, cfg: dict, run: str | None = None) -> dict:
    """A5 / S3: P(really over capacity | forecast fullness) from the model's validation year, so the phone can say
    "70 % chance over capacity" instead of a single number (src/eval/uncertainty.py). Cached in the model's run."""
    from src.config import PARK, RESULTS
    from src.eval.bottlenecks import capacity_at_once
    from src.eval.uncertainty import _flat, calibrate
    from src.serve.predict import model_inputs
    from src.train.trainer import predict
    path = RESULTS / run / "crowd_calibration.json" if run else None
    if path is not None and path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    va = data.origins("val")
    y, open_ = data.targets(va)
    cap = capacity_at_once(cfg, PARK)
    u, t = _flat(predict(model, data, va, model_inputs(model, data), scale), y, open_, cap, np.arange(data.N))
    table = calibrate(u, t) | {"basis": "validation year of the deployed model (simulated counts)"}
    if path is not None:
        path.write_text(json.dumps(table), encoding="utf-8")
    return table


def map_extras(forecast: dict, seg, cfg: dict, data=None, week=None, calibration: dict | None = None) -> dict:
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
        # the week: today .. +6 days; "stgnn" days are forecast on the phone (inputs / extra_inputs), "planning"
        # days carry the planning model's people per hour
        "days": [_day_block(d, src, fc, people=src != "stgnn") for d, src, fc in (week or [])],
        # chance of really being over capacity for a forecast fullness (bins = forecast / capacity_at_once)
        **({"calibration": calibration} if calibration else {}),
    }


def torch_forecast(model, data, origin: int, scale: float) -> np.ndarray:
    """[H, N] people from PyTorch (the reference the Dart engine must match)."""
    from src.serve.predict import model_inputs
    xp, xf, _, _ = data.batch(np.array([origin]), model_inputs(model, data), scale)
    with torch.no_grad():
        return np.clip(model(xp, xf).numpy()[0] * scale, 0, None)


if __name__ == "__main__":
    import geopandas as gpd

    from src.config import PROCESSED, load_config
    from src.eval.data import TrailData
    from src.serve.outlook import build_planner
    from src.serve.predict import build_forecast, load_model
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", required=True, help="where to write the pack + PyTorch output for the Dart test")
    a = ap.parse_args()
    cfg = load_config()
    data = TrailData(cfg)
    model, scale, run = load_model(data, cfg)
    model.eval()
    origin = int(data.origins("test")[100])                     # "tomorrow"; "today" = the day before
    pack = build_pack(data, model, scale, origin, cfg, run=run, extra_origins=[origin - 24])
    seg = gpd.read_file(PROCESSED / "segments.geojson")
    seg["poi"] = seg["poi"].fillna("")
    today = str(data.times[origin - 24].date())
    week = week_forecasts(data, cfg, seg, model, scale, run, today, build_planner(cfg))
    pack["map"] = map_extras(build_forecast(data, cfg, seg, pack["day"], model, scale, run), seg, cfg, data, week,
                             crowd_calibration(model, data, scale, cfg, run))
    from src.live.refresh import add_week_weather
    from src.serve.weather_day import ResearchWeather
    add_week_weather(ResearchWeather(cfg), pack["map"])               # W-d: the week's weather, offline
    pack["expected_people"] = [[round(float(x), 5) for x in row] for row in torch_forecast(model, data, origin, scale)]
    pack["expected_people_today"] = [[round(float(x), 5) for x in row]
                                     for row in torch_forecast(model, data, origin - 24, scale)]
    Path(a.fixture).parent.mkdir(parents=True, exist_ok=True)
    Path(a.fixture).write_text(json.dumps(pack, separators=(",", ":")), encoding="utf-8")
    print(a.fixture, f"{Path(a.fixture).stat().st_size / 1024:.0f} KB")
