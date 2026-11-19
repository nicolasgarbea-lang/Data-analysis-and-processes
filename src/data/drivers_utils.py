"""Small helpers shared by the price-driver loaders (agent D4 only).

- polite HTTP GET with pause + exponential backoff (Energy-Charts rate-limits)
- writing the short data-check markdown files
- turning a local "known from" time into a UTC timestamp (`available_from_utc`)
"""
from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import requests

from src.config import ROOT, path

BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

_last_call: dict[str, float] = {}


def polite_get(url: str, *, params: dict | None = None, min_pause_s: float = 6.0,
               max_tries: int = 8, headers: dict | None = None, timeout: int = 120,
               host_key: str = "default") -> requests.Response:
    """GET a URL, waiting at least `min_pause_s` since the last call to the same host.

    On HTTP 429 or 5xx we wait with exponential backoff (30 s, 60 s, 120 s, ... capped
    at 10 min) and try again. Any other error status raises immediately.
    """
    hdrs = {"User-Agent": BROWSER_UA}
    if headers:
        hdrs.update(headers)
    wait = 30.0
    for attempt in range(1, max_tries + 1):
        since = time.time() - _last_call.get(host_key, 0.0)
        if since < min_pause_s:
            time.sleep(min_pause_s - since)
        try:
            r = requests.get(url, params=params, headers=hdrs, timeout=timeout)
        except requests.RequestException as exc:  # network hiccup → treat like 5xx
            print(f"  network error ({exc}); retry {attempt}/{max_tries} in {wait:.0f}s")
            _last_call[host_key] = time.time()
            time.sleep(wait)
            wait = min(wait * 2, 600)
            continue
        _last_call[host_key] = time.time()
        if r.status_code == 429 or r.status_code >= 500:
            print(f"  HTTP {r.status_code}; retry {attempt}/{max_tries} in {wait:.0f}s")
            time.sleep(wait)
            wait = min(wait * 2, 600)
            continue
        r.raise_for_status()
        return r
    raise RuntimeError(f"Giving up on {url} {params} after {max_tries} tries")


def raw_dir(source: str) -> Path:
    d = path("raw") / source
    d.mkdir(parents=True, exist_ok=True)
    return d


def processed_path(name: str) -> Path:
    d = path("processed")
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{name}.parquet"


def local_time_to_utc(dates: pd.Series, hhmm: str, days_offset: int = 0,
                      tz: str = "Europe/Zurich") -> pd.Series:
    """For each calendar date, return `date + days_offset` at local clock time `hhmm`, in UTC."""
    d = pd.to_datetime(pd.Series(dates).astype(str)) + pd.Timedelta(days=days_offset)
    h, m = (int(x) for x in hhmm.split(":"))
    local = d + pd.Timedelta(hours=h, minutes=m)
    utc = local.dt.tz_localize(tz, ambiguous=False, nonexistent="shift_forward").dt.tz_convert("UTC")
    return utc.astype("datetime64[ns, UTC]")


def write_check(name: str, lines: list[str]) -> Path:
    """Write reports/data_checks/<name>.md (overwrites)."""
    d = ROOT / "reports" / "data_checks"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{name}.md"
    p.write_text(f"# Data check: {name}\n\n" + "\n".join(f"- {x}" for x in lines) + "\n", encoding="utf-8")
    print(p.read_text())
    return p
