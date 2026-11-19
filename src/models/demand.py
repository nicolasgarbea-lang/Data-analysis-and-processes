"""Day-ahead demand model for Zurich (target `demand_mw`, mean MW per 4-hour block).

Run everything (frozen settings from models/demand_best_params.json, < 10 min):
    .venv/bin/python -m src.models.demand
Options:
    --tune          redo the hyper-parameter search (slow) and rewrite the params file
    --experiments   redo the September comparison of variants + sensitivity runs (slow)

How the forecast works (the "best" model)
* Reference = demand of the same block two days before delivery (the last day we know, D−1).
* LightGBM learns log(demand / reference), i.e. "how much higher or lower than the day before
  yesterday" - trees cannot extrapolate a level, but they predict such ratios well.
* Several LightGBM seeds are averaged and blended with a small ridge regression (same target).
* Optionally the model is refit every day ("walk-forward") with all demand known at forecast time.
* Quantile LightGBM models (10/50/90 %) give a prediction band.

Ladder models (plain versions, for comparison): naive = same block 7 days earlier, linear = ridge
on the demand level, rf = random forest on the level, gbm = LightGBM on the level.
"""
from __future__ import annotations

import argparse
import json
import time

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.config import load_config, path
from src.features import feature_sets as fs
from src.models.common import (
    ColumnModel, ColumnSelect, ForecastModel, LinearDesign, apply_weather_map, dm_test, forbidden_columns,
    load_features, mae, make_target, mape, metrics_long, permutation_importance_df, plot_error_by_block,
    plot_forecast_vs_actual, plot_importance, plot_model_ladder, rmse, bias, split_frame,
)

TARGET = fs.TARGET_DEMAND
NAIVE_COL = "demand_lag_7d_same_block"
REF_COL = "demand_lag_2d_same_block"
TARGET_LAG_DAYS = 2          # forecasting delivery day T: the latest known demand row is T−2
LADDER = ["naive", "linear", "rf", "gbm"]
MODELS = LADDER + ["best"]
PARAMS_FILE = "demand_best_params.json"

# trending inputs the LINEAR models leave out (a straight line through them explodes in early years)
LINEAR_DROP = ["ev_count_city", "charging_kw_zh", "stations_zh_count", "year_frac", "covid_stringency"]
LINEAR_ONEHOT = ["block", "weekday", "month", "school_holiday_type"]
LINEAR_CATEGORICAL = LINEAR_ONEHOT + ["daytype", "lag2_daytype"]
LINEAR_INTERACTIONS = [
    ("block", "cat:daytype"), ("block", "cat:lag2_daytype"), ("daytype", "cat:lag2_daytype"),
    ("block", "cat:month"),
    ("block", "temp_c"), ("block", "heating_degree"), ("block", "cooling_degree"),
    ("block", "radiation_wm2"), ("block", "cloud_pct"), ("block", "sunshine_min"), ("block", "daylight_hours"),
    ("block", "demand_lag_2d_same_block"), ("block", "demand_lag_7d_same_block"),
    ("block", "demand_mean_same_block_same_weekday_4w"), ("block", "demand_day_mean_lag_2d"),
    ("daytype", "demand_lag_2d_same_block"), ("daytype", "demand_lag_7d_same_block"),
    ("block", "is_school_holiday"), ("block", "is_bridge_day"), ("block", "is_christmas_period"),
]

# feature groups (for group importance and the sensitivity runs)
EV_COLS = ["ev_count_city", "charging_kw_zh", "stations_zh_count"]
EVENT_COLS = ["event_size", "n_events", "home_game", "kickoff_hour_local"]
SOLAR_COLS = ["solar_ch_mw_lag_2d_same_block", "solar_ch_day_mean_lag_2d"]
HOLIDAY_COLS = ["is_holiday", "is_half_holiday", "is_bridge_day", "is_school_holiday", "school_holiday_type",
                "is_christmas_period", "days_to_next_holiday", "days_since_last_holiday", "is_holiday_prev_day",
                "is_holiday_next_day", "lag2d_was_holiday", "lag7d_was_holiday", "is_working_day"]
WEATHER_COLS = fs.WEATHER_FEATURES + fs.PAST_WEATHER_FEATURES
D1_DEMAND_COLS = ["demand_lag_2d_same_block", *[f"demand_dm1_block_{j}" for j in range(6)],
                  "demand_day_mean_lag_2d", "demand_day_max_lag_2d", "demand_day_min_lag_2d",
                  "demand_mean_last_7d", "demand_mean_last_28d", "demand_trend_7d"]

DEFAULT_PARAMS = {
    "seed": 42,
    "linear_ladder": {"alpha": 10.0},
    "rf_ladder": {"n_estimators": 150, "max_depth": 14, "min_samples_leaf": 5, "max_features": 0.4},
    "gbm_ladder": {"learning_rate": 0.03, "n_estimators": 1500, "num_leaves": 31, "min_child_samples": 20,
                   "subsample": 0.8, "subsample_freq": 1, "colsample_bytree": 0.7, "reg_lambda": 0.0},
    "best": {
        "transform": "logratio",
        "reference_col": REF_COL,
        "weather": "hybrid",               # hybrid | jma | both | oracle
        "extra_features": ["temp_vs_lag2", "rad_vs_lag2"],
        "drop_features": [],
        "gbm_params": {"learning_rate": 0.03, "n_estimators": 1500, "num_leaves": 31, "min_child_samples": 20,
                       "subsample": 0.8, "subsample_freq": 1, "colsample_bytree": 0.7, "reg_lambda": 0.0},
        "n_seeds": 5,
        "objective": "l2",
        "linear_weight": 0.15,
        "linear_alpha": 10.0,
        "half_life_years": None,
        "forecast_row_weight": 1.0,
        "covid_weight": 1.0,
        "walk_forward": False,
        "quantiles": [0.1, 0.5, 0.9],
        "quantile_params": {"learning_rate": 0.03, "n_estimators": 600, "num_leaves": 15,
                            "min_child_samples": 40, "subsample": 0.8, "subsample_freq": 1,
                            "colsample_bytree": 0.7},
    },
}


# ----------------------------------------------------------------------------------------------
# derived features (part of the saved model, so the app gets them automatically)
# ----------------------------------------------------------------------------------------------
class DemandExtras:
    """Adds a few derived columns to rows of features.parquet.

    daytype       0 Monday, 1 Tue–Thu, 4 Friday, 5 Saturday, 6 Sunday or public holiday
    lag2_daytype  type of the reference day (T−2): 0 normal working day, 1 weekend, 2 holiday
    temp_vs_lag2  forecast temperature of the block − observed temperature of the same block on T−2
    rad_vs_lag2   the same for solar radiation (W/m²)"""

    input_columns = ["is_holiday", "weekday", "lag2d_was_holiday", "lag2d_is_weekend", "temp_c",
                     "temp_obs_same_block_lag_2d", "radiation_wm2", "radiation_obs_same_block_lag_2d"]
    output_columns = ["daytype", "lag2_daytype", "temp_vs_lag2", "rad_vs_lag2"]

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        d = df.copy()
        d["daytype"] = np.select([d["is_holiday"] == 1, d["weekday"] == 6, d["weekday"] == 5,
                                  d["weekday"] == 0, d["weekday"] == 4], [6, 6, 5, 0, 4], 1)
        d["lag2_daytype"] = np.select([d["lag2d_was_holiday"] == 1, d["lag2d_is_weekend"] == 1], [2, 1], 0)
        d["temp_vs_lag2"] = d["temp_c"] - d["temp_obs_same_block_lag_2d"]
        d["rad_vs_lag2"] = d["radiation_wm2"] - d["radiation_obs_same_block_lag_2d"]
        return d


# ----------------------------------------------------------------------------------------------
# settings and feature lists
# ----------------------------------------------------------------------------------------------
def load_params() -> dict:
    """Frozen settings from models/demand_best_params.json (defaults if the file does not exist)."""
    f = path("models") / PARAMS_FILE
    if f.exists():
        with open(f) as fh:
            return json.load(fh)
    return json.loads(json.dumps(DEFAULT_PARAMS))


def weather_map_for(variant: str) -> dict:
    """Weather column map for a variant: hybrid (none), jma, oracle; "both" adds columns instead."""
    return {"jma": fs.JMA_WEATHER_MAP, "oracle": fs.ORACLE_WEATHER_MAP}.get(variant, {})


def best_features(cfg: dict) -> list[str]:
    """Input columns of the LightGBM part of the best model."""
    feats = list(fs.DEMAND_FEATURES) + list(cfg.get("extra_features", []))
    if cfg.get("weather") == "both":
        feats += [fs.JMA_WEATHER_MAP[c] for c in fs.DEMAND_FEATURES if c in fs.JMA_WEATHER_MAP]
    drop = set(cfg.get("drop_features", []))
    return [c for c in dict.fromkeys(feats) if c not in drop]


def linear_features(drop=()) -> tuple[list[str], list[str]]:
    """(all input columns, numeric columns) for the ridge models."""
    drop = set(drop) | set(LINEAR_DROP)
    cols = [c for c in fs.DEMAND_FEATURES if c not in drop] + ["daytype", "lag2_daytype", "temp_vs_lag2"]
    numeric = [c for c in cols if c not in LINEAR_CATEGORICAL]
    return cols, numeric


def sample_weights(d: pd.DataFrame, cfg: dict) -> np.ndarray:
    """Row weights: optional recency decay, lower weight for the COVID lockdown (Mar–Jun 2020),
    higher weight for rows with real weather forecasts."""
    w = np.ones(len(d))
    hl = cfg.get("half_life_years")
    if hl:
        age = (d["delivery_date"].max() - d["delivery_date"]).dt.days.to_numpy() / 365.25
        w *= 0.5 ** (age / hl)
    covid = ((d["delivery_date"] >= "2020-03-01") & (d["delivery_date"] <= "2020-06-30")).to_numpy()
    w[covid] *= cfg.get("covid_weight", 1.0)
    w[d["weather_is_forecast"].to_numpy() == 1] *= cfg.get("forecast_row_weight", 1.0)
    return w


# ----------------------------------------------------------------------------------------------
# model builders
# ----------------------------------------------------------------------------------------------
def make_lgbm(params: dict, seed: int, objective: str = "l2", alpha: float | None = None):
    p = dict(params)
    p.setdefault("subsample_freq", 1)
    kw = {"objective": objective, "random_state": seed, "verbose": -1, "n_jobs": 4, "deterministic": True,
          "force_row_wise": True}
    if alpha is not None:
        kw["alpha"] = alpha
    return lgb.LGBMRegressor(**p, **kw)


def make_linear(alpha: float, drop=()) -> Pipeline:
    """Ridge regression on a design with block × weekday-type dummies and per-block slopes."""
    _, numeric = linear_features(drop)
    inter = [(a, b) for a, b in LINEAR_INTERACTIONS if b.startswith("cat:") or b in numeric]
    return Pipeline([("design", LinearDesign(numeric=numeric, onehot=LINEAR_ONEHOT, interactions=inter)),
                     ("scale", StandardScaler()), ("ridge", Ridge(alpha=alpha))])


def fit_ladder(train: pd.DataFrame, params: dict) -> dict:
    """Fit the plain ladder models (naive, linear, rf, gbm), all on the demand LEVEL."""
    seed = params["seed"]
    pre = DemandExtras()
    d = pre.transform(train)
    y = d[TARGET].to_numpy()
    feats = list(fs.DEMAND_FEATURES)
    lin_cols, _ = linear_features()

    lin = make_linear(params["linear_ladder"]["alpha"]).fit(d[lin_cols], y)
    rf = Pipeline([("select", ColumnSelect(feats)), ("impute", SimpleImputer(strategy="median")),
                   ("rf", RandomForestRegressor(random_state=seed, n_jobs=-1, **params["rf_ladder"]))])
    rf.fit(d, y)
    gbm = Pipeline([("select", ColumnSelect(feats)), ("gbm", make_lgbm(params["gbm_ladder"], seed))])
    gbm.fit(d, y)
    info = {"trained_until": str(train["delivery_date"].max().date())}
    return {
        "naive": ColumnModel(NAIVE_COL),
        "linear": ForecastModel(TARGET, lin_cols, [lin], preprocess=pre, info=info),
        "rf": ForecastModel(TARGET, feats, [rf], preprocess=pre, info=info),
        "gbm": ForecastModel(TARGET, feats, [gbm], preprocess=pre, info=info),
    }


def fit_best(train: pd.DataFrame, params: dict, cfg: dict | None = None, quantiles: bool = True) -> ForecastModel:
    """Fit the best configuration (`params["best"]`, or `cfg` if given) on `train`."""
    cfg = cfg or params["best"]
    seed = params["seed"]
    wmap = weather_map_for(cfg.get("weather", "hybrid"))
    pre = DemandExtras()
    d = pre.transform(apply_weather_map(train, wmap))
    ref_col = cfg.get("reference_col", REF_COL)
    transform = cfg.get("transform", "logratio")
    ref = d[ref_col].to_numpy(dtype=float) if transform != "level" else None
    z = make_target(d[TARGET].to_numpy(), ref, transform)
    w = sample_weights(d, cfg)
    feats = best_features(cfg)

    estimators, weights = [], []
    n_seeds = int(cfg.get("n_seeds", 1))
    lw = float(cfg.get("linear_weight", 0.0))
    for k in range(n_seeds):
        m = Pipeline([("select", ColumnSelect(feats)),
                      ("gbm", make_lgbm(cfg["gbm_params"], seed + k, cfg.get("objective", "l2")))])
        m.fit(d, z, gbm__sample_weight=w)
        estimators.append(m)
        weights.append((1 - lw) / n_seeds)
    all_cols = list(feats)
    if lw > 0:
        drop = cfg.get("drop_features", [])
        lin_cols, _ = linear_features(drop)
        lin = make_linear(cfg.get("linear_alpha", 10.0), drop)
        lin.fit(d[lin_cols], z, ridge__sample_weight=w)
        estimators.append(lin)
        weights.append(lw)
        all_cols += lin_cols
    qmodels = {}
    if quantiles and cfg.get("quantiles"):
        for q in cfg["quantiles"]:
            m = Pipeline([("select", ColumnSelect(feats)),
                          ("gbm", make_lgbm(cfg["quantile_params"], seed, "quantile", alpha=q))])
            m.fit(d, z, gbm__sample_weight=w)
            qmodels[q] = m
    return ForecastModel(
        TARGET, list(dict.fromkeys(all_cols)), estimators, weights=weights, transforms=[transform] * len(estimators),
        reference_col=ref_col if transform != "level" else None, weather_map=wmap, quantiles=qmodels,
        quantile_transform=transform, preprocess=pre,
        info={"trained_until": str(train["delivery_date"].max().date()), "config": cfg},
    )


# ----------------------------------------------------------------------------------------------
# training / prediction schemes
# ----------------------------------------------------------------------------------------------
def train(df: pd.DataFrame, until, params: dict, quantiles: bool = True) -> tuple[dict, ForecastModel]:
    """Fit ladder + best on all rows with delivery_date ≤ `until`. Returns (ladder dict, best)."""
    tr = df[df["delivery_date"] <= pd.Timestamp(until)]
    return fit_ladder(tr, params), fit_best(tr, params, quantiles=quantiles)


def predict_frame(rows: pd.DataFrame, ladder: dict, best: ForecastModel | None, split: str) -> pd.DataFrame:
    """Predictions of all models for `rows` in the format of reports/predictions_demand.parquet."""
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
    """Refit the best model every day: for delivery day T use only rows ≤ T−2 (demand known at the
    forecast time on day T−1). Returns a frame with pred_best (and quantiles if asked)."""
    parts = []
    for day in days:
        day = pd.Timestamp(day)
        tr = df[df["delivery_date"] <= day - pd.Timedelta(days=TARGET_LAG_DAYS)]
        rows = df[df["delivery_date"] == day]
        m = fit_best(tr, params, cfg, quantiles=quantiles)
        p = rows[["delivery_date", "block"]].copy()
        p["pred_best"] = m.predict(rows)
        if quantiles and m.quantiles:
            p = pd.concat([p, m.predict_quantiles(rows).set_axis(p.index)], axis=1)
        parts.append(p)
    return pd.concat(parts)


def rolling_backtest(df: pd.DataFrame, params: dict, start="2025-10-01", end="2026-08-31") -> pd.DataFrame:
    """Frozen configuration refit at the start of each month on all rows known then (≤ start − 2 days),
    predicting that month. Split label "rolling"."""
    parts = []
    for m0 in pd.date_range(start, end, freq="MS"):
        m1 = m0 + pd.offsets.MonthEnd(0)
        tr = df[df["delivery_date"] <= m0 - pd.Timedelta(days=TARGET_LAG_DAYS)]
        rows = df[(df["delivery_date"] >= m0) & (df["delivery_date"] <= min(m1, pd.Timestamp(end)))]
        ladder = fit_ladder(tr, params)
        best = fit_best(tr, params, quantiles=True)
        parts.append(predict_frame(rows, ladder, best, "rolling"))
        print(f"  rolling {m0:%Y-%m}: best MAE {mae(parts[-1]['y_true'], parts[-1]['pred_best']):.2f}", flush=True)
    return pd.concat(parts, ignore_index=True)


# ----------------------------------------------------------------------------------------------
# evaluation
# ----------------------------------------------------------------------------------------------
def evaluate(pred: pd.DataFrame, seed: int = 42) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Metrics (long format) and Diebold–Mariano tests from a predictions frame."""
    met = metrics_long(pred, "demand", MODELS, "mape", ci_splits=("val", "test"), seed=seed)
    tests = []
    for split in ["val", "test", "rolling"]:
        g = pred[pred["split"] == split]
        if g.empty:
            continue
        for other in ["naive", "gbm"]:
            r = dm_test(g["y_true"], g["pred_best"], g[f"pred_{other}"], g["delivery_date"])
            tests.append({"target": "demand", "split": split, "model_a": "best", "model_b": other,
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
        "mean_width_mw": g.apply(lambda x: (x.pred_q90 - x.pred_q10).mean()),
    }).round(3)


def group_importance_columns(model: ForecastModel) -> dict:
    """Driver groups for the group permutation importance (raw columns of features.parquet)."""
    cols = set(model.input_columns)
    wmap = model.weather_map
    weather = [wmap.get(c, c) for c in WEATHER_COLS]
    if model.info.get("config", {}).get("weather") == "both":
        weather += [fs.JMA_WEATHER_MAP[c] for c in WEATHER_COLS if c in fs.JMA_WEATHER_MAP]
    groups = {
        "past demand (all lags)": [c for c in fs.DEMAND_LAG_FEATURES],
        "weather (forecast + past observed)": weather,
        "holidays and school holidays": HOLIDAY_COLS,
        "weekday / weekend": ["weekday", "is_weekend", "lag2d_is_weekend"],
        "season (month, day of year, daylight)": ["month", "day_of_year", "week_of_year", "sin_doy", "cos_doy",
                                                  "daylight_hours", "year_frac"],
        "EVs and charging": EV_COLS,
        "Swiss solar (lagged)": SOLAR_COLS,
        "events and football": EVENT_COLS,
        "COVID stringency": ["covid_stringency"],
    }
    return {k: [c for c in v if c in cols] for k, v in groups.items() if any(c in cols for c in v)}


def importance(df: pd.DataFrame, m_val: ForecastModel, m_test: ForecastModel, seed: int):
    """Permutation importance of the best model on September (model fit on train) + October (model
    fit on train+val): single columns and driver groups."""
    rows = pd.concat([split_frame(df, "val"), split_frame(df, "test")])
    is_val = (rows["delivery_date"] <= load_config()["periods"]["val_end"]).to_numpy()

    def predict(d):
        out = np.empty(len(d))
        out[is_val] = m_val.predict(d[is_val])
        out[~is_val] = m_test.predict(d[~is_val])
        return out

    y = rows[TARGET].to_numpy()
    single = permutation_importance_df(predict, rows, y, m_test.input_columns, n_repeats=5, seed=seed)
    groups = permutation_importance_df(predict, rows, y, group_importance_columns(m_test), n_repeats=5, seed=seed)
    return single, groups


# ----------------------------------------------------------------------------------------------
# hyper-parameter search (--tune)
# ----------------------------------------------------------------------------------------------
def _cv_days(train: pd.DataFrame, n_splits: int = 5):
    from sklearn.model_selection import TimeSeriesSplit
    days = np.array(sorted(train["delivery_date"].unique()))
    return [(days[a], days[b]) for a, b in TimeSeriesSplit(n_splits).split(days)]


def cv_score(train: pd.DataFrame, fit_predict, n_splits: int = 5) -> list[float]:
    """MAE per TimeSeriesSplit fold (folds made of whole days). `fit_predict(tr, te) -> preds`."""
    out = []
    for a, b in _cv_days(train, n_splits):
        tr, te = train[train["delivery_date"].isin(a)], train[train["delivery_date"].isin(b)]
        out.append(mae(te[TARGET], fit_predict(tr, te)))
    return out


def tune(df: pd.DataFrame, params: dict, n_trials: int = 30) -> dict:
    """TimeSeriesSplit(5) search on the training period: optuna for the best model's LightGBM,
    small grids for the ladder ridge / random forest / LightGBM."""
    import optuna
    train_df = split_frame(df, "train")
    best_cfg = dict(params["best"], n_seeds=1, linear_weight=0.0, quantiles=[])

    def objective(trial):
        p = {"learning_rate": trial.suggest_float("learning_rate", 0.01, 0.1, log=True),
             "n_estimators": trial.suggest_int("n_estimators", 300, 3000, log=True),
             "num_leaves": trial.suggest_int("num_leaves", 7, 127, log=True),
             "min_child_samples": trial.suggest_int("min_child_samples", 5, 100, log=True),
             "colsample_bytree": trial.suggest_float("colsample_bytree", 0.3, 1.0),
             "subsample": trial.suggest_float("subsample", 0.5, 1.0),
             "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 30, log=True), "subsample_freq": 1}
        cfg = dict(best_cfg, gbm_params=p)
        s = cv_score(train_df, lambda a, b: fit_best(a, params, cfg, quantiles=False).predict(b))
        print(f"  trial {trial.number}: CV MAE {np.mean(s):.3f}", flush=True)
        return float(np.mean(s))

    study = optuna.create_study(sampler=optuna.samplers.TPESampler(seed=params["seed"]))
    study.enqueue_trial({k: v for k, v in params["best"]["gbm_params"].items() if k != "subsample_freq"})
    study.optimize(objective, n_trials=n_trials)
    params["best"]["gbm_params"] = {**study.best_params, "subsample_freq": 1}

    # ladder grids (level target)
    def ladder_cv(p):
        return float(np.mean(cv_score(train_df, lambda a, b: fit_ladder(a, p)[which].predict(b))))
    for which, key, grid in [
        ("linear", "linear_ladder", [{"alpha": a} for a in [1.0, 10.0, 100.0]]),
        ("rf", "rf_ladder", [{"n_estimators": 150, "max_depth": md, "min_samples_leaf": ml, "max_features": mf}
                             for md in [10, 14] for ml in [5, 20] for mf in [0.4, 0.7]]),
        ("gbm", "gbm_ladder", [dict(params["gbm_ladder"], num_leaves=nl, n_estimators=ne)
                               for nl in [15, 31, 63] for ne in [800, 1500]]),
    ]:
        scores = []
        for g in grid:
            p = json.loads(json.dumps(params))
            p[key] = g
            scores.append(ladder_cv(p))
            print(f"  {which} {g}: CV MAE {scores[-1]:.3f}", flush=True)
        params[key] = grid[int(np.argmin(scores))]
    return params


# ----------------------------------------------------------------------------------------------
# experiments on September (--experiments): what was tried, weather variants, sensitivity runs
# ----------------------------------------------------------------------------------------------
def experiments(df: pd.DataFrame, params: dict, parts=("variants", "sensitivity")) -> pd.DataFrame:
    """Compare variants of the best model on September (fit on train) and with the TimeSeriesSplit
    CV on the training period. Sensitivity runs also report October (refit ≤ Sep 30) - they are for
    the notes only, never for choosing the model."""
    base = params["best"]
    tr, va, te, tv = (split_frame(df, s) for s in ["train", "val", "test", "trainval"])
    rows = []

    def run(name, cfg, kind, with_test=False, with_cv=True):
        t0 = time.time()
        m = fit_best(tr, params, cfg, quantiles=False)
        p = m.predict(va)
        r = {"experiment": name, "kind": kind, "val_mae": mae(va[TARGET], p), "val_mape": mape(va[TARGET], p),
             "val_bias": bias(va[TARGET], p)}
        if with_cv:
            s = cv_score(tr, lambda a, b: fit_best(a, params, dict(cfg, n_seeds=1), quantiles=False).predict(b))
            r.update(cv_mae=float(np.mean(s)), cv_mae_last2=float(np.mean(s[-2:])))
        if with_test:
            pt = fit_best(tv, params, cfg, quantiles=False).predict(te)
            r.update(test_mae=mae(te[TARGET], pt), test_mape=mape(te[TARGET], pt))
        rows.append(r)
        print(f"  {name}: val MAE {r['val_mae']:.3f} ({time.time() - t0:.0f}s)", flush=True)

    one = dict(base, n_seeds=1, linear_weight=0.0)       # single LightGBM, fast and comparable
    if "variants" in parts:
        _variants(df, params, base, one, run, rows, tr, va)
    if "sensitivity" in parts:
        _sensitivity(one, run)
    out = pd.DataFrame(rows)
    f = path("reports") / "experiments_demand.csv"
    if f.exists() and set(parts) != {"variants", "sensitivity"}:   # keep the other part of an earlier run
        old = pd.read_csv(f)
        kinds = set(out["kind"])
        out = pd.concat([old[~old["kind"].isin(kinds)], out], ignore_index=True)
    out = out.sort_values("experiment", kind="stable").reset_index(drop=True)
    out.to_csv(f, index=False, float_format="%.4f")
    return out


def _variants(df, params, base, one, run, rows, tr, va):
    """Model variants on September + CV (used to choose the configuration)."""
    run("A  LightGBM log-ratio vs 2-day lag (1 seed)", one, "variant")
    run("A0 LightGBM on the level", dict(one, transform="level"), "variant")
    run("A1 log-ratio vs 7-day lag", dict(one, reference_col=NAIVE_COL), "variant")
    run("A2 difference vs 2-day lag", dict(one, transform="diff"), "variant")
    run("A3 difference vs 4-week same-weekday mean",
        dict(one, transform="diff", reference_col="demand_mean_same_block_same_weekday_4w"), "variant")
    run("B1 L1 loss", dict(one, objective="l1"), "variant")
    run("B2 Huber loss", dict(one, objective="huber", gbm_params=dict(one["gbm_params"], alpha=0.03)), "variant")
    run("C1 recency half-life 1 y", dict(one, half_life_years=1), "variant")
    run("C2 recency half-life 2 y", dict(one, half_life_years=2), "variant")
    run("C3 recency half-life 3 y", dict(one, half_life_years=3), "variant")
    run("C4 COVID lockdown weight 0.1", dict(one, covid_weight=0.1), "variant")
    run("D1 weather: forecast-era rows weight 2", dict(one, forecast_row_weight=2.0), "weather")
    run("D2 weather: JMA forecasts for all years", dict(one, weather="jma"), "weather")
    run("D3 weather: ICON hybrid + JMA columns", dict(one, weather="both"), "weather")
    run("D4 ORACLE weather (observed, NOT achievable)", dict(one, weather="oracle"), "weather")
    run("E1 no extra features (temp/radiation vs lag day)", dict(one, extra_features=[]), "variant")
    run("F1 5 seeds", dict(one, n_seeds=5), "ensemble", with_cv=False)
    run("F2 5 seeds + ridge 15 %", dict(base, walk_forward=False), "ensemble", with_cv=False)
    run("F3 5 seeds + ridge 30 %", dict(base, linear_weight=0.3), "ensemble", with_cv=False)
    # walk-forward on September (single seed + ridge, to keep it affordable)
    wf_cfg = dict(base, n_seeds=1)
    p = walk_forward_best(df, sorted(va["delivery_date"].unique()), params, wf_cfg)["pred_best"].to_numpy()
    st = fit_best(tr, params, wf_cfg, quantiles=False).predict(va)
    rows.append({"experiment": "G0 1 seed + ridge, fit once", "kind": "walk-forward",
                 "val_mae": mae(va[TARGET], st), "val_mape": mape(va[TARGET], st), "val_bias": bias(va[TARGET], st)})
    rows.append({"experiment": "G1 1 seed + ridge, daily walk-forward refit", "kind": "walk-forward",
                 "val_mae": mae(va[TARGET], p), "val_mape": mape(va[TARGET], p), "val_bias": bias(va[TARGET], p)})


def _sensitivity(one, run):
    """Sensitivity runs (single LightGBM, val + test) - for the notes only."""
    run("S0 sensitivity base (1 seed, all features)", one, "sensitivity", with_test=True, with_cv=False)
    run("S1 demand one day later (no D−1 demand)",
        dict(one, drop_features=D1_DEMAND_COLS, reference_col="demand_lag_3d_same_block",
             extra_features=["rad_vs_lag2", "temp_vs_lag2"]), "sensitivity", with_test=True, with_cv=False)
    run("S2 without EV features", dict(one, drop_features=EV_COLS), "sensitivity", with_test=True, with_cv=False)
    run("S3 without event/football features", dict(one, drop_features=EVENT_COLS), "sensitivity",
        with_test=True, with_cv=False)
    run("S4 without weather", dict(one, drop_features=WEATHER_COLS, extra_features=[]), "sensitivity",
        with_test=True, with_cv=False)
    run("S5 without solar (lagged Swiss solar)", dict(one, drop_features=SOLAR_COLS), "sensitivity",
        with_test=True, with_cv=False)


# ----------------------------------------------------------------------------------------------
# notes
# ----------------------------------------------------------------------------------------------
def _md(df: pd.DataFrame, floatfmt: str = ".2f") -> str:
    return df.to_markdown(index=False, floatfmt=floatfmt)


def write_notes(met: pd.DataFrame, tests: pd.DataFrame, imp: pd.DataFrame, gimp: pd.DataFrame,
                cov: pd.DataFrame, params: dict, runtime_s: float):
    """reports/model_notes_demand.md: fixed text (NOTES_*) + tables filled from this run."""
    allm = met[met["block"] == "all"]

    def table(split):
        t = allm[allm["split"] == split][["model", "mae", "rmse", "mape_or_smape", "bias", "mae_ci_low",
                                          "mae_ci_high"]].copy()
        naive = t.loc[t["model"] == "naive", "mae"].iloc[0]
        t["skill_vs_naive_%"] = 100 * (1 - t["mae"] / naive)
        return _md(t.rename(columns={"mape_or_smape": "mape_%"}))

    exp_file = path("reports") / "experiments_demand.csv"
    exp = pd.read_csv(exp_file) if exp_file.exists() else pd.DataFrame()
    blk = met[(met["split"] == "test") & (met["block"] != "all") & (met["model"].isin(["naive", "best"]))]
    blk = blk.pivot(index="block", columns="model", values="mae").reset_index()
    txt = [NOTES_HEAD.format(best=json.dumps(params["best"], indent=None))]
    txt += ["## Validation (September 2026, models fit on data ≤ 30 Aug 2026)\n", table("val"), "\n"]
    txt += ["## Test (October 2026, refit on data ≤ 29 Sep 2026)\n", table("test"), "\n",
            "95 % CI = day-clustered bootstrap (1000 draws of whole days).\n"]
    txt += ["### Test MAE per block (MW)\n", _md(blk), "\n"]
    txt += ["## Rolling-origin backtest (Oct 2025 – Aug 2026, monthly refit)\n", table("rolling"), "\n"]
    if not tests.empty:
        txt += ["## Diebold–Mariano tests (daily mean absolute error; negative = best is better)\n",
                _md(tests[["split", "model_a", "model_b", "mean_diff", "dm_stat", "p_value", "n_days"]], ".3f"), "\n"]
    if not cov.empty:
        txt += ["## Prediction band (quantile LightGBM 10 % / 90 %)\n", _md(cov.reset_index(), ".3f"), "\n"]
    if not exp.empty:
        txt += ["## What was tried (September 2026 + 5-fold time-series CV on the training period)\n",
                "Single LightGBM unless stated; `cv_mae` = mean over the 5 folds, `cv_mae_last2` = the two "
                "most recent folds (closest to the forecast era). Sensitivity rows also show October "
                "(reporting only, not used for choices).\n",
                _md(exp, ".3f"), "\n"]
    txt += [NOTES_CHOICE, "\n"]
    txt += ["## Driver importance\n", "Permutation importance on Sept + Oct 2026 (MAE increase in MW when a "
            "column, or a whole group of columns, is shuffled).\n\n### Groups\n",
            _md(gimp[["feature", "mae_increase", "std"]], ".3f"), "\n\n### Top 20 single columns\n",
            _md(imp.head(20)[["feature", "mae_increase", "std"]], ".3f"), "\n"]
    txt += [NOTES_DRIVERS, "\n", NOTES_LIMITS, "\n", f"_`main()` runtime of this run: {runtime_s / 60:.1f} min._\n"]
    (path("reports") / "model_notes_demand.md").write_text("\n".join(txt), encoding="utf-8")


NOTES_HEAD = """# Demand model – notes (agent M1)

**Target:** `demand_mw` = mean MW of the Zurich city grid load (ewz) in each 4-hour block of the delivery day
(≈ 300 MW). **Forecast time:** day D 10:00, for all six blocks of D+1. The latest known demand is the full day
D−1, i.e. two days before delivery.

**Best model in one sentence:** LightGBM learns *how much higher or lower each block will be than the same block
two days earlier* (log ratio), five LightGBM runs with different seeds are averaged and blended 85 / 15 with a
ridge regression that learns the same ratio. Settings: `{best}`
"""

NOTES_CHOICE = """## Why this model won (decided on September 2026 + CV, before looking at October)
* **Target transform is the big step.** LightGBM on the demand level: CV MAE 6.41 MW, September 3.85. The same
  LightGBM predicting log(demand / same block two days earlier): CV 4.61, September 3.29. Trees cannot extrapolate
  a level, but "a bit higher or lower than the last known day" they predict well. The 2-day reference beats the
  7-day reference (CV 5.88) and the 4-week same-weekday mean (CV 6.74) because it carries the most recent level
  (school holidays, weather spells). A plain difference instead of the log ratio was equal in CV (4.59) but worse on
  September (3.42).
* **Loss:** L1 and Huber were not better in CV (4.88 / 4.78 vs 4.61); Huber looked good on September alone
  (3.19) but we trusted the 5 CV folds more than one month - kept squared error (L2).
* **Weighting:** recency weighting (half-life 1–3 years) and down-weighting the COVID lockdown made CV equal or
  worse - all history is used with equal weight; `covid_stringency` stays an input.
* **Weather source:** the ICON/observed hybrid won. JMA forecasts for all years were clearly worse (Sept 3.82, CV
  4.98) - JMA has no solar radiation, and radiation is the most useful weather input. ICON hybrid + JMA together:
  CV of the last two folds slightly better (4.59 vs 4.61) but September worse (3.44) - not adopted. Giving
  forecast-era rows double weight changed nothing. The ORACLE run with observed weather of the delivery day (NOT
  achievable in practice) reaches 3.01 on September and 3.75 in the last two CV folds: the error of the weather
  forecast costs about 0.3 MW (≈ 9 %) on September and ≈ 0.9 MW in the recent CV folds.
* **Extra features:** forecast minus observed temperature / radiation of the reference day helped a little
  (September 3.37 → 3.29). Ratio versions of all lags (each lag ÷ 2-day lag) and a holiday-"cleaned" reference
  (7-day lag when the 2-day lag day was a holiday) made CV worse and were dropped.
* **Ensemble:** averaging 5 LightGBM seeds (3.29 → 3.24) and blending with 15 % ridge regression on the same log
  ratio (→ 3.20) helped; 30 % ridge was slightly worse (3.22). One-seed LightGBM results move by about ±0.1 MW
  between seeds, so smaller differences on September are noise.
* **Daily walk-forward refit:** on September 3.245 → 3.178 MW (1 seed + ridge). This gain is smaller than the seed
  noise and makes `main()` about 30× slower for the test month, so the model is fit once (≤ 29 Sep) for October.
* **Hyper-parameters:** an optuna search (TimeSeriesSplit 5 folds on the training period, 16 trials) did not
  beat the starting values (learning rate 0.03, 1500 trees, 31 leaves; CV 4.615 vs best other 4.628), so those
  were kept. Ladder ridge/RF/LightGBM settings were set with small CV grids.
* **Per-block models** were not tried separately: `block` is the 2nd most important input of the pooled model
  and the pooled model already gets the per-block shape from `demand_dm1_block_*`.
* **Linear model:** ridge with one-hot block × weekday-type, block × month, per-block slopes for temperature,
  heating/cooling degrees, radiation and the main lags. Trending inputs (EV counts, charging power, year,
  COVID index) were left out: a straight line through them gave absurd forecasts in early CV folds
  (CV 20 → 5.1 MW without them). Missing early values (charging data before Dec 2020, 364-day lag in 2019) are
  filled with the training median plus a "was missing" flag.

### Error on special days (rolling Oct 2025–Aug 2026 + October 2026, MAE in MW)
| day type | rows | naive | gbm (level) | best | best bias |
|---|---|---|---|---|---|
| normal day | 1548 | 13.68 | 5.18 | 4.55 | −0.41 |
| school holiday | 492 | 12.12 | 4.93 | 4.00 | +0.69 |
| public holiday (the six outside 24 Dec–2 Jan) | 36 | 52.54 | 5.12 | 4.49 | +2.11 |
| delivery two days after a holiday (T−2 was a holiday, misleading reference) | 48 | 22.21 | 6.01 | 6.60 | −3.69 |
| Christmas period | 60 | 27.96 | 6.13 | 6.59 | −1.68 |
| bridge day | 6 | 8.47 | 5.50 | 5.34 | −0.06 |
| half holiday (e.g. Sechseläuten, Knabenschiessen) | 6 | 36.67 | 10.45 | 7.72 | +7.59 |

The best model handles holidays themselves well, but on delivery days two days *after* a holiday (when the
reference day T−2 was a holiday) and around Christmas it is slightly worse than the level LightGBM and forecasts too low. Blending in
the level model on such days is the obvious next improvement (not done, to keep the October test untouched).
"""

NOTES_DRIVERS = """## Top-10 drivers (single columns, permutation importance on Sept + Oct 2026)
1. **`demand_lag_2d_same_block`** – demand of the same block on the last known day (D−1); it is the reference the
   model scales, so shuffling it destroys the forecast.
2. **`block`** – time of day: the ratio to the reference day differs between night, office hours and evening.
3. **`is_working_day`** – whether delivery day is a working day (not weekend, not public holiday); offices and
   businesses drive the daytime load.
4. **`weekday`** – Monday vs Friday vs weekend; together with the reference day's weekday it tells how big the
   jump from the reference day is.
5. **`radiation_wm2`** – forecast solar radiation of the block; sunshine lowers the grid load in daytime blocks
   (rooftop solar behind the meter, less lighting).
6. **`demand_dm1_block_2`** – yesterday's 08–12 block: a clean measure of the most recent working-day level.
7. **`radiation_obs_same_block_lag_2d`** – how sunny the reference day was: a sunny reference day had lower load,
   so the model corrects upwards if tomorrow is cloudy (and vice versa).
8. **`lag2d_is_weekend`** – the reference day was a weekend day, so the ratio to a working day is large.
9. **`demand_mean_same_block_same_weekday_4w`** – typical level of this block on this weekday in the last 4 weeks;
   an anchor that is not affected by a single odd day.
10. **`heating_degree`** – how far the forecast temperature is below 15 °C; electric heating and heat pumps raise
    the load on cold days (small in October, more important in winter).

### The driver groups asked for in the brief
* **EVs:** the EV and charging columns add nothing measurable (group importance ≈ 0.00 MW; without them the
  single-LightGBM MAE was even slightly lower, 3.29 → 3.16 in Sept, 3.63 → 3.53 in Oct). They grow smoothly over
  years, and that slow trend is already in the recent demand lags.
* **Weather:** the fourth most important input group, after past demand, weekday/weekend and holidays (shuffling
  all weather columns adds 7.0 MW of MAE; without weather inputs the single LightGBM goes from 3.29 to 7.41 MW in September). Solar
  radiation matters most, temperature less in this mild season.
* **Solar:** the lagged Swiss solar production (Energy-Charts) adds almost nothing (0.013 MW); the solar effect on
  city load is captured through the radiation forecast for the delivery day.
* **Holidays:** essential - the holiday/school-holiday group adds 9.5 MW of MAE when shuffled. On public holidays
  outside 24 Dec–2 Jan (six days) the model's error is 4.5 MW against 52.5 MW for the naive forecast (all ten public
  holidays: 5.6 vs 48.3 MW); the weak spot is delivery two days after a holiday (6.6 MW).
* **Events:** big events and FC Zürich / GC home games add little incremental predictive value in this model
  (importance ≤ 0; without them the single-seed October MAE was 3.47 instead of 3.63 MW, a difference within the
  seed noise). This is not a causal statement about events and load.
* **Data delay:** if demand of D−1 were not yet available (only D−2), the MAE would rise from 3.29 to 3.93 MW in
  September and from 3.63 to 4.70 MW in October (single LightGBM).
"""

NOTES_LIMITS = """## Limitations
* **Weather in training:** before 2024-01-21 the weather inputs are observed values (no forecast archive); only
  the last ~2.7 years use real ICON forecasts. The model therefore may trust the weather a little too much. The
  test months use real forecasts, so the reported test errors are honest.
* **Short test months:** one month = 30–31 days, so the 95 % CI of the test MAE is about ±0.5 MW. The DM test of
  best vs plain LightGBM is significant on September, on October (p ≈ 0.03) and in the 11-month rolling
  backtest.
* **Prediction band:** the 10–90 % band contains 73–78 % of the actuals instead of 80 % - slightly too narrow.
* **Refit dates:** the validation and test models are fit on data up to 30 Aug / 29 Sep, the last day whose
  demand is known when the first forecast of the month is made. (An earlier version used 31 Aug / 30 Sep; an
  independent review flagged it. The fix moved the October error from 3.36 to 3.34 MW.)
* **Days after holidays, Christmas and half-holidays** are the weakest cases (see table above).
* **Importance:** permutation importance splits the credit between related columns (e.g. `weekday`,
  `is_working_day`, `is_weekend`), so single numbers should be read together with the group table.
"""


# ----------------------------------------------------------------------------------------------
# notebook
# ----------------------------------------------------------------------------------------------
def build_notebook():
    """Write and execute notebooks/02_demand_model.ipynb (reads the saved outputs only)."""
    import nbformat
    from nbconvert.preprocessors import ExecutePreprocessor
    from src.config import ROOT

    md, code = nbformat.v4.new_markdown_cell, nbformat.v4.new_code_cell
    cells = [
        md("# 02 – Demand model (Zurich city load, day-ahead, 4-hour blocks)\n\n"
           "Loads the outputs of `python -m src.models.demand` and shows the key tables and figures. "
           "Details and the plain-language summary: `reports/model_notes_demand.md`."),
        code("import os, sys\nsys.path.insert(0, os.path.abspath('..'))\nos.chdir(os.path.abspath('..'))\n"
             "import pandas as pd, joblib\nfrom IPython.display import Image, display\n"
             "import src.models.common as common\npd.set_option('display.precision', 3)"),
        md("## Overall metrics (MW; MAPE in %)"),
        code("met = pd.read_csv('reports/metrics_demand.csv', dtype={'block': str})\n"
             "allm = met[met.block == 'all']\n"
             "allm.pivot_table(index='model', columns='split', values=['mae', 'mape_or_smape'])"
             ".reindex(['naive', 'linear', 'rf', 'gbm', 'best'])"),
        md("## Test month (October 2026) with day-clustered bootstrap 95 % CI for the MAE"),
        code("allm[allm.split == 'test'][['model', 'mae', 'rmse', 'mape_or_smape', 'bias', 'mae_ci_low', "
             "'mae_ci_high']]"),
        md("## MAE per block, test month"),
        code("met[(met.split == 'test') & (met.block != 'all')].pivot(index='block', columns='model', values='mae')"),
        md("## Diebold–Mariano tests (daily MAE; negative mean_diff = best is better)"),
        code("pd.read_csv('reports/model_tests_demand.csv')"),
        md("## Forecast vs actual, October 2026"),
        code("display(Image('reports/figures/demand_test_forecast_vs_actual.png'))"),
        code("display(Image('reports/figures/demand_model_ladder.png'))\n"
             "display(Image('reports/figures/demand_error_by_block.png'))"),
        md("## Prediction band coverage (should be about 80 % inside the 10–90 % band)"),
        code("pr = pd.read_parquet('reports/predictions_demand.parquet')\n"
             "pr['inside'] = (pr.y_true >= pr.pred_q10) & (pr.y_true <= pr.pred_q90)\n"
             "pr.groupby('split').inside.mean()"),
        md("## Drivers (permutation importance on Sep + Oct 2026)"),
        code("display(pd.read_csv('reports/importance_groups_demand.csv'))\n"
             "display(Image('reports/figures/demand_permutation_importance.png'))"),
        md("## What was tried (September 2026 and time-series CV)"),
        code("pd.read_csv('reports/experiments_demand.csv')"),
        md("## The saved model predicts any rows of features.parquet"),
        code("m = joblib.load('models/demand_best.joblib')\n"
             "oct_rows = common.split_frame(common.load_features(), 'test')\n"
             "out = oct_rows[['delivery_date', 'block', 'demand_mw']].copy()\n"
             "out['forecast'] = m.predict(oct_rows)\nout.head(12)"),
    ]
    nb = nbformat.v4.new_notebook(cells=cells)
    nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
    f = ROOT / "notebooks" / "02_demand_model.ipynb"
    f.parent.mkdir(exist_ok=True)
    ExecutePreprocessor(timeout=600, kernel_name="python3").preprocess(nb, {"metadata": {"path": str(f.parent)}})
    nbformat.write(nb, f)
    print(f"notebook written: {f}")

# ----------------------------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tune", action="store_true", help="redo the hyper-parameter search (slow)")
    ap.add_argument("--experiments", action="store_true", help="redo the September variant comparison (slow)")
    ap.add_argument("--notes-only", action="store_true", help="only rewrite the notes from saved outputs")
    ap.add_argument("--notebook", action="store_true", help="only rebuild + execute the notebook")
    ap.add_argument("--skip-rolling", action="store_true", help="skip the rolling backtest (faster, for debugging)")
    args = ap.parse_args(argv)
    if args.notebook:
        build_notebook()
        return
    if args.notes_only:
        rep = path("reports")
        pred = pd.read_parquet(rep / "predictions_demand.parquet")
        info = json.loads((rep / "run_info_demand.json").read_text())
        write_notes(pd.read_csv(rep / "metrics_demand.csv", dtype={"block": str}),
                    pd.read_csv(rep / "model_tests_demand.csv"), pd.read_csv(rep / "importance_demand.csv"),
                    pd.read_csv(rep / "importance_groups_demand.csv"), quantile_coverage(pred), load_params(),
                    info["runtime_seconds"])
        return
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

    print("validation: fit on train ...", flush=True)
    # Demand of the last day before the month is not yet known when the first forecast of the
    # month is made (day D at 10:00 knows demand up to D-1, the delivery day is D+1), so stop one day earlier.
    one_day = pd.Timedelta(days=TARGET_LAG_DAYS - 1)
    lad_tr, best_tr = train(df, p_dates["train_end"] - one_day, params)
    pv = predict_frame(va, lad_tr, best_tr, "val")
    if cfg.get("walk_forward"):
        wf = walk_forward_best(df, sorted(va["delivery_date"].unique()), params, quantiles=False)
        pv["pred_best"] = wf["pred_best"].to_numpy()

    print("test: refit on train + validation ...", flush=True)
    lad_tv, best_tv = train(df, p_dates["val_end"] - one_day, params)
    pt = predict_frame(te, lad_tv, best_tv, "test")
    if cfg.get("walk_forward"):
        wf = walk_forward_best(df, sorted(te["delivery_date"].unique()), params, quantiles=False)
        pt["pred_best"] = wf["pred_best"].to_numpy()

    parts = [pv, pt]
    if not args.skip_rolling:
        print("rolling backtest ...", flush=True)
        parts.insert(0, rolling_backtest(df, params))
    pred = pd.concat(parts, ignore_index=True)
    pred["delivery_date"] = pd.to_datetime(pred["delivery_date"])
    pred.to_parquet(rep / "predictions_demand.parquet", index=False)

    met, tests = evaluate(pred, seed)
    met.to_csv(rep / "metrics_demand.csv", index=False)
    tests.to_csv(rep / "model_tests_demand.csv", index=False)
    cov = quantile_coverage(pred)

    # saved models (fit ≤ 29 Sep 2026)
    joblib.dump(best_tv, models_dir / "demand_best.joblib", compress=3)
    joblib.dump(lad_tv, models_dir / "demand_ladder.joblib", compress=3)

    print("importance ...", flush=True)
    imp, gimp = importance(df, best_tr, best_tv, seed)
    imp.to_csv(rep / "importance_demand.csv", index=False)
    gimp.to_csv(rep / "importance_groups_demand.csv", index=False)

    tp = pred[pred["split"] == "test"]
    plot_forecast_vs_actual(tp, fig / "demand_test_forecast_vs_actual.png",
                            "Zurich demand, October 2026 (test): forecast vs actual", "MW",
                            band=("pred_q10", "pred_q90"))
    plot_error_by_block(met, fig / "demand_error_by_block.png", "test",
                        "Demand: MAE per block, October 2026 (test)", "MW")
    plot_importance(imp, fig / "demand_permutation_importance.png",
                    "Demand (best model): permutation importance, Sep + Oct 2026", "MW")
    plot_model_ladder(met, fig / "demand_model_ladder.png", "Demand: MAE per model and split", "MW")

    runtime = time.time() - t_start
    with open(rep / "run_info_demand.json", "w") as fh:
        json.dump({"runtime_seconds": round(runtime, 1), "finished": pd.Timestamp.now().isoformat()}, fh)
    write_notes(met, tests, imp, gimp, cov, params, runtime)
    allm = met[met["block"] == "all"].pivot(index="model", columns="split", values="mae")
    print(allm.round(3).to_string())
    print(tests.round(4).to_string())
    print(f"done in {runtime / 60:.1f} min")


if __name__ == "__main__":
    # Import the module under its real name so that pickled classes (DemandExtras) are saved as
    # `src.models.demand.DemandExtras`, not `__main__.DemandExtras` (which the app could not load).
    from src.models import demand as _demand
    _demand.main()
