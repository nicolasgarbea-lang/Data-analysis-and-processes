"""Swiss load and production (Energy-Charts `public_power`, country=ch) and the
Energy-Charts day-ahead solar forecast for Switzerland.

Outputs
- data/processed/swiss_power_hourly.parquet
    timestamp_utc (start of the hour, UTC), load_mw, residual_load_mw, solar_mw, wind_onshore_mw,
    hydro_run_of_river_mw, hydro_water_reservoir_mw, hydro_pumped_storage_mw, nuclear_mw,
    others_mw, cross_border_trading_mw, plus quality flags (see below)
- data/processed/swiss_solar_forecast_hourly.parquet
    timestamp_utc, solar_forecast_mw

Quality flags (True = do not trust this value):
- load_bad: load missing, zero, part of a long constant run, far (< 50 % / > 200 %) from the
  surrounding week's median, or on/after the known glitch date 2026-11-16
- solar_bad: solar missing or part of a long constant run during daylight
- wind_bad: wind missing or above 500 MW (impossible for Switzerland)

Run:  .venv/bin/python -m src.data.load_swiss_power [--skip-download] [--force]
"""
from __future__ import annotations

import argparse
import re
from datetime import date, timedelta

import numpy as np
import pandas as pd

from src.config import path
from src.data._energy_charts_targets import fetch_json

RAW_DIR = path("raw") / "energy_charts_public_power_ch"
RAW_FC_DIR = path("raw") / "energy_charts_solar_forecast_ch"
OUT_FILE = path("processed") / "swiss_power_hourly.parquet"
OUT_FC_FILE = path("processed") / "swiss_solar_forecast_hourly.parquet"
CHECK_FILE = path("reports") / "data_checks" / "swiss_power_hourly.md"
CHECK_FC_FILE = path("reports") / "data_checks" / "swiss_solar_forecast_hourly.md"
FIRST_YEAR = 2019
START_UTC = pd.Timestamp("2019-01-01", tz="Europe/Zurich").tz_convert("UTC")  # local midnight = 2018-12-31 23:00 UTC
# Energy-Charts Swiss load is known to be broken after this day (see docs/data_sources.md)
LOAD_BROKEN_FROM_UTC = pd.Timestamp("2026-11-16", tz="UTC")
WIND_MAX_MW = 500     # Swiss installed wind is < 200 MW
CONST_RUN_HOURS = 6  # a value repeated for >= this many hours counts as a "constant stretch"

# production types we keep (Energy-Charts name -> our column name)
KEEP = {
    "Load": "load_mw",
    "Residual load": "residual_load_mw",
    "Solar": "solar_mw",
    "Wind onshore": "wind_onshore_mw",
    "Hydro Run-of-River": "hydro_run_of_river_mw",
    "Hydro water reservoir": "hydro_water_reservoir_mw",
    "Hydro pumped storage": "hydro_pumped_storage_mw",
    "Hydro pumped storage consumption": "hydro_pumped_storage_consumption_mw",
    "Nuclear": "nuclear_mw",
    "Others": "others_mw",
    "Cross border electricity trading": "cross_border_trading_mw",
}


def _year_ranges():
    today = date.today()
    for year in range(FIRST_YEAR, today.year + 1):
        end = f"{year}-12-31" if year < today.year else (today + timedelta(days=1)).isoformat()
        yield year, f"{year}-01-01", end


def _snake(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") + "_mw"


def download_power(force=False, skip_download=False) -> list[dict]:
    chunks = []
    for year, start, end in _year_ranges():
        cache = RAW_DIR / f"public_power_CH_{year}.json"
        print(f"public_power CH {year}: {'cache' if cache.exists() and not force else 'download'}")
        d = fetch_json("public_power", {"country": "ch", "start": start, "end": end}, cache,
                       force=force, skip_download=skip_download)
        if d is not None:
            chunks.append(d)
    return chunks


def download_forecast(force=False, skip_download=False) -> list[dict]:
    chunks = []
    for year, start, end in _year_ranges():
        cache = RAW_FC_DIR / f"solar_forecast_dayahead_CH_{year}.json"
        print(f"solar forecast CH {year}: {'cache' if cache.exists() and not force else 'download'}")
        d = fetch_json("public_power_forecast",
                       {"country": "ch", "production_type": "solar", "forecast_type": "day-ahead",
                        "start": start, "end": end},
                       cache, force=force, skip_download=skip_download)
        if d is not None and d.get("unix_seconds"):
            chunks.append(d)
    return chunks


def power_table(chunks: list[dict]) -> tuple[pd.DataFrame, list[str]]:
    """Wide hourly table of all MW series. Returns (table, list of source names seen)."""
    frames, names = [], set()
    for c in chunks:
        f = pd.DataFrame({"ts": pd.to_datetime(c["unix_seconds"], unit="s", utc=True)})
        for p in c["production_types"]:
            names.add(p["name"])
            if "share" in p["name"].lower():   # percentages, not MW
                continue
            col = KEEP.get(p["name"], _snake(p["name"]))
            f[col] = pd.to_numeric(pd.Series(p["data"]), errors="coerce").values
        frames.append(f)
    raw = pd.concat(frames, ignore_index=True).drop_duplicates("ts").sort_values("ts")
    # the source should be hourly; if a period is 15-min, average it to the hour
    raw["timestamp_utc"] = raw["ts"].dt.floor("h")
    value_cols = [c for c in raw.columns if c.endswith("_mw")]
    hourly = raw.groupby("timestamp_utc")[value_cols].mean()
    grid = pd.date_range(START_UTC, hourly.index.max(), freq="h", name="timestamp_utc")
    hourly = hourly.reindex(grid).reset_index()
    return hourly, sorted(names)


def constant_runs(s: pd.Series, min_len: int) -> pd.Series:
    """True where the value is part of a run of identical (non-NaN) values of length >= min_len."""
    run_id = (s != s.shift()).cumsum()
    run_len = s.groupby(run_id).transform("size")
    return (run_len >= min_len) & s.notna()


def add_flags(df: pd.DataFrame) -> pd.DataFrame:
    load = df["load_mw"]
    # level check: compare with the median of the surrounding week (centred window; this is only a
    # data-quality flag, it is never used as a feature, so looking ahead is fine here)
    week_median = load.rolling(7 * 24 + 1, center=True, min_periods=24).median()
    ratio = load / week_median
    df["load_bad"] = (load.isna() | (load <= 0) | constant_runs(load, CONST_RUN_HOURS)
                      | (ratio < 0.5) | (ratio > 2.0)
                      | (df["timestamp_utc"] >= LOAD_BROKEN_FROM_UTC))
    # a day with many bad hours is not trusted at all (e.g. 2024-12-05)
    day = df["timestamp_utc"].dt.tz_convert("Europe/Zurich").dt.date
    bad_hours_per_day = df["load_bad"].groupby(day).transform("sum")
    df["load_bad"] = df["load_bad"] | (bad_hours_per_day >= 6)
    solar = df["solar_mw"]
    # solar is 0 every night, so only constant runs with a value > 0 are suspicious
    df["solar_bad"] = solar.isna() | (constant_runs(solar, CONST_RUN_HOURS) & (solar > 0))
    # Swiss wind capacity is below 200 MW, so anything above WIND_MAX_MW is a data error
    df["wind_bad"] = df["wind_onshore_mw"].isna() | (df["wind_onshore_mw"] > WIND_MAX_MW)
    return df


def runs_of(mask: pd.Series, ts: pd.Series) -> pd.DataFrame:
    rid = (mask != mask.shift()).cumsum()
    g = ts[mask].groupby(rid[mask]).agg(["first", "last", "count"])
    return g.reset_index(drop=True)


def write_power_check(df: pd.DataFrame, names: list[str]) -> None:
    CHECK_FILE.parent.mkdir(parents=True, exist_ok=True)
    value_cols = [c for c in df.columns if c.endswith("_mw")]
    lines = [
        "# Check: swiss_power_hourly.parquet (Energy-Charts public_power, country=ch)",
        "",
        f"- rows: {len(df)} hourly rows",
        f"- first / last timestamp_utc: {df['timestamp_utc'].min()} / {df['timestamp_utc'].max()}",
        f"- duplicate timestamps: {int(df['timestamp_utc'].duplicated().sum())}",
        f"- source series names: {', '.join(names)} (the 'share' series are % and were dropped)",
        f"- load_bad hours: {int(df['load_bad'].sum())} ({df['load_bad'].mean():.3%}); "
        f"before 2026-11-01: {int(df.loc[df['timestamp_utc'] < '2026-11-01', 'load_bad'].sum())}",
        f"- solar_bad hours: {int(df['solar_bad'].sum())}; wind_bad hours: {int(df['wind_bad'].sum())} "
        f"({df.loc[df['wind_bad'], 'timestamp_utc'].astype(str).tolist()})",
        "- load_bad rule: missing, ≤ 0, constant ≥ 6 h, < 50 % or > 200 % of the centred 7-day median, "
        "or on/after 2026-11-16 (known Energy-Charts glitch); a local day with ≥ 6 bad hours is flagged completely",
        "",
        "## Missing share and constant stretches per column",
        "",
        f"| column | % missing | hours with value 0 | hours in constant runs ≥ {CONST_RUN_HOURS} h (value ≠ 0) | min | max |",
        "|---|---|---|---|---|---|",
    ]
    for c in value_cols:
        s = df[c]
        cr = constant_runs(s, CONST_RUN_HOURS) & (s != 0)
        lines.append(f"| {c} | {s.isna().mean():.3%} | {int((s == 0).sum())} | {int(cr.sum())} | "
                     f"{s.min():.1f} | {s.max():.1f} |")

    lines += ["", "## Load problems (runs of load_bad hours)", "", "| first | last | hours |", "|---|---|---|"]
    for _, r in runs_of(df["load_bad"], df["timestamp_utc"]).iterrows():
        lines.append(f"| {r['first']} | {r['last']} | {r['count']} |")
    lines += ["", "## Solar problems (runs of solar_bad hours)", "", "| first | last | hours |", "|---|---|---|"]
    for _, r in runs_of(df["solar_bad"], df["timestamp_utc"]).iterrows():
        lines.append(f"| {r['first']} | {r['last']} | {r['count']} |")

    lines += ["", "## Yearly means (MW, local calendar year)", ""]
    yearly = df.groupby(df["timestamp_utc"].dt.tz_convert("Europe/Zurich").dt.year)[value_cols].mean().round(0)
    lines.append("| year | " + " | ".join(value_cols) + " |")
    lines.append("|---" * (len(value_cols) + 1) + "|")
    for y, r in yearly.iterrows():
        lines.append(f"| {y} | " + " | ".join(f"{v:.0f}" for v in r.values) + " |")

    # last days: show daily mean load, so the November 2026 glitch is visible
    tail = df[df["timestamp_utc"] >= "2026-11-01"]
    daily = tail.groupby(tail["timestamp_utc"].dt.date)[["load_mw", "solar_mw"]].agg(["mean", "min", "max", "count"])
    lines += ["", "## Daily load and solar from 2026-11-01 (UTC days)", "",
              "| day | load mean | load min | load max | load n | solar mean | solar max |", "|---|---|---|---|---|---|---|"]
    for dday, r in daily.iterrows():
        lines.append(f"| {dday} | {r[('load_mw','mean')]:.0f} | {r[('load_mw','min')]:.0f} | {r[('load_mw','max')]:.0f} | "
                     f"{int(r[('load_mw','count')])} | {r[('solar_mw','mean')]:.0f} | {r[('solar_mw','max')]:.0f} |")
    CHECK_FILE.write_text("\n".join(lines) + "\n")


def forecast_table(chunks: list[dict]) -> pd.DataFrame:
    if not chunks:
        return pd.DataFrame({"timestamp_utc": pd.Series(dtype="datetime64[ns, UTC]"),
                             "solar_forecast_mw": pd.Series(dtype=float)})
    raw = pd.concat([pd.DataFrame({"ts": pd.to_datetime(c["unix_seconds"], unit="s", utc=True),
                                   "v": pd.to_numeric(pd.Series(c["forecast_values"]), errors="coerce")})
                     for c in chunks], ignore_index=True).drop_duplicates("ts").sort_values("ts")
    raw["timestamp_utc"] = raw["ts"].dt.floor("h")
    fc = raw.groupby("timestamp_utc")["v"].mean().rename("solar_forecast_mw")
    first_valid = fc.first_valid_index()
    grid = pd.date_range(first_valid, fc.index.max(), freq="h", name="timestamp_utc")
    return fc.reindex(grid).reset_index()


def write_forecast_check(fc: pd.DataFrame, power: pd.DataFrame) -> None:
    lines = ["# Check: swiss_solar_forecast_hourly.parquet (Energy-Charts day-ahead solar forecast, CH)", ""]
    if fc.empty:
        lines.append("No forecast data returned.")
        CHECK_FC_FILE.write_text("\n".join(lines) + "\n")
        return
    s = fc["solar_forecast_mw"]
    lines += [
        f"- rows: {len(fc)} hourly rows",
        f"- first / last timestamp_utc: {fc['timestamp_utc'].min()} / {fc['timestamp_utc'].max()}",
        f"- first non-null value: {fc.loc[s.notna(), 'timestamp_utc'].min()}",
        f"- missing hours inside its range: {int(s.isna().sum())} ({s.isna().mean():.3%})",
        f"- duplicate timestamps: {int(fc['timestamp_utc'].duplicated().sum())}",
        "",
        "## Scale compared with actual solar (public_power Solar)",
        "",
        "Ratio = sum of forecast / sum of actual over hours where both exist. "
        "Correlation = hourly Pearson correlation.",
        "",
        "| year | hours | forecast mean MW | actual mean MW | ratio | forecast max | actual max | corr |",
        "|---|---|---|---|---|---|---|---|",
    ]
    j = fc.merge(power[["timestamp_utc", "solar_mw"]], on="timestamp_utc").dropna()
    for y, g in j.groupby(j["timestamp_utc"].dt.tz_convert("Europe/Zurich").dt.year):
        if g["solar_mw"].sum() <= 0:
            continue
        ratio = g["solar_forecast_mw"].sum() / g["solar_mw"].sum()
        lines.append(f"| {y} | {len(g)} | {g['solar_forecast_mw'].mean():.0f} | {g['solar_mw'].mean():.0f} | "
                     f"{ratio:.2f} | {g['solar_forecast_mw'].max():.0f} | {g['solar_mw'].max():.0f} | "
                     f"{g['solar_forecast_mw'].corr(g['solar_mw']):.3f} |")
    lines += ["", "## By month (ratio forecast / actual)", "", "| month | ratio | corr |", "|---|---|---|"]
    for m, g in j.groupby(j["timestamp_utc"].dt.tz_convert("Europe/Zurich").dt.strftime("%Y-%m")):
        if g["solar_mw"].sum() > 0:
            lines.append(f"| {m} | {g['solar_forecast_mw'].sum() / g['solar_mw'].sum():.2f} | "
                         f"{g['solar_forecast_mw'].corr(g['solar_mw']):.3f} |")
    CHECK_FC_FILE.write_text("\n".join(lines) + "\n")


def main(skip_download: bool = False, force: bool = False) -> pd.DataFrame:
    """Build swiss_power_hourly.parquet and swiss_solar_forecast_hourly.parquet."""
    power, names = power_table(download_power(force, skip_download))
    # drop trailing hours where nothing at all is reported
    value_cols = [c for c in power.columns if c.endswith("_mw")]
    last = power[value_cols].dropna(how="all").index.max()
    power = power.loc[:last].copy()
    power = add_flags(power)
    power["timestamp_utc"] = power["timestamp_utc"].astype("datetime64[ns, UTC]")
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    power.to_parquet(OUT_FILE, index=False)
    write_power_check(power, names)
    print(f"wrote {OUT_FILE} ({len(power)} rows)")

    fc = forecast_table(download_forecast(force, skip_download))
    fc["timestamp_utc"] = fc["timestamp_utc"].astype("datetime64[ns, UTC]")
    fc.to_parquet(OUT_FC_FILE, index=False)
    write_forecast_check(fc, power)
    print(f"wrote {OUT_FC_FILE} ({len(fc)} rows)")
    return power


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--skip-download", action="store_true", help="use cached raw files only")
    ap.add_argument("--force", action="store_true", help="re-download even if cached")
    a = ap.parse_args()
    main(skip_download=a.skip_download, force=a.force)
