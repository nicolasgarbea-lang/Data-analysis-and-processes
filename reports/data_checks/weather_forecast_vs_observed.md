# Weather check: forecast vs observed (MeteoSwiss SMA Zürich-Fluntern)

Error = forecast - observed, hourly, timestamp_utc = start of hour. Period up to 2026-10-31.
Main forecast = Open-Meteo `icon_seamless`; `_ecmwf` = ecmwf_ifs025; `_jma` = JMA GSM (coarse, long history).
`*_fc_safe` = freshest lead issued before D 10:00 Europe/Zurich (see docs/assumptions_weather.md).
`*_corr` = bias-corrected (offset per month x local hour, fitted on hours before 2026-09-01);
whole-period `_corr` numbers are therefore partly in-sample, the honest test is the last table and Oct 2026.

## Temperature, whole period (°C)

| column | from | n_hours | MAE | bias | corr |
|---|---|---|---|---|---|
| temp_c_fc_day0 | 2023-12-31 | 24840 | 0.68 | 0.11 | 0.99 |
| temp_c_fc_day1 | 2024-01-19 | 24396 | 1.01 | 0.28 | 0.99 |
| temp_c_fc_day2 | 2024-01-20 | 24372 | 1.20 | -0.33 | 0.98 |
| temp_c_fc_safe | 2024-01-19 | 24378 | 1.10 | -0.13 | 0.98 |
| temp_c_fc_safe_corr | 2024-01-19 | 24378 | 1.04 | 0.01 | 0.98 |
| temp_c_fc_safe_ecmwf | 2024-02-03 | 24006 | 1.82 | -1.18 | 0.97 |
| temp_c_fc_day1_jma | 2018-12-01 | 69374 | 1.94 | -1.36 | 0.96 |
| temp_c_fc_day2_jma | 2018-12-01 | 69374 | 2.02 | -1.41 | 0.96 |
| temp_c_fc_safe_jma | 2018-12-01 | 69374 | 2.00 | -1.39 | 0.96 |
| temp_c_fc_safe_jma_corr | 2018-12-01 | 69374 | 1.52 | -0.00 | 0.97 |
| temp_c_era5 | 2018-12-01 | 69374 | 1.04 | -0.26 | 0.99 |

## Temperature, test month October 2026 (°C)

| column | from | n_hours | MAE | bias | corr |
|---|---|---|---|---|---|
| temp_c_fc_day0 | 2026-09-30 | 745 | 0.72 | 0.37 | 0.98 |
| temp_c_fc_day1 | 2026-09-30 | 745 | 1.01 | 0.60 | 0.96 |
| temp_c_fc_day2 | 2026-09-30 | 745 | 1.01 | 0.00 | 0.95 |
| temp_c_fc_safe | 2026-09-30 | 745 | 0.95 | 0.23 | 0.96 |
| temp_c_fc_safe_corr | 2026-09-30 | 745 | 0.96 | 0.18 | 0.96 |
| temp_c_fc_safe_ecmwf | 2026-09-30 | 745 | 1.62 | -1.15 | 0.92 |
| temp_c_fc_day1_jma | 2026-09-30 | 745 | 1.61 | -0.85 | 0.90 |
| temp_c_fc_day2_jma | 2026-09-30 | 745 | 1.64 | -1.06 | 0.90 |
| temp_c_fc_safe_jma | 2026-09-30 | 745 | 1.60 | -0.98 | 0.90 |
| temp_c_fc_safe_jma_corr | 2026-09-30 | 745 | 1.50 | 0.28 | 0.90 |
| temp_c_era5 | 2026-09-30 | 745 | 1.17 | -0.16 | 0.94 |

## Radiation, whole period (W/m²)

| column | from | n_hours | MAE | bias | corr |
|---|---|---|---|---|---|
| radiation_wm2_fc_day0 | 2023-12-31 | 24840 | 28.1 | -2.9 | 1.0 |
| radiation_wm2_fc_day1 | 2024-01-19 | 24396 | 34.8 | -3.5 | 1.0 |
| radiation_wm2_fc_day2 | 2024-01-20 | 24337 | 37.7 | -6.7 | 0.9 |
| radiation_wm2_fc_safe | 2024-01-19 | 24355 | 37.7 | -6.7 | 0.9 |
| radiation_wm2_fc_safe_ecmwf | 2024-03-06 | 23245 | 39.3 | 11.8 | 0.9 |
| radiation_wm2_era5 | 2018-12-01 | 69407 | 34.5 | 3.8 | 0.9 |

## Radiation, October 2026 (W/m²)

| column | from | n_hours | MAE | bias | corr |
|---|---|---|---|---|---|
| radiation_wm2_fc_day0 | 2026-09-30 | 745 | 18.5 | -2.2 | 1.0 |
| radiation_wm2_fc_day1 | 2026-09-30 | 745 | 26.3 | -5.6 | 0.9 |
| radiation_wm2_fc_day2 | 2026-09-30 | 745 | 31.5 | -8.4 | 0.9 |
| radiation_wm2_fc_safe | 2026-09-30 | 745 | 31.5 | -8.4 | 0.9 |
| radiation_wm2_fc_safe_ecmwf | 2026-09-30 | 745 | 33.3 | 4.4 | 0.9 |
| radiation_wm2_era5 | 2026-09-30 | 745 | 25.7 | 0.3 | 0.9 |

## Other variables (safe ICON forecast and ERA5), whole period

| column | n_hours | MAE | bias | corr |
|---|---|---|---|---|
| sunshine_min_fc_safe vs sunshine_min | 24378 | 7.58 | 5.22 | 0.77 |
| wind_ms_fc_safe vs wind_ms | 24371 | 0.79 | -0.31 | 0.69 |
| precip_mm_fc_safe vs precip_mm | 24378 | 0.15 | 0.00 | 0.32 |
| humidity_pct_fc_safe vs humidity_pct | 24378 | 7.55 | 0.06 | 0.85 |
| sunshine_min_era5 vs sunshine_min | 69407 | 9.73 | 9.20 | 0.74 |
| wind_ms_era5 vs wind_ms | 69400 | 0.73 | -0.21 | 0.79 |

## Temperature (ICON) by year

| year | temp_c_fc_day1 MAE | temp_c_fc_day1 bias | temp_c_fc_day2 MAE | temp_c_fc_day2 bias | temp_c_fc_safe MAE | temp_c_fc_safe bias | temp_c_fc_safe_corr MAE | temp_c_fc_safe_corr bias | n_hours |
|---|---|---|---|---|---|---|---|---|---|
| 2024 | 1.03 | 0.15 | 1.16 | -0.28 | 1.09 | -0.19 | 1.03 | -0.07 | 8316 |
| 2025 | 1.02 | 0.31 | 1.21 | -0.38 | 1.11 | -0.14 | 1.05 | 0.02 | 8760 |
| 2026 | 0.99 | 0.40 | 1.24 | -0.31 | 1.10 | -0.03 | 1.03 | 0.08 | 7296 |

## Temperature (ICON) by calendar month

| month | temp_c_fc_day1 MAE | temp_c_fc_day1 bias | temp_c_fc_day2 MAE | temp_c_fc_day2 bias | temp_c_fc_safe MAE | temp_c_fc_safe bias | temp_c_fc_safe_corr MAE | temp_c_fc_safe_corr bias | n_hours |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 1.08 | -0.37 | 1.48 | -1.03 | 1.40 | -0.87 | 1.22 | -0.01 | 1764 |
| 2 | 0.97 | 0.01 | 1.25 | -0.66 | 1.15 | -0.50 | 1.04 | -0.00 | 2040 |
| 3 | 0.99 | -0.06 | 1.40 | -0.79 | 1.25 | -0.54 | 1.15 | 0.00 | 2229 |
| 4 | 0.90 | 0.26 | 1.22 | -0.45 | 1.05 | -0.21 | 0.99 | 0.00 | 2160 |
| 5 | 0.93 | 0.55 | 1.08 | -0.08 | 0.95 | 0.18 | 0.91 | 0.00 | 2232 |
| 6 | 1.16 | 0.61 | 1.25 | -0.12 | 1.15 | 0.17 | 1.12 | -0.00 | 2160 |
| 7 | 1.17 | 0.60 | 1.27 | -0.01 | 1.17 | 0.22 | 1.11 | -0.00 | 2232 |
| 8 | 1.09 | 0.60 | 1.18 | -0.01 | 1.09 | 0.22 | 1.04 | 0.00 | 2232 |
| 9 | 0.91 | 0.44 | 0.98 | -0.07 | 0.89 | 0.10 | 0.86 | 0.01 | 2160 |
| 10 | 0.98 | 0.35 | 1.01 | -0.00 | 0.96 | 0.11 | 0.93 | 0.06 | 2235 |
| 11 | 1.03 | -0.07 | 1.27 | -0.47 | 1.20 | -0.40 | 1.16 | 0.00 | 1440 |
| 12 | 0.95 | 0.10 | 1.08 | -0.50 | 1.04 | -0.35 | 0.97 | 0.00 | 1488 |

## Temperature (JMA, long history) by year

| year | temp_c_fc_day1_jma MAE | temp_c_fc_day1_jma bias | temp_c_fc_day2_jma MAE | temp_c_fc_day2_jma bias | temp_c_fc_safe_jma MAE | temp_c_fc_safe_jma bias | temp_c_fc_safe_jma_corr MAE | temp_c_fc_safe_jma_corr bias | n_hours |
|---|---|---|---|---|---|---|---|---|---|
| 2018 | 1.27 | -0.83 | 1.16 | -0.68 | 1.19 | -0.70 | 1.21 | 0.71 | 743 |
| 2019 | 2.17 | -1.72 | 2.24 | -1.75 | 2.23 | -1.75 | 1.56 | -0.35 | 8760 |
| 2020 | 2.35 | -1.89 | 2.39 | -1.94 | 2.39 | -1.93 | 1.62 | -0.54 | 8784 |
| 2021 | 2.19 | -1.64 | 2.29 | -1.69 | 2.26 | -1.67 | 1.65 | -0.28 | 8727 |
| 2022 | 1.90 | -1.32 | 2.04 | -1.42 | 2.01 | -1.39 | 1.44 | -0.00 | 8760 |
| 2023 | 1.74 | -1.12 | 1.79 | -1.12 | 1.78 | -1.13 | 1.43 | 0.27 | 8760 |
| 2024 | 1.68 | -0.86 | 1.78 | -0.91 | 1.76 | -0.89 | 1.50 | 0.50 | 8784 |
| 2025 | 1.67 | -1.11 | 1.75 | -1.12 | 1.74 | -1.10 | 1.48 | 0.29 | 8760 |
| 2026 | 1.83 | -1.28 | 1.94 | -1.37 | 1.91 | -1.34 | 1.47 | 0.06 | 7296 |

## Radiation (ICON) by year

| year | radiation_wm2_fc_day1 MAE | radiation_wm2_fc_day1 bias | radiation_wm2_fc_day2 MAE | radiation_wm2_fc_day2 bias | radiation_wm2_fc_safe MAE | radiation_wm2_fc_safe bias | n_hours |
|---|---|---|---|---|---|---|---|
| 2024 | 37.2 | -0.7 | 39.0 | -3.5 | 39.0 | -3.4 | 8316 |
| 2025 | 33.8 | -3.4 | 36.4 | -6.6 | 36.4 | -6.6 | 8760 |
| 2026 | 33.2 | -7.1 | 37.9 | -10.6 | 37.9 | -10.5 | 7261 |

## Radiation (ICON) by calendar month

| month | radiation_wm2_fc_day1 MAE | radiation_wm2_fc_day1 bias | radiation_wm2_fc_day2 MAE | radiation_wm2_fc_day2 bias | radiation_wm2_fc_safe MAE | radiation_wm2_fc_safe bias | n_hours |
|---|---|---|---|---|---|---|---|
| 1 | 17.1 | 0.3 | 18.0 | -3.3 | 18.0 | -3.3 | 1764 |
| 2 | 23.9 | 5.1 | 25.3 | 1.8 | 25.3 | 1.8 | 2040 |
| 3 | 31.7 | 5.4 | 35.1 | 5.5 | 35.1 | 5.5 | 2229 |
| 4 | 37.1 | 2.1 | 41.4 | -3.8 | 41.4 | -3.8 | 2125 |
| 5 | 48.9 | -11.3 | 52.7 | -9.2 | 52.7 | -9.1 | 2232 |
| 6 | 53.9 | -15.1 | 59.7 | -21.9 | 59.6 | -21.8 | 2160 |
| 7 | 52.4 | -14.3 | 55.5 | -18.3 | 55.5 | -18.2 | 2232 |
| 8 | 38.3 | -14.2 | 43.7 | -15.5 | 43.7 | -15.5 | 2232 |
| 9 | 32.5 | -9.8 | 35.5 | -14.8 | 35.5 | -14.8 | 2160 |
| 10 | 29.9 | 2.1 | 32.0 | -1.1 | 32.0 | -1.1 | 2235 |
| 11 | 19.0 | 6.7 | 20.2 | 2.8 | 20.2 | 2.8 | 1440 |
| 12 | 17.4 | 9.2 | 16.0 | 5.3 | 16.0 | 5.3 | 1488 |

## Station (SMA, 556 m) vs Open-Meteo grid point (47.378 N, 8.565 E, 557 m)

Mean offset grid - station by calendar month (°C). `day0` = current run (shortest lead).

| month | temp_c_fc_day0 bias | temp_c_fc_day0 corr | temp_c_era5 bias | temp_c_era5 corr | temp_c_fc_day0_jma bias | temp_c_fc_day0_jma corr |
|---|---|---|---|---|---|---|
| 1 | -0.37 | 0.97 | -0.38 | 0.95 | -1.32 | 0.84 |
| 2 | -0.09 | 0.98 | -0.36 | 0.96 | -1.81 | 0.85 |
| 3 | -0.14 | 0.98 | -0.51 | 0.95 | -1.54 | 0.89 |
| 4 | 0.04 | 0.99 | -0.38 | 0.97 | -1.25 | 0.91 |
| 5 | 0.33 | 0.99 | -0.11 | 0.97 | -0.57 | 0.95 |
| 6 | 0.47 | 0.99 | -0.09 | 0.97 | -0.96 | 0.94 |
| 7 | 0.46 | 0.98 | -0.00 | 0.95 | -1.31 | 0.91 |
| 8 | 0.50 | 0.99 | -0.10 | 0.96 | -1.60 | 0.93 |
| 9 | 0.21 | 0.99 | -0.36 | 0.96 | -1.70 | 0.92 |
| 10 | 0.17 | 0.97 | -0.30 | 0.95 | -1.28 | 0.87 |
| 11 | -0.38 | 0.97 | -0.46 | 0.95 | -1.34 | 0.88 |
| 12 | -0.10 | 0.97 | -0.12 | 0.96 | -1.36 | 0.88 |

Mean offset by local hour of day (°C):

| hour | temp_c_fc_day0 bias | temp_c_era5 bias |
|---|---|---|
| 0 | -0.10 | -1.08 |
| 1 | -0.18 | -1.07 |
| 2 | -0.20 | -1.11 |
| 3 | -0.21 | -1.10 |
| 4 | -0.29 | -1.06 |
| 5 | -0.27 | -0.98 |
| 6 | -0.28 | -0.73 |
| 7 | -0.21 | -0.24 |
| 8 | -0.03 | 0.31 |
| 9 | 0.27 | 0.74 |
| 10 | 0.47 | 0.90 |
| 11 | 0.61 | 0.90 |
| 12 | 0.58 | 0.87 |
| 13 | 0.48 | 0.76 |
| 14 | 0.45 | 0.64 |
| 15 | 0.37 | 0.45 |
| 16 | 0.29 | 0.19 |
| 17 | 0.25 | -0.04 |
| 18 | 0.20 | -0.23 |
| 19 | 0.23 | -0.54 |
| 20 | 0.24 | -0.78 |
| 21 | 0.16 | -0.91 |
| 22 | -0.02 | -1.02 |
| 23 | -0.08 | -1.09 |

## Bias correction: out-of-sample test (fit < 2026-09-01, evaluate Sep + Oct 2026, MAE °C)

| variant | ICON temp_c_fc_safe | JMA temp_c_fc_safe_jma |
|---|---|---|
| raw | 0.938 | 2.003 |
| one linear fit | 0.941 | 1.606 |
| linear fit per month | 0.962 | 1.668 |
| offset per month x local hour (used) | 0.929 | 1.556 |

Figure: `reports/figures/weather_forecast_vs_observed.png`
