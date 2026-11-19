"""ECB euro reference rate EUR/CHF (Swiss francs per 1 euro), daily.

Source: ECB Data Portal API
https://data-api.ecb.europa.eu/service/data/EXR/D.CHF.EUR.SP00.A?startPeriod=2018-12-01&format=csvdata
The reference rate is set at the 14:15 CET concertation and published around 16:00 CET on
ECB working days (no rates on weekends and TARGET holidays).
available_from_utc = date 16:00 Europe/Zurich → a forecast on day D at 10:00 uses D-1 (or earlier).
"""
from __future__ import annotations

import argparse

import pandas as pd

from src.data.drivers_utils import local_time_to_utc, polite_get, processed_path, raw_dir, write_check

URL = "https://data-api.ecb.europa.eu/service/data/EXR/D.CHF.EUR.SP00.A"
RAW = "ecb_fx"
FILE = "ecb_eurchf_from_2018-12-01.csv"


def download(force: bool = False) -> None:
    f = raw_dir(RAW) / FILE
    if f.exists() and not force:
        return
    r = polite_get(URL, params={"startPeriod": "2018-12-01", "format": "csvdata"}, min_pause_s=1, host_key="ecb")
    f.write_bytes(r.content)


def main(skip_download: bool = False, force: bool = False) -> pd.DataFrame:
    if not skip_download:
        download(force=force)
    raw = pd.read_csv(raw_dir(RAW) / FILE)
    df = pd.DataFrame({"date": pd.to_datetime(raw["TIME_PERIOD"]).dt.date,
                       "chf_per_eur": pd.to_numeric(raw["OBS_VALUE"], errors="coerce")})
    n_nan = int(df.chf_per_eur.isna().sum())
    df = df.dropna()
    n_dup = int(df.duplicated("date").sum())
    df = df.drop_duplicates("date", keep="last").sort_values("date").reset_index(drop=True)
    df["available_from_utc"] = local_time_to_utc(df["date"], "16:00")
    df.to_parquet(processed_path("eurchf_daily"), index=False)
    gaps = pd.to_datetime(df.date).diff().dt.days
    lines = [
        f"rows: {len(df)}; first {df.date.min()} last {df.date.max()}; NaN dropped {n_nan}; duplicates dropped {n_dup}",
        f"range: {df.chf_per_eur.min():.4f} – {df.chf_per_eur.max():.4f} CHF per EUR",
        f"gaps > 4 days: {int((gaps > 4).sum())} (Easter/Christmas TARGET holidays)",
        "available_from_utc = date 16:00 Europe/Zurich (ECB publishes ~16:00 CET)",
    ]
    write_check("eurchf_daily", lines)
    return df


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-download", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    main(skip_download=a.skip_download, force=a.force)
