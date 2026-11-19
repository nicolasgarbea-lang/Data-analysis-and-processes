"""Zurich electricity demand (ewz "Bruttolastgang Stadt Zürich"), converted to UTC.

Source files
- data/raw/ewz/{YYYY}_ewz_bruttolastgang.csv  (one per year, 2019 → current year)
  columns: zeitpunkt (LOCAL Zurich time, no offset), bruttolastgang (kWh per 15 min), status
- data/raw/ewz_netzebenen/ewz_stromabgabe_netzebenen_stadt_zuerich.csv  (UTC, NE5 + NE7)
  used to (a) check the time conversion, (b) put the duplicated autumn DST rows in the right
  order and (c) fill the two whole days missing in the 2021 file.

Time convention (verified, see reports/data_checks/demand_ewz_crosscheck.md)
- The ewz timestamps label the END of the 15-minute interval: the Netzebenen metadata says
  "values refer to the 15 minutes before this time", and Bruttolastgang equals NE5 + NE7 at the
  same instant with correlation 0.99999 (any 15-min shift is clearly worse). The year files
  therefore run from YYYY-01-01 00:15 to (YYYY+1)-01-01 00:00; the 00:00 row of each file is
  the last interval of the previous year (2019 starts at 00:15 because of this).
- We convert the local END label to UTC and subtract 15 minutes, so `timestamp_utc` is the
  START of the interval, as everywhere else in the project.
- On the autumn DST day the local labels 02:00–02:45 appear twice. The row order in the files is
  not reliable (it changes from year to year and even within a day), so each pair is matched to
  the two UTC candidates using the Netzebenen values.

Outputs
- data/processed/demand_ewz.parquet: timestamp_utc, load_kwh_15min, status, is_filled, fill_method
- data/processed/demand_ewz_hourly.parquet: timestamp_utc, load_mw (mean MW over the hour),
  n_intervals, share_non_final, share_status_f, n_filled

Run:  .venv/bin/python -m src.data.load_ewz_demand [--skip-download] [--force]
"""
from __future__ import annotations

import argparse
from datetime import date

import numpy as np
import pandas as pd
import requests

from src.config import path

RAW_DIR = path("raw") / "ewz"
RAW_NE_DIR = path("raw") / "ewz_netzebenen"
NE_FILE = RAW_NE_DIR / "ewz_stromabgabe_netzebenen_stadt_zuerich.csv"
URL_YEAR = ("https://data.stadt-zuerich.ch/dataset/ewz_bruttolastgang_stadt_zuerich/"
            "download/{year}_ewz_bruttolastgang.csv")
URL_NE = ("https://data.stadt-zuerich.ch/dataset/ewz_stromabgabe_netzebenen_stadt_zuerich/"
          "download/ewz_stromabgabe_netzebenen_stadt_zuerich.csv")
OUT_15 = path("processed") / "demand_ewz.parquet"
OUT_H = path("processed") / "demand_ewz_hourly.parquet"
CHECK_FILE = path("reports") / "data_checks" / "demand_ewz.md"
CROSS_FILE = path("reports") / "data_checks" / "demand_ewz_crosscheck.md"
FIRST_YEAR = 2019
TZ = "Europe/Zurich"
Q = pd.Timedelta(minutes=15)
MAX_INTERP_INTERVALS = 4   # gaps of at most 1 hour may be linearly interpolated


# ---------------------------------------------------------------- download
def _download(url: str, target, force: bool) -> None:
    if target.exists() and not force:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    print(f"download {url}")
    r = requests.get(url, timeout=300, allow_redirects=True)  # the portal redirects
    r.raise_for_status()
    target.write_bytes(r.content)


def download(force: bool = False) -> None:
    for year in range(FIRST_YEAR, date.today().year + 1):
        _download(URL_YEAR.format(year=year), RAW_DIR / f"{year}_ewz_bruttolastgang.csv", force)
    _download(URL_NE, NE_FILE, force)


# ---------------------------------------------------------------- reading
def read_ewz() -> pd.DataFrame:
    """All year files stacked, in file order, with a naive local END label `label_local`."""
    frames = []
    for f in sorted(RAW_DIR.glob("*_ewz_bruttolastgang.csv")):
        d = pd.read_csv(f, encoding="utf-8-sig")
        d["file"] = f.name
        frames.append(d)
    d = pd.concat(frames, ignore_index=True)
    d["label_local"] = pd.to_datetime(d["zeitpunkt"])
    return d.rename(columns={"bruttolastgang": "load_kwh_15min"})


def read_netzebenen() -> pd.Series:
    """NE5 + NE7 in kWh per 15 min, indexed by the UTC START of the interval."""
    n = pd.read_csv(NE_FILE)
    end_utc = pd.to_datetime(n["Timestamp"], utc=True)
    s = pd.Series((n["Value_NE5"] + n["Value_NE7"]).values, index=end_utc - Q, name="ne_kwh")
    return s[~s.index.duplicated()].sort_index()


# ---------------------------------------------------------------- local → UTC
def to_utc(d: pd.DataFrame, ne: pd.Series) -> tuple[pd.DataFrame, list[dict]]:
    """Add `timestamp_utc` (interval START, UTC). Returns (table, log of the DST pair decisions)."""
    d = d.copy()
    dup = d["label_local"].duplicated(keep=False)

    # ordinary rows: the local label is unique, so the conversion is unambiguous
    end_utc = d.loc[~dup, "label_local"].dt.tz_localize(TZ, nonexistent="raise", ambiguous="raise")
    d.loc[~dup, "timestamp_utc"] = end_utc.dt.tz_convert("UTC") - Q

    # duplicated autumn labels: two rows, two UTC candidates (summer time / winter time)
    log = []
    for label, rows in d[dup].groupby("label_local"):
        if len(rows) != 2:
            raise ValueError(f"label {label} appears {len(rows)} times")
        cand_summer = pd.Timestamp(label).tz_localize(TZ, ambiguous=True).tz_convert("UTC") - Q
        cand_winter = pd.Timestamp(label).tz_localize(TZ, ambiguous=False).tz_convert("UTC") - Q
        v1, v2 = rows["load_kwh_15min"].values
        n_s, n_w = ne.get(cand_summer, np.nan), ne.get(cand_winter, np.nan)
        if np.isnan(n_s) or np.isnan(n_w):
            # no reference: assume file order is chronological (documented fallback)
            first_is_summer, method = True, "file order (no Netzebenen value)"
        else:
            keep = abs(v1 - n_s) + abs(v2 - n_w)
            swap = abs(v1 - n_w) + abs(v2 - n_s)
            first_is_summer, method = keep <= swap, "matched to Netzebenen"
        idx1, idx2 = rows.index
        d.loc[idx1, "timestamp_utc"] = cand_summer if first_is_summer else cand_winter
        d.loc[idx2, "timestamp_utc"] = cand_winter if first_is_summer else cand_summer
        log.append({"label_local": label, "row1_kwh": v1, "row2_kwh": v2, "ne_summer": n_s,
                    "ne_winter": n_w, "file_order_chronological": bool(first_is_summer), "method": method})
    d["timestamp_utc"] = pd.to_datetime(d["timestamp_utc"], utc=True)
    return d, log


# ---------------------------------------------------------------- gaps
def complete_grid(d: pd.DataFrame, ne: pd.Series) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Put the data on a full 15-min UTC grid and fill gaps. Returns (table, list of gaps)."""
    s = d.set_index("timestamp_utc")[["load_kwh_15min", "status"]].sort_index()
    if s.index.duplicated().any():
        raise ValueError("duplicate UTC timestamps after conversion")
    grid = pd.date_range(s.index.min(), s.index.max(), freq="15min", name="timestamp_utc")
    s = s.reindex(grid)
    s["is_filled"] = False
    s["fill_method"] = ""

    miss = s["load_kwh_15min"].isna()
    run_id = (miss != miss.shift()).cumsum()
    gaps = (s.index.to_series()[miss].groupby(run_id[miss]).agg(["first", "last", "count"])
            .reset_index(drop=True))
    gaps["filled_with"] = ""

    for i, g in gaps.iterrows():
        span = s.loc[g["first"]:g["last"]].index
        ne_vals = ne.reindex(span)
        if ne_vals.notna().all():
            # NE5 + NE7 is the same quantity (checked: median abs. difference ~2 kWh)
            s.loc[span, "load_kwh_15min"] = ne_vals.values
            s.loc[span, "fill_method"] = "netzebenen"
            gaps.loc[i, "filled_with"] = "netzebenen"
        elif g["count"] <= MAX_INTERP_INTERVALS:
            s["load_kwh_15min"] = s["load_kwh_15min"].interpolate(limit_area="inside",
                                                                  limit=MAX_INTERP_INTERVALS)
            s.loc[span, "fill_method"] = "interpolated"
            gaps.loc[i, "filled_with"] = "interpolated"
        else:
            gaps.loc[i, "filled_with"] = "left missing"
        s.loc[span, "is_filled"] = s.loc[span, "load_kwh_15min"].notna()
    s.loc[~s["is_filled"], "fill_method"] = ""
    return s.reset_index(), gaps


def hourly(q: pd.DataFrame) -> pd.DataFrame:
    """Mean MW per UTC hour. kWh per 15 min × 4 / 1000 = MW."""
    q = q.copy()
    q["hour"] = q["timestamp_utc"].dt.floor("h")
    q["non_final"] = q["status"].notna() & (q["status"] != "W")
    q["is_f"] = q["status"] == "F"
    h = q.groupby("hour").agg(
        load_kwh_mean=("load_kwh_15min", "mean"),
        n_intervals=("load_kwh_15min", "count"),
        share_non_final=("non_final", "mean"),
        share_status_f=("is_f", "mean"),
        n_filled=("is_filled", "sum"),
    )
    h["load_mw"] = h["load_kwh_mean"] * 4 / 1000
    h.loc[h["n_intervals"] < 4, "load_mw"] = np.nan   # incomplete hour → not trusted
    h = h.reset_index().rename(columns={"hour": "timestamp_utc"})
    return h[["timestamp_utc", "load_mw", "n_intervals", "share_non_final", "share_status_f", "n_filled"]]


# ---------------------------------------------------------------- reports
def write_crosscheck(d: pd.DataFrame, ne: pd.Series, log: list[dict]) -> None:
    """Document the start/end question, the DST handling and the agreement with Netzebenen."""
    s = d.set_index("timestamp_utc")["load_kwh_15min"]
    lines = [
        "# Cross-check: ewz Bruttolastgang (local time) vs ewz Netzebenen NE5+NE7 (UTC)",
        "",
        "Netzebenen metadata (data.stadt-zuerich.ch, field `Timestamp`): *\"Die Werte der Bruttoenergie "
        "beziehen sich auf die 15 Minuten vor dieser Zeitangabe\"* → its timestamps mark the END of the interval.",
        "",
        "Below, Bruttolastgang was converted with our rule (local label = END, → UTC, −15 min = START) and "
        "compared with Netzebenen (UTC END label −15 min = START), shifting Netzebenen by k × 15 min.",
        "",
        "| shift of Netzebenen | correlation | mean abs. diff (kWh/15 min) | n |",
        "|---|---|---|---|",
    ]
    for k in range(-4, 5):
        sh = ne.copy()
        sh.index = sh.index + k * Q
        j = pd.concat([s.rename("e"), sh.rename("n")], axis=1, join="inner").dropna()
        lines.append(f"| {k * 15:+d} min | {j['e'].corr(j['n']):.6f} | {(j['e'] - j['n']).abs().mean():.1f} | {len(j)} |")
    j = pd.concat([s.rename("e"), ne.rename("n")], axis=1, join="inner").dropna()
    rel = (j["e"] - j["n"]).abs() / j["n"]
    big = j[rel > 0.01]
    lines += [
        "",
        "Shift 0 is best by far → both files use the same convention, i.e. the ewz local timestamps are END labels too.",
        "Further evidence: every ewz year file starts at 00:15 or ends with the 00:00 row of the next day "
        "(2019 starts 00:15; 2020–2026 start with the 00:00 row = last interval of the previous year; "
        "the 2026 file ends with a single 00:00 row of the next day; the missing 2021 days span exactly "
        "00:15 → 00:00 of the next day).",
        "",
        f"- matched intervals: {len(j)}",
        f"- abs. difference: median {(j['e'] - j['n']).abs().median():.2f} kWh, "
        f"mean {(j['e'] - j['n']).abs().mean():.2f} kWh, max {(j['e'] - j['n']).abs().max():.1f} kWh "
        f"(typical value ~60,000 kWh)",
        f"- intervals with > 1 % difference: {len(big)}"
        + (f" (days: {', '.join(sorted({str(x.date()) for x in big.index}))}; likely later revisions of one file)"
           if len(big) else ""),
        f"- Netzebenen covers {ne.index.min()} → {ne.index.max()} (interval starts, UTC)",
        "",
        "## Autumn DST duplicates (local labels 02:00–02:45 appear twice)",
        "",
        "`file_order_chronological` = True means the first of the two rows in the file is the summer-time "
        "(earlier) interval. The order is not consistent, so sorting by file order would be wrong in "
        f"{sum(not x['file_order_chronological'] for x in log)} of {len(log)} pairs.",
        "",
        "| local label | row 1 kWh | row 2 kWh | NE summer-time | NE winter-time | file order chronological | method |",
        "|---|---|---|---|---|---|---|",
    ]
    for x in log:
        lines.append(f"| {x['label_local']} | {x['row1_kwh']:.0f} | {x['row2_kwh']:.0f} | {x['ne_summer']:.0f} | "
                     f"{x['ne_winter']:.0f} | {x['file_order_chronological']} | {x['method']} |")
    CROSS_FILE.parent.mkdir(parents=True, exist_ok=True)
    CROSS_FILE.write_text("\n".join(lines) + "\n")


def write_check(q: pd.DataFrame, h: pd.DataFrame, gaps: pd.DataFrame, n_raw: int, n_dup_pairs: int) -> None:
    status = q["status"].value_counts(dropna=False).to_dict()
    hh = h[h["timestamp_utc"] < pd.Timestamp("2026-11-01", tz="UTC")]
    local_days = h.assign(day=h["timestamp_utc"].dt.tz_convert(TZ).dt.date).groupby("day").size()
    odd_days = local_days[~local_days.isin([24])]
    lines = [
        "# Check: demand_ewz.parquet / demand_ewz_hourly.parquet (ewz Bruttolastgang, Zurich)",
        "",
        f"- raw rows read: {n_raw}; autumn DST label pairs resolved: {n_dup_pairs} (none dropped)",
        f"- 15-min rows: {len(q)}; first / last timestamp_utc (interval start): "
        f"{q['timestamp_utc'].min()} / {q['timestamp_utc'].max()}",
        f"- local time: {q['timestamp_utc'].min().tz_convert(TZ)} → {q['timestamp_utc'].max().tz_convert(TZ)} (interval start)",
        f"- duplicate UTC timestamps after conversion: {int(q['timestamp_utc'].duplicated().sum())}",
        f"- missing 15-min intervals before filling: {int(gaps['count'].sum())} "
        f"({gaps['count'].sum() / len(q):.3%}); after filling: {int(q['load_kwh_15min'].isna().sum())}",
        f"- filled intervals: {int(q['is_filled'].sum())} "
        f"({q['fill_method'].value_counts().drop('', errors='ignore').to_dict()})",
        f"- status counts (15-min): {status}  (W = final, E = substitute, F = not yet checked; "
        "no W at all in the current files, so `share_non_final` is 1 everywhere — use `share_status_f`)",
        f"- hourly rows: {len(h)}; hours with load_mw missing: {int(h['load_mw'].isna().sum())}; "
        f"hours before 2026-11-01 UTC missing: {int(hh['load_mw'].isna().sum())}",
        f"- load_mw range: min {h['load_mw'].min():.1f}, max {h['load_mw'].max():.1f}, mean {h['load_mw'].mean():.1f} MW",
        f"- local days with ≠ 24 hours (should be only DST days, 23 / 25 h, plus partial first/last day): "
        f"{ {str(k): int(v) for k, v in odd_days.items()} }",
        "",
        "## Gaps in the raw data",
        "",
        "| first interval start (UTC) | last interval start (UTC) | intervals | filled with |",
        "|---|---|---|---|",
    ]
    for _, g in gaps.iterrows():
        lines.append(f"| {g['first']} | {g['last']} | {g['count']} | {g['filled_with']} |")
    if gaps.empty:
        lines.append("| none | | | |")
    f_rows = q[q["status"] == "F"]
    if len(f_rows):
        lines += ["", "## Status F by month (local time)", "", "| month | intervals with F |", "|---|---|"]
        for m, c in f_rows.groupby(f_rows["timestamp_utc"].dt.tz_convert(TZ).dt.strftime("%Y-%m")).size().items():
            lines.append(f"| {m} | {c} |")
    lines += ["", "## Yearly mean load (MW, local calendar year)", "", "| year | mean MW | min | max |", "|---|---|---|---|"]
    for y, g in h.groupby(h["timestamp_utc"].dt.tz_convert(TZ).dt.year)["load_mw"]:
        lines.append(f"| {y} | {g.mean():.1f} | {g.min():.1f} | {g.max():.1f} |")
    CHECK_FILE.parent.mkdir(parents=True, exist_ok=True)
    CHECK_FILE.write_text("\n".join(l for l in lines) + "\n")


# ---------------------------------------------------------------- main
def main(skip_download: bool = False, force: bool = False) -> pd.DataFrame:
    """Build demand_ewz.parquet (15 min) and demand_ewz_hourly.parquet from the ewz CSV files."""
    if not skip_download:
        download(force=force)
    raw = read_ewz()
    ne = read_netzebenen()
    d, log = to_utc(raw, ne)
    write_crosscheck(d, ne, log)
    q, gaps = complete_grid(d, ne)
    q["timestamp_utc"] = q["timestamp_utc"].astype("datetime64[ns, UTC]")
    q = q[["timestamp_utc", "load_kwh_15min", "status", "is_filled", "fill_method"]]
    h = hourly(q)
    h["timestamp_utc"] = h["timestamp_utc"].astype("datetime64[ns, UTC]")
    OUT_15.parent.mkdir(parents=True, exist_ok=True)
    q.to_parquet(OUT_15, index=False)
    h.to_parquet(OUT_H, index=False)
    write_check(q, h, gaps, len(raw), len(log))
    print(f"wrote {OUT_15} ({len(q)} rows) and {OUT_H} ({len(h)} rows)")
    return h


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--skip-download", action="store_true", help="use cached raw files only")
    ap.add_argument("--force", action="store_true", help="re-download even if cached")
    a = ap.parse_args()
    main(skip_download=a.skip_download, force=a.force)
