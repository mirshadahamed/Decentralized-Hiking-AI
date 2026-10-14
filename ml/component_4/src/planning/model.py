"""Long-range planning model: expected crowd for any day 2-90 days ahead (roadmap.md, section 3).

The day-ahead ST-GNN cannot be used this far ahead: it needs yesterday's counts and tomorrow's weather.
This model works from what *is* known when the forecast is made (the issue date):
  - the calendar of the target day (day of week, holiday, Poya, long weekend, school holiday, season)
  - typical weather for that time of year (climatology from the training years), not the actual weather
  - the recent visitor level (mean daily visitors in the 28 days before the issue date)
  - the lead time (how many days ahead)
Two steps:
  1. DailyModel: P10 / P50 / P90 of total park visitors (gradient-boosted quantile regression), split per trail
     with the trail shares learned for that kind of day.
  2. Profiles: average people per segment per hour *per visitor*, by demand level and wet/dry morning,
     scaled by the daily number -> hourly occupancy per segment.
Everything is fitted on the training period only (2022-23).
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

QUANTILES = (0.1, 0.5, 0.9)
TRAIN_LEADS = (2, 3, 5, 7, 10, 14, 21, 30, 45, 60, 75, 90)
LEVEL_DAYS = 28
WET_MM = 2.0                      # morning (05-10 h) rain above this = wet morning
FEATURES = ["dow", "is_weekend", "is_holiday", "is_poya", "is_long_weekend", "is_school_holiday",
            "doy_sin", "doy_cos", "clim_rain", "clim_wet", "level", "lead"]


class DailyTable:
    """One row per day: calendar, morning rain, visitors (total and per trail), climatology."""

    def __init__(self, data, calendar: pd.DataFrame):
        days = pd.DatetimeIndex(data.times[::24])
        rain = np.expm1(data.cov[:, data.cov_names.index("precip_log1p")]).reshape(-1, 24)
        df = calendar.reindex(days)[["dow", "is_weekend", "is_holiday", "is_poya", "is_long_weekend",
                                     "is_school_holiday"]].astype(int).copy()
        doy = days.dayofyear.values
        df["doy"] = doy
        df["doy_sin"], df["doy_cos"] = np.sin(2 * np.pi * doy / 365.25), np.cos(2 * np.pi * doy / 365.25)
        df["morning_rain"] = rain[:, 5:10].sum(1)
        df["visitors"] = data.daily_visitors.astype(float)
        for i, t in enumerate(data.trails):
            df[f"v_{t}"] = data.daily_visitors_by_trail[:, i].astype(float)
        self.trails = list(data.trails)
        self.train_days = data.train_end // 24
        # Climatology of the morning rain: training years, +-15 days around the day of year
        tr = df.iloc[:self.train_days]
        clim_rain, clim_wet = np.zeros(367), np.zeros(367)
        for d in range(1, 367):
            dist = np.minimum(np.abs(tr.doy - d), 365 - np.abs(tr.doy - d))
            win = tr[dist <= 15]
            clim_rain[d], clim_wet[d] = win.morning_rain.mean(), (win.morning_rain > WET_MM).mean()
        df["clim_rain"], df["clim_wet"] = clim_rain[doy], clim_wet[doy]
        df["level"] = df.visitors.shift(1).rolling(LEVEL_DAYS, min_periods=LEVEL_DAYS).mean()  # up to the day before
        self.df = df
        self.days = days

    def features(self, issue_idx: int, target_idx: np.ndarray) -> pd.DataFrame:
        """Feature rows for targets forecast on the issue day (only data before the issue day is used)."""
        X = self.df.iloc[target_idx][FEATURES[:-2]].copy()
        X["level"] = self.df.level.iloc[issue_idx]           # mean of the 28 days before the issue day
        X["lead"] = np.asarray(target_idx) - issue_idx
        return X[FEATURES]


class DailyModel:
    def __init__(self, seed: int = 42):
        self.models = {q: HistGradientBoostingRegressor(loss="quantile", quantile=q, max_iter=300,
                                                        learning_rate=0.05, max_leaf_nodes=15,
                                                        random_state=seed) for q in QUANTILES}

    def fit(self, table: DailyTable):
        rows = []
        n = table.train_days
        for lead in TRAIN_LEADS:
            targets = np.arange(LEVEL_DAYS + lead, n)
            for t in targets:                                     # every (issue, target) pair inside training
                rows.append((t - lead, t))
        issue = np.array([r[0] for r in rows])
        target = np.array([r[1] for r in rows])
        X = table.df.iloc[target][FEATURES[:-2]].reset_index(drop=True)
        X["level"] = table.df.level.values[issue]
        X["lead"] = target - issue
        y = table.df.visitors.values[target]
        for m in self.models.values():
            m.fit(X[FEATURES], y)
        # Trail shares by day type, from training days
        tr = table.df.iloc[:n]
        kind = self._kind(tr)
        self.shares = {k: {t: float(tr[f"v_{t}"][kind == k].sum() / tr.visitors[kind == k].sum())
                           for t in table.trails} for k in np.unique(kind)}
        self.trails = table.trails
        return self

    @staticmethod
    def _kind(df):
        return np.where(df.is_poya | df.is_long_weekend, 2, np.where(df.is_weekend | df.is_holiday, 1, 0))

    def predict(self, table: DailyTable, issue_idx: int, target_idx: np.ndarray) -> pd.DataFrame:
        X = table.features(issue_idx, np.asarray(target_idx))
        q = np.sort(np.column_stack([np.clip(self.models[q].predict(X), 0, None) for q in QUANTILES]), axis=1)
        out = pd.DataFrame(q, columns=["p10", "p50", "p90"], index=table.days[target_idx])
        kind = self._kind(table.df.iloc[target_idx])
        for t in self.trails:
            share = np.array([self.shares[k][t] for k in kind])
            for c in ["p10", "p50", "p90"]:
                out[f"{t}_{c}"] = out[c].values * share
        out["lead"] = X["lead"].values
        return out


class Profiles:
    """People per segment per hour, per park visitor, by demand level (3 bins) x wet/dry morning."""

    def fit(self, data, table: DailyTable):
        n = table.train_days
        v = table.df.visitors.values[:n]
        self.edges = np.quantile(v, [1 / 3, 2 / 3])
        wet = table.df.morning_rain.values[:n] > WET_MM
        occ = data.y[:n * 24].reshape(n, 24, data.N) / np.maximum(v, 1)[:, None, None]
        level = np.digitize(v, self.edges)
        self.prof = np.zeros((3, 2, 24, data.N), dtype=np.float32)
        for lv in range(3):
            for w in (0, 1):
                sel = (level == lv) & (wet == w)
                self.prof[lv, w] = occ[sel].mean(0) if sel.any() else occ[level == lv].mean(0)
        return self

    def hourly(self, visitors: float, p_wet: float) -> np.ndarray:
        """Expected hourly occupancy [24, N] for a day with this many visitors and this chance of a wet morning."""
        lv = int(np.digitize(visitors, self.edges))
        return visitors * ((1 - p_wet) * self.prof[lv, 0] + p_wet * self.prof[lv, 1])


class PlanningModel:
    def __init__(self, data, calendar: pd.DataFrame, seed: int = 42):
        self.data = data
        self.table = DailyTable(data, calendar)
        self.daily = DailyModel(seed).fit(self.table)
        self.profiles = Profiles().fit(data, self.table)
        tr = self.table.df.visitors.iloc[:self.table.train_days]
        self.level_edges = np.quantile(tr, [0.2, 0.4, 0.6, 0.8])   # crowd level 1-5 = quintiles of training days
        self.calibrate()

    def calibrate(self, step_days: int = 7):
        """Conformal range: P10/P90 = P50 x the 10th/90th percentile of actual/P50 on the validation year (2024).
        The boosted quantiles alone were too narrow (only ~60 % of test days fell inside P10-P90)."""
        lo, hi = self.table.train_days, self.data.val_end // 24
        ratios = []
        for issue in range(lo, hi - 2, step_days):
            targets = np.arange(issue + 2, min(issue + 90, hi - 1) + 1)
            p50 = self.daily.predict(self.table, issue, targets).p50.values
            ratios.append(np.log(np.maximum(self.table.df.visitors.values[targets], 1) / np.maximum(p50, 1)))
        r = np.concatenate(ratios)
        self.log_band = (float(np.quantile(r, 0.1)), float(np.quantile(r, 0.9)))

    def day_index(self, date) -> int:
        return int(np.searchsorted(self.table.days, pd.Timestamp(date)))

    def outlook(self, issue_date, horizon: int = 90) -> pd.DataFrame:
        i = self.day_index(issue_date)
        if i < LEVEL_DAYS:
            raise ValueError("issue date needs 28 days of history before it")
        targets = np.arange(i + 1, min(i + horizon, len(self.table.days) - 1) + 1)
        out = self.daily.predict(self.table, i, targets)
        lo, hi = self.log_band
        for c, f in (("p10", np.exp(lo)), ("p90", np.exp(hi))):
            out[c] = out.p50 * f
            for t in self.daily.trails:
                out[f"{t}_{c}"] = out[f"{t}_p50"] * f
        out["crowd_level"] = np.digitize(out.p50, self.level_edges) + 1
        out["p_wet"] = self.table.df.clim_wet.values[targets]
        return out

    def hourly(self, outlook_row: pd.Series, q: str = "p50") -> np.ndarray:
        return self.profiles.hourly(float(outlook_row[q]), float(outlook_row["p_wet"]))
