"""Daily big-event indicators for Zurich -> data/processed/events_daily.parquet.

Input: the hand-made table data/manual/events_zurich.csv (columns date,event,type,size,source_url; one row per
event day; size 1 = small/medium, 2 = large (tens of thousands), 3 = huge (several hundred thousand+)).
Only dates confirmed with a source URL are in the file; unconfirmed events are listed in docs/events_unverified.md.

Output: one row per local Europe/Zurich calendar day, 2018-12-01 .. 2026-12-31:
`event_size` (max size that day, 0 = none), `n_events`, `event_name` (names joined with " | "), `event_types`.
Events are planned and announced in advance, so they count as known on the forecast day.
"""
from __future__ import annotations

import argparse

import pandas as pd

from src.config import path
from src.data._utils_calendar import daily_dates, rel, save_processed, write_check

EVENTS_CSV = "events_zurich.csv"


def read_events(csv_path=None) -> pd.DataFrame:
    """Read and validate the hand-made events table."""
    csv_path = csv_path or path("manual") / EVENTS_CSV
    ev = pd.read_csv(csv_path, parse_dates=["date"])
    required = ["date", "event", "type", "size", "source_url"]
    missing = [c for c in required if c not in ev.columns]
    if missing:
        raise ValueError(f"events file misses columns {missing}")
    if ev["source_url"].isna().any() or not ev["source_url"].str.startswith("http").all():
        raise ValueError("every event row needs a source_url")
    if not ev["size"].between(1, 3).all():
        raise ValueError("size must be 1, 2 or 3")
    return ev


def build(ev: pd.DataFrame) -> pd.DataFrame:
    """Aggregate event rows to one row per day."""
    g = ev.groupby("date")
    daily = pd.DataFrame({
        "event_size": g["size"].max(),
        "n_events": g["event"].nunique(),
        "event_name": g["event"].apply(lambda s: " | ".join(sorted(set(s)))),
        "event_types": g["type"].apply(lambda s: " | ".join(sorted(set(s)))),
    })
    dates = daily_dates()
    out = daily.reindex(dates)
    out["event_size"] = out["event_size"].fillna(0).astype(int)
    out["n_events"] = out["n_events"].fillna(0).astype(int)
    return out.reset_index().rename(columns={"index": "date"})


def main(skip_download: bool = False, force: bool = False) -> pd.DataFrame:
    """Build data/processed/events_daily.parquet (no download: the input is a committed manual file)."""
    ev = read_events()
    n_dup = int(ev.duplicated(["date", "event"]).sum())
    ev = ev.drop_duplicates(["date", "event"])
    df = build(ev)
    out = save_processed(df, "events_daily")
    outside = ev[(ev["date"] < daily_dates().min()) | (ev["date"] > daily_dates().max())]
    notes = [
        f"event rows in manual file: {len(ev)} on {ev['date'].nunique()} days; events: {ev['event'].nunique()}",
        f"days with event_size 3 / 2 / 1: {(df['event_size'] == 3).sum()} / {(df['event_size'] == 2).sum()} / "
        f"{(df['event_size'] == 1).sum()}",
        f"rows outside the daily range (ignored): {len(outside)}",
        "event_name / event_types are empty on days without an event (by design).",
        "Cancelled years (COVID 2020/2021) are simply absent: event_size = 0 on those days.",
    ]
    write_check("events_daily", df, duplicates_removed=n_dup, notes=notes)
    print(f"wrote {rel(out)}: {len(df)} rows")
    return df


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--skip-download", action="store_true", help="no effect (manual input)")
    ap.add_argument("--force", action="store_true", help="no effect (manual input)")
    a = ap.parse_args()
    main(skip_download=a.skip_download, force=a.force)
