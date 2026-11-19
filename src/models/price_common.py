"""Small picklable helpers for the price model (`src/models/price.py`).

They live in their own module so that `joblib.load("models/price_best.joblib")` works from the app
after `import src.models.price_common` (or `import src.models.common`, which the app imports anyway;
joblib imports this module by itself when it unpickles the model).

* `PriceExtras`      derived columns (shape of day D, weekday of day D, fuel spread, interactions)
* `AsinhTarget`      wrapper: the estimator learns asinh-scaled CHANGES vs a reference price
* `DayShapeTarget`   wrapper: two-stage model (day-mean change + within-day shape)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

BLOCKS = range(6)


class PriceExtras:
    """Adds derived columns to rows of features.parquet (all from columns known at 10:00 on day D).

    shape_dD            price of the same block on day D − day-D mean (yesterday's shape for this block)
    shape_lag7          same for the delivery weekday one week earlier
    ref_shape7          day-D mean + mean 7-day shape of this block (a strong "naive" reference)
    dD_weekday          weekday of day D (0 = Monday); dD_daytype 0 working day, 1 Saturday, 2 Sunday/holiday
    day_change_type     code for the pair (day D type, delivery day type): e.g. Sunday→Monday
    gas_vs_price        clean gas cost − day-D mean price (is power cheap or expensive vs gas?)
    de_shape_dD, fr_shape_dD, it_shape_dD   neighbour block price − neighbour day mean on day D
    rad_x_weekend       Zurich radiation × weekend/holiday (sunny Sundays → negative midday prices)
    rad_de_x_trend      German radiation forecast (JMA has none; ICON, NaN before 2024) × years since 2019
    rad_x_trend         Zurich radiation × years since 2019 (solar build-out)
    wind_de_x_winter    German wind³ (JMA, full history) × winter flag (Oct–Mar)
    resid_proxy         Swiss load (D−1, same block) − Swiss solar (D−1, same block) scaled by
                        tomorrow's radiation ratio vs D−1 - a rough residual-load forecast
    """

    input_columns = [
        "block", "weekday", "is_holiday", "is_holiday_prev_day", "month", "year_frac",
        "price_lag_1d_same_block", "price_mean_day_D", "price_lag_7d_same_block", "price_lag_7d_day_mean",
        "price_block_vs_day_ratio_last_7d", "clean_gas_cost",
        "price_de_day_D_same_block", "price_de_mean_day_D", "price_fr_day_D_same_block", "price_fr_mean_day_D",
        "price_it_day_D_same_block", "price_it_mean_day_D", "radiation_wm2", "is_weekend",
        "eu_radiation_wm2_de_mean_safe", "eu_wind_cubed_de_mean_jma_safe",
        "swiss_load_lag_2d_same_block", "swiss_solar_mw_lag_2d_same_block", "radiation_obs_same_block_lag_2d",
    ]
    output_columns = [
        "shape_dD", "shape_lag7", "ref_shape7", "dD_weekday", "dD_daytype", "day_change_type", "gas_vs_price",
        "de_shape_dD", "fr_shape_dD", "it_shape_dD", "rad_x_weekend", "rad_de_x_trend", "rad_x_trend",
        "wind_de_x_winter", "resid_proxy",
    ]

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        d = df.copy()
        d["shape_dD"] = d["price_lag_1d_same_block"] - d["price_mean_day_D"]
        d["shape_lag7"] = d["price_lag_7d_same_block"] - d["price_lag_7d_day_mean"]
        d["ref_shape7"] = d["price_mean_day_D"] + d["price_block_vs_day_ratio_last_7d"]
        d["dD_weekday"] = (d["weekday"] - 1) % 7
        d["dD_daytype"] = np.select([d["is_holiday_prev_day"] == 1, d["dD_weekday"] == 6, d["dD_weekday"] == 5],
                                    [2, 2, 1], 0)
        deliv_type = np.select([d["is_holiday"] == 1, d["weekday"] == 6, d["weekday"] == 5], [2, 2, 1], 0)
        d["day_change_type"] = 3 * d["dD_daytype"] + deliv_type
        d["gas_vs_price"] = d["clean_gas_cost"] - d["price_mean_day_D"]
        for c in ("de", "fr", "it"):
            d[f"{c}_shape_dD"] = d[f"price_{c}_day_D_same_block"] - d[f"price_{c}_mean_day_D"]
        off = ((d["is_weekend"] == 1) | (d["is_holiday"] == 1)).astype(float)
        trend = d["year_frac"] - 2019
        d["rad_x_weekend"] = d["radiation_wm2"] * off
        d["rad_de_x_trend"] = d["eu_radiation_wm2_de_mean_safe"] * trend
        d["rad_x_trend"] = d["radiation_wm2"] * trend
        winter = d["month"].isin([10, 11, 12, 1, 2, 3]).astype(float)
        d["wind_de_x_winter"] = d["eu_wind_cubed_de_mean_jma_safe"] * winter
        ratio = (d["radiation_wm2"] + 20) / (d["radiation_obs_same_block_lag_2d"] + 20)
        d["resid_proxy"] = d["swiss_load_lag_2d_same_block"] - d["swiss_solar_mw_lag_2d_same_block"] * ratio.clip(0, 5)
        return d


class AsinhTarget:
    """Wrap a regressor so it learns  asinh(y / s) − asinh(ref / s)  (a damped price change).

    asinh behaves like a log for large prices and like a straight line near zero, so it works with
    negative prices. `ref_col` must be one of the input columns. predict() returns EUR/MWh."""

    def __init__(self, estimator, ref_col: str, scale: float = 50.0):
        self.estimator = estimator
        self.ref_col = ref_col
        self.scale = scale

    def fit(self, X: pd.DataFrame, y, sample_weight=None, **fit_kw):
        r = X[self.ref_col].to_numpy(float) / self.scale
        z = np.arcsinh(np.asarray(y, float) / self.scale) - np.arcsinh(r)
        if sample_weight is not None:
            fit_kw[self._weight_key()] = sample_weight
        self.estimator.fit(X, z, **fit_kw)
        return self

    def _weight_key(self):
        steps = getattr(self.estimator, "steps", None)
        return f"{steps[-1][0]}__sample_weight" if steps else "sample_weight"

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        r = X[self.ref_col].to_numpy(float) / self.scale
        return self.scale * np.sinh(np.arcsinh(r) + np.asarray(self.estimator.predict(X), float))


class DayShapeTarget:
    """Two-stage model: `level` learns the change of the DAY MEAN vs the day-D mean (one value per
    delivery day, repeated on its 6 rows), `shape` learns block price − delivery-day mean.

    Both are regressors with `.fit(X, z, **kw)` / `.predict(X)`. predict() = day-D mean + level + shape."""

    def __init__(self, level, shape, day_mean_col: str = "price_mean_day_D"):
        self.level = level
        self.shape = shape
        self.day_mean_col = day_mean_col

    def fit(self, X: pd.DataFrame, y, sample_weight=None, day_key=None):
        y = pd.Series(np.asarray(y, float), index=X.index)
        dm = y.groupby(np.asarray(day_key)).transform("mean")
        kw = {} if sample_weight is None else {"sample_weight": sample_weight}
        self.level.fit(X, (dm - X[self.day_mean_col]).to_numpy(), **_kw(self.level, kw))
        self.shape.fit(X, (y - dm).to_numpy(), **_kw(self.shape, kw))
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return X[self.day_mean_col].to_numpy(float) + self.level.predict(X) + self.shape.predict(X)


def _kw(est, kw):
    steps = getattr(est, "steps", None)
    if steps and kw:
        return {f"{steps[-1][0]}__sample_weight": kw["sample_weight"]}
    return kw
