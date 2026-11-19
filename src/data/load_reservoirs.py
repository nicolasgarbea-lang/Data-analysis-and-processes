"""Weekly fill level of Swiss storage reservoirs (BFE, open data "ogd17").

Source: https://www.bfe-ogd.ch/ogd17/ogd17_fuellungsgrad_speicherseen.csv
Dataset title on opendata.swiss: "Füllungsgrad der Speicherseen, Sonntag 24h, Wochenbericht Speicherinhalt".
The value is the stored energy (GWh) on SUNDAY at 24:00. The `Datum` column in the file is the
following MONDAY (= Sunday 24:00 = Monday 00:00), e.g. 2026-11-16.

Publication: weekly. The HTTP Last-Modified header of the file on 2026-11-19 was
Tue 2026-11-17 14:22 GMT, i.e. the value for Sunday 15 Nov 24h appeared on Tuesday afternoon.
We do not have a documented release calendar, so we assume (conservatively) the value is
known from the end of THURSDAY after the Sunday measurement
(available_from_utc = Datum + 3 days, 23:59 local = Thursday end of day, the publication day stated on energiedashboard.admin.ch). With forecasts at 10:00 this means the
week's value is first used on Friday.

Extra columns:
- reservoir_median_pct_same_week: median fill % of the same ISO week in all years STRICTLY
  before the row's year (history from 2000) → no look-ahead.
- reservoir_vs_median_pct: reservoir_fill_pct - that median (percentage points).
"""
from __future__ import annotations

import argparse

import pandas as pd

from src.data.drivers_utils import local_time_to_utc, polite_get, processed_path, raw_dir, write_check

URL = "https://www.bfe-ogd.ch/ogd17/ogd17_fuellungsgrad_speicherseen.csv"
RAW = "bfe_reservoirs"
FILE = "ogd17_fuellungsgrad_speicherseen.csv"
REGIONS = {"Wallis": "wallis", "Graubuenden": "graubuenden", "Tessin": "tessin", "UebrigCH": "rest_ch"}


def download(force: bool = False) -> None:
    f = raw_dir(RAW) / FILE
    if f.exists() and not force:
        return
    f.write_bytes(polite_get(URL, min_pause_s=1, host_key="bfe").content)


def median_same_week_before(df: pd.DataFrame) -> pd.Series:
    """For each row: median fill % of rows with the same ISO week and an earlier year."""
    out = pd.Series(index=df.index, dtype="float64")
    for (yr, wk), idx in df.groupby(["year", "week"]).groups.items():
        hist = df.loc[(df.week == wk) & (df.year < yr), "reservoir_fill_pct"]
        if hist.empty and wk == 53:  # rare ISO week 53: compare with week 52
            hist = df.loc[(df.week == 52) & (df.year < yr), "reservoir_fill_pct"]
        out.loc[idx] = hist.median() if len(hist) else float("nan")
    return out


def main(skip_download: bool = False, force: bool = False) -> pd.DataFrame:
    if not skip_download:
        download(force=force)
    raw = pd.read_csv(raw_dir(RAW) / FILE)
    df = pd.DataFrame({"measure_date": pd.to_datetime(raw["Datum"]).dt.date})
    df["reservoir_gwh_ch"] = raw["TotalCH_speicherinhalt_gwh"].astype(float)
    df["reservoir_max_gwh_ch"] = raw["TotalCH_max_speicherinhalt_gwh"].astype(float)
    df["reservoir_fill_pct"] = 100 * df.reservoir_gwh_ch / df.reservoir_max_gwh_ch
    for src, name in REGIONS.items():
        df[f"reservoir_gwh_{name}"] = raw[f"{src}_speicherinhalt_gwh"].astype(float)
        df[f"reservoir_max_gwh_{name}"] = raw[f"{src}_max_speicherinhalt_gwh"].astype(float)
        df[f"reservoir_fill_pct_{name}"] = 100 * df[f"reservoir_gwh_{name}"] / df[f"reservoir_max_gwh_{name}"]
    n_dup = int(df.duplicated("measure_date").sum())
    df = df.drop_duplicates("measure_date", keep="last").sort_values("measure_date").reset_index(drop=True)

    iso = pd.to_datetime(df.measure_date).dt.isocalendar()
    df["year"], df["week"] = iso["year"].astype(int).values, iso["week"].astype(int).values
    df["reservoir_median_pct_same_week"] = median_same_week_before(df)
    df["reservoir_vs_median_pct"] = df.reservoir_fill_pct - df.reservoir_median_pct_same_week
    df = df.rename(columns={"week": "iso_week"}).drop(columns="year")
    df["available_from_utc"] = local_time_to_utc(df["measure_date"], "23:59", days_offset=3)
    df.to_parquet(processed_path("reservoir_weekly"), index=False)

    wd = pd.to_datetime(df.measure_date).dt.day_of_week.value_counts().to_dict()
    gaps = pd.to_datetime(df.measure_date).diff().dt.days
    lines = [
        f"rows: {len(df)} weeks; first {df.measure_date.min()} last {df.measure_date.max()}; duplicates dropped {n_dup}",
        f"weekday of measure_date (0=Mon): {wd}  (date = Monday 00:00 = Sunday 24h value)",
        f"gaps != 7 days: {int((gaps.dropna() != 7).sum())}",
        f"fill % range: {df.reservoir_fill_pct.min():.1f} – {df.reservoir_fill_pct.max():.1f}; "
        f"max capacity changes over time: {sorted(df.reservoir_max_gwh_ch.unique().tolist())}",
        f"missing: {df.isna().sum()[df.isna().sum() > 0].to_dict()} (median is NaN for year 2000: no earlier history)",
        "available_from_utc = measure_date (Monday) + 3 days at 23:59 Europe/Zurich = Thursday end of day (the federal energy dashboard states Thursday publication; file was "
        "last modified Tue 2026-11-17 14:22 GMT for the 2026-11-16 value)",
    ]
    write_check("reservoir_weekly", lines)
    return df


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-download", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    main(skip_download=a.skip_download, force=a.force)
