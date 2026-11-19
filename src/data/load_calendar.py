"""Daily calendar table for the city of Zurich -> data/processed/calendar_daily.parquet.

One row per local Europe/Zurich calendar day, 2018-12-01 .. 2026-12-31.

Sources
- Public holidays: Python package `holidays`, `holidays.Switzerland(subdiv="ZH")`, plus Berchtoldstag (2 Jan),
  which the package does not list for ZH but which is a day off in the city (it is in the city school calendar).
- City half-holidays (afternoon off): Sechseläuten Monday and Knabenschiessen Monday. Dates are taken from the
  Stadt Zürich school calendar (official, lists "schulfrei: Sechseläuten" / "Knabenschiessen") and hand-checked.
- School holidays: Stadt Zürich `schulferien.csv` (end date is exclusive).
- COVID stringency: Oxford COVID-19 Government Response Tracker (OxCGRT), national file on GitHub, Switzerland.

Everything here is known in advance (calendar) or is a published historical index (COVID), so no publication lag
applies except where noted in docs/data_dictionary_calendar.md.
"""
from __future__ import annotations

import argparse

import holidays
import numpy as np
import pandas as pd

from src.data._utils_calendar import (TZ, daily_dates, download, raw_dir, rel, save_processed,
                                      write_check)

SCHOOL_URL = "https://data.stadt-zuerich.ch/dataset/ssd_schulferien/download/schulferien.csv"
OXCGRT_URL = ("https://raw.githubusercontent.com/OxCGRT/covid-policy-dataset/main/data/"
              "OxCGRT_compact_national_v1.csv")

# Sechseläuten Monday (afternoon off in the city). Source: Stadt Zürich school calendar (SCHOOL_URL), which lists
# the school-free Sechseläuten day for each year, plus sechselaeuten.ch for the cancelled years.
# 2020: cancelled (COVID; Monday would have been 2020-04-20), not in the school calendar -> no half-holiday.
# 2021: public festival cancelled (decided 3 Dec 2020), only the Böögg was burned in Uri without spectators;
#       the school calendar still lists 2021-04-19 as school-free -> we keep the half-holiday flag.
#       https://www.sechselaeuten.ch/assets/downloads/2021/Medienmitteilungen/MM_ZZZ_Boegg%20SL_2021.pdf
SECHSELAEUTEN = {
    2019: "2019-04-08", 2021: "2021-04-19", 2022: "2022-04-25", 2023: "2023-04-17",
    2024: "2024-04-15", 2025: "2025-04-28", 2026: "2026-04-20",
}
# Knabenschiessen Monday (afternoon off in the city). Source: Stadt Zürich school calendar (SCHOOL_URL).
# 2020 cancelled and 2021 only a small shoot-off without fair (COVID), but the school calendar lists both
# Mondays as school-free, so the half-holiday flag is kept. The events table leaves those two years out.
KNABENSCHIESSEN = {
    2019: "2019-09-09", 2020: "2020-09-14", 2021: "2021-09-13", 2022: "2022-09-12",
    2023: "2023-09-11", 2024: "2024-09-09", 2025: "2025-09-15", 2026: "2026-09-14",
}

# Keyword -> school holiday type (checked in this order; first hit wins).
SCHOOL_TYPES = [
    ("weihnacht", "christmas"),
    ("sportferien", "sport"),
    ("frühling", "spring"),
    ("sommer", "summer"),
    ("herbst", "autumn"),
]


def public_holidays(years: range) -> dict[pd.Timestamp, str]:
    """Full public holidays in the city of Zurich: `holidays` ZH + Berchtoldstag (2 Jan)."""
    out = {pd.Timestamp(d): name for d, name in holidays.Switzerland(subdiv="ZH", years=list(years)).items()}
    for y in years:
        out.setdefault(pd.Timestamp(f"{y}-01-02"), "Berchtoldstag")
    return out


def load_school_holidays(csv_path) -> pd.DataFrame:
    """Read the city school calendar and keep only real school-free periods.

    The file mixes public holidays (e.g. "Weihnachten"), school-free days ("Schulen Stadt Zürich schulfrei: ...")
    and holiday periods ("Schulen Stadt Zürich: Herbstferien"). We keep rows that start with "Schulen Stadt Zürich"
    and contain "ferien" or "schulfrei", but not the half-day "Schulschluss" rows or the first school day.
    End dates are exclusive (e.g. Nationalfeiertag 2018-08-01 -> 2018-08-02 is one day).
    """
    s = pd.read_csv(csv_path)
    s["summary"] = s["summary"].astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
    s["start"] = pd.to_datetime(s["start_date"].str[:10])
    s["end"] = pd.to_datetime(s["end_date"].str[:10])
    low = s["summary"].str.lower()
    keep = (low.str.startswith("schulen stadt zürich")
            & (low.str.contains("ferien") | low.str.contains("schulfrei"))
            & ~low.str.contains("schulschluss") & ~low.str.contains("schultag")
            & ~low.str.contains("schuljahres"))
    s = s[keep].copy()
    # a few rows have end == start; treat them as one day
    s.loc[s["end"] <= s["start"], "end"] = s["start"] + pd.Timedelta(days=1)

    def kind(text: str) -> str:
        t = text.lower()
        for key, label in SCHOOL_TYPES:
            if key in t:
                return label
        return "school_free_day"

    s["type"] = s["summary"].map(kind)
    return s[["start", "end", "type", "summary"]].reset_index(drop=True)


def hours_in_local_day(dates: pd.DatetimeIndex) -> np.ndarray:
    """Length of each local day in hours (23 on the spring DST change, 25 in autumn, else 24)."""
    start = dates.tz_localize(TZ)
    end = (dates + pd.Timedelta(days=1)).tz_localize(TZ)
    return ((end.tz_convert("UTC") - start.tz_convert("UTC")) / pd.Timedelta(hours=1)).astype(int).to_numpy()


def days_to_from(flag: pd.Series, extra_dates: list[pd.Timestamp]) -> tuple[pd.Series, pd.Series]:
    """Days until the next and since the last holiday (0 on a holiday). Uses holidays outside the table edges too."""
    hol = np.array(sorted(set(flag.index[flag.astype(bool)]) | set(extra_dates)), dtype="datetime64[ns]")
    d = flag.index.values
    nxt = np.searchsorted(hol, d, side="left")
    prv = np.searchsorted(hol, d, side="right") - 1
    to_next = (hol[np.clip(nxt, 0, len(hol) - 1)] - d) / np.timedelta64(1, "D")
    since = (d - hol[np.clip(prv, 0, len(hol) - 1)]) / np.timedelta64(1, "D")
    to_next = np.where(nxt < len(hol), to_next, np.nan)
    since = np.where(prv >= 0, since, np.nan)
    return pd.Series(to_next, index=flag.index), pd.Series(since, index=flag.index)


def load_covid(csv_path) -> pd.Series:
    """OxCGRT stringency index (0-100) for Switzerland, national level, 2020-01-01 .. 2022-12-31."""
    cols = ["CountryCode", "Jurisdiction", "Date", "StringencyIndex_Average"]
    d = pd.read_csv(csv_path, usecols=cols, low_memory=False)
    d = d[(d["CountryCode"] == "CHE") & (d["Jurisdiction"] == "NAT_TOTAL")]
    d["date"] = pd.to_datetime(d["Date"].astype(str), format="%Y%m%d")
    return d.drop_duplicates("date").set_index("date")["StringencyIndex_Average"]


def build(school_csv, oxcgrt_csv) -> pd.DataFrame:
    """Build the daily calendar table from the cached raw files."""
    dates = daily_dates()
    df = pd.DataFrame(index=dates)
    df["weekday"] = dates.day_of_week
    df["month"] = dates.month
    df["day_of_year"] = dates.day_of_year
    df["is_weekend"] = (dates.day_of_week >= 5).astype(int)

    years = range(dates.year.min() - 1, dates.year.max() + 2)
    ph = public_holidays(years)
    df["holiday_name"] = [ph.get(d) for d in dates]
    df["is_holiday"] = df["holiday_name"].notna().astype(int)

    half = {pd.Timestamp(v): "Sechseläuten (afternoon)" for v in SECHSELAEUTEN.values()}
    half.update({pd.Timestamp(v): "Knabenschiessen (afternoon)" for v in KNABENSCHIESSEN.values()})
    df["half_holiday_name"] = [half.get(d) for d in dates]
    df["is_half_holiday"] = df["half_holiday_name"].notna().astype(int)

    # bridge day: a working day with a holiday on one side and a weekend or holiday on the other side
    off = (df["is_weekend"] == 1) | (df["is_holiday"] == 1)
    hol = df["is_holiday"] == 1
    prev_off, next_off = off.shift(1, fill_value=False), off.shift(-1, fill_value=False)
    prev_hol, next_hol = hol.shift(1, fill_value=False), hol.shift(-1, fill_value=False)
    df["is_bridge_day"] = (~off & ((prev_hol & next_off) | (next_hol & prev_off))).astype(int)

    school = load_school_holidays(school_csv)
    df["school_holiday_type"] = None
    for row in school.itertuples():
        span = (dates >= row.start) & (dates < row.end)
        # a long holiday period wins over a single school-free day if they overlap
        current = df.loc[span, "school_holiday_type"]
        take = current.isna() | (current == "school_free_day")
        df.loc[current.index[take.to_numpy()], "school_holiday_type"] = row.type
    df["is_school_holiday"] = df["school_holiday_type"].notna().astype(int)

    extra = [d for d in ph if d < dates.min() or d > dates.max()]
    to_next, since = days_to_from(df["is_holiday"], extra)
    df["days_to_next_holiday"] = to_next.astype(int)
    df["days_since_last_holiday"] = since.astype(int)

    md = dates.month * 100 + dates.day
    df["is_christmas_period"] = ((md >= 1224) | (md <= 102)).astype(int)
    df["hours_in_day"] = hours_in_local_day(dates)
    df["is_dst_change_day"] = (df["hours_in_day"] != 24).astype(int)

    covid = load_covid(oxcgrt_csv)
    df["covid_stringency"] = covid.reindex(dates).to_numpy()
    filled = df["covid_stringency"].copy()
    filled[dates < covid.index.min()] = 0.0   # before 2020: no measures
    filled[dates > covid.index.max()] = 0.0   # after 2022: tracker stopped, measures lifted (see assumptions)
    df["covid_stringency_filled"] = filled

    df = df.reset_index().rename(columns={"index": "date"})
    order = ["date", "weekday", "month", "day_of_year", "is_weekend", "is_holiday", "holiday_name",
             "is_half_holiday", "half_holiday_name", "is_bridge_day", "is_school_holiday", "school_holiday_type",
             "days_to_next_holiday", "days_since_last_holiday", "is_christmas_period", "is_dst_change_day",
             "hours_in_day", "covid_stringency", "covid_stringency_filled"]
    return df[order]


def main(skip_download: bool = False, force: bool = False) -> pd.DataFrame:
    """Download (if needed) and build data/processed/calendar_daily.parquet."""
    school_csv = raw_dir("schulferien") / "schulferien.csv"
    oxcgrt_csv = raw_dir("oxcgrt") / "OxCGRT_compact_national_v1.csv"
    if not skip_download:
        download(SCHOOL_URL, school_csv, force=force)
        download(OXCGRT_URL, oxcgrt_csv, force=force)
    df = build(school_csv, oxcgrt_csv)
    n_before = len(df)
    df = df.drop_duplicates("date")
    out = save_processed(df, "calendar_daily")
    notes = [
        f"public holidays per year (incl. Berchtoldstag): "
        f"{df.groupby(pd.to_datetime(df['date']).dt.year)['is_holiday'].sum().to_dict()}",
        f"bridge days: {int(df['is_bridge_day'].sum())}; half-holidays: {int(df['is_half_holiday'].sum())}",
        f"school-holiday days: {int(df['is_school_holiday'].sum())}; types: "
        f"{df['school_holiday_type'].value_counts().to_dict()}",
        f"DST days: {int(df['is_dst_change_day'].sum())} (hours_in_day values {sorted(df['hours_in_day'].unique())})",
        "holiday_name / half_holiday_name / school_holiday_type are empty on normal days (by design).",
        "covid_stringency is NaN outside 2020-01-01..2022-12-31 (OxCGRT coverage); use covid_stringency_filled "
        "(0 outside) in models.",
    ]
    write_check("calendar_daily", df, duplicates_removed=n_before - len(df), notes=notes)
    print(f"wrote {rel(out)}: {len(df)} rows")
    return df


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--skip-download", action="store_true", help="use cached raw files only")
    ap.add_argument("--force", action="store_true", help="re-download raw files")
    a = ap.parse_args()
    main(skip_download=a.skip_download, force=a.force)
