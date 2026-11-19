"""Day-ahead prices of the Swiss neighbour zones (DE-LU, FR, AT, IT-North) from Energy-Charts.

Source: https://api.energy-charts.info/price?bzn=<zone>&start=YYYY-MM-DD&end=YYYY-MM-DD
(CC BY 4.0). Timestamps in the JSON are unix seconds (UTC) marking the START of each
interval. Since the SDAC switch to 15-minute products (1 Oct 2025) the series is in
15-minute steps; we average to hourly (mean of the four quarter-hours).

Download: one yearly chunk per zone, cached as raw JSON in data/raw/energy_charts_neighbours/.
Energy-Charts blocks after ~15 quick calls, so we pause >= 6 s between calls and back off on 429.

Output: data/processed/price_neighbours_hourly.parquet with
timestamp_utc, price_de_eur_mwh, price_fr_eur_mwh, price_at_eur_mwh, price_it_north_eur_mwh.

Publication: the SDAC auction for delivery day D+1 closes 12:00 CET on day D and results are
published ~12:45-13:00 CET on day D (see docs/auction_timing.md). So at our forecast time
(10:00 Zurich on D) prices for the whole of delivery day D are known, prices for D+1 are not.
"""
from __future__ import annotations

import argparse
import json
from datetime import date

import pandas as pd

from src.data.drivers_utils import polite_get, processed_path, raw_dir, write_check

API = "https://api.energy-charts.info/price"
ZONES = {"DE-LU": "price_de_eur_mwh", "FR": "price_fr_eur_mwh",
         "AT": "price_at_eur_mwh", "IT-North": "price_it_north_eur_mwh"}
FIRST_YEAR = 2019
LAST_DAY = date(2026, 11, 18)  # latest delivery day available on 2026-11-19 (data fetched once)
RAW = "energy_charts_neighbours"


def _chunks():
    for y in range(FIRST_YEAR, LAST_DAY.year + 1):
        start = date(y, 1, 1)
        end = date(y, 12, 31) if y < LAST_DAY.year else LAST_DAY
        yield start, end


def download(force: bool = False) -> None:
    """Download yearly JSON chunks for each zone (skips files that exist unless force)."""
    d = raw_dir(RAW)
    for zone in ZONES:
        for start, end in _chunks():
            f = d / f"{zone}_{start}_{end}.json"
            if f.exists() and not force:
                continue
            print(f"fetch {zone} {start} → {end}")
            r = polite_get(API, params={"bzn": zone, "start": str(start), "end": str(end)},
                           min_pause_s=6.0, host_key="energy-charts")
            data = r.json()
            if not data.get("unix_seconds"):
                raise RuntimeError(f"empty response for {zone} {start}: {str(data)[:200]}")
            f.write_text(json.dumps(data), encoding="utf-8")


def _read_zone(zone: str) -> pd.Series:
    parts = []
    for f in sorted(raw_dir(RAW).glob(f"{zone}_*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        s = pd.Series(data["price"], index=pd.to_datetime(data["unix_seconds"], unit="s", utc=True),
                      dtype="float64")
        parts.append(s)
    s = pd.concat(parts)
    s = s[~s.index.duplicated(keep="last")].sort_index()
    # average 15-min (or hourly) values to the hour that contains them
    return s.groupby(s.index.floor("h")).mean()


def build() -> pd.DataFrame:
    cols = {col: _read_zone(z) for z, col in ZONES.items()}
    df = pd.DataFrame(cols)
    full = pd.date_range(pd.Timestamp("2019-01-01", tz="UTC"), df.index.max(), freq="h").astype("datetime64[ns, UTC]")
    df = df.reindex(full)
    df.index.name = "timestamp_utc"
    return df.reset_index()


def main(skip_download: bool = False, force: bool = False) -> pd.DataFrame:
    if not skip_download:
        download(force=force)
    df = build()
    out = processed_path("price_neighbours_hourly")
    df.to_parquet(out, index=False)
    period = df[(df.timestamp_utc >= "2019-01-01") & (df.timestamp_utc < "2026-11-02")]
    lines = [f"file: `{out.relative_to(out.parents[2])}`", f"rows: {len(df)} (hourly, UTC, interval start)",
             f"first: {df.timestamp_utc.min()}  last: {df.timestamp_utc.max()}",
             "duplicates removed: overlapping chunk timestamps dropped (keep last); 15-min averaged to hourly",
             "raw resolution: hourly until 2025-09-30 22:00 UTC, 15-min from 2025-09-30 22:00 UTC (SDAC 15-min MTU, "
             "delivery day 1 Oct 2025) → mean of 4 quarter-hours",
             "publication: delivery day D values known from D-1 ~13:00 Europe/Zurich (SDAC results); "
             "at forecast time D 10:00 only delivery hours up to end of local day D may be used"]
    for c in ZONES.values():
        s = period[c]
        lines.append(f"{c}: missing {s.isna().mean()*100:.3f}% in 2019-01-01→2026-11-01 "
                     f"({s.isna().sum()} h), min {s.min():.1f}, max {s.max():.1f}, mean {s.mean():.1f}")
        gaps = period.loc[s.isna(), "timestamp_utc"]
        if len(gaps):
            lines.append(f"  missing hours of {c} (first 10): {', '.join(str(t) for t in gaps.head(10))}")
    write_check("price_neighbours_hourly", lines)
    return df


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-download", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    main(skip_download=a.skip_download, force=a.force)
