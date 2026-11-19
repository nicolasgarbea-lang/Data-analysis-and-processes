"""Archived weather FORECASTS for 9 European points that drive the Swiss day-ahead price (Open-Meteo previous-runs API).

Why: the Swiss price follows the German price, which depends on German wind and solar, and French demand
depends strongly on temperature (electric heating). Alpine precipitation drives Swiss hydro inflow.

Points (name: lat, lon):
  de_north 53.9/8.9 (North Sea coast wind), de_northeast 53.4/12.5, de_central 51.3/9.5 (wind points),
  de_south 48.6/11.5 (Bavarian solar), fr_paris 48.85/2.35, fr_lyon 45.76/4.84, it_milan 45.46/9.19,
  ch_alps 46.5/8.3 (hydro inflow / precipitation), ch_bern 46.95/7.45.

Models:
- `icon_seamless` (DWD ICON): real forecasts from 2024-01 -> columns `<var>_<point>_safe`.
  Wind at 100 m (hub height) is available, so `wind100_ms_*` is used.
- `jma_seamless` (JMA GSM, ~0.5 deg): archive back to 2018, no radiation, no 100 m wind -> 10 m wind,
  columns `<var>_<point>_jma_safe`.

All conventions are REUSED from `src/data/load_openmeteo_forecast.py` (agent D2) by importing its functions:
- Open-Meteo stamp - 1 h -> `timestamp_utc` = START of hour.
- leakage-safe lead: `safe_lead_days()` with the same run cadence and publication delay per model as D2
  (ICON 3 h / 4 h, JMA 6 h / 6 h): day1 only if its model run was published by D 10:00 Europe/Zurich, else day2.

Outputs:
- data/processed/weather_europe_forecast_hourly.parquet      (ONLY `*_safe` columns + timestamp_utc)
- data/processed/weather_europe_forecast_raw_hourly.parquet  (day1 / day2 values + lead used, for checks)
Run: .venv/bin/python -m src.data.load_openmeteo_europe [--skip-download] [--force]
"""
from __future__ import annotations

import argparse
import json
import time

import numpy as np
import pandas as pd
import requests

from src.config import ROOT, path
from src.data.load_openmeteo_forecast import END_DATE, MODELS as D2_MODELS, START, URL, get_json, safe_lead_days

POINTS = {
    "de_north": (53.9, 8.9),
    "de_northeast": (53.4, 12.5),
    "de_central": (51.3, 9.5),
    "de_south": (48.6, 11.5),
    "fr_paris": (48.85, 2.35),
    "fr_lyon": (45.76, 4.84),
    "it_milan": (45.46, 9.19),
    "ch_alps": (46.5, 8.3),
    "ch_bern": (46.95, 7.45),
}
WIND_POINTS = ["de_north", "de_northeast", "de_central"]
DE_POINTS = ["de_north", "de_northeast", "de_central", "de_south"]
FR_POINTS = ["fr_paris", "fr_lyon"]
RADIATION_POINTS = [p for p in POINTS if not p.startswith("fr_")]  # DE, CH, IT
PRECIP_POINTS = ["ch_alps"]
WIND_CAP_MS = 25.0  # cap before cubing (turbines cut out / power curve is flat above rated speed)

# Open-Meteo variable -> (our base name, factor to our unit, points that keep it)
VARIABLES = {
    "temperature_2m": ("temp_c", 1.0, list(POINTS)),
    "shortwave_radiation": ("radiation_wm2", 1.0, RADIATION_POINTS),
    "wind_speed_100m": ("wind100_ms", 1 / 3.6, WIND_POINTS),  # km/h -> m/s
    "wind_speed_10m": ("wind10_ms", 1 / 3.6, WIND_POINTS),
    "precipitation": ("precip_mm", 1.0, PRECIP_POINTS),
}
# model -> (column suffix, first year, variables, wind variable used for wind_cubed); cadence/delay come from D2
MODELS = {
    "icon_seamless": ("", 2024, ["temperature_2m", "shortwave_radiation", "wind_speed_100m", "precipitation"],
                      "wind100_ms"),
    "jma_seamless": ("_jma", 2018, ["temperature_2m", "wind_speed_10m", "precipitation"], "wind10_ms"),
}
LEADS = {"_previous_day1": "day1", "_previous_day2": "day2"}  # day0 is never available at forecast time

RAW_DIR = path("raw") / "openmeteo_europe"
OUT_FILE = path("processed") / "weather_europe_forecast_hourly.parquet"
RAW_OUT_FILE = path("processed") / "weather_europe_forecast_raw_hourly.parquet"
PRICE_FILE = path("processed") / "price_neighbours_hourly.parquet"
CHECK_FILE = ROOT / "reports" / "data_checks" / "weather_europe_forecast_hourly.md"
PAUSE_S = 60  # one big call (9 points x 1 year) per minute keeps us far below the free per-minute weight


def fetch(params: dict, rounds: int = 6) -> list:
    """D2's `get_json` (backoff on 429/5xx), retried with long pauses if the server times out or keeps failing."""
    for attempt in range(rounds):
        try:
            return get_json(URL, params)
        except (requests.RequestException, RuntimeError) as e:
            wait = 120 * 2 ** attempt
            print(f"  request failed ({str(e)[:120]}), retrying in {wait} s", flush=True)
            time.sleep(wait)
    raise RuntimeError("previous-runs API not reachable, giving up (cached years are kept)")


def cadence_delay(model: str) -> tuple[int, int]:
    """Run cadence and publication delay (hours) exactly as D2 assumed for this model."""
    _, _, _, cadence, delay = D2_MODELS[model]
    return cadence, delay


# ----------------------------------------------------------------------------------------------------------
# download
# ----------------------------------------------------------------------------------------------------------
def download(force: bool = False) -> None:
    """One cached JSON per model and year (all 9 points in one multi-location call) in data/raw/openmeteo_europe/."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    lats = ",".join(str(p[0]) for p in POINTS.values())
    lons = ",".join(str(p[1]) for p in POINTS.values())
    first_call = True
    for model, (_, first_year, variables, _) in MODELS.items():
        for year in range(first_year, 2027):
            target = RAW_DIR / f"{model}_{year}.json"
            if target.exists() and not force:
                continue
            if not first_call:
                time.sleep(PAUSE_S)
            first_call = False
            start = max(pd.Timestamp(f"{year}-01-01"), START.tz_localize(None) - pd.Timedelta(days=1))
            end = min(pd.Timestamp(f"{year}-12-31"), pd.Timestamp(END_DATE))
            hourly = [v + lead for v in variables for lead in LEADS]
            params = dict(latitude=lats, longitude=lons, hourly=",".join(hourly), models=model, timezone="GMT",
                          start_date=start.date().isoformat(), end_date=end.date().isoformat())
            print(f"fetching {model} {year} ...", flush=True)
            data = fetch(params)
            if not isinstance(data, list) or len(data) != len(POINTS):
                raise RuntimeError(f"expected {len(POINTS)} locations, got {type(data)}")
            target.write_text(json.dumps(data), encoding="utf-8")


# ----------------------------------------------------------------------------------------------------------
# build
# ----------------------------------------------------------------------------------------------------------
def read_model(model: str) -> pd.DataFrame:
    """Cached JSON of one model -> wide frame with columns `<base>_<point>_<day1|day2><suffix>`, index = start of hour."""
    suffix, first_year, variables, _ = MODELS[model]
    frames = []
    for year in range(first_year, 2027):
        f = RAW_DIR / f"{model}_{year}.json"
        if not f.exists():
            continue
        locations = json.loads(f.read_text(encoding="utf-8"))
        cols = {}
        for point, loc in zip(POINTS, locations):  # API returns locations in request order
            h = loc["hourly"]
            idx = pd.to_datetime(h["time"]).tz_localize("UTC") - pd.Timedelta(hours=1)  # D2 convention
            for v in variables:
                base, factor, keep = VARIABLES[v]
                if point not in keep:
                    continue
                for lead, our in LEADS.items():
                    vals = pd.to_numeric(pd.Series(h[v + lead], index=idx), errors="coerce") * factor
                    if v == "precipitation":
                        vals = vals.clip(lower=0)  # JMA archive has a few -0.1 mm values (rounding artefact)
                    cols[f"{base}_{point}_{our}{suffix}"] = vals
        frames.append(pd.DataFrame(cols))
    df = pd.concat(frames)
    return df[~df.index.duplicated(keep="last")].sort_index()


def wind_cubed(speed_ms: pd.Series | np.ndarray) -> np.ndarray:
    """Wind speed in m/s, capped at 25 m/s, cubed (wind power ~ v^3)."""
    return np.minimum(np.asarray(speed_ms, dtype=float), WIND_CAP_MS) ** 3


def build_safe(raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Pick day1/day2 per row with D2's `safe_lead_days`, then add wind_cubed and regional means.

    Returns (safe frame, raw frame with the lead columns added)."""
    ts = raw["timestamp_utc"]
    safe = pd.DataFrame({"timestamp_utc": ts})
    for model, (suffix, _, variables, wind_base) in MODELS.items():
        cadence, delay = cadence_delay(model)
        lead = safe_lead_days(ts, cadence, delay).to_numpy()
        raw[f"safe_lead_days{suffix}"] = lead.astype("int8")
        for v in variables:
            base, _, keep = VARIABLES[v]
            for point in keep:
                d1 = raw[f"{base}_{point}_day1{suffix}"].to_numpy()
                d2 = raw[f"{base}_{point}_day2{suffix}"].to_numpy()
                safe[f"{base}_{point}{suffix}_safe"] = np.where(lead == 1, d1, d2)
        for point in WIND_POINTS:
            safe[f"wind_cubed_{point}{suffix}_safe"] = wind_cubed(safe[f"{wind_base}_{point}{suffix}_safe"])
        # regional means (NaN if any point is missing, so the mean never silently changes composition)
        safe[f"wind_cubed_de_mean{suffix}_safe"] = safe[[f"wind_cubed_{p}{suffix}_safe" for p in WIND_POINTS]].mean(
            axis=1, skipna=False)
        safe[f"temp_c_fr_mean{suffix}_safe"] = safe[[f"temp_c_{p}{suffix}_safe" for p in FR_POINTS]].mean(
            axis=1, skipna=False)
        if "shortwave_radiation" in variables:
            safe[f"radiation_wm2_de_mean{suffix}_safe"] = safe[
                [f"radiation_wm2_{p}{suffix}_safe" for p in DE_POINTS]].mean(axis=1, skipna=False)
    return safe, raw


def correlations(safe: pd.DataFrame) -> list[str]:
    """Sanity check: DE wind and DE radiation forecasts must correlate negatively with the DE day-ahead price."""
    if not PRICE_FILE.exists():
        return ["- price file missing, correlation check skipped"]
    price = pd.read_parquet(PRICE_FILE)[["timestamp_utc", "price_de_eur_mwh"]]
    m = safe.merge(price, on="timestamp_utc", how="inner")
    local_hour = m["timestamp_utc"].dt.tz_convert("Europe/Zurich").dt.hour
    y24 = m["timestamp_utc"] >= pd.Timestamp("2024-01-01", tz="UTC")
    mid = local_hour.between(11, 14)
    out = ["| forecast column | rows | sample | Pearson r | Spearman r |", "|---|---|---|---|---|"]

    def add(col: str, mask: pd.Series, label: str) -> None:
        d = m.loc[mask, [col, "price_de_eur_mwh"]].dropna()
        if len(d) < 100:
            return
        p = d[col].corr(d["price_de_eur_mwh"])
        s = d[col].corr(d["price_de_eur_mwh"], method="spearman")
        out.append(f"| {col} | {len(d):,} | {label} | {p:.3f} | {s:.3f} |")

    add("wind_cubed_de_mean_safe", y24, "all hours 2024-2026")
    add("wind_cubed_de_mean_jma_safe", y24, "all hours 2024-2026")
    add("wind_cubed_de_mean_jma_safe", m["timestamp_utc"].notna(), "all hours 2019-2026")
    add("radiation_wm2_de_mean_safe", y24 & mid, "local 11-14 h, 2024-2026")
    add("radiation_wm2_de_mean_safe", y24, "all hours 2024-2026")
    add("temp_c_fr_mean_safe", y24, "all hours 2024-2026 (FR price: see note)")
    return out


def write_check(safe: pd.DataFrame, raw: pd.DataFrame) -> list[str]:
    CHECK_FILE.parent.mkdir(parents=True, exist_ok=True)
    local_hour = safe["timestamp_utc"].dt.tz_convert("Europe/Zurich").dt.hour
    lines = [
        "# Data check: weather_europe_forecast_hourly (Open-Meteo previous-runs API, 9 European points)",
        "",
        f"- Rows: {len(safe):,}; timestamp_utc {safe['timestamp_utc'].min()} -> {safe['timestamp_utc'].max()} "
        "(complete hourly grid, START of hour, UTC)",
        f"- Duplicates removed: {raw.attrs.get('dups', 0)}",
        "- `<var>_<point>_safe` = icon_seamless; `<var>_<point>_jma_safe` = jma_seamless (10 m wind, no radiation).",
        "- Lead rule, time shift (Open-Meteo stamp -1 h), cadence/delay reused from src/data/load_openmeteo_forecast.py.",
    ]
    for suffix, name in (("", "ICON"), ("_jma", "JMA")):
        lead = raw[f"safe_lead_days{suffix}"]
        hrs = sorted(local_hour[lead == 1].unique().tolist())
        lines.append(f"- {name}: day1 used for delivery-day local hours {hrs}, day2 otherwise "
                     f"(day1 share {(lead == 1).mean():.1%}).")
    lines += ["", "## Coverage and NaN per column", "",
              "| column | first valid (UTC) | last valid (UTC) | NaN after first valid | min | max |",
              "|---|---|---|---|---|---|"]
    for c in safe.columns[1:]:
        s = safe.set_index("timestamp_utc")[c]
        first, last = s.first_valid_index(), s.last_valid_index()
        nan = s.loc[first:].isna().mean() if first is not None else 1.0
        lines.append(f"| {c} | {first} | {last} | {nan:.3%} | {s.min():.1f} | {s.max():.1f} |")
    corr = correlations(safe)
    lines += ["", "## Sanity check: correlation with the DE day-ahead price (`price_neighbours_hourly.price_de_eur_mwh`)",
              "", *corr, "",
              "Expected: wind and midday radiation negative (more renewables -> lower price). Temperature in France "
              "is listed for information only; its effect on the DE price is non-linear (cold -> high price)."]
    CHECK_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return corr


def main(skip_download: bool = False, force: bool = False) -> pd.DataFrame:
    """Build data/processed/weather_europe_forecast_hourly.parquet (+ raw day1/day2 file)."""
    if not skip_download:
        download(force=force)
    parts = [read_model(m) for m in MODELS]
    df = pd.concat(parts, axis=1, sort=True)
    end = pd.Timestamp(END_DATE, tz="UTC") + pd.Timedelta(hours=22)  # last full Open-Meteo day, shifted -1 h
    grid = pd.date_range(START, end, freq="h", tz="UTC", name="timestamp_utc")
    dups = int(df.index.duplicated().sum())
    raw = df.reindex(grid).reset_index()
    raw["timestamp_utc"] = raw["timestamp_utc"].astype("datetime64[ns, UTC]")
    raw.attrs["dups"] = dups
    safe, raw = build_safe(raw)
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    safe.to_parquet(OUT_FILE, index=False)
    raw.to_parquet(RAW_OUT_FILE, index=False)
    corr = write_check(safe, raw)
    print(f"wrote {OUT_FILE} ({len(safe):,} rows, {safe['timestamp_utc'].min()} -> {safe['timestamp_utc'].max()})")
    print("\n".join(corr))
    return safe


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--skip-download", action="store_true", help="rebuild from cached raw files only")
    ap.add_argument("--force", action="store_true", help="re-download even if raw files exist")
    a = ap.parse_args()
    main(skip_download=a.skip_download, force=a.force)
