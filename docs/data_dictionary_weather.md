# Data dictionary – weather (agent D2)

All files: one row per UTC hour, `timestamp_utc` = tz-aware UTC, **START** of the hour the value describes.
Built by `src/data/load_meteoswiss.py`, `src/data/load_openmeteo_forecast.py`, `src/data/load_openmeteo_archive.py`
(bias correction in `src/data/check_weather_forecast.py`).

## `data/processed/weather_observed_hourly.parquet` (MeteoSwiss SMA Zürich-Fluntern, 2018-12-01 → 2026-11-18)

| column | unit | source | time convention | publication lag |
|---|---|---|---|---|
| timestamp_utc | UTC | – | start of hour (MeteoSwiss stamp = end of hour, shifted −1 h) | – |
| temp_c | °C | MeteoSwiss `tre200h0` (air temp 2 m, hourly mean) | mean over the hour | ~1 h ("now" files); "recent" file updated daily → treat as known up to end of D−1 |
| sunshine_min | min | `sre000h0` (sunshine duration, hourly sum) | sum over the hour | as above |
| radiation_wm2 | W/m² | `gre000h0` (global radiation, hourly mean) | mean over the hour | as above |
| wind_ms | m/s | `fkl010h0` (wind speed scalar, hourly mean) | mean over the hour | as above |
| precip_mm | mm | `rre150h0` (precipitation, hourly sum) | sum over the hour | as above |
| humidity_pct | % | `ure200h0` (relative humidity 2 m, hourly mean) | mean over the hour | as above |
| `<col>_interpolated` | bool | derived | True if the value was filled by linear interpolation (gap ≤ 3 h) | – |

## `data/processed/weather_forecast_hourly.parquet` (Open-Meteo previous-runs API, 2018-12-01 → 2026-11-03 22:00)

Base names: `temp_c` (°C), `radiation_wm2` (W/m², shortwave), `sunshine_min` (min, from seconds),
`wind_ms` (m/s at 10 m, from km/h), `precip_mm` (mm), `cloud_pct` (% total cloud cover), `humidity_pct` (% at 2 m).
Open-Meteo stamp −1 h → row T holds the Open-Meteo value stamped T+1 h: instantaneous variables (temp, wind,
cloud, humidity) are the value at the END of hour T; radiation/sunshine/precip are the mean/sum over hour T.

| column pattern | model | meaning | real data from (timestamp_utc) | publication lag |
|---|---|---|---|---|
| `<base>_fc_day0` | icon_seamless | current (latest) run – **not** available at forecast time, comparison only | 2023-12-31 | – |
| `<base>_fc_day1` | icon_seamless | value predicted ≥24 h before the Open-Meteo valid time (latest run ≤ valid−24 h) | 2024-01-19 | run + 4 h (assumed) |
| `<base>_fc_day2` | icon_seamless | same, ≥48 h before | 2024-01-20 | run + 4 h |
| `<base>_fc_safe` | icon_seamless | **use this**: day1 if published before D 10:00 local, else day2 | 2024-01-19 23:00 (= delivery day 2024-01-20) | ≤ D 10:00 Europe/Zurich by construction |
| `fc_safe_lead_days` | icon_seamless | 1 or 2 = lead used in `*_fc_safe` | – | – |
| `temp_c_fc_safe_corr` | icon_seamless | `temp_c_fc_safe` + mean(obs − fc) per (month, local hour), fitted before 2026-09-01 | 2024-01-19 23:00 | as `_fc_safe` |
| `<base>_fc_day0/1/2_ecmwf`, `<base>_fc_safe_ecmwf`, `fc_safe_lead_days_ecmwf` | ecmwf_ifs025 | same logic, ECMWF IFS 0.25° | temp 2024-02-03, radiation/sunshine 2024-03-06, humidity 2024-02-29 | run + 8 h |
| `<base>_fc_day0/1/2_jma`, `<base>_fc_safe_jma`, `fc_safe_lead_days_jma` | jma_seamless (JMA GSM) | same logic; only temp, wind, precip, cloud, humidity (no radiation/sunshine) | 2018-12-01 (full period) | run + 6 h |
| `temp_c_fc_safe_jma_corr` | jma_seamless | bias-corrected JMA safe temperature (same method) | 2018-12-01 | as `_fc_safe_jma` |

## `data/processed/weather_archive_hourly.parquet` (Open-Meteo archive, ERA5, 2018-12-01 → 2026-11-03 22:00)

| column | unit | source | time convention | publication lag |
|---|---|---|---|---|
| temp_c_era5, radiation_wm2_era5, sunshine_min_era5, wind_ms_era5, precip_mm_era5, cloud_pct_era5, humidity_pct_era5 | as above | Open-Meteo archive API, `models=era5`, 47.378 N 8.565 E | as forecast file (stamp −1 h) | ~5 days; reanalysis → **never a D+1 input**, cross-check / gap filler only |
