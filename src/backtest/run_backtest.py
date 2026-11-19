"""Backtest: forecast -> battery plan -> hourly bids -> settlement with ACTUAL data.

For every delivery day of a period and for every strategy we

1. take the demand and price forecasts per block (as they were known at forecast time),
2. let the optimiser (MILP) plan buy / charge / discharge, either per block or per hour
   (decision option ``plan_resolution``),
3. turn the plan into hourly auction bids (``src/decision/bids.py``),
4. settle the bids with the ACTUAL hourly prices and the ACTUAL hourly demand:
   * charge bids clear only in hours where the actual price <= limit price,
   * the battery follows the cleared plan hour by hour (planned discharge that is
     physically impossible because the battery is too empty is not delivered),
   * the gap between actual demand and the energy available for the city is the
     imbalance, settled at a penalty price (see ``ImbalanceParams``),
5. carry the ACTUAL end-of-day charge level into the next day.

Run it (from the repo root)::

    .venv/bin/python -m src.backtest.run_backtest                 # tuning + val + test + rolling + sensitivities
    .venv/bin/python -m src.backtest.run_backtest --require-ml    # same, fail if a prediction file is missing
    .venv/bin/python -m src.backtest.run_backtest --start 2026-10-01 --end 2026-10-31

Public API (used by the Streamlit app and the notebook)
-------------------------------------------------------
``plan_day(delivery_date, strategy="ml_battery", battery=None, soc_start_mwh=None,
decision=None, settle=True, ...)`` returns a dict:

* ``plan`` - DataFrame, ALWAYS 6 rows (one per block): ``period, block, hours,
  demand_mwh, price_eur_mwh`` (block forecast), ``buy_mwh, charge_mwh, discharge_mwh,
  sell_mwh, soc_mwh`` (charge level at the end of the block), ``option`` (buy |
  buy_and_store | use_storage | use_storage_and_buy) and ``charge_limit_eur_mwh``
  (charge-weighted mean of the hourly limits, NaN = no limit / no charge). In hourly
  mode these are the sums of the hourly plan. ``plan.attrs``: status, cost_eur (expected),
  cost_no_battery_eur, saving_eur, cycles, soc_start_mwh, plan_resolution.
* ``plan_periods`` - the optimiser's own plan (6 blocks or 23/24/25 hours).
* ``hourly`` - one row per delivery hour: forecast need, planned discharge, demand bid,
  charge bid, limit, at-risk protection volume, option.
* ``bids`` - tidy bid table (``bids_table(bids)`` makes the app/CSV table).
* ``settlement`` (also ``hourly_settlement``) - hourly settlement with actuals (only if
  ``settle``): cleared charge, actual charge/discharge, charge level, shortage, surplus,
  day-ahead / imbalance / wear cost in EUR and CHF.
* ``summary`` - one dict with the day's totals (see ``_day_summary``), ``soc_end_mwh``,
  ``decision`` (the DecisionParams used).

``run_backtest(start, end, strategies=None, battery=None, decision=None, ...)`` returns
``(daily, summary)`` (+ hourly settlement with ``keep_hourly``). ``tuned_decision()`` returns
the decision rules chosen in ``reports/decision_tuning.csv``. ``load_forecasts()`` returns
the forecast table per (delivery_date, block).
"""
from __future__ import annotations

import argparse
import bisect
import datetime as dt
import os
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, fields, replace
from functools import lru_cache
import multiprocessing as mp

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.optimize import Bounds, LinearConstraint, milp

from src.config import ROOT, load_config
from src.decision.bids import (
    add_protection,
    bids_from_hourly_plan,
    block_hour_shares,
    charge_limit_prices,
    hourly_plan,
)
from src.optimisation.battery_lp import BatteryParams, label_option, solve_battery_plan

REPORTS = ROOT / "reports"
FIGURES = REPORTS / "figures"
PRED_FILES = {
    "demand": REPORTS / "predictions_demand.parquet",
    "price": REPORTS / "predictions_price.parquet",
}
TUNING_FILE = REPORTS / "decision_tuning.csv"
TOL = 1e-6
SOC_TOL = 1e-6

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------
# demand / price: which forecast is used ("naive", "ml", "actual", "custom" = given by the
# caller). battery: does the strategy use the battery. policy: which decision rules
#   tuned         = the rules chosen in reports/decision_tuning.csv (or the ``decision`` argument)
#   default       = config.yaml defaults (plain block plan)
#   oracle_block  = perfect foresight with the same 4-hour block rules (no limits, no margin)
#   oracle_hourly = the CEILING: one hourly perfect-foresight plan over the whole period
#   given         = exactly the ``decision`` argument (sensitivity runs)
STRATEGIES = {
    "baseline_naive_no_battery": dict(demand="naive", price=None, battery=False, policy=None),
    "ml_no_battery": dict(demand="ml", price=None, battery=False, policy=None),
    "naive_battery": dict(demand="naive", price="naive", battery=True, policy="tuned"),
    "ml_battery": dict(demand="ml", price="ml", battery=True, policy="tuned"),
    "ml_battery_block_default": dict(demand="ml", price="ml", battery=True, policy="default"),
    "perfect_foresight_battery": dict(demand="actual", price="actual", battery=True, policy="oracle_block"),
    "perfect_foresight_hourly_battery": dict(demand="actual", price="actual", battery=True, policy="oracle_hourly"),
    "perfect_demand_no_battery": dict(demand="actual", price=None, battery=False, policy=None),
}
MAIN_STRATEGIES = list(STRATEGIES)
BASELINE = "baseline_naive_no_battery"
PRODUCT = "ml_battery"
PRODUCT_DEFAULT = "ml_battery_block_default"
BLOCK_ORACLE = "perfect_foresight_battery"
CEILING = "perfect_foresight_hourly_battery"
PERFECT_NO_BATTERY = "perfect_demand_no_battery"
# battery strategy -> the strategy with the same demand forecast but no battery
NO_BATTERY_PAIR = {
    "naive_battery": BASELINE,
    PRODUCT: "ml_no_battery",
    PRODUCT_DEFAULT: "ml_no_battery",
    BLOCK_ORACLE: PERFECT_NO_BATTERY,
    CEILING: PERFECT_NO_BATTERY,
}
LABELS = {
    BASELINE: "1 Baseline: naive, no battery",
    "ml_no_battery": "2 ML demand, no battery",
    "naive_battery": "3 Naive + battery",
    PRODUCT: "4 ML + battery (product, tuned)",
    PRODUCT_DEFAULT: "4b ML + battery, block plan, defaults",
    BLOCK_ORACLE: "5 Perfect foresight, same 4-hour block rules",
    CEILING: "6 Perfect foresight, hourly (ceiling)",
    PERFECT_NO_BATTERY: "7 Perfect demand, no battery",
}


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DecisionParams:
    """Decision rules on top of the optimiser (all chosen on pre-October data only).

    plan_resolution : "block" = the optimiser plans the 6 block forecasts (hourly bids =
        block plan spread over the hours); "hourly_shape" = the 6 block price forecasts are
        turned into 23/24/25 hourly forecasts by adding the typical within-block hourly
        price shape of the last ``shape_days`` days (known at forecast time), hourly demand =
        block forecast x last week's hourly shape; the optimiser plans the hours.
    shape_days : number of past days for the hourly price shape.
    shape_daytype : True = use only past days of the same day type (workday vs
        weekend/holiday) for the shape.
    charge_limit_factor : limit = expected discharge price x factor - wear cost.
    use_limit : False = charge bids are price-independent (no limit).
    limit_rule : "factor" or "quantile" (limit additionally capped at the q90 price forecast).
    min_spread_eur_mwh : extra margin (EUR per MWh discharged) the expected price spread
        must cover before the battery cycles. It is added to the wear cost in the PLAN only
        (the real wear cost is still used for the limit price and the bill).
    protect : "none" or "at_risk_bid" (see ``src.decision.bids.add_protection``).
    """

    plan_resolution: str = "block"
    shape_days: int = 7
    shape_daytype: bool = False
    charge_limit_factor: float = 0.9
    use_limit: bool = True
    limit_rule: str = "factor"
    min_spread_eur_mwh: float = 0.0
    protect: str = "none"

    def __post_init__(self):
        if self.plan_resolution not in ("block", "hourly_shape"):
            raise ValueError(f"plan_resolution must be 'block' or 'hourly_shape', not {self.plan_resolution!r}")
        if self.limit_rule not in ("factor", "quantile"):
            raise ValueError(f"limit_rule must be 'factor' or 'quantile', not {self.limit_rule!r}")
        if self.protect not in ("none", "at_risk_bid"):
            raise ValueError(f"protect must be 'none' or 'at_risk_bid', not {self.protect!r}")

    @classmethod
    def from_config(cls, **overrides) -> "DecisionParams":
        b = load_config().get("bidding", {})
        kw = {}
        for f in fields(cls):
            if f.name in b:
                kw[f.name] = type(f.default)(b[f.name]) if not isinstance(f.default, bool) else bool(b[f.name])
        return replace(cls(**kw), **overrides)

    @property
    def limit_label(self) -> str:
        if not self.use_limit:
            return "none"
        return f"{self.charge_limit_factor:g}" + (" & q90" if self.limit_rule == "quantile" else "")

    def describe(self) -> str:
        res = self.plan_resolution if self.plan_resolution == "block" else (
            f"hourly_shape({self.shape_days}d{', same day type' if self.shape_daytype else ''})")
        return (f"{res}, limit {self.limit_label}, margin {self.min_spread_eur_mwh:g} EUR/MWh, "
                f"protect {self.protect}")


ORACLE_DECISION = DecisionParams(plan_resolution="block", use_limit=False, min_spread_eur_mwh=0.0, protect="none")


@dataclass(frozen=True)
class ImbalanceParams:
    """Imbalance prices relative to the actual day-ahead price p of the hour.

    Shortage (city used more than we had): we pay ``p + (shortage_factor - 1) * |p|`` per MWh.
    Surplus (we had more than the city used): we receive ``p - (1 - surplus_factor) * |p|``.
    With |p| the penalty hurts also when p is negative.
    """

    shortage_factor: float = 1.2
    surplus_factor: float = 0.8

    @classmethod
    def from_config(cls, **overrides) -> "ImbalanceParams":
        c = load_config().get("imbalance", {})
        base = cls(
            shortage_factor=float(c.get("shortage_price_factor", 1.2)),
            surplus_factor=float(c.get("surplus_price_factor", 0.8)),
        )
        return replace(base, **overrides)


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
def _to_date(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s.astype(str)).dt.date


def _as_date(d) -> dt.date:
    return pd.Timestamp(str(d)).date()


@lru_cache(maxsize=1)
def load_data() -> dict:
    """Read the feature table (block targets, naive lags) and the hourly actuals once.

    Returns a dict with ``blocks`` (DataFrame per date, 6 rows), ``hours`` (DataFrame per
    date, 23/24/25 rows), ``dates`` (sorted dates with hourly data), ``daytype`` (date ->
    "workday" | "free") and ``price_dev`` (date -> {local hour: hourly price minus its block
    mean}) for the hourly price shape.
    """
    cols = [
        "delivery_date", "block", "hours_in_block", "demand_mw", "price_eur_mwh",
        "demand_lag_7d_same_block", "price_lag_7d_same_block",
        "demand_mean_same_block_same_weekday_4w", "price_lag_1d_same_block", "actual_eurchf",
        "is_weekend", "is_holiday",
    ]
    feats = pd.read_parquet(ROOT / load_config()["paths"]["features"], columns=cols)
    feats["delivery_date"] = _to_date(feats["delivery_date"])
    feats = feats.sort_values(["delivery_date", "block"])
    hourly = pd.read_parquet(ROOT / load_config()["paths"]["processed"] / "hourly_actuals.parquet")
    hourly["delivery_date"] = _to_date(hourly["delivery_date"])
    hourly = hourly.sort_values("timestamp_utc").reset_index(drop=True)
    hourly["price_dev"] = hourly["price_eur_mwh"] - hourly.groupby(["delivery_date", "block"])["price_eur_mwh"].transform("mean")
    dev = hourly.groupby(["delivery_date", "hour_local"])["price_dev"].mean()
    price_dev = {d: g.droplevel(0).to_dict() for d, g in dev.groupby(level=0)}
    free = feats.groupby("delivery_date")[["is_weekend", "is_holiday"]].max()
    daytype = {d: ("free" if (bool(r.is_weekend) or bool(r.is_holiday)) else "workday") for d, r in free.iterrows()}
    hours = {d: g.drop(columns="price_dev").reset_index(drop=True) for d, g in hourly.groupby("delivery_date")}
    return {
        "features": feats,
        "blocks": {d: g.reset_index(drop=True) for d, g in feats.groupby("delivery_date")},
        "hours": hours,
        "dates": sorted(hours),
        "daytype": daytype,
        "price_dev": price_dev,
    }


def expected_hours(d) -> int:
    """Number of hours of a local delivery day: 23 (spring DST), 25 (autumn DST) or 24."""
    tz = load_config()["timezone"]
    t0 = pd.Timestamp(str(_as_date(d))).tz_localize(tz)
    t1 = (pd.Timestamp(str(_as_date(d))) + pd.Timedelta(days=1)).tz_localize(tz)
    return int(round((t1 - t0).total_seconds() / 3600))


def _where(hrs: pd.DataFrame, i: int) -> str:
    if "local_time" in hrs:
        return f"{pd.Timestamp(hrs['local_time'].iloc[i]):%Y-%m-%d %H:%M%z}"
    return f"hour {i}"


def day_hours(d, need_actuals: bool = True) -> pd.DataFrame:
    """Hourly rows of a delivery day, validated.

    Raises KeyError if the day is missing, ValueError if the number of hours is not the
    day's 23/24/25, if the hours are not consecutive, or (``need_actuals``) if an actual
    price, demand or EUR/CHF value is missing or not finite (the error names the hour).
    """
    d = _as_date(d)
    hrs = load_data()["hours"].get(d)
    if hrs is None:
        raise KeyError(f"no hourly data for delivery date {d}")
    n = expected_hours(d)
    if len(hrs) != n:
        raise ValueError(f"{d}: {len(hrs)} hourly rows, expected {n} (23/24/25 hours on DST days)")
    steps = pd.to_datetime(hrs["timestamp_utc"]).diff().dropna()
    if (steps != pd.Timedelta(hours=1)).any():
        raise ValueError(f"{d}: hourly timestamps are not consecutive")
    if need_actuals:
        for col, what in [("price_eur_mwh", "day-ahead price"), ("demand_mw", "demand"), ("eurchf", "EUR/CHF rate")]:
            v = pd.to_numeric(hrs[col], errors="coerce").to_numpy(float)
            bad = np.where(~np.isfinite(v))[0]
            if len(bad):
                raise ValueError(f"{_where(hrs, bad[0])}: actual {what} is missing or not finite")
    return hrs


def _periods_cfg() -> dict:
    p = load_config()["periods"]
    return {**p, "rolling_start": p.get("rolling_start", "2025-10-01")}


def split_of(d: dt.date) -> str:
    """Name of the evaluation period of a date when no prediction file says otherwise."""
    p = _periods_cfg()
    s = str(d)
    if p["val_start"] <= s <= p["val_end"]:
        return "val"
    if p["test_start"] <= s <= p["test_end"]:
        return "test"
    if p["rolling_start"] <= s <= p["train_end"]:
        return "rolling"
    return "other"


def ml_predictions_available() -> bool:
    return all(f.exists() for f in PRED_FILES.values())


@lru_cache(maxsize=2)
def load_forecasts(require_ml: bool = False) -> pd.DataFrame:
    """Demand and price forecasts per (delivery_date, block), as known at forecast time.

    Columns: ``delivery_date, block, split, demand_naive_mw, demand_ml_mw,
    price_naive_eur_mwh, price_ml_eur_mwh, price_q10_eur_mwh, price_q90_eur_mwh,
    demand_source, price_source``.

    * naive = same block 7 days earlier (``*_lag_7d_same_block``, or ``pred_naive``).
    * ml = ``pred_best`` from ``reports/predictions_<target>.parquet`` when the file exists.
      If it does not exist, a clearly labelled STAND-IN is used (source = "standin"):
      demand = mean of the same block on the same weekday over the last 4 weeks,
      price = same block on day D (``price_lag_1d_same_block``, known since D-1's
      auction). Both use only information known at forecast time, but they are NOT the
      project's ML models.
    * q10/q90 = ``pred_q10``/``pred_q90`` of the price file if present (else NaN).
    * ``require_ml=True`` raises an error when a prediction file is missing.
    """
    missing = [k for k, f in PRED_FILES.items() if not f.exists()]
    if require_ml and missing:
        raise FileNotFoundError(
            f"--require-ml: ML prediction files missing for {missing}: "
            + ", ".join(str(PRED_FILES[k]) for k in missing)
        )
    f = load_data()["features"]
    out = pd.DataFrame({
        "delivery_date": f["delivery_date"].to_numpy(),
        "block": f["block"].to_numpy(),
        "demand_naive_mw": f["demand_lag_7d_same_block"].to_numpy(),
        "price_naive_eur_mwh": f["price_lag_7d_same_block"].to_numpy(),
        "demand_ml_mw": f["demand_mean_same_block_same_weekday_4w"].to_numpy(),
        "price_ml_eur_mwh": f["price_lag_1d_same_block"].to_numpy(),
        "price_q10_eur_mwh": np.nan,
        "price_q90_eur_mwh": np.nan,
    })
    out["demand_source"] = "standin"
    out["price_source"] = "standin"
    out["split"] = [split_of(d) for d in out["delivery_date"]]
    split_from_file = None
    for target in ["demand", "price"]:
        if target in missing:
            continue
        p = pd.read_parquet(PRED_FILES[target])
        p["delivery_date"] = _to_date(p["delivery_date"])
        p = p.drop_duplicates(["delivery_date", "block"], keep="last")
        col_ml = "demand_ml_mw" if target == "demand" else "price_ml_eur_mwh"
        col_naive = "demand_naive_mw" if target == "demand" else "price_naive_eur_mwh"
        extra = [c for c in ["pred_q10", "pred_q90"] if c in p] if target == "price" else []
        m = out[["delivery_date", "block"]].merge(
            p[["delivery_date", "block", "split", "pred_best", "pred_naive"] + extra], how="left",
            on=["delivery_date", "block"])
        # Only dates covered by the prediction file have an ML forecast. Outside them the
        # ML forecast is missing (no silent stand-in mixing).
        out[col_ml] = m["pred_best"].to_numpy()
        out[col_naive] = np.where(m["pred_naive"].notna(), m["pred_naive"], out[col_naive])
        out[f"{target}_source"] = np.where(m["pred_best"].notna(), "ml", "missing")
        for c in extra:
            out[f"price_{c[5:]}_eur_mwh"] = m[c].to_numpy()
        split_from_file = m["split"] if split_from_file is None else split_from_file.fillna(m["split"])
    if split_from_file is not None:
        out["split"] = np.where(split_from_file.notna(), split_from_file, out["split"])
    return out


@lru_cache(maxsize=2)
def _forecast_index(require_ml: bool = False) -> dict:
    fc = load_forecasts(require_ml)
    return {d: g.sort_values("block").reset_index(drop=True) for d, g in fc.groupby("delivery_date")}


def forecast_sources() -> dict:
    """{'demand': 'ml' | 'standin', 'price': 'ml' | 'standin'} (which file exists)."""
    return {k: ("ml" if f.exists() else "standin") for k, f in PRED_FILES.items()}


def forecast_source() -> str:
    """'ml' if both real prediction files are used, else a text that says stand-in."""
    s = forecast_sources()
    if all(v == "ml" for v in s.values()):
        return "ml"
    have = [k for k, v in s.items() if v == "ml"]
    return "standin" if not have else f"mixed (ml for {have}, stand-in for the rest)"


def source_text() -> str:
    """Plain text for notes and figure titles."""
    s = forecast_sources()
    dem = "ML (pred_best)" if s["demand"] == "ml" else "STAND-IN (4-week same-weekday block mean)"
    pri = "ML (pred_best)" if s["price"] == "ml" else "STAND-IN (same block on day D)"
    return f"demand forecast: {dem}; price forecast: {pri}"


# ---------------------------------------------------------------------------
# Hourly price shape (decision option "hourly_shape")
# ---------------------------------------------------------------------------
@lru_cache(maxsize=8192)
def price_shape(delivery_date, days: int = 7, same_daytype: bool = False) -> tuple:
    """Typical within-block hourly price shape known at forecast time.

    For delivery day T, the reference days are the last ``days`` days STRICTLY before T
    (T-1 = day D, whose prices are known since D-1's auction). With ``same_daytype`` only
    days of the same type (workday / weekend+holiday) within the last 8 weeks are used.
    Shape of local hour h = mean over the reference days of (hourly price - mean price of
    its block that day). Returns a tuple of (hour, shape) pairs; empty if no reference.
    """
    data = load_data()
    d = _as_date(delivery_date)
    dates = data["dates"]
    i = bisect.bisect_left(dates, d)
    ref = []
    for x in reversed(dates[:i]):
        if (d - x).days > (56 if same_daytype else days + 7):
            break
        if same_daytype and data["daytype"].get(x) != data["daytype"].get(d):
            continue
        if x in data["price_dev"]:
            ref.append(x)
        if len(ref) >= days:
            break
    assert all(x < d for x in ref)
    if not ref:
        return tuple()
    s = pd.DataFrame([data["price_dev"][x] for x in ref]).mean(axis=0)
    return tuple((int(h), float(v)) for h, v in s.items() if np.isfinite(v))


def hourly_price_forecast(price_blk, hours: pd.DataFrame, shape: tuple) -> np.ndarray:
    """Block price forecast + within-block shape, re-centred so that every block keeps its
    forecast mean. ``hours`` needs ``block`` and ``hour_local`` (23/24/25 rows)."""
    sh = dict(shape)
    dev = np.array([sh.get(int(h), 0.0) for h in hours["hour_local"]], float)
    blk = hours["block"].to_numpy(int)
    out = np.asarray(price_blk, float)[blk].copy()
    for b in np.unique(blk):
        m = blk == b
        out[m] += dev[m] - dev[m].mean()
    return out


# ---------------------------------------------------------------------------
# Settlement of one day
# ---------------------------------------------------------------------------
def settle_hours(
    hp: pd.DataFrame,
    actual_demand_mwh,
    actual_price_eur_mwh,
    eurchf,
    battery: BatteryParams,
    soc_start_mwh: float,
    imbalance: ImbalanceParams | None = None,
) -> tuple[pd.DataFrame, float]:
    """Settle one day hour by hour with the actual prices and demand.

    ``hp`` needs the columns ``demand_bid_mwh, charge_bid_mwh, charge_limit_eur_mwh``
    (NaN = price-independent) and ``planned_discharge_mwh``. Every hour is 1 h long.

    Imbalance price (p = actual day-ahead price of the hour):
    shortage costs ``p + (shortage_factor - 1)|p|`` per MWh, surplus earns
    ``p - (1 - surplus_factor)|p|`` per MWh.

    Raises ValueError (naming the hour) if an actual value or a bid is missing / not finite.
    Returns the hourly settlement table and the actual charge level at the end of the day.
    Energy conservation and charge-level limits are asserted for every hour.
    """
    imb = imbalance or ImbalanceParams.from_config()
    n = len(hp)
    arrays = {}
    for key, vals, what in [("d", actual_demand_mwh, "demand"), ("p", actual_price_eur_mwh, "day-ahead price"),
                            ("fx", eurchf, "EUR/CHF rate")]:
        v = pd.to_numeric(pd.Series(np.asarray(vals).ravel()), errors="coerce").to_numpy(float)
        if len(v) != n:
            raise ValueError(f"actual {what}: {len(v)} values for {n} hours")
        bad = np.where(~np.isfinite(v))[0]
        if len(bad):
            raise ValueError(f"{_where(hp, bad[0])}: actual {what} is missing or not finite")
        arrays[key] = v
    d_act, p, fx = arrays["d"], arrays["p"], arrays["fx"]
    q = hp["demand_bid_mwh"].to_numpy(float)
    cb = hp["charge_bid_mwh"].to_numpy(float)
    lim = hp["charge_limit_eur_mwh"].to_numpy(float)
    dis_plan = hp["planned_discharge_mwh"].to_numpy(float)
    for v, what in [(q, "demand bid"), (cb, "charge bid"), (dis_plan, "planned discharge")]:
        bad = np.where(~np.isfinite(v))[0]
        if len(bad):
            raise ValueError(f"{_where(hp, bad[0])}: {what} is not finite")
    eta_c, eta_d = battery.eta_charge, battery.eta_discharge

    cleared = np.zeros(n)
    stored = np.zeros(n)     # energy taken from the grid into the battery
    overflow = np.zeros(n)   # cleared charge energy that did not fit -> goes to the city
    dis = np.zeros(n)
    soc_after = np.zeros(n)
    soc = float(soc_start_mwh)
    if not (battery.soc_min - SOC_TOL <= soc <= battery.soc_max + SOC_TOL):
        raise ValueError(f"start charge level {soc:.6f} MWh is outside {battery.soc_min:.2f}-{battery.soc_max:.2f} MWh")
    soc = min(max(soc, battery.soc_min), battery.soc_max)
    for h in range(n):
        if cb[h] > TOL and (np.isnan(lim[h]) or p[h] <= lim[h] + 1e-9):
            cleared[h] = cb[h]
        room = max(battery.soc_max - soc, 0.0) / eta_c
        stored[h] = min(cleared[h], room, battery.power_mw)
        if cleared[h] - stored[h] < 1e-7:   # numerical dust: keep it in the battery accounting
            stored[h] = cleared[h] if cleared[h] <= battery.power_mw else stored[h]
        overflow[h] = cleared[h] - stored[h]
        soc += eta_c * stored[h]
        can_give = max(soc - battery.soc_min, 0.0) * eta_d
        dis[h] = min(dis_plan[h], can_give, battery.power_mw)
        if dis[h] < TOL:
            dis[h] = 0.0
        soc -= dis[h] / eta_d
        # charge level must stay inside the limits (tiny rounding is clipped)
        assert battery.soc_min - SOC_TOL <= soc <= battery.soc_max + SOC_TOL, f"charge level {soc} out of limits"
        soc = min(max(soc, battery.soc_min), battery.soc_max)
        soc_after[h] = soc
        assert not (stored[h] > TOL and dis[h] > TOL), "charge and discharge in the same hour"

    available = q + overflow + dis
    gap = d_act - available
    shortage = np.maximum(gap, 0.0)
    surplus = np.maximum(-gap, 0.0)
    # energy conservation: bought + discharged + shortage - surplus = demand + stored
    lhs = q + cleared + dis + shortage - surplus
    rhs = d_act + stored
    assert np.allclose(lhs, rhs, atol=1e-6), "energy conservation violated"

    da_cost = (q + cleared) * p
    short_price = p + (imb.shortage_factor - 1.0) * np.abs(p)
    surplus_price = p - (1.0 - imb.surplus_factor) * np.abs(p)
    imb_cost = shortage * short_price - surplus * surplus_price
    penalty = shortage * (imb.shortage_factor - 1.0) * np.abs(p) + surplus * (1.0 - imb.surplus_factor) * np.abs(p)
    wear = battery.wear_cost_eur_per_mwh * dis
    total = da_cost + imb_cost + wear

    out = hp.copy().reset_index(drop=True)
    out["actual_demand_mwh"] = d_act
    out["actual_price_eur_mwh"] = p
    out["eurchf"] = fx
    out["charge_cleared_mwh"] = cleared
    out["charged_mwh"] = stored
    out["charge_overflow_mwh"] = overflow
    out["discharged_mwh"] = dis
    out["discharge_not_delivered_mwh"] = dis_plan - dis
    out["soc_end_mwh"] = soc_after
    out["available_mwh"] = available
    out["shortage_mwh"] = shortage
    out["surplus_mwh"] = surplus
    out["da_cost_eur"] = da_cost
    out["imbalance_cost_eur"] = imb_cost
    out["imbalance_penalty_eur"] = penalty
    out["wear_cost_eur"] = wear
    out["total_cost_eur"] = total
    out["total_cost_chf"] = total * fx
    return out, soc


def carry_soc(soc: float, battery: BatteryParams) -> float:
    """Charge level handed to the next day: tiny numerical drift is clipped, anything
    larger is a bug (AssertionError)."""
    assert np.isfinite(soc), "carried charge level is not finite"
    assert battery.soc_min - SOC_TOL <= soc <= battery.soc_max + SOC_TOL, (
        f"carried charge level {soc:.6f} MWh outside {battery.soc_min:.2f}-{battery.soc_max:.2f}")
    return float(min(max(soc, battery.soc_min), battery.soc_max))


# ---------------------------------------------------------------------------
# One day: forecast -> plan -> bids -> settlement
# ---------------------------------------------------------------------------
def _no_battery_plan(demand_mwh, price, hours) -> pd.DataFrame:
    """Plan for strategies without battery: buy exactly the forecast demand."""
    d = np.asarray(demand_mwh, float)
    plan = pd.DataFrame({
        "hours": np.asarray(hours, float), "demand_mwh": d,
        "price_eur_mwh": np.asarray(price, float), "buy_mwh": d,
        "charge_mwh": 0.0, "discharge_mwh": 0.0, "sell_mwh": 0.0, "soc_mwh": np.nan,
        "option": "buy",
    })
    plan.attrs.update(status="no battery", cycles=0.0)
    return plan


def _solve(demand, price, hours, battery_plan, soc_start, allow_sell=False):
    """Solve the MILP; end-of-day target = configured start level.

    Only if that target is explicitly INFEASIBLE (e.g. a very small battery that cannot
    get back to the target in one day) the target is relaxed to "end where you started";
    every other solver failure is raised. Returns (plan, relaxed_flag).
    """
    try:
        plan = solve_battery_plan(demand, price, hours=hours, battery=battery_plan, allow_sell=allow_sell,
                                  soc_start_mwh=soc_start, soc_end_mwh=battery_plan.soc_start)
        return plan, False
    except RuntimeError as e:
        if "infeasible" not in str(e).lower():
            raise
        plan = solve_battery_plan(demand, price, hours=hours, battery=battery_plan, allow_sell=allow_sell,
                                  soc_start_mwh=soc_start, soc_end_mwh=soc_start)
        return plan, True


def _schedule_plan(demand, price, ch, dis, soc0, battery) -> pd.DataFrame:
    """Hourly plan from a given charge/discharge schedule (used by the period ceiling)."""
    d, ch, dis = np.asarray(demand, float), np.asarray(ch, float), np.asarray(dis, float)
    soc = soc0 + np.cumsum(battery.eta_charge * ch - dis / battery.eta_discharge)
    assert (soc >= battery.soc_min - 1e-5).all() and (soc <= battery.soc_max + 1e-5).all()
    soc = np.clip(soc, battery.soc_min, battery.soc_max)
    plan = pd.DataFrame({"hours": 1.0, "demand_mwh": d, "price_eur_mwh": np.asarray(price, float),
                         "buy_mwh": d + ch - dis, "charge_mwh": ch, "discharge_mwh": dis, "sell_mwh": 0.0,
                         "soc_mwh": soc})
    plan["option"] = [label_option(r.buy_mwh, r.charge_mwh, r.discharge_mwh) for r in plan.itertuples()]
    plan.attrs.update(status="Optimal (period ceiling)")
    return plan


def _block_option(buy, charge, discharge) -> str:
    """Block label when an hourly plan both charges and discharges inside one block: the
    net direction decides."""
    if charge > 1e-3 and discharge > 1e-3:
        return "buy_and_store" if charge >= discharge else "use_storage_and_buy"
    return label_option(buy, charge, discharge)


def _block_view(plan_p: pd.DataFrame, hours: pd.DataFrame, blk: pd.DataFrame, price_blk, limits) -> pd.DataFrame:
    """Aggregate an hourly plan back to the 6 blocks (for the decision table)."""
    b_of = hours["block"].to_numpy(int)
    rows = []
    lim = np.full(len(plan_p), np.nan) if limits is None else np.asarray(limits, float)
    for b in range(len(blk)):
        m = b_of == b
        g = plan_p.loc[m]
        ch = float(g["charge_mwh"].sum())
        w = g["charge_mwh"].to_numpy(float)
        lm = lim[m]
        ok = (w > 1e-9) & np.isfinite(lm)
        rows.append({
            "period": b, "block": b, "hours": float(m.sum()),
            "demand_mwh": float(g["demand_mwh"].sum()), "price_eur_mwh": float(np.asarray(price_blk, float)[b]),
            "buy_mwh": float(g["buy_mwh"].sum()), "charge_mwh": ch,
            "discharge_mwh": float(g["discharge_mwh"].sum()), "sell_mwh": float(g["sell_mwh"].sum()),
            "soc_mwh": float(g["soc_mwh"].iloc[-1]) if len(g) else np.nan,
            "charge_limit_eur_mwh": float((w[ok] * lm[ok]).sum() / w[ok].sum()) if ok.any() else np.nan,
        })
    out = pd.DataFrame(rows)
    out["option"] = [_block_option(r.buy_mwh, r.charge_mwh, r.discharge_mwh) for r in out.itertuples()]
    out = out[["period", "block", "hours", "demand_mwh", "price_eur_mwh", "buy_mwh", "charge_mwh",
               "discharge_mwh", "sell_mwh", "soc_mwh", "option", "charge_limit_eur_mwh"]]
    out.attrs.update(plan_p.attrs)
    return out


def _spec(strategy) -> tuple[dict, str]:
    spec = dict(STRATEGIES[strategy]) if isinstance(strategy, str) else dict(strategy)
    name = strategy if isinstance(strategy, str) else spec.get("name", "custom")
    if "policy" not in spec:  # older dict format
        if spec.get("hourly"):
            spec["policy"] = "oracle_hourly"
        elif spec.get("price") == "actual":
            spec["policy"] = "oracle_block"
        else:
            spec["policy"] = "given" if spec.get("battery") else None
    return spec, name


def resolve_decision(strategy, decision: DecisionParams | None = None) -> DecisionParams:
    """Decision rules a strategy really uses (oracles: none; 4b: config defaults)."""
    spec, _ = _spec(strategy)
    pol = spec.get("policy")
    if pol in ("oracle_block", "oracle_hourly"):
        return ORACLE_DECISION
    if pol == "default":
        return DecisionParams.from_config()
    return decision if decision is not None else tuned_decision()


def plan_day(
    delivery_date,
    strategy="ml_battery",
    battery: BatteryParams | None = None,
    soc_start_mwh: float | None = None,
    decision: DecisionParams | None = None,
    imbalance: ImbalanceParams | None = None,
    price_override=None,
    demand_override_mw=None,
    require_ml: bool = False,
    settle: bool = True,
    allow_sell: bool | None = None,
    fixed_schedule=None,
) -> dict:
    """Plan and (optionally) settle one delivery day. See the module docstring for the
    returned dict.

    Parameters
    ----------
    delivery_date : the day to plan (date or "YYYY-MM-DD").
    strategy : a name from ``STRATEGIES`` or a dict with the same keys.
    battery : battery data (default config.yaml).
    soc_start_mwh : charge level at the start of the day (default: config start level).
    decision : decision rules for "tuned"/"given" strategies (default: ``tuned_decision()``).
    imbalance : imbalance prices (default config.yaml).
    price_override : 6 block prices (EUR/MWh) to plan with instead of the forecast
        (strategy price "custom"); used by the price-error sensitivity and the app.
    demand_override_mw : 6 block demand forecasts (mean MW) instead of the forecast.
    settle : False = skip the settlement (e.g. for the real "tomorrow" without actuals).
    allow_sell : allow selling back to the market (default config ``battery.allow_sell``).
    fixed_schedule : (charge, discharge) per hour; used internally by the period ceiling.
    """
    d = _as_date(delivery_date)
    spec, name = _spec(strategy)
    battery = battery or BatteryParams.from_config()
    dec = resolve_decision(spec, decision)
    policy = spec.get("policy")
    oracle = policy in ("oracle_block", "oracle_hourly")
    if allow_sell is None:
        allow_sell = bool(load_config()["battery"].get("allow_sell", False))
    data = load_data()
    if d not in data["blocks"]:
        raise KeyError(f"no data for delivery date {d}")
    blk = data["blocks"][d]
    uses_actual = spec["demand"] == "actual" or spec.get("price") == "actual"
    hrs = day_hours(d, need_actuals=settle or uses_actual)
    fc = _forecast_index(require_ml).get(d)
    soc0 = battery.soc_start if soc_start_mwh is None else float(soc_start_mwh)
    h_blk = blk["hours_in_block"].to_numpy(float)
    if len(blk) != 6 or abs(h_blk.sum() - len(hrs)) > 1e-9:
        raise ValueError(f"{d}: block table ({len(blk)} blocks, {h_blk.sum():g} h) does not match {len(hrs)} hours")

    def _fc(col):
        if fc is None:
            raise ValueError(f"{d} {name}: no forecast row for this date")
        return fc[col].to_numpy(float)

    # --- demand forecast per block (mean MW) ---
    if demand_override_mw is not None:
        dem_mw = np.asarray(demand_override_mw, float)
    elif spec["demand"] == "actual":
        dem_mw = blk["demand_mw"].to_numpy(float)
    else:
        dem_mw = _fc(f"demand_{spec['demand']}_mw")
    # --- price forecast per block ---
    q90_blk = None
    if price_override is not None:
        price_blk = np.asarray(price_override, float)
    elif spec.get("price") is None:
        price_blk = np.full(len(blk), np.nan)
    elif spec["price"] == "actual":
        price_blk = blk["price_eur_mwh"].to_numpy(float)
    else:
        price_blk = _fc(f"price_{spec['price']}_eur_mwh")
        if spec["price"] == "ml" and fc is not None:
            q90_blk = fc["price_q90_eur_mwh"].to_numpy(float)
    bad = np.where(~np.isfinite(dem_mw))[0]
    if len(bad):
        raise ValueError(f"{d} {name}: demand forecast missing for block {bad[0]} "
                         "(are the ML predictions available for this date?)")
    bad = np.where(~np.isfinite(price_blk))[0]
    if spec["battery"] and len(bad):
        raise ValueError(f"{d} {name}: price forecast missing for block {bad[0]} "
                         "(are the ML predictions available for this date?)")

    # --- hourly forecast need (block forecast x hourly shape) ---
    hours = hrs[["delivery_date", "timestamp_utc", "local_time", "hour_local", "block"]].copy()
    b_of = hours["block"].to_numpy(int)
    shares = np.zeros(len(hours))
    ref_hours = data["hours"].get(d - dt.timedelta(days=7))
    actual_shape = spec["demand"] == "actual" and demand_override_mw is None
    for b in range(len(blk)):
        m = b_of == b
        if actual_shape:
            v = hrs.loc[m, "demand_mw"].to_numpy(float)
            shares[m] = v / v.sum()  # actual shape of the delivery day itself
        else:
            ref = None if ref_hours is None else ref_hours.loc[ref_hours["block"] == b, ["hour_local", "demand_mw"]]
            shares[m] = block_hour_shares(hours.loc[m, "hour_local"].tolist(), ref)
    need_h = (dem_mw * h_blk)[b_of] * shares

    hourly_mode = bool(spec["battery"]) and (policy == "oracle_hourly" or dec.plan_resolution == "hourly_shape")
    if hourly_mode:
        hours["period"] = np.arange(len(hours))
        hours["share"] = 1.0
        per_demand = need_h
        per_hours = np.ones(len(hours))
        if spec.get("price") == "actual" and price_override is None:
            per_price = hrs["price_eur_mwh"].to_numpy(float)
        else:
            per_price = hourly_price_forecast(price_blk, hours, price_shape(d, dec.shape_days, dec.shape_daytype))
        q90 = None if q90_blk is None else hourly_price_forecast(
            q90_blk, hours, price_shape(d, dec.shape_days, dec.shape_daytype))
    else:
        hours["period"] = b_of
        hours["share"] = shares
        per_demand = dem_mw * h_blk
        per_price = price_blk
        per_hours = h_blk
        q90 = q90_blk

    # --- plan ---
    relaxed = False
    if spec["battery"]:
        if fixed_schedule is not None:
            if not hourly_mode:
                raise ValueError("fixed_schedule needs an hourly strategy")
            plan_p = _schedule_plan(per_demand, per_price, fixed_schedule[0], fixed_schedule[1], soc0, battery)
        else:
            margin = 0.0 if oracle else dec.min_spread_eur_mwh
            plan_bat = replace(battery, wear_cost_eur_per_mwh=battery.wear_cost_eur_per_mwh + margin)
            if allow_sell or hourly_mode:
                lp_demand = per_demand
            else:
                # discharge of a block may not exceed what its hours can take:
                # sum over hours of min(forecast need, power). The optimiser enforces
                # discharge <= demand of the period, so we hand it this capped demand and buy
                # the rest of the block (a constant) outside the optimisation.
                cap = np.array([np.minimum(need_h[b_of == b], battery.power_mw).sum() for b in range(len(blk))])
                lp_demand = np.minimum(per_demand, cap)
            plan_p, relaxed = _solve(lp_demand, per_price, per_hours, plan_bat, soc0, allow_sell)
            extra = per_demand - lp_demand
            plan_p["demand_mwh"] = per_demand
            plan_p["buy_mwh"] = plan_p["buy_mwh"] + extra
            plan_p["option"] = [label_option(r.buy_mwh, r.charge_mwh, r.discharge_mwh) for r in plan_p.itertuples()]
        if oracle or not dec.use_limit:
            limits = np.full(len(plan_p), np.nan)  # price-independent charge bids
        else:
            if dec.limit_rule == "quantile" and (q90 is None or not np.isfinite(q90).all()):
                raise ValueError(f"{d}: limit_rule 'quantile' needs pred_q90 in the price predictions")
            limits = charge_limit_prices(plan_p, dec.charge_limit_factor, battery.wear_cost_eur_per_mwh,
                                         price_q90=q90 if dec.limit_rule == "quantile" else None)
        p_ = plan_p["price_eur_mwh"].to_numpy(float)
        cost = float((p_ * (plan_p["buy_mwh"] - plan_p["sell_mwh"])).sum()
                     + battery.wear_cost_eur_per_mwh * plan_p["discharge_mwh"].sum())
        plan_p.attrs.update(cost_eur=cost, cost_no_battery_eur=float((p_ * per_demand).sum()),
                            cycles=float(plan_p["discharge_mwh"].sum() / battery.usable_mwh) if battery.usable_mwh > 0 else 0.0,
                            soc_start_mwh=soc0)
        plan_p.attrs["saving_eur"] = plan_p.attrs["cost_no_battery_eur"] - cost
    else:
        plan_p = _no_battery_plan(per_demand, per_price, per_hours)
        limits = None
    plan_p.attrs["plan_resolution"] = "hourly" if hourly_mode else "block"
    plan_p.insert(0, "period", np.arange(len(plan_p)))
    plan_p.insert(1, "block", hours["block"].to_numpy() if hourly_mode else blk["block"].to_numpy())
    plan_p["charge_limit_eur_mwh"] = np.nan if limits is None else limits

    hp = hourly_plan(plan_p, hours, limits, power_mw=battery.power_mw, cap_by_need=not allow_sell)
    if spec["battery"] and not oracle and dec.protect == "at_risk_bid":
        hp = add_protection(hp, soc0, battery.soc_min, battery.eta_charge, battery.eta_discharge)
    bids = bids_from_hourly_plan(hp)
    plan = _block_view(plan_p, hours, blk, price_blk if np.isfinite(price_blk).all() else
                       blk["price_eur_mwh"].to_numpy(float), limits) if hourly_mode else plan_p
    result = {"plan": plan, "plan_periods": plan_p, "bids": bids, "hourly": hp, "soc_end_mwh": np.nan,
              "summary": None, "settlement": None, "hourly_settlement": None, "decision": dec}
    if not settle:
        return result

    # --- settle with actuals ---
    st, soc_end = settle_hours(hp, hrs["demand_mw"].to_numpy(float), hrs["price_eur_mwh"].to_numpy(float),
                               hrs["eurchf"].to_numpy(float), battery, soc0, imbalance)
    if not spec["battery"]:
        assert st["charged_mwh"].abs().sum() == 0 and st["discharged_mwh"].abs().sum() == 0
    st.insert(0, "strategy", name)
    s = _day_summary(d, name, st, plan_p, per_demand, battery, soc0, soc_end, relaxed, dec if spec["battery"] else None)
    result.update(settlement=st, hourly_settlement=st, summary=s, soc_end_mwh=soc_end)
    return result


def _day_summary(d, name, st, plan_p, per_demand, battery, soc0, soc_end, relaxed, dec) -> dict:
    bid_charge = float(st["charge_bid_mwh"].sum())
    cleared = float(st["charge_cleared_mwh"].sum())
    fx = st["eurchf"].to_numpy()
    return {
        "delivery_date": d,
        "strategy": name,
        "decision": "" if dec is None else dec.describe(),
        "n_hours": int(len(st)),
        "actual_price_mean_eur_mwh": float(st["actual_price_eur_mwh"].mean()),
        "eurchf_mean": float(st["eurchf"].mean()),
        "eta_discharge": battery.eta_discharge,
        "forecast_demand_mwh": float(np.sum(per_demand)),
        "actual_demand_mwh": float(st["actual_demand_mwh"].sum()),
        "demand_bid_mwh": float(st["demand_bid_mwh"].sum()),
        "at_risk_bid_mwh": float(st["at_risk_bid_mwh"].sum()) if "at_risk_bid_mwh" in st else 0.0,
        "charge_bid_mwh": bid_charge,
        "charge_cleared_mwh": cleared,
        "share_charge_cleared": cleared / bid_charge if bid_charge > TOL else np.nan,
        "energy_bought_mwh": float((st["demand_bid_mwh"] + st["charge_cleared_mwh"]).sum()),
        "charged_mwh": float(st["charged_mwh"].sum()),
        "planned_discharge_mwh": float(plan_p["discharge_mwh"].sum()),
        "discharged_mwh": float(st["discharged_mwh"].sum()),
        "discharge_not_delivered_mwh": float(st["discharge_not_delivered_mwh"].sum()),
        "cycles": float(st["discharged_mwh"].sum() / battery.usable_mwh) if battery.usable_mwh > 0 else 0.0,
        "battery_idle": bool(st["charged_mwh"].sum() < 1e-3 and st["discharged_mwh"].sum() < 1e-3),
        "plan_has_discharge": bool(plan_p["discharge_mwh"].sum() > 1e-3),
        "shortage_mwh": float(st["shortage_mwh"].sum()),
        "surplus_mwh": float(st["surplus_mwh"].sum()),
        "soc_start_mwh": soc0,
        "soc_end_mwh": soc_end,
        "soc_target_relaxed": relaxed,
        "da_cost_eur": float(st["da_cost_eur"].sum()),
        "imbalance_cost_eur": float(st["imbalance_cost_eur"].sum()),
        "imbalance_penalty_eur": float(st["imbalance_penalty_eur"].sum()),
        "wear_cost_eur": float(st["wear_cost_eur"].sum()),
        "total_cost_eur": float(st["total_cost_eur"].sum()),
        "da_cost_chf": float((st["da_cost_eur"] * fx).sum()),
        "imbalance_cost_chf": float((st["imbalance_cost_eur"] * fx).sum()),
        "imbalance_penalty_chf": float((st["imbalance_penalty_eur"] * fx).sum()),
        "wear_cost_chf": float((st["wear_cost_eur"] * fx).sum()),
        "total_cost_chf": float((st["total_cost_eur"] * fx).sum()),
    }


# ---------------------------------------------------------------------------
# The ceiling: one hourly perfect-foresight plan over the whole period
# ---------------------------------------------------------------------------
def solve_period_oracle(dates, battery: BatteryParams | None = None, soc_start_mwh: float | None = None) -> dict:
    """Cheapest possible battery schedule over ALL hours of ``dates`` with perfect foresight.

    Constraints: power per hour, charge level limits, at most ``max_cycles_per_day`` per
    delivery day, discharge <= the hour's demand (no selling), and the charge level at the
    END of the period equals the START level (matched opening and closing inventory).
    Charging and discharging in the same hour is forbidden by a yes/no variable in hours
    with a negative price (only there it can pay off); elsewhere such pairs are netted out
    afterwards, which never makes the plan worse. Returns {date: (charge, discharge)} per hour.
    """
    battery = battery or BatteryParams.from_config()
    soc0 = battery.soc_start if soc_start_mwh is None else float(soc_start_mwh)
    frames = [day_hours(d, True) for d in dates]
    dmd = np.concatenate([f["demand_mw"].to_numpy(float) for f in frames])
    p = np.concatenate([f["price_eur_mwh"].to_numpy(float) for f in frames])
    day_idx = np.concatenate([np.full(len(f), i) for i, f in enumerate(frames)])
    n, P = len(p), battery.power_mw
    eta_c, eta_d = battery.eta_charge, battery.eta_discharge
    neg = np.where(p < 0)[0]
    nb = len(neg)
    CH, DIS, SOC = 0, n, 2 * n
    nvar = 3 * n + nb
    c = np.zeros(nvar)
    c[CH:CH + n] = p + 1e-6          # tiny tie-breaker: stay idle when nothing is earned
    c[DIS:DIS + n] = -p + battery.wear_cost_eur_per_mwh
    lb = np.zeros(nvar)
    ub = np.full(nvar, 1.0)
    ub[CH:CH + n] = P
    ub[DIS:DIS + n] = np.minimum(P, dmd)
    lb[SOC:SOC + n], ub[SOC:SOC + n] = battery.soc_min, battery.soc_max
    integrality = np.zeros(nvar)
    integrality[3 * n:] = 1
    r = np.arange(n)
    # soc_t - soc_{t-1} - eta_c ch_t + dis_t / eta_d = 0 (t=0: = soc0)
    A_dyn = sparse.coo_matrix(
        (np.concatenate([np.ones(n), -np.ones(n - 1), -eta_c * np.ones(n), np.ones(n) / eta_d]),
         (np.concatenate([r, r[1:], r, r]), np.concatenate([SOC + r, SOC + r[:-1], CH + r, DIS + r]))),
        shape=(n, nvar))
    rhs = np.zeros(n)
    rhs[0] = soc0
    A_end = sparse.coo_matrix(([1.0], ([0], [SOC + n - 1])), shape=(1, nvar))
    nd = len(frames)
    A_cyc = sparse.coo_matrix((np.ones(n), (day_idx, DIS + r)), shape=(nd, nvar))
    blocks = [A_dyn, A_end, A_cyc]
    lo = [rhs, [soc0], np.full(nd, -np.inf)]
    hi = [rhs, [soc0], np.full(nd, battery.max_cycles_per_day * battery.usable_mwh)]
    if nb:
        k = np.arange(nb)
        A_c = sparse.coo_matrix((np.concatenate([np.ones(nb), -P * np.ones(nb)]),
                                 (np.concatenate([k, k]), np.concatenate([CH + neg, 3 * n + k]))), shape=(nb, nvar))
        A_d = sparse.coo_matrix((np.concatenate([np.ones(nb), P * np.ones(nb)]),
                                 (np.concatenate([k, k]), np.concatenate([DIS + neg, 3 * n + k]))), shape=(nb, nvar))
        blocks += [A_c, A_d]
        lo += [np.full(nb, -np.inf), np.full(nb, -np.inf)]
        hi += [np.zeros(nb), np.full(nb, P)]
    res = milp(c, constraints=LinearConstraint(sparse.vstack(blocks).tocsr(), np.concatenate(lo), np.concatenate(hi)),
               bounds=Bounds(lb, ub), integrality=integrality, options={"mip_rel_gap": 0.0})
    if not res.success:
        raise RuntimeError(f"period ceiling could not be solved: {res.message}")
    ch = np.where(res.x[CH:CH + n] < 1e-7, 0.0, res.x[CH:CH + n])
    dis = np.where(res.x[DIS:DIS + n] < 1e-7, 0.0, res.x[DIS:DIS + n])
    both = (ch > 0) & (dis > 0)
    if both.any():  # net out (keeps the charge level path, never costs more when p >= 0)
        net = eta_c * ch[both] - dis[both] / eta_d
        ch[both] = np.where(net > 0, net / eta_c, 0.0)
        dis[both] = np.where(net < 0, -net * eta_d, 0.0)
    out, i = {}, 0
    for d, f in zip(dates, frames):
        out[_as_date(d)] = (ch[i:i + len(f)].copy(), dis[i:i + len(f)].copy())
        i += len(f)
    return out


# ---------------------------------------------------------------------------
# Many days
# ---------------------------------------------------------------------------
def uses_battery(strategy) -> bool:
    spec, _ = _spec(strategy)
    return bool(spec["battery"])


def run_strategy(dates, strategy, battery=None, decision=None, imbalance=None,
                 price_overrides: dict | None = None, require_ml=False, keep_hourly=False,
                 allow_sell=None, soc_start_mwh=None):
    """Run one strategy day after day, carrying the actual charge level to the next day.

    The charge level at the end of day D is known when day D+1 is planned: the
    auction results of D are known since D-1 and the battery follows only the cleared
    bids (not the demand), so its path is fully known. The ceiling strategy is planned
    once for the whole period (``solve_period_oracle``) and then settled day by day.
    """
    battery = battery or BatteryParams.from_config()
    soc = battery.soc_start if soc_start_mwh is None else float(soc_start_mwh)
    spec, _ = _spec(strategy)
    dec = resolve_decision(spec, decision) if spec["battery"] else decision
    sched = None
    if spec.get("policy") == "oracle_hourly" and price_overrides is None and len(dates):
        sched = solve_period_oracle(dates, battery, soc)
    rows, hourly = [], []
    for d in dates:
        po = None if price_overrides is None else price_overrides[d]
        r = plan_day(d, strategy, battery=battery, soc_start_mwh=soc, decision=dec,
                     imbalance=imbalance, price_override=po, require_ml=require_ml, allow_sell=allow_sell,
                     fixed_schedule=None if sched is None else sched[_as_date(d)])
        if spec["battery"]:
            soc = carry_soc(r["soc_end_mwh"], battery)
        rows.append(r["summary"])
        if keep_hourly:
            hourly.append(r["hourly_settlement"])
    daily = pd.DataFrame(rows)
    return (daily, pd.concat(hourly, ignore_index=True)) if keep_hourly else (daily, None)


def dates_between(start, end) -> list[dt.date]:
    data = load_data()
    s, e = _as_date(start), _as_date(end)
    return [d for d in sorted(data["blocks"]) if s <= d <= e and d in data["hours"]]


def _run_task(kw: dict):
    """Worker entry point for the process pool (must be a top-level function)."""
    kw = dict(kw)
    tag = kw.pop("tag", None)
    daily, hourly = run_strategy(**kw)
    return tag, daily, hourly


def n_workers() -> int:
    env = os.environ.get("BACKTEST_WORKERS")
    if env:
        return max(1, int(env))
    return max(1, min(8, (os.cpu_count() or 2) - 1))


def run_tasks(tasks: list[dict], workers: int | None = None) -> list:
    """Run ``run_strategy`` for many settings, in parallel processes when it pays off.
    Every task is a dict of ``run_strategy`` arguments plus an optional ``tag``. Results
    come back in task order as (tag, daily, hourly)."""
    workers = n_workers() if workers is None else workers
    if workers <= 1 or len(tasks) <= 1:
        return [_run_task(t) for t in tasks]
    with ProcessPoolExecutor(max_workers=min(workers, len(tasks)), mp_context=mp.get_context("spawn")) as ex:
        return list(ex.map(_run_task, tasks))


def run_backtest(start, end, strategies=None, battery=None, decision=None, imbalance=None,
                 require_ml=False, keep_hourly=False, n_boot=1000, workers: int | None = 1):
    """Backtest the strategies from ``start`` to ``end`` (inclusive), every strategy
    starting with the battery at the configured start level.

    Returns ``(daily_df, summary_df)`` (and the hourly settlement as a third element if
    ``keep_hourly``). ``daily_df`` has one row per day x strategy with a ``split`` column;
    ``summary_df`` one row per split x strategy (see ``summarise``).
    """
    strategies = strategies or MAIN_STRATEGIES
    dates = dates_between(start, end)
    fc_split = load_forecasts(require_ml).drop_duplicates("delivery_date").set_index("delivery_date")["split"]
    tasks = [dict(dates=dates, strategy=s, battery=battery, decision=decision, imbalance=imbalance,
                  require_ml=require_ml, keep_hourly=keep_hourly) for s in strategies]
    res = run_tasks(tasks, workers)
    daily = pd.concat([r[1] for r in res], ignore_index=True)
    daily.insert(1, "split", daily["delivery_date"].map(fc_split).fillna("other"))
    summary = summarise(daily, n_boot=n_boot)
    if keep_hourly:
        return daily, summary, pd.concat([r[2] for r in res], ignore_index=True)
    return daily, summary


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------
def bootstrap_sums(x, idx) -> np.ndarray:
    """Sum of ``x`` for every row of the resampling index matrix ``idx`` (draws x days)."""
    x = np.asarray(x, float)
    return x[np.asarray(idx)].sum(axis=1)


def paired_bootstrap_ci(cost_a, cost_b, n_boot: int = 1000, seed: int = 42, shift: float = 0.0,
                        idx=None) -> tuple[float, float]:
    """95 % interval of ``sum(cost_a - cost_b) + shift`` when whole days are resampled
    (the same days for both strategies, i.e. a PAIRED bootstrap). ``shift`` is a constant
    added to every draw (e.g. the end-of-period inventory adjustment). ``idx`` can be given
    explicitly (draws x days) for hand-checked examples."""
    diff = np.asarray(cost_a, float) - np.asarray(cost_b, float)
    if len(diff) == 0 or (idx is None and n_boot <= 0):
        return np.nan, np.nan
    if idx is None:
        idx = np.random.default_rng(seed).integers(0, len(diff), size=(n_boot, len(diff)))
    sums = bootstrap_sums(diff, idx) + shift
    return float(np.percentile(sums, 2.5)), float(np.percentile(sums, 97.5))


def _boot_ci(x: np.ndarray, n_boot: int, seed: int) -> tuple[float, float]:
    """95% interval of the SUM of daily values when whole days are resampled."""
    return paired_bootstrap_ci(x, np.zeros(len(x)), n_boot, seed)


def inventory_value_chf(g: pd.DataFrame) -> tuple[float, float]:
    """Value of the change in stored energy over a period for ONE strategy.

    ``g`` = the strategy's daily rows of the period. Stored energy at the end minus at the
    start (MWh in the battery) is valued at what it can deliver to the city
    (x discharge efficiency) at the period's mean actual day-ahead price, converted with
    the period's mean EUR/CHF. Returns (change in MWh, value in CHF). A strategy that ends
    the period with less energy than it started gets a positive extra cost.
    """
    g = g.sort_values("delivery_date")
    dsoc = float(g["soc_end_mwh"].iloc[-1] - g["soc_start_mwh"].iloc[0])
    w = g["n_hours"].to_numpy(float)
    p_mean = float((g["actual_price_mean_eur_mwh"] * w).sum() / w.sum())
    fx = float((g["eurchf_mean"] * w).sum() / w.sum())
    eta_d = float(g["eta_discharge"].iloc[0])
    return dsoc, dsoc * eta_d * p_mean * fx


def summarise(daily: pd.DataFrame, n_boot: int = 1000, seed: int | None = None) -> pd.DataFrame:
    """One row per split x strategy with totals, savings and the shares of the ceiling.

    Definitions (C = total cost in CHF over the period, "adj" = inventory-adjusted:
    C_adj = C - value of the change in stored energy, see ``inventory_value_chf``):
    * saving_vs_baseline_chf = C1 - C_s (raw), saving_vs_baseline_adj_chf = C1 - C_s,adj
      (with paired day-bootstrap 95 % intervals)
    * pct_perfect_captured = (C1 - C_s,adj) / (C1 - C6,adj)   (6 = hourly ceiling)
    * pct_block_perfect_captured = (C1 - C_s,adj) / (C1 - C5,adj)
    * battery_value_adj_chf = C_pair - C_s,adj, pair = same forecasts without battery
      (3 -> 1, 4/4b -> 2, 5/6 -> 7); pct_battery_value_captured = battery_value / (C7 - C6,adj)
    """
    seed = load_config().get("random_seed", 42) if seed is None else seed
    out = []
    for split, g in daily.groupby("split", sort=False):
        piv = g.pivot_table(index="delivery_date", columns="strategy", values="total_cost_chf")
        tot = g.groupby("strategy")["total_cost_chf"].sum()
        inv = {s: inventory_value_chf(gs) for s, gs in g.groupby("strategy")}
        adj = {s: tot[s] - inv[s][1] for s in tot.index}
        c1 = adj.get(BASELINE, np.nan)
        c5, c6, c7 = adj.get(BLOCK_ORACLE, np.nan), adj.get(CEILING, np.nan), adj.get(PERFECT_NO_BATTERY, np.nan)
        for s, gs in g.groupby("strategy", sort=False):
            r = {"split": split, "strategy": s, "label": LABELS.get(s, s), "days": len(gs),
                 "decision": gs["decision"].iloc[0] if "decision" in gs else ""}
            for c in ["total_cost_eur", "total_cost_chf", "da_cost_chf", "imbalance_cost_chf",
                      "imbalance_penalty_chf", "wear_cost_chf", "energy_bought_mwh", "charged_mwh",
                      "discharged_mwh", "discharge_not_delivered_mwh", "shortage_mwh", "surplus_mwh", "cycles",
                      "at_risk_bid_mwh"]:
                if c in gs:
                    r[c] = float(gs[c].sum())
            r["inventory_change_mwh"], r["inventory_value_chf"] = inv[s]
            r["total_cost_adj_chf"] = adj[s]
            r["days_battery_idle"] = int(gs["battery_idle"].sum())
            bid = gs["charge_bid_mwh"].sum()
            r["share_charge_cleared"] = float(gs["charge_cleared_mwh"].sum() / bid) if bid > TOL else np.nan
            r["saving_vs_baseline_chf"] = tot.get(BASELINE, np.nan) - r["total_cost_chf"]
            r["saving_vs_baseline_adj_chf"] = c1 - adj[s]
            if BASELINE in piv and s in piv:
                ok = piv[BASELINE].notna() & piv[s].notna()
                cb, cs = piv.loc[ok, BASELINE].to_numpy(), piv.loc[ok, s].to_numpy()
                shift = inv[s][1] - inv.get(BASELINE, (0, 0.0))[1]
                r["saving_ci_low_chf"], r["saving_ci_high_chf"] = paired_bootstrap_ci(cb, cs, n_boot, seed)
                r["saving_adj_ci_low_chf"], r["saving_adj_ci_high_chf"] = paired_bootstrap_ci(
                    cb, cs, n_boot, seed, shift=shift)
                r["days_cheaper_than_baseline"] = int(((cb - cs) > 0.005).sum())
            den = c1 - c6
            r["pct_perfect_captured"] = 100 * r["saving_vs_baseline_adj_chf"] / den if abs(den) > 1e-9 else np.nan
            den5 = c1 - c5
            r["pct_block_perfect_captured"] = 100 * r["saving_vs_baseline_adj_chf"] / den5 if abs(den5) > 1e-9 else np.nan
            pair = NO_BATTERY_PAIR.get(s)
            if pair is not None and pair in tot:
                r["battery_value_chf"] = tot[pair] - r["total_cost_chf"]
                r["battery_value_adj_chf"] = adj[pair] - adj[s]
                bden = c7 - c6
                r["pct_battery_value_captured"] = 100 * r["battery_value_adj_chf"] / bden if abs(bden) > 1e-9 else np.nan
            out.append(r)
    res = pd.DataFrame(out)
    order = {s: i for i, s in enumerate(MAIN_STRATEGIES)}
    res["_o"] = res["strategy"].map(order).fillna(99)
    return res.sort_values(["_o"], kind="stable").sort_values("split", key=lambda s: s.map(
        {"test": 0, "val": 1, "rolling": 2}).fillna(3), kind="stable").drop(columns="_o").reset_index(drop=True)


def decomposition(summary: pd.DataFrame) -> pd.DataFrame:
    """Split the product's (inventory-adjusted) saving vs the baseline into its sources.

    * demand_forecast_part = C1 - C2  (better demand forecast -> less imbalance)
    * battery_part         = C2 - C4  (battery with ML forecasts and the tuned rules)
      = block_default_battery_part (C2 - C4b) + tuning_and_shaping_part (C4b - C4)
    * total                = C1 - C4  = demand_forecast_part + battery_part
    * ceiling_battery_value = C7 - C6, block_rule_cost = C5 - C6 (what the 4-hour block
      rules cost under perfect foresight)
    """
    rows = []
    for split, g in summary.groupby("split", sort=False):
        c = g.set_index("strategy")["total_cost_adj_chf"]
        craw = g.set_index("strategy")["total_cost_chf"]
        need = [BASELINE, "ml_no_battery", PRODUCT, CEILING, PERFECT_NO_BATTERY]
        if not all(k in c for k in need):
            continue
        r = {
            "split": split,
            "total_saving_chf": c[BASELINE] - c[PRODUCT],
            "total_saving_raw_chf": craw[BASELINE] - craw[PRODUCT],
            "demand_forecast_part_chf": c[BASELINE] - c["ml_no_battery"],
            "battery_part_chf": c["ml_no_battery"] - c[PRODUCT],
        }
        if PRODUCT_DEFAULT in c:
            r["block_default_battery_part_chf"] = c["ml_no_battery"] - c[PRODUCT_DEFAULT]
            r["tuning_and_shaping_part_chf"] = c[PRODUCT_DEFAULT] - c[PRODUCT]
        r.update({
            "ceiling_total_saving_chf": c[BASELINE] - c[CEILING],
            "ceiling_battery_value_chf": c[PERFECT_NO_BATTERY] - c[CEILING],
            "forecast_error_cost_ml_chf": c["ml_no_battery"] - c[PERFECT_NO_BATTERY],
            "forecast_error_cost_naive_chf": c[BASELINE] - c[PERFECT_NO_BATTERY],
        })
        r["pct_ceiling_captured_total"] = 100 * r["total_saving_chf"] / r["ceiling_total_saving_chf"]
        r["pct_ceiling_battery_value_captured"] = 100 * r["battery_part_chf"] / r["ceiling_battery_value_chf"]
        if BLOCK_ORACLE in c:
            r["block_perfect_battery_value_chf"] = c[PERFECT_NO_BATTERY] - c[BLOCK_ORACLE]
            r["block_rule_cost_chf"] = c[BLOCK_ORACLE] - c[CEILING]
        rows.append(r)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Tuned decision rules
# ---------------------------------------------------------------------------
_TUNED_CACHE: dict = {}


def tuning_cutoff() -> dt.date:
    """Last delivery day whose settlement data is known when the first test day is planned.

    Day T (= test start) is planned on T-1 before 10:00; the last complete day then is
    T-2 (day T-1 is not over yet)."""
    return _as_date(_periods_cfg()["test_start"]) - dt.timedelta(days=2)


def tuning_periods() -> dict:
    """{'rolling': [...], 'september': [...]} - the days the decision rules are tuned on."""
    p = _periods_cfg()
    return {"rolling": dates_between(p["rolling_start"], p["train_end"]),
            "september": dates_between(p["val_start"], tuning_cutoff())}


def decision_from_row(row) -> DecisionParams:
    kw = {}
    for f in fields(DecisionParams):
        if f.name in row and pd.notna(row[f.name]):
            v = row[f.name]
            if isinstance(f.default, bool):
                v = str(v).strip().lower() in ("true", "1", "yes")
            else:
                v = type(f.default)(v)
            kw[f.name] = v
    return DecisionParams(**kw)


def tuned_decision() -> DecisionParams:
    """Decision rules chosen on pre-October data (``reports/decision_tuning.csv``), or the
    config defaults if no tuning was stored yet. Used by the app and by strategy 4."""
    default = DecisionParams.from_config()
    if not TUNING_FILE.exists():
        return default
    key = TUNING_FILE.stat().st_mtime_ns
    if key in _TUNED_CACHE:
        return _TUNED_CACHE[key]
    t = pd.read_csv(TUNING_FILE)
    c = t[t["chosen"].astype(str).str.lower().isin(["true", "1"])] if "chosen" in t else t.iloc[0:0]
    out = default
    if len(c) and "plan_resolution" in c:
        out = decision_from_row(c.iloc[0])
    _TUNED_CACHE.clear()
    _TUNED_CACHE[key] = out
    return out


def decision_dict(dec: DecisionParams) -> dict:
    return asdict(dec)


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------
def _period(split: str) -> tuple[str, str]:
    p = _periods_cfg()
    return {"val": (p["val_start"], p["val_end"]), "test": (p["test_start"], p["test_end"]),
            "rolling": (p["rolling_start"], p["train_end"])}[split]


def _ml_dates(dates, require_ml) -> list:
    """Dates that have a forecast for every source that is used (ML where a file exists)."""
    fc = load_forecasts(require_ml)
    ok = set(fc.loc[(fc["demand_source"] != "missing") & (fc["price_source"] != "missing"), "delivery_date"])
    return [d for d in dates if d in ok]


def main(argv=None) -> None:
    from src.backtest import analysis as an

    ap = argparse.ArgumentParser(description="Backtest the day-ahead planning strategies.")
    ap.add_argument("--start", help="first delivery date (YYYY-MM-DD)")
    ap.add_argument("--end", help="last delivery date (YYYY-MM-DD)")
    ap.add_argument("--split", choices=["val", "test", "rolling"], help="use a predefined period")
    ap.add_argument("--require-ml", action="store_true", help="fail if an ML prediction file is missing")
    ap.add_argument("--skip-sensitivity", action="store_true", help="skip the sensitivity runs")
    ap.add_argument("--skip-rolling", action="store_true", help="do not backtest the rolling period")
    ap.add_argument("--workers", type=int, default=None, help="parallel processes (default: cpu-1, max 8)")
    args = ap.parse_args(argv)
    if args.workers:
        os.environ["BACKTEST_WORKERS"] = str(args.workers)
    t0 = time.time()
    load_forecasts(args.require_ml)  # raises with --require-ml if files are missing
    source = forecast_source()
    sources = forecast_sources()
    tag = "" if source == "ml" else " [price: STAND-IN]" if sources["demand"] == "ml" else " [STAND-IN forecasts]"
    print(f"Forecast source: {source_text()}")
    REPORTS.mkdir(exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 250)

    # --- a single custom period -------------------------------------------------
    if args.start or args.end or args.split:
        start, end = _period(args.split) if args.split else (args.start, args.end)
        start, end = args.start or start, args.end or end
        dec = tuned_decision()
        daily, summary = run_backtest(start, end, decision=dec, require_ml=args.require_ml, workers=None)
        stem = f"backtest_{start}_{end}"
        daily.to_csv(REPORTS / f"{stem}.csv", index=False)
        summary.to_csv(REPORTS / f"{stem}_summary.csv", index=False)
        print(summary[["split", "strategy", "total_cost_chf", "saving_vs_baseline_adj_chf", "pct_perfect_captured",
                       "battery_value_adj_chf", "cycles", "days_battery_idle"]].round(1).to_string(index=False))
        print(f"Wrote reports/{stem}.csv and _summary.csv ({time.time() - t0:.1f} s); decision = {dec.describe()}")
        return

    # --- 1. tune the decision rules on data before October -----------------------
    per = tuning_periods()
    per = {k: _ml_dates(v, args.require_ml) for k, v in per.items()}
    print(f"Tuning decision rules on rolling ({len(per['rolling'])} days) + September up to "
          f"{tuning_cutoff()} ({len(per['september'])} days) ...")
    tab, dec, kept = an.tune_decision(per["rolling"], per["september"], require_ml=args.require_ml)
    tab.insert(0, "price_source", sources["price"])
    tab.insert(0, "demand_source", sources["demand"])
    tab.to_csv(TUNING_FILE, index=False)
    _TUNED_CACHE.clear()
    print(("  kept config defaults" if kept else "  chosen") + f": {dec.describe()}  ({time.time() - t0:.0f} s)")

    # --- 2. main backtest ----------------------------------------------------------
    print("Running the main backtest ...")
    splits = {"val": dates_between(*_period("val")), "test": dates_between(*_period("test"))}
    if not args.skip_rolling:
        splits["rolling"] = dates_between(*_period("rolling"))
    splits = {k: _ml_dates(v, args.require_ml) for k, v in splits.items()}
    tasks = [dict(tag=(name, s), dates=dates, strategy=s, decision=dec, require_ml=args.require_ml,
                  keep_hourly=(name == "test")) for name, dates in splits.items() if dates for s in MAIN_STRATEGIES]
    res = run_tasks(tasks)
    daily_l, hourly_l = [], []
    for (name, _s), d, h in res:
        d.insert(1, "split", name)
        daily_l.append(d)
        if name == "test":
            hourly_l.append(h)
    daily = pd.concat(daily_l, ignore_index=True)
    daily.insert(2, "demand_source", sources["demand"])
    daily.insert(3, "price_source", sources["price"])
    summary = summarise(daily)
    summary.insert(2, "demand_source", sources["demand"])
    summary.insert(3, "price_source", sources["price"])
    decomp = decomposition(summary)
    decomp.insert(1, "price_source", sources["price"])
    decomp.insert(1, "demand_source", sources["demand"])
    daily.to_csv(REPORTS / "backtest.csv", index=False)
    summary.to_csv(REPORTS / "backtest_summary.csv", index=False)
    decomp.to_csv(REPORTS / "backtest_decomposition.csv", index=False)
    pd.concat(hourly_l, ignore_index=True).to_parquet(REPORTS / "backtest_hourly_test.parquet", index=False)
    exc = an.day_exceptions(daily, summary)
    exc.to_csv(REPORTS / "backtest_exceptions.csv", index=False)
    print(f"  main backtest done ({time.time() - t0:.0f} s)")

    an.fig_cumulative(daily[daily["split"] == "test"], FIGURES / "backtest_cumulative_savings_test.png", tag)
    an.fig_cost_breakdown(summary, FIGURES / "backtest_cost_breakdown.png", "test", tag)
    an.fig_tuning(tab, FIGURES / "backtest_decision_tuning.png", tag)

    sens = {}
    if not args.skip_sensitivity:
        print("Sensitivity runs on the test month (information only) ...")
        sens = an.run_sensitivities(splits["test"], dec, args.require_ml, tag)
        print(f"  sensitivities done ({time.time() - t0:.0f} s)")

    an.write_notes(REPORTS / "backtest_notes.md", sources, summary, decomp, exc, tab, dec, kept, sens)
    cols = ["split", "strategy", "total_cost_chf", "saving_vs_baseline_chf", "saving_vs_baseline_adj_chf",
            "saving_adj_ci_low_chf", "saving_adj_ci_high_chf", "pct_perfect_captured", "battery_value_adj_chf",
            "pct_battery_value_captured", "imbalance_penalty_chf", "cycles", "days_battery_idle", "share_charge_cleared"]
    print(summary[cols].round(1).to_string(index=False))
    print(decomp.round(1).T.to_string())
    print(f"Exceptions: {exc.groupby(['split', 'check']).size().to_dict()}")
    print(f"Done in {time.time() - t0:.0f} s. Outputs in reports/ and reports/figures/.")


if __name__ == "__main__":
    main()
