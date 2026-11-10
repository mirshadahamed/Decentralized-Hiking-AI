"""G4 + W3b (objective O3, claim C2): does traffic pretraining help where the park has FEW counts - and does a real
domain-adaptation method do better than plain fine-tuning?

    python -m src.eval.sparse_transfer                 (both parks, 3 seeds; needs LATEST_PRETRAIN and LATEST_PRETRAIN_PEMS)
    python -m src.eval.sparse_transfer --quick         (1 seed, 1 epoch, 30 days: checks the pipeline)

RQ5 asked this with every segment counted. Here the park is as deployed (RQ11b): the realistic world S1, the model
sees counts only at the gates and the ranger spots, the loss covers every segment (the synthetic target), and it is
scored on the sections nobody counts. Only the park's last k days of counts are used (30 / 90 / 365), fixed epochs,
no validation year (a new park has none). Arms, same seeds:
  HA_k         historical average of the same k days
  scratch      random weights
  traffic2     fine-tuned from METR-LA -> PEMS-BAY (RQ5's source)
  traffic4     fine-tuned from METR-LA -> PEMS-BAY -> PeMS04 -> PeMS08 (the proposal's four networks)
  frozen4      traffic4 with the graph + recurrent core kept fixed (layer freezing, RQ5)
  dann4        traffic4, fine-tuned with adversarial domain alignment to PeMS08 (DANN / DASTNet-style,
               trainer._Adversary, weight ADV_WEIGHT): the encoder is pushed to keep what roads and trails share
Inputs follow the Horton Plains covariate list (the traffic data was built with it), as in RQ5.
Outputs results/<timestamp>_sparse_transfer/: metrics.csv, tests.json, log.txt
"""
import argparse
import json

import numpy as np
import pandas as pd
import torch

from src.config import RESULTS, load_config, processed_dir
from src.eval.data import TrailData
from src.eval.metrics import paired_tests
from src.eval.sparse_sensors import settings
from src.models.baselines import HistoricalAverage
from src.pretrain.traffic import TrafficData
from src.run_benchmark import evaluate
from src.train.trainer import FREEZE_CORE, predict, train
from src.utils import new_run_dir

PARKS = ["horton_plains", "adams_peak"]
ADV_WEIGHT = 0.1
ARMS = ["scratch", "traffic2", "traffic4", "frozen4", "dann4"]


def load(park, common, train_cfg, days):
    cfg = load_config(park=park)
    cfg["train"] = train_cfg
    d = TrailData(cfg, path=processed_dir(park) / "dataset_s1.npz").restrict_covariates(common)
    return cfg, d.use_last_train_days(days)


def checkpoints(pointer):
    run = RESULTS / (RESULTS / pointer).read_text(encoding="utf-8").strip()
    return run.name, {int(p.stem.split("_s")[-1]): torch.load(p, weights_only=False)["state_dict"]
                      for p in run.glob("traffic_stgnn_s*.pt")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, nargs="+", default=[30, 90, 365])
    ap.add_argument("--seeds", type=int, nargs="+", default=[42, 43, 44])
    ap.add_argument("--parks", nargs="+", default=PARKS)
    ap.add_argument("--fewshot-epochs", type=int, default=15)
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()
    train_cfg = dict(load_config(park="horton_plains")["train"])
    if a.quick:
        a.days, a.seeds, a.fewshot_epochs = [30], a.seeds[:1], 1
    name2, w2 = checkpoints("LATEST_PRETRAIN")
    name4, w4 = checkpoints("LATEST_PRETRAIN_PEMS")
    common = TrailData(load_config(park="horton_plains"), path=processed_dir("horton_plains") / "dataset.npz").cov_names
    run = new_run_dir("sparse_transfer" + ("_quick" if a.quick else ""), load_config())
    logf = open(run / "log.txt", "w", encoding="utf-8")

    def log(m):
        print(m, flush=True)
        logf.write(m + "\n")
        logf.flush()

    log(f"traffic2 = {name2}, traffic4 = {name4}; seeds {a.seeds}; days {a.days}; adversary weight {ADV_WEIGHT}")
    rows, tests = [], {}
    for park in a.parks:
        tests[park] = {}
        for k in a.days:
            cfg, d = load(park, common, train_cfg, k)
            sensed = settings(d)["spot"]
            every = np.ones(d.N, bool)
            uncounted = np.where(~sensed)[0]
            te = d.origins("test")
            source = TrafficData("pems08", d, cfg)
            day_err = {}

            def add(name, preds):
                rs, des = zip(*(evaluate(name, p, d, te, uncounted, cfg) for p in preds))
                row = {"park": park, "days": k, "model": name, "n_seeds": len(preds)}
                row.update({c: float(np.mean([r[c] for r in rs])) for c in rs[0] if c != "model"})
                rows.append(row)
                day_err[name] = np.mean(des, axis=0)
                log(f"[{park} {k}d] {name}: MAE uncounted = {row['MAE']:.3f}")

            add("HA", [HistoricalAverage().fit(d, every).predict(d, te)])
            preds = {arm: [] for arm in ARMS}
            for s in a.seeds:
                common_kw = dict(select_on_val=False, epochs=a.fewshot_epochs, loss_nodes=every)
                setups = {"scratch": {}, "traffic2": {"init_state": w2[s]}, "traffic4": {"init_state": w4[s]},
                          "frozen4": {"init_state": w4[s], "freeze": FREEZE_CORE},
                          "dann4": {"init_state": w4[s], "adversary": (source, ADV_WEIGHT)}}
                for arm, kw in setups.items():
                    m, sc = train(d, "stgnn", sensed, cfg, s, log=lambda x, arm=arm: log(f"[{park} {k}d {arm}] {x}"),
                                  **common_kw, **kw)
                    preds[arm].append(predict(m, d, te, sensed, sc))
            for arm in ARMS:
                add(arm, preds[arm])
            tests[park][f"{k}_days"] = {arm: paired_tests(day_err, arm) for arm in ("traffic4", "dann4")}
    df = pd.DataFrame(rows)
    df.to_csv(run / "metrics.csv", index=False)
    (run / "tests.json").write_text(json.dumps({"traffic2": name2, "traffic4": name4, "seeds": a.seeds,
                                                "adversary_weight": ADV_WEIGHT, "tests": tests}, indent=2),
                                    encoding="utf-8")
    if not a.quick:
        (RESULTS / "LATEST_SPARSE_TRANSFER").write_text(run.name, encoding="utf-8")
    log(df.pivot_table(index=["park", "days"], columns="model", values="MAE").round(3).to_string())
    log(f"done -> {run}")


if __name__ == "__main__":
    main()
