# Assumptions – European weather forecasts (agent D5)

## Reuse of D2's conventions
- All time and leakage rules are imported from `src/data/load_openmeteo_forecast.py` (`safe_lead_days`, `START`, `END_DATE`, `URL`, `get_json`, model cadence/delay), so Zurich and European weather follow exactly the same rule. Reason: one rule, one place to explain it.
- Open-Meteo stamp −1 h → `timestamp_utc` = START of hour (instantaneous temp/wind = value at end of the hour; radiation/precip = mean/sum over the hour). Reason: same as D2, matches the price file convention.
- Leakage-safe lead: per row, day1 only if `floor(valid − 24 h, cadence) + delay ≤ D 10:00 Europe/Zurich`, else day2 (see `docs/assumptions_weather.md`). ICON cadence 3 h / delay 4 h, JMA 6 h / 6 h. Result: day1 only for delivery-day local hours 00–05/06, day2 otherwise. Reason: forecast time D 10:00 for delivery day D+1.
- Assumption (as D2): archived previous-runs values equal what was available in real time. Reason: cannot be verified retroactively.

## Points and variables
- Point coordinates are the ones given in the task (North Sea coast, NE Germany, central Germany, Bavaria, Paris, Lyon, Milan, central Swiss Alps, Bern). Open-Meteo snaps each point to the nearest model grid cell (JMA ~0.5°, e.g. 53.9/8.9 → 54.0/9.0). Reason: a few representative points per driver is enough for a university model; a full grid would be overkill.
- ICON wind uses `wind_speed_100m` (available in previous-runs for `icon_seamless`), JMA uses `wind_speed_10m` (JMA has no 100 m wind). Reason: 100 m ≈ hub height; 10 m is the only JMA option.
- `wind_cubed = min(speed_ms, 25)^3`. Reason: wind power ∝ v³ below rated speed; capping at 25 m/s (typical cut-out) limits the effect of storms.
- Radiation only for DE/CH/IT points, temperature for all points, precipitation only for `ch_alps` (ICON and JMA). JMA has no radiation. Reason: task scope; French solar is small relative to French temperature effect.
- Regional means (`*_de_mean_*`, `*_fr_mean_*`) are plain unweighted means and are NaN if any member point is NaN. Reason: simple and transparent; the mean never silently changes composition. `radiation_wm2_de_mean_safe` averages all 4 DE points (incl. de_south), `wind_cubed_de_mean_*` the 3 wind points.
- The mean of cubes (not the cube of the mean) is used for `wind_cubed_de_mean_*`. Reason: approximates total wind power across sites.

## Download
- One multi-location call per model and calendar year (all 9 points in one request), only `_previous_day1` and `_previous_day2` (day0 is never usable), 60 s pause between calls, exponential backoff on 429/5xx (D2's `get_json`). Raw JSON cached in `data/raw/openmeteo_europe/<model>_<year>.json`. Reason: keeps the free-tier weight per minute/hour low.
- ICON is fetched from 2024 (no real previous-runs data before 2024-01); JMA from 2018-11-30. The processed file spans 2018-12-01 00:00 → 2026-11-03 22:00 UTC; ICON columns are NaN before their first real value. Reason: same grid as D2's Zurich file.

## Sanity check
- Correlations with the DE day-ahead price (`price_neighbours_hourly.price_de_eur_mwh`) are reported in `reports/data_checks/weather_europe_forecast_hourly.md`; a test requires wind_cubed (ICON, 2024–2026) r < −0.1 and midday radiation r < 0. Reason: catches unit or shift errors cheaply.

## Gaps and quirks found in the data
- ICON day1 values start 2024-01-19 (first safe row 2024-01-19 23:00 UTC = delivery day 2024-01-20), but `wind_speed_100m` only starts 2024-02-16 (first safe row 2024-02-16 23:00 UTC). Reason: that is when the variable enters the archive; earlier rows stay NaN (use the JMA wind there).
- ICON radiation is NaN for 23 h (2026-04-10 05:00 → 2026-04-11 10:00 UTC) at all points, the same archive gap D2 found for Zurich. Reason: missing upstream; left NaN, not filled.
- JMA precipitation (`precip_mm_ch_alps_jma_safe`) is NaN for 227 h between 2026-04-13 12:00 and 2026-04-26 17:00 UTC (about 17 h a day). Reason: missing upstream; left NaN.
- 12 JMA precipitation values were −0.1 mm; all precipitation is clipped at 0. Reason: a negative rain amount is physically impossible (rounding artefact).
- The previous-runs API was down for about 45 min during the first download (HTTP 504); `fetch()` retries with long pauses on timeouts as well as 429/5xx. Reason: D2's `get_json` does not catch timeouts.
