"""Train a neural forecaster with masked L1 loss and early stopping on the validation year."""
import copy
import time

import numpy as np
import torch

from src.models.stgnn import STGNN
from src.utils import set_seed


def masked_l1(pred, y, open_mask, node_mask):
    m = open_mask[:, :, None] & node_mask[None, None, :]
    return (pred - y).abs()[m].mean()


def build_model(data, kind, hidden):
    f_past = 2 + data.cov.shape[1] + data.static.shape[1]
    f_fut = data.cov.shape[1] + data.static.shape[1]
    spec = {"stgnn": dict(use_graph=True, rnn="gru"),
            "gru_nograph": dict(use_graph=False, rnn="gru"),
            "lstm": dict(use_graph=False, rnn="lstm")}[kind]
    return STGNN(f_past, f_fut, data.edge_index, hidden=hidden, **spec)


@torch.no_grad()
def predict(model, data, origins, sensed, scale, batch=128):
    model.eval()
    out = []
    for i in range(0, len(origins), batch):
        xp, xf, _, _ = data.batch(origins[i:i + batch], sensed, scale)
        out.append(model(xp, xf).numpy())
    return np.clip(np.concatenate(out) * scale, 0, None)       # [D, H, N] in persons


def train(data, kind, sensed, cfg, seed, log=print):
    """sensed: bool [N]; unsensed nodes give no input history and no training loss."""
    tc = cfg["train"]
    set_seed(seed)
    rng = np.random.default_rng(seed)
    scale = data.y_scale(sensed)
    model = build_model(data, kind, tc["hidden"])
    opt = torch.optim.Adam(model.parameters(), lr=tc["lr"])
    tr_o, va_o = data.origins("train", tc["train_origin_stride"]), data.origins("val")
    node_mask = torch.from_numpy(sensed)

    best, best_state, bad = np.inf, None, 0
    for ep in range(tc["epochs"]):
        t0 = time.time()
        model.train()
        perm = rng.permutation(tr_o)
        losses = []
        for i in range(0, len(perm), tc["batch_size"]):
            xp, xf, y, om = data.batch(perm[i:i + tc["batch_size"]], sensed, scale)
            # Train on every hour (so the model learns the trail is empty at night);
            # validation and test are scored on open hours only.
            loss = masked_l1(model(xp, xf), y, torch.ones_like(om), node_mask)
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            opt.step()
            losses.append(loss.item())
        model.eval()
        with torch.no_grad():
            xp, xf, y, om = data.batch(va_o, sensed, scale)
            val = masked_l1(model(xp, xf), y, om, node_mask).item()
        log(f"  {kind} seed={seed} ep={ep:02d} train={np.mean(losses):.4f} val={val:.4f} ({time.time() - t0:.1f}s)")
        if val < best - 1e-4:
            best, best_state, bad = val, copy.deepcopy(model.state_dict()), 0
        else:
            bad += 1
            if bad >= tc["patience"]:
                break
    model.load_state_dict(best_state)
    return model, scale
