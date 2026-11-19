"""Checks of the processed target files (D1). Reads processed parquet only, no network."""
from __future__ import annotations

import pandas as pd
import pytest

from src.config import path

P = path("processed")
TZ = "Europe/Zurich"
PERIOD_START = pd.Timestamp("2019-01-01", tz=TZ).tz_convert("UTC")      # first local hour of 2019
PERIOD_END = pd.Timestamp("2026-11-01", tz=TZ).tz_convert("UTC")        # end of the test month


def _load(name: str) -> pd.DataFrame:
    f = P / name
    if not f.exists():
        pytest.skip(f"{f} missing; run the loader first")
    return pd.read_parquet(f)


def _check_time_axis(df: pd.DataFrame, freq: str) -> None:
    ts = df["timestamp_utc"]
    assert str(ts.dt.tz) == "UTC"
    assert ts.dtype == "datetime64[ns, UTC]"
    assert ts.is_monotonic_increasing
    assert not ts.duplicated().any()
    # complete regular grid (no silently missing rows)
    steps = ts.diff().dropna().unique()
    assert len(steps) == 1 and steps[0] == pd.Timedelta(freq)


def _in_period(df: pd.DataFrame) -> pd.DataFrame:
    return df[(df["timestamp_utc"] >= PERIOD_START) & (df["timestamp_utc"] < PERIOD_END)]


# ------------------------------------------------------------------ demand
def test_demand_15min():
    df = _load("demand_ewz.parquet")
    _check_time_axis(df, "15min")
    assert df["timestamp_utc"].min() <= PERIOD_START
    assert df["timestamp_utc"].max() >= PERIOD_END - pd.Timedelta("15min")
    part = _in_period(df)
    assert len(part) == (PERIOD_END - PERIOD_START) / pd.Timedelta("15min")
    assert part["load_kwh_15min"].isna().mean() < 0.005
    # 15-min energy in Zurich: roughly 40,000 – 130,000 kWh (160 – 520 MW)
    assert part["load_kwh_15min"].between(30_000, 150_000).all()
    assert set(df["status"].dropna().unique()) <= {"W", "E", "F", "N", "G"}
    # filled rows are flagged and are only a tiny share
    assert df.loc[df["is_filled"], "status"].isna().all()
    assert df["is_filled"].mean() < 0.005


def test_demand_hourly():
    df = _load("demand_ewz_hourly.parquet")
    _check_time_axis(df, "1h")
    part = _in_period(df)
    assert len(part) == (PERIOD_END - PERIOD_START) / pd.Timedelta(hours=1)
    assert part["load_mw"].isna().mean() < 0.005
    assert part["load_mw"].between(120, 600).all()
    assert (part["n_intervals"] == 4).all()
    assert part["share_non_final"].between(0, 1).all()


def test_demand_hourly_matches_15min():
    q = _load("demand_ewz.parquet")
    h = _load("demand_ewz_hourly.parquet")
    q = q.assign(hour=q["timestamp_utc"].dt.floor("h"))
    mw = q.groupby("hour")["load_kwh_15min"].sum() / 1000  # MWh in the hour = mean MW
    j = h.set_index("timestamp_utc")["load_mw"].dropna()
    assert (mw.reindex(j.index) - j).abs().max() < 1e-6


def test_demand_dst_days_have_23_and_25_hours():
    h = _load("demand_ewz_hourly.parquet")
    per_day = h.groupby(h["timestamp_utc"].dt.tz_convert(TZ).dt.date).size()
    assert per_day[pd.Timestamp("2026-03-29").date()] == 23
    assert per_day[pd.Timestamp("2026-10-25").date()] == 25
    assert per_day[pd.Timestamp("2026-10-01").date()] == 24


def test_demand_daily_profile_is_plausible():
    """Night (local 02–04 h) must be lower than late morning (local 10–12 h) on working days."""
    h = _load("demand_ewz_hourly.parquet")
    loc = h["timestamp_utc"].dt.tz_convert(TZ)
    wd = h[loc.dt.day_of_week < 5]
    hr = loc[loc.dt.day_of_week < 5].dt.hour
    assert wd.loc[hr.between(2, 3), "load_mw"].mean() < 0.8 * wd.loc[hr.between(10, 11), "load_mw"].mean()


# ------------------------------------------------------------------ price
def test_price_ch():
    df = _load("price_ch_hourly.parquet")
    _check_time_axis(df, "1h")
    assert df["timestamp_utc"].min() <= PERIOD_START
    assert df["timestamp_utc"].max() >= PERIOD_END
    part = _in_period(df)
    assert len(part) == (PERIOD_END - PERIOD_START) / pd.Timedelta(hours=1)
    assert part["price_eur_mwh"].isna().mean() < 0.005
    assert part["price_eur_mwh"].between(-1000, 4000).all()
    # source is hourly until 2026-11-03, 15-min (4 values per hour) afterwards
    assert (part["n_values"] == 1).all()


# ------------------------------------------------------------------ Swiss power
def test_swiss_power():
    df = _load("swiss_power_hourly.parquet")
    _check_time_axis(df, "1h")
    part = _in_period(df)
    assert len(part) == (PERIOD_END - PERIOD_START) / pd.Timedelta(hours=1)
    for c in ["load_mw", "solar_mw"]:
        assert c in df.columns
        assert part[c].isna().mean() < 0.005
    good = part[~part["load_bad"]]
    assert good["load_mw"].between(2000, 15000).all()
    assert part["solar_mw"].min() >= 0 and part["solar_mw"].max() < 10000
    # the known glitch: load after 2026-11-16 must be flagged
    assert df.loc[df["timestamp_utc"] >= pd.Timestamp("2026-11-16", tz="UTC"), "load_bad"].all()


def test_solar_forecast():
    df = _load("swiss_solar_forecast_hourly.parquet")
    _check_time_axis(df, "1h")
    assert df["solar_forecast_mw"].isna().mean() < 0.01
    assert df["solar_forecast_mw"].min() >= 0
