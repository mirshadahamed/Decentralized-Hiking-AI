"""Paths and config loading for Component 4, per park.

The park is chosen with the environment variable C4_PARK (default: horton_plains):
    $env:C4_PARK = "adams_peak"; .venv\\Scripts\\python.exe -m src.data.build_dataset
- horton_plains keeps the original folders (data/, results/) and configs/default.yaml.
- any other park reads configs/default.yaml overridden by configs/parks/<park>.yaml and uses
  data/<park>/ and results/<park>/.
"""
import copy
import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]          # research/component_4
CONFIGS = ROOT / "configs"
DEFAULT_PARK = "horton_plains"
PARK = os.environ.get("C4_PARK", DEFAULT_PARK)

DATA = ROOT / "data" if PARK == DEFAULT_PARK else ROOT / "data" / PARK
RAW = DATA / "raw"
INTERIM = DATA / "interim"
PROCESSED = DATA / "processed"
RESULTS = ROOT / "results" if PARK == DEFAULT_PARK else ROOT / "results" / PARK
FIGURES = RESULTS / "figures"

for _p in (RAW, INTERIM, PROCESSED, RESULTS, FIGURES):
    _p.mkdir(parents=True, exist_ok=True)


def processed_dir(park: str) -> Path:
    """data/processed of any park (for experiments that use two parks at once)."""
    return (ROOT / "data" if park == DEFAULT_PARK else ROOT / "data" / park) / "processed"


def parks() -> list:
    return [DEFAULT_PARK] + sorted(p.stem for p in (CONFIGS / "parks").glob("*.yaml") if p.stem != DEFAULT_PARK)


def _merge(base: dict, over: dict) -> dict:
    """Deep merge: dicts are merged key by key, everything else (lists, numbers) is replaced.
    A dict with `__replace__: true` replaces the base dict completely (e.g. a park's own POIs and routes)."""
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and v.get("__replace__"):
            out[k] = _strip(v)
        elif isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = _strip(v) if isinstance(v, dict) else copy.deepcopy(v)
    return out


def _strip(d: dict) -> dict:
    return {k: (_strip(v) if isinstance(v, dict) else copy.deepcopy(v)) for k, v in d.items() if k != "__replace__"}


def load_config(name: str = "default", park: str | None = None) -> dict:
    park = park or PARK
    with open(CONFIGS / f"{name}.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    over = CONFIGS / "parks" / f"{park}.yaml"
    if park != DEFAULT_PARK and over.exists():
        with open(over, encoding="utf-8") as f:
            cfg = _merge(cfg, yaml.safe_load(f))
    cfg["park"] = park
    return cfg


def _modes(cfg):
    from src.control import modes                     # lazy: src.control imports src.config
    return modes


def destination_info(cfg: dict) -> dict:
    """What the app's trip planner shows for a park (gateway /parks and the park's own /destination)."""
    d, a = cfg.get("destination", {}), cfg["area"]
    lat, lon = a["weather_point"]
    return {"id": cfg["park"], "name": a["name"], "kind": d.get("kind", "park"), "region": d.get("region", ""),
            "summary": d.get("summary", ""), "elevation": d.get("elevation", ""), "best_time": d.get("best_time", ""),
            "getting_there": d.get("getting_there", ""), "facts": d.get("facts", []), "accent": d.get("accent", ""),
            "booking_mode": cfg["control"].get("booking_mode", "required"),
            "trail_modes": _modes(cfg).trail_modes(cfg), "modes": _modes(cfg).park_modes(cfg),
            "trails": a["trail_names"], "trail_info": a.get("trail_info", {}), "center": {"lat": lat, "lon": lon}}
