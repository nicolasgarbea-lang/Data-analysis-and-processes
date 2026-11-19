"""Write the JSON files the web app reads (contract: ``web/src/data/types.ts``).

Run from the repo root::

    .venv/bin/python -m src.export.export_web                 # writes web/public/data/
    .venv/bin/python -m src.export.export_web --out /tmp/x    # somewhere else (tests)

Files written (every number is read or computed from repo files at export time):

* ``meta.json``            Meta: settings, sources, the 61 delivery days of Sept + Oct 2026
* ``days/<date>.json``     DayPlan of the product (``ml_battery``, tuned rules, default battery) for every
                           day; the charge level is carried day to day exactly as in the backtest (the
                           exporter asserts that every day reproduces ``reports/backtest.csv``)
* ``backtest.json``        Backtest: the three periods, strategies, decomposition, sensitivities
* ``models.json``          {"demand": ModelInfo, "price": ModelInfo}
* ``drivers.json``         Drivers: the data behind the driver charts
* ``method.json``          Method: sources, time rules, limitations, review findings

``build_day_plan`` is the single builder of a DayPlan; ``api/server.py`` calls the same function for a
custom battery, and ``month_result`` is the whole-month re-run of the live API.

Definitions that the contract leaves open (also listed in the module that uses them):

* ``summary.eurchf`` = EUR/CHF rate known at forecast time (ECB rate of D-1, ``eurchf_d_1``); it converts
  the EXPECTED cost and saving. Realised costs use the hourly rate of the delivery date (as the backtest).
* ``summary.cycles`` = cycles actually delivered after settlement (discharged MWh / usable MWh), the
  number the backtest reports. Energy to buy / charged / discharged are the PLANNED values.
* ``hours[].price_fc`` = the hourly price the optimiser planned with (hourly-shape mode), otherwise the
  block forecast of the hour's block.
* ``hours[].charge_actual_mwh`` = energy that actually went from the grid into the battery
  (cleared charge minus what did not fit); ``discharge_actual_mwh`` = energy actually delivered.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import re
import time
from dataclasses import asdict, fields
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from src.backtest import run_backtest as rb
from src.config import ROOT, load_config
from src.optimisation.battery_lp import BatteryParams

REPORTS = ROOT / "reports"
DOCS = ROOT / "docs"
PROCESSED = ROOT / "data" / "processed"
DEFAULT_OUT = ROOT / "web" / "public" / "data"

PRODUCT = rb.PRODUCT
BASELINE = rb.BASELINE
NO_BATTERY = "ml_no_battery"
CEILING = rb.CEILING
COMPANY = "Limmat Energie AG"
TOL_CHF = 0.01  # reproduction tolerance against reports/backtest.csv

# ---------------------------------------------------------------------------
# readable names (same wording as the earlier Streamlit app)
# ---------------------------------------------------------------------------
STRATEGIES = [
    # key, readable name, kind, one plain sentence
    (BASELINE, "Baseline: last week's demand, no battery", "baseline",
     "Buys the demand of the same block one week earlier and has no battery."),
    (NO_BATTERY, "ML demand forecast, no battery", "reference",
     "Buys the ML demand forecast and has no battery."),
    ("naive_battery", "Naive forecasts + battery", "reference",
     "Plans the battery with last week's demand and prices under the same tuned rules as the product."),
    (PRODUCT, "Our product: ML forecasts + battery", "product",
     "Plans the battery hour by hour with the ML demand and price forecasts and the tuned bidding rules."),
    (rb.PRODUCT_DEFAULT, "ML + battery, simple 4-hour block plan", "reference",
     "Uses the same ML forecasts but plans the six 4-hour blocks with the default rules."),
    (rb.BLOCK_ORACLE, "Perfect foresight, 4-hour block rules", "reference",
     "Knows the real demand and prices in advance but must follow the same 4-hour block rules."),
    (rb.HOURLY_DAILY_ORACLE, "Perfect foresight, hourly, back to start level every day", "reference",
     "Knows everything in advance and plans every hour, but returns to the start level every evening."),
    (CEILING, "Perfect foresight, hourly (best possible)", "ceiling",
     "Knows everything in advance and plans all hours of the period at once, the best result possible."),
    (rb.PERFECT_NO_BATTERY, "Perfect demand forecast, no battery", "reference",
     "Knows the real demand in advance and has no battery."),
]
STRATEGY_NAMES = {k: n for k, n, _, _ in STRATEGIES}
CUMULATIVE_KEYS = [NO_BATTERY, PRODUCT, rb.BLOCK_ORACLE, CEILING]

MODEL_NAMES = {"naive": "Naive (copy a past value)", "linear": "Linear regression", "rf": "Random forest",
               "gbm": "Gradient boosting (LightGBM)", "best": "Best model (final)"}

# Plain-language labels of model inputs. Every feature in the top 15 of an importance file must be
# here (the exporter raises otherwise, so no raw column name reaches the app).
FEATURE_LABELS = {
    # demand history
    "demand_lag_2d_same_block": "Demand of the same block on the last known day (D−1)",
    "demand_lag_3d_same_block": "Demand of the same block three days before delivery",
    "demand_lag_7d_same_block": "Demand of the same block one week earlier",
    "demand_lag_8d_same_block": "Demand of the same block eight days before delivery",
    "demand_mean_same_block_same_weekday_4w": "Average demand of this block on the same weekday, last 4 weeks",
    "expected_demand_proxy": "Typical demand of this block and weekday (last 4 weeks)",
    "demand_day_min_lag_2d": "Lowest block demand of the last known day",
    "demand_day_max_lag_2d": "Highest block demand of the last known day",
    **{f"demand_dm1_block_{b}": f"Demand of block {a:02d}–{e:02d} on the last known day"
       for b, (a, e) in enumerate([(0, 4), (4, 8), (8, 12), (12, 16), (16, 20), (20, 24)])},
    # calendar
    "block": "Time of day (which 4-hour block)",
    "is_working_day": "Working day or not",
    "weekday": "Day of the week",
    "is_weekend": "Weekend",
    "is_holiday": "Public holiday",
    "is_school_holiday": "School holidays",
    "lag2d_is_weekend": "Last known day was a weekend",
    "lag2d_was_holiday": "Last known day was a public holiday",
    "days_to_next_holiday": "Days until the next public holiday",
    "month": "Month of the year",
    "day_of_year": "Day of the year",
    # Zurich weather
    "radiation_wm2": "Solar radiation forecast for the block",
    "radiation_day_mean": "Solar radiation forecast, day average",
    "radiation_obs_same_block_lag_2d": "Measured solar radiation, same block on the last known day",
    "temp_c": "Temperature forecast for the block",
    "temp_c_sq": "Temperature forecast, squared (very cold or hot)",
    "heating_degree": "Heating need (degrees below 15 °C)",
    "cooling_degree": "Cooling need (degrees above 22 °C)",
    "temp_change_fc_vs_dm1": "Temperature change against the last known day",
    "temp_obs_same_block_lag_2d": "Measured temperature, same block on the last known day",
    "temp_obs_mean_last_3d": "Measured temperature, average of the last 3 days",
    "temp_obs_mean_last_7d": "Measured temperature, average of the last 7 days",
    "temp_day_mean": "Temperature forecast, day average",
    "humidity_pct": "Humidity forecast",
    "sunshine_day_sum": "Sunshine forecast, hours per day",
    "sunshine_min": "Sunshine forecast for the block",
    "cloud_pct": "Cloud cover forecast",
    "wind_ms": "Wind speed forecast, Zurich",
    "precip_mm": "Rain forecast, Zurich",
    # price history and neighbours
    "price_mean_day_D": "Swiss price today (day D), daily average",
    "price_block_vs_day_ratio_last_7d": "Usual price gap of this block to the day average, last 7 days",
    "price_lag_1d_same_block": "Swiss price of the same block today (day D)",
    "price_lag_7d_same_block": "Swiss price of the same block one week earlier",
    "price_lag_14d_same_block": "Swiss price of the same block two weeks earlier",
    "price_de_mean_day_D": "German price today, daily average",
    "price_fr_mean_day_D": "French price today, daily average",
    "price_it_day_D_same_block": "Italian price of the same block today",
    "spread_ch_de_day_D": "Swiss minus German price today",
    "spread_ch_it_day_D": "Swiss minus Italian price today",
    "price_spread_day_D": "Gap between today's most and least expensive hours",
    "price_max_day_D": "Highest Swiss price today",
    "price_min_day_D": "Lowest Swiss price today",
    "price_mean_last_7d": "Swiss price, average of the last 7 days",
    "price_mean_last_28d": "Swiss price, average of the last 4 weeks",
    # fuels and Europe
    "clean_gas_cost": "Cost of power from gas, incl. CO₂ (last close)",
    "gas_ttf_d_1": "Gas price (last close)",
    "gas_ttf_change_5d": "Change in the gas price over 5 days",
    "eu_radiation_wm2_de_mean_safe": "Solar radiation forecast, Germany",
    "eu_temp_c_fr_paris_jma_safe": "Temperature forecast, Paris",
    "eu_temp_c_fr_mean_jma_safe": "Temperature forecast, France",
    "eu_wind10_ms_de_north_jma_safe": "Wind forecast, northern Germany",
    "eu_wind10_ms_de_northeast_jma_safe_day": "Wind forecast, north-eastern Germany (day)",
    "swiss_net_import_mw_lag_2d": "Swiss net imports on the last known day",
}

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# ---------------------------------------------------------------------------
# number helpers: NaN / inf -> None, fixed rounding per unit
# ---------------------------------------------------------------------------
def num(x, nd: int):
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v):
        return None
    v = round(v, nd)
    return 0.0 if v == 0 else v  # no "-0.0"


def mw(x):  # MW and MWh
    return num(x, 3)


def eur(x):  # prices EUR/MWh
    return num(x, 2)


def chf(x):
    return num(x, 2)


def frac(x):
    return num(x, 4)


def req(x, f=num, *a):
    """Value that the contract does not allow to be null."""
    v = f(x, *a) if a else f(x)
    if v is None:
        raise ValueError(f"required number is missing or not finite: {x!r}")
    return v


def _date(x) -> dt.date:
    return pd.Timestamp(str(x)).date()


def block_labels() -> list[str]:
    return [f"{a:02d}–{b:02d}" for a, b in load_config()["blocks"]]


def periods() -> dict:
    return load_config()["periods"]


# ---------------------------------------------------------------------------
# battery settings <-> BatteryParams
# ---------------------------------------------------------------------------
BATTERY_FIELDS = [f.name for f in fields(BatteryParams)]


def default_battery_settings() -> dict:
    b = asdict(BatteryParams.from_config())
    b["allow_sell"] = bool(load_config()["battery"].get("allow_sell", False))
    return {k: (bool(v) if k == "allow_sell" else float(v)) for k, v in b.items()}


def battery_params(settings: dict) -> BatteryParams:
    return BatteryParams(**{k: float(settings[k]) for k in BATTERY_FIELDS})


def battery_json(settings: dict) -> dict:
    out = {k: num(settings[k], 6) for k in BATTERY_FIELDS}
    out["allow_sell"] = bool(settings.get("allow_sell", False))
    return out


# ---------------------------------------------------------------------------
# cached inputs
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _calendar() -> pd.DataFrame:
    c = pd.read_parquet(PROCESSED / "calendar_daily.parquet",
                        columns=["date", "is_weekend", "is_holiday", "holiday_name"])
    c["date"] = pd.to_datetime(c["date"].astype(str)).dt.date
    e = pd.read_parquet(PROCESSED / "events_daily.parquet", columns=["date", "event_name"])
    e["date"] = pd.to_datetime(e["date"].astype(str)).dt.date
    return c.merge(e, on="date", how="left").set_index("date")


@lru_cache(maxsize=1)
def _eurchf_known() -> dict:
    f = pd.read_parquet(ROOT / load_config()["paths"]["features"], columns=["delivery_date", "eurchf_d_1"])
    f["delivery_date"] = pd.to_datetime(f["delivery_date"].astype(str)).dt.date
    return f.drop_duplicates("delivery_date").set_index("delivery_date")["eurchf_d_1"].to_dict()


@lru_cache(maxsize=1)
def _demand_bands() -> dict:
    p = pd.read_parquet(REPORTS / "predictions_demand.parquet")
    p["delivery_date"] = pd.to_datetime(p["delivery_date"].astype(str)).dt.date
    p = p.drop_duplicates(["delivery_date", "block"], keep="last")
    q10 = p["pred_q10"] if "pred_q10" in p else np.nan
    q90 = p["pred_q90"] if "pred_q90" in p else np.nan
    return {(d, int(b)): (lo, hi) for d, b, lo, hi in zip(p["delivery_date"], p["block"], q10, q90)}


@lru_cache(maxsize=1)
def backtest_daily() -> pd.DataFrame:
    b = pd.read_csv(REPORTS / "backtest.csv")
    b["delivery_date"] = pd.to_datetime(b["delivery_date"].astype(str)).dt.date
    return b


def carried_soc(d) -> float | None:
    """Charge level at the start of day ``d`` in the stored backtest of the product (default battery)."""
    b = backtest_daily()
    r = b[(b["strategy"] == PRODUCT) & (b["delivery_date"] == _date(d)) & b["split"].isin(["val", "test"])]
    if len(r) == 0 or not np.isfinite(r["soc_start_mwh"].iloc[0]):
        return None
    return float(r["soc_start_mwh"].iloc[0])


@lru_cache(maxsize=256)
def _no_battery_summary(d: dt.date, strategy: str, allow_sell: bool) -> dict:
    """Settled day of a strategy without battery (does not depend on the battery settings)."""
    return rb.plan_day(d, strategy, soc_start_mwh=None, allow_sell=allow_sell)["summary"]


def export_dates() -> list[tuple[dt.date, str]]:
    """Delivery days of the validation (September) and test (October) months, with their split."""
    p = periods()
    out = [(d, "val") for d in rb.dates_between(p["val_start"], p["val_end"])]
    out += [(d, "test") for d in rb.dates_between(p["test_start"], p["test_end"])]
    return out


def day_info(d: dt.date) -> dict:
    cal = _calendar()
    r = cal.loc[d] if d in cal.index else None
    hol = bool(r["is_holiday"]) if r is not None else False
    name = r["holiday_name"] if r is not None and isinstance(r["holiday_name"], str) and hol else None
    ev = r["event_name"] if r is not None and isinstance(r["event_name"], str) and r["event_name"] else None
    return {
        "weekday": f"{d:%A}",
        "is_holiday": hol,
        "is_weekend": bool(r["is_weekend"]) if r is not None else d.weekday() >= 5,
        "holiday_name": name,
        "event_name": ev,
        "hours": rb.expected_hours(d),
    }


# ---------------------------------------------------------------------------
# DayPlan (shared by the exporter and the API)
# ---------------------------------------------------------------------------
def _hour_label(t) -> str:
    return f"{pd.Timestamp(t):%H:%M}"


def _utc(t) -> str:
    return pd.Timestamp(t).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


def build_day_plan(date, battery: dict, soc_start_mwh: float, split: str) -> dict:
    """DayPlan (see types.ts) of the product for one delivery day.

    ``battery`` = BatterySettings dict, ``soc_start_mwh`` = charge level at the start of the day.
    Plans and settles ``ml_battery`` with the tuned decision rules (``plan_day`` default), and settles
    ``ml_no_battery`` and the baseline for the realised savings.
    """
    d = _date(date)
    bat = battery_params(battery)
    allow_sell = bool(battery.get("allow_sell", False))
    r = rb.plan_day(d, PRODUCT, battery=bat, soc_start_mwh=soc_start_mwh, allow_sell=allow_sell)
    s = r["summary"]
    s_nb = _no_battery_summary(d, NO_BATTERY, allow_sell)
    s_base = _no_battery_summary(d, BASELINE, allow_sell)
    plan, pp, hp, st = r["plan"], r["plan_periods"], r["hourly"], r["settlement"]
    blk = rb.load_data()["blocks"][d]
    fc = rb._forecast_index().get(d)
    bands = _demand_bands()
    labels = block_labels()
    fx = _eurchf_known().get(d, np.nan)
    if not np.isfinite(fx):
        raise ValueError(f"{d}: EUR/CHF rate known at forecast time is missing")

    blocks = []
    for i in range(6):
        p = plan.iloc[i]
        hrs = float(blk["hours_in_block"].iloc[i])
        q = bands.get((d, i), (np.nan, np.nan))
        blocks.append({
            "block": i,
            "label": labels[i],
            "hours": int(round(hrs)),
            "demand_fc_mw": req(p["demand_mwh"] / hrs, mw),
            "demand_q10_mw": mw(q[0]),
            "demand_q90_mw": mw(q[1]),
            "demand_actual_mw": req(blk["demand_mw"].iloc[i], mw),
            "demand_naive_mw": req(fc["demand_naive_mw"].iloc[i], mw),
            "price_fc": req(fc["price_ml_eur_mwh"].iloc[i], eur),
            "price_q10": eur(fc["price_q10_eur_mwh"].iloc[i]),
            "price_q90": eur(fc["price_q90_eur_mwh"].iloc[i]),
            "price_actual": req(blk["price_eur_mwh"].iloc[i], eur),
            "price_naive": req(fc["price_naive_eur_mwh"].iloc[i], eur),
            "buy_mwh": req(p["buy_mwh"], mw),
            "charge_mwh": req(p["charge_mwh"], mw),
            "discharge_mwh": req(p["discharge_mwh"], mw),
            "sell_mwh": req(p["sell_mwh"], mw),
            "soc_end_mwh": req(p["soc_mwh"], mw),
            "option": str(p["option"]),
            "charge_limit_eur_mwh": eur(p["charge_limit_eur_mwh"]),
        })

    hourly_mode = pp.attrs.get("plan_resolution") == "hourly" and len(pp) == len(hp)
    price_h = (pp["price_eur_mwh"].to_numpy(float) if hourly_mode
               else fc["price_ml_eur_mwh"].to_numpy(float)[hp["block"].to_numpy(int)])
    hours = []
    for h in range(len(st)):
        x = st.iloc[h]
        fxh = float(x["eurchf"])
        hours.append({
            "utc": _utc(x["timestamp_utc"]),
            "hour": _hour_label(x["local_time"]),
            "block": int(x["block"]),
            "demand_fc_mw": req(x["need_mwh"], mw),
            "demand_actual_mw": req(x["actual_demand_mwh"], mw),
            "price_fc": eur(price_h[h]),
            "price_actual": req(x["actual_price_eur_mwh"], eur),
            "demand_bid_mwh": req(x["demand_bid_mwh"], mw),
            "charge_bid_mwh": req(x["charge_bid_mwh"], mw),
            "charge_limit_eur_mwh": eur(x["charge_limit_eur_mwh"]) if x["charge_bid_mwh"] > 1e-9 else None,
            "planned_discharge_mwh": req(x["planned_discharge_mwh"], mw),
            "charge_cleared_mwh": req(x["charge_cleared_mwh"], mw),
            "charge_actual_mwh": req(x["charged_mwh"], mw),
            "discharge_actual_mwh": req(x["discharged_mwh"], mw),
            "soc_mwh": req(x["soc_end_mwh"], mw),
            "shortage_mwh": req(x["shortage_mwh"], mw),
            "surplus_mwh": req(x["surplus_mwh"], mw),
            "da_cost_chf": req(x["da_cost_eur"] * fxh, chf),
            "imbalance_cost_chf": req(x["imbalance_cost_eur"] * fxh, chf),
            "imbalance_penalty_chf": req(x["imbalance_penalty_eur"] * fxh, chf),
            "wear_cost_chf": req(x["wear_cost_eur"] * fxh, chf),
        })

    bids = []
    for b in r["bids"].sort_values(["timestamp_utc", "bid_type"], kind="stable").itertuples():
        if b.volume_mwh <= 1e-9:
            continue
        bids.append({
            "hour": _hour_label(b.local_time),
            "utc": _utc(b.timestamp_utc),
            "block": int(b.block),
            "bid_type": str(b.bid_type),
            "volume_mwh": req(b.volume_mwh, mw),
            "limit_price_eur_mwh": eur(b.limit_price_eur_mwh),
        })

    at = plan.attrs
    info = day_info(d)
    summary = {
        "soc_start_mwh": req(s["soc_start_mwh"], mw),
        "soc_end_mwh": req(s["soc_end_mwh"], mw),
        "energy_to_buy_mwh": req(plan["buy_mwh"].sum(), mw),
        "charged_mwh": req(plan["charge_mwh"].sum(), mw),
        "discharged_mwh": req(plan["discharge_mwh"].sum(), mw),
        "cycles": req(s["cycles"], frac),
        "expected_cost_chf": req(at["cost_eur"] * fx, chf),
        "expected_battery_saving_chf": req(at["saving_eur"] * fx, chf),
        "realised_cost_chf": req(s["total_cost_chf"], chf),
        "realised_battery_saving_chf": req(s_nb["total_cost_chf"] - s["total_cost_chf"], chf),
        "realised_saving_vs_baseline_chf": req(s_base["total_cost_chf"] - s["total_cost_chf"], chf),
        "baseline_cost_chf": req(s_base["total_cost_chf"], chf),
        "imbalance_penalty_chf": req(s["imbalance_penalty_chf"], chf),
        "imbalance_cost_chf": req(s["imbalance_cost_chf"], chf),
        "wear_cost_chf": req(s["wear_cost_chf"], chf),
        "share_charge_cleared": frac(s["share_charge_cleared"]),
        "eurchf": req(fx, num, 6),
    }
    return {
        "date": str(d),
        "split": split,
        "weekday": info["weekday"],
        "is_holiday": info["is_holiday"],
        "holiday_name": info["holiday_name"],
        "event_name": info["event_name"],
        "battery": battery_json(battery),
        "blocks": blocks,
        "hours": hours,
        "bids": bids,
        "summary": summary,
        "_raw": {"total_cost_chf": float(s["total_cost_chf"]), "soc_end_mwh": float(s["soc_end_mwh"]),
                 "no_battery_cost_chf": float(s_nb["total_cost_chf"]),
                 "baseline_cost_chf": float(s_base["total_cost_chf"])},
    }


def strip_raw(plan: dict) -> dict:
    return {k: v for k, v in plan.items() if k != "_raw"}


def export_days() -> dict[str, dict]:
    """DayPlans of Sept + Oct with the charge level carried day to day like ``run_strategy``
    (every period starts at the configured start level). Asserts the backtest is reproduced."""
    bat = default_battery_settings()
    params = battery_params(bat)
    bt = backtest_daily().set_index(["split", "strategy", "delivery_date"])
    out = {}
    soc, last_split = None, None
    for d, split in export_dates():
        if split != last_split:
            soc, last_split = params.soc_start, split
        plan = build_day_plan(d, bat, soc, split)
        raw = plan.pop("_raw")
        ref = bt.loc[(split, PRODUCT, d)]
        for what, mine, theirs in [
            ("start charge level", soc, ref["soc_start_mwh"]),
            ("product cost", raw["total_cost_chf"], ref["total_cost_chf"]),
            ("ML no-battery cost", raw["no_battery_cost_chf"], bt.loc[(split, NO_BATTERY, d), "total_cost_chf"]),
            ("baseline cost", raw["baseline_cost_chf"], bt.loc[(split, BASELINE, d), "total_cost_chf"]),
        ]:
            assert abs(mine - theirs) <= TOL_CHF, f"{d} {what}: exporter {mine:.4f} vs backtest.csv {theirs:.4f}"
        soc = rb.carry_soc(raw["soc_end_mwh"], params)
        out[str(d)] = plan
    want = sorted(set(map(str, bt.xs(PRODUCT, level="strategy").loc[["val", "test"]].index.get_level_values(-1))))
    assert sorted(out) == want, "exported days differ from the val/test days in reports/backtest.csv"
    return out


# ---------------------------------------------------------------------------
# whole month re-run (live API)
# ---------------------------------------------------------------------------
@lru_cache(maxsize=4)
def _month_no_battery(allow_sell: bool) -> pd.DataFrame:
    p = periods()
    dates = rb.dates_between(p["test_start"], p["test_end"])
    rows = [rb.run_strategy(dates, s)[0] for s in [BASELINE, NO_BATTERY, rb.PERFECT_NO_BATTERY]]
    return pd.concat(rows, ignore_index=True)


def month_result(battery: dict) -> dict:
    """MonthResult: the test month with the baseline, ML without battery, the product and the hourly
    ceiling for the given battery (as the earlier Streamlit app's "whole month" button, plus the perfect-demand
    no-battery run that the ceiling's battery value needs). Inventory-adjusted like the backtest."""
    p = periods()
    dates = rb.dates_between(p["test_start"], p["test_end"])
    bat = battery_params(battery)
    sell = bool(battery.get("allow_sell", False))
    daily = [_month_no_battery(sell)]
    for s in [PRODUCT, CEILING]:
        daily.append(rb.run_strategy(dates, s, battery=bat, allow_sell=sell)[0])
    daily = pd.concat(daily, ignore_index=True)
    daily.insert(1, "split", "test")
    summ = rb.summarise(daily, n_boot=0).set_index("strategy")
    prod, ceil = summ.loc[PRODUCT], summ.loc[CEILING]
    return {
        "days": int(prod["days"]),
        "baseline_cost_chf": req(summ.loc[BASELINE, "total_cost_adj_chf"], chf),
        "product_cost_chf": req(prod["total_cost_adj_chf"], chf),
        "no_battery_cost_chf": req(summ.loc[NO_BATTERY, "total_cost_adj_chf"], chf),
        "ceiling_cost_chf": req(ceil["total_cost_adj_chf"], chf),
        "saving_vs_baseline_chf": req(prod["saving_vs_baseline_adj_chf"], chf),
        "battery_value_chf": req(prod["battery_value_adj_chf"], chf),
        "ceiling_battery_value_chf": req(ceil["battery_value_adj_chf"], chf),
        "cycles": req(prod["cycles"], frac),
    }


# ---------------------------------------------------------------------------
# meta.json
# ---------------------------------------------------------------------------
def _input_stamp() -> str:
    """Newest modification time of the main inputs (keeps the output deterministic)."""
    files = [REPORTS / "backtest.csv", REPORTS / "backtest_summary.csv", REPORTS / "predictions_demand.parquet",
             REPORTS / "predictions_price.parquet", REPORTS / "decision_tuning.csv",
             ROOT / load_config()["paths"]["features"]]
    t = max(f.stat().st_mtime for f in files if f.exists())
    return dt.datetime.fromtimestamp(int(t), tz=dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_meta() -> dict:
    cfg = load_config()
    dec = rb.tuned_decision()
    s = pd.read_csv(REPORTS / "backtest_summary.csv")
    return {
        "generated_at": _input_stamp(),
        "company": COMPANY,
        "forecast_time_local": cfg["auction"]["forecast_time_local"],
        "gate_closure_local": cfg["auction"]["gate_closure_local"],
        "battery": battery_json(default_battery_settings()),
        "imbalance": {"shortage_price_factor": float(cfg["imbalance"]["shortage_price_factor"]),
                      "surplus_price_factor": float(cfg["imbalance"]["surplus_price_factor"])},
        "decision": {"description": dec.describe(), "plan_resolution": dec.plan_resolution,
                     "charge_limit_factor": float(dec.charge_limit_factor)},
        "demand_source": str(s["demand_source"].iloc[0]),
        "price_source": str(s["price_source"].iloc[0]),
        "days": [{"date": str(d), "split": sp, **{k: v for k, v in day_info(d).items()
                                                   if k in ("weekday", "is_holiday", "is_weekend", "hours")}}
                 for d, sp in export_dates()],
        "block_labels": block_labels(),
    }


# ---------------------------------------------------------------------------
# backtest.json
# ---------------------------------------------------------------------------
def _split_label(split: str) -> str:
    p = periods()
    if split == "test":
        return f"{pd.Timestamp(p['test_start']):%B %Y} (test)"
    if split == "val":
        return f"{pd.Timestamp(p['val_start']):%B %Y} (validation)"
    return f"{pd.Timestamp(p['rolling_start']):%b %Y} – {pd.Timestamp(p['train_end']):%b %Y} (rolling)"


def build_backtest() -> dict:
    summ = pd.read_csv(REPORTS / "backtest_summary.csv")
    dec = pd.read_csv(REPORTS / "backtest_decomposition.csv").set_index("split")
    ci = pd.read_csv(REPORTS / "backtest_ci_sensitivity.csv")
    daily = backtest_daily()
    splits = []
    for split in ["test", "val", "rolling"]:
        s = summ[summ["split"] == split].set_index("strategy")
        if s.empty:
            continue
        rows = []
        for key, name, kind, note in STRATEGIES:
            if key not in s.index:
                continue
            r = s.loc[key]
            base = key == BASELINE
            rows.append({
                "key": key, "name": name, "note": note, "kind": kind,
                "total_cost_chf": req(r["total_cost_adj_chf"], chf),
                "saving_vs_baseline_chf": req(r["saving_vs_baseline_adj_chf"], chf),
                "saving_ci_low_chf": None if base else chf(r["saving_adj_ci_low_chf"]),
                "saving_ci_high_chf": None if base else chf(r["saving_adj_ci_high_chf"]),
                "imbalance_penalty_chf": req(r["imbalance_penalty_chf"], chf),
                "wear_cost_chf": req(r["wear_cost_chf"], chf),
                "cycles": req(r["cycles"], frac),
                "pct_of_ceiling": num(r["pct_perfect_captured"], 2),
            })
        d = dec.loc[split]
        decomposition = {k: req(d[k], chf) for k in [
            "total_saving_chf", "demand_forecast_part_chf", "battery_part_chf", "block_default_battery_part_chf",
            "tuning_and_shaping_part_chf", "ceiling_total_saving_chf", "ceiling_battery_value_chf"]}
        decomposition["pct_ceiling_captured_total"] = req(d["pct_ceiling_captured_total"], num, 2)
        decomposition["pct_ceiling_battery_value_captured"] = req(d["pct_ceiling_battery_value_captured"], num, 2)
        for k in ["finer_dispatch_part_chf", "interday_flexibility_part_chf"]:
            decomposition[k] = chf(d[k]) if k in d else None
        c = ci[(ci["split"] == split) & (ci["strategy"] == PRODUCT)]
        ci_obj = None
        if len(c):
            c = c.iloc[0]
            ci_obj = {"independent_low": req(c["ci_independent_days_low_chf"], chf),
                      "independent_high": req(c["ci_independent_days_high_chf"], chf),
                      "block_low": req(c["ci_block_low_chf"], chf), "block_high": req(c["ci_block_high_chf"], chf),
                      "lag1_autocorr": req(c["lag1_autocorr_daily_saving"], frac)}
        dd = daily[daily["split"] == split].pivot_table(index="delivery_date", columns="strategy",
                                                        values="total_cost_chf").sort_index()
        dates = [str(x) for x in dd.index]
        series = [{"key": k, "name": STRATEGY_NAMES[k],
                   "values": [req(v, chf) for v in (dd[BASELINE] - dd[k]).cumsum()]}
                  for k in CUMULATIVE_KEYS if k in dd]
        daily_parts = [{"date": str(i), "demand_part_chf": req(dd.loc[i, BASELINE] - dd.loc[i, NO_BATTERY], chf),
                        "battery_part_chf": req(dd.loc[i, NO_BATTERY] - dd.loc[i, PRODUCT], chf)} for i in dd.index]
        splits.append({
            "split": split, "label": _split_label(split), "out_of_sample": split == "test",
            "days": int(s.loc[PRODUCT, "days"]), "strategies": rows, "decomposition": decomposition,
            "ci": ci_obj, "cumulative": {"dates": dates, "series": series}, "daily": daily_parts,
        })

    bs = pd.read_csv(REPORTS / "backtest_battery_sensitivity.csv")
    piv = bs.pivot_table(index=["power_mw", "capacity_mwh"], columns="strategy", values="battery_value_chf")
    battery_size = [{"power_mw": num(p, 3), "capacity_mwh": num(c, 3),
                     "ml_battery_value_chf": req(r[PRODUCT], chf), "ceiling_battery_value_chf": req(r[CEILING], chf)}
                    for (p, c), r in piv.sort_index().iterrows()]

    pe = pd.read_csv(REPORTS / "backtest_price_error_sensitivity.csv")
    noise = pe[pe["forecast"] == "noise"].groupby("sigma").agg(
        mae=("price_mae_eur_mwh", "mean"), lost=("lost_saving_chf", "mean")).reset_index().sort_values("sigma")

    def _pe(key):
        r = pe[pe["forecast"] == key].iloc[0]
        return {"mae_eur_mwh": req(r["price_mae_eur_mwh"], eur), "lost_chf": req(r["lost_saving_chf"], chf)}

    price_error = {"points": [{"mae_eur_mwh": req(r.mae, eur), "lost_chf": req(r.lost, chf)} for r in noise.itertuples()],
                   "slope_chf_per_eur": req(pe["slope_chf_per_eur"].iloc[0], chf),
                   "ml": _pe("ml"), "naive": _pe("naive")}

    ds = pd.read_csv(REPORTS / "backtest_decision_sensitivity.csv")
    imb = []
    for r in ds[ds["parameter"] == "imbalance_factors"].itertuples():
        sf, uf = (float(x) for x in str(r.value).split("/"))
        imb.append({"shortage_factor": sf, "surplus_factor": uf,
                    "total_saving_chf": req(r.saving_ml_battery_vs_baseline_chf, chf),
                    "demand_part_chf": req(r.demand_forecast_part_chf, chf),
                    "battery_part_chf": req(r.battery_value_ml_chf, chf)})
    imb.sort(key=lambda x: x["shortage_factor"])
    cfg_imb = load_config()["imbalance"]
    d = dec.loc["test"]
    ref = [x for x in imb if x["shortage_factor"] == cfg_imb["shortage_price_factor"]
           and x["surplus_factor"] == cfg_imb["surplus_price_factor"]]
    assert len(ref) == 1, "no imbalance sensitivity row for the configured factors"
    for k, col in [("total_saving_chf", "total_saving_chf"), ("demand_part_chf", "demand_forecast_part_chf"),
                   ("battery_part_chf", "battery_part_chf")]:
        assert abs(ref[0][k] - d[col]) < 1.0, f"imbalance sensitivity {k} differs from the decomposition"
    return {"splits": splits, "battery_size": battery_size, "price_error": price_error, "imbalance": imb}


# ---------------------------------------------------------------------------
# models.json
# ---------------------------------------------------------------------------
def _settings_from_notes(target: str) -> dict:
    t = (REPORTS / f"model_notes_{target}.md").read_text(encoding="utf-8")
    m = re.search(r"Settings: `(\{.*?\})`", t)
    return json.loads(m.group(1)) if m else {}


def feature_label(f: str) -> str:
    if f not in FEATURE_LABELS:
        raise KeyError(f"no plain-language label for feature {f!r}: add it to FEATURE_LABELS")
    return FEATURE_LABELS[f]


def _best_description(target: str, m: pd.DataFrame) -> str:
    st = _settings_from_notes(target)
    a = m[(m["block"].astype(str) == "all") & (m["split"] == "test")].set_index("model")
    lw = st.get("linear_weight")
    seeds = st.get("n_seeds")
    blend = (f"{seeds} LightGBM runs with different seeds are averaged and blended "
             f"{round(100 * (1 - lw))} / {round(100 * lw)} with a ridge regression") if lw is not None else \
        "LightGBM is blended with a ridge regression"
    if target == "demand":
        first = ("It starts from the demand of the same block on the last known day and LightGBM learns how much "
                 f"higher or lower each block of tomorrow will be; {blend}.")
        second = (f"In the test month it is off by {a.loc['best', 'mae']:.2f} MW per block on average "
                  f"({a.loc['best', 'mape_or_smape']:.2f} % MAPE), against {a.loc['naive', 'mae']:.2f} MW "
                  "for last week's value.")
    else:
        refit = st.get("refit_every_days")
        first = ("It starts from a price already known, the mean Swiss price of day D plus the usual gap of each "
                 f"block to the day mean over the last 7 days, and LightGBM learns the change from it; {blend}"
                 + (f", refit every {refit} days." if refit else "."))
        second = (f"In the test month it is off by {a.loc['best', 'mae']:.2f} EUR/MWh per block on average "
                  f"({a.loc['best', 'mape_or_smape']:.2f} % sMAPE), against {a.loc['naive', 'mae']:.2f} EUR/MWh "
                  "for last week's price.")
    return first + " " + second


def build_model(target: str) -> dict:
    m = pd.read_csv(REPORTS / f"metrics_{target}.csv")
    unit = "MW" if target == "demand" else "EUR/MWh"
    rnd = mw if target == "demand" else eur
    a = m[m["block"].astype(str) == "all"]
    ladder = []
    for mod, name in MODEL_NAMES.items():
        g = a[a["model"] == mod].set_index("split")
        if "test" not in g.index:
            continue
        ladder.append({"model": mod, "name": name, "val_mae": req(g.loc["val", "mae"], rnd),
                       "test_mae": req(g.loc["test", "mae"], rnd),
                       "test_ci_low": req(g.loc["test", "mae_ci_low"], rnd),
                       "test_ci_high": req(g.loc["test", "mae_ci_high"], rnd),
                       "test_pct": req(g.loc["test", "mape_or_smape"], num, 2),
                       "rolling_mae": rnd(g.loc["rolling", "mae"]) if "rolling" in g.index else None})
    t = m[(m["split"] == "test") & (m["block"].astype(str) != "all")].copy()
    t["block"] = t["block"].astype(int)
    labels = block_labels()
    by_block = []
    for b in range(6):
        g = t[t["block"] == b].set_index("model")
        by_block.append({"block": b, "label": labels[b], "best_mae": req(g.loc["best", "mae"], rnd),
                         "naive_mae": req(g.loc["naive", "mae"], rnd)})
    imp = pd.read_csv(REPORTS / f"importance_{target}.csv").sort_values("mae_increase", ascending=False,
                                                                        kind="stable").head(15)
    importance = [{"feature": r.feature, "label": feature_label(r.feature), "value": req(r.mae_increase, num, 4)}
                  for r in imp.itertuples()]
    grp = pd.read_csv(REPORTS / f"importance_groups_{target}.csv").sort_values("mae_increase", ascending=False,
                                                                               kind="stable")
    groups = [{"group": r.feature, "value": req(r.mae_increase, num, 4)} for r in grp.itertuples()]
    p = pd.read_parquet(REPORTS / f"predictions_{target}.parquet")
    p = p[p["split"] == "test"].copy()
    p["delivery_date"] = pd.to_datetime(p["delivery_date"].astype(str)).dt.date
    p = p.drop_duplicates(["delivery_date", "block"], keep="last").sort_values(["delivery_date", "block"])
    series = [{"date": str(r.delivery_date), "block": int(r.block), "actual": req(r.y_true, rnd),
               "best": req(r.pred_best, rnd), "naive": req(r.pred_naive, rnd),
               "q10": rnd(getattr(r, "pred_q10", np.nan)), "q90": rnd(getattr(r, "pred_q90", np.nan))}
              for r in p.itertuples()]
    return {"target": target, "unit": unit, "pct_metric": "MAPE" if target == "demand" else "sMAPE",
            "best_description": _best_description(target, m), "ladder": ladder, "by_block": by_block,
            "importance": importance, "groups": groups, "test_series": series}


# ---------------------------------------------------------------------------
# drivers.json
# ---------------------------------------------------------------------------
DRIVER_COLS = ["delivery_date", "block", "hours_in_block", "demand_mw", "price_eur_mwh", "temp_c_obs",
               "radiation_wm2_obs", "ev_count_city", "is_weekend", "is_holiday", "is_working_day", "event_size",
               "weekday", "month", "gas_ttf_d_1", "price_mean_last_28d", "eu_wind100_ms_de_north_safe_day",
               "eu_wind100_ms_de_northeast_safe_day", "eu_wind100_ms_de_central_safe_day"]


def _binned(x: pd.Series, y: pd.Series, bins, min_n: int = 10) -> list[tuple]:
    """(bin, mean, n) for bins with at least ``min_n`` values (as app/charts.binned_line)."""
    cut = pd.cut(x, bins)
    g = y.groupby(cut, observed=True).agg(["mean", "size"])
    g = g[g["size"] >= min_n]
    return [(iv, float(r["mean"]), int(r["size"])) for iv, r in g.iterrows()]


def build_drivers() -> dict:
    import pyarrow.parquet as pq

    p = periods()
    end = pd.Timestamp(p["test_end"])
    have = set(pq.ParquetFile(ROOT / load_config()["paths"]["features"]).schema.names)
    f = pd.read_parquet(ROOT / load_config()["paths"]["features"], columns=[c for c in DRIVER_COLS if c in have])
    f["date"] = pd.to_datetime(f["delivery_date"].astype(str))
    f = f[(f["date"] <= end)]
    fd = f[f["demand_mw"].notna()]
    labels = block_labels()

    # demand vs temperature, working days 2024-2026, 2 degree bins per block
    r24 = fd[(fd["date"].dt.year >= 2024) & (fd["is_working_day"] == 1)]
    temp = []
    for b in range(6):
        g = r24[r24["block"] == b].dropna(subset=["temp_c_obs"])
        pts = [{"temp_c": num(iv.mid, 1), "demand_mw": req(m, mw), "n": n}
               for iv, m, n in _binned(g["temp_c_obs"], g["demand_mw"], np.arange(-15, 37, 2))]
        temp.append({"block": b, "label": labels[b], "points": pts})

    # midday demand vs radiation, block 12-16, working days, April-September
    g = r24[(r24["block"] == 3) & r24["month"].between(4, 9)].dropna(subset=["radiation_wm2_obs"])
    radiation = [{"radiation_wm2": num(iv.mid, 1), "demand_mw": req(m, mw), "n": n}
                 for iv, m, n in _binned(g["radiation_wm2_obs"], g["demand_mw"], np.arange(0, 1001, 50))]

    # hourly profiles
    h = pd.read_parquet(PROCESSED / "hourly_actuals.parquet", columns=["delivery_date", "hour_local", "demand_mw",
                                                                      "price_eur_mwh", "timestamp_utc"])
    h["date"] = pd.to_datetime(h["delivery_date"].astype(str))
    h = h[h["date"] <= end]
    days = f.drop_duplicates("delivery_date").set_index("date")
    last12 = h[h["date"] > end - pd.Timedelta(days=365)].copy()
    hol = last12["date"].map(days["is_holiday"]).fillna(0).astype(bool)
    wd = last12["date"].dt.day_of_week
    last12["daytype"] = np.where(hol, "Public holiday", np.where(wd == 5, "Saturday",
                                                                  np.where(wd == 6, "Sunday", "Working day")))
    profile = []
    for dtp in ["Working day", "Saturday", "Sunday", "Public holiday"]:
        g = last12[last12["daytype"] == dtp].groupby("hour_local")["demand_mw"].mean().sort_index()
        profile.append({"daytype": dtp, "hours": [int(x) for x in g.index], "demand_mw": [req(v, mw) for v in g]})

    # EVs vs night demand, per year
    ev = []
    night = fd[fd["block"] == 0].groupby(fd["date"].dt.year)["demand_mw"].mean()
    evc = days.groupby(days.index.year)["ev_count_city"].mean()
    for y in sorted(set(night.index) & set(evc.dropna().index)):
        ev.append({"year": int(y), "ev_count": int(round(evc[y])), "night_demand_mw": req(night[y], mw)})

    def _profile(dates_set) -> tuple[list, list]:
        g = h[h["date"].isin(dates_set)].groupby("hour_local")["demand_mw"].mean().sort_index()
        return [int(x) for x in g.index], [req(v, mw) for v in g]

    # Street Parade 2026 vs nearby normal Saturdays
    ev_d = pd.read_parquet(PROCESSED / "events_daily.parquet", columns=["date", "event_name"])
    ev_d["date"] = pd.to_datetime(ev_d["date"].astype(str))
    year = end.year
    sp = ev_d[(ev_d["event_name"].fillna("").str.contains("Street Parade")) & (ev_d["date"].dt.year == year)]["date"]
    street = []
    if len(sp):
        pday = sp.iloc[0]
        sat = days[(days.index.day_of_week == 5) & (days["is_holiday"] == 0) & (days["event_size"].fillna(0) == 0)]
        others = [x for x in sat.index if 0 < abs((x - pday).days) <= 21]
        hh, vv = _profile({pday})
        street.append({"label": f"Street Parade, {pday.day} {MONTHS[pday.month - 1]} {pday.year}", "hours": hh,
                       "demand_mw": vv})
        hh, vv = _profile(set(others))
        street.append({"label": f"Other Saturdays within 3 weeks (mean of {len(others)})", "hours": hh,
                       "demand_mw": vv})

    # autumn school holidays vs other October working days (test year)
    cal = pd.read_parquet(PROCESSED / "calendar_daily.parquet", columns=["date", "school_holiday_type"])
    cal["date"] = pd.to_datetime(cal["date"].astype(str))
    autumn = set(cal.loc[cal["school_holiday_type"].astype(str) == "autumn", "date"])
    octw = [x for x in days.index if x.year == year and x.month == 10 and days.loc[x, "is_working_day"] == 1]
    a_days = {x for x in octw if x in autumn}
    o_days = {x for x in octw if x not in autumn}
    school = []
    for lbl, ds_ in [(f"Autumn school holidays, working days ({len(a_days)})", a_days),
                     (f"Other October working days ({len(o_days)})", o_days)]:
        hh, vv = _profile(ds_)
        school.append({"label": lbl, "hours": hh, "demand_mw": vv})

    # price heatmap, last 24 months
    start24 = (end - pd.DateOffset(months=24)).to_period("M") + 1
    fp = f[f["date"].dt.to_period("M") >= start24]
    piv = fp.pivot_table(index=fp["date"].dt.to_period("M"), columns="block", values="price_eur_mwh", aggfunc="mean")
    heat = {"months": [str(m) for m in piv.index], "blocks": labels,
            "values": [[req(piv.loc[m, b], eur) for b in range(6)] for m in piv.index]}

    # daily prices for wind and gas
    fpr = f.dropna(subset=["price_eur_mwh"])
    w = fpr["hours_in_block"].astype(float)
    day = pd.DataFrame({"price": (fpr["price_eur_mwh"] * w).groupby(fpr["date"]).sum() / w.groupby(fpr["date"]).sum()})
    day = day.join(days[["gas_ttf_d_1", "price_mean_last_28d"]])
    wind_cols = [c for c in f.columns if c.startswith("eu_wind100_ms_de_")]
    day["wind"] = days[wind_cols].mean(axis=1)
    g = day.assign(dev=day["price"] - day["price_mean_last_28d"]).dropna(subset=["wind", "dev"])
    g = g[g.index > end - pd.Timedelta(days=730)]
    wind = [{"wind_bin": f"{iv.left:g}–{iv.right:g} m/s", "price_vs_recent_eur": req(m, eur), "n": n}
            for iv, m, n in _binned(g["wind"], g["dev"], np.arange(0, 21, 1))]
    mo = day.dropna(subset=["gas_ttf_d_1", "price"]).resample("MS").mean()
    gas = [{"month": f"{i:%Y-%m}", "gas_eur_mwh": req(r.gas_ttf_d_1, eur), "price_eur_mwh": req(r.price, eur)}
           for i, r in mo.iterrows() if np.isfinite(r.gas_ttf_d_1) and np.isfinite(r.price)]

    # hours with a negative Swiss price per year
    hp = h.dropna(subset=["price_eur_mwh"])
    neg = (hp["price_eur_mwh"] < 0).groupby(hp["date"].dt.year).sum()
    negative = [{"year": int(y), "hours": int(v)} for y, v in neg.sort_index().items()]

    return {"temp_demand": temp, "radiation_demand": radiation, "profile": profile, "ev": ev,
            "street_parade": street, "school_holiday": school, "price_heatmap": heat, "wind_price": wind,
            "gas_price": gas, "negative_hours": negative}


# ---------------------------------------------------------------------------
# method.json
# ---------------------------------------------------------------------------
def _plain(s: str) -> str:
    s = re.sub(r"\*\*|__|`", "", s)
    s = re.sub(r"(?<!\w)\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"\1", s)
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    return re.sub(r"\s+", " ", s).strip()


def _table_rows(block: str) -> list[list[str]]:
    rows = []
    for line in block.splitlines():
        line = line.strip()
        if not line.startswith("|") or re.match(r"^\|[\s\-:|]+\|$", line):
            continue
        rows.append([c.strip() for c in line.strip("|").split("|")])
    return rows[1:]  # without the header


def _sentences(text: str, n: int) -> str:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9(])", text)
    return " ".join(parts[:n]).strip()


def build_sources() -> list[dict]:
    t = (DOCS / "data_sources.md").read_text(encoding="utf-8")
    m = re.search(r"^## Summary\s*$(.*?)(?=^---|^## )", t, flags=re.M | re.S)
    out = []
    for r in _table_rows(m.group(1)):
        if len(r) < 5:
            continue
        inp, src, step, period, access = (_plain(x) for x in r[:5])
        out.append({"input": inp, "source": src, "step": step, "note": f"{period}; {access}"})
    return out


def build_time_rules() -> list[dict]:
    a = load_config()["auction"]
    ft = a["forecast_time_local"]
    return [
        {"input": "Zurich demand", "known": "Up to the end of day D−1: the DSO reads its own meters (the public "
                                            "ewz file lags about one and a half days)."},
        {"input": "Swiss day-ahead prices", "known": "All hours of day D (that auction was held on D−1); no price "
                                                     "of the delivery day D+1."},
        {"input": "Neighbour prices (DE, FR, AT, IT-North)", "known": "All hours of day D; the coupled European "
                                                                      "auction for D+1 closes only at 12:00."},
        {"input": "Gas, CO₂ and EUR/CHF", "known": f"Last close published before {ft} on day D, i.e. the "
                                                   "values of D−1 (gas from 18:00, ECB rate from 16:00)."},
        {"input": "Reservoir levels", "known": "The weekly level of Sunday is published on Thursday by 23:59 "
                                               "and first used in Friday's forecast."},
        {"input": "Weather forecast for D+1", "known": f"The model run available by {ft} on day D under the "
                                                       "assumed release delays (ICON 4 h, ECMWF 8 h, JMA 6 h); "
                                                       "for most hours the run from the day before."},
        {"input": "Observed weather", "known": "Hours that end by 09:00 on day D (one hour publication margin)."},
        {"input": "Swiss load and generation", "known": "Up to the end of day D−1."},
        {"input": "Electric cars and charging", "known": "Only figures already published on day D (yearly car "
                                                         "count, monthly charging data with a delay)."},
        {"input": "Calendar, holidays, events", "known": "Known in advance (announced months ahead)."},
    ]


def build_limitations() -> list[dict]:
    cfg = load_config()
    dec = pd.read_csv(REPORTS / "backtest_decomposition.csv").set_index("split").loc["test"]
    ds = pd.read_csv(REPORTS / "backtest_decision_sensitivity.csv")
    ci = pd.read_csv(REPORTS / "backtest_ci_sensitivity.csv").set_index("split").loc["test"]
    bat = BatteryParams.from_config()
    imb = cfg["imbalance"]
    sf = float(imb["shortage_price_factor"])
    half = 1 + (sf - 1) / 2
    hrow = ds[(ds["parameter"] == "imbalance_factors")
              & (ds["value"].astype(str) == f"{half:g}/{1 - (sf - 1) / 2:g}")]
    share = 100 * dec["demand_forecast_part_chf"] / dec["total_saving_chf"]
    pen = f"±{100 * (sf - 1):.0f} %"
    text = (f"The penalty for being off (shortfall at p + {sf - 1:g}·|p|, surplus at p − {1 - imb['surplus_price_factor']:g}·|p|) "
            f"is our assumption, and it drives about {share:.0f} % of the October saving through the better demand "
            "forecast.")
    if len(hrow):
        h = hrow.iloc[0]
        text += (f" With half the penalty (±{100 * (half - 1):.0f} % instead of {pen}) the saving falls from "
                 f"CHF {dec['total_saving_chf']:,.0f} to CHF {h['saving_ml_battery_vs_baseline_chf']:,.0f}; the "
                 f"battery part stays at about CHF {h['battery_value_ml_chf']:,.0f}.")
    p = periods()
    cyc = bat.max_cycles_per_day * bat.usable_mwh
    return [
        {"title": "Assumed imbalance penalty", "text": text},
        {"title": "Only one test month",
         "text": f"October 2026 ({int(ci['days'])} days) is the only clean test. Similar days come in runs, so "
                 f"the 95 % interval of the saving is wide: CHF {ci['ci_block_low_chf']:,.0f} to "
                 f"CHF {ci['ci_block_high_chf']:,.0f} with a 7-day block bootstrap."},
        {"title": "Validation month was used for tuning",
         "text": f"The decision rules were tuned on {p['rolling_start']} to {p['train_end']} plus September up to "
                 f"{rb.tuning_cutoff():%d %B}, so the September and rolling results are not out-of-sample tests of "
                 "the rules (the forecasts themselves are)."},
        {"title": "Fictional battery and company",
         "text": f"{COMPANY} and its {bat.power_mw:g} MW / {bat.capacity_mwh:g} MWh battery do not exist. The "
                 "Zurich demand and the Swiss prices are real."},
        {"title": "Observed weather in older training years",
         "text": "No forecast archive exists before January 2024, so older training rows use observed weather "
                 "instead of forecasts. The validation and test months use real forecasts only."},
        {"title": "One weather pre-processing choice saw October",
         "text": "The choice between two temperature-correction methods compared errors on September and October "
                 "weather. The two methods differ by about 0.01 °C and the choice never saw demand or prices."},
        {"title": "Cycle definition",
         "text": f"One cycle means {cyc:g} MWh delivered to the grid per day (the project brief's definition). "
                 f"After discharge losses a full swing of the usable stored energy delivers only "
                 f"{bat.usable_mwh * bat.eta_discharge:.2f} MWh, so the battery may do slightly more than one "
                 "physical cycle."},
        {"title": "Unofficial gas price source",
         "text": "The gas price comes from Yahoo Finance (TTF front-month future), an unofficial source for "
                 "personal and educational use, because the university's data terminal export was not available."},
        {"title": "Demand known up to yesterday",
         "text": "We assume the DSO knows its own demand up to the end of D−1 because it reads its own meters. "
                 "The public ewz file comes about one and a half days later."},
        {"title": "No intraday market",
         "text": "Only the day-ahead auction with hourly bids is modelled. Forecast errors are settled as "
                 "imbalance; correcting them on the intraday market or with 15-minute products is not modelled."},
        {"title": "Price taker",
         "text": "We assume our bids do not move the auction price and that a charge bid clears fully or not at "
                 "all. This is why the battery value grows almost in proportion to the battery size."},
    ]


def build_reviews() -> list[dict]:
    t = (DOCS / "review_log.md").read_text(encoding="utf-8")
    out = []
    for m in re.finditer(r"^## (.+?)\s*$(.*?)(?=^## |\Z)", t, flags=re.M | re.S):
        phase = _plain(m.group(1)).replace("–", "–")
        phase = re.sub(r"\s*\(.*?\)\s*$", "", phase)
        for r in _table_rows(m.group(2)):
            if len(r) < 2:
                continue
            finding, decision = _plain(r[0]), _plain(r[1])
            if finding.lower() == "finding":
                continue
            finding = re.sub(r"^[Mm]\d+\s+", "", finding)
            out.append({"phase": phase, "finding": _sentences(finding, 2), "decision": _sentences(decision, 2)})
    return out


def build_method() -> dict:
    return {"sources": build_sources(), "time_rules": build_time_rules(), "limitations": build_limitations(),
            "reviews": build_reviews()}


# ---------------------------------------------------------------------------
# write everything
# ---------------------------------------------------------------------------
def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    txt = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    path.write_text(txt + "\n", encoding="utf-8")


def export_all(out: Path = DEFAULT_OUT) -> dict:
    out = Path(out)
    t0 = time.time()
    days = export_days()
    dd = out / "days"
    dd.mkdir(parents=True, exist_ok=True)
    for old in dd.glob("*.json"):
        if old.stem not in days:
            old.unlink()
    for d, plan in days.items():
        write_json(dd / f"{d}.json", plan)
    write_json(out / "meta.json", build_meta())
    write_json(out / "backtest.json", build_backtest())
    write_json(out / "models.json", {"demand": build_model("demand"), "price": build_model("price")})
    write_json(out / "drivers.json", build_drivers())
    write_json(out / "method.json", build_method())
    size = sum(f.stat().st_size for f in out.rglob("*.json"))
    return {"days": len(days), "bytes": size, "seconds": time.time() - t0}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Export the JSON data of the web app.")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="output folder (default web/public/data)")
    args = ap.parse_args(argv)
    info = export_all(Path(args.out))
    print(f"Wrote {info['days']} day plans + 5 files to {args.out} "
          f"({info['bytes'] / 1024:.0f} KB, {info['seconds']:.1f} s)")


if __name__ == "__main__":
    main()
