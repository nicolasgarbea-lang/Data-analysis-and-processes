"""Cached data access for the app. Everything is read from files at run time.

Files read (all committed to the repo):
  config.yaml, data/processed/features.parquet, data/processed/hourly_actuals.parquet,
  reports/predictions_{demand,price}.parquet, reports/backtest*.csv, reports/decision_tuning.csv,
  reports/metrics_*.csv, reports/importance_*.csv, reports/importance_groups_*.csv, docs/*.md, docs/*.svg

The planning functions come from ``src.backtest.run_backtest`` (they read the same files).
When a prediction / backtest file appears or changes, the caches are cleared automatically
(every cached function takes ``data_version()`` as an argument).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
DOCS = ROOT / "docs"
PROCESSED = ROOT / "data" / "processed"

from src.backtest import run_backtest as rb  # noqa: E402  (sys.path set by streamlit_app.py)
from src.config import load_config  # noqa: E402
from src.decision.bids import bids_table  # noqa: E402
from src.optimisation.battery_lp import BatteryParams  # noqa: E402

WATCHED = [
    REPORTS / "predictions_demand.parquet",
    REPORTS / "predictions_price.parquet",
    REPORTS / "backtest.csv",
    REPORTS / "backtest_summary.csv",
    REPORTS / "decision_tuning.csv",
    REPORTS / "metrics_price.csv",
    REPORTS / "importance_price.csv",
]


@st.cache_resource
def _last_stamp() -> dict:
    return {"stamp": None}


def data_version() -> tuple:
    """File stamps of the files that can change while the app runs. A change clears the
    lru caches inside ``src.backtest.run_backtest`` so new forecasts are picked up."""
    stamp = tuple((p.name, p.stat().st_mtime_ns if p.exists() else 0) for p in WATCHED)
    holder = _last_stamp()
    if holder["stamp"] is not None and holder["stamp"] != stamp:
        for f in (rb.load_forecasts, rb._forecast_index):
            f.cache_clear()
    holder["stamp"] = stamp
    return stamp


def cfg() -> dict:
    return load_config()


def block_names() -> list[str]:
    return [f"{a:02d}-{b:02d}" for a, b in cfg()["blocks"]]


def periods() -> dict:
    return cfg()["periods"]


def to_date(x) -> dt.date:
    return pd.Timestamp(str(x)).date()


# ---------------------------------------------------------------------------
# status of the inputs
# ---------------------------------------------------------------------------
def sources(version) -> dict:
    """{'demand': 'ml'|'standin', 'price': 'ml'|'standin'} for the live planning."""
    return rb.forecast_sources()


@st.cache_data(show_spinner=False)
def backtest_sources(version) -> dict:
    """Which forecasts the stored backtest files were made with."""
    s = read_csv("backtest_summary.csv", version)
    if s is None or "price_source" not in s:
        return {}
    return {"demand": str(s["demand_source"].iloc[0]), "price": str(s["price_source"].iloc[0])}


@st.cache_data(show_spinner=False)
def read_csv(name: str, version) -> pd.DataFrame | None:
    p = REPORTS / name
    if not p.exists():
        return None
    return pd.read_csv(p)


@st.cache_data(show_spinner=False)
def _read_text(path: str, mtime: int) -> str | None:
    p = ROOT / path
    return p.read_text(encoding="utf-8") if p.exists() else None


def read_text(path: str) -> str | None:
    """Text of a repo file (cached until the file changes), None if it does not exist."""
    p = ROOT / path
    return _read_text(path, p.stat().st_mtime_ns if p.exists() else 0)


# ---------------------------------------------------------------------------
# forecasts and actuals of one day
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def day_forecasts(date_str: str, version) -> pd.DataFrame:
    """Per block: ML demand forecast (MW) + 10/90 band, ML price forecast (EUR/MWh) + band,
    naive forecasts, actual demand and price, hours, EUR/CHF known at forecast time."""
    d = to_date(date_str)
    fc = rb.load_forecasts()
    fc = fc[fc["delivery_date"] == d].sort_values("block").reset_index(drop=True)
    blk = rb.load_data()["blocks"][d]
    out = pd.DataFrame({
        "block": blk["block"].to_numpy(),
        "block_name": block_names()[: len(blk)],
        "hours": blk["hours_in_block"].to_numpy(float),
        "actual_demand_mw": blk["demand_mw"].to_numpy(float),
        "actual_price": blk["price_eur_mwh"].to_numpy(float),
    })
    out["demand_mw"] = fc["demand_ml_mw"].to_numpy(float) if len(fc) else np.nan
    out["price"] = fc["price_ml_eur_mwh"].to_numpy(float) if len(fc) else np.nan
    out["price_q10"] = fc["price_q10_eur_mwh"].to_numpy(float) if len(fc) else np.nan
    out["price_q90"] = fc["price_q90_eur_mwh"].to_numpy(float) if len(fc) else np.nan
    out["demand_naive_mw"] = fc["demand_naive_mw"].to_numpy(float) if len(fc) else np.nan
    out["demand_q10"] = np.nan
    out["demand_q90"] = np.nan
    pf = REPORTS / "predictions_demand.parquet"
    if pf.exists():
        p = pd.read_parquet(pf)
        p["delivery_date"] = pd.to_datetime(p["delivery_date"]).dt.date
        p = p[p["delivery_date"] == d].drop_duplicates("block", keep="last").set_index("block")
        for q in ("q10", "q90"):
            if f"pred_{q}" in p:
                out[f"demand_{q}"] = out["block"].map(p[f"pred_{q}"]).to_numpy(float)
    feats = features_small(version)
    row = feats[feats["delivery_date"] == d]
    out["eurchf_known"] = float(row["eurchf_d_1"].iloc[0]) if len(row) and "eurchf_d_1" in row else np.nan
    return out


@st.cache_data(show_spinner=False)
def selectable_dates(version) -> list[dt.date]:
    """Delivery days of the validation and test months that have data and forecasts."""
    p = periods()
    fc = rb.load_forecasts()
    ok = fc[(fc["demand_source"] != "missing") & (fc["price_source"] != "missing")
            & fc["demand_ml_mw"].notna() & fc["price_ml_eur_mwh"].notna()]
    counts = ok.groupby("delivery_date").size()
    good = set(counts[counts == 6].index)
    days = rb.dates_between(p["val_start"], p["test_end"])
    return [d for d in days if d in good]


@st.cache_data(show_spinner=False)
def carried_soc(date_str: str, version) -> float | None:
    """Charge level at the start of the day in the stored backtest of the product."""
    bt = read_csv("backtest.csv", version)
    if bt is None:
        return None
    r = bt[(bt["strategy"] == rb.PRODUCT) & (bt["delivery_date"].astype(str) == date_str)]
    if len(r) == 0 or not np.isfinite(r["soc_start_mwh"].iloc[0]):
        return None
    return float(r["soc_start_mwh"].iloc[0])


def battery_from(params: dict) -> BatteryParams:
    return BatteryParams(**params)


def default_battery() -> dict:
    return asdict(BatteryParams.from_config())


@st.cache_data(show_spinner=False, max_entries=256)
def plan(date_str: str, strategy: str, battery: tuple, soc_start: float | None, allow_sell: bool,
         version) -> dict:
    """``plan_day`` for one day, turned into plain picklable pieces."""
    bat = battery_from(dict(battery))
    r = rb.plan_day(date_str, strategy, battery=bat, soc_start_mwh=soc_start, allow_sell=allow_sell)
    pl = r["plan"]
    return {
        "plan": pl.copy(),
        "attrs": dict(pl.attrs),
        "plan_periods": r["plan_periods"].copy(),
        "plan_periods_attrs": dict(r["plan_periods"].attrs),
        "hourly": r["hourly"].copy(),
        "bids": bids_table(r["bids"]),
        "settlement": None if r["settlement"] is None else r["settlement"].copy(),
        "summary": r["summary"],
        "decision": r["decision"].describe() if r["decision"] is not None else "",
    }


@st.cache_data(show_spinner=False, max_entries=16)
def month_rerun(battery: tuple, allow_sell: bool, version) -> pd.DataFrame:
    """Test month with the product, the baseline and the ceiling for a custom battery.

    ``run_backtest`` has no ``allow_sell`` argument, so the strategies are run with
    ``run_strategy`` and summarised with the same function as the stored backtest."""
    p = periods()
    bat = battery_from(dict(battery))
    dates = rb.dates_between(p["test_start"], p["test_end"])
    fc_split = rb.load_forecasts().drop_duplicates("delivery_date").set_index("delivery_date")["split"]
    daily = []
    for s in [rb.BASELINE, "ml_no_battery", rb.PRODUCT, rb.CEILING]:
        d, _ = rb.run_strategy(dates, s, battery=bat, allow_sell=allow_sell if rb.uses_battery(s) else None)
        daily.append(d)
    daily = pd.concat(daily, ignore_index=True)
    daily.insert(1, "split", daily["delivery_date"].map(fc_split).fillna("other"))
    return rb.summarise(daily, n_boot=200)


# ---------------------------------------------------------------------------
# data for the driver charts
# ---------------------------------------------------------------------------
FEATURE_COLS = [
    "delivery_date", "block", "hours_in_block", "demand_mw", "price_eur_mwh", "temp_c_obs", "temp_c",
    "radiation_wm2_obs", "radiation_wm2", "ev_count_city", "charging_kw_zh", "is_weekend", "is_holiday",
    "is_school_holiday", "is_working_day", "event_size", "n_events", "weekday", "month", "gas_ttf_d_1",
    "eu_wind100_ms_de_north_safe_day", "eu_wind100_ms_de_northeast_safe_day",
    "eu_wind100_ms_de_central_safe_day", "price_mean_last_28d", "eurchf_d_1", "actual_eurchf",
]


@st.cache_data(show_spinner=False)
def features_small(version=None) -> pd.DataFrame:
    import pyarrow.parquet as pq

    path = PROCESSED / "features.parquet"
    have = set(pq.ParquetFile(path).schema.names)
    f = pd.read_parquet(path, columns=[c for c in FEATURE_COLS if c in have])
    f["delivery_date"] = pd.to_datetime(f["delivery_date"].astype(str)).dt.date
    return f


@st.cache_data(show_spinner=False)
def hourly_actuals() -> pd.DataFrame:
    h = pd.read_parquet(PROCESSED / "hourly_actuals.parquet")
    h["delivery_date"] = pd.to_datetime(h["delivery_date"].astype(str)).dt.date
    return h
