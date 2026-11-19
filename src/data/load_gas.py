"""TTF natural-gas front-month futures, daily close, EUR/MWh.

UNOFFICIAL FALLBACK SOURCE: Yahoo Finance chart endpoint for ticker `TTF=F`
(https://query1.finance.yahoo.com/v8/finance/chart/TTF=F?interval=1d&period1=..&period2=..).
The official HSG LSEG/Bloomberg export was not available. Yahoo rejects plain `requests`
calls with HTTP 429, so we use `curl_cffi` (impersonates a Chrome browser, as the
`yfinance` package does). Licence of Yahoo data: personal/educational use only.

Yahoo stamps each daily bar with the exchange session start (~00:00 Amsterdam time ≈ 22:00/23:00
UTC of the previous day for ICE Endex ... or 05:00 UTC). We take the trading day = calendar date of
the timestamp converted to Europe/Amsterdam (ICE Endex TTF trades on Amsterdam time).

Publication: ICE Endex TTF settles ~17:30 CET (settlement window 16:15-16:30 London);
we assume the close of trading day T is known from T 18:00 Europe/Zurich
→ for a forecast on day D 10:00 only closes of days <= D-1 are usable.
"""
from __future__ import annotations

import argparse
import json

import pandas as pd

from src.data.drivers_utils import local_time_to_utc, processed_path, raw_dir, write_check

URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
PERIOD1 = 1543622400   # 2018-12-01 00:00 UTC
PERIOD2 = 1795046400   # 2026-11-19 00:00 UTC
RAW = "yahoo"


def fetch_yahoo(ticker: str, force: bool = False) -> dict:
    """Download (or read cached) Yahoo chart JSON for `ticker`."""
    f = raw_dir(RAW) / f"{ticker.replace('=', '_')}_{PERIOD1}_{PERIOD2}.json"
    if f.exists() and not force:
        return json.loads(f.read_text(encoding="utf-8"))
    from curl_cffi import requests as cr  # imported lazily: only needed for downloading
    r = cr.Session(impersonate="chrome").get(
        URL.format(ticker=ticker),
        params={"interval": "1d", "period1": PERIOD1, "period2": PERIOD2}, timeout=60)
    r.raise_for_status()
    f.write_text(r.text, encoding="utf-8")
    return r.json()


def yahoo_to_daily(data: dict, tz: str = "Europe/Amsterdam") -> pd.DataFrame:
    """Turn Yahoo chart JSON into (date, close) with the trading day in exchange time."""
    res = data["chart"]["result"][0]
    ts = pd.to_datetime(res["timestamp"], unit="s", utc=True)
    close = pd.Series(res["indicators"]["quote"][0]["close"], dtype="float64")
    df = pd.DataFrame({"date": ts.tz_convert(tz).date, "close": close.values})
    return df


def main(skip_download: bool = False, force: bool = False) -> pd.DataFrame:
    if skip_download:
        f = raw_dir(RAW) / f"TTF_F_{PERIOD1}_{PERIOD2}.json"
        data = json.loads(f.read_text(encoding="utf-8"))
    else:
        data = fetch_yahoo("TTF=F", force=force)
    df = yahoo_to_daily(data).rename(columns={"close": "gas_ttf_eur_mwh"})
    n_raw = len(df)
    n_nan = int(df.gas_ttf_eur_mwh.isna().sum())
    df = df.dropna(subset=["gas_ttf_eur_mwh"])
    n_dup = int(df.duplicated("date").sum())
    df = df.drop_duplicates("date", keep="last").sort_values("date").reset_index(drop=True)
    df["available_from_utc"] = local_time_to_utc(df["date"], "18:00")
    df["source"] = "yahoo_TTF=F_unofficial"
    df.to_parquet(processed_path("gas_ttf_daily"), index=False)

    # checks: gaps in business days and large daily jumps
    d = pd.to_datetime(df["date"])
    gap_days = d.diff().dt.days
    big_gaps = df.loc[gap_days > 4, "date"]
    ret = df.gas_ttf_eur_mwh.pct_change().abs()
    jumps = df.loc[ret > 0.3, ["date", "gas_ttf_eur_mwh"]]
    lines = [
        "source: Yahoo Finance `TTF=F` (UNOFFICIAL fallback; HSG LSEG/Bloomberg export not available)",
        f"rows: {len(df)} trading days (raw bars {n_raw}, {n_nan} with null close dropped, {n_dup} duplicate dates dropped)",
        f"first: {df.date.min()}  last: {df.date.max()}",
        f"range: min {df.gas_ttf_eur_mwh.min():.2f}, max {df.gas_ttf_eur_mwh.max():.2f} EUR/MWh "
        f"(max on {df.loc[df.gas_ttf_eur_mwh.idxmax(), 'date']})",
        f"gaps > 4 calendar days (before date shown): {len(big_gaps)} → {', '.join(map(str, big_gaps.head(15)))}",
        f"daily moves > 30%: {len(jumps)} → " + ", ".join(f"{r.date}={r.gas_ttf_eur_mwh:.1f}" for r in jumps.itertuples()),
        "available_from_utc = trading day 18:00 Europe/Zurich (after ICE Endex settlement); use only rows with "
        "available_from_utc <= forecast time",
    ]
    write_check("gas_ttf_daily", lines)
    return df


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-download", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    main(skip_download=a.skip_download, force=a.force)
