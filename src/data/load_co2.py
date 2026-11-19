"""EU carbon allowance (EUA) price, daily, EUR/tCO2 – from EEX primary-market auctions.

Source (official, free): EEX "EUA Emission Spot Primary Market Auction Report"
page https://www.eex.com/en/market-data/market-data-hub/environmentals/eex-eua-primary-auction-spot-download
 - archive 2012-2025: .../Archive_Reports/emission-spot-primary-market-auction-report-2012-2025-data.zip
 - current year 2026: https://public.eex-group.com/eex/eua-auction-report/emission-spot-primary-market-auction-report-2026-data.xlsx

Each row in the files is one auction (EU common auction, DE, PL, ...). The bidding window
closes at 11:00 CET and EEX publishes the clearing price shortly after (EU Auctioning
Regulation: no later than 15 minutes after closing). We take the volume-weighted mean of
all successful auctions on a day as that day's EUA price.

Auctions are not held every day (usually Mon-Thu plus some Fridays, paused in August
weeks and over Christmas/New Year), so the daily table has gaps: the feature builder
should take the latest auction with available_from_utc <= forecast time (as-of join).

available_from_utc = auction day 12:00 Europe/Zurich (conservative; results ~11:15).
For a forecast at 10:00 on D the latest usable auction is therefore from D-1 or earlier.
"""
from __future__ import annotations

import argparse
import io
import zipfile

import pandas as pd

from src.data.drivers_utils import BROWSER_UA, local_time_to_utc, polite_get, processed_path, raw_dir, write_check

ARCHIVE_URL = ("https://www.eex.com/fileadmin/EEX/Downloads/Markets/Environmentals/"
               "EUA_Emission_Spot_Primary_Market_Auction_Report/Archive_Reports/"
               "emission-spot-primary-market-auction-report-2012-2025-data.zip")
CURRENT_URL = ("https://public.eex-group.com/eex/eua-auction-report/"
               "emission-spot-primary-market-auction-report-2026-data.xlsx")
RAW = "eex_eua"
ARCHIVE_FILE = "archive_2012-2025.zip"
CURRENT_FILE = "emission-spot-primary-market-auction-report-2026-data.xlsx"


def download(force: bool = False) -> None:
    d = raw_dir(RAW)
    for url, name in [(ARCHIVE_URL, ARCHIVE_FILE), (CURRENT_URL, CURRENT_FILE)]:
        f = d / name
        if f.exists() and not force:
            continue
        r = polite_get(url, min_pause_s=2, headers={"User-Agent": BROWSER_UA}, host_key="eex")
        f.write_bytes(r.content)


def read_report(content: bytes) -> pd.DataFrame:
    """Read one yearly EEX auction report (xls or xlsx). The header row contains 'Date'."""
    raw = pd.read_excel(io.BytesIO(content), header=None)
    hdr_row = raw.index[raw.apply(lambda r: (r.astype(str) == "Date").any(), axis=1)][0]
    df = raw.iloc[hdr_row + 1:].copy()
    df.columns = [str(c).strip() for c in raw.iloc[hdr_row]]
    def col(prefix: str) -> pd.Series:
        """First column whose name starts with `prefix` (names differ slightly between years)."""
        name = next(c for c in df.columns if c.lower().startswith(prefix.lower()))
        return df[name]

    out = pd.DataFrame({
        "date": pd.to_datetime(df["Date"], errors="coerce").dt.date,
        "auction_name": col("Auction Name"),
        "status": df["Status"] if "Status" in df.columns else "successful",
        "price": pd.to_numeric(col("Auction Price"), errors="coerce"),
        "volume": pd.to_numeric(col("Auction Volume"), errors="coerce"),
    })
    return out.dropna(subset=["date"])


def read_all() -> pd.DataFrame:
    d = raw_dir(RAW)
    parts = []
    with zipfile.ZipFile(d / ARCHIVE_FILE) as z:
        for n in sorted(z.namelist()):
            if n.endswith((".xls", ".xlsx")) and any(f"-{y}-data" in n for y in range(2018, 2026)):
                parts.append(read_report(z.read(n)))
    parts.append(read_report((d / CURRENT_FILE).read_bytes()))
    return pd.concat(parts, ignore_index=True)


def main(skip_download: bool = False, force: bool = False) -> pd.DataFrame:
    if not skip_download:
        download(force=force)
    a = read_all()
    n_all = len(a)
    ok = a[a.status.astype(str).str.lower().str.startswith("success") & a.price.notna() & (a.volume > 0)]
    n_dup = int(ok.duplicated(["date", "auction_name"]).sum())
    ok = ok.drop_duplicates(["date", "auction_name"])
    ok = ok.assign(pv=ok.price * ok.volume)
    g = ok.groupby("date").agg(pv=("pv", "sum"), vol=("volume", "sum"), n_auctions=("price", "size"))
    df = pd.DataFrame({"date": g.index, "co2_eua_eur_t": (g.pv / g.vol).round(3).values,
                       "n_auctions": g.n_auctions.values})
    df = df[df.date >= pd.Timestamp("2018-12-01").date()].sort_values("date").reset_index(drop=True)
    df["available_from_utc"] = local_time_to_utc(df["date"], "12:00")
    df["source"] = "EEX_primary_auction"
    df.to_parquet(processed_path("co2_eua_daily"), index=False)

    d = pd.to_datetime(df.date)
    gaps = d.diff().dt.days
    long_gaps = df.loc[gaps > 7, "date"]
    period = df[(d >= "2019-01-01") & (d <= "2026-10-31")]
    lines = [
        "source: EEX primary-market auction reports (archive zip 2012-2025 + 2026 xlsx), official",
        f"auction rows read: {n_all}; successful used: {len(ok)}; duplicate auction rows dropped: {n_dup}",
        f"rows (auction days): {len(df)}; in 2019-01-01→2026-10-31: {len(period)}",
        f"first: {df.date.min()}  last: {df.date.max()}",
        f"range: min {df.co2_eua_eur_t.min():.2f}, max {df.co2_eua_eur_t.max():.2f} EUR/t",
        f"gaps > 7 days without auction (date after gap, gap days): " +
        ", ".join(f"{dt}({int(x)})" for dt, x in zip(long_gaps, gaps[gaps > 7])),
        "daily value = volume-weighted mean of all successful auctions that day",
        "no auctions on most Fridays/weekends, in parts of August and around New Year → as-of join with last value",
        "available_from_utc = auction day 12:00 Europe/Zurich (results published ~11:15)",
    ]
    write_check("co2_eua_daily", lines)
    return df


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-download", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    main(skip_download=a.skip_download, force=a.force)
