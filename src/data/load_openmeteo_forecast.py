"""Archived weather FORECASTS for Zurich from the Open-Meteo Previous-Runs API.

For every valid hour the API returns the value of the current run (plain name) and the value that was
predicted ~24 h (`_previous_day1`) and ~48 h (`_previous_day2`) before that hour
(https://open-meteo.com/en/docs/previous-runs-api: "_previous_day1 is the value that was predicted 24 hours
before valid time, _previous_day2 48 hours before"). We checked with the Single-Runs API that
`_previous_dayN` at valid time V comes from the LATEST model run initialised at or before V - N*24 h.

Models fetched (point 47.378 N, 8.565 E):
- `icon_seamless` (DWD ICON-D2/EU/global): all 7 variables, real data from 2024-01-19 (day1) -> main columns.
- `ecmwf_ifs025`: all 7 variables from 2024-02-04 (temperature) / 2024-03-07 (radiation) -> `*_ecmwf` columns.
- `jma_seamless` (JMA GSM, ~0.5 deg): temperature, wind, precipitation, cloud cover, humidity back to 2018,
  no radiation / sunshine -> `*_jma` columns (only real forecast archive that covers the whole training period).

Time convention: Open-Meteo labels instantaneous values (temperature, wind, cloud, humidity) at the instant and
"preceding hour" values (radiation mean, precipitation sum, sunshine sum) at the END of the hour. We shift every
Open-Meteo stamp by -1 h, so `timestamp_utc` = START of the hour, matching the observed file
(row T holds the Open-Meteo value stamped T+1h).

Leakage-safe columns `*_fc_safe`: see `safe_lead_days()` and docs/assumptions_weather.md.

Output: data/processed/weather_forecast_hourly.parquet
Run:    .venv/bin/python -m src.data.load_openmeteo_forecast [--skip-download] [--force]
"""
from __future__ import annotations

import argparse
import json
import time

import numpy as np
import pandas as pd
import requests

from src.config import ROOT, load_config, path

URL = "https://previous-runs-api.open-meteo.com/v1/forecast"
LAT, LON = 47.378, 8.565
# Open-Meteo variable -> (our base name, conversion factor to our unit)
VARIABLES = {
    "temperature_2m": ("temp_c", 1.0),
    "shortwave_radiation": ("radiation_wm2", 1.0),
    "sunshine_duration": ("sunshine_min", 1 / 60),  # seconds -> minutes
    "wind_speed_10m": ("wind_ms", 1 / 3.6),         # km/h -> m/s
    "precipitation": ("precip_mm", 1.0),
    "cloud_cover": ("cloud_pct", 1.0),
    "relative_humidity_2m": ("humidity_pct", 1.0),
}
# model -> (column suffix, first year to fetch, variables available, run cadence h, publication delay h)
MODELS = {
    "icon_seamless": ("", 2024, list(VARIABLES), 3, 4),
    "ecmwf_ifs025": ("_ecmwf", 2024, list(VARIABLES), 6, 8),
    "jma_seamless": ("_jma", 2018,
                     ["temperature_2m", "wind_speed_10m", "precipitation", "cloud_cover", "relative_humidity_2m"],
                     6, 6),
}
LEADS = {"": "_fc_day0", "_previous_day1": "_fc_day1", "_previous_day2": "_fc_day2"}
START = pd.Timestamp("2018-12-01", tz="UTC")
END_DATE = "2026-11-03"  # a few days past the raw period so local days are complete

RAW_DIR = path("raw") / "openmeteo_forecast"
OUT_FILE = path("processed") / "weather_forecast_hourly.parquet"
CHECK_FILE = ROOT / "reports" / "data_checks" / "weather_forecast_hourly.md"


# ----------------------------------------------------------------------------------------------------------
# download
# ----------------------------------------------------------------------------------------------------------
def get_json(url: str, params: dict, tries: int = 6) -> dict:
    """GET with exponential backoff on 429 / 5xx."""
    for attempt in range(tries):
        r = requests.get(url, params=params, timeout=180)
        if r.status_code == 200:
            return r.json()
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(10 * 2 ** attempt)
            continue
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
    raise RuntimeError(f"giving up after {tries} tries: {url}")


def download(force: bool = False) -> None:
    """One cached JSON per model and year in data/raw/openmeteo_forecast/."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for model, (_, first_year, variables, _, _) in MODELS.items():
        for year in range(first_year, 2027):
            target = RAW_DIR / f"{model}_{year}.json"
            if target.exists() and not force:
                continue
            start = max(pd.Timestamp(f"{year}-01-01"), START.tz_localize(None) - pd.Timedelta(days=1))
            end = min(pd.Timestamp(f"{year}-12-31"), pd.Timestamp(END_DATE))
            hourly = [v + lead for v in variables for lead in LEADS]
            params = dict(latitude=LAT, longitude=LON, hourly=",".join(hourly), models=model, timezone="GMT",
                          start_date=start.date().isoformat(), end_date=end.date().isoformat())
            print(f"fetching {model} {year} ...")
            data = get_json(URL, params)
            target.write_text(json.dumps(data), encoding="utf-8")
            time.sleep(5)


# ----------------------------------------------------------------------------------------------------------
# leakage-safe lead selection
# ----------------------------------------------------------------------------------------------------------
def forecast_time_utc(timestamp_utc: pd.Series) -> pd.Series:
    """Our forecast time for the delivery day that contains each hour: day D 10:00 Europe/Zurich, D = local day - 1."""
    cfg = load_config()
    tz = cfg["timezone"]
    hh, mm = map(int, cfg["auction"]["forecast_time_local"].split(":"))
    local_day = timestamp_utc.dt.tz_convert(tz).dt.normalize().dt.tz_localize(None)  # naive local midnight
    issue_local = local_day - pd.Timedelta(days=1) + pd.Timedelta(hours=hh, minutes=mm)
    return issue_local.dt.tz_localize(tz).dt.tz_convert("UTC")


def run_init_utc(valid_om_utc: pd.Series, lead_days: int, cadence_h: int) -> pd.Series:
    """Model run behind `_previous_day<lead_days>`: latest run on the cadence grid at or before valid - lead*24 h."""
    return (valid_om_utc - pd.Timedelta(days=lead_days)).dt.floor(f"{cadence_h}h")


def safe_lead_days(timestamp_utc: pd.Series, cadence_h: int, delay_h: int) -> pd.Series:
    """Freshest lead (1 or 2 days) whose model run was published before our forecast time.

    Rule (re-derivable in a test):
      valid_om = timestamp_utc + 1 h               (Open-Meteo stamp of this row, see module docstring)
      F        = forecast_time_utc(timestamp_utc)  (day D 10:00 Europe/Zurich for delivery day D+1)
      init_N   = floor(valid_om - N*24 h, cadence_h)
      lead 1 is used if init_1 + delay_h <= F, otherwise lead 2 (which then must satisfy init_2 + delay_h <= F).
    """
    valid_om = timestamp_utc + pd.Timedelta(hours=1)
    F = forecast_time_utc(timestamp_utc)
    ok1 = run_init_utc(valid_om, 1, cadence_h) + pd.Timedelta(hours=delay_h) <= F
    ok2 = run_init_utc(valid_om, 2, cadence_h) + pd.Timedelta(hours=delay_h) <= F
    if not ok2.all():
        raise AssertionError("lead 2 is not always available before the forecast time")
    return pd.Series(np.where(ok1, 1, 2), index=timestamp_utc.index)


# ----------------------------------------------------------------------------------------------------------
# build
# ----------------------------------------------------------------------------------------------------------
def read_model(model: str) -> pd.DataFrame:
    """Concatenate the cached yearly JSON files of one model into a frame with our column names."""
    suffix, first_year, variables, _, _ = MODELS[model]
    frames = []
    for year in range(first_year, 2027):
        f = RAW_DIR / f"{model}_{year}.json"
        if not f.exists():
            continue
        h = json.loads(f.read_text(encoding="utf-8"))["hourly"]
        df = pd.DataFrame(h)
        df["timestamp_utc"] = pd.to_datetime(df.pop("time")).dt.tz_localize("UTC") - pd.Timedelta(hours=1)
        rename = {}
        for v in variables:
            base, factor = VARIABLES[v]
            for lead, our in LEADS.items():
                df[v + lead] = df[v + lead].astype(float) * factor
                rename[v + lead] = base + our + suffix
        frames.append(df.rename(columns=rename))
    df = pd.concat(frames).drop_duplicates("timestamp_utc", keep="last").set_index("timestamp_utc").sort_index()
    return df


def first_valid_dates(df: pd.DataFrame) -> pd.DataFrame:
    """First timestamp with a value and share missing after that, per column."""
    rows = []
    for c in df.columns:
        s = df[c]
        first = s.first_valid_index()
        after = s.loc[first:] if first is not None else s.iloc[:0]
        rows.append({"column": c, "first_valid_utc": first, "missing_after_first": after.isna().mean()})
    return pd.DataFrame(rows)


def add_safe_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add `*_fc_safe` (and the lead used) for every model."""
    ts = df["timestamp_utc"]
    for model, (suffix, _, variables, cadence, delay) in MODELS.items():
        lead = safe_lead_days(ts, cadence, delay)
        df[f"fc_safe_lead_days{suffix}"] = lead.astype("int8")
        for v in variables:
            base = VARIABLES[v][0]
            d1, d2 = df[f"{base}_fc_day1{suffix}"], df[f"{base}_fc_day2{suffix}"]
            df[f"{base}_fc_safe{suffix}"] = np.where(lead == 1, d1, d2)
    return df


def write_check(df: pd.DataFrame, fv: pd.DataFrame) -> None:
    CHECK_FILE.parent.mkdir(parents=True, exist_ok=True)
    lead = df["fc_safe_lead_days"]
    local_hour = df["timestamp_utc"].dt.tz_convert("Europe/Zurich").dt.hour
    share_d1 = (lead == 1).groupby(local_hour).mean()
    d1_hours = sorted(share_d1[share_d1 > 0].index.tolist())
    lines = [
        "# Data check: weather_forecast_hourly (Open-Meteo previous-runs API)",
        "",
        f"- Rows: {len(df):,}; timestamp_utc {df['timestamp_utc'].min()} -> {df['timestamp_utc'].max()} (hourly grid)",
        "- Main columns (no suffix) = `icon_seamless`; `_ecmwf` = `ecmwf_ifs025`; `_jma` = `jma_seamless` (JMA GSM).",
        "- Time shift: Open-Meteo stamp -1 h -> timestamp_utc = START of hour.",
        "- Units converted: sunshine s -> min, wind km/h -> m/s.",
        f"- `*_fc_safe` (icon) uses day1 for delivery-day local hours {d1_hours} (share per hour: "
        + ", ".join(f"{h}: {share_d1[h]:.2f}" for h in d1_hours) + "), day2 otherwise.",
        "",
        "## First non-null value and missing share after it, per column",
        "",
        "| column | first valid (UTC, start of hour) | missing after first |",
        "|---|---|---|",
    ]
    for _, r in fv.iterrows():
        lines.append(f"| {r['column']} | {r['first_valid_utc']} | {r['missing_after_first']:.3%} |")
    CHECK_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(skip_download: bool = False, force: bool = False) -> pd.DataFrame:
    """Build data/processed/weather_forecast_hourly.parquet."""
    if not skip_download:
        download(force=force)
    parts = [read_model(m) for m in MODELS]
    end = pd.Timestamp(END_DATE, tz="UTC") + pd.Timedelta(hours=22)  # last full Open-Meteo day, shifted -1 h
    df = pd.concat(parts, axis=1, sort=True)
    df = df.loc[(df.index >= START) & (df.index <= end)]
    # keep rows from the first real forecast value of any model on
    first = min(df[c].first_valid_index() for c in df.columns if "_fc_day1" in c)
    grid = pd.date_range(first, end, freq="h", tz="UTC", name="timestamp_utc")
    df = df.reindex(grid).reset_index()
    df["timestamp_utc"] = df["timestamp_utc"].astype("datetime64[ns, UTC]")
    fv = first_valid_dates(df.set_index("timestamp_utc"))
    df = add_safe_columns(df)
    # bias correction of the safe temperature (fit on observed data before the validation period)
    try:
        from src.data.check_weather_forecast import add_bias_correction
        df = add_bias_correction(df)
    except (FileNotFoundError, ImportError) as e:
        print(f"bias correction skipped ({e})")
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_FILE, index=False)
    write_check(df, fv)
    print(f"wrote {OUT_FILE} ({len(df):,} rows, {df['timestamp_utc'].min()} -> {df['timestamp_utc'].max()})")
    return df


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--skip-download", action="store_true", help="rebuild from cached raw files only")
    ap.add_argument("--force", action="store_true", help="re-download even if raw files exist")
    a = ap.parse_args()
    main(skip_download=a.skip_download, force=a.force)
