"""Live data refresh: extend the stored input tables with the newest data of every source.

`refresh_tables(today)` starts from the stored tables (`build_features.load_tables()`, which end in
early or mid November 2026), downloads a recent window of every source (about the last 21 days up to
the latest available value, forecasts up to today + 2 days) and appends it. The result has exactly the
same keys, columns, dtypes and time conventions as the files in data/processed/, so
`build_features(tables, [tomorrow])` works on it unchanged.

Rules
- The loader code in src/data/ does the parsing and unit conversion. We call it with some module
  constants (raw folder, first year, start / end dates, output file) temporarily replaced by
  `patched(...)`, so nothing is copied and nothing is written to data/raw/ or data/processed/.
- Where a fresh row and a stored row have the same key (timestamp_utc, date or measure_date), the
  fresh row wins.
- A source that fails does not stop the refresh: its stored table is kept and its status says why.
- Weather forecasts: the raw lead columns (`*_fc_day0/1/2*`) are merged with the stored ones first,
  then the leakage-safe columns and the temperature bias correction are recomputed on the FULL frame
  (the bias fit needs the old rows).
- Cache: raw downloads in data/live/raw/<today>/, merged tables in data/live/processed/<today>/
  (<file name>.parquet + status.json). A second call on the same day reuses the cache unless force=True.

Run:  python -m src.live.refresh [--force]
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import functools
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import ROOT, path
from src.data.load_openmeteo_forecast import URL as OM_URL
from src.data.load_openmeteo_forecast import get_json as _om_loader_get_json   # unpatched reference
from src.features.build_features import OPTIONAL_TABLES, TABLE_FILES, load_tables

TZ = "Europe/Zurich"
LIVE_DIR = ROOT / "data" / "live"
WINDOW_DAYS = 21          # how far back every source is re-downloaded
MAX_WINDOW_DAYS = 90      # never reach further back than this, even if the stored table is old
EC_MAX_RETRIES = 3        # Energy-Charts tries per call in live mode (the backfill loaders use 8)
OM_TRIES = 4              # Open-Meteo tries per call (exponential backoff 10, 20, 40 s)
OM_PAUSE_S = 10           # pause between two Open-Meteo calls
OM_ROUNDS = 3             # extra rounds for truncated / failed Open-Meteo responses

LABELS = {
    "demand": "Zurich demand (ewz)",
    "price": "Swiss day-ahead price",
    "neighbours": "Neighbour day-ahead prices (DE, FR, AT, IT-North)",
    "power": "Swiss load and generation (Energy-Charts)",
    "weather_obs": "Observed weather Zurich (MeteoSwiss)",
    "weather_fc": "Weather forecast Zurich (Open-Meteo)",
    "gas": "Gas price (TTF)",
    "co2": "CO2 price (EUA auctions)",
    "eurchf": "EUR/CHF exchange rate (ECB)",
    "reservoir": "Swiss reservoir fill level (BFE)",
    "calendar": "Calendar and holidays",
    "de_forecasts": "German wind, solar and load forecasts",
    "ch_solar_fc": "Swiss solar forecast (Energy-Charts)",
    "weather_europe": "Weather forecast Europe (Open-Meteo)",
}
# column that must be non-null for a row to count as "data up to"
MAIN_COL = {
    "demand": "load_mw", "price": "price_eur_mwh", "neighbours": "price_de_eur_mwh",
    "power": "solar_mw", "weather_obs": "temp_c", "weather_fc": "temp_c_fc_safe",
    "gas": "gas_ttf_eur_mwh", "co2": "co2_eua_eur_t", "eurchf": "chf_per_eur",
    "reservoir": "reservoir_fill_pct", "calendar": "is_holiday",
    "de_forecasts": "load_da_forecast_de_mw", "ch_solar_fc": "solar_forecast_mw",
    "weather_europe": "temp_c_de_north_safe",
}
DAILY = {"gas": "date", "co2": "date", "eurchf": "date", "reservoir": "measure_date", "calendar": "date"}
FORECASTS = {"weather_fc", "weather_europe", "de_forecasts", "ch_solar_fc"}


# ----------------------------------------------------------------------------------------------------------
# small helpers
# ----------------------------------------------------------------------------------------------------------
def zurich_today() -> dt.date:
    return pd.Timestamp.now(tz=TZ).date()


def key_col(key: str) -> str:
    return DAILY.get(key, "timestamp_utc")


def raw_root(today: dt.date) -> Path:
    return LIVE_DIR / "raw" / today.isoformat()


def processed_root(today: dt.date) -> Path:
    return LIVE_DIR / "processed" / today.isoformat()


@contextlib.contextmanager
def patched(module, **attrs):
    """Temporarily replace module attributes (constants or functions), restore them afterwards."""
    old = {k: getattr(module, k) for k in attrs}
    try:
        for k, v in attrs.items():
            setattr(module, k, v)
        yield module
    finally:
        for k, v in old.items():
            setattr(module, k, v)


@contextlib.contextmanager
def system_certificates():
    """On Windows, verify HTTPS against certifi PLUS the Windows certificate store.

    Machines behind an antivirus / proxy that re-signs HTTPS traffic only trust its root certificate
    through the Windows store, which `requests` (certifi) and curl_cffi ignore. Verification stays on;
    we only widen the trusted roots to what the operating system already trusts. Skipped when the user
    has set REQUESTS_CA_BUNDLE themselves or when not on Windows."""
    import os
    import ssl
    if sys.platform != "win32" or os.environ.get("REQUESTS_CA_BUNDLE"):
        yield
        return
    import certifi
    pem = [Path(certifi.where()).read_text(encoding="ascii")]
    for store in ("ROOT", "CA"):
        for cert, enc, _ in ssl.enum_certificates(store):
            if enc == "x509_asn":
                pem.append(ssl.DER_cert_to_PEM_cert(cert))
    bundle = LIVE_DIR / "ca_bundle.pem"
    bundle.parent.mkdir(parents=True, exist_ok=True)
    bundle.write_text("\n".join(pem), encoding="ascii")
    old = {k: os.environ.get(k) for k in ("REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE")}
    os.environ["REQUESTS_CA_BUNDLE"] = os.environ["CURL_CA_BUNDLE"] = str(bundle)
    try:
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _noop(*args, **kwargs):
    return None


def local_midnight_utc(day: dt.date) -> pd.Timestamp:
    return pd.Timestamp(day).tz_localize(TZ).tz_convert("UTC")


@dataclass
class Ctx:
    """What a fetcher needs: today's date, the raw folder of today, the window start, force flag."""
    today: dt.date
    raw: Path
    start: dt.date
    force: bool = False

    @property
    def start_utc(self) -> pd.Timestamp:
        return local_midnight_utc(self.start)

    def dir(self, name: str) -> Path:
        d = self.raw / name
        d.mkdir(parents=True, exist_ok=True)
        return d

    def raw_dir_fn(self):
        """Replacement for drivers_utils.raw_dir: raw folders under data/live/raw/<today>/."""
        return lambda source: self.dir(source)

    def processed_path_fn(self):
        """Replacement for drivers_utils.processed_path: loader output goes to a scratch folder."""
        return lambda name: self.dir("_loader_output") / f"{name}.parquet"


def window_start(stored: pd.DataFrame | None, key: str, today: dt.date) -> dt.date:
    """Start of the re-download window: 21 days back, earlier if the stored table ends before that."""
    start = today - dt.timedelta(days=WINDOW_DAYS)
    if stored is not None and len(stored):
        last = stored[key_col(key)].max()
        if key_col(key) == "timestamp_utc":
            last_day = pd.Timestamp(last).tz_convert(TZ).date()
        else:
            last_day = pd.Timestamp(last).date()
        start = min(start, last_day - dt.timedelta(days=1))
    return max(start, today - dt.timedelta(days=MAX_WINDOW_DAYS))


# ----------------------------------------------------------------------------------------------------------
# merging
# ----------------------------------------------------------------------------------------------------------
def _cast_like(df: pd.DataFrame, like: pd.DataFrame) -> pd.DataFrame:
    """Give every column the dtype it has in `like` (where the conversion works)."""
    for c in like.columns:
        if c in df.columns and df[c].dtype != like[c].dtype:
            try:
                df[c] = df[c].astype(like[c].dtype)
            except (TypeError, ValueError):
                pass
    return df


def _fill_flags(df: pd.DataFrame, like: pd.DataFrame) -> pd.DataFrame:
    """Rows created by completing the hourly grid: integer counters 0, booleans False (or the constant flag)."""
    for c in like.columns:
        if c not in df.columns or not df[c].isna().any():
            continue
        if pd.api.types.is_bool_dtype(like[c]):
            const = like[c].dropna().unique()
            df[c] = df[c].fillna(bool(const[0]) if len(const) == 1 else False)
        elif pd.api.types.is_integer_dtype(like[c]):
            df[c] = df[c].fillna(0)
    return df


def merge_fresh(stored: pd.DataFrame, fresh: pd.DataFrame, key: str, complete_grid: bool | None = None) -> pd.DataFrame:
    """Append `fresh` to `stored` with the stored schema; on equal keys the fresh row wins.

    Hourly tables are put back on a complete hourly grid (as the loaders write them)."""
    if fresh is None or len(fresh) == 0:
        return stored.copy()
    fresh = fresh.copy()
    for c in stored.columns:
        if c not in fresh.columns:
            fresh[c] = np.nan
    fresh = fresh[list(stored.columns)]
    if key == "timestamp_utc":
        fresh[key] = pd.to_datetime(fresh[key], utc=True).astype(stored[key].dtype)
    elif stored[key].dtype == object:   # columns of datetime.date objects
        fresh[key] = pd.to_datetime(fresh[key]).dt.date
    # avoid concat dtype surprises (e.g. bool + NaN -> object): cast fresh first, where possible
    fresh = _cast_like(fresh, stored)
    out = pd.concat([stored, fresh], ignore_index=True)
    out = out.drop_duplicates(key, keep="last").sort_values(key).reset_index(drop=True)
    if complete_grid is None:
        complete_grid = key == "timestamp_utc"
    if complete_grid and len(out):
        grid = pd.date_range(out[key].min(), out[key].max(), freq="h", name=key)
        if len(grid) != len(out):
            out = out.set_index(key).reindex(grid).reset_index()
            out[key] = out[key].astype(stored[key].dtype)
    out = _fill_flags(out, stored)
    return _cast_like(out, stored)[list(stored.columns)]


def _trim(fresh: pd.DataFrame, start_utc: pd.Timestamp, value_cols: list[str] | None = None) -> pd.DataFrame:
    """Keep fresh hourly rows from `start_utc` up to the last row with any value (loaders pad grids with NaN)."""
    f = fresh[fresh["timestamp_utc"] >= start_utc]
    cols = value_cols or [c for c in f.columns if c != "timestamp_utc"
                          and pd.api.types.is_float_dtype(f[c])]
    has = f[cols].notna().any(axis=1)
    if not has.any():
        return f.iloc[:0]
    return f.loc[: has[has].index[-1]].reset_index(drop=True)


# ----------------------------------------------------------------------------------------------------------
# fetchers: download the recent window and parse it with the loader code -> fresh rows (stored schema)
# ----------------------------------------------------------------------------------------------------------
def _ec_fetch(endpoint: str, params: dict, cache: Path, force: bool) -> dict:
    """Energy-Charts call through the shared polite helper (>= 7 s between calls, backoff on 429/5xx)."""
    from src.data import _energy_charts_targets as ec
    with patched(ec, MAX_RETRIES=EC_MAX_RETRIES):
        data = ec.fetch_json(endpoint, params, cache, force=force)
    if not data or not data.get("unix_seconds"):
        raise RuntimeError(f"no data from Energy-Charts {endpoint} {params}")
    return data


def _om_get_json(params: dict) -> dict:
    """Open-Meteo previous-runs call: the loader's `get_json` (backoff on 429/5xx), plus a few retries when
    the response is cut off (seen live: truncated JSON) or the connection fails. Bounded."""
    import requests
    last = None
    for attempt in range(OM_ROUNDS):
        try:
            return _om_loader_get_json(OM_URL, params, tries=OM_TRIES)
        except (requests.RequestException, ValueError) as e:   # JSONDecodeError is a ValueError
            last = e
            print(f"  Open-Meteo request failed ({str(e)[:100]}), retry in {15 * 2 ** attempt} s", flush=True)
            time.sleep(15 * 2 ** attempt)
    raise RuntimeError(f"Open-Meteo not reachable after {OM_ROUNDS} rounds: {last}")


def fetch_demand(ctx: Ctx) -> pd.DataFrame:
    """ewz yearly CSV(s) of the window -> hourly table with the loader's UTC and hourly logic."""
    from src.data import load_ewz_demand as m
    d = ctx.dir("ewz")
    for year in sorted({ctx.start.year, ctx.today.year}):
        m._download(m.URL_YEAR.format(year=year), d / f"{year}_ewz_bruttolastgang.csv", ctx.force)
    with patched(m, RAW_DIR=d):
        raw = m.read_ewz()
    # the Netzebenen reference file (history file, only used for DST pairs and gap filling) is not
    # downloaded live: without it DST pairs follow file order and short gaps are interpolated
    ne = pd.Series(dtype=float, index=pd.DatetimeIndex([], tz="UTC"), name="ne_kwh")
    d_utc, _ = m.to_utc(raw, ne)
    q, _ = m.complete_grid(d_utc, ne)
    q["timestamp_utc"] = q["timestamp_utc"].astype("datetime64[ns, UTC]")
    q = q[["timestamp_utc", "load_kwh_15min", "status", "is_filled", "fill_method"]]
    h = m.hourly(q)
    h["timestamp_utc"] = h["timestamp_utc"].astype("datetime64[ns, UTC]")
    return _trim(h, ctx.start_utc, ["load_mw"])


def fetch_price(ctx: Ctx) -> pd.DataFrame:
    """Energy-Charts bzn=CH for the window (incl. tomorrow if published), 15 min -> hourly mean."""
    from src.data import load_price_ch as m
    end = ctx.today + dt.timedelta(days=2)
    data = _ec_fetch("price", {"bzn": "CH", "start": ctx.start.isoformat(), "end": end.isoformat()},
                     ctx.dir("energy_charts_price_ch") / f"price_CH_{ctx.start}_{end}.json", ctx.force)
    with patched(m, START_UTC=ctx.start_utc):
        df, _ = m.to_hourly([data])
    last_valid = df["price_eur_mwh"].last_valid_index()
    df = df.loc[:last_valid].reset_index(drop=True)
    df["price_eur_mwh"] = df["price_eur_mwh"].astype(float)
    df["timestamp_utc"] = df["timestamp_utc"].astype("datetime64[ns, UTC]")
    return df


def fetch_neighbours(ctx: Ctx) -> pd.DataFrame:
    from src.data import load_neighbour_prices as m
    d = ctx.dir("energy_charts_neighbours")
    end = ctx.today + dt.timedelta(days=2)
    for zone in m.ZONES:
        _ec_fetch("price", {"bzn": zone, "start": ctx.start.isoformat(), "end": end.isoformat()},
                  d / f"{zone}_{ctx.start}_{end}.json", ctx.force)
    with patched(m, RAW=str(d)):          # raw_dir(RAW): an absolute path replaces data/raw/
        df = m.build()
    return _trim(df, ctx.start_utc)


def _ec_year_ranges(ctx: Ctx, end: dt.date):
    """Replacement for load_swiss_power._year_ranges: one chunk = the window."""
    def ranges():
        yield ctx.start.year, ctx.start.isoformat(), end.isoformat()
    return ranges


def fetch_power(ctx: Ctx) -> pd.DataFrame:
    """Energy-Charts public_power CH (value columns only; the *_bad flags are recomputed after merging)."""
    from src.data import _energy_charts_targets as ec
    from src.data import load_swiss_power as m
    end = ctx.today + dt.timedelta(days=1)
    with patched(m, _year_ranges=_ec_year_ranges(ctx, end), RAW_DIR=ctx.dir("energy_charts_public_power_ch"),
                 START_UTC=ctx.start_utc), patched(ec, MAX_RETRIES=EC_MAX_RETRIES):
        chunks = m.download_power(force=ctx.force)
        if not chunks:
            raise RuntimeError("no data from Energy-Charts public_power")
        power, _ = m.power_table(chunks)
    value_cols = [c for c in power.columns if c.endswith("_mw")]
    last = power[value_cols].dropna(how="all").index.max()
    power = power.loc[:last].copy()
    power["timestamp_utc"] = power["timestamp_utc"].astype("datetime64[ns, UTC]")
    return _trim(power, ctx.start_utc, value_cols)


def fetch_ch_solar_fc(ctx: Ctx) -> pd.DataFrame:
    from src.data import _energy_charts_targets as ec
    from src.data import load_swiss_power as m
    end = ctx.today + dt.timedelta(days=2)
    with patched(m, _year_ranges=_ec_year_ranges(ctx, end), RAW_FC_DIR=ctx.dir("energy_charts_solar_forecast_ch")), \
            patched(ec, MAX_RETRIES=EC_MAX_RETRIES):
        chunks = m.download_forecast(force=ctx.force)
        if not chunks:
            raise RuntimeError("no data from Energy-Charts solar forecast")
        fc = m.forecast_table(chunks)
    fc["timestamp_utc"] = fc["timestamp_utc"].astype("datetime64[ns, UTC]")
    return _trim(fc, ctx.start_utc)


def fetch_de_forecasts(ctx: Ctx) -> pd.DataFrame:
    from src.data import load_de_forecasts as m
    d = ctx.dir("energy_charts_de_forecasts")
    end = ctx.today + dt.timedelta(days=2)
    for ptype in m.TYPES:
        _ec_fetch("public_power_forecast",
                  {"country": "de", "production_type": ptype, "forecast_type": "day-ahead",
                   "start": ctx.start.isoformat(), "end": end.isoformat()},
                  d / f"de_{ptype}_dayahead_{ctx.start}_{end}.json", ctx.force)
    with patched(m, RAW=str(d), processed_path=ctx.processed_path_fn(), write_check=_noop):
        df = m.main(skip_download=True)
    return _trim(df, ctx.start_utc, list(m.TYPES.values()))


def fetch_weather_obs(ctx: Ctx) -> pd.DataFrame:
    """MeteoSwiss SMA `*_h_recent.csv` only (the historical files are not needed for the window)."""
    from src.data import load_meteoswiss as m
    d = ctx.dir("meteoswiss")
    recent = [f for f in m.FILES if f.endswith("_h_recent.csv")]
    with patched(m, FILES=recent, RAW_DIR=d, START=ctx.start_utc - pd.Timedelta(days=3),
                 OUT_FILE=ctx.dir("_loader_output") / "weather_observed_hourly.parquet", write_check=_noop):
        df = m.main(force=ctx.force)
    return _trim(df, ctx.start_utc, list(m.COLUMNS.values()))


def fetch_weather_fc(ctx: Ctx) -> pd.DataFrame:
    """Raw lead columns (`*_fc_day0/1/2*`) of all models for the window up to today + 2 days."""
    from src.data import load_openmeteo_forecast as m
    end_date = (ctx.today + dt.timedelta(days=2)).isoformat()
    # first year = window year, so read_model() reads the file the download wrote (named per year)
    models = {k: (v[0], ctx.start.year, *v[2:]) for k, v in m.MODELS.items()}
    with patched(m, RAW_DIR=ctx.dir("openmeteo_forecast"), START=pd.Timestamp(ctx.start, tz="UTC"),
                 END_DATE=end_date, MODELS=models, get_json=lambda url, params: _om_get_json(params)):
        m.download(force=ctx.force)
        parts = [m.read_model(x) for x in models]
    end = pd.Timestamp(end_date, tz="UTC") + pd.Timedelta(hours=22)   # last full Open-Meteo day, shifted -1 h
    df = pd.concat(parts, axis=1, sort=True)
    df = df.loc[(df.index >= ctx.start_utc) & (df.index <= end)]
    df.index.name = "timestamp_utc"
    df = df.reset_index()
    df["timestamp_utc"] = df["timestamp_utc"].astype("datetime64[ns, UTC]")
    return df


def fetch_weather_europe(ctx: Ctx) -> pd.DataFrame:
    """Raw day1/day2 columns of the 9 European points for the window up to today + 2 days."""
    from src.data import load_openmeteo_europe as e
    end_date = (ctx.today + dt.timedelta(days=2)).isoformat()
    models = {k: (v[0], ctx.start.year, v[2], v[3]) for k, v in e.MODELS.items()}
    with patched(e, RAW_DIR=ctx.dir("openmeteo_europe"), START=pd.Timestamp(ctx.start, tz="UTC"),
                 END_DATE=end_date, MODELS=models, PAUSE_S=OM_PAUSE_S, fetch=_om_get_json):
        e.download(force=ctx.force)
        parts = [e.read_model(x) for x in models]
    end = pd.Timestamp(end_date, tz="UTC") + pd.Timedelta(hours=22)
    df = pd.concat(parts, axis=1, sort=True)
    df = df.loc[(df.index >= ctx.start_utc) & (df.index <= end)]
    df.index.name = "timestamp_utc"
    df = df.reset_index()
    df["timestamp_utc"] = df["timestamp_utc"].astype("datetime64[ns, UTC]")
    return df


def _driver_patches(module, ctx: Ctx, **extra):
    """Patches for the daily driver loaders: raw files, loader output and check files go to data/live/."""
    from src.data.drivers_utils import polite_get
    attrs = dict(raw_dir=ctx.raw_dir_fn(), processed_path=ctx.processed_path_fn(), write_check=_noop)
    if hasattr(module, "polite_get"):
        attrs["polite_get"] = functools.partial(polite_get, max_tries=3)
    attrs.update(extra)
    return patched(module, **attrs)


def fetch_gas(ctx: Ctx) -> pd.DataFrame:
    from src.data import load_gas as m
    p1 = int(pd.Timestamp(ctx.start - dt.timedelta(days=7), tz="UTC").timestamp())
    p2 = int(pd.Timestamp(ctx.today + dt.timedelta(days=1), tz="UTC").timestamp())
    with _driver_patches(m, ctx, PERIOD1=p1, PERIOD2=p2):
        return m.main(force=ctx.force)


def fetch_co2(ctx: Ctx) -> pd.DataFrame:
    """Only the current-year EEX report (the 2012-2025 archive is not needed for the window)."""
    from src.data import load_co2 as m
    from src.data.drivers_utils import BROWSER_UA, polite_get
    d = ctx.dir(m.RAW)

    def download(force: bool = False) -> None:
        f = d / m.CURRENT_FILE
        if f.exists() and not force:
            return
        r = polite_get(m.CURRENT_URL, min_pause_s=2, headers={"User-Agent": BROWSER_UA}, host_key="eex",
                       max_tries=3)
        f.write_bytes(r.content)

    def read_all() -> pd.DataFrame:
        return m.read_report((d / m.CURRENT_FILE).read_bytes())

    with _driver_patches(m, ctx, download=download, read_all=read_all):
        df = m.main(force=ctx.force)
    return df[pd.to_datetime(df["date"]) >= pd.Timestamp(ctx.start)]


def fetch_eurchf(ctx: Ctx) -> pd.DataFrame:
    from src.data import load_fx as m
    with _driver_patches(m, ctx):
        return m.main(force=ctx.force)


def fetch_reservoir(ctx: Ctx) -> pd.DataFrame:
    """Whole BFE file (small, and the same-week median needs the full history)."""
    from src.data import load_reservoirs as m
    with _driver_patches(m, ctx):
        return m.main(force=ctx.force)


# ----------------------------------------------------------------------------------------------------------
# combine: stored table + fresh rows -> new table (stored schema)
# ----------------------------------------------------------------------------------------------------------
def combine_default(key: str, stored: pd.DataFrame, fresh: pd.DataFrame, ctx: Ctx) -> pd.DataFrame:
    if key in DAILY and "available_from_utc" in fresh.columns:
        # a value is only kept once it is published (e.g. today's intraday gas price is not a close yet)
        fresh = fresh[fresh["available_from_utc"] <= pd.Timestamp.now(tz="UTC")]
    return merge_fresh(stored, fresh, key_col(key))


def combine_power(key: str, stored: pd.DataFrame, fresh: pd.DataFrame, ctx: Ctx) -> pd.DataFrame:
    """Merge the MW columns, then recompute the *_bad flags on the full frame, exactly as the loader does."""
    from src.data import load_swiss_power as m
    flags = [c for c in stored.columns if c.endswith("_bad")]
    values = stored.drop(columns=flags)
    merged = merge_fresh(values, fresh, "timestamp_utc")
    merged = m.add_flags(merged)
    return _cast_like(merged, stored)[list(stored.columns)]


def combine_weather_fc(key: str, stored: pd.DataFrame, fresh: pd.DataFrame, ctx: Ctx) -> pd.DataFrame:
    """Merge the raw lead columns, then recompute the safe columns and the bias correction on the full frame."""
    from src.data import load_openmeteo_forecast as m
    from src.data.check_weather_forecast import add_bias_correction
    raw_cols = [c for c in stored.columns if re.search(r"_fc_day[012]", c)]
    merged = merge_fresh(stored[["timestamp_utc", *raw_cols]], fresh, "timestamp_utc")
    merged = m.add_safe_columns(merged)
    merged = add_bias_correction(merged)
    return _cast_like(merged, stored)[list(stored.columns)]


EUROPE_RAW_FILE = "weather_europe_forecast_raw_hourly"


def combine_weather_europe(key: str, stored: pd.DataFrame, fresh: pd.DataFrame, ctx: Ctx) -> pd.DataFrame:
    """Merge with the stored raw day1/day2 file, then rebuild the safe columns with the loader's build_safe."""
    from src.data import load_openmeteo_europe as e
    stored_raw = pd.read_parquet(path("processed") / f"{EUROPE_RAW_FILE}.parquet")
    raw_cols = [c for c in stored_raw.columns if re.search(r"_day[12](_jma)?$", c)]
    merged = merge_fresh(stored_raw[["timestamp_utc", *raw_cols]], fresh, "timestamp_utc")
    safe, raw = e.build_safe(merged)
    raw.to_parquet(ctx.dir("_loader_output") / f"{EUROPE_RAW_FILE}.parquet", index=False)
    return _cast_like(safe, stored)[list(stored.columns)]


COMBINE = {"power": combine_power, "weather_fc": combine_weather_fc, "weather_europe": combine_weather_europe}


# ----------------------------------------------------------------------------------------------------------
# status
# ----------------------------------------------------------------------------------------------------------
def _local_end(ts: pd.Timestamp) -> str:
    """End of the hour starting at `ts`, in Zurich time, e.g. '19 Nov 24:00'."""
    end = (pd.Timestamp(ts) + pd.Timedelta(hours=1)).tz_convert(TZ)
    if end.hour == 0 and end.minute == 0:
        prev = end - pd.Timedelta(days=1)
        return f"{prev.day} {prev.strftime('%b')} 24:00"
    return f"{end.day} {end.strftime('%b %H:%M')}"


def last_timestamp(key: str, df: pd.DataFrame) -> pd.Timestamp | None:
    col = MAIN_COL.get(key)
    if df is None or len(df) == 0 or col not in df.columns:
        return None
    good = df[df[col].notna()]
    if good.empty:
        return None
    if key == "calendar":
        return local_midnight_utc(pd.Timestamp(good["date"].max()).date())
    if key in DAILY:
        return pd.Timestamp(good.sort_values(DAILY[key])["available_from_utc"].iloc[-1])
    return pd.Timestamp(good["timestamp_utc"].max())


def describe(key: str, df: pd.DataFrame, today: dt.date) -> str:
    """Plain-English 'data up to ...' sentence."""
    last = last_timestamp(key, df)
    if last is None:
        return "no values"
    if key == "calendar":
        last_day = pd.Timestamp(df["date"].max()).date()
        tomorrow = today + dt.timedelta(days=1)
        if tomorrow > last_day:
            return f"WARNING: calendar ends {last_day}, tomorrow ({tomorrow}) is not covered"
        return f"calendar covers up to {last_day:%d %b %Y}"
    if key in DAILY:
        good = df[df[MAIN_COL[key]].notna()]
        day = pd.Timestamp(good[DAILY[key]].max())
        return f"latest value for {day:%d %b}, usable from {last.tz_convert(TZ):%d %b %H:%M}"
    if key == "demand":
        return f"ewz publishes ~1.5 days late: data up to {_local_end(last)}"
    if key in FORECASTS:
        return f"forecasts up to {_local_end(last)}"
    return f"data up to {_local_end(last)}"


def _status(key: str, df: pd.DataFrame | None, rows_added: int, ok: bool, message: str) -> dict:
    last = last_timestamp(key, df) if df is not None else None
    return {"source": key, "label": LABELS.get(key, key),
            "last_timestamp_utc": last.isoformat() if last is not None else None,
            "rows_added": int(rows_added), "ok": bool(ok), "message": message}


# ----------------------------------------------------------------------------------------------------------
# main API
# ----------------------------------------------------------------------------------------------------------
def update_source(key: str, stored: pd.DataFrame, today: dt.date, force: bool) -> pd.DataFrame:
    """Download the window of one source and merge it with the stored table."""
    ctx = Ctx(today=today, raw=raw_root(today), start=window_start(stored, key, today), force=force)
    fetch = getattr(sys.modules[__name__], f"fetch_{key}")   # looked up at call time (tests patch it)
    fresh = fetch(ctx)
    combine = COMBINE.get(key)
    if combine is not None:
        new = combine(key, stored, fresh, ctx)
    else:
        new = combine_default(key, stored, fresh, ctx)
    if list(new.columns) != list(stored.columns):
        raise RuntimeError("schema changed after merge")
    return new


def save_cache(tables: dict, status: list[dict], today: dt.date) -> Path:
    out = processed_root(today)
    out.mkdir(parents=True, exist_ok=True)
    for key, df in tables.items():
        df.to_parquet(out / f"{TABLE_FILES[key]}.parquet", index=False)
    meta = {"today": today.isoformat(), "fetched_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
            "tables": sorted(tables), "sources": status}
    (out / "status.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return out


def load_cached_tables(today: dt.date | None = None) -> tuple[dict[str, pd.DataFrame], list[dict]] | None:
    """Merged tables and status of `today` from data/live/processed/<today>/ (None if there is no cache)."""
    today = today or zurich_today()
    folder = processed_root(today)
    status_file = folder / "status.json"
    if not status_file.exists():
        return None
    meta = json.loads(status_file.read_text(encoding="utf-8"))
    tables = {}
    for key in meta.get("tables", list(TABLE_FILES)):
        f = folder / f"{TABLE_FILES[key]}.parquet"
        if not f.exists():
            if key in OPTIONAL_TABLES:
                continue
            return None          # incomplete cache -> refresh again
        tables[key] = pd.read_parquet(f)
    return tables, meta["sources"]


def refresh_tables(today: dt.date | None = None, force: bool = False
                   ) -> tuple[dict[str, pd.DataFrame], list[dict]]:
    """Stored tables + the newest data of every source. Returns (tables, status list)."""
    today = today or zurich_today()
    if not force:
        cached = load_cached_tables(today)
        if cached is not None:
            return cached
    stored = load_tables()
    with system_certificates():
        tables, status = _refresh_all(stored, today, force)
    save_cache(tables, status, today)
    return tables, status


def _refresh_all(stored: dict, today: dt.date, force: bool) -> tuple[dict, list[dict]]:
    tables: dict[str, pd.DataFrame] = {}
    status: list[dict] = []
    for key in TABLE_FILES:
        if key not in stored:
            status.append(_status(key, None, 0, False, "no stored table"))
            continue
        old = stored[key]
        if key == "calendar":
            tables[key] = old
            msg = describe(key, old, today)
            status.append(_status(key, old, 0, not msg.startswith("WARNING"), msg))
            continue
        t0 = time.time()
        print(f"[refresh] {key} ...", flush=True)
        try:
            new = update_source(key, old, today, force)
            added = len(new) - len(old)
            tables[key] = new
            status.append(_status(key, new, added, True, describe(key, new, today)))
        except Exception as e:  # one failing source must not stop the refresh
            reason = f"{type(e).__name__}: {str(e)[:160]}"
            tables[key] = old
            status.append(_status(key, old, 0, False,
                                  f"download failed, using stored data ({describe(key, old, today)}): {reason}"))
        print(f"[refresh] {key} done in {time.time() - t0:.0f} s: {status[-1]['message']}", flush=True)
    return tables, status


def format_status(status: list[dict]) -> str:
    lines = [f"{'source':<15}{'ok':<5}{'last (UTC)':<27}{'+rows':>7}  message", "-" * 110]
    for s in status:
        lines.append(f"{s['source']:<15}{'yes' if s['ok'] else 'NO':<5}{str(s['last_timestamp_utc']):<27}"
                     f"{s['rows_added']:>7}  {s['message']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--force", action="store_true", help="download again even if today's cache exists")
    a = ap.parse_args(argv)
    t0 = time.time()
    _, status = refresh_tables(force=a.force)
    print(format_status(status))
    print(f"\nrefresh took {time.time() - t0:.0f} s; cache: {processed_root(zurich_today())}")


if __name__ == "__main__":
    main()
