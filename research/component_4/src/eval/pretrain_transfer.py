"""RQ5 - the proposal's central gap: does pretraining on dense urban traffic help a tiny, sparse trail graph?

    python -m src.eval.pretrain_transfer               # needs results/LATEST_PRETRAIN (src.pretrain.traffic)

For each park (test year 2025, every segment counted, day-ahead from midnight) and seed:
  scratch_full / pretrained_full   trained on the park's 2 years, from random weights / from the traffic weights
                                    (both with early stopping on the 2024 validation year)
  scratch_<k> / pretrained_<k>      only the park's last k days (30, 90, 365); fixed epochs, no validation year
  traffic_zero_shot                 the traffic weights used unchanged (scale from the park's last 30 days)
  HA, HA_<k>                        historical average from 2 years / k days
The model inputs follow the Horton Plains covariate list (the traffic data was built with it), so at Adam's Peak
the pilgrimage-season flag is left out in this experiment (both arms equally).
Outputs results/<timestamp>_pretrain_transfer/: metrics.csv, tests.json, log.txt
"""
import argparse
import json

import numpy as np
import pandas as pd
import torch

from src.config import RESULTS, load_config, processed_dir
from src.eval.data import TrailData
from src.eval.metrics import paired_tests
from src.eval.transfer import load as load_park
from src.models.baselines import HistoricalAverage
from src.run_benchmark import evaluate
from src.train.trainer import build_model, load_weights, predict, train
from src.utils import new_run_dir

PARKS = ["horton_plains", "adams_peak"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, nargs="+", default=[30, 90, 365])
    ap.add_argument("--seeds", type=int, nargs="+", default=None, help="default: the seeds that were pretrained")
    ap.add_argument("--fewshot-epochs", type=int, default=15)
    ap.add_argument("--parks", nargs="+", default=PARKS)
    a = ap.parse_args()
    pre_dir = RESULTS / (RESULTS / "LATEST_PRETRAIN").read_text(encoding="utf-8").strip()
    ckpts = {int(p.stem.split("_s")[-1]): torch.load(p, weights_only=False) for p in pre_dir.glob("traffic_stgnn_s*.pt")}
    seeds = a.seeds or sorted(ckpts)
    kind = "stgnn"
    train_cfg = dict(load_config(park="horton_plains")["train"])
    # the traffic data was built with Horton Plains' covariate list: use it for both parks
    common = TrailData(load_config(park="horton_plains"), path=processed_dir("horton_plains") / "dataset.npz").cov_names

    run = new_run_dir("pretrain_transfer", load_config())
    logf = open(run / "log.txt", "w", encoding="utf-8")

    def log(msg):
        print(msg, flush=True)
        logf.write(msg + "\n")
        logf.flush()

    log(f"pretrained weights: {pre_dir.name} ({ckpts[seeds[0]]['source']}), seeds {seeds}")
    rows, tests = [], {}
    for park in a.parks:
        cfg, d = load_park(park, common, train_cfg)
        te, every, nodes = d.origins("test"), np.ones(d.N, bool), np.arange(d.N)
        day_err = {}

        def add(name, preds, data):
            rs, des = zip(*(evaluate(name, p, data, te, nodes, cfg) for p in preds))
            row = {"park": park, "model": name, "n_seeds": len(preds)}
            for k in rs[0]:
                if k != "model":
                    row[k] = float(np.mean([r[k] for r in rs]))
            rows.append(row)
            day_err[name] = np.mean(des, axis=0)
            log(f"[{park}] {name}: MAE={row['MAE']:.3f} RMSE={row['RMSE']:.3f}")

        add("HA", [HistoricalAverage().fit(d, every).predict(d, te)], d)
        _, d30 = load_park(park, common, train_cfg, 30)
        zs, sc_full, pre_full = [], [], []
        for s in seeds:
            w = ckpts[s]["state_dict"]
            m = load_weights(build_model(d, kind, train_cfg["hidden"]), w)
            zs.append(predict(m, d, te, every, d30.y_scale(every)))
            m, sc = train(d, kind, every, cfg, s, log=lambda x: log(f"[{park} full scratch] {x}"))
            sc_full.append(predict(m, d, te, every, sc))
            m, sc = train(d, kind, every, cfg, s, log=lambda x: log(f"[{park} full pretrained] {x}"), init_state=w)
            pre_full.append(predict(m, d, te, every, sc))
        add("traffic_zero_shot", zs, d)
        add("scratch_full", sc_full, d)
        add("pretrained_full", pre_full, d)

        for k in a.days:
            _, dk = load_park(park, common, train_cfg, k)
            add(f"HA_{k}", [HistoricalAverage().fit(dk, every).predict(dk, te)], dk)
            p_sc, p_pre = [], []
            for s in seeds:
                tag = lambda x, how: log(f"[{park} {k}d {how}] {x}")
                m, sc = train(dk, kind, every, cfg, s, log=lambda x: tag(x, "scratch"), select_on_val=False,
                              epochs=a.fewshot_epochs)
                p_sc.append(predict(m, dk, te, every, sc))
                m, sc = train(dk, kind, every, cfg, s, log=lambda x: tag(x, "pretrained"), select_on_val=False,
                              epochs=a.fewshot_epochs, init_state=ckpts[s]["state_dict"])
                p_pre.append(predict(m, dk, te, every, sc))
            add(f"scratch_{k}", p_sc, dk)
            add(f"pretrained_{k}", p_pre, dk)

        t = {"full": paired_tests({x: day_err[x] for x in ("pretrained_full", "scratch_full", "HA")}, "pretrained_full"),
             "zero_shot": paired_tests({x: day_err[x] for x in ("traffic_zero_shot", "HA")}, "traffic_zero_shot")}
        for k in a.days:
            t[f"{k}_days"] = paired_tests({x: day_err[x] for x in (f"pretrained_{k}", f"scratch_{k}", f"HA_{k}")},
                                          f"pretrained_{k}")
        tests[park] = t

    df = pd.DataFrame(rows)
    df.to_csv(run / "metrics.csv", index=False)
    (run / "tests.json").write_text(json.dumps({"pretrained": pre_dir.name, "seeds": seeds, "days": a.days,
                                                "covariates": list(common), "tests": tests}, indent=2), encoding="utf-8")
    (RESULTS / "LATEST_PRETRAIN_TRANSFER").write_text(run.name, encoding="utf-8")
    log(df[["park", "model", "MAE", "RMSE"]].round(3).to_string(index=False))
    log(f"done -> {run}")


if __name__ == "__main__":
    main()
