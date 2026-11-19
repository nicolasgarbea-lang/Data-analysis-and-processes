"""No-future-information tests for data/processed/features.parquet.

(a) Rebuild: for 200 sampled rows, cut every input table down to what was known at the row's
    forecast_issue_time_utc (rules written here independently of the feature code), rebuild
    that delivery date with build_features() and compare every default feature.
(b) Poison: add +1e6 to every value that was NOT yet known at the issue time and check that the
    rebuilt features do not change.
(c) Hand checks of a few features computed directly with pandas.
(d) The default feature lists contain no oracle / actual / unverified / target columns.

Hybrid weather (forecast if available, else observed) is a documented limitation: on rows with
weather_is_forecast == 0 it uses observed weather of the delivery day, so there we only check
that it equals the forecast column if present, else the `_obs` column.

Run: .venv/bin/python -m pytest tests/test_no_leakage.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.config import path
from src.features import feature_sets as fs
from src.features.build_features import build_features, load_tables

TZ = "Europe/Zurich"
POISON = 1e6
FEATURES = list(dict.fromkeys(fs.DEMAND_FEATURES + fs.PRICE_FEATURES))
HYBRID = set(fs.ORACLE_WEATHER_MAP)


# ---------------------------------------------------------------- fixtures
@pytest.fixture(scope="module")
def tables():
    return load_tables()


@pytest.fixture(scope="module")
def stored():
    f = path("features")
    if not f.exists():
        pytest.skip("features.parquet not built")
    df = pd.read_parquet(f)
    df["delivery_date"] = pd.to_datetime(df["delivery_date"])
    return df.set_index(["delivery_date", "block"])


@pytest.fixture(scope="module")
def sample(stored):
    """200 (date, block) rows: Oct 2026, DST days, year boundaries, edges, plus random rows."""
    rng = np.random.default_rng(42)
    dates = stored.index.get_level_values(0).unique()
    forced = []
    oct26 = dates[(dates >= "2026-10-01") & (dates <= "2026-10-31")]
    forced += [(d, int(rng.integers(6))) for d in rng.choice(oct26, 25, replace=False)]
    dst = stored[stored["hours_in_block"] != 4].index.tolist()        # all 3-/5-hour blocks
    forced += dst
    for y in range(2019, 2027):
        for md in ("01-01", "01-02", "12-31"):
            d = pd.Timestamp(f"{y}-{md}")
            if d in dates:
                forced.append((d, int(rng.integers(6))))
    forced += [(dates[0], 0), (dates[-1], 5), (pd.Timestamp("2024-01-20"), 2), (pd.Timestamp("2024-01-21"), 3)]
    forced = list(dict.fromkeys(forced))
    pool = [ix for ix in stored.index if ix not in set(forced)]
    extra = rng.choice(len(pool), 200 - len(forced), replace=False)
    return forced + [pool[i] for i in extra]


# ---------------------------------------------------------------- availability rules (independent)
def midnight_utc(day: pd.Timestamp) -> pd.Timestamp:
    """UTC time of local midnight at the start of `day`."""
    return pd.Timestamp(day).tz_localize(TZ).tz_convert("UTC")


def cutoffs(delivery: pd.Timestamp, issue: pd.Timestamp) -> dict:
    return {
        "demand": midnight_utc(delivery - pd.Timedelta(days=1)),   # data before day D
        "price": midnight_utc(delivery),                          # all of day D known
        "power": midnight_utc(delivery - pd.Timedelta(days=1)),   # data before day D
        "obs_hour_end": issue - pd.Timedelta(hours=1),            # observed hour must END by issue - 1 h
        "issue": issue,
        "day_lo": midnight_utc(delivery),
        "day_hi": midnight_utc(delivery + pd.Timedelta(days=1)),
    }


def truncate(tables: dict, delivery: pd.Timestamp, issue: pd.Timestamp) -> dict:
    """Keep only information available at the issue time."""
    c = cutoffs(delivery, issue)
    t = dict(tables)
    ts = lambda k: tables[k]["timestamp_utc"]
    t["demand"] = tables["demand"][ts("demand") < c["demand"]]
    t["price"] = tables["price"][ts("price") < c["price"]]
    t["neighbours"] = tables["neighbours"][ts("neighbours") < c["price"]]
    t["power"] = tables["power"][ts("power") < c["power"]]
    t["weather_obs"] = tables["weather_obs"][ts("weather_obs") + pd.Timedelta(hours=1) <= c["obs_hour_end"]]
    for k in ("gas", "co2", "eurchf", "reservoir"):
        t[k] = tables[k][tables[k]["available_from_utc"] <= issue]
    for k in ("weather_fc", "weather_europe", "de_forecasts", "ch_solar_fc"):
        if k not in tables:
            continue
        df = tables[k][(ts(k) >= c["day_lo"]) & (ts(k) < c["day_hi"])]
        if k == "weather_fc":  # only the leakage-safe columns of the forecast file
            df = df[["timestamp_utc"] + [col for col in df.columns if "_safe" in col]]
        t[k] = df
    return t   # calendar tables stay complete (known in advance)


def poison(tables: dict, delivery: pd.Timestamp, issue: pd.Timestamp) -> dict:
    """Add +1e6 to every value that is not yet known at the issue time."""
    c = cutoffs(delivery, issue)
    t = dict(tables)

    def bump(key, mask, cols=None):
        df = tables[key].copy()
        cols = cols or [col for col in df.columns if pd.api.types.is_float_dtype(df[col])]
        df.loc[mask, cols] = df.loc[mask, cols] + POISON
        t[key] = df

    ts = lambda k: tables[k]["timestamp_utc"]
    bump("demand", ts("demand") >= c["demand"], ["load_mw"])
    bump("price", ts("price") >= c["price"], ["price_eur_mwh"])
    bump("neighbours", ts("neighbours") >= c["price"])
    bump("power", ts("power") >= c["power"])
    bump("weather_obs", ts("weather_obs") + pd.Timedelta(hours=1) > c["obs_hour_end"])
    bump("gas", tables["gas"]["available_from_utc"] > issue, ["gas_ttf_eur_mwh"])
    bump("co2", tables["co2"]["available_from_utc"] > issue, ["co2_eua_eur_t"])
    bump("eurchf", tables["eurchf"]["available_from_utc"] > issue, ["chf_per_eur"])
    bump("reservoir", tables["reservoir"]["available_from_utc"] > issue,
         ["reservoir_fill_pct", "reservoir_vs_median_pct"])
    for k in ("weather_fc", "weather_europe"):
        if k in tables:
            outside = (ts(k) < c["day_lo"]) | (ts(k) >= c["day_hi"])
            bump(k, outside)
    # non-safe forecast columns (day0/day1/day2 raw leads) must never be used
    fc = t["weather_fc"].copy()
    raw = [col for col in fc.columns if "_fc_day" in col]
    fc[raw] = fc[raw] + POISON
    t["weather_fc"] = fc
    return t


# ---------------------------------------------------------------- comparison
def compare_row(stored_row: pd.Series, rebuilt_row: pd.Series) -> list[str]:
    """Names of features where the rebuilt value differs from the stored one."""
    bad = []
    is_fc = stored_row["weather_is_forecast"] == 1
    for col in FEATURES:
        if col == "block":          # part of the index
            continue
        a = stored_row[col]
        if col in HYBRID and not is_fc:
            # documented limitation: hybrid = ICON forecast if present, else observed
            fc_col = fs.FORECAST_WEATHER_MAP[col]
            expected = stored_row[fc_col] if pd.notna(stored_row[fc_col]) else stored_row[fs.ORACLE_WEATHER_MAP[col]]
        else:
            expected = rebuilt_row[col]
        if not ((pd.isna(a) and pd.isna(expected)) or a == expected):
            bad.append(f"{col}: stored={a} rebuilt={expected}")
    return bad


def _check(sample, stored, tables, transform):
    by_date: dict = {}
    for d, b in sample:
        by_date.setdefault(d, []).append(b)
    problems = []
    for d, blocks in by_date.items():
        issue = stored.loc[(d, blocks[0]), "forecast_issue_time_utc"]
        rebuilt = build_features(transform(tables, d, issue), [d])
        rebuilt["delivery_date"] = pd.to_datetime(rebuilt["delivery_date"])
        rebuilt = rebuilt.set_index(["delivery_date", "block"])
        for b in blocks:
            bad = compare_row(stored.loc[(d, b)], rebuilt.loc[(d, b)])
            problems += [f"{d.date()} block {b}: {x}" for x in bad]
    return problems


# ---------------------------------------------------------------- tests
def test_sample_has_required_rows(sample):
    dates = pd.DatetimeIndex([d for d, _ in sample])
    assert len(sample) == 200 and len(set(sample)) == 200
    assert ((dates >= "2026-10-01") & (dates <= "2026-10-31")).sum() >= 20
    assert (dates.month == 1).any() and (dates.month == 12).any()
    assert any(d in dates for d in pd.to_datetime(["2026-03-29", "2026-10-25"]))


def test_rebuild_from_truncated_inputs(sample, stored, tables):
    problems = _check(sample, stored, tables, truncate)
    assert not problems, f"{len(problems)} mismatches, first: {problems[:10]}"


def test_poisoned_future_does_not_change_features(sample, stored, tables):
    problems = _check(sample, stored, tables, poison)
    assert not problems, f"{len(problems)} mismatches, first: {problems[:10]}"


def test_hand_checks(stored, tables):
    """Five features for delivery 2026-10-15, block 2 (08-12 local), recomputed with plain pandas."""
    d, b = pd.Timestamp("2026-10-15"), 2
    row = stored.loc[(d, b)]

    def local(df):
        lt = df["timestamp_utc"].dt.tz_convert(TZ)
        return df.assign(day=lt.dt.tz_localize(None).dt.normalize(), hour=lt.dt.hour)

    dem, pr, fc = local(tables["demand"]), local(tables["price"]), local(tables["weather_fc"])
    in_block = lambda x: (x["hour"] >= 8) & (x["hour"] < 12)
    # 1. demand same block two days before delivery (2026-10-13)
    v = dem[(dem["day"] == "2026-10-13") & in_block(dem)]["load_mw"].mean()
    assert row["demand_lag_2d_same_block"] == pytest.approx(v, rel=1e-12)
    # 2. price same block of day D (2026-10-14)
    v = pr[(pr["day"] == "2026-10-14") & in_block(pr)]["price_eur_mwh"].mean()
    assert row["price_lag_1d_same_block"] == pytest.approx(v, rel=1e-12)
    # 3. hourly price spread of day D
    day_d = pr[pr["day"] == "2026-10-14"]["price_eur_mwh"]
    assert row["price_spread_day_D"] == pytest.approx(day_d.max() - day_d.min(), rel=1e-12)
    # 4. latest gas close published by 2026-10-14 10:00 Zurich
    issue = pd.Timestamp("2026-10-14 10:00", tz=TZ).tz_convert("UTC")
    assert row["forecast_issue_time_utc"] == issue
    gas = tables["gas"]
    v = gas[gas["available_from_utc"] <= issue].sort_values("available_from_utc")["gas_ttf_eur_mwh"].iloc[-1]
    assert row["gas_ttf_d_1"] == pytest.approx(v, rel=1e-12)
    # 5. ICON safe bias-corrected temperature forecast of the delivery block
    v = fc[(fc["day"] == "2026-10-15") & in_block(fc)]["temp_c_fc_safe_corr"].mean()
    assert row["temp_c_fc"] == pytest.approx(v, rel=1e-12)
    assert row["temp_c"] == row["temp_c_fc"]          # hybrid uses the forecast in 2026
    # 6. demand mean over days D-7..D-1 (2026-10-07 .. 2026-10-13)
    v = dem[(dem["day"] >= "2026-10-07") & (dem["day"] <= "2026-10-13")]["load_mw"].mean()
    assert row["demand_mean_last_7d"] == pytest.approx(v, rel=1e-12)
    # DST: 25-hour day has a 5-hour first block
    assert stored.loc[(pd.Timestamp("2026-10-25"), 0), "hours_in_block"] == 5
    assert stored.loc[(pd.Timestamp("2026-03-29"), 0), "hours_in_block"] == 3


def test_default_lists_are_clean(stored):
    banned_exact = {fs.TARGET_DEMAND, fs.TARGET_PRICE}
    for name, cols in (("DEMAND_FEATURES", fs.DEMAND_FEATURES), ("PRICE_FEATURES", fs.PRICE_FEATURES)):
        assert len(cols) == len(set(cols)), f"duplicates in {name}"
        for col in cols:
            assert col not in banned_exact, f"{name} contains target {col}"
            assert not col.endswith("_obs"), f"{name} contains oracle weather {col}"
            assert not col.startswith(("actual_", "unverified_")), f"{name} contains {col}"
            assert col in stored.columns or col == "block", f"{name}: {col} not in features.parquet"
    for m in (fs.ORACLE_WEATHER_MAP, fs.FORECAST_WEATHER_MAP, fs.JMA_WEATHER_MAP):
        for h, alt in m.items():
            assert h in stored.columns and alt in stored.columns, (h, alt)
