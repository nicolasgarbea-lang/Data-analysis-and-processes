"""Small helpers shared by the calendar / EV / events / football loaders (agent D3 only).

Daily tables in this group are keyed by `date` = local Europe/Zurich calendar day.
"""
from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import requests

from src.config import ROOT, path

DAILY_START = "2018-12-01"
DAILY_END = "2026-12-31"
TZ = "Europe/Zurich"
USER_AGENT = "Mozilla/5.0 (university project; daily calendar features)"


def daily_dates() -> pd.DatetimeIndex:
    """All local calendar days of the daily tables (naive dates, one per day, no gaps)."""
    return pd.date_range(DAILY_START, DAILY_END, freq="D", name="date")


def raw_dir(source: str) -> Path:
    """Folder for raw downloads of one source, created if needed."""
    d = path("raw") / source
    d.mkdir(parents=True, exist_ok=True)
    return d


def download(url: str, dest: Path, force: bool = False, retries: int = 4) -> Path:
    """Download `url` to `dest` unless the file is already cached.

    Retries with exponential backoff on network errors, 429 and 5xx answers.
    """
    if dest.exists() and dest.stat().st_size > 0 and not force:
        return dest
    wait = 5
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=120)
            if r.status_code == 429 or r.status_code >= 500:
                raise requests.HTTPError(f"HTTP {r.status_code}")
            r.raise_for_status()
            dest.write_bytes(r.content)
            return dest
        except (requests.RequestException, requests.HTTPError) as exc:
            if attempt == retries:
                raise RuntimeError(f"Download failed after {retries} tries: {url} ({exc})") from exc
            time.sleep(wait)
            wait *= 2
    return dest


def save_processed(df: pd.DataFrame, name: str) -> Path:
    """Write a daily table to data/processed/<name>.parquet (`date` stored as a plain date)."""
    out = path("processed") / f"{name}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df.to_parquet(out, index=False)
    return out


def write_check(name: str, df: pd.DataFrame, duplicates_removed: int = 0, notes: list[str] | None = None) -> Path:
    """Write the short check file reports/data_checks/<name>.md for a daily table."""
    out = path("reports") / "data_checks" / f"{name}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    value_cols = [c for c in df.columns if c != "date"]
    miss = df[value_cols].isna().mean().mul(100).round(2)
    lines = [
        f"# Data check: {name}",
        "",
        f"- rows: {len(df)}",
        f"- first date: {pd.to_datetime(df['date']).min().date()}  (local Europe/Zurich calendar day)",
        f"- last date: {pd.to_datetime(df['date']).max().date()}",
        f"- duplicate dates removed: {duplicates_removed}",
        f"- % missing overall: {df[value_cols].isna().mean().mean() * 100:.2f}",
        "",
        "| column | % missing |",
        "|---|---|",
    ]
    lines += [f"| {c} | {miss[c]} |" for c in value_cols]
    if notes:
        lines += ["", "## Notes", ""] + [f"- {n}" for n in notes]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def rel(p: Path) -> str:
    """Path relative to the repo root, for log messages."""
    try:
        return str(Path(p).relative_to(ROOT))
    except ValueError:
        return str(p)
