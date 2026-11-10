"""One command for the core results of the thesis (C1-C5), both pilot parks, in a fixed order (plan item C1).

    python -m src.run_core --list                         (print the steps and what each answers; runs nothing)
    python -m src.run_core                                (every step, Horton Plains then Adam's Peak)
    python -m src.run_core --from sparse --parks adams_peak
    python -m src.run_core --data                         (first rebuild both datasets, e.g. after the December
                                                           field counts recalibrate the simulator)

Each step is the same module a person would run by hand, in its own process, with C4_PARK set; seeds come from
the configs and each script's defaults, so a re-run reproduces the run folders under results/<park>/.
Steps that compare parks (transfer, pretraining) run once, not per park. A failed step stops the run.
The log is results/<timestamp>_run_core.log. Rough times on a 4-core laptop are in STEPS.
"""
import argparse
import os
import subprocess
import sys
import time
from datetime import datetime

from src.config import RESULTS

PARKS = ["horton_plains", "adams_peak"]

# (name, module + args, per park?, answers, rough time per park)
DATA = [
    ("dataset", ["src.data.build_dataset"], True, "trail graph + simulated counts (default world)", "5 min"),
    ("dataset_s1", ["src.data.build_dataset", "--world", "s1"], True, "realistic world S1", "5 min"),
]
STEPS = [
    ("benchmark", ["src.run_benchmark"], True, "RQ1 graph vs no graph, temporal + spatial CV (C1)", "5 h"),
    ("bottlenecks", ["src.eval.bottlenecks"], False, "RQ1b over-capacity events (C3)", "10 min"),
    ("sparse", ["src.eval.sparse_sensors", "--world", "s1", "--settings", "gate", "spot", "zero"], True,
     "RQ10 / RQ11 / RQ11b few counts (C1, C4)", "4 h"),
    ("placement", ["src.eval.placement", "--world", "s1"], True, "RQ11d where to count (C4)", "1.5 h"),
    ("quota", ["src.control.evaluate_quota"], True, "RQ9 quota vs static (C5)", "20 min"),
    ("quota_s1", ["src.control.evaluate_quota", "--world", "s1"], True, "RQ9b quota in the realistic world (C5)", "10 min"),
    ("conformal", ["src.eval.conformal"], True, "forecast ranges, cautious quota (FR10)", "5 min"),
    ("robustness", ["src.eval.robustness"], True, "G5 wrong assumptions", "10 min"),
    ("transfer", ["src.eval.transfer", "--seeds", "42", "43", "44"], False, "RQ2 park to park (C2)", "4 h"),
    ("sparse_transfer", ["src.eval.sparse_transfer", "--days", "30", "90"], False,
     "G4 / W3b traffic pretraining and adaptation with few counts (C2, O3)", "4 h"),
    ("peak_loss", ["src.eval.peak_loss"], False, "G8 peak-aware loss (C3)", "6 h"),
    ("edge", ["src.edge.export"], True, "RQ6 on-device size and latency (O6)", "2 min"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--parks", nargs="+", default=PARKS)
    ap.add_argument("--from", dest="start", default=None, help="start at this step (skip the ones before)")
    ap.add_argument("--only", nargs="+", default=None, help="run only these steps")
    ap.add_argument("--data", action="store_true", help="rebuild the datasets first")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    steps = (DATA if a.data else []) + STEPS
    names = [s[0] for s in steps]
    if a.start:
        steps = steps[names.index(a.start):]
    if a.only:
        steps = [s for s in steps if s[0] in a.only]
    if a.list:
        for name, cmd, per_park, what, t in steps:
            print(f"{name:16s} {'per park' if per_park else 'once    '} ~{t:7s} {what}\n{'':16s} python -m {' '.join(cmd)}")
        return
    log = RESULTS / f"{datetime.now():%Y%m%d_%H%M%S}_run_core.log"
    with open(log, "w", encoding="utf-8") as f:
        for name, cmd, per_park, what, _ in steps:
            for park in (a.parks if per_park else [None]):
                env = dict(os.environ) | ({"C4_PARK": park} if park else {})
                t0 = time.time()
                f.write(f"=== {datetime.now():%H:%M:%S} {name} {park or ''}: {what}\n")
                f.flush()
                r = subprocess.run([sys.executable, "-m", *cmd], env=env, stdout=f, stderr=subprocess.STDOUT)
                msg = f"=== {name} {park or ''} exit {r.returncode} after {(time.time() - t0) / 60:.1f} min\n"
                f.write(msg)
                f.flush()
                print(msg.strip(), flush=True)
                if r.returncode:
                    sys.exit(f"stopped at {name}; see {log}")
    print(f"done; log {log}")


if __name__ == "__main__":
    main()
