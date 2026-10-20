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


def torch_forecast(model, data, origin: int, scale: float) -> np.ndarray:
    """[H, N] people from PyTorch (the reference the Dart engine must match)."""
    xp, xf, _, _ = data.batch(np.array([origin]), np.ones(data.N, bool), scale)
    with torch.no_grad():
        return np.clip(model(xp, xf).numpy()[0] * scale, 0, None)


if __name__ == "__main__":
    from src.config import load_config
    from src.eval.data import TrailData
    from src.serve.predict import load_model
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", required=True, help="where to write the pack + PyTorch output for the Dart test")
    a = ap.parse_args()
    cfg = load_config()
    data = TrailData(cfg)
    model, scale, run = load_model(data, cfg)
    model.eval()
    origin = int(data.origins("test")[100])
    pack = build_pack(data, model, scale, origin, cfg, run=run)
    pack["expected_people"] = [[round(float(x), 5) for x in row] for row in torch_forecast(model, data, origin, scale)]
    Path(a.fixture).parent.mkdir(parents=True, exist_ok=True)
    Path(a.fixture).write_text(json.dumps(pack, separators=(",", ":")), encoding="utf-8")
    print(a.fixture, f"{Path(a.fixture).stat().st_size / 1024:.0f} KB")
