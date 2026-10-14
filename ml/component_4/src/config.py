"""Paths and config loading for Component 4."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]          # ml/component_4
DATA = ROOT / "data"
RAW = DATA / "raw"
INTERIM = DATA / "interim"
PROCESSED = DATA / "processed"
RESULTS = ROOT / "results"
FIGURES = RESULTS / "figures"
CONFIGS = ROOT / "configs"

for _p in (RAW, INTERIM, PROCESSED, RESULTS, FIGURES):
    _p.mkdir(parents=True, exist_ok=True)


def load_config(name: str = "default") -> dict:
    with open(CONFIGS / f"{name}.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)
