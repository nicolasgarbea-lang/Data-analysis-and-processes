"""Offline tests of the live refresh (src/live/refresh.py): every fetcher is replaced by a tiny fixture."""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from src.features.build_features import TABLE_FILES
from src.live import refresh

TODAY = dt.date(2026, 11, 21)


def _hours(start: str, n: int) -> pd.Series:
    return pd.Series(pd.date_range(start, periods=n, freq="h", tz="UTC")).astype("datetime64[ns, UTC]")


def _price(start: str, n: int, value: float) -> pd.DataFrame:
    return pd.DataFrame({"timestamp_utc": _hours(start, n),
                         "price_eur_mwh": np.full(n, value, dtype=float),
                         "n_values": np.full(n, 4, dtype="int64")})


def _demand(start: str, n: int, value: float) -> pd.DataFrame:
    return pd.DataFrame({"timestamp_utc": _hours(start, n), "load_mw": np.full(n, value),
                         "n_intervals": np.full(n, 4, dtype="int64"), "share_non_final": 1.0,
                         "share_status_f": 1.0, "n_filled": np.zeros(n, dtype="int64")})


def _gas(dates: list[str], value: float) -> pd.DataFrame:
    d = pd.Series([pd.Timestamp(x).date() for x in dates], dtype=object)
    avail = pd.to_datetime(pd.Series(dates)).dt.tz_localize("Europe/Zurich") + pd.Timedelta(hours=18)
    return pd.DataFrame({"date": d, "gas_ttf_eur_mwh": float(value),
                         "available_from_utc": avail.dt.tz_convert("UTC").astype("datetime64[ns, UTC]"),
                         "source": "yahoo_TTF=F_unofficial"})


@pytest.fixture
def stored():
    return {"price": _price("2026-11-18 00:00", 48, 100.0),
            "demand": _demand("2026-11-15 00:00", 48, 300.0),
            "gas": _gas(["2026-11-16", "2026-11-17"], 80.0)}


@pytest.fixture
def offline(monkeypatch, tmp_path, stored):
    """No network, cache in tmp_path, stored tables = the small fixtures; unknown sources fail."""
    monkeypatch.setattr(refresh, "LIVE_DIR", tmp_path)
    monkeypatch.setattr(refresh, "load_tables", lambda: {k: v.copy() for k, v in stored.items()})

    def boom(ctx):
        raise AssertionError("network fetcher called in an offline test")

    for key in TABLE_FILES:
        if hasattr(refresh, f"fetch_{key}"):
            monkeypatch.setattr(refresh, f"fetch_{key}", boom)
    return monkeypatch


def test_merge_keeps_schema(stored):
    old = stored["price"]
    # fresh rows from a loader: other column order, int32 counter, microsecond timestamps
    fresh = _price("2026-11-20 00:00", 24, 120.0)[["n_values", "price_eur_mwh", "timestamp_utc"]]
    fresh["n_values"] = fresh["n_values"].astype("int32")
    fresh["timestamp_utc"] = fresh["timestamp_utc"].astype("datetime64[us, UTC]")
    out = refresh.merge_fresh(old, fresh, "timestamp_utc")
    assert list(out.columns) == list(old.columns)
    assert dict(out.dtypes) == dict(old.dtypes)
    assert out["timestamp_utc"].is_monotonic_increasing and not out["timestamp_utc"].duplicated().any()
    assert len(out) == 72
    # daily table with datetime.date keys
    g = refresh.merge_fresh(stored["gas"], _gas(["2026-11-18"], 81.0), "date")
    assert list(g.columns) == list(stored["gas"].columns) and dict(g.dtypes) == dict(stored["gas"].dtypes)
    assert g["date"].iloc[-1] == dt.date(2026, 11, 18)


def test_merge_completes_hourly_grid(stored):
    fresh = _price("2026-11-21 00:00", 3, 90.0)    # leaves a gap after the stored rows
    out = refresh.merge_fresh(stored["price"], fresh, "timestamp_utc")
    assert (out["timestamp_utc"].diff().dropna() == pd.Timedelta("1h")).all()
    gap = out[out["price_eur_mwh"].isna()]
    assert len(gap) == 24 and (gap["n_values"] == 0).all()


def test_fresh_rows_win_on_overlap(stored):
    fresh = _price("2026-11-19 00:00", 48, 150.0)   # overlaps the last 24 stored hours
    out = refresh.merge_fresh(stored["price"], fresh, "timestamp_utc")
    assert len(out) == 72
    s = out.set_index("timestamp_utc")["price_eur_mwh"]
    assert (s[: "2026-11-18 23:00"] == 100.0).all()
    assert (s["2026-11-19 00:00":] == 150.0).all()


def test_failing_source_keeps_stored_table(offline, stored):
    offline.setattr(refresh, "fetch_price", lambda ctx: _price("2026-11-19 00:00", 48, 150.0))

    def broken(ctx):
        raise ConnectionError("ewz portal down")

    offline.setattr(refresh, "fetch_demand", broken)
    tables, status = refresh.refresh_tables(TODAY)
    by = {s["source"]: s for s in status}
    assert by["price"]["ok"] and by["price"]["rows_added"] == 24
    assert by["price"]["last_timestamp_utc"] == "2026-11-20T23:00:00+00:00"
    assert not by["demand"]["ok"] and "ewz portal down" in by["demand"]["message"]
    pd.testing.assert_frame_equal(tables["demand"], stored["demand"])
    assert by["demand"]["last_timestamp_utc"] == stored["demand"]["timestamp_utc"].max().isoformat()
    # every status has the agreed keys
    for s in status:
        assert set(s) == {"source", "label", "last_timestamp_utc", "rows_added", "ok", "message"}


def test_unpublished_daily_values_are_dropped(offline, stored):
    tomorrow = (pd.Timestamp.now(tz="Europe/Zurich") + pd.Timedelta(days=1)).date().isoformat()
    offline.setattr(refresh, "fetch_gas", lambda ctx: _gas(["2026-11-18", tomorrow], 81.0))
    tables, _ = refresh.refresh_tables(TODAY)
    assert tables["gas"]["date"].max() == dt.date(2026, 11, 18)


def test_cache_round_trip(offline, stored, tmp_path):
    calls = []

    def fetch_price(ctx):
        calls.append(ctx.start)
        return _price("2026-11-19 00:00", 48, 150.0)

    offline.setattr(refresh, "fetch_price", fetch_price)
    assert refresh.load_cached_tables(TODAY) is None
    tables, status = refresh.refresh_tables(TODAY)
    assert (tmp_path / "processed" / TODAY.isoformat() / "status.json").exists()
    cached = refresh.load_cached_tables(TODAY)
    assert cached is not None
    c_tables, c_status = cached
    assert c_status == status
    for key in tables:
        pd.testing.assert_frame_equal(c_tables[key], tables[key])
    # same day again: served from the cache, no download
    refresh.refresh_tables(TODAY)
    assert len(calls) == 1
    # force: downloads again
    refresh.refresh_tables(TODAY, force=True)
    assert len(calls) == 2
    assert calls[0] == TODAY - dt.timedelta(days=refresh.WINDOW_DAYS)
