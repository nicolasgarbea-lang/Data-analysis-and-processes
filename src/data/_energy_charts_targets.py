"""Small helper to download Energy-Charts API data politely (used by the D1 target loaders).

Energy-Charts blocks clients that send many quick requests. This helper therefore
- caches every chunk as raw JSON on disk (a rerun never refetches a cached chunk),
- waits at least MIN_PAUSE_S seconds between two network calls,
- retries with exponential backoff on HTTP 429 and 5xx errors.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import requests

BASE_URL = "https://api.energy-charts.info"
MIN_PAUSE_S = 7.0          # pause between calls (another agent shares the rate limit)
MAX_RETRIES = 8
_last_call = [0.0]         # time of the last network call (module-level, simple)


def fetch_json(endpoint: str, params: dict, cache_file: Path, force: bool = False,
               skip_download: bool = False) -> dict | None:
    """Return the JSON for one API call, using `cache_file` as cache.

    If `skip_download` is True only the cache is read (None if it is missing).
    """
    cache_file = Path(cache_file)
    if cache_file.exists() and not force:
        return json.loads(cache_file.read_text())
    if skip_download:
        return None

    url = f"{BASE_URL}/{endpoint}"
    wait = 30.0
    for attempt in range(1, MAX_RETRIES + 1):
        # respect the minimum pause between calls
        gap = time.time() - _last_call[0]
        if gap < MIN_PAUSE_S:
            time.sleep(MIN_PAUSE_S - gap)
        _last_call[0] = time.time()
        try:
            r = requests.get(url, params=params, timeout=120)
        except requests.RequestException as e:
            print(f"  network error ({e}); retry {attempt} in {wait:.0f} s")
            time.sleep(wait)
            wait = min(wait * 2, 600)
            continue
        if r.status_code == 200:
            data = r.json()
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(data))
            return data
        if r.status_code == 404:
            # Energy-Charts answers 404 when there is no data for the period
            print(f"  404 for {url} {params}: {r.text[:200]}")
            return None
        if r.status_code == 429 or r.status_code >= 500:
            print(f"  HTTP {r.status_code}; retry {attempt} in {wait:.0f} s")
            time.sleep(wait)
            wait = min(wait * 2, 600)
            continue
        r.raise_for_status()
    raise RuntimeError(f"Energy-Charts call failed after {MAX_RETRIES} tries: {url} {params}")
