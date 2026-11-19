"""Observed hourly weather at MeteoSwiss station SMA (Zürich-Fluntern).

Source: MeteoSwiss Open Data (SwissMetNet), files
    ogd-smn_sma_h_historical_2010-2019.csv, ogd-smn_sma_h_historical_2020-2029.csv, ogd-smn_sma_h_recent.csv
from https://data.geo.admin.ch/ch.meteoschweiz.ogd-smn/sma/

Time convention (official MeteoSwiss OGD documentation, https://opendatadocs.meteoswiss.ch/general/download,
section "Time stamps and time intervals"): all reference time stamps are UTC, and for hourly ("h") values
"ReferenceTS 16:00 = 15:10 to 16:00", i.e. the time stamp marks the END of the measuring interval.
We therefore subtract one hour so that `timestamp_utc` is the START of the hour the value describes.

Output: data/processed/weather_observed_hourly.parquet
    timestamp_utc, temp_c, sunshine_min, radiation_wm2, wind_ms, precip_mm, humidity_pct,
    plus one boolean `<col>_interpolated` flag per value column.

Run:  .venv/bin/python -m src.data.load_meteoswiss [--skip-download] [--force]
"""
from __future__ import annotations

import argparse
import time

import numpy as np
import pandas as pd
import requests

from src.config import ROOT, path

BASE_URL = "https://data.geo.admin.ch/ch.meteoschweiz.ogd-smn"
FILES = [
    "sma/ogd-smn_sma_h_historical_2010-2019.csv",
    "sma/ogd-smn_sma_h_historical_2020-2029.csv",
    "sma/ogd-smn_sma_h_recent.csv",
    "ogd-smn_meta_parameters.csv",  # code list, kept for documentation
]
# MeteoSwiss parameter code -> our column name (meanings checked in ogd-smn_meta_parameters.csv)
COLUMNS = {
    "tre200h0": "temp_c",         # air temperature 2 m above ground, hourly mean, °C
    "sre000h0": "sunshine_min",   # sunshine duration, hourly sum, min
    "gre000h0": "radiation_wm2",  # global radiation, hourly mean, W/m²
    "fkl010h0": "wind_ms",        # wind speed scalar, hourly mean, m/s
    "rre150h0": "precip_mm",      # precipitation, hourly sum, mm
    "ure200h0": "humidity_pct",   # relative humidity 2 m, hourly mean, %
}
START = pd.Timestamp("2018-12-01", tz="UTC")
MAX_GAP_HOURS = 3  # gaps up to this length are filled by linear interpolation

RAW_DIR = path("raw") / "meteoswiss"
OUT_FILE = path("processed") / "weather_observed_hourly.parquet"
CHECK_FILE = ROOT / "reports" / "data_checks" / "weather_observed_hourly.md"


def download(force: bool = False) -> None:
    """Download the station files (cached: skipped if the file exists, unless force=True)."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for rel in FILES:
        target = RAW_DIR / rel.split("/")[-1]
        # the "recent" file changes daily, the historical ones are stable
        if target.exists() and not force:
            continue
        for attempt in range(5):
            r = requests.get(f"{BASE_URL}/{rel}", timeout=120)
            if r.status_code == 200:
                target.write_bytes(r.content)
                break
            time.sleep(2 ** attempt * 5)
        else:
            raise RuntimeError(f"Download failed: {rel} (HTTP {r.status_code})")
        time.sleep(1)


def read_raw() -> tuple[pd.DataFrame, int]:
    """Read and join the three station files. Returns (frame, number of duplicate rows dropped)."""
    frames = []
    for rel in FILES[:3]:
        f = RAW_DIR / rel.split("/")[-1]
        df = pd.read_csv(f, sep=";", encoding="cp1252", usecols=["reference_timestamp", *COLUMNS])
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    ts_end = pd.to_datetime(df["reference_timestamp"], format="%d.%m.%Y %H:%M").dt.tz_localize("UTC")
    # END-of-interval stamp -> START of the hour described
    df["timestamp_utc"] = ts_end - pd.Timedelta(hours=1)
    df = df.drop(columns="reference_timestamp").rename(columns=COLUMNS)
    n_before = len(df)
    # historical and recent files overlap: keep the last file's value (recent = newest checks)
    df = df.drop_duplicates(subset="timestamp_utc", keep="last")
    n_dup = n_before - len(df)
    return df.sort_values("timestamp_utc").reset_index(drop=True), n_dup


def find_gaps(s: pd.Series) -> pd.DataFrame:
    """List runs of consecutive NaN in a series indexed by time: start, end (last missing hour), hours."""
    na = s.isna().to_numpy()
    if not na.any():
        return pd.DataFrame(columns=["start", "end", "hours"])
    idx = s.index
    change = np.diff(np.r_[0, na.astype(int), 0])
    starts, ends = np.where(change == 1)[0], np.where(change == -1)[0] - 1
    return pd.DataFrame({"start": idx[starts], "end": idx[ends], "hours": ends - starts + 1})


def fill_short_gaps(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Linear interpolation of gaps <= MAX_GAP_HOURS (flagged); longer gaps stay NaN. Returns (df, gap tables)."""
    gaps = {}
    for col in COLUMNS.values():
        g = find_gaps(df[col])
        gaps[col] = g
        short = g[g["hours"] <= MAX_GAP_HOURS]
        fill_mask = pd.Series(False, index=df.index)
        for _, row in short.iterrows():
            fill_mask.loc[row["start"]:row["end"]] = True
        interp = df[col].interpolate(method="time", limit_area="inside")
        df[col] = df[col].where(~fill_mask, interp)
        df[f"{col}_interpolated"] = fill_mask
    return df, gaps


def write_check(df: pd.DataFrame, n_dup: int, gaps: dict, raw_missing: dict) -> None:
    """Write the short data-check markdown file."""
    CHECK_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Data check: weather_observed_hourly (MeteoSwiss SMA Zürich-Fluntern)",
        "",
        f"- Rows: {len(df):,} (hourly, complete UTC grid)",
        f"- First / last timestamp_utc: {df['timestamp_utc'].min()} / {df['timestamp_utc'].max()}",
        f"- Duplicates removed after joining historical + recent files: {n_dup:,}",
        "- Time shift: MeteoSwiss hourly stamp = END of interval -> shifted -1 h to START of hour.",
        f"- Gaps <= {MAX_GAP_HOURS} h linearly interpolated (flag column `<col>_interpolated`), longer gaps left NaN.",
        "",
        "| column | missing before fill | missing before fill % | filled (<=3 h) | still missing | still missing % | long gaps (>3 h) |",
        "|---|---|---|---|---|---|---|",
    ]
    for col in COLUMNS.values():
        n_fill = int(df[f"{col}_interpolated"].sum())
        n_left = int(df[col].isna().sum())
        n_long = int((gaps[col]["hours"] > MAX_GAP_HOURS).sum())
        lines.append(
            f"| {col} | {raw_missing[col]:,} | {raw_missing[col] / len(df):.3%} | {n_fill:,} | {n_left:,} | "
            f"{n_left / len(df):.3%} | {n_long} |"
        )
    lines += ["", "## Gaps longer than 3 h (left as NaN)", ""]
    any_long = False
    for col, g in gaps.items():
        long = g[g["hours"] > MAX_GAP_HOURS]
        for _, row in long.iterrows():
            any_long = True
            lines.append(f"- `{col}`: {row['start']} -> {row['end']} ({row['hours']} h)")
    if not any_long:
        lines.append("- none")
    lines += ["", "## Gaps of 1-3 h (interpolated)", ""]
    for col, g in gaps.items():
        short = g[g["hours"] <= MAX_GAP_HOURS]
        lines.append(f"- `{col}`: {len(short)} gaps, {int(short['hours'].sum())} hours")
    CHECK_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(skip_download: bool = False, force: bool = False) -> pd.DataFrame:
    """Build data/processed/weather_observed_hourly.parquet from the MeteoSwiss station files."""
    if not skip_download:
        download(force=force)
    df, n_dup = read_raw()
    df = df[df["timestamp_utc"] >= START]
    # put on a complete hourly grid so missing hours become visible NaN
    grid = pd.date_range(START, df["timestamp_utc"].max(), freq="h", tz="UTC", name="timestamp_utc")
    df = df.set_index("timestamp_utc").reindex(grid)
    raw_missing = {c: int(df[c].isna().sum()) for c in COLUMNS.values()}
    df, gaps = fill_short_gaps(df)
    df = df.reset_index()
    df["timestamp_utc"] = df["timestamp_utc"].astype("datetime64[ns, UTC]")
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_FILE, index=False)
    write_check(df, n_dup, gaps, raw_missing)
    print(f"wrote {OUT_FILE} ({len(df):,} rows, {df['timestamp_utc'].min()} -> {df['timestamp_utc'].max()})")
    return df


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--skip-download", action="store_true", help="rebuild from cached raw files only")
    ap.add_argument("--force", action="store_true", help="re-download even if raw files exist")
    a = ap.parse_args()
    main(skip_download=a.skip_download, force=a.force)
