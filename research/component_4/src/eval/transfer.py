"""RQ2: does a forecaster trained on one park work on another park? (NFR3: other OSM-mapped parks)

    python -m src.eval.transfer                    # both directions, ST-GNN and GRU without graph, 30 and 90 days
    python -m src.eval.transfer --quick            # 1 epoch, 30 days: checks the pipeline

For each target park (test year 2025, every segment has counts, day-ahead forecasts from midnight):
  in_domain    trained on the target's 2 years of counts (the best case, reference)
  zero_shot    trained on the OTHER park only, used unchanged; only the size of the counts (scale) comes from the
               target's last 30 days
  scratch_<k>  trained on only the target's last k days of counts
  finetune_<k> the other park's model, then trained on the same k days
  HA, HA_<k>   historical average from 2 years / k days of target counts
Few-shot models train a fixed number of epochs with no early stopping on the target's validation year: a new
park does not have a year of counts to choose a model with.
Both parks get the same inputs: the covariates they share and the same transferable segment descriptions
(no trail or POI one-hots; decisions.md 15 Oct 2026), so the weights fit either graph.
Outputs results/<timestamp>_transfer/: metrics.csv, tests.json, log.txt
"""
import argparse
import json

import numpy as np
import pandas as pd

from src.config import RESULTS, load_config, processed_dir
from src.eval.data import TrailData
from src.eval.metrics import paired_tests
from src.models.baselines import HistoricalAverage
from src.run_benchmark import evaluate
from src.train.trainer import build_model, load_weights, predict, train
from src.utils import new_run_dir

PARKS = ["horton_plains", "adams_peak"]
KINDS = ["stgnn", "gru_nograph"]
SCALE_DAYS = 30


def load(park, common, train_cfg, days=None):
    cfg = load_config(park=park)
    cfg["train"] = train_cfg                                  # same hyper-parameters for both parks
    d = TrailData(cfg, path=processed_dir(park) / "dataset.npz").restrict_covariates(common)
    if days:
        d.use_last_train_days(days)
    return cfg, d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, nargs="+", default=[30, 90])
    ap.add_argument("--seeds", type=int, nargs="+", default=[42])
    ap.add_argument("--fewshot-epochs", type=int, default=15)
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()
    train_cfg = dict(load_config(park="horton_plains")["train"])
    if a.quick:
        train_cfg.update(epochs=1)
        a.days, a.seeds, a.fewshot_epochs = [30], [42], 1

    names = [TrailData(load_config(park=p), path=processed_dir(p) / "dataset.npz").cov_names for p in PARKS]
    common = [c for c in names[0] if all(c in n for n in names[1:])]
    run = new_run_dir("transfer" + ("_quick" if a.quick else ""), load_config())
    logf = open(run / "log.txt", "w", encoding="utf-8")

    def log(msg):
        print(msg, flush=True)
        logf.write(msg + "\n")
        logf.flush()

    log(f"shared covariates ({len(common)}): {common}")

    # 1. one model per park, kind and seed on that park's full training data
    full = {}
    for park in PARKS:
        cfg, d = load(park, common, train_cfg)
        for kind in KINDS:
            for s in a.seeds:
                m, _ = train(d, kind, np.ones(d.N, bool), cfg, s, log=lambda x: log(f"[{park}] {x}"))
                full[park, kind, s] = {k: v.clone() for k, v in m.state_dict().items()}

    rows, tests = [], {}
    for tgt in PARKS:
        src = next(p for p in PARKS if p != tgt)
        cfg, d = load(tgt, common, train_cfg)
        te, every = d.origins("test"), np.ones(d.N, bool)
        nodes = np.arange(d.N)
        day_err = {}

        def add(name, preds, data):
            """preds: one prediction per seed; metrics averaged over seeds, per-day errors too."""
            rs, des = zip(*(evaluate(name, p, data, te, nodes, cfg) for p in preds))
            row = {"target": tgt, "source": src if ("zero" in name or "finetune" in name) else tgt,
                   "model": name, "n_seeds": len(preds)}
            for k in rs[0]:
                if k != "model":
                    row[k] = float(np.mean([r[k] for r in rs]))
            rows.append(row)
            day_err[name] = np.mean(des, axis=0)
            log(f"[{tgt}] {name}: MAE={row['MAE']:.3f} RMSE={row['RMSE']:.3f}")

        add("HA", [HistoricalAverage().fit(d, every).predict(d, te)], d)
        _, d_scale = load(tgt, common, train_cfg, SCALE_DAYS)
        for kind in KINDS:
            preds_in, preds_zs = [], []
            for s in a.seeds:
                m = load_weights(build_model(d, kind, train_cfg["hidden"]), full[tgt, kind, s])
                preds_in.append(predict(m, d, te, every, d.y_scale(every)))
                m = load_weights(build_model(d, kind, train_cfg["hidden"]), full[src, kind, s])
                preds_zs.append(predict(m, d, te, every, d_scale.y_scale(every)))
            add(f"{kind}_in_domain", preds_in, d)
            add(f"{kind}_zero_shot", preds_zs, d)

        for k in a.days:
            _, dk = load(tgt, common, train_cfg, k)
            add(f"HA_{k}", [HistoricalAverage().fit(dk, every).predict(dk, te)], dk)
            for kind in KINDS:
                p_scratch, p_ft = [], []
                for s in a.seeds:
                    tag = lambda x, how: log(f"[{tgt} {k}d {how}] {x}")
                    m, sc = train(dk, kind, every, cfg, s, log=lambda x: tag(x, "scratch"), select_on_val=False,
                                  epochs=a.fewshot_epochs)
                    p_scratch.append(predict(m, dk, te, every, sc))
                    m, sc = train(dk, kind, every, cfg, s, log=lambda x: tag(x, "finetune"), select_on_val=False,
                                  epochs=a.fewshot_epochs, init_state=full[src, kind, s])
                    p_ft.append(predict(m, dk, te, every, sc))
                add(f"{kind}_scratch_{k}", p_scratch, dk)
                add(f"{kind}_finetune_{k}", p_ft, dk)

        # paired tests over forecast days (Holm within each question)
        t = {}
        for kind in KINDS:
            t[f"{kind}_zero_shot"] = paired_tests({x: day_err[x] for x in
                                                   (f"{kind}_zero_shot", f"{kind}_in_domain", "HA")}, f"{kind}_zero_shot")
            for k in a.days:
                ft = f"{kind}_finetune_{k}"
                t[ft] = paired_tests({x: day_err[x] for x in (ft, f"{kind}_scratch_{k}", f"HA_{k}", "HA")}, ft)
        t["graph_zero_shot"] = paired_tests({x: day_err[x] for x in ("stgnn_zero_shot", "gru_nograph_zero_shot")},
                                            "stgnn_zero_shot")
        tests[tgt] = t

    df = pd.DataFrame(rows)
    df.to_csv(run / "metrics.csv", index=False)
    (run / "tests.json").write_text(json.dumps({"shared_covariates": common, "seeds": a.seeds, "days": a.days,
                                                "tests": tests}, indent=2), encoding="utf-8")
    (RESULTS / "LATEST_TRANSFER").write_text(run.name, encoding="utf-8")
    log(df[["target", "model", "MAE", "RMSE"]].round(3).to_string(index=False))
    log(f"done -> {run}")


if __name__ == "__main__":
    main()
