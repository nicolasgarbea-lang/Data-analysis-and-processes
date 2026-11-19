"""German day-ahead forecasts of solar, wind and load from Energy-Charts (optional driver).

Source: https://api.energy-charts.info/public_power_forecast?country=de&production_type=<type>
        &forecast_type=day-ahead&start=..&end=..   (Fraunhofer ISE, CC BY 4.0)
Raw: 15-minute MW values (unix seconds = interval START, UTC), yearly chunks cached as JSON in
data/raw/energy_charts_de_forecasts/. We average to hourly.

Output: data/processed/de_forecasts_hourly.parquet with
timestamp_utc, solar_da_forecast_de_mw, wind_onshore_da_forecast_de_mw,
wind_offshore_da_forecast_de_mw, load_da_forecast_de_mw, publication_time_unverified (bool).

PUBLICATION TIME IS NOT VERIFIED. The API does not say when a day-ahead value was issued.
Legal deadlines (EU Transparency Regulation 543/2013): day-ahead load forecast no later than
2 h before day-ahead gate closure (= 10:00 CET for SDAC, Art. 6), wind/solar day-ahead forecast
no later than 18:00 CET on D-1 (Art. 14). The wind/solar deadline is AFTER our 10:00 forecast
time, so these values may not be known at 10:00 on D. Use only with this caveat (or as a
sensitivity check), see docs/assumptions_drivers.md.
"""
from __future__ import annotations

import argparse
import json
from datetime import date

import pandas as pd

from src.data.drivers_utils import polite_get, processed_path, raw_dir, write_check

API = "https://api.energy-charts.info/public_power_forecast"
TYPES = {"solar": "solar_da_forecast_de_mw", "wind_onshore": "wind_onshore_da_forecast_de_mw",
         "wind_offshore": "wind_offshore_da_forecast_de_mw", "load": "load_da_forecast_de_mw"}
FIRST_YEAR = 2019
LAST_DAY = date(2026, 11, 18)
RAW = "energy_charts_de_forecasts"


def download(force: bool = False) -> None:
    d = raw_dir(RAW)
    for ptype in TYPES:
        for y in range(FIRST_YEAR, LAST_DAY.year + 1):
            start, end = date(y, 1, 1), (date(y, 12, 31) if y < LAST_DAY.year else LAST_DAY)
            f = d / f"de_{ptype}_dayahead_{start}_{end}.json"
            if f.exists() and not force:
                continue
            print(f"fetch {ptype} {start} → {end}", flush=True)
            r = polite_get(API, params={"country": "de", "production_type": ptype, "forecast_type": "day-ahead",
                                        "start": str(start), "end": str(end)},
                           min_pause_s=6.0, host_key="energy-charts")
            f.write_text(r.text, encoding="utf-8")


def _read(ptype: str) -> pd.Series:
    parts = []
    for f in sorted(raw_dir(RAW).glob(f"de_{ptype}_dayahead_*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        if not data.get("unix_seconds"):
            continue
        parts.append(pd.Series(data["forecast_values"], dtype="float64",
                               index=pd.to_datetime(data["unix_seconds"], unit="s", utc=True)))
    s = pd.concat(parts)
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s.groupby(s.index.floor("h")).mean()


def main(skip_download: bool = False, force: bool = False) -> pd.DataFrame:
    if not skip_download:
        download(force=force)
    df = pd.DataFrame({col: _read(t) for t, col in TYPES.items()})
    full = pd.date_range(pd.Timestamp("2019-01-01", tz="UTC"), df.index.max(), freq="h")
    df = df.reindex(full)
    df.index = df.index.astype("datetime64[ns, UTC]")
    df.index.name = "timestamp_utc"
    df = df.reset_index()
    df["publication_time_unverified"] = True
    df.to_parquet(processed_path("de_forecasts_hourly"), index=False)

    period = df[df.timestamp_utc < pd.Timestamp("2026-11-01", tz="UTC")]
    lines = [f"rows: {len(df)} hourly; first {df.timestamp_utc.min()} last {df.timestamp_utc.max()}",
             "raw 15-min values averaged to hourly; duplicates between chunks dropped (keep last)"]
    for c in TYPES.values():
        s = period[c]
        first = s.first_valid_index()
        lines.append(f"{c}: missing {s.isna().mean()*100:.2f}% (2019-01-01→2026-11-01), "
                     f"first valid {period.timestamp_utc[first] if first is not None else None}, "
                     f"min {s.min():.0f}, max {s.max():.0f}")
    lines.append("PUBLICATION TIME UNVERIFIED: API gives no issue time. Legal deadlines: load D-1 10:00 CET (Art. 6 "
                 "Reg. 543/2013, borderline for our 10:00 forecast), wind/solar D-1 18:00 CET (Art. 14, after our "
                 "forecast time). Flag column publication_time_unverified=True.")
    write_check("de_forecasts_hourly", lines)
    return df


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-download", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    main(skip_download=a.skip_download, force=a.force)
