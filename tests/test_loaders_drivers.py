"""Checks of the processed price-driver tables (agent D4). Reads processed parquet only."""
from __future__ import annotations

import pandas as pd
import pytest

from src.config import path

P = path("processed")
START, END = pd.Timestamp("2019-01-01", tz="UTC"), pd.Timestamp("2026-11-01", tz="UTC")


def _read(name: str) -> pd.DataFrame:
    f = P / f"{name}.parquet"
    if not f.exists():
        pytest.skip(f"{f} missing – run the loader first")
    return pd.read_parquet(f)


def _is_utc(s: pd.Series) -> bool:
    return isinstance(s.dtype, pd.DatetimeTZDtype) and str(s.dt.tz) == "UTC"


# ---------- hourly neighbour prices ----------
def test_neighbour_prices():
    df = _read("price_neighbours_hourly")
    assert _is_utc(df.timestamp_utc)
    assert df.timestamp_utc.is_monotonic_increasing and not df.timestamp_utc.duplicated().any()
    assert (df.timestamp_utc.diff().dropna() == pd.Timedelta("1h")).all()
    assert df.timestamp_utc.min() <= START and df.timestamp_utc.max() >= END
    period = df[(df.timestamp_utc >= START) & (df.timestamp_utc < END)]
    for c in ["price_de_eur_mwh", "price_fr_eur_mwh", "price_at_eur_mwh", "price_it_north_eur_mwh"]:
        assert period[c].isna().mean() < 0.005, c
        assert period[c].dropna().between(-600, 4100).all(), c
        assert 30 < period[c].mean() < 200, c


# ---------- daily / weekly tables ----------
DAILY = {
    "gas_ttf_daily": ("gas_ttf_eur_mwh", 2, 400),
    "co2_eua_daily": ("co2_eua_eur_t", 5, 120),
    "eurchf_daily": ("chf_per_eur", 0.85, 1.25),
}


@pytest.mark.parametrize("name", list(DAILY))
def test_daily_tables(name):
    df = _read(name)
    col, lo, hi = DAILY[name]
    d = pd.to_datetime(df["date"])
    assert d.is_monotonic_increasing and not d.duplicated().any()
    assert d.min() <= pd.Timestamp("2019-01-07") and d.max() >= pd.Timestamp("2026-10-30")
    assert df[col].notna().all() and df[col].between(lo, hi).all()
    assert _is_utc(df.available_from_utc)
    # value of a day is only known after that day has started (no same-morning knowledge)
    start_local = d.dt.tz_localize("Europe/Zurich").dt.tz_convert("UTC")
    assert (df.available_from_utc > start_local).all()
    # no long holes inside the period (CO2 has year-end auction breaks up to ~46 days)
    inside = d[(d >= "2019-01-01") & (d <= "2026-10-31")]
    max_gap = 50 if name == "co2_eua_daily" else 6
    assert inside.diff().dt.days.max() <= max_gap


def test_gas_crisis_values_present():
    df = _read("gas_ttf_daily")
    peak = df.loc[pd.to_datetime(df.date).dt.year == 2022, "gas_ttf_eur_mwh"].max()
    assert 250 < peak < 400  # Aug 2022 peak ~340 EUR/MWh


def test_reservoirs():
    df = _read("reservoir_weekly")
    d = pd.to_datetime(df.measure_date)
    assert d.is_monotonic_increasing and not d.duplicated().any()
    assert (d.dt.day_of_week == 0).all()  # file dates are Mondays (= Sunday 24h value)
    assert d.min() <= pd.Timestamp("2019-01-07") and d.max() >= pd.Timestamp("2026-10-26")
    assert df.reservoir_fill_pct.between(0, 100).all()
    assert _is_utc(df.available_from_utc)
    assert (df.available_from_utc > d.dt.tz_localize("Europe/Zurich").dt.tz_convert("UTC")).all()
    recent = df[d >= "2019-01-01"]
    assert recent.reservoir_median_pct_same_week.notna().all()
    # median uses only earlier years: recompute one row by hand
    row = recent.iloc[100]
    yr, wk = pd.Timestamp(row.measure_date).isocalendar()[:2]
    iso = d.dt.isocalendar()
    hist = df.loc[(iso.week == wk).values & (iso.year < yr).values, "reservoir_fill_pct"]
    assert row.reservoir_median_pct_same_week == pytest.approx(hist.median())
    assert (recent.reservoir_vs_median_pct - (recent.reservoir_fill_pct - recent.reservoir_median_pct_same_week)
            ).abs().max() < 1e-9


def test_de_forecasts():
    df = _read("de_forecasts_hourly")
    assert _is_utc(df.timestamp_utc)
    assert df.timestamp_utc.is_monotonic_increasing and not df.timestamp_utc.duplicated().any()
    for c in [c for c in df.columns if c.endswith("_mw")]:
        assert (df[c].dropna() >= 0).all(), c
