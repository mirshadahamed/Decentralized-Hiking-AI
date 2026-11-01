"""Train a neural forecaster with masked L1 loss and early stopping on the validation year."""
import copy
import time
from pathlib import Path

import numpy as np
import torch

from src.models.stgnn import GRAPH_BUFFERS, STGNN
from src.utils import set_seed


def masked_l1(pred, y, open_mask, node_mask, peak=None):
    """Mean absolute error over open hours and the given segments. peak=(threshold [N] in scaled units, weight):
    errors where the target is at or above the threshold count `weight` times more (G8: over-capacity hours are
    rare, so a plain MAE is happy to smooth them away)."""
    m = open_mask[:, :, None] & node_mask[None, None, :]
    e = (pred - y).abs()
    if peak is not None:
        thr, w = peak
        e = e * (1 + (w - 1) * (y >= thr[None, None, :]).float())
    return e[m].mean()


def build_model(data, kind, hidden):
    f_past = 2 + data.cov.shape[1] + data.static.shape[1]
    f_fut = data.cov.shape[1] + data.static.shape[1]
    spec = {"stgnn": dict(use_graph=True, rnn="gru"),
            "stgnn_lstm": dict(use_graph=True, rnn="lstm"),        # graph + LSTM cell (P0-4)
            "stgnn_dir": dict(use_graph=True, rnn="gru",            # directed diffusion along the trails
                              direction=(data.segment_trail, data.segment_walk_position)),
            "gru_nograph": dict(use_graph=False, rnn="gru"),
            "lstm": dict(use_graph=False, rnn="lstm")}[kind]
    return STGNN(f_past, f_fut, data.edge_index, data.edge_weight, hidden=hidden, n_nodes=data.N, **spec)


@torch.no_grad()
def predict(model, data, origins, sensed, scale, batch=128):
    model.eval()
    out = []
    for i in range(0, len(origins), batch):
        xp, xf, _, _ = data.batch(origins[i:i + batch], sensed, scale)
        out.append(model(xp, xf).numpy())
    return np.clip(np.concatenate(out) * scale, 0, None)       # [D, H, N] in persons


def load_weights(model, state: dict):
    """Weights trained on another park: everything except the graph (adjacency) of that park."""
    model.load_state_dict({k: v for k, v in state.items() if k not in GRAPH_BUFFERS}, strict=False)
    return model


FREEZE_CORE = ("g1.", "g2.", "rnn.", "g_out.")   # graph + recurrent core; inp / fut / head stay trainable


def random_counts(rng, base, max_extra):
    """base plus 0..max_extra other segments, at random (mask augmentation)."""
    s = base.copy()
    free = np.where(~base)[0]
    k = int(rng.integers(0, min(max_extra, len(free)) + 1))
    s[rng.choice(free, k, replace=False)] = True
    return s


def train(data, kind, sensed, cfg, seed, log=print, init_state=None, select_on_val=True, epochs=None, freeze=(),
          loss_nodes=None, peak=None, mask_aug=None):
    """sensed: bool [N]; unsensed nodes give no input history and (by default) no training loss.
    loss_nodes: bool [N] segments scored in the loss, if not the sensed ones (sensor-sparse protocol G1: the
    synthetic target covers every segment, while as input the model sees only what the park measures).
    init_state: start from these weights (fine-tuning a model trained on another park).
    select_on_val=False: no early stopping on the validation year; train `epochs` and keep the last weights
    (few-shot: a new park does not have a year of counts to choose the model with).
    freeze: parameter-name prefixes kept fixed (domain adaptation: e.g. FREEZE_CORE keeps the pretrained
    spatio-temporal core and adapts only the input and output layers to the new domain).
    peak: (threshold [N] in persons, weight) - peak-aware loss for training and model selection (G8).
    mask_aug: (base [N] bool, max_extra) - each training batch sees counts at `base` plus 0..max_extra random
    other segments, so one model takes counts from ANY set of places (rangers count where they are that day;
    src.eval.placement). Validation uses `sensed`."""
    tc = cfg["train"]
    set_seed(seed)
    rng = np.random.default_rng(seed)
    loss_nodes = sensed if loss_nodes is None else loss_nodes
    scale = data.y_scale(loss_nodes)
    model = build_model(data, kind, tc["hidden"])
    if init_state is not None:
        load_weights(model, init_state)
    for n, p in model.named_parameters():
        if n.startswith(tuple(freeze)):
            p.requires_grad_(False)
    opt = torch.optim.Adam([p for p in model.parameters() if p.requires_grad], lr=tc["lr"])
    tr_o, va_o = data.origins("train", tc["train_origin_stride"]), data.origins("val")
    node_mask = torch.from_numpy(loss_nodes)
    pk = None if peak is None else (torch.as_tensor(np.asarray(peak[0]) / scale, dtype=torch.float32), float(peak[1]))

    best, best_state, bad = np.inf, None, 0
    for ep in range(epochs or tc["epochs"]):
        t0 = time.time()
        model.train()
        perm = rng.permutation(tr_o)
        losses = []
        for i in range(0, len(perm), tc["batch_size"]):
            s_b = sensed if mask_aug is None else random_counts(rng, *mask_aug)
            xp, xf, y, om = data.batch(perm[i:i + tc["batch_size"]], s_b, scale)
            # Train on every hour (so the model learns the trail is empty at night);
            # validation and test are scored on open hours only.
            loss = masked_l1(model(xp, xf), y, torch.ones_like(om), node_mask, pk)
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            opt.step()
            losses.append(loss.item())
        if not select_on_val:
            log(f"  {kind} seed={seed} ep={ep:02d} train={np.mean(losses):.4f} ({time.time() - t0:.1f}s)")
            continue
        model.eval()
        with torch.no_grad():
            xp, xf, y, om = data.batch(va_o, sensed, scale)
            val = masked_l1(model(xp, xf), y, om, node_mask, pk).item()
        log(f"  {kind} seed={seed} ep={ep:02d} train={np.mean(losses):.4f} val={val:.4f} ({time.time() - t0:.1f}s)")
        if val < best - 1e-4:
            best, best_state, bad = val, copy.deepcopy(model.state_dict()), 0
        else:
            bad += 1
            if bad >= tc["patience"]:
                break
    if best_state is not None:
        model.load_state_dict(best_state)
    return model, scale


def train_or_load(ref: Path | None, name: str, data, kind, sensed, cfg, seed, log=print, **kw):
    """The checkpoint `ref/models/<name>.pt` of an earlier run with the same data and seeds, if it exists and
    was trained on the same segments; otherwise train. Lets a run add one model and still test it against the
    earlier ones on the same days."""
    path = None if ref is None else Path(ref) / "models" / f"{name}.pt"
    if path is not None and path.exists():
        ck = torch.load(path, weights_only=False)
        if ck["kind"] == kind and np.array_equal(np.asarray(ck["sensed"]), sensed):
            model = build_model(data, kind, cfg["train"]["hidden"])
            model.load_state_dict(ck["state_dict"])
            log(f"  {kind} seed={seed}: loaded {path}")
            return model, ck["scale"]
    return train(data, kind, sensed, cfg, seed, log=log, **kw)


def joint_train(datas: list, kind, cfg, seed, log=print):
    """One model trained on several parks at once (each batch from one park, with that park's graph; every
    segment counted). The parks must share covariates and segment descriptions (src.eval.transfer). Early
    stopping on the mean validation loss over the parks. Returns the state dict (without any park's graph)."""
    tc = cfg["train"]
    set_seed(seed)
    rng = np.random.default_rng(seed)
    models = [build_model(d, kind, tc["hidden"]) for d in datas]
    graphs = [{n: b for n, b in m.named_buffers() if n in GRAPH_BUFFERS} for m in models]
    model = models[0]
    every = [np.ones(d.N, bool) for d in datas]
    scales = [d.y_scale(e) for d, e in zip(datas, every)]
    opt = torch.optim.Adam(model.parameters(), lr=tc["lr"])

    def use(p):
        for n, b in graphs[p].items():
            setattr(model, n, b)

    best, best_state, bad = np.inf, None, 0
    for ep in range(tc["epochs"]):
        t0 = time.time()
        model.train()
        jobs = [(p, o) for p, d in enumerate(datas)
                for o in np.array_split(rng.permutation(d.origins("train", tc["train_origin_stride"])),
                                        max(1, len(d.origins("train", tc["train_origin_stride"])) // tc["batch_size"]))]
        losses = []
        for j in rng.permutation(len(jobs)):
            p, o = jobs[j]
            use(p)
            xp, xf, y, om = datas[p].batch(o, every[p], scales[p])
            loss = masked_l1(model(xp, xf), y, torch.ones_like(om), torch.from_numpy(every[p]))
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            opt.step()
            losses.append(loss.item())
        model.eval()
        vals = []
        with torch.no_grad():
            for p, d in enumerate(datas):
                use(p)
                xp, xf, y, om = d.batch(d.origins("val"), every[p], scales[p])
                vals.append(masked_l1(model(xp, xf), y, om, torch.from_numpy(every[p])).item())
        val = float(np.mean(vals))
        log(f"  joint {kind} seed={seed} ep={ep:02d} train={np.mean(losses):.4f} val={val:.4f} ({time.time() - t0:.1f}s)")
        if val < best - 1e-4:
            best, best_state, bad = val, copy.deepcopy(model.state_dict()), 0
        else:
            bad += 1
            if bad >= tc["patience"]:
                break
    return {k: v for k, v in (best_state or model.state_dict()).items() if k not in GRAPH_BUFFERS}
