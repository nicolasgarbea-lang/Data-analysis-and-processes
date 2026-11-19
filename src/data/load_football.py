"""Daily home-game flags for the two Zurich Super League clubs -> data/processed/football_daily.parquet.

Source: football-data.co.uk, Swiss Super League results file SWZ.csv (columns Date, Time, Home, Away, ...).
We keep home games of FC Zürich (`Zurich`) and Grasshoppers (`Grasshoppers`); both play at Stadion Letzigrund.

Time zone of the `Time` column: UK time (Europe/London). Evidence: Saturday games show 17:00/19:30 and Sunday
games 13:15/15:30, while Super League kick-offs are 18:00/20:30 and 14:15/16:30 Swiss time. UK and Swiss DST
switch on the same days, so Swiss time = UK time + 1 hour all year; we convert with the tz database anyway.

Coverage: league games only (no Swiss Cup, no European games, no friendlies). Fixtures are published weeks ahead,
so a home game on D+1 is known on day D.
"""
from __future__ import annotations

import argparse

import pandas as pd

from src.data._utils_calendar import TZ, daily_dates, download, raw_dir, rel, save_processed, write_check

SWZ_URL = "https://www.football-data.co.uk/new/SWZ.csv"
ZURICH_TEAMS = ["Zurich", "Grasshoppers"]


def read_home_games(csv_path) -> pd.DataFrame:
    """Home games of the Zurich clubs with kick-off converted to Swiss local time."""
    g = pd.read_csv(csv_path, encoding="utf-8-sig", usecols=["Season", "Date", "Time", "Home", "Away"])
    g = g[g["Home"].isin(ZURICH_TEAMS)].copy()
    g["Time"] = g["Time"].fillna("")
    has_time = g["Time"].str.match(r"^\d{1,2}:\d{2}$")
    uk = pd.to_datetime(g["Date"] + " " + g["Time"].where(has_time, "00:00"), format="%d/%m/%Y %H:%M")
    local = uk.dt.tz_localize("Europe/London").dt.tz_convert(TZ)
    g["date"] = local.dt.tz_localize(None).dt.normalize().where(has_time, uk.dt.normalize())
    g["kickoff_hour_local"] = (local.dt.hour + local.dt.minute / 60).where(has_time)
    return g


def build(games: pd.DataFrame) -> pd.DataFrame:
    """One row per day: home_game, n_home_games, earliest local kick-off hour, home team(s)."""
    d = games.groupby("date").agg(
        n_home_games=("Home", "size"),
        kickoff_hour_local=("kickoff_hour_local", "min"),
        home_team=("Home", lambda s: " | ".join(sorted(set(s)))),
    )
    out = d.reindex(daily_dates())
    out["n_home_games"] = out["n_home_games"].fillna(0).astype(int)
    out["home_game"] = (out["n_home_games"] > 0).astype(int)
    out = out.reset_index().rename(columns={"index": "date"})
    return out[["date", "home_game", "n_home_games", "kickoff_hour_local", "home_team"]]


def main(skip_download: bool = False, force: bool = False) -> pd.DataFrame:
    """Download (if needed) and build data/processed/football_daily.parquet."""
    csv_path = raw_dir("football") / "SWZ.csv"
    if not skip_download:
        download(SWZ_URL, csv_path, force=force)
    games = read_home_games(csv_path)
    n_dup = int(games.duplicated(["date", "Home"]).sum())
    games = games.drop_duplicates(["date", "Home"])
    df = build(games)
    out = save_processed(df, "football_daily")
    in_range = games[(games["date"] >= daily_dates().min()) & (games["date"] <= daily_dates().max())]
    last_game = pd.to_datetime(games["date"]).max().date()
    notes = [
        f"file covers seasons {games['Season'].min()} .. {games['Season'].max()}; last listed Zurich home game: "
        f"{last_game} (games after the download date are missing; the table is only complete up to then)",
        f"home games in range: {len(in_range)} (Zurich {int((in_range['Home'] == 'Zurich').sum())}, "
        f"Grasshoppers {int((in_range['Home'] == 'Grasshoppers').sum())}); missing kick-off times: "
        f"{int(in_range['kickoff_hour_local'].isna().sum())}",
        f"days with 2 home games: {int((df['n_home_games'] > 1).sum())}",
        "Time column read as UK time and converted to Europe/Zurich (+1 h).",
        "Only Super League games: Swiss Cup and European home games are NOT included.",
        "kickoff_hour_local / home_team are empty on days without a home game (by design).",
    ]
    write_check("football_daily", df, duplicates_removed=n_dup, notes=notes)
    print(f"wrote {rel(out)}: {len(df)} rows")
    return df


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--skip-download", action="store_true", help="use cached raw files only")
    ap.add_argument("--force", action="store_true", help="re-download raw files")
    a = ap.parse_args()
    main(skip_download=a.skip_download, force=a.force)
