"""Shape and completeness checks for features.parquet and hourly_actuals.parquet.

Run: .venv/bin/python -m pytest tests/test_features.py -s   (-s prints the NaN table)
"""
from __future__ import annotations

import pandas as pd
import pytest

from src.config import path
from src.features import feature_sets as fs

# default features that are allowed to have more NaN after 2019-02-15, with the date from which
# they must be complete (None = may stay NaN, e.g. optional external file)
LATE_STARTING = {**fs.LATE_START_FEATURES}


@pytest.fixture(scope="module")
def feat():
    f = path("features")
    if not f.exists():
        pytest.skip("features.parquet not built")
    df = pd.read_parquet(f)
    df["_d"] = pd.to_datetime(df["delivery_date"])
    return df


def test_one_row_per_date_and_block(feat):
    n_days = feat["_d"].nunique()
    assert n_days == (pd.Timestamp("2026-11-01") - pd.Timestamp("2019-01-15")).days + 1
    assert len(feat) == n_days * 6
    assert not feat.duplicated(["delivery_date", "block"]).any()
    assert set(feat["block"]) == set(range(6))


def test_hours_per_day(feat):
    hours = feat.groupby("_d")["hours_in_block"].sum()
    assert set(hours.unique()) <= {23, 24, 25}
    assert (hours == 23).sum() == 8 and (hours == 25).sum() == 8   # 8 springs, 8 autumns
    assert (feat["block_start_utc"].diff().dropna() > pd.Timedelta(0)).all()


def test_issue_time_is_10_local_day_before(feat):
    local = feat["forecast_issue_time_utc"].dt.tz_convert("Europe/Zurich")
    assert (local.dt.hour == 10).all() and (local.dt.minute == 0).all()
    assert (local.dt.tz_localize(None).dt.normalize() == feat["_d"] - pd.Timedelta(days=1)).all()


def test_targets_complete(feat):
    period = feat[(feat["_d"] >= "2019-01-15") & (feat["_d"] <= "2026-10-31")]
    assert period["demand_mw"].notna().all()
    assert period["price_eur_mwh"].notna().all()
    assert period["demand_mw"].between(150, 500).all()


def test_nan_share_of_default_features(feat):
    later = feat[feat["_d"] >= "2019-02-15"]
    cols = list(dict.fromkeys(fs.DEMAND_FEATURES + fs.PRICE_FEATURES))
    share = later[cols].isna().mean().sort_values(ascending=False)
    print("\nNaN share of default features from 2019-02-15 (non-zero only):")
    print(share[share > 0].to_string())
    for col, v in share.items():
        if col.startswith("eu_"):
            continue
        if col in LATE_STARTING:
            after = feat[feat["_d"] >= LATE_STARTING[col]][col].isna().mean()
            assert after < 0.02, f"{col}: {after:.2%} NaN after {LATE_STARTING[col]}"
            continue
        assert v < 0.02, f"{col}: {v:.2%} NaN"


def test_hourly_actuals():
    f = path("processed") / "hourly_actuals.parquet"
    if not f.exists():
        pytest.skip("hourly_actuals.parquet not built")
    h = pd.read_parquet(f)
    assert not h["timestamp_utc"].duplicated().any()
    per_day = h.groupby("delivery_date").size()
    assert set(per_day.unique()) == {23, 24, 25}
    assert str(per_day.index.min()) == "2019-01-01" and str(per_day.index.max()) == "2026-11-01"
    assert h[["demand_mw", "price_eur_mwh", "eurchf"]].notna().all().all()
    assert (h["block"] == h["hour_local"] // 4).all()


def test_hourly_actuals_match_block_targets(feat):
    """Block means of hourly actuals = the block targets in features.parquet."""
    h = pd.read_parquet(path("processed") / "hourly_actuals.parquet")
    h["_d"] = pd.to_datetime(h["delivery_date"])
    g = h.groupby(["_d", "block"]).agg(demand=("demand_mw", "mean"), price=("price_eur_mwh", "mean"),
                                       n=("demand_mw", "size"))
    m = feat.set_index(["_d", "block"]).join(g, how="inner")
    assert len(m) == len(feat)
    assert (m["n"] == m["hours_in_block"]).all()
    assert ((m["demand"] - m["demand_mw"]).abs() < 1e-9).all()
    assert ((m["price"] - m["price_eur_mwh"]).abs() < 1e-9).all()
