"""Where should rangers count? One model for any set of counted places, and the best places to count (S4c).

    python -m src.eval.placement --world s1               (current park; $env:C4_PARK = "adams_peak" for the other)
    python -m src.eval.placement --world s1 --quick       (1 epoch, 1 seed, 3 places: checks the pipeline)

RQ11b showed that only the graph model carries a few counts to the sections nobody counts, with the counted
places fixed in advance (gates + viewpoints). In a park the counted places change: who is on duty, where they
stand. Here each model is trained with MASK AUGMENTATION: every batch sees counts at the gates plus a random set of
0..max_extra other sections (src.train.trainer.random_counts), so one model takes counts from any places.
Then, on the validation year, places are added greedily: each step adds the section whose counts lower the MAE
on the interior most, for the forecast issued at --hour (default 10:00: rangers count in the morning, the rest
of the day is re-forecast; src.live.intraday) and scored on the rest of that day. Scored on the test year 2025,
at --hour and day-ahead (00:00), for k = 0..max_k extra places:
  greedy    the chosen places (per model)
  random    10 random sets of k places (the same sets for every model)
  rangers   the places of RQ11b (viewpoints + halfway checkpoints), at their own k
Paired tests per day (Holm): greedy vs random and vs the rangers' places, ST-GNN vs the GRU without graph.
Outputs results/<park>/<timestamp>_placement[_s1]/: curve.csv, order.json, stats.json, models/*.pt;
results/<park>/LATEST_PLACEMENT[_S1] (the counting order the ranger app shows, src.live.intraday).
"""
import argparse
import json

import numpy as np
import pandas as pd
import torch

from src.config import PROCESSED, RESULTS, load_config
from src.eval.data import TrailData
from src.eval.metrics import paired_tests, per_day_mae
from src.eval.sparse_sensors import settings
from src.train.trainer import predict, train
from src.utils import new_run_dir

KINDS = ["stgnn", "gru_nograph"]
N_RANDOM = 10


def place_name(data, n: int) -> str:
    poi = str(data.segment_poi[n])
    return f"{n}" + (f" ({poi})" if poi else f" ({data.segment_trail[n]}, {data.segment_walk_position[n]:.0%})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--world", choices=["default", "s1"], default="s1")
    ap.add_argument("--kinds", nargs="+", default=KINDS, choices=KINDS + ["stgnn_dir"])
    ap.add_argument("--seeds", type=int, nargs="+", default=[42, 43])
    ap.add_argument("--max-k", type=int, default=8, help="extra counted places to choose, besides the gates")
    ap.add_argument("--hour", type=int, default=10, help="forecast issued at this hour, for the rest of the day")
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()
    cfg = load_config()
    if a.quick:
        cfg["train"].update(epochs=1)
        a.seeds, a.max_k = a.seeds[:1], 3
    data = TrailData(cfg, path=PROCESSED / ("dataset_s1.npz" if a.world == "s1" else "dataset.npz"))
    sets = settings(data)
    gate, rangers = sets["gate"], sets["spot"]
    interior = np.where(~gate)[0]
    every = np.ones(data.N, bool)
    max_extra = max(2 * a.max_k, int(rangers.sum() - gate.sum()), data.N // 3)
    run = new_run_dir("placement" + ("_s1" if a.world == "s1" else "") + ("_quick" if a.quick else ""), cfg)
    (run / "models").mkdir()
    logf = open(run / "log.txt", "w", encoding="utf-8")

    def log(m):
        print(m, flush=True)
        logf.write(m + "\n")
        logf.flush()

    log(f"gates {np.where(gate)[0].tolist()}; rangers' places {np.where(rangers & ~gate)[0].tolist()}; "
        f"training with gates + 0..{max_extra} random places; seeds {a.seeds}")
    models = {}
    for kind in a.kinds:
        for s in a.seeds:
            m, sc = train(data, kind, rangers, cfg, s, log=log, loss_nodes=every, mask_aug=(gate, max_extra))
            models[kind, s] = (m, sc)
            torch.save({"state_dict": m.state_dict(), "scale": sc, "kind": kind, "sensed": rangers,
                        "mask_aug": [gate.tolist(), max_extra], "seed": s}, run / "models" / f"{kind}_s{s}.pt")

    def windows(split, hour):
        """Origins at `hour` and their targets, scored on open hours of the same day only."""
        o = data.origins(split) + hour
        o = o[o + data.H <= data.T]
        y, om = data.targets(o)
        return o, y, om & (np.arange(data.H)[None] < 24 - hour)

    va = windows("val", a.hour)
    te = {a.hour: windows("test", a.hour), 0: windows("test", 0)}

    def day_err(kind, sensed, win, *node_sets):
        """[days] MAE on each of `node_sets` (default: the interior), mean over seeds; one prediction per seed."""
        o, y, om = win
        preds = [predict(m, data, o, sensed, sc) for (k, _), (m, sc) in models.items() if k == kind]
        out = [np.mean([per_day_mae(p, y, om, nodes) for p in preds], axis=0) for nodes in (node_sets or [interior])]
        return out[0] if len(out) == 1 else out

    def with_places(places):
        s = gate.copy()
        s[list(places)] = True
        return s

    order = {}
    for kind in a.kinds:
        chosen = []
        for step in range(a.max_k):
            cand = [n for n in interior if n not in chosen]
            score = {n: float(day_err(kind, with_places(chosen + [n]), va).mean()) for n in cand}
            best = min(score, key=score.get)
            chosen.append(int(best))
            log(f"[{kind}] place {step + 1}: {place_name(data, best)}  validation MAE {score[best]:.4f}")
        order[kind] = chosen

    rng = np.random.default_rng(0)
    randoms = {k: [rng.choice(interior, k, replace=False).tolist() for _ in range(N_RANDOM)] for k in range(1, a.max_k + 1)}
    k_rangers = int((rangers & ~gate).sum())
    rows, days, stats = [], {}, {}
    rp = np.where(rangers & ~gate)[0]
    for kind in a.kinds:
        for hr, win in te.items():
            for k in range(0, a.max_k + 1):
                sets_k = {"greedy": [order[kind][:k]], "random": randoms[k]} if k else {"gates only": [[]]}
                for how, places_list in sets_k.items():
                    errs, unc = [], []
                    for places in places_list:
                        s = with_places(places)
                        e, u = day_err(kind, s, win, interior, np.setdiff1d(interior, places))
                        errs.append(e)
                        unc.append(u.mean())
                    days[kind, hr, how, k] = np.mean(errs, axis=0)
                    rows.append({"model": kind, "from_hour": hr, "places": how, "k": k, "MAE": float(np.mean(errs)),
                                 "MAE_uncounted": float(np.mean(unc)), "n_sets": len(places_list)})
            e, u = day_err(kind, rangers, win, interior, np.setdiff1d(interior, rp))
            days[kind, hr, "rangers", k_rangers] = e
            rows.append({"model": kind, "from_hour": hr, "places": "rangers", "k": k_rangers, "MAE": float(e.mean()),
                         "MAE_uncounted": float(u.mean()), "n_sets": 1})
            st = {f"k{k}_greedy_vs_random": paired_tests({"greedy": days[kind, hr, "greedy", k],
                                                           "random": days[kind, hr, "random", k]}, "greedy")
                  for k in range(1, a.max_k + 1)}
            if k_rangers <= a.max_k:
                st["greedy_vs_rangers_same_k"] = paired_tests({"greedy": days[kind, hr, "greedy", k_rangers],
                                                                "rangers": days[kind, hr, "rangers", k_rangers]}, "greedy")
            stats[f"{kind}_from_{hr:02d}h"] = st
    if "stgnn" in a.kinds and "gru_nograph" in a.kinds:
        for hr in te:
            stats[f"graph_vs_nograph_from_{hr:02d}h"] = {
                f"k{k}": paired_tests({m: days[m, hr, "greedy" if k else "gates only", k] for m in ("stgnn", "gru_nograph")},
                                      "stgnn") for k in range(0, a.max_k + 1)}

    df = pd.DataFrame(rows)
    df.to_csv(run / "curve.csv", index=False)
    (run / "stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    (run / "order.json").write_text(json.dumps({
        "gates": np.where(gate)[0].tolist(), "rangers": np.where(rangers & ~gate)[0].tolist(), "max_extra": max_extra,
        "order": order, "names": {kind: [place_name(data, n) for n in o] for kind, o in order.items()},
        "seeds": a.seeds, "world": a.world}, indent=2), encoding="utf-8")
    if not a.quick:
        (RESULTS / ("LATEST_PLACEMENT_S1" if a.world == "s1" else "LATEST_PLACEMENT")).write_text(run.name, encoding="utf-8")
    log(df.pivot_table(index=["from_hour", "k"], columns=["model", "places"], values="MAE").round(3).to_string())
    log(f"done -> {run}")


if __name__ == "__main__":
    main()
