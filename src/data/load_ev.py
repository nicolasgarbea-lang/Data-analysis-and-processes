"""Daily EV indicators for Zurich -> data/processed/ev_daily.parquet.

One row per local Europe/Zurich calendar day, 2018-12-01 .. 2026-12-31.

Sources
1. Stadt Zürich, "Bestand der Personenwagen nach Treibstoffart, Rechtsform und Stadtquartier" (VER200OD2001.csv).
   Yearly car stock on 30 September. We keep `Treibstoffart2Lang == "Elektrisch"` and sum over all quarters
   and legal forms -> electric cars in the city on 30 Sept of each year.
2. BFE "ich tanke strom" monthly key figures per canton: `stations_ZH_count` (charging stations, canton Zurich)
   and `chargingPower_ZH_sum` (installed charging power in kW, canton Zurich), 2020-11 .. 2026-10.

Two kinds of columns
- "true" columns (`ev_count_city`, `stations_zh_count`, `charging_kw_zh`): best estimate of the real value on the
  day, interpolated between published points. They use values that were published LATER, so they are fine for
  plots and analysis but NOT for forecasting features.
- `_known` columns: only values already published on that day (leakage-safe for features). Rules:
  * EV stock: the 30 Sept value of year Y is assumed public from 1 August of year Y+1 (the portal shows the
    2025 value was last updated on 13.07.2026; we round up to 1 August as a safety margin). On a given day we
    take the last published value and extend it with the last published yearly growth (straight line), because
    the stock grows steadily and a flat carry-forward would be ~10-14 months stale.
  * BFE charging: the value for month M is assumed public from the 15th of month M+1 (the October 2026 value
    was online on 19 Nov 2026). We carry the last published value forward (monthly steps are small).
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from src.data._utils_calendar import daily_dates, download, raw_dir, rel, save_processed, write_check

EV_URL = ("https://data.stadt-zuerich.ch/dataset/prd_ssz_fz_pw_bestand_jahr_quartier_antriebsart_rechtsform_od2001/"
          "download/VER200OD2001.csv")
BFE_URL = "https://www.uvek-gis.admin.ch/BFE/ogd/57/ich_tanke_strom_Kennzahlen_monatlich.csv"

EV_PUBLISH_MONTH_DAY = (8, 1)    # 30 Sept of year Y -> public on 1 Aug of Y+1
BFE_PUBLISH_DAY = 15             # month M -> public on the 15th of month M+1


def read_ev_yearly(csv_path) -> pd.Series:
    """Electric cars in the city of Zurich on 30 Sept of each year (index = 30 Sept date)."""
    v = pd.read_csv(csv_path, encoding="utf-8-sig")
    e = v[v["Treibstoffart2Lang"] == "Elektrisch"].groupby("StichtagDat")["AnzFahrzeuge"].sum()
    e.index = pd.to_datetime(e.index)
    return e.sort_index().astype(float)


def read_bfe_monthly(csv_path) -> pd.DataFrame:
    """Monthly canton-Zurich charging figures, index = last day of the month."""
    b = pd.read_csv(csv_path, encoding="utf-8-sig", usecols=["year", "month", "stations_ZH_count",
                                                             "chargingPower_ZH_sum"])
    month_end = pd.to_datetime(dict(year=b["year"], month=b["month"], day=1)) + pd.offsets.MonthEnd(0)
    b = b.rename(columns={"stations_ZH_count": "stations_zh_count", "chargingPower_ZH_sum": "charging_kw_zh"})
    b.index = pd.DatetimeIndex(month_end, name="month_end")
    return b[["stations_zh_count", "charging_kw_zh"]].astype(float).sort_index()


def interpolate_daily(points: pd.Series, dates: pd.DatetimeIndex, extrapolate: bool) -> pd.Series:
    """Straight-line interpolation of point values to every day.

    After the last point: extend with the last slope if `extrapolate`, else keep the last value.
    Before the first point: NaN.
    """
    x = points.index.values.astype("datetime64[D]").astype(float)
    y = points.to_numpy()
    d = dates.values.astype("datetime64[D]").astype(float)
    out = np.interp(d, x, y, left=np.nan, right=np.nan)
    after = d > x[-1]
    if extrapolate and len(x) >= 2:
        slope = (y[-1] - y[-2]) / (x[-1] - x[-2])
        out[after] = y[-1] + slope * (d[after] - x[-1])
    else:
        out[after] = y[-1]
    return pd.Series(out, index=dates)


def ev_known(points: pd.Series, dates: pd.DatetimeIndex) -> pd.Series:
    """Leakage-safe EV stock: last published value + last published yearly growth (straight line)."""
    month, day = EV_PUBLISH_MONTH_DAY
    published = pd.to_datetime([f"{t.year + 1}-{month:02d}-{day:02d}" for t in points.index])
    out = pd.Series(np.nan, index=dates)
    for i, d in enumerate(dates):
        avail = points[published <= d]
        if len(avail) == 0:
            continue
        t_last, v_last = avail.index[-1], avail.iloc[-1]
        if len(avail) >= 2:
            slope = (v_last - avail.iloc[-2]) / (t_last - avail.index[-2]).days
        else:
            slope = 0.0
        out.iloc[i] = v_last + slope * (d - t_last).days
    return out


def bfe_known(monthly: pd.Series, dates: pd.DatetimeIndex) -> pd.Series:
    """Leakage-safe BFE value: last monthly value already published (month M public on the 15th of M+1)."""
    pub = monthly.index + pd.Timedelta(days=BFE_PUBLISH_DAY)  # month end + 15 days = 15th of next month
    s = pd.Series(monthly.to_numpy(), index=pub)
    return s.reindex(dates, method="ffill")


def backcast(monthly: pd.Series, dates: pd.DatetimeIndex, n_months: int = 12) -> pd.Series:
    """Rough back-extrapolation before the series starts: straight-line trend of the first `n_months`,
    extended backwards and clipped at 0. Clearly synthetic; observed values are used where they exist."""
    first = monthly.iloc[:n_months]
    x = first.index.values.astype("datetime64[D]").astype(float)
    a, b = np.polyfit(x, first.to_numpy(), 1)
    d = dates.values.astype("datetime64[D]").astype(float)
    est = np.clip(a * d + b, 0, None)
    obs = interpolate_daily(monthly, dates, extrapolate=False)
    return pd.Series(np.where(np.isnan(obs), est, obs), index=dates)


def build(ev_csv, bfe_csv) -> pd.DataFrame:
    """Build the daily EV table from cached raw files."""
    dates = daily_dates()
    ev = read_ev_yearly(ev_csv)
    bfe = read_bfe_monthly(bfe_csv)
    df = pd.DataFrame(index=dates)
    df["ev_count_city"] = interpolate_daily(ev, dates, extrapolate=True)
    df["ev_count_city_is_extrapolated"] = (dates > ev.index.max()).astype(int)
    df["ev_count_city_known"] = ev_known(ev, dates)
    for col in ["stations_zh_count", "charging_kw_zh"]:
        df[col] = interpolate_daily(bfe[col], dates, extrapolate=False)
        df[f"{col}_known"] = bfe_known(bfe[col], dates)
    df["charging_kw_zh_backcast"] = backcast(bfe["charging_kw_zh"], dates)
    # beyond the last monthly value the "true" columns are only held flat; mark it
    df["bfe_is_held_after_last_month"] = (dates > bfe.index.max()).astype(int)
    return df.reset_index().rename(columns={"index": "date"})


def main(skip_download: bool = False, force: bool = False) -> pd.DataFrame:
    """Download (if needed) and build data/processed/ev_daily.parquet."""
    ev_csv = raw_dir("ev_stadt_zuerich") / "VER200OD2001.csv"
    bfe_csv = raw_dir("bfe_charging") / "ich_tanke_strom_Kennzahlen_monatlich.csv"
    if not skip_download:
        download(EV_URL, ev_csv, force=force)
        download(BFE_URL, bfe_csv, force=force)
    df = build(ev_csv, bfe_csv)
    out = save_processed(df, "ev_daily")
    ev = read_ev_yearly(ev_csv)
    bfe = read_bfe_monthly(bfe_csv)
    notes = [
        f"EV stock points (30 Sept): {', '.join(f'{d.year}: {int(v)}' for d, v in ev.items() if d.year >= 2017)}",
        f"EV values after {ev.index.max().date()} are extrapolated with the last yearly slope "
        "(ev_count_city_is_extrapolated = 1).",
        f"BFE monthly data {bfe.index.min():%Y-%m} .. {bfe.index.max():%Y-%m} ({len(bfe)} months); "
        "monthly value placed on the last day of its month and interpolated linearly.",
        "stations_zh_count / charging_kw_zh are NaN before 2020-11-30 (series does not exist); "
        "the _known versions are NaN before 2020-12-15.",
        "charging_kw_zh_backcast fills the time before 2020-11 with a straight-line trend of the first 12 months "
        "(synthetic, clipped at 0).",
        f"ev_count_city_known on 2026-10-01: {df.loc[df['date'] == '2026-10-01', 'ev_count_city_known'].iloc[0]:.0f}"
        f" vs interpolated truth {df.loc[df['date'] == '2026-10-01', 'ev_count_city'].iloc[0]:.0f}",
    ]
    write_check("ev_daily", df, notes=notes)
    print(f"wrote {rel(out)}: {len(df)} rows")
    return df


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--skip-download", action="store_true", help="use cached raw files only")
    ap.add_argument("--force", action="store_true", help="re-download raw files")
    a = ap.parse_args()
    main(skip_download=a.skip_download, force=a.force)
