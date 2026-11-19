"""Checks of the daily calendar / EV / events / football tables (agent D3). Reads processed files only."""
from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from src.config import path

P = path("processed")
FIRST, LAST = pd.Timestamp("2018-12-01"), pd.Timestamp("2026-12-31")
TABLES = ["calendar_daily", "ev_daily", "events_daily", "football_daily", "calendar_features_daily"]


def _read(name: str) -> pd.DataFrame:
    f = P / f"{name}.parquet"
    if not f.exists():
        pytest.skip(f"{f} missing - run the loader first")
    df = pd.read_parquet(f)
    return df


def _by_date(name: str) -> pd.DataFrame:
    df = _read(name)
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")


# ---------- shape of every daily table ----------
@pytest.mark.parametrize("name", TABLES)
def test_one_row_per_day_no_gaps(name):
    df = _read(name)
    assert isinstance(df["date"].iloc[0], dt.date)          # plain date, not a timestamp
    d = pd.to_datetime(df["date"])
    assert d.is_monotonic_increasing and not d.duplicated().any()
    assert d.min() == FIRST and d.max() == LAST
    assert len(df) == (LAST - FIRST).days + 1                # no gaps


# ---------- calendar ----------
def test_calendar_known_days():
    c = _by_date("calendar_daily")
    assert c.loc["2026-08-01", "is_holiday"] == 1                     # National Day
    assert c.loc["2026-01-02", "holiday_name"] == "Berchtoldstag"
    assert c.loc["2026-12-25", "is_holiday"] == 1
    assert c.loc["2026-10-07", "is_holiday"] == 0
    assert c.loc["2026-04-20", "is_half_holiday"] == 1                # Sechseläuten 2026
    assert c.loc["2026-09-14", "is_half_holiday"] == 1                # Knabenschiessen 2026
    assert c.loc["2020-04-20", "is_half_holiday"] == 0                # Sechseläuten 2020 cancelled
    assert c.loc["2026-05-15", "is_bridge_day"] == 1                  # Friday after Ascension
    assert c.loc["2026-05-13", "is_bridge_day"] == 0
    assert c["is_holiday"].groupby(c.index.year).sum().loc[2019:2026].eq(10).all()


def test_calendar_school_holidays_end_exclusive():
    c = _by_date("calendar_daily")
    autumn = c.loc["2026-10-05":"2026-10-16"]
    assert (autumn["is_school_holiday"] == 1).all() and (autumn["school_holiday_type"] == "autumn").all()
    assert c.loc["2026-10-04", "is_school_holiday"] == 0
    assert c.loc["2026-10-17", "is_school_holiday"] == 0              # end date in file is exclusive
    assert c.loc["2026-08-14", "school_holiday_type"] == "summer"
    assert c.loc["2026-08-17", "is_school_holiday"] == 0              # first school day


def test_calendar_dst_and_basic_columns():
    c = _by_date("calendar_daily")
    assert c.loc["2026-10-25", "hours_in_day"] == 25
    assert c.loc["2026-03-29", "hours_in_day"] == 23
    assert c.loc["2026-10-24", "hours_in_day"] == 24
    assert set(c["hours_in_day"].unique()) == {23, 24, 25}
    assert c["is_dst_change_day"].groupby(c.index.year).sum().loc[2019:2026].eq(2).all()
    assert c.loc["2026-11-19", "weekday"] == 3 and c.loc["2026-11-21", "is_weekend"] == 1
    assert c.loc["2026-12-24", "is_christmas_period"] == 1
    assert c.loc["2026-01-02", "is_christmas_period"] == 1
    assert c.loc["2026-01-03", "is_christmas_period"] == 0
    assert c.loc["2026-08-01", "days_to_next_holiday"] == 0
    assert c.loc["2026-07-31", "days_to_next_holiday"] == 1
    assert c.loc["2026-08-02", "days_since_last_holiday"] == 1
    assert c[["days_to_next_holiday", "days_since_last_holiday"]].notna().all().all()


def test_calendar_covid():
    c = _by_date("calendar_daily")
    s = c["covid_stringency"].dropna()
    assert s.index.min() == pd.Timestamp("2020-01-01") and s.index.max() == pd.Timestamp("2022-12-31")
    assert s.between(0, 100).all()
    assert c.loc["2020-04-01", "covid_stringency"] > 60                # first lockdown
    assert c["covid_stringency_filled"].notna().all()
    assert c.loc["2019-06-01", "covid_stringency_filled"] == 0


# ---------- EVs ----------
def test_ev_values_and_known_rule():
    e = _by_date("ev_daily")
    assert e.loc["2025-09-30", "ev_count_city"] == pytest.approx(9743)
    assert e.loc["2019-09-30", "ev_count_city"] == pytest.approx(1467)
    assert e["ev_count_city"].is_monotonic_increasing
    assert e["ev_count_city"].between(500, 30000).all()
    # 2025 value is public from 2026-08-01: the day before, the known value must still be built from 2024
    slope_23_24 = (7571 - 5991) / 366  # 2023-09-30 -> 2024-09-30 spans a leap day
    expected = 7571 + slope_23_24 * (pd.Timestamp("2026-07-31") - pd.Timestamp("2024-09-30")).days
    assert e.loc["2026-07-31", "ev_count_city_known"] == pytest.approx(expected)
    assert e.loc["2026-08-01", "ev_count_city_known"] != pytest.approx(expected)
    assert e["ev_count_city_known"].notna().all()


def test_bfe_charging_known_rule():
    e = _by_date("ev_daily")
    assert e.loc[:"2020-11-29", "charging_kw_zh"].isna().all()       # series does not exist before 2020-11
    assert e.loc[:"2020-12-14", "charging_kw_zh_known"].isna().all()
    assert e.loc["2020-12-15", "charging_kw_zh_known"] == pytest.approx(21511)    # Nov 2020 value
    assert e.loc["2026-10-31", "charging_kw_zh"] == pytest.approx(158188)
    assert e.loc["2026-11-14", "charging_kw_zh_known"] == pytest.approx(147949)    # still Sept 2026 value
    assert e.loc["2026-11-15", "charging_kw_zh_known"] == pytest.approx(158188)
    assert e.loc["2026-10-31", "stations_zh_count"] == pytest.approx(2605)
    assert e["charging_kw_zh_backcast"].notna().all() and (e["charging_kw_zh_backcast"] >= 0).all()
    k = e["charging_kw_zh_known"].dropna()
    assert k.between(10_000, 500_000).all()


# ---------- events ----------
def test_events_manual_file():
    f = path("manual") / "events_zurich.csv"
    ev = pd.read_csv(f)
    assert list(ev.columns) == ["date", "event", "type", "size", "source_url"]
    assert ev["source_url"].str.startswith("http").all()
    assert ev["size"].between(1, 3).all()
    assert not ev.duplicated(["date", "event"]).any()


def test_events_daily():
    d = _by_date("events_daily")
    assert d.loc["2024-08-10", "event_size"] == 3 and "Street Parade" in d.loc["2024-08-10", "event_name"]
    assert d.loc["2026-08-08", "event_size"] == 3
    assert d.loc["2020-08-08", "event_size"] == 0          # Street Parade 2020 cancelled
    assert d.loc["2023-07-08", "event_size"] == 3          # Züri Fäscht 2023
    assert d["event_size"].between(0, 3).all()
    assert ((d["n_events"] > 0) == (d["event_size"] > 0)).all()
    assert (d["event_size"] > 0).sum() > 150


# ---------- football ----------
def test_football():
    f = _by_date("football_daily")
    assert set(f["home_game"].unique()) <= {0, 1}
    assert ((f["n_home_games"] > 0) == (f["home_game"] == 1)).all()
    k = f["kickoff_hour_local"].dropna()
    assert k.between(11, 22).all()
    assert (f["home_game"] == 1).sum() > 200
    assert f.loc[f["home_game"] == 1, "home_team"].isin(["Zurich", "Grasshoppers", "Grasshoppers | Zurich"]).all()
    # a known game: Grasshoppers v ... on Sat 7 Nov 2026, 19:30 UK time = 20:30 Swiss time
    assert f.loc["2026-11-07", "home_game"] == 1 and f.loc["2026-11-07", "kickoff_hour_local"] == 20.5


# ---------- merged ----------
def test_merged_table_has_all_columns():
    m = _read("calendar_features_daily")
    for name in TABLES[:-1]:
        part = _read(name)
        assert set(part.columns) <= set(m.columns), name
    assert m["is_holiday"].notna().all() and m["event_size"].notna().all() and m["home_game"].notna().all()
