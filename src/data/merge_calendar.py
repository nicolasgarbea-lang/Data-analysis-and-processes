"""Merge the daily calendar-type tables into data/processed/calendar_features_daily.parquet.

Inputs (all keyed by `date` = local Europe/Zurich calendar day, 2018-12-01 .. 2026-12-31):
calendar_daily, ev_daily, events_daily, football_daily. One output row per date with all their columns.
`main()` first rebuilds the four inputs by calling their loaders.
"""
from __future__ import annotations

import argparse

import pandas as pd

from src.config import path
from src.data import load_calendar, load_ev, load_events, load_football
from src.data._utils_calendar import daily_dates, rel, save_processed, write_check

PARTS = ["calendar_daily", "ev_daily", "events_daily", "football_daily"]


def merge() -> pd.DataFrame:
    """Join the four processed daily tables on `date` (outer join on the full date range)."""
    out = pd.DataFrame({"date": daily_dates()})
    for name in PARTS:
        part = pd.read_parquet(path("processed") / f"{name}.parquet")
        part["date"] = pd.to_datetime(part["date"])
        if part["date"].duplicated().any():
            raise ValueError(f"{name} has duplicate dates")
        clash = (set(part.columns) & set(out.columns)) - {"date"}
        if clash:
            raise ValueError(f"column clash with {name}: {clash}")
        out = out.merge(part, on="date", how="left", validate="one_to_one")
    return out


def main(skip_download: bool = False, force: bool = False) -> pd.DataFrame:
    """Rebuild the four inputs, then write the merged table."""
    load_calendar.main(skip_download=skip_download, force=force)
    load_ev.main(skip_download=skip_download, force=force)
    load_events.main()
    load_football.main(skip_download=skip_download, force=force)
    df = merge()
    out = save_processed(df, "calendar_features_daily")
    write_check("calendar_features_daily", df, notes=[
        f"merged from {', '.join(PARTS)} on `date` (local Zurich day); {df.shape[1] - 1} value columns",
        "see the check files of the parts for details; text columns are empty on normal days by design",
    ])
    print(f"wrote {rel(out)}: {len(df)} rows, {df.shape[1]} columns")
    return df


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--skip-download", action="store_true", help="use cached raw files only")
    ap.add_argument("--force", action="store_true", help="re-download raw files")
    a = ap.parse_args()
    main(skip_download=a.skip_download, force=a.force)
