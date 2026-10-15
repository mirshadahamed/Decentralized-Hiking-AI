"""Forecasting windows, temporal split and spatial blocks (D5).

Origin o: inputs are hours [o-L, o), targets are hours [o, o+H).
- train origins: every `stride` hours, whole target window inside the train period
- val / test origins: midnight only (day-ahead forecast for the permit decision), target window inside the period
Scalers are fitted on the train period (and on sensed nodes only) - never on val/test.
"""
import numpy as np
import pandas as pd
import torch

from src.config import PROCESSED


class TrailData:
    def __init__(self, cfg):
        d = np.load(PROCESSED / "dataset.npz", allow_pickle=True)
        self.cfg = cfg
        self.y = d["occ_obs"].astype(np.float32)            # [T, N] observed headcount
        self.y_true = d["occ_true"].astype(np.float32)
        self.cov = d["cov"].astype(np.float32)               # [T, Fc]
        self.cov_names = list(d["cov_names"])
        self.static = d["static"].astype(np.float32)         # [N, Fs]
        self.static_names = list(d["static_names"])
        self.edge_index = torch.tensor(d["edge_index"], dtype=torch.long)
        self.edge_weight = torch.tensor(d["edge_weight"], dtype=torch.float32)
        self.times = pd.to_datetime(d["times"].astype("datetime64[h]"))
        self.daily_visitors = d["daily_visitors"]
        self.daily_visitors_by_trail = d["daily_visitors_by_trail"]        # [days, trails]
        self.trails = list(d["trails"])
        self.segment_trail = np.asarray(d["segment_trail"])                 # [N] trail of each segment
        self.segment_poi = np.asarray(d["segment_poi"])                     # [N] POI key or ""
        self.segment_walk_position = d["segment_walk_position"]            # [N] 0..1 along its trail
        self.T, self.N = self.y.shape
        self.L, self.H = cfg["task"]["input_steps"], cfg["task"]["horizon"]

        dates = cfg["dates"]
        self.train_end = int(np.searchsorted(self.times, pd.Timestamp(dates["train_end"]) + pd.Timedelta(days=1)))
        self.val_end = int(np.searchsorted(self.times, pd.Timestamp(dates["val_end"]) + pd.Timedelta(days=1)))
        lo, hi = cfg["task"]["open_hours"]
        hour = np.asarray(self.times.hour)
        self.open = (hour >= lo) & (hour <= hi)

        # Covariate and static scaling: train period only (static has no time axis).
        mu, sd = self.cov[:self.train_end].mean(0), self.cov[:self.train_end].std(0) + 1e-6
        self.cov_s = (self.cov - mu) / sd
        self.static_s = (self.static - self.static.mean(0)) / (self.static.std(0) + 1e-6)

    # ----- splits -----
    def origins(self, split: str, stride: int = 1) -> np.ndarray:
        L, H = self.L, self.H
        if split == "train":
            return np.arange(L, self.train_end - H + 1, stride)
        start, end = (self.train_end, self.val_end) if split == "val" else (self.val_end, self.T)
        o = np.arange(max(start, L), end - H + 1)
        return o[np.asarray(self.times[o].hour) == 0]

    def walk_order(self) -> np.ndarray:
        """Segments trail by trail (config order), each in walking order."""
        wp = self.segment_walk_position
        trail_rank = np.array([self.trails.index(t) for t in self.segment_trail])
        return np.lexsort((wp, trail_rank))

    def spatial_blocks(self, k: int) -> list:
        """k contiguous blocks of segments along the trails' walking order."""
        return [np.sort(b) for b in np.array_split(self.walk_order(), k)]

    # ----- tensors -----
    def y_scale(self, sensed: np.ndarray) -> float:
        return float(self.y[:self.train_end][:, sensed].std())

    def batch(self, origins: np.ndarray, sensed: np.ndarray, scale: float):
        """Model inputs for a batch of origins.
        x_past [B, L, N, 2+Fc+Fs]: scaled occupancy (0 if not sensed), sensed flag, covariates, static
        x_fut  [B, H, N, Fc+Fs]   : known future covariates (calendar + weather) and static
        y      [B, H, N] scaled targets, open [B, H] scoring mask
        """
        o = np.asarray(origins)
        past = o[:, None] + np.arange(-self.L, 0)
        fut = o[:, None] + np.arange(self.H)
        B, N = len(o), self.N
        m = sensed.astype(np.float32)
        occ = self.y[past] / scale * m                                  # [B, L, N]
        flag = np.broadcast_to(m, occ.shape)
        st = self.static_s[None, None]
        x_past = np.concatenate([occ[..., None], flag[..., None],
                                 np.broadcast_to(self.cov_s[past][:, :, None], (B, self.L, N, self.cov.shape[1])),
                                 np.broadcast_to(st, (B, self.L, N, st.shape[-1]))], axis=-1)
        x_fut = np.concatenate([np.broadcast_to(self.cov_s[fut][:, :, None], (B, self.H, N, self.cov.shape[1])),
                                np.broadcast_to(st, (B, self.H, N, st.shape[-1]))], axis=-1)
        return (torch.from_numpy(np.ascontiguousarray(x_past)), torch.from_numpy(np.ascontiguousarray(x_fut)),
                torch.from_numpy(self.y[fut] / scale), torch.from_numpy(self.open[fut]))

    def targets(self, origins: np.ndarray, true: bool = False):
        fut = np.asarray(origins)[:, None] + np.arange(self.H)
        return (self.y_true if true else self.y)[fut], self.open[fut]   # [D, H, N], [D, H]
