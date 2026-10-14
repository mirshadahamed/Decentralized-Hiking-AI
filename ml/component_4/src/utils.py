"""Seeding and run logging, so every result can be reproduced."""
import json
import os
import random
import subprocess
from datetime import datetime

import numpy as np
import torch

from src.config import RESULTS


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


def git_hash() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def new_run_dir(tag: str, cfg: dict):
    """Create results/<timestamp>_<tag>/ and store the config, seed and git hash in it."""
    run = RESULTS / f"{datetime.now():%Y%m%d_%H%M%S}_{tag}"
    run.mkdir(parents=True, exist_ok=True)
    meta = {"tag": tag, "git": git_hash(), "created": datetime.now().isoformat(), "config": cfg}
    (run / "run.json").write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
    return run
