"""Day-ahead price model for Switzerland (target `price_eur_mwh`, mean CH day-ahead price per 4-hour block).

Run everything (frozen settings from models/price_best_params.json, < 10 min):
    .venv/bin/python -m src.models.price
Options:
    --tune          redo the hyper-parameter search (slow) and rewrite the params file
    --experiments   redo the September comparison of variants + sensitivity runs (slow)

How the forecast works (the "best" model, details in reports/model_notes_price.md)
* Reference = a price that is already known at 10:00 on day D (see `params["best"]["reference_col"]`).
* LightGBM learns the CHANGE of the block price versus that reference - trees cannot extrapolate a
  fuel-driven price level, but they predict changes well.
* Recent days get more weight (exponential decay with a half-life), several seeds are averaged and
  blended with a LEAR-style ridge regression (same target).
* Quantile LightGBM models (10/50/90 %) give a prediction band for the decision layer.

Ladder models (plain versions, for comparison): naive = same block 7 days earlier, linear = ridge
on the price level, rf = random forest on the level, gbm = LightGBM on the level.
"""
from __future__ import annotations

import argparse
import json
import time

import joblib
from joblib import Parallel, delayed
import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.config import load_config, path
from src.features import feature_sets as fs
from src.models.common import (
    ColumnModel, ColumnSelect, ForecastModel, LinearDesign, apply_weather_map, bias, dm_test, load_features, mae,
    metrics_long, permutation_importance_df, plot_error_by_block, plot_forecast_vs_actual, plot_importance,
    plot_model_ladder, rmse, smape, split_frame,
)
from src.models.price_common import AsinhTarget, DayShapeTarget, PriceExtras, ScaledQuantile

TARGET = fs.TARGET_PRICE
NAIVE_COL = "price_lag_7d_same_block"
TARGET_LAG_DAYS = 1          # forecasting delivery day T: the latest known price row is T−1 (= day D)
LADDER = ["naive", "linear", "rf", "gbm"]
MODELS = LADDER + ["best"]
PARAMS_FILE = "price_best_params.json"
N_PROCESSES = 5              # parallel model fits (walk-forward chunks, rolling months)
BLOCK_LABELS = ["00–04", "04–08", "08–12", "12–16", "16–20", "20–24"]

# ---- feature groups (sensitivity runs and group importance) ----
EU_COLS = [c for c in fs.PRICE_FEATURES if c.startswith("eu_")]
EU_ICON_COLS = [c for c in EU_COLS if "_jma_" not in c]
EU_JMA_COLS = [c for c in EU_COLS if "_jma_" in c]
NEIGHBOUR_COLS = list(fs.NEIGHBOUR_FEATURES) + ["de_shape_dD", "fr_shape_dD", "it_shape_dD"]
FUEL_COLS = ["gas_ttf_d_1", "gas_ttf_change_5d", "gas_ttf_mean_20d", "co2_eua_d_1", "co2_staleness_days",
             "eurchf_d_1", "clean_gas_cost", "gas_vs_price"]
HYDRO_COLS = ["reservoir_fill_pct", "reservoir_vs_median_pct", "reservoir_change_1w"]
ZH_WEATHER_COLS = list(fs.WEATHER_FEATURES) + list(fs.PAST_WEATHER_FEATURES) + ["rad_x_weekend", "rad_x_trend"]
CH_PRICE_COLS = list(fs.PRICE_LAG_FEATURES) + ["shape_dD", "shape_lag7", "ref_shape7"]
SWISS_SYSTEM_COLS = list(fs.SWISS_SYSTEM_FEATURES) + ["resid_proxy", "solar_ch_mw_lag_2d_same_block",
                                                      "solar_ch_day_mean_lag_2d"]
DEMAND_COLS = ["demand_lag_2d_same_block", "demand_day_mean_lag_2d", "demand_lag_7d_same_block",
               "expected_demand_proxy"]
CALENDAR_COLS = list(fs.CALENDAR_FEATURES) + ["dD_weekday", "dD_daytype", "day_change_type"]
UNVERIFIED_DE = ["unverified_de_solar_fc", "unverified_de_solar_fc_day", "unverified_de_wind_onshore_fc",
                 "unverified_de_wind_onshore_fc_day", "unverified_de_wind_offshore_fc",
                 "unverified_de_wind_offshore_fc_day", "unverified_de_load_fc", "unverified_de_load_fc_day"]

# named groups for `drop_features` in the params file (keeps the json short)
DROP_GROUPS = {"EU_ICON": EU_ICON_COLS, "NONE": []}

# linear models: categorical columns made into dummies; trending inputs that a straight line extrapolates badly
LINEAR_ONEHOT = ["block", "weekday", "month", "day_change_type"]
LINEAR_CATEGORICAL = LINEAR_ONEHOT + ["school_holiday_type", "dD_weekday", "dD_daytype", "kickoff_hour_local"]
LINEAR_DROP = ["year_frac", "covid_stringency", "day_of_year", "week_of_year"]

DEFAULT_PARAMS = {
    "seed": 42,
    "linear_ladder": {"alpha": 10.0},
    "rf_ladder": {"n_estimators": 120, "max_depth": 14, "min_samples_leaf": 5, "max_features": 0.4},
    "gbm_ladder": {"learning_rate": 0.03, "n_estimators": 1000, "num_leaves": 31, "min_child_samples": 20,
                   "subsample": 0.8, "subsample_freq": 1, "colsample_bytree": 0.5, "reg_lambda": 0.0},
    "best": {
        "transform": "diff",                   # level | diff | asinh
        "reference_col": "ref_shape7",
        "asinh_scale": 50.0,
        "weather": "hybrid",                   # hybrid | oracle (sensitivity only)
        "drop_features": "EU_ICON",               # name of a column group (see DROP_GROUPS) or a list
        "add_features": [],
        "use_extras": True,
        "gbm_params": {"learning_rate": 0.03, "n_estimators": 1000, "num_leaves": 31, "min_child_samples": 20,
                       "subsample": 0.8, "subsample_freq": 1, "colsample_bytree": 0.5, "reg_lambda": 0.0},
        "n_seeds": 3,
        "objective": "l2",
        "huber_alpha": 20.0,
        "half_life_years": 1.0,
        "start_date": None,
        "linear_weight": 0.35,
        "linear_alpha": 30.0,
        "linear_windows_years": [None],
        "walk_forward": True,
        "refit_every_days": 7,
        "quantiles": [0.1, 0.5, 0.9],
        "band_factor": 1.4,
        "quantile_params": {"learning_rate": 0.03, "n_estimators": 600, "num_leaves": 15,
                            "min_child_samples": 40, "subsample": 0.8, "subsample_freq": 1,
                            "colsample_bytree": 0.5},
    },
}


# ----------------------------------------------------------------------------------------------
# settings and feature lists
# ----------------------------------------------------------------------------------------------
def load_params() -> dict:
    """Frozen settings from models/price_best_params.json (defaults if the file does not exist)."""
    f = path("models") / PARAMS_FILE
    if f.exists():
        with open(f) as fh:
            return json.load(fh)
    return json.loads(json.dumps(DEFAULT_PARAMS))


def weather_map_for(variant: str) -> dict:
    """Weather column map: "hybrid" (none) or "oracle" (observed Zurich weather, sensitivity only)."""
    return {"oracle": fs.ORACLE_WEATHER_MAP, "jma": fs.JMA_WEATHER_MAP}.get(variant, {})


def best_features(cfg: dict) -> list[str]:
    """Input columns of the LightGBM part of the best model (raw + derived columns)."""
    feats = list(fs.PRICE_FEATURES)
    if cfg.get("use_extras", True):
        feats += PriceExtras.output_columns
    feats += list(cfg.get("add_features", []))
    drop = set(dropped(cfg))
    return [c for c in dict.fromkeys(feats) if c not in drop]


def dropped(cfg: dict) -> list[str]:
    """Columns the configuration leaves out (`drop_features` may be a group name or a list)."""
    drop = cfg.get("drop_features", [])
    return list(DROP_GROUPS[drop] if isinstance(drop, str) else drop)


def with_drop(cfg: dict, cols) -> dict:
    """Copy of `cfg` that leaves out `cols` IN ADDITION to the columns it already drops."""
    return dict(cfg, drop_features=list(dict.fromkeys(dropped(cfg) + list(cols))))


def linear_columns(feats: list[str], onehot=LINEAR_ONEHOT) -> tuple[list[str], list[str]]:
    """(input columns, numeric columns) of the ridge models built from a feature list."""
    cols = [c for c in feats if c not in LINEAR_DROP]
    for c in onehot:
        if c not in cols:
            cols.append(c)
    numeric = [c for c in cols if c not in LINEAR_CATEGORICAL]
    return cols, numeric


def sample_weights(d: pd.DataFrame, cfg: dict) -> np.ndarray:
    """Row weights: exponential recency decay with half-life `half_life_years` (None = equal weights)."""
    w = np.ones(len(d))
    hl = cfg.get("half_life_years")
    if hl:
        age = (d["delivery_date"].max() - d["delivery_date"]).dt.days.to_numpy() / 365.25
        w *= 0.5 ** (age / hl)
    return w


# ----------------------------------------------------------------------------------------------
# model builders
# ----------------------------------------------------------------------------------------------
def make_lgbm(params: dict, seed: int, objective: str = "l2", alpha: float | None = None):
    p = dict(params)
    p.setdefault("subsample_freq", 1)
    # 2 threads is the fastest setting for this small table; speed comes from fitting several models in
    # parallel processes instead (see `N_PROCESSES`)
    kw = {"objective": objective, "random_state": seed, "verbose": -1, "n_jobs": 2, "deterministic": True,
          "force_row_wise": True}
    if alpha is not None:
        kw["alpha"] = alpha
    return lgb.LGBMRegressor(**p, **kw)


def make_linear(alpha: float, cols: list[str], numeric: list[str], onehot=LINEAR_ONEHOT) -> Pipeline:
    """Ridge regression (LEAR-style benchmark) on a design with block / weekday / month dummies and
    per-block slopes for the most important prices."""
    inter = [("block", c) for c in ["price_lag_1d_same_block", "price_mean_day_D", "price_lag_7d_same_block",
                                    "radiation_wm2", "clean_gas_cost", "price_de_day_D_same_block",
                                    "eu_wind_cubed_de_mean_jma_safe", "eu_radiation_wm2_de_mean_safe"]
             if c in numeric]
    inter += [("block", "cat:weekday")]
    return Pipeline([("select", ColumnSelect(cols)),
                     ("design", LinearDesign(numeric=numeric, onehot=onehot, interactions=inter)),
                     ("scale", StandardScaler()), ("ridge", Ridge(alpha=alpha))])


def fit_ladder(train: pd.DataFrame, params: dict) -> dict:
    """Fit the plain ladder models (naive, linear, rf, gbm), all on the price LEVEL with the default
    PRICE_FEATURES (no derived columns, no recency weights)."""
    seed = params["seed"]
    train = train[train[TARGET].notna()]
    y = train[TARGET].to_numpy()
    feats = list(fs.PRICE_FEATURES)
    onehot = ["block", "weekday", "month"]              # the ladder has no derived columns
    lin_cols, lin_num = linear_columns(feats, onehot)
    lin = make_linear(params["linear_ladder"]["alpha"], lin_cols, lin_num, onehot).fit(train, y)
    rf = Pipeline([("select", ColumnSelect(feats)), ("impute", SimpleImputer(strategy="median")),
                   ("rf", RandomForestRegressor(random_state=seed, n_jobs=2, **params["rf_ladder"]))])
    rf.fit(train, y)
    gbm = Pipeline([("select", ColumnSelect(feats)), ("gbm", make_lgbm(params["gbm_ladder"], seed))])
    gbm.fit(train, y)
    info = {"trained_until": str(train["delivery_date"].max().date())}
    return {
        "naive": ColumnModel(NAIVE_COL),
        "linear": ForecastModel(TARGET, lin_cols, [lin], info=info),
        "rf": ForecastModel(TARGET, feats, [rf], info=info),
        "gbm": ForecastModel(TARGET, feats, [gbm], info=info),
    }


def _wrap(est, cfg: dict):
    """Apply the asinh target wrapper if the configuration asks for it."""
    if cfg.get("transform") == "asinh":
        return AsinhTarget(est, cfg["reference_col"], cfg.get("asinh_scale", 50.0))
    return est


def fit_best(train: pd.DataFrame, params: dict, cfg: dict | None = None, quantiles: bool = True) -> ForecastModel:
    """Fit the best configuration (`params["best"]`, or `cfg` if given) on `train`."""
    cfg = cfg or params["best"]
    seed = params["seed"]
    wmap = weather_map_for(cfg.get("weather", "hybrid"))
    pre = PriceExtras()
    d = pre.transform(apply_weather_map(train, wmap))
    d = d[d[TARGET].notna()]
    if cfg.get("start_date"):
        d = d[d["delivery_date"] >= pd.Timestamp(cfg["start_date"])]
    transform = cfg.get("transform", "diff")
    ref_col = cfg.get("reference_col")
    # ForecastModel handles "level" and "diff"; asinh is handled inside the AsinhTarget wrapper
    fm_transform = "diff" if transform == "diff" else "level"
    y = d[TARGET].to_numpy()
    z = y - d[ref_col].to_numpy() if transform == "diff" else y
    w = sample_weights(d, cfg)
    feats = best_features(cfg)
    if transform == "asinh" and ref_col not in feats:
        feats.append(ref_col)

    estimators, weights = [], []
    n_seeds = int(cfg.get("n_seeds", 1))
    lw = float(cfg.get("linear_weight", 0.0))
    obj = cfg.get("objective", "l2")
    alpha = cfg.get("huber_alpha") if obj == "huber" else None
    transforms = []
    for k in range(n_seeds):
        if cfg.get("two_stage"):
            # day-mean change vs day D + within-day shape, each learnt by its own LightGBM
            m = DayShapeTarget(*[Pipeline([("select", ColumnSelect(feats)),
                                           ("gbm", make_lgbm(cfg["gbm_params"], seed + k + j, obj, alpha))])
                                 for j in (0, 100)])
            m.fit(d, y, sample_weight=w, day_key=d["delivery_date"].to_numpy())
            transforms.append("level")
        else:
            m = _wrap(Pipeline([("select", ColumnSelect(feats)),
                                ("gbm", make_lgbm(cfg["gbm_params"], seed + k, obj, alpha))]), cfg)
            if isinstance(m, AsinhTarget):
                m.fit(d, y, sample_weight=w)
            else:
                m.fit(d, z, gbm__sample_weight=w)
            transforms.append(fm_transform)
        estimators.append(m)
        weights.append((1 - lw) / n_seeds)
    all_cols = list(feats)
    if lw > 0:
        lin_cols, lin_num = linear_columns(feats)
        windows = cfg.get("linear_windows_years") or [None]
        for win in windows:
            dd, zz, ww = d, z, w
            if win:
                keep = (d["delivery_date"] > d["delivery_date"].max() - pd.Timedelta(days=int(365.25 * win))).to_numpy()
                dd, zz, ww = d[keep], z[keep], w[keep]
            lin = _wrap(make_linear(cfg.get("linear_alpha", 30.0), lin_cols, lin_num), cfg)
            if isinstance(lin, AsinhTarget):
                lin.fit(dd, dd[TARGET].to_numpy(), sample_weight=ww)
            else:
                lin.fit(dd, zz, ridge__sample_weight=ww)
            estimators.append(lin)
            transforms.append(fm_transform)
            weights.append(lw / len(windows))
        all_cols += lin_cols
    qmodels = {}
    if quantiles and cfg.get("quantiles"):
        for q in cfg["quantiles"]:
            m = _wrap(Pipeline([("select", ColumnSelect(feats)),
                                ("gbm", make_lgbm(cfg["quantile_params"], seed, "quantile", alpha=q))]), cfg)
            if isinstance(m, AsinhTarget):
                m.fit(d, y, sample_weight=w)
            else:
                m.fit(d, z, gbm__sample_weight=w)
            qmodels[q] = m
        k = float(cfg.get("band_factor", 1.0))
        if k != 1.0 and 0.5 in qmodels:
            med = qmodels[0.5]
            qmodels = {q: (m if q == 0.5 else ScaledQuantile(m, med, k)) for q, m in qmodels.items()}
    # the model reads the prepared frame; ForecastModel._X selects `features`, so the reference and
    # every column a linear part needs must be in that list
    if ref_col and ref_col not in all_cols:
        all_cols.append(ref_col)
    return ForecastModel(
        TARGET, list(dict.fromkeys(all_cols)), estimators, weights=weights, transforms=transforms,
        reference_col=ref_col if fm_transform == "diff" else None, weather_map=wmap, quantiles=qmodels,
        quantile_transform=fm_transform, preprocess=pre,
        info={"trained_until": str(d["delivery_date"].max().date()), "config": cfg},
    )


# ----------------------------------------------------------------------------------------------
# training / prediction schemes
# ----------------------------------------------------------------------------------------------
def train(df: pd.DataFrame, until, params: dict, quantiles: bool = True) -> tuple[dict, ForecastModel]:
    """Fit ladder + best on all rows with delivery_date ≤ `until`. Returns (ladder dict, best)."""
    tr = df[df["delivery_date"] <= pd.Timestamp(until)]
    return fit_ladder(tr, params), fit_best(tr, params, quantiles=quantiles)


def predict_frame(rows: pd.DataFrame, ladder: dict, best: ForecastModel | None, split: str) -> pd.DataFrame:
    """Predictions of all models for `rows` in the format of reports/predictions_price.parquet."""
    out = rows[["delivery_date", "block"]].copy()
    out["split"] = split
    out["y_true"] = rows[TARGET].to_numpy()
    for name, m in ladder.items():
        out[f"pred_{name}"] = m.predict(rows)
    if best is not None:
        out["pred_best"] = best.predict(rows)
        if best.quantiles:
            out = pd.concat([out, best.predict_quantiles(rows).set_axis(out.index)], axis=1)
    return out


def walk_forward_best(df: pd.DataFrame, days, params: dict, cfg: dict | None = None,
                      quantiles: bool = False) -> pd.DataFrame:
    """Refit the best model during the month: a model refit on day R uses only rows ≤ R−1 (prices known
    at the forecast time for delivery day R) and forecasts R, R+1, … until the next refit
    (`refit_every_days`, 1 = every day). Returns a frame with pred_best (and quantiles if asked)."""
    cfg = cfg or params["best"]
    every = int(cfg.get("refit_every_days", 1) or 1)
    days = [pd.Timestamp(x) for x in sorted(days)]
    chunks = [days[i:i + every] for i in range(0, len(days), every)]
    parts = Parallel(n_jobs=min(N_PROCESSES, len(chunks)))(
        delayed(_walk_forward_chunk)(df, chunk, params, cfg, quantiles) for chunk in chunks)
    return pd.concat(parts)


def _walk_forward_chunk(df, chunk, params, cfg, quantiles):
    """One refit of the walk-forward: fit on rows ≤ first day − 1, forecast all days of the chunk."""
    tr = df[df["delivery_date"] <= chunk[0] - pd.Timedelta(days=TARGET_LAG_DAYS)]
    rows = df[df["delivery_date"].isin(chunk)]
    m = fit_best(tr, params, cfg, quantiles=quantiles)
    p = rows[["delivery_date", "block"]].copy()
    p["pred_best"] = m.predict(rows)
    if quantiles and m.quantiles:
        p = pd.concat([p, m.predict_quantiles(rows).set_axis(p.index)], axis=1)
    return p


def rolling_backtest(df: pd.DataFrame, params: dict, start="2025-10-01", end="2026-08-31") -> pd.DataFrame:
    """Frozen configuration refit at the start of each month on all rows known then (≤ start − 1 day),
    predicting that month. Split label "rolling"."""
    months = list(pd.date_range(start, end, freq="MS"))
    parts = Parallel(n_jobs=min(N_PROCESSES, len(months)))(
        delayed(_rolling_month)(df, m0, params, end) for m0 in months)
    for m0, p in zip(months, parts):
        print(f"  rolling {m0:%Y-%m}: best MAE {mae(p['y_true'], p['pred_best']):.2f}", flush=True)
    return pd.concat(parts, ignore_index=True)


def _rolling_month(df, m0, params, end):
    """Fit ladder + best on rows ≤ m0 − 1 day and predict the month starting at m0."""
    m1 = m0 + pd.offsets.MonthEnd(0)
    tr = df[df["delivery_date"] <= m0 - pd.Timedelta(days=TARGET_LAG_DAYS)]
    rows = df[(df["delivery_date"] >= m0) & (df["delivery_date"] <= min(m1, pd.Timestamp(end)))]
    rows = rows[rows[TARGET].notna()]
    return predict_frame(rows, fit_ladder(tr, params), fit_best(tr, params, quantiles=True), "rolling")


# ----------------------------------------------------------------------------------------------
# evaluation
# ----------------------------------------------------------------------------------------------
def decision_scores(g: pd.DataFrame, col: str) -> dict:
    """Metrics that matter for the battery plan, from rows with delivery_date, y_true and `col`:

    rank_corr      Spearman rank correlation of the 6 block prices within a day (mean over days)
    hit_cheapest   share of days where the cheapest forecast block is the cheapest actual block
    hit_dearest    same for the most expensive block
    shape_mae      MAE of the within-day deviation (block price − day mean): is the daily SHAPE right?
    daymean_mae    MAE of the day-mean price (is the LEVEL right?)"""
    rc, hc, he, dv, dm = [], [], [], [], []
    for _, x in g.groupby("delivery_date"):
        y, p = x["y_true"].to_numpy(float), x[col].to_numpy(float)
        if len(y) < 2 or np.isnan(p).any():
            continue
        r = spearmanr(y, p).statistic
        rc.append(r if np.isfinite(r) else 0.0)
        hc.append(np.argmin(y) == np.argmin(p))
        he.append(np.argmax(y) == np.argmax(p))
        dv.append(np.mean(np.abs((y - y.mean()) - (p - p.mean()))))
        dm.append(abs(y.mean() - p.mean()))
    return {"rank_corr": float(np.mean(rc)), "hit_cheapest": float(np.mean(hc)), "hit_dearest": float(np.mean(he)),
            "shape_mae": float(np.mean(dv)), "daymean_mae": float(np.mean(dm)), "n_days": len(rc)}


def decision_table(pred: pd.DataFrame) -> pd.DataFrame:
    """Decision metrics for every model and split."""
    rows = []
    for split, g in pred.groupby("split", sort=False):
        for m in MODELS:
            if f"pred_{m}" in g.columns:
                rows.append({"target": "price", "split": split, "model": m, **decision_scores(g, f"pred_{m}")})
    return pd.DataFrame(rows)


def evaluate(pred: pd.DataFrame, seed: int = 42) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Metrics (long format, sMAPE) and Diebold–Mariano tests from a predictions frame."""
    met = metrics_long(pred, "price", MODELS, "smape", ci_splits=("val", "test"), seed=seed)
    tests = []
    for split in ["val", "test", "rolling"]:
        g = pred[pred["split"] == split]
        if g.empty:
            continue
        for other in ["naive", "gbm"]:
            r = dm_test(g["y_true"], g["pred_best"], g[f"pred_{other}"], g["delivery_date"])
            tests.append({"target": "price", "split": split, "model_a": "best", "model_b": other,
                          "loss": "daily mean absolute error", **r})
    return met, pd.DataFrame(tests)


def quantile_coverage(pred: pd.DataFrame) -> pd.DataFrame:
    """Share of actuals inside the 10–90 % band, and below q10 / above q90, per split."""
    if "pred_q10" not in pred.columns:
        return pd.DataFrame()
    g = pred.dropna(subset=["pred_q10"]).groupby("split")
    return pd.DataFrame({
        "inside_10_90": g.apply(lambda x: ((x.y_true >= x.pred_q10) & (x.y_true <= x.pred_q90)).mean()),
        "below_q10": g.apply(lambda x: (x.y_true < x.pred_q10).mean()),
        "above_q90": g.apply(lambda x: (x.y_true > x.pred_q90).mean()),
        "mean_width_eur": g.apply(lambda x: (x.pred_q90 - x.pred_q10).mean()),
    }).round(3)


def worst_blocks(pred: pd.DataFrame, df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """The `n` test blocks with the largest absolute error of the best model, with context columns and an
    automatic short description of what was special (the notes add a human explanation)."""
    t = pred[pred["split"] == "test"].copy()
    t["error"] = t["pred_best"] - t["y_true"]
    t["abs_error"] = t["error"].abs()
    ctx = ["weekday", "is_holiday", "price_lag_1d_same_block", "price_mean_day_D", "price_lag_7d_same_block",
           "price_neg_hours_day_D", "radiation_wm2", "eu_wind_cubed_de_mean_jma_safe", "gas_ttf_d_1",
           "actual_price_min_block", "actual_price_max_block"]
    t = t.merge(df[["delivery_date", "block"] + [c for c in ctx if c in df.columns]],
                on=["delivery_date", "block"], how="left")
    w = t.nlargest(n, "abs_error").copy()
    day_mean = pred[pred["split"] == "test"].groupby("delivery_date")["y_true"].mean()
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    def describe(r):
        bits = [names[int(r["weekday"])] + (" (holiday)" if r["is_holiday"] == 1 else "")]
        bits.append("forecast too high" if r["error"] > 0 else "forecast too low")
        jump = r["y_true"] - r["price_lag_1d_same_block"]
        if abs(jump) > 40:
            bits.append(f"price {'jumped' if jump > 0 else 'fell'} {abs(jump):.0f} EUR vs same block on day D")
        if r["y_true"] < 30:
            bits.append("very low / negative-price block")
        if r["actual_price_max_block"] - r["actual_price_min_block"] > 80:
            bits.append("large swing inside the block")
        dm = day_mean.get(r["delivery_date"], np.nan)
        if np.isfinite(dm) and r["block"] in (4, 5) and r["y_true"] > dm * 1.25:
            bits.append("evening spike")
        if r["block"] == 3 and r["y_true"] < dm * 0.6:
            bits.append("deep solar midday dip")
        return "; ".join(bits)

    w["what_happened"] = w.apply(describe, axis=1)
    w["block"] = w["block"].map(lambda b: f"{int(b)} ({BLOCK_LABELS[int(b)]})")
    w["delivery_date"] = pd.to_datetime(w["delivery_date"]).dt.date
    keep = ["delivery_date", "block", "y_true", "pred_best", "error", "pred_naive", "price_lag_1d_same_block",
            "pred_q10", "pred_q90", "what_happened"]
    return w[[c for c in keep if c in w.columns]].reset_index(drop=True)


def group_importance_columns(model: ForecastModel) -> dict:
    """Driver groups for the group permutation importance (raw columns of features.parquet).

    Derived columns are rebuilt by the model's preprocess from the raw columns, so shuffling the raw
    columns of a group also scrambles the derived columns built from them."""
    cols = set(model.input_columns)
    groups = {
        "CH price of day D (lags, shape)": list(fs.PRICE_LAG_FEATURES),
        "neighbour prices DE/FR/AT/IT (day D)": list(fs.NEIGHBOUR_FEATURES),
        "gas / CO2 / EUR-CHF": [c for c in FUEL_COLS if c in fs.FUEL_HYDRO_FEATURES],
        "Swiss reservoirs": HYDRO_COLS,
        "European weather forecasts ICON (eu_*)": EU_ICON_COLS,
        "European weather forecasts JMA (eu_*_jma)": EU_JMA_COLS,
        "Zurich weather (forecast + past observed)": list(fs.WEATHER_FEATURES) + list(fs.PAST_WEATHER_FEATURES),
        "Swiss system D−1 (load, hydro, nuclear, solar)": list(fs.SWISS_SYSTEM_FEATURES)
        + ["solar_ch_mw_lag_2d_same_block", "solar_ch_day_mean_lag_2d"],
        "Zurich demand lags": DEMAND_COLS,
        "calendar (block, weekday, holidays, season)": list(fs.CALENDAR_FEATURES),
    }
    return {k: [c for c in v if c in cols] for k, v in groups.items() if any(c in cols for c in v)}


def importance(df: pd.DataFrame, m_val: ForecastModel, m_test: ForecastModel, seed: int):
    """Permutation importance of the best model on September (fit on train) + October (fit on train+val):
    single raw columns and driver groups."""
    rows = pd.concat([split_frame(df, "val"), split_frame(df, "test")])
    rows = rows[rows[TARGET].notna()]
    is_val = (rows["delivery_date"] <= pd.Timestamp(load_config()["periods"]["val_end"])).to_numpy()

    def predict(d):
        out = np.empty(len(d))
        out[is_val] = m_val.predict(d[is_val])
        out[~is_val] = m_test.predict(d[~is_val])
        return out

    y = rows[TARGET].to_numpy()
    single = permutation_importance_df(predict, rows, y, m_test.input_columns, n_repeats=3, seed=seed)
    groups = permutation_importance_df(predict, rows, y, group_importance_columns(m_test), n_repeats=5, seed=seed)
    return single, groups


# ----------------------------------------------------------------------------------------------
# hyper-parameter search (--tune)
# ----------------------------------------------------------------------------------------------
def _cv_days(train_df: pd.DataFrame, n_splits: int = 5):
    from sklearn.model_selection import TimeSeriesSplit
    days = np.array(sorted(train_df["delivery_date"].unique()))
    return [(days[a], days[b]) for a, b in TimeSeriesSplit(n_splits).split(days)]


def cv_score(train_df: pd.DataFrame, fit_predict, n_splits: int = 5) -> list[float]:
    """MAE per TimeSeriesSplit fold (folds made of whole days). `fit_predict(tr, te) -> preds`."""
    train_df = train_df[train_df[TARGET].notna()]

    def one(a, b):
        tr, te = train_df[train_df["delivery_date"].isin(a)], train_df[train_df["delivery_date"].isin(b)]
        return mae(te[TARGET], fit_predict(tr, te))
    return Parallel(n_jobs=n_splits, prefer="threads")(delayed(one)(a, b) for a, b in _cv_days(train_df, n_splits))


def tune(df: pd.DataFrame, params: dict, n_trials: int = 25) -> dict:
    """TimeSeriesSplit(5) search on the training period: optuna for the best model's LightGBM (score =
    mean of the two most recent folds, the regime closest to 2026), small grids for the ladder."""
    import optuna
    train_df = split_frame(df, "train")
    best_cfg = dict(params["best"], n_seeds=1, linear_weight=0.0, quantiles=[])

    def objective(trial):
        p = {"learning_rate": trial.suggest_float("learning_rate", 0.01, 0.1, log=True),
             "n_estimators": trial.suggest_int("n_estimators", 300, 2500, log=True),
             "num_leaves": trial.suggest_int("num_leaves", 7, 127, log=True),
             "min_child_samples": trial.suggest_int("min_child_samples", 5, 100, log=True),
             "colsample_bytree": trial.suggest_float("colsample_bytree", 0.2, 1.0),
             "subsample": trial.suggest_float("subsample", 0.5, 1.0),
             "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 30, log=True), "subsample_freq": 1}
        cfg = dict(best_cfg, gbm_params=p)
        s = cv_score(train_df, lambda a, b: fit_best(a, params, cfg, quantiles=False).predict(b))
        print(f"  trial {trial.number}: CV MAE {np.mean(s):.3f}, last-2 folds {np.mean(s[-2:]):.3f}", flush=True)
        return float(np.mean(s[-2:]))

    study = optuna.create_study(sampler=optuna.samplers.TPESampler(seed=params["seed"]))
    start = {k: v for k, v in params["best"]["gbm_params"].items() if k != "subsample_freq"}
    study.enqueue_trial(dict(start, reg_lambda=max(start.get("reg_lambda", 0.0), 1e-3)))
    study.optimize(objective, n_trials=n_trials)
    params["best"]["gbm_params"] = {**study.best_params, "subsample_freq": 1}

    def ladder_cv(p, which):
        return float(np.mean(cv_score(train_df, lambda a, b: fit_ladder(a, p)[which].predict(b))))
    for which, key, grid in [
        ("linear", "linear_ladder", [{"alpha": a} for a in [1.0, 10.0, 100.0]]),
        ("rf", "rf_ladder", [{"n_estimators": 120, "max_depth": md, "min_samples_leaf": ml, "max_features": 0.4}
                             for md in [10, 14] for ml in [5, 20]]),
        ("gbm", "gbm_ladder", [dict(params["gbm_ladder"], num_leaves=nl, n_estimators=ne)
                               for nl in [15, 31] for ne in [500, 1000]]),
    ]:
        scores = []
        for g in grid:
            p = json.loads(json.dumps(params))
            p[key] = g
            scores.append(ladder_cv(p, which))
            print(f"  {which} {g}: CV MAE {scores[-1]:.3f}", flush=True)
        params[key] = grid[int(np.argmin(scores))]
    return params


# ----------------------------------------------------------------------------------------------
# experiments on September (--experiments)
# ----------------------------------------------------------------------------------------------
def experiments(df: pd.DataFrame, params: dict, parts=("variants", "sensitivity")) -> pd.DataFrame:
    """Compare variants of the best model on September (fit on train) and with the TimeSeriesSplit CV on
    the training period. Sensitivity runs also report October (refit ≤ Sep 30) - for the notes only,
    never for choosing the model."""
    base = params["best"]
    tr, va, te, tv = (split_frame(df, s) for s in ["train", "val", "test", "trainval"])
    va, te = va[va[TARGET].notna()], te[te[TARGET].notna()]
    rows = []

    def record(name, kind, p, extra=None):
        g = va[["delivery_date", "block"]].assign(y_true=va[TARGET].to_numpy(), p=p)
        r = {"experiment": name, "kind": kind, "val_mae": mae(va[TARGET], p), "val_smape": smape(va[TARGET], p),
             "val_bias": bias(va[TARGET], p)}
        ds = decision_scores(g, "p")
        r.update(val_rank_corr=ds["rank_corr"], val_shape_mae=ds["shape_mae"])
        r.update(extra or {})
        rows.append(r)
        print(f"  {name}: val MAE {r['val_mae']:.3f}", flush=True)
        return r

    def run(name, cfg, kind, with_test=False, with_cv=True):
        m = fit_best(tr, params, cfg, quantiles=False)
        p = m.predict(va)
        extra = {}
        if with_cv:
            s = cv_score(tr, lambda a, b: fit_best(a, params, dict(cfg, n_seeds=1), quantiles=False).predict(b))
            extra.update(cv_mae=float(np.mean(s)), cv_mae_last2=float(np.mean(s[-2:])))
        if with_test:
            pt = fit_best(tv, params, cfg, quantiles=False).predict(te)
            extra.update(test_mae=mae(te[TARGET], pt), test_smape=smape(te[TARGET], pt))
        return record(name, kind, p, extra)

    one = dict(base, n_seeds=1, linear_weight=0.0)
    if "variants" in parts:
        _variants(df, params, base, one, run, record, tr, va)
    if "sensitivity" in parts:
        _sensitivity(one, run)
    out = pd.DataFrame(rows)
    f = path("reports") / "experiments_price.csv"
    if f.exists() and set(parts) != {"variants", "sensitivity"}:
        old = pd.read_csv(f)
        out = pd.concat([old[~old["kind"].isin(set(out["kind"]))], out], ignore_index=True)
    out = out.sort_values("experiment", kind="stable").reset_index(drop=True)
    out.to_csv(f, index=False, float_format="%.4f")
    return out


def _variants(df, params, base, one, run, record, tr, va):
    """Model variants on September + CV (used to choose the configuration)."""
    lvl = dict(one, transform="level", half_life_years=None)
    run("A0 LightGBM on the level, equal weights", lvl, "target")
    run("A1 change vs same block of day D", dict(one, reference_col="price_lag_1d_same_block"), "target")
    run("A2 change vs day-D mean price", dict(one, reference_col="price_mean_day_D"), "target")
    run("A3 change vs day-D mean + 7-day block shape", dict(one, reference_col="ref_shape7"), "target")
    run("A4 asinh change vs day-D mean + 7-day shape", dict(one, reference_col="ref_shape7", transform="asinh"),
        "target")
    run("A5 asinh change vs same block of day D",
        dict(one, reference_col="price_lag_1d_same_block", transform="asinh"), "target")
    run("B0 no recency weights", dict(one, half_life_years=None), "recency")
    run("B1 recency half-life 0.5 y", dict(one, half_life_years=0.5), "recency")
    run("B2 recency half-life 1.5 y", dict(one, half_life_years=1.5), "recency")
    run("B3 recency half-life 2 y", dict(one, half_life_years=2.0), "recency")
    run("B4 train 2023+ only", dict(one, start_date="2023-01-01"), "recency", with_cv=False)  # early CV folds empty
    run("B5 train 2024+ only (ICON era)", dict(one, start_date="2024-01-01"), "recency", with_cv=False)
    run("C1 L1 loss", dict(one, objective="l1"), "loss")
    run("C2 Huber loss (delta 20 EUR)", dict(one, objective="huber", huber_alpha=20.0), "loss")
    run("D1 no derived features", dict(one, use_extras=False), "features")
    run("D2 with ICON eu_* columns (drop nothing)", dict(one, drop_features=[]), "features")
    run("D3 without Zurich weather", with_drop(one, ZH_WEATHER_COLS), "features")
    run("D4 without Zurich demand lags", with_drop(one, DEMAND_COLS), "features")
    run("E1 3 seeds", dict(one, n_seeds=3), "ensemble", with_cv=False)
    for lw in (0.2, 0.35, 0.5):
        run(f"E2 3 seeds + LEAR ridge {int(lw * 100)} %", dict(one, n_seeds=3, linear_weight=lw), "ensemble",
            with_cv=False)
    run("E3 3 seeds + ridge 35 %, ridge averaged over 3 windows (all, 2 y, 1 y)",
        dict(one, n_seeds=3, linear_weight=0.35, linear_windows_years=[None, 2, 1]), "ensemble", with_cv=False)
    run("E4 LEAR ridge alone", dict(one, n_seeds=0, linear_weight=1.0), "ensemble")
    run("E5 two-stage: day-mean change + within-day shape (2 LightGBMs)", dict(one, two_stage=True), "target")
    # refits during the month, with the final configuration
    days = sorted(va["delivery_date"].unique())
    st = fit_best(tr, params, dict(base, quantiles=[]), quantiles=False).predict(va)
    record("G0 final config, fit once on train", "walk-forward", st)
    for every, label in [(7, "weekly"), (1, "daily")]:
        cfg = dict(base, refit_every_days=every, quantiles=[])
        p = walk_forward_best(df, days, params, cfg)["pred_best"].to_numpy()
        record(f"G{1 if every == 7 else 2} final config, {label} walk-forward refit", "walk-forward", p)


def _sensitivity(one, run):
    """Sensitivity runs (single LightGBM, val + test) - for the notes only."""
    kw = dict(kind="sensitivity", with_test=True, with_cv=False)
    run("S0 sensitivity base (1 seed, all features)", one, **kw)
    run("S1 without European weather (all eu_*)", with_drop(one, EU_COLS + ["rad_de_x_trend", "wind_de_x_winter"]),
        **kw)
    run("S2 without neighbour prices", with_drop(one, NEIGHBOUR_COLS), **kw)
    run("S3 without gas / CO2 / FX", with_drop(one, FUEL_COLS), **kw)
    run("S4 ORACLE Zurich weather (observed, NOT achievable)", dict(one, weather="oracle"), **kw)
    run("S5 + German TSO forecasts unverified_de_* (NOT allowed in product)", dict(one, add_features=UNVERIFIED_DE),
        **kw)


# ----------------------------------------------------------------------------------------------
# notes
# ----------------------------------------------------------------------------------------------
def _md(df: pd.DataFrame, floatfmt: str = ".2f") -> str:
    return df.to_markdown(index=False, floatfmt=floatfmt)


def write_notes(met, tests, dec, imp, gimp, cov, worst, params, runtime_s):
    """reports/model_notes_price.md: fixed text (NOTES_*) + tables filled from this run."""
    allm = met[met["block"] == "all"]

    def table(split):
        t = allm[allm["split"] == split][["model", "mae", "rmse", "mape_or_smape", "bias", "mae_ci_low",
                                          "mae_ci_high"]].copy()
        naive = t.loc[t["model"] == "naive", "mae"].iloc[0]
        t["skill_vs_naive_%"] = 100 * (1 - t["mae"] / naive)
        return _md(t.rename(columns={"mape_or_smape": "smape_%"}))

    def dtable(split):
        t = dec[dec["split"] == split].drop(columns=["target", "split"])
        return _md(t, ".3f")

    exp_file = path("reports") / "experiments_price.csv"
    exp = pd.read_csv(exp_file) if exp_file.exists() else pd.DataFrame()
    blk = met[(met["split"] == "test") & (met["block"] != "all") & (met["model"].isin(["naive", "gbm", "best"]))]
    blk = blk.pivot(index="block", columns="model", values="mae").reset_index()
    txt = [NOTES_HEAD.format(best=json.dumps(params["best"], indent=None))]
    txt += ["## Validation (September 2026, models fit on data ≤ 31 Aug 2026)\n", table("val"), "\n",
            "Decision metrics (September):\n", dtable("val"), "\n"]
    txt += ["## Test (October 2026, refit on data ≤ 30 Sep 2026, evaluated once)\n", table("test"), "\n",
            "95 % CI = day-clustered bootstrap (1000 draws of whole days).\n\n", "Decision metrics (October):\n",
            dtable("test"), "\n", NOTES_DECISION_HELP, "\n"]
    txt += ["### Test MAE per block (EUR/MWh)\n", _md(blk), "\n"]
    if "rolling" in set(allm["split"]):
        txt += ["## Rolling-origin backtest (Oct 2025 – Aug 2026, monthly refit)\n", table("rolling"), "\n",
                dtable("rolling"), "\n"]
    if not tests.empty:
        txt += ["## Diebold–Mariano tests (daily mean absolute error; negative = best is better)\n",
                _md(tests[["split", "model_a", "model_b", "mean_diff", "dm_stat", "p_value", "n_days"]], ".3f"), "\n"]
    if not cov.empty:
        txt += ["## Prediction band (quantile LightGBM 10 % / 90 %)\n", _md(cov.reset_index(), ".3f"), "\n"]
    txt += ["## The 10 worst test blocks (largest |error| of the best model)\n", _md(worst, ".1f"), "\n",
            NOTES_WORST, "\n"]
    if not exp.empty:
        txt += ["## What was tried (September 2026 + 5-fold time-series CV on the training period)\n",
                "Single LightGBM with the final settings unless stated; `cv_mae` = mean over the 5 folds (the "
                "first folds are dominated by the 2021–2022 crisis), `cv_mae_last2` = the two most recent folds. "
                "Sensitivity rows also show October (reporting only, never used for choices).\n",
                _md(exp, ".3f"), "\n"]
    txt += [NOTES_CHOICE, "\n"]
    txt += ["## Driver importance\n", "Permutation importance on Sept + Oct 2026 (MAE increase in EUR/MWh when a "
            "column, or a whole group of columns, is shuffled).\n\n### Groups\n",
            _md(gimp[["feature", "mae_increase", "std"]], ".3f"), "\n\n### Top 20 single columns\n",
            _md(imp.head(20)[["feature", "mae_increase", "std"]], ".3f"), "\n"]
    txt += [NOTES_DRIVERS, "\n", NOTES_LIMITS, "\n", f"_`main()` runtime of this run: {runtime_s / 60:.1f} min._\n"]
    (path("reports") / "model_notes_price.md").write_text("\n".join(txt), encoding="utf-8")


NOTES_HEAD = """# Price model – notes (agent M2)

**Target:** `price_eur_mwh` = mean Swiss day-ahead price (EPEX CH) of each 4-hour block of the delivery day,
EUR/MWh. Prices can be near zero or negative, so the percentage error is the symmetric MAPE (sMAPE), not MAPE.
**Forecast time:** day D 10:00, for the six blocks of D+1. All CH and neighbour prices of day D are known (the
auction for D ran on D−1); no price of D+1 is known.

**Best model in one sentence:** we start from a price we already know – *the mean CH price of day D plus the
usual difference of this block from the day mean over the last 7 days* (`ref_shape7`) – and LightGBM learns how
much tomorrow's block will differ from it; recent days count more (weight halves every year), three LightGBM
seeds are averaged and blended 65 / 35 with a LEAR-style ridge regression that learns the same change, and the
model is refit every 7 days during the month with all prices known at that time. A quantile LightGBM (10/50/90 %)
gives a band, widened by a factor 1.4 chosen on September so that ~80 % of actual prices fall inside it.

Settings: `{best}`

(`drop_features: "EU_ICON"` = the ICON-based European weather columns `eu_*_safe` are left out, see "What was tried".)
"""

NOTES_DECISION_HELP = """`rank_corr` = Spearman correlation of the 6 block prices inside a day (1 = perfect order),
`hit_cheapest` / `hit_dearest` = share of days where the model picks the right cheapest / most expensive block
(this is what the battery plan needs), `shape_mae` = MAE of (block − day mean), `daymean_mae` = MAE of the daily
mean price (the level, used by the limit bids)."""

NOTES_WORST = """**What happened (after-the-fact look at the data, incl. the German price of the delivery day):**

1. **Thu 29 Oct, 16–20 – the biggest miss (−131 EUR).** A cold, almost wind-still evening in Germany (JMA wind
   index ≈ 1, German price of that block ≈ 470 EUR, one CH hour at ≈ 600 EUR). The model forecast 319 (same block
   on day D: 329, naive: 246); a block price of 451 EUR is far above anything since 2023 (the 2024 – Sep 2026
   maximum was 282 EUR), so the trees had no similar case to learn from. The 10–90 % band (270–364) missed it too.
2. **Sat 10 Oct, 12–16 (−46).** The model expected the usual sunny-weekend midday dip (139). Germany did crash to
   ≈ 0 EUR (windy and sunny), but Switzerland stayed at 185 – CH decoupled from DE (most likely the
   interconnectors were full; we have no capacity data). The naive forecast (60) was even worse.
3. **Wed 28 Oct, 16–20 (−43)** and **Wed 28 Oct, 12–16 (−30).** The start of the same cold, low-wind spell:
   the whole day rose by ≈ 30 EUR vs day D and the evening ramp was steeper than ever before.
4. **Thu 1 Oct, 08–12 / 12–16 / 16–20 (−29 to −35).** First day of the test month: the day-mean price rose by
   ≈ 21 EUR vs 30 Sep (180 → 201) without a matching move in gas; a model that learns changes vs day D
   under-shoots such sudden level jumps.
5. **Thu 8 Oct, 12–16 (−33).** Windy in Germany (German price ≈ 107), the model expected a midday dip; Switzerland
   stayed at ≈ 214 – again CH decoupled from DE.
6. **Sun 11 Oct, 12–16 (+31, the only "too high" miss in the top 6).** A real sunny-Sunday solar dip (89 EUR;
   Germany 34). The model went down from 185 on Saturday to 120, but not far enough.
7. **Mon 26 Oct, 08–12 (+29).** Windy Monday morning after the autumn clock change (German price ≈ 99); the
   model expected a normal Monday morning ramp.

**Pattern:** 8 of the 10 worst blocks are forecasts that were *too low*, all in the day-time and evening blocks
(08–20) of a month in which prices rose by ≈ 30 % (gas TTF from ≈ 72 to ≈ 97 EUR/MWh). The model is anchored on day D, so it
follows a trend with a lag of about one day; the mean October bias is −6.5 EUR/MWh. The two "too high" misses are
weekend/Monday blocks with much more wind or sun than usual. There were no negative prices in October 2026.
"""

NOTES_CHOICE = """## Why this model won
* **Learn the change, not the level.** LightGBM on the price level (A0) has a CV MAE of ≈ 41 EUR because trees
  cannot predict a price level they have never seen (the 2021–2022 crisis); learning the change vs a known
  price cuts that to ≈ 12.6. Of the references, `ref_shape7` (day-D mean + 7-day block shape, A3) was best on
  September and on the CV. The asinh-scaled change (A4/A5) and a two-stage day-mean + shape model (E5) were worse.
* **Recency weights.** A half-life of 1 year beat no weights and 0.5 / 1.5 / 2 years on September (the CV is
  flat at 12.5–13.0). Training only on 2023+ or 2024+ (B4/B5) was worse: the model needs the long history.
* **L2 loss.** L1 and Huber (C1/C2) were not better on September or CV.
* **Features.** Leaving out the ICON European weather columns (`eu_*_safe`, which only exist from 2024) helped
  on September (13.9 vs 14.2) *and* on the CV (12.6 vs 12.8): with only 2.5 years of data the tree splits on them
  are noisy, while the JMA columns (`eu_*_jma_safe`, full history) carry the German wind / temperature signal.
  Derived columns (`PriceExtras`, e.g. day-D shape, weekday of day D, gas cost vs price, radiation × weekend)
  helped (D1: 15.1 without them).
* **Ensemble.** The LEAR-style ridge regression alone (E4) is close to a single LightGBM on September (14.1) but
  much worse on the CV (16.7); blended 35 % it lowers the September MAE from 14.0 to 13.7 and lowers the bias by about 30 % (from −3.8 to −2.6).
  Averaging the ridge over three calibration windows (E3) did not help.
* **Weekly walk-forward refit** (G1) beat a single fit (G0, 13.62 vs 13.67) and reduced the bias from −2.6 to −1.4
  EUR; a daily refit (G2) was not better.
* **Hyper-parameters.** An optuna search (15 trials, score = MAE of the two most recent CV folds,
  `reports/tuning_price.csv`) found settings with a slightly better CV score, but all of them were worse on
  September (14.6–16.9 vs 14.3), so the default LightGBM settings were kept. Differences between configurations
  are often within the seed noise (≈ ±0.3 EUR on September with one seed), which is why we average 3 seeds.
"""

NOTES_DRIVERS = """## Top-10 drivers
Single columns, permutation importance on Sep + Oct 2026 (see the table above). Shuffling a column that is part
of the reference (`price_mean_day_D`, `price_block_vs_day_ratio_last_7d`) also breaks the reference itself, so
these two are inflated by construction.

1. **`price_mean_day_D`** – today's average CH price is the anchor: tomorrow's prices are mostly today's level plus a
   change.
2. **`radiation_wm2`** – the Zurich solar-radiation forecast for the block tells the model how deep the midday solar
   dip will be (more sun = cheaper 12–16 block).
3. **`price_block_vs_day_ratio_last_7d`** – the typical shape of the day over the last week (night cheap, evening
   expensive) is the second half of the reference.
4. **`block`** – the time of day itself: the evening block 16–20 and night block 20–24 are the most expensive,
   midday the cheapest.
5. **`weekday`** – Saturdays, Sundays and Mondays differ from day D in a predictable way (e.g. Sunday → Monday
   prices rise, Friday → Saturday prices fall).
6. **`is_weekend`** – weekend demand is lower, so weekend prices (especially midday) fall below the weekday level.
7. **`clean_gas_cost`** – the cost of a gas power plant (gas + CO₂) sets the price in many hours; when it is far above
   or below today's price, prices move towards it.
8. **`price_lag_1d_same_block`** – the price of the same block today adds detail the 7-day shape misses
   (e.g. a new evening peak).
9. **`eu_radiation_wm2_de_mean_safe`** – the German solar forecast (used through `rad_de_x_trend`, radiation × years
   since 2019): German solar build-out pushes the midday price down more every year.
10. **`price_de_mean_day_D`** – the German price of day D: Switzerland mostly imports the German price level, the
    CH–DE spread changes only slowly.

Group view: the CH price of day D (lags + shape), the calendar and the Zurich weather forecast are by far the most
important groups; the JMA European weather forecasts (German wind, French/German temperature), neighbour prices
and gas/CO₂ follow; Swiss reservoir fill and the Swiss system data of D−1 add almost nothing on these two months.
"""

NOTES_LIMITS = """## Sensitivity runs (single LightGBM, for the notes only – not used for choosing the model)
See rows S0–S5 in "What was tried" (val = September, test = October, fit on data ≤ Aug 31 / ≤ Sep 30):
* Without any European weather forecast (S1): September MAE +1.7, October +0.7 EUR – the JMA German wind and
  temperature forecasts are worth keeping.
* Without neighbour prices (S2): +0.5 / +1.3 EUR.
* Without gas / CO₂ / FX (S3): +1.2 / +0.1 EUR (the CH price of day D already contains most of the fuel level).
* ORACLE Zurich weather (S4, observed weather of the delivery day, not achievable): *worse* (15.0 vs 13.9 on
  September). Training on observed weather before 2024 and on forecasts after makes the weather columns
  inconsistent; perfect Zurich weather is not what limits the price forecast.
* With the German TSO day-ahead wind/solar/load forecasts (S5, `unverified_de_*` – NOT allowed in the product,
  because they may be published after 10:00): September −0.4 EUR, October +0.6 EUR. Their value is small and not
  stable; the JMA wind forecast already carries most of the information.

## Limitations
* **Trends and spikes.** The model is anchored on day D, so in a month with a strong upward trend (October 2026:
  +30 %) it is too low on average (bias −6.5 EUR/MWh) and it misses scarcity spikes (29 Oct evening, 451 EUR).
  The 10–90 % band covers 87 % of October but its misses are almost all on the upper side.
* **One validation month.** September has only 30 days; many choices differ by less than the seed noise. The CV and
  the rolling backtest (Oct 2025 – Aug 2026) support the main choices, but the rolling backtest shows the best
  model is NOT significantly better than the plain LightGBM there (DM p ≈ 0.3) – the big gain vs gbm in
  September/October comes from months where the price level moves.
* **Weather history.** Zurich weather is observed before 2024 and forecast after; ICON European weather exists only
  from 2024 (left out), JMA has no radiation. Better European solar forecasts with a long history would help.
* **No cross-border capacity data.** Several misses are days where CH decoupled from Germany (possibly full interconnectors - this is a guess);
  we have no capacity or flow forecasts.
* **The saved model file is one fit.** `models/price_best.joblib` is the fit on data up to 30 Sep. The scored
  October forecast (`pred_best`) comes from weekly refits, so the file reproduces only the first 7 days exactly.
  Used alone for the whole of October the single fit scores an MAE of 12.35 EUR/MWh (checked by the independent
  reviewer); the battery result changes by about CHF 250.
* **One derived input still uses ICON data:** `rad_de_x_trend` (German radiation forecast x solar build-out trend)
  is kept although the raw ICON European columns are left out.
* **October sensitivity runs:** the "without X" runs were scored on October too, after the settings were frozen.
  The code does not enforce this order, so we state it here: no choice was made with October numbers.
* **Importance is from the fixed models** (fit ≤ Aug 31 / ≤ Sep 30), not from the weekly walk-forward refits that
  produce `pred_best`; the drivers are the same, the numbers slightly differ.
"""


# ----------------------------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tune", action="store_true", help="redo the hyper-parameter search (slow)")
    ap.add_argument("--experiments", action="store_true", help="redo the September variant comparison (slow)")
    ap.add_argument("--skip-rolling", action="store_true", help="skip the rolling backtest (faster, for debugging)")
    args = ap.parse_args(argv)
    t_start = time.time()
    df = load_features()
    params = load_params()
    seed = params["seed"] = load_config()["random_seed"]
    models_dir, rep, fig = path("models"), path("reports"), path("figures")
    for p in (models_dir, rep, fig):
        p.mkdir(parents=True, exist_ok=True)

    if args.tune:
        print("tuning ...", flush=True)
        params = tune(df, params)
    with open(models_dir / PARAMS_FILE, "w") as fh:
        json.dump(params, fh, indent=2)
    if args.experiments:
        print("experiments on September ...", flush=True)
        experiments(df, params)

    p_dates = {k: pd.Timestamp(v) for k, v in load_config()["periods"].items()}
    cfg = params["best"]
    va, te = split_frame(df, "val"), split_frame(df, "test")
    va, te = va[va[TARGET].notna()], te[te[TARGET].notna()]

    print("fit on train (for validation) and on train + validation (for test) ...", flush=True)
    (lad_tr, best_tr), (lad_tv, best_tv) = Parallel(n_jobs=2)(
        delayed(train)(df, p_dates[k], params) for k in ["train_end", "val_end"])
    pv = predict_frame(va, lad_tr, best_tr, "val")
    pt = predict_frame(te, lad_tv, best_tv, "test")
    if cfg.get("walk_forward"):
        # best model refit during the month (only prices known at forecast time); the ladder stays static
        print("walk-forward refits for September and October ...", flush=True)
        for frame, rows in [(pv, va), (pt, te)]:
            wf = walk_forward_best(df, sorted(rows["delivery_date"].unique()), params, quantiles=True)
            wf = frame[["delivery_date", "block"]].merge(wf, on=["delivery_date", "block"], how="left")
            for c in ["pred_best", "pred_q10", "pred_q50", "pred_q90"]:
                if c in wf.columns:
                    frame[c] = wf[c].to_numpy()

    parts = [pv, pt]
    if not args.skip_rolling:
        print("rolling backtest ...", flush=True)
        parts.insert(0, rolling_backtest(df, params))
    pred = pd.concat(parts, ignore_index=True)
    pred["delivery_date"] = pd.to_datetime(pred["delivery_date"])
    pred.to_parquet(rep / "predictions_price.parquet", index=False)

    met, tests = evaluate(pred, seed)
    met.to_csv(rep / "metrics_price.csv", index=False)
    tests.to_csv(rep / "model_tests_price.csv", index=False)
    dec = decision_table(pred)
    dec.to_csv(rep / "decision_metrics_price.csv", index=False)
    cov = quantile_coverage(pred)
    worst = worst_blocks(pred, df)
    worst.to_csv(rep / "worst_blocks_price.csv", index=False)

    joblib.dump(best_tv, models_dir / "price_best.joblib", compress=3)
    joblib.dump(lad_tv, models_dir / "price_ladder.joblib", compress=3)

    print("importance ...", flush=True)
    imp, gimp = importance(df, best_tr, best_tv, seed)
    imp.to_csv(rep / "importance_price.csv", index=False)
    gimp.to_csv(rep / "importance_groups_price.csv", index=False)

    tp = pred[pred["split"] == "test"]
    plot_forecast_vs_actual(tp, fig / "price_test_forecast_vs_actual.png",
                            "Swiss day-ahead price, October 2026 (test): forecast vs actual", "EUR/MWh",
                            band=("pred_q10", "pred_q90"))
    plot_error_by_block(met, fig / "price_error_by_block.png", "test",
                        "Price: MAE per block, October 2026 (test)", "EUR/MWh")
    plot_importance(imp, fig / "price_permutation_importance.png",
                    "Price (best model): permutation importance, Sep + Oct 2026", "EUR/MWh")
    plot_model_ladder(met, fig / "price_model_ladder.png", "Price: MAE per model and split", "EUR/MWh")

    runtime = time.time() - t_start
    write_notes(met, tests, dec, imp, gimp, cov, worst, params, runtime)
    allm = met[met["block"] == "all"].pivot(index="model", columns="split", values="mae")
    print(allm.round(3).to_string())
    print(dec.round(3).to_string())
    print(tests.round(4).to_string())
    print(f"done in {runtime / 60:.1f} min")


if __name__ == "__main__":
    main()
