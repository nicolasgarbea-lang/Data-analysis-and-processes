"""Checks on the processed weather files (no network). Run: .venv/bin/python -m pytest tests/test_loaders_weather.py"""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
TZ = "Europe/Zurich"
PERIOD_START = pd.Timestamp("2019-01-01", tz="UTC")
PERIOD_END = pd.Timestamp("2026-11-01", tz="UTC")


def load(name: str) -> pd.DataFrame:
    f = PROC / f"{name}.parquet"
    if not f.exists():
        pytest.skip(f"{f} not built")
    return pd.read_parquet(f)


@pytest.fixture(scope="module")
def obs():
    return load("weather_observed_hourly")


@pytest.fixture(scope="module")
def fc():
    return load("weather_forecast_hourly")


@pytest.fixture(scope="module")
def era():
    return load("weather_archive_hourly")


@pytest.mark.parametrize("name", ["weather_observed_hourly", "weather_forecast_hourly", "weather_archive_hourly"])
def test_time_index(name):
    df = load(name)
    ts = df["timestamp_utc"]
    assert str(ts.dtype) == "datetime64[ns, UTC]"
    assert ts.is_monotonic_increasing
    assert not ts.duplicated().any()
    # complete hourly grid
    assert (ts.diff().dropna() == pd.Timedelta(hours=1)).all()


def test_coverage(obs, era, fc):
    for df in (obs, era):
        assert df["timestamp_utc"].min() <= PERIOD_START
        assert df["timestamp_utc"].max() >= PERIOD_END
    first_icon = fc.loc[fc["temp_c_fc_day1"].notna(), "timestamp_utc"].min()
    assert first_icon <= pd.Timestamp("2024-01-20", tz="UTC")
    assert fc["timestamp_utc"].max() >= PERIOD_END


def test_observed_ranges_and_missing(obs):
    period = obs[(obs["timestamp_utc"] >= PERIOD_START) & (obs["timestamp_utc"] < PERIOD_END)]
    limits = {"temp_c": (-25, 40), "sunshine_min": (0, 60), "radiation_wm2": (0, 1300), "wind_ms": (0, 40),
              "precip_mm": (0, 80), "humidity_pct": (0, 100)}
    for col, (lo, hi) in limits.items():
        s = period[col].dropna()
        assert s.between(lo, hi).all(), col
        assert period[col].isna().mean() < 0.005, col
        # interpolated values only where flagged, and the flag never sits on a NaN
        assert not (period[f"{col}_interpolated"] & period[col].isna()).any()


def test_observed_start_of_hour_convention(obs):
    """After the -1 h shift, mean June radiation must peak in the 11:00-12:00 UTC bin (solar noon ~11:26 UTC)."""
    j = obs[obs["timestamp_utc"].dt.month == 6]
    m = j.groupby(j["timestamp_utc"].dt.hour)["radiation_wm2"].mean()
    assert m.idxmax() == 11
    assert abs(m[10] - m[12]) < 0.1 * m[11]


def test_forecast_units_and_ranges(fc):
    first = fc["timestamp_utc"][fc["temp_c_fc_safe"].first_valid_index()]
    s = fc[fc["timestamp_utc"] >= first]
    assert s["temp_c_fc_safe"].dropna().between(-25, 42).all()
    assert s["sunshine_min_fc_safe"].dropna().between(0, 60.01).all()  # converted from seconds
    assert s["wind_ms_fc_safe"].dropna().between(0, 40).all()  # converted from km/h
    assert s["radiation_wm2_fc_safe"].dropna().between(0, 1200).all()
    assert s["temp_c_fc_safe"].isna().mean() < 0.005
    assert fc["temp_c_fc_safe_jma"].isna().mean() < 0.01  # JMA covers the full period


def expected_lead(ts: pd.Series, cadence_h: int, delay_h: int) -> pd.Series:
    """Re-derivation of the leakage-safe rule (docs/assumptions_weather.md), independent of the loader code."""
    local = ts.dt.tz_convert(TZ)
    out = []
    for t_utc, t_loc in zip(ts, local):
        issue = pd.Timestamp(t_loc.date() - pd.Timedelta(days=1)).replace(hour=10).tz_localize(TZ).tz_convert("UTC")
        valid_om = t_utc + pd.Timedelta(hours=1)
        init1 = (valid_om - pd.Timedelta(days=1)).floor(f"{cadence_h}h")
        init2 = (valid_om - pd.Timedelta(days=2)).floor(f"{cadence_h}h")
        assert init2 + pd.Timedelta(hours=delay_h) <= issue
        out.append(1 if init1 + pd.Timedelta(hours=delay_h) <= issue else 2)
    return pd.Series(out, index=ts.index)


@pytest.mark.parametrize("suffix,cadence,delay", [("", 3, 4), ("_ecmwf", 6, 8), ("_jma", 6, 6)])
def test_safe_rule_rederived(fc, suffix, cadence, delay):
    sample = fc.sample(500, random_state=1)
    exp = expected_lead(sample["timestamp_utc"], cadence, delay)
    assert (sample[f"fc_safe_lead_days{suffix}"].to_numpy() == exp.to_numpy()).all()
    pick = np.where(exp == 1, sample[f"temp_c_fc_day1{suffix}"], sample[f"temp_c_fc_day2{suffix}"])
    np.testing.assert_array_equal(sample[f"temp_c_fc_safe{suffix}"].to_numpy(), pick)


def test_safe_never_uses_day1_after_morning(fc):
    """Day1 may only be used for early-morning hours of the delivery day (local hour < 7)."""
    hour = fc["timestamp_utc"].dt.tz_convert(TZ).dt.hour
    assert (hour[fc["fc_safe_lead_days"] == 1] < 7).all()


def test_bias_correction_present(fc):
    assert "temp_c_fc_safe_corr" in fc and "temp_c_fc_safe_jma_corr" in fc
    diff = (fc["temp_c_fc_safe_corr"] - fc["temp_c_fc_safe"]).abs().dropna()
    assert diff.max() < 5


def test_archive_ranges(era):
    period = era[(era["timestamp_utc"] >= PERIOD_START) & (era["timestamp_utc"] < PERIOD_END)]
    assert period.drop(columns="timestamp_utc").isna().mean().max() < 0.005
    assert period["temp_c_era5"].between(-25, 40).all()
    assert period["sunshine_min_era5"].between(0, 60.01).all()


def test_forecast_close_to_observed(obs, fc):
    """Sanity: the safe ICON temperature forecast has MAE below 2 °C against the station."""
    m = obs.merge(fc, on="timestamp_utc").dropna(subset=["temp_c", "temp_c_fc_safe"])
    assert (m["temp_c_fc_safe"] - m["temp_c"]).abs().mean() < 2
