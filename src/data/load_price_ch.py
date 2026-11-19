"""Swiss day-ahead price (bidding zone CH) from the Energy-Charts API.

Output: data/processed/price_ch_hourly.parquet with
    timestamp_utc (start of the hour, UTC), price_eur_mwh, n_values

The API returns UTC unix timestamps (start of the delivery period). Up to the
end of the hourly auction the step is 1 hour; after the switch to 15-minute
products the four quarter-hour prices are averaged to one hourly price.
`n_values` tells how many source values went into each hour (1 or 4).

Run:  .venv/bin/python -m src.data.load_price_ch [--skip-download] [--force]
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta

import numpy as np
import pandas as pd

from src.config import path
from src.data._energy_charts_targets import fetch_json

RAW_DIR = path("raw") / "energy_charts_price_ch"
OUT_FILE = path("processed") / "price_ch_hourly.parquet"
CHECK_FILE = path("reports") / "data_checks" / "price_ch_hourly.md"
FIRST_YEAR = 2019
START_UTC = pd.Timestamp("2019-01-01", tz="Europe/Zurich").tz_convert("UTC")  # local midnight = 2018-12-31 23:00 UTC


def download(force: bool = False, skip_download: bool = False) -> list[dict]:
    """Download one JSON per calendar year (cached in data/raw/energy_charts_price_ch/)."""
    today = date.today()
    chunks = []
    for year in range(FIRST_YEAR, today.year + 1):
        start = f"{year}-01-01"
        # the API treats `end` as a whole (local) day, inclusive
        end = f"{year}-12-31" if year < today.year else (today + timedelta(days=2)).isoformat()
        cache = RAW_DIR / f"price_CH_{year}.json"
        print(f"price CH {year}: {'cache' if cache.exists() and not force else 'download'}")
        data = fetch_json("price", {"bzn": "CH", "start": start, "end": end}, cache,
                          force=force, skip_download=skip_download)
        if data is None:
            print(f"  no data for {year}")
            continue
        chunks.append(data)
    return chunks


def to_hourly(chunks: list[dict]) -> tuple[pd.DataFrame, dict]:
    """Turn the JSON chunks into an hourly UTC table. Returns (table, info for the check file)."""
    raw = pd.concat(
        [pd.DataFrame({"unix": c["unix_seconds"], "price": c["price"]}) for c in chunks],
        ignore_index=True,
    )
    raw["ts"] = pd.to_datetime(raw["unix"], unit="s", utc=True)
    n_raw = len(raw)
    raw = raw.drop_duplicates("ts").sort_values("ts")   # yearly chunks overlap by a few hours
    info = {"raw_rows": n_raw, "overlap_rows_removed": n_raw - len(raw),
            "null_prices_raw": int(raw["price"].isna().sum())}

    # where does the source step change from 60 to 15 minutes?
    step = raw["ts"].diff().dt.total_seconds().div(60)
    first_15 = raw.loc[step.shift(-1) == 15, "ts"]  # value whose successor is 15 min later
    info["first_15min_value_utc"] = str(first_15.iloc[0]) if len(first_15) else "none"

    raw["hour"] = raw["ts"].dt.floor("h")
    hourly = raw.groupby("hour").agg(price_eur_mwh=("price", "mean"),
                                     n_values=("price", "count")).reset_index()
    hourly = hourly.rename(columns={"hour": "timestamp_utc"})

    # put on a complete hourly grid so missing hours become visible as NaN
    grid = pd.date_range(START_UTC, hourly["timestamp_utc"].max(), freq="h")
    hourly = hourly.set_index("timestamp_utc").reindex(grid)
    hourly.index.name = "timestamp_utc"
    hourly["n_values"] = hourly["n_values"].fillna(0).astype(int)
    hourly = hourly.reset_index()
    hourly = hourly[hourly["timestamp_utc"] >= START_UTC]
    # an hour in the 15-min era with fewer than 4 values is incomplete
    era15 = hourly["timestamp_utc"] >= pd.Timestamp(info["first_15min_value_utc"]).floor("h") \
        if info["first_15min_value_utc"] != "none" else pd.Series(False, index=hourly.index)
    info["incomplete_15min_hours"] = int(((hourly["n_values"] < 4) & (hourly["n_values"] > 0) & era15).sum())
    return hourly, info


def gaps_table(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """List runs of consecutive missing hours in `col`."""
    miss = df[col].isna()
    run_id = (miss != miss.shift()).cumsum()
    runs = df[miss].groupby(run_id[miss])["timestamp_utc"].agg(["first", "last", "count"])
    return runs.reset_index(drop=True)


def write_check(df: pd.DataFrame, info: dict) -> None:
    CHECK_FILE.parent.mkdir(parents=True, exist_ok=True)
    gaps = gaps_table(df, "price_eur_mwh")
    p = df["price_eur_mwh"]
    in_period = df[df["timestamp_utc"] < pd.Timestamp("2026-11-01", tz="UTC")]
    lines = [
        "# Check: price_ch_hourly.parquet (Energy-Charts day-ahead, bzn=CH)",
        "",
        f"- rows: {len(df)} hourly rows",
        f"- first / last timestamp_utc: {df['timestamp_utc'].min()} / {df['timestamp_utc'].max()}",
        f"- missing hours (NaN price), whole file: {int(p.isna().sum())} ({p.isna().mean():.4%})",
        f"- missing hours 2019-01-01 → 2026-10-31 UTC: {int(in_period['price_eur_mwh'].isna().sum())}",
        f"- duplicate timestamps removed (overlap of yearly chunks): {info['overlap_rows_removed']}",
        f"- null prices in raw JSON: {info['null_prices_raw']}",
        f"- first 15-min value in source (UTC): {info['first_15min_value_utc']}; hours after that are the mean of 4 quarter-hours",
        f"- incomplete hours in the 15-min era (<4 values): {info['incomplete_15min_hours']}",
        f"- price range: min {p.min():.2f}, max {p.max():.2f}, mean {p.mean():.2f} EUR/MWh",
        f"- hours with negative price: {int((p < 0).sum())}",
        "",
        "## Gaps (runs of missing hours)",
        "",
    ]
    if len(gaps):
        lines += ["| first | last | hours |", "|---|---|---|"]
        lines += [f"| {r['first']} | {r['last']} | {r['count']} |" for _, r in gaps.iterrows()]
    else:
        lines.append("none")
    lines += ["", "## Mean price per year (EUR/MWh)", "", "| year | mean | min | max |", "|---|---|---|---|"]
    for y, g in df.groupby(df["timestamp_utc"].dt.year)["price_eur_mwh"]:
        lines.append(f"| {y} | {g.mean():.1f} | {g.min():.1f} | {g.max():.1f} |")
    CHECK_FILE.write_text("\n".join(lines) + "\n")


def main(skip_download: bool = False, force: bool = False) -> pd.DataFrame:
    """Build data/processed/price_ch_hourly.parquet (from cache only if skip_download)."""
    chunks = download(force=force, skip_download=skip_download)
    df, info = to_hourly(chunks)
    # drop trailing hours without a price (the API grid can run past the last auction)
    last_valid = df["price_eur_mwh"].last_valid_index()
    df = df.loc[:last_valid].reset_index(drop=True)
    df["price_eur_mwh"] = df["price_eur_mwh"].astype(float)
    df["timestamp_utc"] = df["timestamp_utc"].astype("datetime64[ns, UTC]")
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_FILE, index=False)
    write_check(df, info)
    print(f"wrote {OUT_FILE} ({len(df)} rows, {df['timestamp_utc'].min()} → {df['timestamp_utc'].max()})")
    return df


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--skip-download", action="store_true", help="use cached raw files only")
    ap.add_argument("--force", action="store_true", help="re-download even if cached")
    a = ap.parse_args()
    main(skip_download=a.skip_download, force=a.force)
