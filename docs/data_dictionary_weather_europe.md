# Data dictionary – European weather forecasts (agent D5)

Built by `src/data/load_openmeteo_europe.py` from the Open-Meteo previous-runs API
(`https://previous-runs-api.open-meteo.com/v1/forecast`), raw JSON in `data/raw/openmeteo_europe/`.
One row per UTC hour, 2018-12-01 00:00 → 2026-11-03 22:00 UTC, complete hourly grid.
`timestamp_utc` = tz-aware UTC, **START** of the hour (Open-Meteo stamp −1 h, as in D2's Zurich file): temperature and
wind are the value at the END of hour T, radiation and precipitation are the mean/sum over hour T.

Points: `de_north` 53.9/8.9, `de_northeast` 53.4/12.5, `de_central` 51.3/9.5, `de_south` 48.6/11.5,
`fr_paris` 48.85/2.35, `fr_lyon` 45.76/4.84, `it_milan` 45.46/9.19, `ch_alps` 46.5/8.3, `ch_bern` 46.95/7.45.

All `*_safe` columns are leakage-safe for a forecast made at day D 10:00 Europe/Zurich for local delivery day D+1
(day1 lead if its run was published by then, else day2; rule in `docs/assumptions_weather.md`).
Publication lag: ≤ D 10:00 Europe/Zurich by construction (ICON run + 4 h, JMA run + 6 h).

## `data/processed/weather_europe_forecast_hourly.parquet`

| column | unit | source / model | points | time convention | real data from |
|---|---|---|---|---|---|
| timestamp_utc | UTC | – | – | start of hour | – |
| `temp_c_<point>_safe` | °C | `temperature_2m`, icon_seamless | all 9 | instant, end of hour | 2024-01-19 23:00 |
| `radiation_wm2_<point>_safe` | W/m² | `shortwave_radiation`, icon_seamless | DE ×4, it_milan, ch_alps, ch_bern | mean over hour | 2024-01-19 23:00 |
| `wind100_ms_<point>_safe` | m/s (from km/h) | `wind_speed_100m`, icon_seamless | de_north, de_northeast, de_central | instant, end of hour | 2024-02-16 23:00 |
| `wind_cubed_<point>_safe` | (m/s)³ | derived: min(wind100, 25)³ | same 3 | as wind | 2024-02-16 23:00 |
| `precip_mm_ch_alps_safe` | mm | `precipitation`, icon_seamless | ch_alps | sum over hour | 2024-01-19 23:00 |
| `wind_cubed_de_mean_safe` | (m/s)³ | mean of the 3 `wind_cubed_*_safe` | – | as wind | 2024-02-16 23:00 |
| `radiation_wm2_de_mean_safe` | W/m² | mean of the 4 DE radiation columns | – | mean over hour | 2024-01-19 23:00 |
| `temp_c_fr_mean_safe` | °C | mean of fr_paris, fr_lyon | – | instant | 2024-01-19 23:00 |
| `temp_c_<point>_jma_safe` | °C | `temperature_2m`, jma_seamless (JMA GSM) | all 9 | instant | 2018-12-01 |
| `wind10_ms_<point>_jma_safe` | m/s (from km/h) | `wind_speed_10m`, jma_seamless (no 100 m in JMA) | 3 wind points | instant | 2018-12-01 |
| `wind_cubed_<point>_jma_safe` | (m/s)³ | min(wind10, 25)³ | 3 wind points | instant | 2018-12-01 |
| `precip_mm_ch_alps_jma_safe` | mm | `precipitation`, jma_seamless | ch_alps | sum over hour | 2018-12-01 |
| `wind_cubed_de_mean_jma_safe` | (m/s)³ | mean of 3 JMA wind_cubed | – | instant | 2018-12-01 |
| `temp_c_fr_mean_jma_safe` | °C | mean of 2 JMA FR temps | – | instant | 2018-12-01 |

No JMA radiation (not in the JMA archive). Note: 10 m JMA wind is much lower than 100 m ICON wind; do not mix them
in one feature without rescaling. Exact first valid timestamps and NaN shares: `reports/data_checks/weather_europe_forecast_hourly.md`.

## `data/processed/weather_europe_forecast_raw_hourly.parquet` (checks only, NOT a model input)

| column | meaning |
|---|---|
| timestamp_utc | as above |
| `<base>_<point>_day1[_jma]`, `<base>_<point>_day2[_jma]` | Open-Meteo `_previous_day1/2` values (converted units) |
| `safe_lead_days`, `safe_lead_days_jma` | lead (1 or 2) picked for `*_safe` (ICON, JMA) |
