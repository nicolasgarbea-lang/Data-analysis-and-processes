"""Checks on the European weather forecast files (no network).

Run: .venv/bin/python -m pytest tests/test_loaders_weather_europe.py
"""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
TZ = "Europe/Zurich"
POINTS = ["de_north", "de_northeast", "de_central", "de_south", "fr_paris", "fr_lyon", "it_milan", "ch_alps",
          "ch_bern"]
WIND_POINTS = ["de_north", "de_northeast", "de_central"]
PERIOD_START = pd.Timestamp("2019-01-01", tz="UTC")
PERIOD_END = pd.Timestamp("2026-11-01", tz="UTC")
ICON_FIRST = pd.Timestamp("2024-01-21", tz="UTC")  # ICON safe values must exist from here on at the latest
ICON_WIND100_FIRST = pd.Timestamp("2024-02-18", tz="UTC")  # 100 m wind enters the ICON archive later


def load(name: str) -> pd.DataFrame:
    f = PROC / f"{name}.parquet"
    if not f.exists():
        pytest.skip(f"{f} not built")
    return pd.read_parquet(f)


@pytest.fixture(scope="module")
def safe():
    return load("weather_europe_forecast_hourly")


@pytest.fixture(scope="module")
def raw():
    return load("weather_europe_forecast_raw_hourly")


@pytest.mark.parametrize("name", ["weather_europe_forecast_hourly", "weather_europe_forecast_raw_hourly"])
def test_time_index(name):
    ts = load(name)["timestamp_utc"]
    assert str(ts.dtype) == "datetime64[ns, UTC]"
    assert ts.is_monotonic_increasing
    assert not ts.duplicated().any()
    assert (ts.diff().dropna() == pd.Timedelta(hours=1)).all()


def test_only_safe_columns(safe):
    cols = [c for c in safe.columns if c != "timestamp_utc"]
    assert all(c.endswith("_safe") for c in cols)
    assert not any(("day1" in c) or ("day2" in c) or ("day0" in c) for c in cols)
    assert all(pd.api.types.is_float_dtype(safe[c]) for c in cols)


def test_expected_columns(safe):
    for p in POINTS:
        assert f"temp_c_{p}_safe" in safe and f"temp_c_{p}_jma_safe" in safe
        assert (f"radiation_wm2_{p}_safe" in safe) == (not p.startswith("fr_"))
    for p in WIND_POINTS:
        for c in (f"wind100_ms_{p}_safe", f"wind_cubed_{p}_safe", f"wind10_ms_{p}_jma_safe",
                  f"wind_cubed_{p}_jma_safe"):
            assert c in safe
    for c in ("wind_cubed_de_mean_safe", "radiation_wm2_de_mean_safe", "temp_c_fr_mean_safe",
              "wind_cubed_de_mean_jma_safe", "temp_c_fr_mean_jma_safe", "precip_mm_ch_alps_safe"):
        assert c in safe


def test_coverage(safe):
    assert safe["timestamp_utc"].min() <= pd.Timestamp("2018-12-01", tz="UTC")
    assert safe["timestamp_utc"].max() >= PERIOD_END
    period = safe[(safe["timestamp_utc"] >= PERIOD_START) & (safe["timestamp_utc"] < PERIOD_END)]
    icon = safe[(safe["timestamp_utc"] >= ICON_FIRST) & (safe["timestamp_utc"] < PERIOD_END)]
    for c in safe.columns[1:]:
        if "_jma_" in c:
            assert period[c].isna().mean() < 0.01, c   # JMA covers the full period
        else:
            first = ICON_WIND100_FIRST if "wind" in c else ICON_FIRST
            sub = icon[icon["timestamp_utc"] >= first]
            assert sub[c].isna().mean() < 0.01, c      # ICON from 2024-01 on (100 m wind from 2024-02-17)
            assert safe.loc[safe["timestamp_utc"] < pd.Timestamp("2024-01-01", tz="UTC"), c].isna().all(), c


def test_ranges(safe):
    for c in safe.columns[1:]:
        s = safe[c].dropna()
        if c.startswith("temp_c"):
            assert s.between(-35, 45).all(), c
        elif c.startswith("radiation"):
            assert s.between(0, 1200).all(), c
        elif c.startswith(("wind100", "wind10")):
            assert s.between(0, 50).all(), c       # m/s (converted from km/h)
        elif c.startswith("wind_cubed"):
            assert s.between(0, 25 ** 3 + 1e-6).all(), c
        elif c.startswith("precip"):
            assert s.between(0, 100).all(), c
    # unit sanity: North Sea 100 m wind should average roughly 6-12 m/s (km/h would be ~3.6x larger)
    assert 5 < safe["wind100_ms_de_north_safe"].mean() < 13


def test_wind_cubed_and_means(safe):
    for p in WIND_POINTS:
        exp = np.minimum(safe[f"wind100_ms_{p}_safe"], 25) ** 3
        np.testing.assert_allclose(safe[f"wind_cubed_{p}_safe"], exp, equal_nan=True)
    m = safe[[f"wind_cubed_{p}_safe" for p in WIND_POINTS]].mean(axis=1, skipna=False)
    np.testing.assert_allclose(safe["wind_cubed_de_mean_safe"], m, equal_nan=True)


def test_radiation_start_of_hour(safe):
    """After the -1 h shift, mean June radiation in Bavaria (11.5 E, solar noon ~11:14 UTC) peaks at 10 or 11 UTC."""
    j = safe[safe["timestamp_utc"].dt.month == 6]
    m = j.groupby(j["timestamp_utc"].dt.hour)["radiation_wm2_de_south_safe"].mean()
    assert m.idxmax() in (10, 11)
    assert m[[0, 1, 2, 20, 21, 22, 23]].max() < 1


def expected_lead(ts: pd.Series, cadence_h: int, delay_h: int) -> pd.Series:
    """Re-derivation of the leakage-safe rule (docs/assumptions_weather.md), independent of the loader code."""
    out = []
    for t_utc, t_loc in zip(ts, ts.dt.tz_convert(TZ)):
        issue = pd.Timestamp(t_loc.date() - pd.Timedelta(days=1)).replace(hour=10).tz_localize(TZ).tz_convert("UTC")
        valid_om = t_utc + pd.Timedelta(hours=1)
        init1 = (valid_om - pd.Timedelta(days=1)).floor(f"{cadence_h}h")
        init2 = (valid_om - pd.Timedelta(days=2)).floor(f"{cadence_h}h")
        assert init2 + pd.Timedelta(hours=delay_h) <= issue
        out.append(1 if init1 + pd.Timedelta(hours=delay_h) <= issue else 2)
    return pd.Series(out, index=ts.index)


@pytest.mark.parametrize("suffix,cadence,delay,col", [("", 3, 4, "temp_c_fr_paris"),
                                                       ("", 3, 4, "wind100_ms_de_north"),
                                                       ("_jma", 6, 6, "temp_c_ch_bern"),
                                                       ("_jma", 6, 6, "wind10_ms_de_central")])
def test_safe_rule_rederived(safe, raw, suffix, cadence, delay, col):
    sample_idx = raw.sample(500, random_state=1).index
    r, s = raw.loc[sample_idx], safe.loc[sample_idx]
    assert (r["timestamp_utc"].to_numpy() == s["timestamp_utc"].to_numpy()).all()
    exp = expected_lead(r["timestamp_utc"], cadence, delay)
    assert (r[f"safe_lead_days{suffix}"].to_numpy() == exp.to_numpy()).all()
    pick = np.where(exp == 1, r[f"{col}_day1{suffix}"], r[f"{col}_day2{suffix}"])
    np.testing.assert_array_equal(s[f"{col}{suffix}_safe"].to_numpy(), pick)


def test_day1_only_early_morning(raw):
    hour = raw["timestamp_utc"].dt.tz_convert(TZ).dt.hour
    for suffix in ("", "_jma"):
        assert (hour[raw[f"safe_lead_days{suffix}"] == 1] < 7).all()


def test_wind_negatively_correlated_with_de_price(safe):
    f = PROC / "price_neighbours_hourly.parquet"
    if not f.exists():
        pytest.skip("price file not built")
    m = safe.merge(pd.read_parquet(f), on="timestamp_utc")
    m = m[m["timestamp_utc"] >= pd.Timestamp("2024-01-01", tz="UTC")]
    assert m["wind_cubed_de_mean_safe"].corr(m["price_de_eur_mwh"]) < -0.1
    mid = m[m["timestamp_utc"].dt.tz_convert(TZ).dt.hour.between(11, 14)]
    assert mid["radiation_wm2_de_mean_safe"].corr(mid["price_de_eur_mwh"]) < 0
