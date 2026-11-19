"""Shared helpers for the forecasting models (demand and price).

What is in here (all plain functions, used by `src/models/demand.py` and `src/models/price.py`):

* data:      `load_features`, `split_frame`, `train_rows_known_at`, `apply_weather_map`
* metrics:   `mae`, `rmse`, `mape`, `smape`, `bias`, `bootstrap_mae_ci`, `metrics_long`
* tests:     `dm_test` (Diebold-Mariano on daily mean absolute errors)
* models:    `ColumnModel` (naive forecast = copy one column), `ColumnSelect`, `LinearDesign` (feature builder for
             linear models), `ForecastModel` (the saved-model wrapper with `predict(df)`)
* figures:   `plot_forecast_vs_actual`, `plot_error_by_block`, `plot_model_ladder`, `plot_importance`
* importance: `permutation_importance_df`

The saved models (`models/<target>_best.joblib`) are `ForecastModel` objects. Load them with
`import src.models.common` + `joblib.load(...)`, then call `.predict(rows_of_features_parquet)`.
"""
from __future__ import annotations

import math
from typing import Callable, Iterable, Sequence

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin

from src.config import load_config, path

# Columns that must never be model inputs (only allowed in a clearly labelled oracle run).
FORBIDDEN_PREFIXES = ("actual_", "unverified_")
FORBIDDEN_SUFFIXES = ("_obs",)
TARGET_COLUMNS = ("demand_mw", "price_eur_mwh")


# ----------------------------------------------------------------------------------------------
# data
# ----------------------------------------------------------------------------------------------
def load_features(file=None) -> pd.DataFrame:
    """Read features.parquet, turn `delivery_date` into a pandas Timestamp (midnight, no time zone)
    and sort by (delivery_date, block)."""
    df = pd.read_parquet(file or path("features"))
    df["delivery_date"] = pd.to_datetime(df["delivery_date"]).dt.tz_localize(None).dt.normalize()
    return df.sort_values(["delivery_date", "block"]).reset_index(drop=True)


def period_dates() -> dict:
    """Train / validation / test boundaries from config.yaml as Timestamps."""
    p = load_config()["periods"]
    return {k: pd.Timestamp(v) for k, v in p.items()}


def split_frame(df: pd.DataFrame, split: str) -> pd.DataFrame:
    """Rows of one split: "train" (≤ train_end), "val" (September 2026), "test" (October 2026),
    "trainval" (≤ val_end), "test2" (January 2026)."""
    p = period_dates()
    d = df["delivery_date"]
    masks = {
        "train": d <= p["train_end"],
        "val": (d >= p["val_start"]) & (d <= p["val_end"]),
        "test": (d >= p["test_start"]) & (d <= p["test_end"]),
        "trainval": d <= p["val_end"],
        "test2": (d >= p["test2_start"]) & (d <= p["test2_end"]),
    }
    return df[masks[split]].copy()


def train_rows_known_at(df: pd.DataFrame, delivery_date, target_lag_days: int) -> pd.DataFrame:
    """Rows whose TARGET is already known when forecasting `delivery_date`.

    target_lag_days = 2 for demand (latest known demand row is T−2), 1 for price (T−1)."""
    last = pd.Timestamp(delivery_date) - pd.Timedelta(days=target_lag_days)
    return df[df["delivery_date"] <= last]


def apply_weather_map(df: pd.DataFrame, mapping: dict | None) -> pd.DataFrame:
    """Return a copy where every hybrid weather column `h` is replaced by `df[mapping[h]]`
    (e.g. JMA forecasts or observed 'oracle' weather). Columns not in `df` are skipped."""
    if not mapping:
        return df
    out = df.copy()
    for h, alt in mapping.items():
        if alt in df.columns:
            out[h] = df[alt]
    return out


def forbidden_columns(columns: Iterable[str], allowed_target: str | None = None) -> list[str]:
    """Columns that look like leakage: `*_obs`, `actual_*`, `unverified_*` or a target column."""
    bad = []
    for c in columns:
        if c.startswith(FORBIDDEN_PREFIXES) or c.endswith(FORBIDDEN_SUFFIXES) or c in TARGET_COLUMNS:
            bad.append(c)
    return bad


# ----------------------------------------------------------------------------------------------
# metrics
# ----------------------------------------------------------------------------------------------
def mae(y, p) -> float:
    return float(np.mean(np.abs(np.asarray(y) - np.asarray(p))))


def rmse(y, p) -> float:
    return float(np.sqrt(np.mean((np.asarray(y) - np.asarray(p)) ** 2)))


def mape(y, p) -> float:
    """Mean absolute percentage error in % (fine for demand, which is never near 0)."""
    y, p = np.asarray(y, float), np.asarray(p, float)
    return float(100 * np.mean(np.abs(y - p) / np.abs(y)))


def smape(y, p) -> float:
    """Symmetric MAPE in % (0..200): |y−p| / ((|y|+|p|)/2). Pairs with y = p = 0 count as 0 error."""
    y, p = np.asarray(y, float), np.asarray(p, float)
    den = (np.abs(y) + np.abs(p)) / 2
    ratio = np.where(den == 0, 0.0, np.abs(y - p) / np.where(den == 0, 1, den))
    return float(100 * np.mean(ratio))


def bias(y, p) -> float:
    """Mean of (forecast − actual): positive = forecast too high."""
    return float(np.mean(np.asarray(p) - np.asarray(y)))


def bootstrap_mae_ci(y, p, days, n_draws: int = 1000, seed: int = 42, level: float = 0.95):
    """Day-clustered bootstrap CI for the MAE: resample whole delivery days with replacement.

    Returns (low, high)."""
    err = pd.DataFrame({"day": np.asarray(days), "ae": np.abs(np.asarray(y) - np.asarray(p))})
    by_day = err.groupby("day")["ae"].agg(["sum", "count"])
    s, c = by_day["sum"].to_numpy(), by_day["count"].to_numpy()
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(s), size=(n_draws, len(s)))
    draws = s[idx].sum(axis=1) / c[idx].sum(axis=1)
    a = (1 - level) / 2
    return float(np.quantile(draws, a)), float(np.quantile(draws, 1 - a))


def metrics_long(pred: pd.DataFrame, target: str, models: Sequence[str], pct_metric: str = "mape",
                 ci_splits: Sequence[str] = ("test",), n_draws: int = 1000, seed: int = 42) -> pd.DataFrame:
    """Long metrics table from a predictions frame.

    `pred` needs columns delivery_date, block, split, y_true and pred_<model> for each model.
    Output columns: target, split, model, block ("all" or 0..5), mae, rmse, mape_or_smape, bias, n,
    mae_ci_low, mae_ci_high (CI only for splits in `ci_splits`, overall and per block)."""
    pct = mape if pct_metric == "mape" else smape
    rows = []
    for split, g in pred.groupby("split", sort=False):
        for m in models:
            col = f"pred_{m}"
            if col not in g.columns:
                continue
            for blk, gb in [("all", g)] + [(int(b), x) for b, x in g.groupby("block")]:
                ok = gb[col].notna() & gb["y_true"].notna()
                gb = gb[ok]
                if len(gb) == 0:
                    continue
                lo = hi = np.nan
                if split in ci_splits:
                    lo, hi = bootstrap_mae_ci(gb["y_true"], gb[col], gb["delivery_date"], n_draws, seed)
                rows.append({
                    "target": target, "split": split, "model": m, "block": str(blk),
                    "mae": mae(gb["y_true"], gb[col]), "rmse": rmse(gb["y_true"], gb[col]),
                    "mape_or_smape": pct(gb["y_true"], gb[col]), "bias": bias(gb["y_true"], gb[col]),
                    "n": int(len(gb)), "mae_ci_low": lo, "mae_ci_high": hi,
                })
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------------------------
# Diebold-Mariano test
# ----------------------------------------------------------------------------------------------
def dm_test(y, p_a, p_b, days, max_lag: int | None = None) -> dict:
    """Diebold-Mariano test on DAILY mean absolute errors (one loss value per delivery day).

    d_t = MAE_day(model A) − MAE_day(model B). Negative mean = A is better.
    Variance with Newey-West weights (lag = floor(n^(1/3)) by default) and the Harvey-Leybourne-
    Newbold small-sample correction; p-value from a t distribution with n−1 degrees of freedom
    (two-sided). Returns dict with mean_diff, dm_stat, p_value, n_days."""
    from scipy import stats

    e = pd.DataFrame({"day": np.asarray(days),
                      "a": np.abs(np.asarray(y) - np.asarray(p_a)),
                      "b": np.abs(np.asarray(y) - np.asarray(p_b))})
    daily = e.groupby("day")[["a", "b"]].mean()
    d = (daily["a"] - daily["b"]).to_numpy()
    n = len(d)
    if max_lag is None:
        max_lag = int(math.floor(n ** (1 / 3)))
    dbar = d.mean()
    dc = d - dbar
    var = np.sum(dc * dc) / n
    for k in range(1, max_lag + 1):
        w = 1 - k / (max_lag + 1)
        var += 2 * w * np.sum(dc[k:] * dc[:-k]) / n
    if var <= 0:
        return {"mean_diff": float(dbar), "dm_stat": np.nan, "p_value": np.nan, "n_days": n}
    dm = dbar / math.sqrt(var / n)
    h = 1  # one-step (one day) ahead
    hln = math.sqrt((n + 1 - 2 * h + h * (h - 1) / n) / n)
    dm_adj = dm * hln
    p = 2 * stats.t.sf(abs(dm_adj), df=n - 1)
    return {"mean_diff": float(dbar), "dm_stat": float(dm_adj), "p_value": float(p), "n_days": n}


# ----------------------------------------------------------------------------------------------
# model building blocks (must live here so joblib.load works from the app)
# ----------------------------------------------------------------------------------------------
class ColumnModel:
    """'Model' that returns one column of the input, e.g. the naive 7-day lag."""

    def __init__(self, column: str):
        self.column = column
        self.features = [column]

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        return df[self.column].to_numpy(dtype=float)


class ColumnSelect(BaseEstimator, TransformerMixin):
    """First step of a Pipeline: keep only `columns` of the input DataFrame (in this order)."""

    def __init__(self, columns: Sequence[str] = ()):
        self.columns = columns

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        return pd.DataFrame(X)[list(self.columns)]


class LinearDesign(BaseEstimator, TransformerMixin):
    """Feature builder for linear models (use inside a sklearn Pipeline before a scaler + Ridge).

    * numeric columns: median imputation (medians from the training data) + a 0/1 "was missing"
      column for columns that had NaN in training;
    * `onehot`: integer columns turned into one-hot dummies (categories seen in training);
    * `interactions`: list of (categorical_col, other) pairs. If `other` is a numeric column, one
      new column `1[cat == k] * other` is made per category k (e.g. a temperature slope per block).
      If `other` is written as "cat:<column>", one dummy per combination of the two categories is
      made (e.g. `("block", "cat:daytype")` = block × weekday-type one-hot).
    The output is a float numpy array."""

    def __init__(self, numeric: Sequence[str] = (), onehot: Sequence[str] = (),
                 interactions: Sequence[tuple] = ()):
        self.numeric = numeric
        self.onehot = onehot
        self.interactions = interactions

    def fit(self, X: pd.DataFrame, y=None):
        X = pd.DataFrame(X)
        self.medians_ = X[list(self.numeric)].median().fillna(0.0)
        self.missing_cols_ = [c for c in self.numeric if X[c].isna().any()]
        cats = set(self.onehot)
        for a, b in self.interactions:
            cats.add(a)
            if isinstance(b, str) and b.startswith("cat:"):
                cats.add(b[4:])
        self.categories_ = {c: sorted(pd.unique(X[c].dropna())) for c in cats}
        self.feature_names_ = list(self._build(X).columns)
        return self

    def _build(self, X: pd.DataFrame) -> pd.DataFrame:
        num = X[list(self.numeric)].astype(float).fillna(self.medians_)
        parts = [num]
        if self.missing_cols_:
            parts.append(X[self.missing_cols_].isna().astype(float).add_suffix("_missing"))
        for c in self.onehot:
            parts.append(pd.DataFrame({f"{c}={k}": (X[c] == k).astype(float) for k in self.categories_[c]},
                                      index=X.index))
        for a, b in self.interactions:
            if isinstance(b, str) and b.startswith("cat:"):
                b2 = b[4:]
                cols = {f"{a}={i}&{b2}={j}": ((X[a] == i) & (X[b2] == j)).astype(float)
                        for i in self.categories_[a] for j in self.categories_[b2]}
            else:
                v = X[b].astype(float).fillna(self.medians_.get(b, 0.0))
                cols = {f"{a}={i}*{b}": (X[a] == i).astype(float) * v for i in self.categories_[a]}
            parts.append(pd.DataFrame(cols, index=X.index))
        return pd.concat(parts, axis=1)

    def transform(self, X):
        out = self._build(pd.DataFrame(X))
        return out.to_numpy(dtype=float)

    def get_feature_names_out(self, input_features=None):
        return np.array(self.feature_names_)


def make_target(y: np.ndarray, ref: np.ndarray | None, transform: str) -> np.ndarray:
    """Turn the target into what the estimator learns.

    "level": y; "diff": y − ref; "ratio": y / ref − 1; "logratio": log(y / ref)."""
    if transform == "level":
        return np.asarray(y, float)
    if transform == "diff":
        return np.asarray(y, float) - ref
    if transform == "ratio":
        return np.asarray(y, float) / ref - 1
    if transform == "logratio":
        return np.log(np.asarray(y, float) / ref)
    raise ValueError(transform)


def invert_target(z: np.ndarray, ref: np.ndarray | None, transform: str) -> np.ndarray:
    """Inverse of `make_target`."""
    if transform == "level":
        return z
    if transform == "diff":
        return z + ref
    if transform == "ratio":
        return (1 + z) * ref
    if transform == "logratio":
        return np.exp(z) * ref
    raise ValueError(transform)


class ForecastModel:
    """The saved model: one object with `predict(df)` that takes rows of features.parquet.

    Parameters
    ----------
    target        name of the target column (only for documentation / training helpers)
    features      input columns the estimators expect (hybrid names, before the weather map)
    estimators    list of fitted objects with `.predict(X_dataframe)` (sklearn pipelines, LightGBM)
    weights       ensemble weights (default: equal); final = sum(w_i * component_i)
    transforms    per estimator: "level", "diff", "ratio" or "logratio" (see `make_target`)
    reference_col column used by non-level transforms (e.g. demand_lag_7d_same_block)
    weather_map   optional {hybrid_col: alternative_col} applied before predicting (e.g. JMA)
    quantiles     optional {0.1: est, 0.5: est, 0.9: est} (same transform as `quantile_transform`)
    preprocess    optional object with `.transform(df) -> df` that adds derived columns (run after
                  the weather map, before features / reference are read). Must be picklable, i.e. a
                  class defined in a module (e.g. `src.models.demand.DemandExtras`).
    info          free dict (config, training period, scores) stored with the model
    """

    def __init__(self, target: str, features: Sequence[str], estimators: list, weights=None,
                 transforms=None, reference_col: str | None = None, weather_map: dict | None = None,
                 quantiles: dict | None = None, quantile_transform: str = "level", preprocess=None,
                 info: dict | None = None):
        self.target = target
        self.features = list(features)
        self.estimators = list(estimators)
        self.weights = list(weights) if weights is not None else [1 / len(estimators)] * len(estimators)
        self.transforms = list(transforms) if transforms is not None else ["level"] * len(estimators)
        self.reference_col = reference_col
        self.weather_map = dict(weather_map or {})
        self.quantiles = dict(quantiles or {})
        self.quantile_transform = quantile_transform
        self.preprocess = preprocess
        self.info = dict(info or {})

    @property
    def input_columns(self) -> list[str]:
        """Raw columns of features.parquet the model reads (for importance / checks).

        Columns created by `preprocess` are replaced by the raw columns it declares in its
        `input_columns` attribute (if it has one)."""
        made = set(getattr(self.preprocess, "output_columns", []))
        cols = [c for c in self.features if c not in made]
        cols += list(getattr(self.preprocess, "input_columns", []))
        if self.reference_col and self.reference_col not in made:
            cols.append(self.reference_col)
        cols = [self.weather_map.get(c, c) for c in cols]
        return list(dict.fromkeys(cols))

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        """Weather map + preprocess: the frame the estimators and the reference are read from."""
        d = apply_weather_map(df, self.weather_map)
        if self.preprocess is not None:
            d = self.preprocess.transform(d)
        return d

    def _X(self, d: pd.DataFrame) -> pd.DataFrame:
        return d[self.features]

    def _ref(self, d: pd.DataFrame):
        return d[self.reference_col].to_numpy(dtype=float) if self.reference_col else None

    def predict_components(self, df: pd.DataFrame) -> np.ndarray:
        """Matrix (n_rows × n_estimators) of each component's forecast on the target scale."""
        d = self.prepare(df)
        X, ref = self._X(d), self._ref(d)
        return np.column_stack([invert_target(np.asarray(e.predict(X), float), ref, t)
                                for e, t in zip(self.estimators, self.transforms)])

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        return self.predict_components(df) @ np.asarray(self.weights, float)

    def predict_quantiles(self, df: pd.DataFrame) -> pd.DataFrame:
        """Columns pred_q10, pred_q50, pred_q90 (sorted per row so they never cross)."""
        if not self.quantiles:
            raise ValueError("model has no quantile estimators")
        d = self.prepare(df)
        X, ref = self._X(d), self._ref(d)
        qs = sorted(self.quantiles)
        m = np.column_stack([invert_target(np.asarray(self.quantiles[q].predict(X), float), ref,
                                           self.quantile_transform) for q in qs])
        m = np.sort(m, axis=1)
        return pd.DataFrame(m, columns=[f"pred_q{int(round(q * 100)):02d}" for q in qs], index=df.index)


# ----------------------------------------------------------------------------------------------
# permutation importance
# ----------------------------------------------------------------------------------------------
def permutation_importance_df(predict: Callable[[pd.DataFrame], np.ndarray], df: pd.DataFrame,
                              y: np.ndarray, columns, n_repeats: int = 5,
                              seed: int = 42) -> pd.DataFrame:
    """Increase in MAE when an input column (or a group of columns) is shuffled.

    `predict` takes a frame like `df`. `columns` is either a list of column names (each shuffled on
    its own) or a dict {group_name: [columns]} (the columns of a group are shuffled together, with
    the same row order, so their relation inside a row is kept). Returns feature, mae_increase
    (mean over `n_repeats`), std, base_mae, sorted from most to least important."""
    rng = np.random.default_rng(seed)
    y = np.asarray(y, float)
    base = mae(y, predict(df))
    groups = columns if isinstance(columns, dict) else {c: [c] for c in columns}
    rows = []
    for name, cols in groups.items():
        cols = [c for c in cols if c in df.columns]
        if not cols:
            continue
        incs = []
        for _ in range(n_repeats):
            d = df.copy()
            order = rng.permutation(len(d))
            for c in cols:
                d[c] = d[c].to_numpy()[order]
            incs.append(mae(y, predict(d)) - base)
        rows.append({"feature": name, "mae_increase": float(np.mean(incs)), "std": float(np.std(incs))})
    out = pd.DataFrame(rows).sort_values("mae_increase", ascending=False).reset_index(drop=True)
    out["base_mae"] = base
    return out


# ----------------------------------------------------------------------------------------------
# figures
# ----------------------------------------------------------------------------------------------
def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def plot_forecast_vs_actual(pred: pd.DataFrame, file, title: str, unit: str,
                            models=("best", "naive"), band: tuple | None = None):
    """Line plot of y_true and some forecasts over the rows of `pred` (time order).

    `band` = (low_col, high_col) draws a shaded prediction band."""
    plt = _plt()
    p = pred.sort_values(["delivery_date", "block"]).reset_index(drop=True)
    x = p["delivery_date"] + pd.to_timedelta(p["block"] * 4 + 2, unit="h")
    fig, ax = plt.subplots(figsize=(13, 4.5))
    if band and all(c in p.columns for c in band):
        ax.fill_between(x, p[band[0]], p[band[1]], color="#9ecae1", alpha=0.5, label="10–90 % band")
    ax.plot(x, p["y_true"], color="black", lw=1.6, label="actual")
    colors = {"best": "#d62728", "naive": "#7f7f7f", "gbm": "#1f77b4", "linear": "#2ca02c"}
    for m in models:
        ax.plot(x, p[f"pred_{m}"], lw=1.1, ls="-" if m == "best" else "--",
                color=colors.get(m), label=f"{m} forecast")
    ax.set_title(title)
    ax.set_ylabel(unit)
    ax.legend(loc="upper left", ncol=4, fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(file, dpi=130)
    plt.close(fig)


def plot_error_by_block(metrics: pd.DataFrame, file, split: str, title: str, unit: str,
                        models=("naive", "linear", "rf", "gbm", "best")):
    """Grouped bars: MAE per block for each model on one split."""
    plt = _plt()
    m = metrics[(metrics["split"] == split) & (metrics["block"] != "all")]
    blocks = sorted(m["block"].unique(), key=int)
    labels = ["00–04", "04–08", "08–12", "12–16", "16–20", "20–24"]
    fig, ax = plt.subplots(figsize=(10, 4.5))
    w = 0.8 / len(models)
    for i, name in enumerate(models):
        vals = [m[(m["model"] == name) & (m["block"] == b)]["mae"].mean() for b in blocks]
        ax.bar(np.arange(len(blocks)) + i * w - 0.4 + w / 2, vals, width=w, label=name)
    ax.set_xticks(range(len(blocks)))
    ax.set_xticklabels([labels[int(b)] for b in blocks])
    ax.set_ylabel(f"MAE ({unit})")
    ax.set_title(title)
    ax.legend(fontsize=9)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(file, dpi=130)
    plt.close(fig)


def plot_model_ladder(metrics: pd.DataFrame, file, title: str, unit: str,
                      models=("naive", "linear", "rf", "gbm", "best"), splits=("rolling", "val", "test")):
    """Bars: overall MAE per model, one group per split."""
    plt = _plt()
    m = metrics[metrics["block"] == "all"]
    splits = [s for s in splits if s in set(m["split"])]
    fig, ax = plt.subplots(figsize=(9, 4.5))
    w = 0.8 / len(models)
    for i, name in enumerate(models):
        vals = [m[(m["model"] == name) & (m["split"] == s)]["mae"].mean() for s in splits]
        bars = ax.bar(np.arange(len(splits)) + i * w - 0.4 + w / 2, vals, width=w, label=name)
        for b, v in zip(bars, vals):
            if np.isfinite(v):
                ax.text(b.get_x() + b.get_width() / 2, v, f"{v:.1f}", ha="center", va="bottom", fontsize=7)
    ax.set_xticks(range(len(splits)))
    ax.set_xticklabels(splits)
    ax.set_ylabel(f"MAE ({unit})")
    ax.set_title(title)
    ax.legend(fontsize=9)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(file, dpi=130)
    plt.close(fig)


def plot_importance(imp: pd.DataFrame, file, title: str, unit: str, top: int = 20):
    """Horizontal bars of the permutation importance (top `top` features)."""
    plt = _plt()
    d = imp.head(top).iloc[::-1]
    fig, ax = plt.subplots(figsize=(8, 0.32 * len(d) + 1.2))
    ax.barh(d["feature"], d["mae_increase"], xerr=d.get("std"), color="#4c72b0")
    ax.set_xlabel(f"MAE increase when shuffled ({unit})")
    ax.set_title(title)
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    fig.savefig(file, dpi=130)
    plt.close(fig)
