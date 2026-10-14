"""Historical average and ARIMA baselines (D3). The LSTM baseline is STGNN(use_graph=False, rnn='lstm')."""
import warnings

import numpy as np
from joblib import Parallel, delayed


def day_type(cov, cov_names):
    """0 = weekday, 1 = weekend / public holiday, 2 = Poya or long weekend (known in advance)."""
    c = {n: cov[:, i] for i, n in enumerate(cov_names)}
    dt = np.where((c["is_weekend"] > 0) | (c["is_holiday"] > 0), 1, 0)
    return np.where((c["is_poya"] > 0) | (c["is_long_weekend"] > 0), 2, dt)


class HistoricalAverage:
    """Mean occupancy per segment x hour of day x day type, from the train period.
    Unsensed segments (spatial CV) get the mean profile of the sensed segments."""

    def fit(self, data, sensed):
        tr = slice(0, data.train_end)
        dt = day_type(data.cov, data.cov_names)[tr]
        hr = np.asarray(data.times.hour)[tr]
        y = data.y[tr]
        self.table = np.zeros((3, 24, data.N), dtype=np.float32)
        for t in range(3):
            for h in range(24):
                sel = (dt == t) & (hr == h)
                self.table[t, h] = y[sel].mean(0) if sel.any() else 0.0
        pooled = self.table[:, :, sensed].mean(-1, keepdims=True)
        self.table[:, :, ~sensed] = pooled
        self.dt, self.hr = day_type(data.cov, data.cov_names), np.asarray(data.times.hour)
        return self

    def predict(self, data, origins):
        fut = np.asarray(origins)[:, None] + np.arange(data.H)
        return self.table[self.dt[fut], self.hr[fut]]          # [D, H, N]


def _arima_node(series, train_end, origins, H, order, seasonal, fit_days, hist_days):
    from statsmodels.tsa.statespace.sarimax import SARIMAX
    warnings.filterwarnings("ignore")
    fit = SARIMAX(series[train_end - fit_days * 24:train_end], order=order, seasonal_order=seasonal,
                  enforce_stationarity=False, enforce_invertibility=False).fit(disp=False)
    out = np.zeros((len(origins), H), dtype=np.float32)
    # Same fitted parameters, filtered forward through the data one day at a time:
    # the forecast at each origin only uses observations before that origin.
    res = fit.apply(series[origins[0] - hist_days * 24:origins[0]])
    for i, o in enumerate(origins):
        out[i] = res.forecast(H)
        if i + 1 < len(origins):
            res = res.extend(series[o:origins[i + 1]])
    return np.clip(out, 0, None)


class ARIMABaseline:
    """Seasonal ARIMA per segment, fitted on the last `fit_days` of the train period."""

    def __init__(self, cfg):
        a = cfg["arima"]
        self.order, self.seasonal = tuple(a["order"]), tuple(a["seasonal_order"])
        self.fit_days, self.hist_days = a["fit_days"], a["history_days"]

    def predict(self, data, origins, nodes):
        cols = Parallel(n_jobs=-1)(delayed(_arima_node)(
            data.y[:, n].astype(float), data.train_end, origins, data.H,
            self.order, self.seasonal, self.fit_days, self.hist_days) for n in nodes)
        pred = np.zeros((len(origins), data.H, data.N), dtype=np.float32)
        for n, c in zip(nodes, cols):
            pred[:, :, n] = c
        return pred
