"""ERA5 reanalysis for Zurich from the Open-Meteo Historical Weather (archive) API.

Used as a gap-filler / cross-check for the MeteoSwiss station data. Reanalysis is NOT a forecast: it uses
observations of the hour itself, so it must never be used as a model input for D+1.

Endpoint: https://archive-api.open-meteo.com/v1/archive  (models=era5, point 47.378 N, 8.565 E)
Time convention: same as the forecast loader - Open-Meteo stamp -1 h, so `timestamp_utc` = START of the hour
(instantaneous variables are the value at the end of that hour; radiation/precip/sunshine are the hour's mean/sum).
ERA5 is published with ~5 days delay.

Output: data/processed/weather_archive_hourly.parquet with columns `<name>_era5`.
Run:    .venv/bin/python -m src.data.load_openmeteo_archive [--skip-download] [--force]
"""
from __future__ import annotations

import argparse
import json
import time

import pandas as pd

from src.config import ROOT, path
from src.data.load_openmeteo_forecast import LAT, LON, VARIABLES, get_json

URL = "https://archive-api.open-meteo.com/v1/archive"
MODEL = "era5"
START = pd.Timestamp("2018-12-01", tz="UTC")
END_DATE = "2026-11-03"

RAW_DIR = path("raw") / "openmeteo_archive"
OUT_FILE = path("processed") / "weather_archive_hourly.parquet"
CHECK_FILE = ROOT / "reports" / "data_checks" / "weather_archive_hourly.md"


def download(force: bool = False) -> None:
    """One cached JSON per year in data/raw/openmeteo_archive/."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for year in range(2018, 2027):
        target = RAW_DIR / f"{MODEL}_{year}.json"
        if target.exists() and not force:
            continue
        start = "2018-11-30" if year == 2018 else f"{year}-01-01"
        end = END_DATE if year == 2026 else f"{year}-12-31"
        params = dict(latitude=LAT, longitude=LON, hourly=",".join(VARIABLES), models=MODEL, timezone="GMT",
                      start_date=start, end_date=end)
        print(f"fetching {MODEL} {year} ...")
        target.write_text(json.dumps(get_json(URL, params)), encoding="utf-8")
        time.sleep(5)


def main(skip_download: bool = False, force: bool = False) -> pd.DataFrame:
    """Build data/processed/weather_archive_hourly.parquet."""
    if not skip_download:
        download(force=force)
    frames = []
    for year in range(2018, 2027):
        h = json.loads((RAW_DIR / f"{MODEL}_{year}.json").read_text(encoding="utf-8"))["hourly"]
        df = pd.DataFrame(h)
        df["timestamp_utc"] = pd.to_datetime(df.pop("time")).dt.tz_localize("UTC") - pd.Timedelta(hours=1)
        for v, (base, factor) in VARIABLES.items():
            df[f"{base}_era5"] = df.pop(v).astype(float) * factor
        frames.append(df)
    df = pd.concat(frames)
    n_before = len(df)
    df = df.drop_duplicates("timestamp_utc", keep="last")
    n_dup = n_before - len(df)
    end = pd.Timestamp(END_DATE, tz="UTC") + pd.Timedelta(hours=22)
    grid = pd.date_range(START, end, freq="h", tz="UTC", name="timestamp_utc")
    df = df.set_index("timestamp_utc").reindex(grid).reset_index()
    df["timestamp_utc"] = df["timestamp_utc"].astype("datetime64[ns, UTC]")
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_FILE, index=False)

    CHECK_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Data check: weather_archive_hourly (Open-Meteo archive, ERA5 reanalysis)",
        "",
        f"- Rows: {len(df):,}; timestamp_utc {df['timestamp_utc'].min()} -> {df['timestamp_utc'].max()}",
        f"- Duplicates removed: {n_dup}",
        "- Time shift: Open-Meteo stamp -1 h -> START of hour. Units: sunshine min, wind m/s.",
        "- Reanalysis = not available at forecast time. Cross-check / gap filler only.",
        "",
        "| column | missing | missing % |",
        "|---|---|---|",
    ]
    for c in df.columns[1:]:
        lines.append(f"| {c} | {int(df[c].isna().sum())} | {df[c].isna().mean():.3%} |")
    CHECK_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT_FILE} ({len(df):,} rows)")
    return df


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--skip-download", action="store_true", help="rebuild from cached raw files only")
    ap.add_argument("--force", action="store_true", help="re-download even if raw files exist")
    a = ap.parse_args()
    main(skip_download=a.skip_download, force=a.force)
