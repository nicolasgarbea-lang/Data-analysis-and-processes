"""Build the feature table: one row per (delivery date, block).

How to read this module
-----------------------
* The forecast is made on day D at 10:00 Europe/Zurich (`auction.forecast_time_local`)
  for the delivery day D+1. Every row has `delivery_date` (= D+1) and
  `forecast_issue_time_utc` (= D 10:00 local, in UTC).
* Every time-series feature is "a statistic (mean, max, ...) of one hourly column over one
  time window [start, end) in UTC". The windows are built from the LOCAL clock (blocks of
  4 local hours, local days), so daylight-saving days come out right (3- or 5-hour blocks).
* Each hourly source has an availability CUTOFF per row (see `cutoffs`). Before computing a
  feature, `Ctx.window()` checks that the window ends at or before that cutoff. If a feature
  would look into the future the build stops with an error. Only columns that are meant to be
  "oracle" (targets, `actual_*`, `*_obs` weather of the delivery day) skip this check, and they
  are kept out of the default model inputs (see `src/features/feature_sets.py`).
* Daily tables with a publication time (gas, CO2, EUR/CHF, reservoirs) use a strict as-of
  lookup: the latest row with `available_from_utc <= forecast_issue_time_utc`.

`build_features(tables, delivery_dates)` takes the input tables as a dict of DataFrames and
an optional list of delivery dates. The leakage test uses this to rebuild single rows from
truncated input data.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.config import ROOT, load_config, path

TZ = "Europe/Zurich"
FIRST_DELIVERY = pd.Timestamp("2019-01-15")
LAST_DELIVERY = pd.Timestamp("2026-11-01")
ACTUALS_FIRST_DAY = pd.Timestamp("2019-01-01")
HOUR_NS = 3_600 * 10**9
DAY = pd.Timedelta(days=1)

# file name (without .parquet) -> key in the tables dict
TABLE_FILES = {
    "demand": "demand_ewz_hourly",
    "price": "price_ch_hourly",
    "neighbours": "price_neighbours_hourly",
    "power": "swiss_power_hourly",
    "weather_obs": "weather_observed_hourly",
    "weather_fc": "weather_forecast_hourly",
    "gas": "gas_ttf_daily",
    "co2": "co2_eua_daily",
    "eurchf": "eurchf_daily",
    "reservoir": "reservoir_weekly",
    "calendar": "calendar_features_daily",
    "de_forecasts": "de_forecasts_hourly",
    "ch_solar_fc": "swiss_solar_forecast_hourly",
    "weather_europe": "weather_europe_forecast_hourly",  # optional, may be missing
}
OPTIONAL_TABLES = {"weather_europe"}

# weather variables: name -> (observed column, ICON safe column, ECMWF safe column used to fill gaps)
WEATHER_VARS = {
    "temp_c": ("temp_c", "temp_c_fc_safe_corr", "temp_c_fc_safe_ecmwf"),
    "radiation_wm2": ("radiation_wm2", "radiation_wm2_fc_safe", "radiation_wm2_fc_safe_ecmwf"),
    "sunshine_min": ("sunshine_min", "sunshine_min_fc_safe", "sunshine_min_fc_safe_ecmwf"),
    "wind_ms": ("wind_ms", "wind_ms_fc_safe", "wind_ms_fc_safe_ecmwf"),
    "precip_mm": ("precip_mm", "precip_mm_fc_safe", "precip_mm_fc_safe_ecmwf"),
    "cloud_pct": (None, "cloud_pct_fc_safe", "cloud_pct_fc_safe_ecmwf"),  # no observed cloud cover
    "humidity_pct": ("humidity_pct", "humidity_pct_fc_safe", "humidity_pct_fc_safe_ecmwf"),
}
# JMA safe forecasts (real forecasts back to 2018)
JMA_VARS = {
    "temp_c": "temp_c_fc_safe_jma_corr",
    "wind_ms": "wind_ms_fc_safe_jma",
    "precip_mm": "precip_mm_fc_safe_jma",
    "cloud_pct": "cloud_pct_fc_safe_jma",
    "humidity_pct": "humidity_pct_fc_safe_jma",
}
SCHOOL_HOLIDAY_CODES = {"": 0, "christmas": 1, "sport": 2, "spring": 3, "summer": 4,
                        "autumn": 5, "school_free_day": 6}
NEIGHBOURS = {"de": "price_de_eur_mwh", "fr": "price_fr_eur_mwh",
              "at": "price_at_eur_mwh", "it": "price_it_north_eur_mwh"}
ZURICH_LAT = 47.378


# ----------------------------------------------------------------------------------------
# small helpers
# ----------------------------------------------------------------------------------------
def to_ns(values) -> np.ndarray:
    """UTC timestamps -> int64 nanoseconds (works for Series, Index, arrays)."""
    return pd.DatetimeIndex(values).as_unit("ns").asi8


def window_agg(ts: np.ndarray, vals: np.ndarray, starts: np.ndarray, ends: np.ndarray,
               how: str = "mean") -> np.ndarray:
    """Statistic of `vals` over each window [start, end); `ts` must be sorted (int64 ns).

    NaN values are ignored. A window without any value gives NaN.
    The result for a window depends ONLY on the values inside the window.
    """
    s = np.searchsorted(ts, starts, side="left")
    e = np.searchsorted(ts, ends, side="left")
    v = np.append(vals.astype(float), np.nan)          # dummy last value -> index len(ts) valid
    ok = ~np.isnan(v)
    idx = np.empty(2 * len(s), dtype=np.int64)
    idx[0::2], idx[1::2] = s, e
    empty = e <= s
    n = np.add.reduceat(ok.astype(np.int64), idx)[0::2].astype(float)
    n[empty] = 0
    if how == "count":
        return n
    if how in ("max", "min"):
        fill = -np.inf if how == "max" else np.inf
        func = np.maximum if how == "max" else np.minimum
        out = func.reduceat(np.where(ok, v, fill), idx)[0::2]
    else:
        x = np.where(ok, v, 0.0)
        if how == "neg_count":
            out = np.add.reduceat((x < 0).astype(float), idx)[0::2]
            out[empty] = 0
            return np.where(n > 0, out, np.nan)
        sums = np.add.reduceat(x, idx)[0::2]
        if how == "sum":
            out = sums
        elif how == "mean":
            out = sums / np.where(n > 0, n, 1)
        elif how == "std":
            sq = np.add.reduceat(x * x, idx)[0::2]
            var = (sq - sums * sums / np.where(n > 0, n, 1)) / np.where(n > 1, n - 1, 1)
            out = np.sqrt(np.clip(var, 0, None))
            out[n < 2] = np.nan
        else:
            raise ValueError(how)
    out = out.astype(float)
    out[n == 0] = np.nan
    return out


class Hourly:
    """An hourly table as sorted numpy arrays (timestamp_utc = start of hour)."""

    def __init__(self, df: pd.DataFrame | None, cols: list[str] | None = None):
        if df is None or len(df) == 0:
            self.ts, self.vals = np.array([], dtype=np.int64), {}
            if cols:
                self.vals = {c: np.array([], dtype=float) for c in cols}
            return
        df = df.sort_values("timestamp_utc")
        cols = cols or [c for c in df.columns if c != "timestamp_utc"]
        self.ts = to_ns(df["timestamp_utc"])
        self.vals = {c: df[c].to_numpy(dtype=float) for c in cols}


class AsOf:
    """A daily/weekly table with `available_from_utc`, for strict as-of lookups."""

    def __init__(self, df: pd.DataFrame, cols: list[str], date_col: str = "date"):
        df = df.dropna(subset=cols[:1]).sort_values("available_from_utc").reset_index(drop=True)
        self.avail = to_ns(df["available_from_utc"])
        self.dates = pd.to_datetime(df[date_col]).to_numpy()
        self.vals = {c: df[c].to_numpy(dtype=float) for c in cols}

    def latest_index(self, issue_ns: np.ndarray) -> np.ndarray:
        """Index of the newest row published at or before the issue time (-1 = none)."""
        return np.searchsorted(self.avail, issue_ns, side="right") - 1

    def value(self, col: str, idx: np.ndarray) -> np.ndarray:
        v = self.vals[col]
        out = np.full(len(idx), np.nan)
        good = idx >= 0
        out[good] = v[idx[good]]
        return out


class TimeGrid:
    """UTC start/end of every local block and local day between two dates."""

    def __init__(self, first_date: pd.Timestamp, last_date: pd.Timestamp):
        start = pd.Timestamp(first_date).tz_localize(TZ).tz_convert("UTC")
        end = (pd.Timestamp(last_date) + DAY).tz_localize(TZ).tz_convert("UTC")
        hours = pd.date_range(start, end, freq="h", inclusive="left").as_unit("ns")
        local = hours.tz_convert(TZ)
        df = pd.DataFrame({"ns": hours.asi8,
                           "date": local.tz_localize(None).normalize(),
                           "block": local.hour // 4})
        g = df.groupby(["date", "block"])["ns"]
        self.blocks = pd.DataFrame({"start": g.min(), "end": g.max() + HOUR_NS, "n": g.size()})
        d = df.groupby("date")["ns"]
        self.days = pd.DataFrame({"start": d.min(), "end": d.max() + HOUR_NS, "n": d.size()})

    def block_window(self, dates: pd.DatetimeIndex, blocks: np.ndarray):
        idx = pd.MultiIndex.from_arrays([dates, blocks])
        w = self.blocks.reindex(idx)
        return w["start"].to_numpy(), w["end"].to_numpy()

    def day_window(self, dates: pd.DatetimeIndex, last_dates: pd.DatetimeIndex | None = None):
        """[start of `dates`, end of `last_dates`) - several whole local days if given."""
        last_dates = dates if last_dates is None else last_dates
        return (self.days["start"].reindex(dates).to_numpy(),
                self.days["end"].reindex(last_dates).to_numpy())


# ----------------------------------------------------------------------------------------
# context: rows + sources + cutoffs + the leakage guard
# ----------------------------------------------------------------------------------------
class Ctx:
    """Everything the feature functions need. `window()` enforces the availability cutoffs."""

    def __init__(self, rows: pd.DataFrame, grid: TimeGrid, sources: dict, tables: dict):
        self.rows, self.grid, self.src, self.tables = rows, grid, sources, tables
        self.d = pd.DatetimeIndex(rows["_date"])                    # delivery date (naive)
        self.b = rows["block"].to_numpy()
        self.issue = to_ns(rows["forecast_issue_time_utc"])
        day_start = grid.days["start"]
        d_start = day_start.reindex(self.d).to_numpy()                       # start of D+1
        dm1_start = day_start.reindex(self.d - DAY).to_numpy()               # start of D
        d_end = grid.days["end"].reindex(self.d).to_numpy()                  # end of D+1
        # latest allowed END of a window, per source and row
        self.cutoff = {
            "demand": dm1_start,            # ewz demand known up to end of D-1
            "price": d_start,               # CH prices of day D known (auction D-1)
            "neighbours": d_start,          # SDAC prices of day D known
            "power": dm1_start,             # Swiss load/generation known up to end of D-1
            "weather_obs": self.issue - HOUR_NS,  # hours ending <= issue time - 1 h
        }
        # forecast sources: only windows inside the delivery day D+1
        self.delivery_day = (d_start, d_end)

    # ---- generic window with leakage guard ----
    def window(self, src: str, col: str, starts, ends, how="mean", oracle=False):
        if not oracle:
            if src in self.cutoff:
                bad = ~(ends <= self.cutoff[src])
            else:  # forecast table: delivery day only
                lo, hi = self.delivery_day
                bad = ~((starts >= lo) & (ends <= hi))
            if bad.any():
                raise AssertionError(f"leakage: {src}.{col} window beyond availability cutoff")
        h = self.src[src]
        return window_agg(h.ts, h.vals[col], starts, ends, how)

    # ---- convenience wrappers (k = days before the delivery date) ----
    def block(self, src, col, k, how="mean", block=None, oracle=False):
        """Same block (or block `block`) of local day delivery_date - k."""
        blocks = self.b if block is None else np.full(len(self.b), block)
        s, e = self.grid.block_window(self.d - k * DAY, blocks)
        return self.window(src, col, s, e, how, oracle)

    def day(self, src, col, k, how="mean", oracle=False):
        """Whole local day delivery_date - k."""
        s, e = self.grid.day_window(self.d - k * DAY)
        return self.window(src, col, s, e, how, oracle)

    def days(self, src, col, k_first, k_last, how="mean"):
        """Local days delivery_date - k_first ... delivery_date - k_last (inclusive, k_first > k_last)."""
        s, e = self.grid.day_window(self.d - k_first * DAY, self.d - k_last * DAY)
        return self.window(src, col, s, e, how)

    def cal(self, k: int) -> pd.DataFrame:
        """Calendar table rows for local day delivery_date - k (k may be negative)."""
        return self.tables["_calendar"].reindex(self.d - k * DAY)


# ----------------------------------------------------------------------------------------
# loading and preparing inputs
# ----------------------------------------------------------------------------------------
def load_tables() -> dict[str, pd.DataFrame]:
    """Read all processed input tables (the optional European weather file only if present)."""
    folder = path("processed")
    tables = {}
    for key, name in TABLE_FILES.items():
        f = folder / f"{name}.parquet"
        if not f.exists():
            if key in OPTIONAL_TABLES:
                continue
            raise FileNotFoundError(f)
        tables[key] = pd.read_parquet(f)
    return tables


def prepare_sources(tables: dict) -> dict:
    """Turn the raw tables into Hourly / AsOf objects with the derived hourly columns."""
    src = {}
    src["demand"] = Hourly(tables["demand"], ["load_mw"])
    src["price"] = Hourly(tables["price"], ["price_eur_mwh"])
    src["neighbours"] = Hourly(tables["neighbours"], list(NEIGHBOURS.values()))

    # Swiss power: bad hours -> NaN, plus residual load = load - solar - wind - run-of-river
    p = tables["power"].copy()
    p.loc[p["load_bad"].astype(bool), "load_mw"] = np.nan
    p.loc[p["wind_bad"].astype(bool), "wind_onshore_mw"] = np.nan
    p.loc[p["solar_bad"].astype(bool), "solar_mw"] = np.nan
    p["residual_mw"] = p["load_mw"] - p["solar_mw"] - p["wind_onshore_mw"] - p["hydro_run_of_river_mw"]
    src["power"] = Hourly(p, ["load_mw", "solar_mw", "nuclear_mw", "hydro_run_of_river_mw",
                              "hydro_water_reservoir_mw", "hydro_pumped_storage_mw",
                              "cross_border_trading_mw", "residual_mw"])

    obs_cols = [o for o, _, _ in WEATHER_VARS.values() if o]
    src["weather_obs"] = Hourly(tables["weather_obs"], obs_cols)

    # forecasts: ICON safe, gaps filled from ECMWF safe; JMA safe (bias-corrected temp)
    w = tables["weather_fc"]
    fc = pd.DataFrame({"timestamp_utc": w["timestamp_utc"]})
    for var, (_, icon, ecmwf) in WEATHER_VARS.items():
        fc[f"{var}_fc"] = w[icon].fillna(w[ecmwf]) if ecmwf in w else w[icon]
    for var, col in JMA_VARS.items():
        fc[f"{var}_fc_jma"] = w[col]
    src["weather_fc"] = Hourly(fc)

    de = tables["de_forecasts"].rename(columns={
        "solar_da_forecast_de_mw": "de_solar_fc", "wind_onshore_da_forecast_de_mw": "de_wind_onshore_fc",
        "wind_offshore_da_forecast_de_mw": "de_wind_offshore_fc", "load_da_forecast_de_mw": "de_load_fc"})
    src["de_forecasts"] = Hourly(de, ["de_solar_fc", "de_wind_onshore_fc", "de_wind_offshore_fc", "de_load_fc"])
    src["ch_solar_fc"] = Hourly(tables["ch_solar_fc"], ["solar_forecast_mw"])

    eu = tables.get("weather_europe")
    if eu is not None:
        num = [c for c in eu.columns if c != "timestamp_utc" and pd.api.types.is_numeric_dtype(eu[c])
               and not pd.api.types.is_bool_dtype(eu[c])]
        src["weather_europe"] = Hourly(eu, num)

    src["gas"] = AsOf(tables["gas"], ["gas_ttf_eur_mwh"])
    src["co2"] = AsOf(tables["co2"], ["co2_eua_eur_t"])
    src["eurchf"] = AsOf(tables["eurchf"], ["chf_per_eur"])
    src["reservoir"] = AsOf(tables["reservoir"], ["reservoir_fill_pct", "reservoir_vs_median_pct"],
                            date_col="measure_date")
    return src


def make_rows(dates: pd.DatetimeIndex, grid: TimeGrid) -> pd.DataFrame:
    """Skeleton: one row per (delivery date, block) with block times and the issue time."""
    hh, mm = map(int, load_config()["auction"]["forecast_time_local"].split(":"))
    d = np.repeat(dates.to_numpy(), 6)
    b = np.tile(np.arange(6), len(dates))
    rows = pd.DataFrame({"_date": pd.DatetimeIndex(d), "block": b})
    s, e = grid.block_window(pd.DatetimeIndex(d), b)
    rows.insert(0, "delivery_date", rows["_date"].dt.date)
    rows["block_start_utc"] = pd.to_datetime(s, utc=True)
    rows["hours_in_block"] = ((e - s) // HOUR_NS).astype(int)
    issue_local = (rows["_date"] - DAY + pd.Timedelta(hours=hh, minutes=mm)).dt.tz_localize(TZ)
    rows["forecast_issue_time_utc"] = issue_local.dt.tz_convert("UTC").dt.as_unit("ns")
    return rows


# ----------------------------------------------------------------------------------------
# feature groups
# ----------------------------------------------------------------------------------------
def targets_and_actuals(c: Ctx) -> dict:
    """Targets (block means) and same-row actuals for settlement. Oracle - never features."""
    f = {}
    n_d = c.block("demand", "load_mw", 0, "count", oracle=True)
    n_p = c.block("price", "price_eur_mwh", 0, "count", oracle=True)
    full_d = n_d == c.rows["hours_in_block"].to_numpy()
    full_p = n_p == c.rows["hours_in_block"].to_numpy()
    f["demand_mw"] = np.where(full_d, c.block("demand", "load_mw", 0, oracle=True), np.nan)
    f["price_eur_mwh"] = np.where(full_p, c.block("price", "price_eur_mwh", 0, oracle=True), np.nan)
    f["actual_demand_mwh"] = f["demand_mw"] * c.rows["hours_in_block"].to_numpy()
    f["actual_price_min_block"] = c.block("price", "price_eur_mwh", 0, "min", oracle=True)
    f["actual_price_max_block"] = c.block("price", "price_eur_mwh", 0, "max", oracle=True)
    f["actual_cost_eur"] = np.where(full_d & full_p, c.block("_cost", "cost_eur", 0, "sum", oracle=True), np.nan)
    # ECB rate of the delivery date, or the last rate before it (weekends/holidays)
    fx = c.src["eurchf"]
    i = np.searchsorted(fx.dates, c.d.to_numpy(), side="right") - 1
    f["actual_eurchf"] = np.where(i >= 0, fx.vals["chf_per_eur"][np.clip(i, 0, None)], np.nan)
    return f


def demand_features(c: Ctx) -> dict:
    """Zurich demand lags (known up to the end of D-1, i.e. >= 2 days before delivery)."""
    f = {}
    for k in (2, 3, 7, 8, 14, 21, 28, 364):
        f[f"demand_lag_{k}d_same_block"] = c.block("demand", "load_mw", k)
    f["demand_mean_same_block_same_weekday_4w"] = np.nanmean(
        np.vstack([f[f"demand_lag_{k}d_same_block"] for k in (7, 14, 21, 28)]), axis=0)
    f["demand_day_mean_lag_2d"] = c.day("demand", "load_mw", 2)
    f["demand_day_mean_lag_7d"] = c.day("demand", "load_mw", 7)
    f["demand_mean_last_7d"] = c.days("demand", "load_mw", 8, 2)        # days D-7 .. D-1
    f["demand_mean_last_28d"] = c.days("demand", "load_mw", 29, 2)      # days D-28 .. D-1
    f["demand_day_max_lag_2d"] = c.day("demand", "load_mw", 2, "max")
    f["demand_day_min_lag_2d"] = c.day("demand", "load_mw", 2, "min")
    for j in range(6):
        f[f"demand_dm1_block_{j}"] = c.block("demand", "load_mw", 2, block=j)
    prev_7d = c.days("demand", "load_mw", 15, 9)                         # days D-14 .. D-8
    f["demand_trend_7d"] = f["demand_mean_last_7d"] / prev_7d
    f["expected_demand_proxy"] = f["demand_mean_same_block_same_weekday_4w"]
    return f


def _temp_derived(temp: np.ndarray, suffix: str) -> dict:
    return {f"temp_c_sq{suffix}": temp ** 2,
            f"heating_degree{suffix}": np.maximum(0, 15 - temp),
            f"cooling_degree{suffix}": np.maximum(0, temp - 22)}


def delivery_weather_features(c: Ctx) -> dict:
    """Weather of the delivery block/day: `_obs` (oracle), `_fc` (ICON), `_fc_jma`, and hybrid."""
    f = {}
    hours_block = c.rows["hours_in_block"].to_numpy()
    hours_day = c.grid.days["n"].reindex(c.d).to_numpy()

    def fc_block(col):  # ICON forecast block mean, only if every hour of the block is forecast
        full = c.block("weather_fc", col, 0, "count") == hours_block
        return np.where(full, c.block("weather_fc", col, 0), np.nan)

    def fc_day(col, how):  # same for the whole delivery day
        full = c.day("weather_fc", col, 0, "count") == hours_day
        return np.where(full, c.day("weather_fc", col, 0, how), np.nan)

    for var, (obs, _, _) in WEATHER_VARS.items():
        if obs:  # observed weather of D+1 = ORACLE (stored only with suffix _obs)
            f[f"{var}_obs"] = c.block("weather_obs", obs, 0, oracle=True)
        f[f"{var}_fc"] = fc_block(f"{var}_fc")
    for var in JMA_VARS:
        f[f"{var}_fc_jma"] = c.block("weather_fc", f"{var}_fc_jma", 0)

    # delivery-day aggregates
    day_specs = {"temp_day_mean": ("temp_c", "mean"), "temp_day_min": ("temp_c", "min"),
                 "temp_day_max": ("temp_c", "max"), "radiation_day_mean": ("radiation_wm2", "mean"),
                 "sunshine_day_sum": ("sunshine_min", "sum")}
    for name, (var, how) in day_specs.items():
        f[f"{name}_obs"] = c.day("weather_obs", var, 0, how, oracle=True)
        f[f"{name}_fc"] = fc_day(f"{var}_fc", how)
    for name in ("temp_day_mean", "temp_day_min", "temp_day_max"):
        how = day_specs[name][1]
        f[f"{name}_fc_jma"] = c.day("weather_fc", "temp_c_fc_jma", 0, how)

    # hybrid model input: forecast where available, else observed (documented limitation)
    hybrid_vars = [v for v, (o, _, _) in WEATHER_VARS.items() if o] + list(day_specs)
    is_fc = np.ones(len(c.b), dtype=bool)
    for var in hybrid_vars:
        fc, ob = f[f"{var}_fc"], f[f"{var}_obs"]
        f[var] = np.where(np.isnan(fc), ob, fc)
        is_fc &= ~np.isnan(fc)
    # cloud cover has no observation: fall back to the (real) JMA forecast instead
    f["cloud_pct"] = np.where(np.isnan(f["cloud_pct_fc"]), f["cloud_pct_fc_jma"], f["cloud_pct_fc"])
    f["weather_is_forecast"] = is_fc.astype(int)

    for suffix in ("_obs", "_fc", "_fc_jma", ""):
        f.update(_temp_derived(f[f"temp_c{suffix}"], suffix))
    return f


def past_weather_features(c: Ctx, f_weather: dict) -> dict:
    """Observed weather known at issue time (hours ending <= issue time - 1 h)."""
    f = {}
    f["temp_obs_mean_dm1"] = c.day("weather_obs", "temp_c", 2)
    f["temp_obs_mean_last_3d"] = c.days("weather_obs", "temp_c", 4, 2)
    f["temp_obs_mean_last_7d"] = c.days("weather_obs", "temp_c", 8, 2)
    f["temp_obs_same_block_lag_2d"] = c.block("weather_obs", "temp_c", 2)
    f["radiation_obs_same_block_lag_2d"] = c.block("weather_obs", "radiation_wm2", 2)
    end = c.issue - HOUR_NS
    f["temp_obs_last_24h_mean"] = c.window("weather_obs", "temp_c", end - 24 * HOUR_NS, end)
    for suffix in ("", "_obs", "_fc", "_fc_jma"):
        f[f"temp_change_fc_vs_dm1{suffix}"] = f_weather[f"temp_c{suffix}"] - f["temp_obs_same_block_lag_2d"]
    return f


def solar_and_ev_features(c: Ctx) -> dict:
    """Lagged Swiss solar production and EV / charging stock (published values only)."""
    f = {"solar_ch_mw_lag_2d_same_block": c.block("power", "solar_mw", 2),
         "solar_ch_day_mean_lag_2d": c.day("power", "solar_mw", 2)}
    # values as published on day D (the day the forecast is made), not on the delivery day
    cal = c.cal(1)
    f["ev_count_city"] = cal["ev_count_city_known"].to_numpy(float)
    f["charging_kw_zh"] = cal["charging_kw_zh_known"].to_numpy(float)
    f["stations_zh_count"] = cal["stations_zh_count_known"].to_numpy(float)
    return f


def daylight_hours(day_of_year: np.ndarray, lat: float = ZURICH_LAT) -> np.ndarray:
    """Astronomical day length (hours) from the solar declination (simple textbook formula)."""
    decl = np.radians(23.44) * np.sin(2 * np.pi * (284 + day_of_year) / 365.0)
    cos_w = np.clip(-np.tan(np.radians(lat)) * np.tan(decl), -1, 1)
    return 2 * np.degrees(np.arccos(cos_w)) / 15.0


def calendar_features(c: Ctx) -> dict:
    """Calendar, holidays, events and football for the delivery date (all known in advance)."""
    cal = c.cal(0)
    f = {}
    for col in ("weekday", "month", "day_of_year", "is_weekend", "is_holiday", "is_half_holiday",
                "is_bridge_day", "is_school_holiday", "is_christmas_period", "days_to_next_holiday",
                "days_since_last_holiday", "event_size", "n_events", "home_game", "is_dst_change_day"):
        f[col] = cal[col].to_numpy()
    name = cal["school_holiday_type"].fillna("").astype(str)
    f["school_holiday_type"] = name.map(SCHOOL_HOLIDAY_CODES).fillna(-1).astype(int).to_numpy()
    f["school_holiday_type_name"] = name.to_numpy(dtype=object)
    f["kickoff_hour_local"] = cal["kickoff_hour_local"].fillna(0).to_numpy(float)  # 0 = no home game
    f["covid_stringency"] = cal["covid_stringency_filled"].to_numpy(float)
    iso = c.d.isocalendar()
    f["week_of_year"] = iso["week"].to_numpy().astype(int)
    days_in_year = np.where(c.d.is_leap_year, 366, 365)
    f["year_frac"] = c.d.year.to_numpy() + (c.d.day_of_year.to_numpy() - 1) / days_in_year
    doy = c.d.day_of_year.to_numpy()
    f["sin_doy"] = np.sin(2 * np.pi * doy / 365.25)
    f["cos_doy"] = np.cos(2 * np.pi * doy / 365.25)
    f["daylight_hours"] = daylight_hours(doy)
    f["is_holiday_prev_day"] = c.cal(1)["is_holiday"].to_numpy()
    f["is_holiday_next_day"] = c.cal(-1)["is_holiday"].to_numpy()
    f["lag2d_was_holiday"] = c.cal(2)["is_holiday"].to_numpy()
    f["lag7d_was_holiday"] = c.cal(7)["is_holiday"].to_numpy()
    f["lag2d_is_weekend"] = c.cal(2)["is_weekend"].to_numpy()
    f["is_working_day"] = ((f["is_weekend"] == 0) & (f["is_holiday"] == 0)).astype(int)
    return f


def price_features(c: Ctx) -> dict:
    """CH day-ahead price lags. All hours of day D (= delivery - 1) are known."""
    p = "price_eur_mwh"
    f = {}
    for k in (1, 2, 7, 14):
        f[f"price_lag_{k}d_same_block"] = c.block("price", p, k)
    f["price_mean_day_D"] = c.day("price", p, 1)
    f["price_min_day_D"] = c.day("price", p, 1, "min")
    f["price_max_day_D"] = c.day("price", p, 1, "max")
    f["price_spread_day_D"] = f["price_max_day_D"] - f["price_min_day_D"]
    f["price_std_day_D"] = c.day("price", p, 1, "std")
    for j in range(6):
        f[f"price_dD_block_{j}"] = c.block("price", p, 1, block=j)
    f["price_mean_last_7d"] = c.days("price", p, 7, 1)        # days D-6 .. D
    f["price_mean_last_28d"] = c.days("price", p, 28, 1)      # days D-27 .. D
    f["price_std_last_7d"] = c.days("price", p, 7, 1, "std")
    diffs = [c.block("price", p, k) - c.day("price", p, k) for k in range(1, 8)]
    f["price_block_vs_day_ratio_last_7d"] = np.nanmean(np.vstack(diffs), axis=0)
    f["price_neg_hours_day_D"] = c.day("price", p, 1, "neg_count")
    f["price_neg_hours_last_7d"] = c.days("price", p, 7, 1, "neg_count")
    f["price_lag_7d_day_mean"] = c.day("price", p, 7)
    return f


def neighbour_features(c: Ctx, ch: dict) -> dict:
    """DE / FR / AT / IT-North prices of day D (SDAC for D+1 is published after our forecast)."""
    f = {}
    for code, col in NEIGHBOURS.items():
        f[f"price_{code}_day_D_same_block"] = c.block("neighbours", col, 1)
        f[f"price_{code}_mean_day_D"] = c.day("neighbours", col, 1)
        f[f"spread_ch_{code}_day_D"] = ch["price_mean_day_D"] - f[f"price_{code}_mean_day_D"]
        daily = [c.day("price", "price_eur_mwh", k) - c.day("neighbours", col, k) for k in range(1, 8)]
        f[f"spread_ch_{code}_mean_7d"] = np.nanmean(np.vstack(daily), axis=0)
    f["price_de_lag_7d_same_block"] = c.block("neighbours", NEIGHBOURS["de"], 7)
    return f


def fuel_and_hydro_features(c: Ctx) -> dict:
    """Gas, CO2, EUR/CHF and reservoirs: latest value published at or before the issue time."""
    f = {}
    gas = c.src["gas"]
    i = gas.latest_index(c.issue)
    f["gas_ttf_d_1"] = gas.value("gas_ttf_eur_mwh", i)
    f["gas_ttf_change_5d"] = f["gas_ttf_d_1"] - gas.value("gas_ttf_eur_mwh", np.where(i >= 5, i - 5, -1))
    v = gas.vals["gas_ttf_eur_mwh"]
    f["gas_ttf_mean_20d"] = np.array([v[max(0, j - 19): j + 1].mean() if j >= 0 else np.nan for j in i])

    co2 = c.src["co2"]
    j = co2.latest_index(c.issue)
    f["co2_eua_d_1"] = co2.value("co2_eua_eur_t", j)
    last_auction = pd.DatetimeIndex(np.where(j >= 0, co2.dates[np.clip(j, 0, None)], np.datetime64("NaT")))
    f["co2_staleness_days"] = ((c.d - DAY) - last_auction).days.to_numpy(dtype=float)

    fx = c.src["eurchf"]
    f["eurchf_d_1"] = fx.value("chf_per_eur", fx.latest_index(c.issue))
    # CCGT marginal cost proxy: 50 % efficiency, 0.37 tCO2 per MWh_el
    f["clean_gas_cost"] = f["gas_ttf_d_1"] / 0.5 + 0.37 * f["co2_eua_d_1"]

    res = c.src["reservoir"]
    r = res.latest_index(c.issue)
    f["reservoir_fill_pct"] = res.value("reservoir_fill_pct", r)
    f["reservoir_vs_median_pct"] = res.value("reservoir_vs_median_pct", r)
    f["reservoir_change_1w"] = f["reservoir_fill_pct"] - res.value("reservoir_fill_pct", np.where(r >= 1, r - 1, -1))
    return f


def swiss_system_features(c: Ctx) -> dict:
    """Swiss load and generation (Energy-Charts), known up to the end of D-1 (= delivery - 2)."""
    return {
        "swiss_load_lag_2d_same_block": c.block("power", "load_mw", 2),
        "swiss_load_day_mean_lag_2d": c.day("power", "load_mw", 2),
        "swiss_nuclear_mw_lag_2d": c.day("power", "nuclear_mw", 2),
        "swiss_hydro_ror_mw_lag_2d": c.day("power", "hydro_run_of_river_mw", 2),
        "swiss_hydro_storage_mw_lag_2d": c.day("power", "hydro_water_reservoir_mw", 2),
        "swiss_hydro_pumped_mw_lag_2d": c.day("power", "hydro_pumped_storage_mw", 2),
        "swiss_solar_mw_lag_2d_same_block": c.block("power", "solar_mw", 2),
        "swiss_residual_load_lag_2d_same_block": c.block("power", "residual_mw", 2),
        "swiss_net_import_mw_lag_2d": c.day("power", "cross_border_trading_mw", 2),
    }


def unverified_features(c: Ctx) -> dict:
    """Day-ahead forecasts for D+1 whose publication time is NOT verified (excluded by default)."""
    f = {}
    for col in ("de_solar_fc", "de_wind_onshore_fc", "de_wind_offshore_fc", "de_load_fc"):
        f[f"unverified_{col}"] = c.block("de_forecasts", col, 0)
        f[f"unverified_{col}_day"] = c.day("de_forecasts", col, 0)
    f["unverified_ch_solar_fc"] = c.block("ch_solar_fc", "solar_forecast_mw", 0)
    f["unverified_ch_solar_fc_day"] = c.day("ch_solar_fc", "solar_forecast_mw", 0)
    return f


def europe_weather_features(c: Ctx) -> dict:
    """Optional: every numeric column of weather_europe_forecast_hourly as block and day mean."""
    if "weather_europe" not in c.src:
        return {}
    f = {}
    for col in c.src["weather_europe"].vals:
        f[f"eu_{col}"] = c.block("weather_europe", col, 0)
        f[f"eu_{col}_day"] = c.day("weather_europe", col, 0)
    return f


# ----------------------------------------------------------------------------------------
# main entry points
# ----------------------------------------------------------------------------------------
def _cost_source(tables: dict) -> Hourly:
    """Hourly EUR cost of the actual demand at the actual price (for `actual_cost_eur`)."""
    m = tables["demand"][["timestamp_utc", "load_mw"]].merge(
        tables["price"][["timestamp_utc", "price_eur_mwh"]], on="timestamp_utc", how="inner")
    m["cost_eur"] = m["load_mw"] * m["price_eur_mwh"]
    return Hourly(m, ["cost_eur"])


def build_features(tables: dict | None = None, delivery_dates=None) -> pd.DataFrame:
    """Build the feature table.

    tables: dict of input DataFrames (keys as in TABLE_FILES); default = read from data/processed.
    delivery_dates: optional list of local delivery dates; default = 2019-01-15 .. 2026-11-01.
    """
    tables = load_tables() if tables is None else tables
    if delivery_dates is None:
        dates = pd.date_range(FIRST_DELIVERY, LAST_DELIVERY, freq="D")
    else:
        dates = pd.DatetimeIndex(pd.to_datetime(list(delivery_dates))).normalize().unique().sort_values()

    grid = TimeGrid(dates.min() - pd.Timedelta(days=400), dates.max() + 2 * DAY)
    rows = make_rows(dates, grid)
    src = prepare_sources(tables)
    src["_cost"] = _cost_source(tables)
    cal = tables["calendar"].copy()
    cal.index = pd.DatetimeIndex(pd.to_datetime(cal["date"]))
    tables = {**tables, "_calendar": cal}
    c = Ctx(rows, grid, src, tables)

    f = {}
    f.update(targets_and_actuals(c))
    f.update(demand_features(c))
    w = delivery_weather_features(c)
    f.update(w)
    f.update(past_weather_features(c, w))
    f.update(solar_and_ev_features(c))
    f.update(calendar_features(c))
    ch = price_features(c)
    f.update(ch)
    f.update(neighbour_features(c, ch))
    f.update(fuel_and_hydro_features(c))
    f.update(swiss_system_features(c))
    f.update(unverified_features(c))
    f.update(europe_weather_features(c))

    out = pd.concat([rows.drop(columns="_date"), pd.DataFrame(f, index=rows.index)], axis=1)
    return out


def build_hourly_actuals(tables: dict | None = None) -> pd.DataFrame:
    """One row per UTC hour (2019-01-01 .. 2026-11-01 local days) with actual demand and price."""
    tables = load_tables() if tables is None else tables
    start = ACTUALS_FIRST_DAY.tz_localize(TZ).tz_convert("UTC")
    end = (LAST_DELIVERY + DAY).tz_localize(TZ).tz_convert("UTC")
    hours = pd.date_range(start, end, freq="h", inclusive="left").as_unit("ns")
    df = pd.DataFrame({"timestamp_utc": hours})
    local = df["timestamp_utc"].dt.tz_convert(TZ)
    df["local_time"] = local
    df["delivery_date"] = local.dt.date
    df["hour_local"] = local.dt.hour
    df["block"] = df["hour_local"] // 4
    d = tables["demand"][["timestamp_utc", "load_mw"]].copy()
    p = tables["price"][["timestamp_utc", "price_eur_mwh"]].copy()
    for t in (d, p):
        t["timestamp_utc"] = t["timestamp_utc"].dt.as_unit("ns")
    df = df.merge(d.rename(columns={"load_mw": "demand_mw"}), on="timestamp_utc", how="left")
    df = df.merge(p, on="timestamp_utc", how="left")
    fx = tables["eurchf"].copy()
    fx["date"] = pd.to_datetime(fx["date"])
    fx = fx.sort_values("date")
    day = pd.DataFrame({"date": pd.to_datetime(df["delivery_date"])})
    rate = pd.merge_asof(day.reset_index().sort_values("date"), fx[["date", "chf_per_eur"]],
                         on="date", direction="backward").set_index("index").sort_index()
    df["eurchf"] = rate["chf_per_eur"].to_numpy()
    return df


def write_report(feat: pd.DataFrame, out: Path) -> None:
    """reports/data_checks/features.md: size, date range and NaN share per column."""
    nan = feat.isna().mean().sort_values(ascending=False)
    late = feat[pd.to_datetime(feat["delivery_date"]) >= "2019-02-15"].isna().mean()
    lines = ["# Data check: features.parquet", "",
             f"- rows: {len(feat)} ({feat['delivery_date'].nunique()} delivery days x 6 blocks)",
             f"- columns: {feat.shape[1]}",
             f"- delivery dates: {feat['delivery_date'].min()} -> {feat['delivery_date'].max()} (local Europe/Zurich days)",
             f"- hours_in_block values: {sorted(feat['hours_in_block'].unique().tolist())}",
             f"- built by `src/features/build_features.py`; column meaning in `docs/data_dictionary_features.md`",
             f"- weather_is_forecast = 1 on {100 * feat['weather_is_forecast'].mean():.1f} % of rows "
             f"(ICON forecasts from 2024-01-21; before, hybrid weather = observed, documented limitation)",
             "- expected late starts: `*_fc` (ICON) before 2024-01-21, `charging_kw_zh`/`stations_zh_count` "
             "before 2020-12-15, `demand_lag_364d_same_block` before 2020-01, `eu_*` if the file is missing",
             "", "## Columns with > 1 % NaN (whole table)", "",
             "| column | NaN % | NaN % from 2019-02-15 |", "|---|---|---|"]
    for col, v in nan.items():
        if v > 0.01:
            lines.append(f"| {col} | {100 * v:.2f} | {100 * late[col]:.2f} |")
    lines += ["", "## NaN share per column", "", "| column | NaN % | NaN % from 2019-02-15 |", "|---|---|---|"]
    for col in feat.columns:
        lines.append(f"| {col} | {100 * nan[col]:.3f} | {100 * late[col]:.3f} |")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    tables = load_tables()
    feat = build_features(tables)
    feat.to_parquet(path("features"), index=False)
    hourly = build_hourly_actuals(tables)
    hourly.to_parquet(path("processed") / "hourly_actuals.parquet", index=False)
    write_report(feat, ROOT / "reports" / "data_checks" / "features.md")
    print(f"features: {feat.shape}, hourly_actuals: {hourly.shape}")
    if "weather_europe" not in tables:
        print("note: weather_europe_forecast_hourly.parquet not found -> no eu_* columns")


if __name__ == "__main__":
    main()
