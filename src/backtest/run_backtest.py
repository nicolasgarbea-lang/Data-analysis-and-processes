"""Backtest: forecast -> battery plan -> hourly bids -> settlement with ACTUAL data.

For every delivery day of a period and for every strategy we

1. take the demand and price forecasts per block (as they were known at forecast time),
2. let the optimiser (MILP) plan buy / charge / discharge per block,
3. turn the plan into hourly auction bids (``src/decision/bids.py``),
4. settle the bids with the ACTUAL hourly prices and the ACTUAL hourly demand:
   * charge bids clear only in hours where the actual price <= limit price,
   * the battery follows the cleared plan hour by hour (planned discharge that is
     physically impossible because the battery is too empty is not delivered),
   * the gap between actual demand and the energy available for the city is the
     imbalance, settled at a penalty price,
5. carry the ACTUAL end-of-day charge level into the next day.

Run it (from the repo root)::

    .venv/bin/python -m src.backtest.run_backtest                      # val + test (+ rolling)
    .venv/bin/python -m src.backtest.run_backtest --start 2026-10-01 --end 2026-10-31
    .venv/bin/python -m src.backtest.run_backtest --split test --require-ml

The Streamlit app imports ``plan_day`` and ``run_backtest`` from here.
"""
from __future__ import annotations

import argparse
import datetime as dt
import time
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import ROOT, load_config
from src.decision.bids import (
    block_hour_shares,
    bids_from_hourly_plan,
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
TOL = 1e-6

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------
# demand / price: which forecast is used ("naive", "ml", "actual", "custom" = given
# by the caller). battery: does the strategy use the battery. hourly: plan with 24
# hourly periods instead of the 6 blocks.
STRATEGIES = {
    "baseline_naive_no_battery": dict(demand="naive", price=None, battery=False, hourly=False),
    "ml_no_battery": dict(demand="ml", price=None, battery=False, hourly=False),
    "naive_battery": dict(demand="naive", price="naive", battery=True, hourly=False),
    "ml_battery": dict(demand="ml", price="ml", battery=True, hourly=False),
    "perfect_foresight_battery": dict(demand="actual", price="actual", battery=True, hourly=False),
    "perfect_foresight_hourly_battery": dict(demand="actual", price="actual", battery=True, hourly=True),
    "perfect_demand_no_battery": dict(demand="actual", price=None, battery=False, hourly=False),
}
MAIN_STRATEGIES = list(STRATEGIES)
BASELINE = "baseline_naive_no_battery"
PRODUCT = "ml_battery"
# battery strategy -> the strategy with the same demand forecast but no battery
NO_BATTERY_PAIR = {
    "naive_battery": "baseline_naive_no_battery",
    "ml_battery": "ml_no_battery",
    "perfect_foresight_battery": "perfect_demand_no_battery",
    "perfect_foresight_hourly_battery": "perfect_demand_no_battery",
}
LABELS = {
    "baseline_naive_no_battery": "1 Baseline: naive, no battery",
    "ml_no_battery": "2 ML demand, no battery",
    "naive_battery": "3 Naive + battery",
    "ml_battery": "4 ML + battery (product)",
    "perfect_foresight_battery": "5 Perfect foresight + battery",
    "perfect_foresight_hourly_battery": "6 Perfect foresight, hourly plan",
    "perfect_demand_no_battery": "7 Perfect demand, no battery",
}


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DecisionParams:
    """Decision rules on top of the optimiser.

    charge_limit_factor : limit = expected discharge price x factor - wear cost.
    min_spread_eur_mwh : extra margin (EUR per MWh discharged) the expected price spread
        must cover before the battery cycles. It is added to the wear cost in the
        PLAN only (real wear cost is still used for the limit price and the bill).
    use_limit : False = charge bids are price-independent (no limit).
    """

    charge_limit_factor: float = 0.9
    min_spread_eur_mwh: float = 0.0
    use_limit: bool = True

    @classmethod
    def from_config(cls, **overrides) -> "DecisionParams":
        b = load_config().get("bidding", {})
        base = cls(
            charge_limit_factor=float(b.get("charge_limit_factor", 0.9)),
            min_spread_eur_mwh=float(b.get("min_spread_eur_mwh", 0.0)),
        )
        return replace(base, **overrides)


@dataclass(frozen=True)
class ImbalanceParams:
    """Imbalance prices relative to the actual day-ahead price p of the hour.

    Shortage (city used more than we had): we pay ``p + (shortage_factor - 1) * |p|``.
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

    Returns a dict with ``blocks`` (DataFrame per date, 6 rows) and ``hours`` (DataFrame
    per date, 23/24/25 rows) for fast look-ups.
    """
    cols = [
        "delivery_date", "block", "hours_in_block", "demand_mw", "price_eur_mwh",
        "demand_lag_7d_same_block", "price_lag_7d_same_block",
        "demand_mean_same_block_same_weekday_4w", "price_lag_1d_same_block", "actual_eurchf",
    ]
    feats = pd.read_parquet(ROOT / load_config()["paths"]["features"], columns=cols)
    feats["delivery_date"] = _to_date(feats["delivery_date"])
    feats = feats.sort_values(["delivery_date", "block"])
    hourly = pd.read_parquet(ROOT / load_config()["paths"]["processed"] / "hourly_actuals.parquet")
    hourly["delivery_date"] = _to_date(hourly["delivery_date"])
    hourly = hourly.sort_values("timestamp_utc").reset_index(drop=True)
    return {
        "features": feats,
        "blocks": {d: g.reset_index(drop=True) for d, g in feats.groupby("delivery_date")},
        "hours": {d: g.reset_index(drop=True) for d, g in hourly.groupby("delivery_date")},
    }


def split_of(d: dt.date) -> str:
    """Name of the evaluation period of a date when no prediction file says otherwise."""
    p = load_config()["periods"]
    s = str(d)
    if p["val_start"] <= s <= p["val_end"]:
        return "val"
    if p["test_start"] <= s <= p["test_end"]:
        return "test"
    if "2025-10-01" <= s <= p["train_end"]:
        return "rolling"
    return "other"


def ml_predictions_available() -> bool:
    return all(f.exists() for f in PRED_FILES.values())


@lru_cache(maxsize=2)
def load_forecasts(require_ml: bool = False) -> pd.DataFrame:
    """Demand and price forecasts per (delivery_date, block), as known at forecast time.

    Columns: ``delivery_date, block, split, demand_naive_mw, demand_ml_mw,
    price_naive_eur_mwh, price_ml_eur_mwh, demand_source, price_source``.

    * naive = same block 7 days earlier (``*_lag_7d_same_block``).
    * ml = ``pred_best`` from ``reports/predictions_<target>.parquet`` when the file exists.
      If it does not exist, a clearly labelled STAND-IN is used (source = "standin"):
      demand = mean of the same block on the same weekday over the last 4 weeks,
      price = same block on day D (``price_lag_1d_same_block``, known since D-1's
      auction). Both are honest forecasts that use only information known at
      forecast time, but they are NOT the project's ML models.
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
        m = out[["delivery_date", "block"]].merge(
            p[["delivery_date", "block", "split", "pred_best", "pred_naive"]], how="left",
            on=["delivery_date", "block"])
        # Only dates covered by the prediction file have an ML forecast. Outside them the
        # ML forecast is missing (no silent stand-in mixing).
        out[col_ml] = m["pred_best"].to_numpy()
        out[col_naive] = np.where(m["pred_naive"].notna(), m["pred_naive"], out[col_naive])
        out[f"{target}_source"] = np.where(m["pred_best"].notna(), "ml", "missing")
        split_from_file = m["split"] if split_from_file is None else split_from_file.fillna(m["split"])
    if split_from_file is not None:
        out["split"] = np.where(split_from_file.notna(), split_from_file, out["split"])
    return out


@lru_cache(maxsize=2)
def _forecast_index(require_ml: bool = False) -> dict:
    fc = load_forecasts(require_ml)
    return {d: g.sort_values("block").reset_index(drop=True) for d, g in fc.groupby("delivery_date")}


def forecast_source() -> str:
    """'ml' if both real prediction files are used, else a text that says stand-in."""
    if ml_predictions_available():
        return "ml"
    have = [k for k, f in PRED_FILES.items() if f.exists()]
    return "standin" if not have else f"mixed (ml for {have}, stand-in for the rest)"


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

    Returns the hourly settlement table and the actual charge level at the end of the day.
    Energy conservation and charge-level limits are asserted for every hour.
    """
    imb = imbalance or ImbalanceParams.from_config()
    d_act = np.asarray(actual_demand_mwh, float)
    p = np.asarray(actual_price_eur_mwh, float)
    fx = np.asarray(eurchf, float)
    q = hp["demand_bid_mwh"].to_numpy(float)
    cb = hp["charge_bid_mwh"].to_numpy(float)
    lim = hp["charge_limit_eur_mwh"].to_numpy(float)
    dis_plan = hp["planned_discharge_mwh"].to_numpy(float)
    n = len(hp)
    eta_c, eta_d = battery.eta_charge, battery.eta_discharge

    cleared = np.zeros(n)
    stored = np.zeros(n)     # energy taken from the grid into the battery
    overflow = np.zeros(n)   # cleared charge energy that did not fit -> goes to the city
    dis = np.zeros(n)
    soc_after = np.zeros(n)
    soc = float(soc_start_mwh)
    assert battery.soc_min - 1e-6 <= soc <= battery.soc_max + 1e-6, "start charge level out of limits"
    for h in range(n):
        if cb[h] > TOL and (np.isnan(lim[h]) or p[h] <= lim[h] + 1e-9):
            cleared[h] = cb[h]
        room = max(battery.soc_max - soc, 0.0) / eta_c
        stored[h] = min(cleared[h], room, battery.power_mw)
        overflow[h] = cleared[h] - stored[h]
        soc += eta_c * stored[h]
        can_give = max(soc - battery.soc_min, 0.0) * eta_d
        dis[h] = min(dis_plan[h], can_give, battery.power_mw)
        if dis[h] < TOL:
            dis[h] = 0.0
        soc -= dis[h] / eta_d
        # charge level must stay inside the limits (tiny rounding is clipped)
        assert battery.soc_min - 1e-6 <= soc <= battery.soc_max + 1e-6, f"charge level {soc} out of limits"
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


def _solve(demand, price, hours, battery_plan, soc_start):
    """Solve the MILP; end-of-day target = configured start level.

    If that target cannot be reached (should not happen with the default battery,
    which can move 20 MWh per hour), the target is relaxed to "end where you started".
    Returns (plan, relaxed_flag).
    """
    try:
        plan = solve_battery_plan(demand, price, hours=hours, battery=battery_plan,
                                  soc_start_mwh=soc_start, soc_end_mwh=battery_plan.soc_start)
        return plan, False
    except RuntimeError:
        plan = solve_battery_plan(demand, price, hours=hours, battery=battery_plan,
                                  soc_start_mwh=soc_start, soc_end_mwh=soc_start)
        return plan, True


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
) -> dict:
    """Plan and (optionally) settle one delivery day.

    Parameters
    ----------
    delivery_date : the day to plan (date or "YYYY-MM-DD").
    strategy : a name from ``STRATEGIES`` or a dict with the same keys.
    battery : battery data (default config.yaml).
    soc_start_mwh : charge level at the start of the day (default: config start level).
    decision, imbalance : decision rules and imbalance prices (default config.yaml).
    price_override : 6 block prices (EUR/MWh) to plan with instead of the forecast
        (strategy price "custom"); used by the price-error sensitivity and the app.
    demand_override_mw : 6 block demand forecasts (mean MW) instead of the forecast.
    settle : False = skip the settlement (e.g. for the real "tomorrow" without actuals).

    Returns a dict with ``plan`` (per period), ``hourly`` (hourly plan + settlement),
    ``bids`` (tidy bid table), ``summary`` (one dict with the day's numbers) and
    ``soc_end_mwh`` (actual end-of-day charge level).
    """
    d = _as_date(delivery_date)
    spec = dict(STRATEGIES[strategy]) if isinstance(strategy, str) else dict(strategy)
    name = strategy if isinstance(strategy, str) else spec.get("name", "custom")
    battery = battery or BatteryParams.from_config()
    decision = decision or DecisionParams.from_config()
    data = load_data()
    if d not in data["blocks"] or d not in data["hours"]:
        raise KeyError(f"no data for delivery date {d}")
    blk = data["blocks"][d]
    hrs = data["hours"][d]
    fc = _forecast_index(require_ml).get(d)
    soc0 = battery.soc_start if soc_start_mwh is None else float(soc_start_mwh)
    h_blk = blk["hours_in_block"].to_numpy(float)

    # --- demand forecast per block (MWh) ---
    if demand_override_mw is not None:
        dem_mw = np.asarray(demand_override_mw, float)
    elif spec["demand"] == "actual":
        dem_mw = blk["demand_mw"].to_numpy(float)
    else:
        dem_mw = fc[f"demand_{spec['demand']}_mw"].to_numpy(float)
    # --- price forecast per block ---
    if price_override is not None:
        price_blk = np.asarray(price_override, float)
    elif spec["price"] is None:
        price_blk = np.full(len(blk), np.nan)
    elif spec["price"] == "actual":
        price_blk = blk["price_eur_mwh"].to_numpy(float)
    else:
        price_blk = fc[f"price_{spec['price']}_eur_mwh"].to_numpy(float)
    if np.isnan(dem_mw).any() or (spec["battery"] and np.isnan(price_blk).any()):
        raise ValueError(f"{d} {name}: forecast missing (are the ML predictions available for this date?)")

    # --- periods and hourly shares ---
    hours = hrs[["delivery_date", "timestamp_utc", "local_time", "hour_local", "block"]].copy()
    if spec.get("hourly"):
        hours["period"] = np.arange(len(hours))
        hours["share"] = 1.0
        per_demand = hrs["demand_mw"].to_numpy(float)  # 1 h each -> MWh
        per_price = hrs["price_eur_mwh"].to_numpy(float)
        per_hours = np.ones(len(hours))
    else:
        hours["period"] = hours["block"].to_numpy()
        shares = np.zeros(len(hours))
        ref_hours = data["hours"].get(d - dt.timedelta(days=7))
        for b in range(len(blk)):
            m = (hours["block"] == b).to_numpy()
            if spec["demand"] == "actual" and demand_override_mw is None:
                ref = hrs.loc[m, ["hour_local", "demand_mw"]]
                v = ref["demand_mw"].to_numpy(float)
                shares[m] = v / v.sum()  # actual shape of the delivery day itself
            else:
                ref = None if ref_hours is None else ref_hours.loc[ref_hours["block"] == b, ["hour_local", "demand_mw"]]
                shares[m] = block_hour_shares(hours.loc[m, "hour_local"].tolist(), ref)
        hours["share"] = shares
        per_demand = dem_mw * h_blk
        per_price = price_blk
        per_hours = h_blk

    # --- plan ---
    relaxed = False
    if spec["battery"]:
        plan_bat = replace(battery, wear_cost_eur_per_mwh=battery.wear_cost_eur_per_mwh + decision.min_spread_eur_mwh)
        plan, relaxed = _solve(per_demand, per_price, per_hours, plan_bat, soc0)
        perfect = spec["price"] == "actual" and price_override is None
        if perfect or not decision.use_limit:
            limits = np.full(len(plan), np.nan)  # charge limit not binding
        else:
            limits = charge_limit_prices(plan, decision.charge_limit_factor, battery.wear_cost_eur_per_mwh)
    else:
        plan = _no_battery_plan(per_demand, per_price, per_hours)
        limits = None
    plan.insert(0, "period", np.arange(len(plan)))
    if spec.get("hourly"):
        plan.insert(1, "block", hours["block"].to_numpy())
    else:
        plan.insert(1, "block", blk["block"].to_numpy())
    plan["charge_limit_eur_mwh"] = np.nan if limits is None else limits

    hp = hourly_plan(plan, hours, limits)
    bids = bids_from_hourly_plan(hp)
    result = {"plan": plan, "bids": bids, "hourly": hp, "soc_end_mwh": np.nan, "summary": None}
    if not settle:
        return result

    # --- settle with actuals ---
    st, soc_end = settle_hours(hp, hrs["demand_mw"].to_numpy(float), hrs["price_eur_mwh"].to_numpy(float),
                               hrs["eurchf"].to_numpy(float), battery, soc0, imbalance)
    if not spec["battery"]:
        assert st["charged_mwh"].abs().sum() == 0 and st["discharged_mwh"].abs().sum() == 0
    st.insert(0, "strategy", name)
    bid_charge = float(st["charge_bid_mwh"].sum())
    cleared = float(st["charge_cleared_mwh"].sum())
    fx = st["eurchf"].to_numpy()
    s = {
        "delivery_date": d,
        "strategy": name,
        "forecast_demand_mwh": float(per_demand.sum()),
        "actual_demand_mwh": float(st["actual_demand_mwh"].sum()),
        "demand_bid_mwh": float(st["demand_bid_mwh"].sum()),
        "charge_bid_mwh": bid_charge,
        "charge_cleared_mwh": cleared,
        "share_charge_cleared": cleared / bid_charge if bid_charge > TOL else np.nan,
        "energy_bought_mwh": float((st["demand_bid_mwh"] + st["charge_cleared_mwh"]).sum()),
        "charged_mwh": float(st["charged_mwh"].sum()),
        "planned_discharge_mwh": float(plan["discharge_mwh"].sum()),
        "discharged_mwh": float(st["discharged_mwh"].sum()),
        "discharge_not_delivered_mwh": float(st["discharge_not_delivered_mwh"].sum()),
        "cycles": float(st["discharged_mwh"].sum() / battery.usable_mwh) if battery.usable_mwh > 0 else 0.0,
        "battery_idle": bool(st["charged_mwh"].sum() < 1e-3 and st["discharged_mwh"].sum() < 1e-3),
        "plan_has_discharge": bool(plan["discharge_mwh"].sum() > 1e-3),
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
    result.update(hourly_settlement=st, summary=s, soc_end_mwh=soc_end)
    return result


# ---------------------------------------------------------------------------
# Many days
# ---------------------------------------------------------------------------
def uses_battery(strategy) -> bool:
    spec = STRATEGIES[strategy] if isinstance(strategy, str) else strategy
    return bool(spec["battery"])


def run_strategy(dates, strategy, battery=None, decision=None, imbalance=None,
                 price_overrides: dict | None = None, require_ml=False, keep_hourly=False):
    """Run one strategy day after day, carrying the actual charge level to the next day.

    The charge level at the end of day D is known when day D+1 is planned: the
    auction results of D are known since D-1 and the battery follows only the cleared
    bids (not the demand), so its path is fully known.
    """
    battery = battery or BatteryParams.from_config()
    soc = battery.soc_start
    rows, hourly = [], []
    for d in dates:
        po = None if price_overrides is None else price_overrides[d]
        r = plan_day(d, strategy, battery=battery, soc_start_mwh=soc, decision=decision,
                     imbalance=imbalance, price_override=po, require_ml=require_ml)
        if uses_battery(strategy):
            soc = r["soc_end_mwh"]
        rows.append(r["summary"])
        if keep_hourly:
            hourly.append(r["hourly_settlement"])
    daily = pd.DataFrame(rows)
    return (daily, pd.concat(hourly, ignore_index=True)) if keep_hourly else (daily, None)


def dates_between(start, end) -> list[dt.date]:
    data = load_data()
    s, e = _as_date(start), _as_date(end)
    return [d for d in sorted(data["blocks"]) if s <= d <= e and d in data["hours"]]


def run_backtest(start, end, strategies=None, battery=None, decision=None, imbalance=None,
                 require_ml=False, keep_hourly=False, n_boot=1000):
    """Backtest all strategies from ``start`` to ``end`` (inclusive).

    Returns ``(daily_df, summary_df)`` (and the hourly settlement as a third element if
    ``keep_hourly``). ``daily_df`` has one row per day x strategy with a ``split`` column;
    ``summary_df`` one row per split x strategy.
    """
    strategies = strategies or MAIN_STRATEGIES
    dates = dates_between(start, end)
    fc_split = load_forecasts(require_ml).drop_duplicates("delivery_date").set_index("delivery_date")["split"]
    daily, hourly = [], []
    for s in strategies:
        dd, hh = run_strategy(dates, s, battery, decision, imbalance, require_ml=require_ml, keep_hourly=keep_hourly)
        daily.append(dd)
        if keep_hourly:
            hourly.append(hh)
    daily = pd.concat(daily, ignore_index=True)
    daily.insert(1, "split", daily["delivery_date"].map(fc_split).fillna("other"))
    summary = summarise(daily, n_boot=n_boot)
    if keep_hourly:
        return daily, summary, pd.concat(hourly, ignore_index=True)
    return daily, summary


def _boot_ci(x: np.ndarray, n_boot: int, seed: int) -> tuple[float, float]:
    """95% interval of the SUM of daily values when whole days are resampled."""
    if len(x) == 0 or n_boot <= 0:
        return np.nan, np.nan
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(x), size=(n_boot, len(x)))
    sums = x[idx].sum(axis=1)
    return float(np.percentile(sums, 2.5)), float(np.percentile(sums, 97.5))


def summarise(daily: pd.DataFrame, n_boot: int = 1000, seed: int | None = None) -> pd.DataFrame:
    """One row per split x strategy with totals, savings and the shares of perfect foresight.

    Definitions (costs C in CHF over the period; numbers = strategy numbers):
    * saving_vs_baseline = C1 - C_s
    * pct_perfect_captured = (C1 - C_s) / (C1 - C5)   (total: forecasts + battery)
    * battery_value = C_pair - C_s, where pair = same forecasts without battery
      (3 -> 1, 4 -> 2, 5 and 6 -> 7)
    * pct_battery_value_captured = battery_value / (C7 - C5)
    """
    seed = load_config().get("random_seed", 42) if seed is None else seed
    out = []
    for split, g in daily.groupby("split", sort=False):
        piv = g.pivot_table(index="delivery_date", columns="strategy", values="total_cost_chf")
        tot = g.groupby("strategy")["total_cost_chf"].sum()
        c1 = tot.get(BASELINE, np.nan)
        c5 = tot.get("perfect_foresight_battery", np.nan)
        c7 = tot.get("perfect_demand_no_battery", np.nan)
        for s, gs in g.groupby("strategy", sort=False):
            r = {"split": split, "strategy": s, "days": len(gs), "label": LABELS.get(s, s)}
            for c in ["total_cost_eur", "total_cost_chf", "da_cost_chf", "imbalance_cost_chf",
                      "imbalance_penalty_chf", "wear_cost_chf", "energy_bought_mwh", "charged_mwh",
                      "discharged_mwh", "discharge_not_delivered_mwh", "shortage_mwh", "surplus_mwh", "cycles"]:
                r[c] = float(gs[c].sum())
            r["days_battery_idle"] = int(gs["battery_idle"].sum())
            bid = gs["charge_bid_mwh"].sum()
            r["share_charge_cleared"] = float(gs["charge_cleared_mwh"].sum() / bid) if bid > TOL else np.nan
            r["saving_vs_baseline_chf"] = c1 - r["total_cost_chf"]
            if BASELINE in piv and s in piv:
                daily_saving = (piv[BASELINE] - piv[s]).dropna().to_numpy()
                r["saving_ci_low_chf"], r["saving_ci_high_chf"] = _boot_ci(daily_saving, n_boot, seed)
                r["days_cheaper_than_baseline"] = int((daily_saving > 0.005).sum())
            denom = c1 - c5
            r["pct_perfect_captured"] = 100 * r["saving_vs_baseline_chf"] / denom if abs(denom) > 1e-9 else np.nan
            pair = NO_BATTERY_PAIR.get(s)
            if pair is not None and pair in tot:
                r["battery_value_chf"] = tot[pair] - r["total_cost_chf"]
                bdenom = c7 - c5
                r["pct_battery_value_captured"] = 100 * r["battery_value_chf"] / bdenom if abs(bdenom) > 1e-9 else np.nan
            out.append(r)
    return pd.DataFrame(out)


def decomposition(summary: pd.DataFrame) -> pd.DataFrame:
    """Split the product's saving vs the baseline into its two sources, per split.

    * demand_forecast_part = C1 - C2  (better demand forecast -> less imbalance)
    * battery_part         = C2 - C4  (battery arbitrage with ML forecasts)
    * total                = C1 - C4  = sum of the two
    * perfect_battery_value = C7 - C5, block_simplification_cost = C5 - C6
    """
    rows = []
    for split, g in summary.groupby("split", sort=False):
        c = g.set_index("strategy")["total_cost_chf"]
        need = [BASELINE, "ml_no_battery", PRODUCT, "perfect_foresight_battery", "perfect_demand_no_battery"]
        if not all(k in c for k in need):
            continue
        r = {
            "split": split,
            "total_saving_chf": c[BASELINE] - c[PRODUCT],
            "demand_forecast_part_chf": c[BASELINE] - c["ml_no_battery"],
            "battery_part_chf": c["ml_no_battery"] - c[PRODUCT],
            "perfect_total_saving_chf": c[BASELINE] - c["perfect_foresight_battery"],
            "perfect_battery_value_chf": c["perfect_demand_no_battery"] - c["perfect_foresight_battery"],
            "forecast_error_cost_ml_chf": c["ml_no_battery"] - c["perfect_demand_no_battery"],
            "forecast_error_cost_naive_chf": c[BASELINE] - c["perfect_demand_no_battery"],
        }
        r["pct_perfect_captured_total"] = 100 * r["total_saving_chf"] / r["perfect_total_saving_chf"]
        r["pct_perfect_battery_value_captured"] = 100 * r["battery_part_chf"] / r["perfect_battery_value_chf"]
        if "perfect_foresight_hourly_battery" in c:
            r["block_simplification_cost_chf"] = c["perfect_foresight_battery"] - c["perfect_foresight_hourly_battery"]
        rows.append(r)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------
TUNING_FILE = REPORTS / "decision_tuning.csv"


def tuned_decision() -> DecisionParams:
    """Decision rules chosen on the validation month (``reports/decision_tuning.csv``),
    or the config defaults if no tuning was stored yet. Used by the app."""
    default = DecisionParams.from_config()
    if not TUNING_FILE.exists():
        return default
    t = pd.read_csv(TUNING_FILE)
    c = t[t["chosen"]]
    if len(c) == 0:
        return default
    c = c.iloc[0]
    f = str(c["charge_limit_factor"])
    return replace(default, use_limit=f != "none",
                   charge_limit_factor=default.charge_limit_factor if f == "none" else float(f),
                   min_spread_eur_mwh=float(c["min_spread_eur_mwh"]))


def _period(split: str) -> tuple[str, str]:
    p = load_config()["periods"]
    return {"val": (p["val_start"], p["val_end"]), "test": (p["test_start"], p["test_end"]),
            "rolling": ("2025-10-01", p["train_end"])}[split]


def main(argv=None) -> None:
    from src.backtest import analysis as an

    ap = argparse.ArgumentParser(description="Backtest the day-ahead planning strategies.")
    ap.add_argument("--start", help="first delivery date (YYYY-MM-DD)")
    ap.add_argument("--end", help="last delivery date (YYYY-MM-DD)")
    ap.add_argument("--split", choices=["val", "test", "rolling"], help="use a predefined period")
    ap.add_argument("--require-ml", action="store_true", help="fail if the ML prediction files are missing")
    ap.add_argument("--with-rolling", action="store_true", help="also run the rolling period with stand-in forecasts")
    ap.add_argument("--skip-sensitivity", action="store_true", help="skip the (slower) sensitivity runs")
    args = ap.parse_args(argv)
    t0 = time.time()
    load_forecasts(args.require_ml)  # raises with --require-ml if files are missing
    source = "ml" if args.require_ml else forecast_source()
    tag = "" if source == "ml" else " [STAND-IN forecasts]"
    print(f"Forecast source: {source}")
    REPORTS.mkdir(exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 250)

    # --- a single custom period -------------------------------------------------
    if args.start or args.end or args.split:
        start, end = _period(args.split) if args.split else (args.start, args.end)
        start, end = args.start or start, args.end or end
        dec = tuned_decision()
        daily, summary = run_backtest(start, end, decision=dec, require_ml=args.require_ml)
        stem = f"backtest_{start}_{end}"
        daily.to_csv(REPORTS / f"{stem}.csv", index=False)
        summary.to_csv(REPORTS / f"{stem}_summary.csv", index=False)
        print(summary[["split", "strategy", "total_cost_chf", "saving_vs_baseline_chf", "pct_perfect_captured",
                       "battery_value_chf", "cycles", "days_battery_idle"]].round(1).to_string(index=False))
        print(f"Wrote reports/{stem}.csv and _summary.csv ({time.time() - t0:.1f} s); decision = {dec}")
        return

    # --- full run: tune on validation, then val + test (+ rolling) --------------
    val_dates = dates_between(*_period("val"))
    test_dates = dates_between(*_period("test"))
    fc = load_forecasts(args.require_ml)
    has_rolling_ml = source == "ml" and (fc["split"] == "rolling").any()
    rolling_dates = dates_between(*_period("rolling")) if (has_rolling_ml or args.with_rolling) else []
    if has_rolling_ml:
        ok = set(fc.loc[(fc["split"] == "rolling") & (fc["demand_source"] == "ml") & (fc["price_source"] == "ml"), "delivery_date"])
        rolling_dates = [d for d in rolling_dates if d in ok]

    print("Tuning decision rules on the validation month" + (" + rolling period" if rolling_dates else "") + " ...")
    tab, dec, kept = an.tune_decision(val_dates, rolling_dates or None, require_ml=args.require_ml)
    tab.insert(0, "forecast_source", source)
    tab.to_csv(TUNING_FILE, index=False)
    print(("  kept config defaults" if kept else "  chosen") + f": {dec}")

    print("Running the main backtest ...")
    daily_l, hourly_test = [], None
    for name, dates in [("val", val_dates), ("test", test_dates), ("rolling", rolling_dates)]:
        if not dates:
            continue
        out = run_backtest(dates[0], dates[-1], decision=dec, require_ml=args.require_ml,
                           keep_hourly=(name == "test"))
        d = out[0]
        d["split"] = name
        daily_l.append(d)
        if name == "test":
            hourly_test = out[2]
    daily = pd.concat(daily_l, ignore_index=True)
    daily.insert(2, "forecast_source", source)
    summary = summarise(daily)
    summary.insert(2, "forecast_source", source)
    decomp = decomposition(summary)
    daily.to_csv(REPORTS / "backtest.csv", index=False)
    summary.to_csv(REPORTS / "backtest_summary.csv", index=False)
    decomp.to_csv(REPORTS / "backtest_decomposition.csv", index=False)
    hourly_test.to_parquet(REPORTS / "backtest_hourly_test.parquet", index=False)
    exc = an.day_exceptions(daily)
    exc.to_csv(REPORTS / "backtest_exceptions.csv", index=False)

    an.fig_cumulative(daily[daily["split"] == "test"], FIGURES / "backtest_cumulative_savings_test.png", tag)
    an.fig_cost_breakdown(summary, FIGURES / "backtest_cost_breakdown.png", "test", tag)

    price_tab = size_tab = sens_tab = None
    if not args.skip_sensitivity:
        print("Sensitivity runs on the test month (information only) ...")
        size_tab = an.battery_size_sensitivity(test_dates, dec, args.require_ml)
        size_tab.to_csv(REPORTS / "backtest_battery_sensitivity.csv", index=False)
        an.fig_battery_size(size_tab, FIGURES / "backtest_battery_size_sensitivity.png", tag)
        price_tab = an.price_error_sensitivity(test_dates, dec, require_ml=args.require_ml)
        pt = price_tab.copy()
        pt["slope_chf_per_eur_mae_month"] = price_tab.attrs["slope_chf_per_eur"]
        pt.to_csv(REPORTS / "backtest_price_error_sensitivity.csv", index=False)
        an.fig_price_error(price_tab, FIGURES / "backtest_price_error_sensitivity.png", tag)
        sens_tab = an.decision_sensitivity(test_dates, dec, args.require_ml)
        sens_tab.to_csv(REPORTS / "backtest_decision_sensitivity.csv", index=False)
        an.fig_decision_sensitivity(sens_tab, FIGURES / "backtest_decision_sensitivity.png", tag)

    an.write_notes(REPORTS / "backtest_notes.md", source, summary, decomp, exc, tab, dec, kept,
                   price_tab, size_tab, sens_tab)
    cols = ["split", "strategy", "total_cost_chf", "saving_vs_baseline_chf", "saving_ci_low_chf",
            "saving_ci_high_chf", "pct_perfect_captured", "battery_value_chf", "pct_battery_value_captured",
            "imbalance_penalty_chf", "cycles", "days_battery_idle", "share_charge_cleared"]
    print(summary[cols].round(1).to_string(index=False))
    print(decomp.round(1).T.to_string())
    print(f"Exceptions: {exc.groupby(['split', 'check']).size().to_dict()}")
    print(f"Done in {time.time() - t0:.0f} s. Outputs in reports/ and reports/figures/.")


if __name__ == "__main__":
    main()
