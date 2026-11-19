# Data check: weather_europe_forecast_hourly (Open-Meteo previous-runs API, 9 European points)

- Rows: 69,479; timestamp_utc 2018-12-01 00:00:00+00:00 -> 2026-11-03 22:00:00+00:00 (complete hourly grid, START of hour, UTC)
- Duplicates removed: 0
- `<var>_<point>_safe` = icon_seamless; `<var>_<point>_jma_safe` = jma_seamless (10 m wind, no radiation).
- Lead rule, time shift (Open-Meteo stamp -1 h), cadence/delay reused from src/data/load_openmeteo_forecast.py.
- ICON: day1 used for delivery-day local hours [0, 1, 2, 3, 4, 5, 6], day2 otherwise (day1 share 27.4%).
- JMA: day1 used for delivery-day local hours [0, 1, 2, 3, 4, 5, 6], day2 otherwise (day1 share 27.4%).

## Coverage and NaN per column

| column | first valid (UTC) | last valid (UTC) | NaN after first valid | min | max |
|---|---|---|---|---|---|
| temp_c_de_north_safe | 2024-01-19 23:00:00+00:00 | 2026-11-03 22:00:00+00:00 | 0.025% | -7.6 | 31.5 |
| temp_c_de_northeast_safe | 2024-01-19 23:00:00+00:00 | 2026-11-03 22:00:00+00:00 | 0.025% | -11.0 | 38.9 |
| temp_c_de_central_safe | 2024-01-19 23:00:00+00:00 | 2026-11-03 22:00:00+00:00 | 0.025% | -7.7 | 38.4 |
| temp_c_de_south_safe | 2024-01-19 23:00:00+00:00 | 2026-11-03 22:00:00+00:00 | 0.025% | -10.7 | 36.6 |
| temp_c_fr_paris_safe | 2024-01-19 23:00:00+00:00 | 2026-11-03 22:00:00+00:00 | 0.025% | -5.0 | 39.6 |
| temp_c_fr_lyon_safe | 2024-01-19 23:00:00+00:00 | 2026-11-03 22:00:00+00:00 | 0.025% | -5.5 | 40.6 |
| temp_c_it_milan_safe | 2024-01-19 23:00:00+00:00 | 2026-11-03 22:00:00+00:00 | 0.025% | -4.2 | 36.9 |
| temp_c_ch_alps_safe | 2024-01-19 23:00:00+00:00 | 2026-11-03 22:00:00+00:00 | 0.025% | -18.3 | 28.1 |
| temp_c_ch_bern_safe | 2024-01-19 23:00:00+00:00 | 2026-11-03 22:00:00+00:00 | 0.025% | -11.9 | 36.7 |
| radiation_wm2_de_north_safe | 2024-01-19 23:00:00+00:00 | 2026-11-03 22:00:00+00:00 | 0.119% | 0.0 | 836.0 |
| radiation_wm2_de_northeast_safe | 2024-01-19 23:00:00+00:00 | 2026-11-03 22:00:00+00:00 | 0.119% | 0.0 | 862.0 |
| radiation_wm2_de_central_safe | 2024-01-19 23:00:00+00:00 | 2026-11-03 22:00:00+00:00 | 0.119% | 0.0 | 872.0 |
| radiation_wm2_de_south_safe | 2024-01-19 23:00:00+00:00 | 2026-11-03 22:00:00+00:00 | 0.119% | 0.0 | 906.0 |
| radiation_wm2_it_milan_safe | 2024-01-19 23:00:00+00:00 | 2026-11-03 22:00:00+00:00 | 0.119% | 0.0 | 939.0 |
| radiation_wm2_ch_alps_safe | 2024-01-19 23:00:00+00:00 | 2026-11-03 22:00:00+00:00 | 0.119% | 0.0 | 1006.0 |
| radiation_wm2_ch_bern_safe | 2024-01-19 23:00:00+00:00 | 2026-11-03 22:00:00+00:00 | 0.119% | 0.0 | 919.0 |
| wind100_ms_de_north_safe | 2024-02-16 23:00:00+00:00 | 2026-11-03 22:00:00+00:00 | 0.025% | 0.0 | 35.1 |
| wind100_ms_de_northeast_safe | 2024-02-16 23:00:00+00:00 | 2026-11-03 22:00:00+00:00 | 0.025% | 0.1 | 21.9 |
| wind100_ms_de_central_safe | 2024-02-16 23:00:00+00:00 | 2026-11-03 22:00:00+00:00 | 0.025% | 0.0 | 22.7 |
| precip_mm_ch_alps_safe | 2024-01-19 23:00:00+00:00 | 2026-11-03 22:00:00+00:00 | 0.025% | 0.0 | 12.0 |
| wind_cubed_de_north_safe | 2024-02-16 23:00:00+00:00 | 2026-11-03 22:00:00+00:00 | 0.025% | 0.0 | 15625.0 |
| wind_cubed_de_northeast_safe | 2024-02-16 23:00:00+00:00 | 2026-11-03 22:00:00+00:00 | 0.025% | 0.0 | 10447.6 |
| wind_cubed_de_central_safe | 2024-02-16 23:00:00+00:00 | 2026-11-03 22:00:00+00:00 | 0.025% | 0.0 | 11688.5 |
| wind_cubed_de_mean_safe | 2024-02-16 23:00:00+00:00 | 2026-11-03 22:00:00+00:00 | 0.025% | 0.0 | 8343.4 |
| temp_c_fr_mean_safe | 2024-01-19 23:00:00+00:00 | 2026-11-03 22:00:00+00:00 | 0.025% | -4.5 | 38.9 |
| radiation_wm2_de_mean_safe | 2024-01-19 23:00:00+00:00 | 2026-11-03 22:00:00+00:00 | 0.119% | 0.0 | 861.2 |
| temp_c_de_north_jma_safe | 2018-12-01 00:00:00+00:00 | 2026-11-03 22:00:00+00:00 | 0.000% | -6.8 | 30.5 |
| temp_c_de_northeast_jma_safe | 2018-12-01 00:00:00+00:00 | 2026-11-03 22:00:00+00:00 | 0.000% | -9.8 | 34.1 |
| temp_c_de_central_jma_safe | 2018-12-01 00:00:00+00:00 | 2026-11-03 22:00:00+00:00 | 0.000% | -16.1 | 32.8 |
| temp_c_de_south_jma_safe | 2018-12-01 00:00:00+00:00 | 2026-11-03 22:00:00+00:00 | 0.000% | -15.6 | 33.7 |
| temp_c_fr_paris_jma_safe | 2018-12-01 00:00:00+00:00 | 2026-11-03 22:00:00+00:00 | 0.000% | -5.0 | 38.3 |
| temp_c_fr_lyon_jma_safe | 2018-12-01 00:00:00+00:00 | 2026-11-03 22:00:00+00:00 | 0.000% | -5.8 | 38.1 |
| temp_c_it_milan_jma_safe | 2018-12-01 00:00:00+00:00 | 2026-11-03 22:00:00+00:00 | 0.000% | -16.5 | 36.7 |
| temp_c_ch_alps_jma_safe | 2018-12-01 00:00:00+00:00 | 2026-11-03 22:00:00+00:00 | 0.000% | -15.3 | 29.4 |
| temp_c_ch_bern_jma_safe | 2018-12-01 00:00:00+00:00 | 2026-11-03 22:00:00+00:00 | 0.000% | -10.8 | 34.3 |
| wind10_ms_de_north_jma_safe | 2018-12-01 00:00:00+00:00 | 2026-11-03 22:00:00+00:00 | 0.000% | 0.0 | 19.2 |
| wind10_ms_de_northeast_jma_safe | 2018-12-01 00:00:00+00:00 | 2026-11-03 22:00:00+00:00 | 0.000% | 0.0 | 10.5 |
| wind10_ms_de_central_jma_safe | 2018-12-01 00:00:00+00:00 | 2026-11-03 22:00:00+00:00 | 0.000% | 0.0 | 10.4 |
| precip_mm_ch_alps_jma_safe | 2018-12-01 00:00:00+00:00 | 2026-11-03 22:00:00+00:00 | 0.327% | 0.0 | 14.4 |
| wind_cubed_de_north_jma_safe | 2018-12-01 00:00:00+00:00 | 2026-11-03 22:00:00+00:00 | 0.000% | 0.0 | 7133.3 |
| wind_cubed_de_northeast_jma_safe | 2018-12-01 00:00:00+00:00 | 2026-11-03 22:00:00+00:00 | 0.000% | 0.0 | 1148.5 |
| wind_cubed_de_central_jma_safe | 2018-12-01 00:00:00+00:00 | 2026-11-03 22:00:00+00:00 | 0.000% | 0.0 | 1139.3 |
| wind_cubed_de_mean_jma_safe | 2018-12-01 00:00:00+00:00 | 2026-11-03 22:00:00+00:00 | 0.000% | 0.0 | 2823.2 |
| temp_c_fr_mean_jma_safe | 2018-12-01 00:00:00+00:00 | 2026-11-03 22:00:00+00:00 | 0.000% | -4.1 | 37.2 |

## Sanity check: correlation with the DE day-ahead price (`price_neighbours_hourly.price_de_eur_mwh`)

| forecast column | rows | sample | Pearson r | Spearman r |
|---|---|---|---|---|
| wind_cubed_de_mean_safe | 23,778 | all hours 2024-2026 | -0.284 | -0.289 |
| wind_cubed_de_mean_jma_safe | 24,911 | all hours 2024-2026 | -0.298 | -0.380 |
| wind_cubed_de_mean_jma_safe | 68,735 | all hours 2019-2026 | -0.202 | -0.272 |
| radiation_wm2_de_mean_safe | 4,069 | local 11-14 h, 2024-2026 | -0.606 | -0.649 |
| radiation_wm2_de_mean_safe | 24,427 | all hours 2024-2026 | -0.467 | -0.328 |
| temp_c_fr_mean_safe | 24,450 | all hours 2024-2026 (FR price: see note) | -0.130 | -0.119 |

Expected: wind and midday radiation negative (more renewables -> lower price). Temperature in France is listed for information only; its effect on the DE price is non-linear (cold -> high price).
