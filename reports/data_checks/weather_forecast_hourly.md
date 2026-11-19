# Data check: weather_forecast_hourly (Open-Meteo previous-runs API)

- Rows: 69,479; timestamp_utc 2018-12-01 00:00:00+00:00 -> 2026-11-03 22:00:00+00:00 (hourly grid)
- Main columns (no suffix) = `icon_seamless`; `_ecmwf` = `ecmwf_ifs025`; `_jma` = `jma_seamless` (JMA GSM).
- Time shift: Open-Meteo stamp -1 h -> timestamp_utc = START of hour.
- Units converted: sunshine s -> min, wind km/h -> m/s.
- `*_fc_safe` (icon) uses day1 for delivery-day local hours [0, 1, 2, 3, 4, 5, 6] (share per hour: 0: 1.00, 1: 1.00, 2: 1.00, 3: 1.00, 4: 1.00, 5: 1.00, 6: 0.59), day2 otherwise.

## First non-null value and missing share after it, per column

| column | first valid (UTC, start of hour) | missing after first |
|---|---|---|
| temp_c_fc_day0 | 2023-12-31 23:00:00+00:00 | 0.000% |
| temp_c_fc_day1 | 2024-01-19 11:00:00+00:00 | 0.000% |
| temp_c_fc_day2 | 2024-01-20 11:00:00+00:00 | 0.000% |
| radiation_wm2_fc_day0 | 2023-12-31 23:00:00+00:00 | 0.000% |
| radiation_wm2_fc_day1 | 2024-01-19 11:00:00+00:00 | 0.000% |
| radiation_wm2_fc_day2 | 2024-01-20 11:00:00+00:00 | 0.143% |
| sunshine_min_fc_day0 | 2023-12-31 23:00:00+00:00 | 0.000% |
| sunshine_min_fc_day1 | 2024-01-19 11:00:00+00:00 | 0.000% |
| sunshine_min_fc_day2 | 2024-01-20 11:00:00+00:00 | 0.000% |
| wind_ms_fc_day0 | 2023-12-31 23:00:00+00:00 | 0.000% |
| wind_ms_fc_day1 | 2024-01-19 11:00:00+00:00 | 0.000% |
| wind_ms_fc_day2 | 2024-01-20 11:00:00+00:00 | 0.000% |
| precip_mm_fc_day0 | 2023-12-31 23:00:00+00:00 | 0.000% |
| precip_mm_fc_day1 | 2024-01-19 11:00:00+00:00 | 0.000% |
| precip_mm_fc_day2 | 2024-01-20 11:00:00+00:00 | 0.000% |
| cloud_pct_fc_day0 | 2023-12-31 23:00:00+00:00 | 0.000% |
| cloud_pct_fc_day1 | 2024-01-19 11:00:00+00:00 | 0.000% |
| cloud_pct_fc_day2 | 2024-01-20 11:00:00+00:00 | 0.143% |
| humidity_pct_fc_day0 | 2023-12-31 23:00:00+00:00 | 0.000% |
| humidity_pct_fc_day1 | 2024-01-19 11:00:00+00:00 | 0.000% |
| humidity_pct_fc_day2 | 2024-01-20 11:00:00+00:00 | 0.000% |
| temp_c_fc_day0_ecmwf | 2024-02-02 23:00:00+00:00 | 0.000% |
| temp_c_fc_day1_ecmwf | 2024-02-03 23:00:00+00:00 | 0.000% |
| temp_c_fc_day2_ecmwf | 2024-02-04 23:00:00+00:00 | 0.000% |
| radiation_wm2_fc_day0_ecmwf | 2024-03-05 07:00:00+00:00 | 0.000% |
| radiation_wm2_fc_day1_ecmwf | 2024-03-06 16:00:00+00:00 | 0.000% |
| radiation_wm2_fc_day2_ecmwf | 2024-03-07 16:00:00+00:00 | 0.000% |
| sunshine_min_fc_day0_ecmwf | 2024-03-05 07:00:00+00:00 | 0.000% |
| sunshine_min_fc_day1_ecmwf | 2024-03-06 16:00:00+00:00 | 0.000% |
| sunshine_min_fc_day2_ecmwf | 2024-03-07 16:00:00+00:00 | 0.000% |
| wind_ms_fc_day0_ecmwf | 2024-02-02 23:00:00+00:00 | 0.000% |
| wind_ms_fc_day1_ecmwf | 2024-02-03 23:00:00+00:00 | 0.000% |
| wind_ms_fc_day2_ecmwf | 2024-02-04 23:00:00+00:00 | 0.000% |
| precip_mm_fc_day0_ecmwf | 2024-02-02 21:00:00+00:00 | 1.007% |
| precip_mm_fc_day1_ecmwf | 2024-02-03 21:00:00+00:00 | 0.000% |
| precip_mm_fc_day2_ecmwf | 2024-02-04 21:00:00+00:00 | 0.000% |
| cloud_pct_fc_day0_ecmwf | 2024-02-02 23:00:00+00:00 | 0.000% |
| cloud_pct_fc_day1_ecmwf | 2024-02-03 23:00:00+00:00 | 0.000% |
| cloud_pct_fc_day2_ecmwf | 2024-02-04 23:00:00+00:00 | 0.536% |
| humidity_pct_fc_day0_ecmwf | 2024-02-28 17:00:00+00:00 | 0.000% |
| humidity_pct_fc_day1_ecmwf | 2024-02-29 17:00:00+00:00 | 0.549% |
| humidity_pct_fc_day2_ecmwf | 2024-03-01 17:00:00+00:00 | 0.000% |
| temp_c_fc_day0_jma | 2018-12-01 00:00:00+00:00 | 0.000% |
| temp_c_fc_day1_jma | 2018-12-01 00:00:00+00:00 | 0.000% |
| temp_c_fc_day2_jma | 2018-12-01 00:00:00+00:00 | 0.000% |
| wind_ms_fc_day0_jma | 2018-12-01 00:00:00+00:00 | 0.000% |
| wind_ms_fc_day1_jma | 2018-12-01 00:00:00+00:00 | 0.000% |
| wind_ms_fc_day2_jma | 2018-12-01 00:00:00+00:00 | 0.000% |
| precip_mm_fc_day0_jma | 2018-12-01 00:00:00+00:00 | 0.000% |
| precip_mm_fc_day1_jma | 2018-12-01 00:00:00+00:00 | 0.000% |
| precip_mm_fc_day2_jma | 2018-12-01 00:00:00+00:00 | 0.458% |
| cloud_pct_fc_day0_jma | 2018-12-01 00:00:00+00:00 | 0.000% |
| cloud_pct_fc_day1_jma | 2018-12-01 00:00:00+00:00 | 0.458% |
| cloud_pct_fc_day2_jma | 2018-12-01 00:00:00+00:00 | 0.000% |
| humidity_pct_fc_day0_jma | 2018-12-01 00:00:00+00:00 | 0.000% |
| humidity_pct_fc_day1_jma | 2018-12-01 00:00:00+00:00 | 0.458% |
| humidity_pct_fc_day2_jma | 2018-12-01 00:00:00+00:00 | 0.000% |
