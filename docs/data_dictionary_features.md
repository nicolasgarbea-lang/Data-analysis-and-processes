# Data dictionary – feature table (agent F1)

File: `data/processed/features.parquet`, built by `src/features/build_features.py` (`python -m src.features.build_features`).
One row per **(delivery_date, block)**, delivery dates 2019-01-15 → 2026-11-01 (local Europe/Zurich days), 6 blocks per day.

**Time rule.** The forecast is made on day **D** at 10:00 Europe/Zurich (`forecast_issue_time_utc`) for delivery day **D+1** = `delivery_date`.
"lag k d" = the same local block (or local day) **k days before the delivery date**. So lag 1 d = day D, lag 2 d = day D−1.
All windows are built on the local clock and converted to UTC (DST days have 23/25 hours, blocks of 3/5 hours).

Availability cutoffs (latest allowed END of the data window; checked in code by `Ctx.window()` and in `tests/test_no_leakage.py`):

| source | file | known up to | so the smallest lag is |
|---|---|---|---|
| Zurich demand (ewz) | demand_ewz_hourly | end of local day D−1 | 2 d |
| CH price | price_ch_hourly | end of local day D (auction on D−1) | 1 d |
| DE/FR/AT/IT-North prices | price_neighbours_hourly | end of local day D (SDAC on D−1) | 1 d |
| Swiss load/generation | swiss_power_hourly | end of local day D−1 (`load_bad`/`wind_bad`/`solar_bad` hours → NaN) | 2 d |
| observed weather (MeteoSwiss SMA) | weather_observed_hourly | hours ending ≤ issue time − 1 h (i.e. ≤ 09:00 local on D) | – |
| weather forecasts | weather_forecast_hourly `*_fc_safe*` | delivery day only; each hour is leakage-safe by construction (D2) | – |
| gas, CO₂, EUR/CHF, reservoirs | *_daily / reservoir_weekly | latest row with `available_from_utc` ≤ issue time | – |
| calendar, holidays, events, football, EV `_known` | calendar_features_daily | known in advance | – |

Column groups: **key** (identifiers), **target**, **actual** (same-row truth, never a feature), **oracle** (observed weather of the delivery day, `_obs`, never a default feature), **unverified** (publication time not verified, never a default feature), **feature**.

## Keys

| column | type | unit | rule |
|---|---|---|---|
| delivery_date | key | local date | delivery day D+1 |
| block | key / feature | 0–5 | local clock blocks 00–04, 04–08, 08–12, 12–16, 16–20, 20–24 |
| block_start_utc | key | UTC | start of the first hour of the block |
| hours_in_block | key / feature | h | 4; 3 (block 0 on spring DST day) or 5 (block 0 on autumn DST day) |
| forecast_issue_time_utc | key | UTC | D 10:00 Europe/Zurich (`auction.forecast_time_local`) |

## Targets and actuals (not features)

| column | type | unit | source | rule |
|---|---|---|---|---|
| demand_mw | target | MW | demand_ewz_hourly.load_mw | mean of the hourly values of the delivery block; NaN unless every hour is present |
| price_eur_mwh | target | EUR/MWh | price_ch_hourly | mean of the hourly CH prices of the block; NaN unless complete |
| actual_demand_mwh | actual | MWh | – | demand_mw × hours_in_block |
| actual_price_min_block, actual_price_max_block | actual | EUR/MWh | price_ch_hourly | min / max hourly price in the block |
| actual_cost_eur | actual | EUR | demand + price | Σ over hours of load_mw × price (cost of buying the actual demand at the actual hourly price) |
| actual_eurchf | actual | CHF per EUR | eurchf_daily | ECB rate of the delivery date, or the last rate before it (for CHF conversion of results) |

## Demand features (ewz, known up to end of D−1)

| column | unit | rule |
|---|---|---|
| demand_lag_2d_same_block, demand_lag_3d_same_block, demand_lag_7d_same_block, demand_lag_8d_same_block, demand_lag_14d_same_block, demand_lag_21d_same_block, demand_lag_28d_same_block, demand_lag_364d_same_block | MW | mean of the same block k days before delivery (7, 14, 21, 28, 364 = same weekday) |
| demand_mean_same_block_same_weekday_4w | MW | mean of lags 7, 14, 21, 28 (NaN ignored) |
| expected_demand_proxy | MW | = demand_mean_same_block_same_weekday_4w |
| demand_day_mean_lag_2d, demand_day_mean_lag_7d | MW | mean of the local day delivery−2 / delivery−7 |
| demand_day_max_lag_2d, demand_day_min_lag_2d | MW | max / min hourly value of day delivery−2 (= D−1) |
| demand_mean_last_7d | MW | hourly mean over days D−7 … D−1 (delivery−8 … delivery−2) |
| demand_mean_last_28d | MW | hourly mean over days D−28 … D−1 |
| demand_trend_7d | ratio | demand_mean_last_7d ÷ mean of days D−14 … D−8 |
| demand_dm1_block_0 … demand_dm1_block_5 | MW | the six block means of day D−1 (previous-day shape) |

## Weather of the delivery block / day

Variables: `temp_c` (°C), `radiation_wm2` (W/m²), `sunshine_min` (min per hour), `wind_ms` (m/s), `precip_mm` (mm per hour), `cloud_pct` (%), `humidity_pct` (%). Block values are means over the hours of the delivery block.

| column | type | rule |
|---|---|---|
| temp_c_obs, radiation_wm2_obs, sunshine_min_obs, wind_ms_obs, precip_mm_obs, humidity_pct_obs | **oracle** | observed MeteoSwiss SMA block mean of the delivery day (not known at issue time; for benchmarks only). No observed cloud cover. |
| temp_c_fc, radiation_wm2_fc, sunshine_min_fc, wind_ms_fc, precip_mm_fc, cloud_pct_fc, humidity_pct_fc | feature (not default) | ICON-seamless safe forecast block mean: `temp_c_fc_safe_corr` for temperature, `<var>_fc_safe` otherwise; single missing hours filled from the ECMWF `_fc_safe_ecmwf` column (23-h gap 2026-04-10/11 in radiation and cloud). NaN unless every hour of the block has a forecast → NaN before 2024-01-21 (2024-01-20 is only partly covered) |
| temp_c_fc_jma, wind_ms_fc_jma, precip_mm_fc_jma, cloud_pct_fc_jma, humidity_pct_fc_jma | feature (not default) | JMA GSM safe forecast block mean (`temp_c_fc_safe_jma_corr`, `<var>_fc_safe_jma`); real forecasts back to 2019; mean of available hours |
| temp_c, radiation_wm2, sunshine_min, wind_ms, precip_mm, humidity_pct | **feature (hybrid)** | `<var>_fc` if not NaN, else `<var>_obs`. Before 2024-01-21 this is OBSERVED weather (documented limitation) |
| cloud_pct | feature (hybrid) | `cloud_pct_fc`, else `cloud_pct_fc_jma` (a real forecast, no observation exists) |
| weather_is_forecast | feature | 1 if all hybrid block and day weather values of the row come from the ICON forecast, else 0 (0 before 2024-01-21) |
| temp_c_sq, heating_degree, cooling_degree (+ `_obs`, `_fc`, `_fc_jma`) | as the temperature they use | temp², max(0, 15 − temp), max(0, temp − 22) of the block temperature |
| temp_day_mean, temp_day_min, temp_day_max (+ `_obs`, `_fc`, `_fc_jma`) | as above | mean / min / max hourly temperature of the whole delivery day; hybrid = `_fc` day value if the whole day is forecast, else `_obs` |
| radiation_day_mean, sunshine_day_sum (+ `_obs`, `_fc`) | as above | delivery-day mean radiation (W/m²) / total sunshine (min) |

## Past observed weather (known at issue time)

| column | unit | rule |
|---|---|---|
| temp_obs_mean_dm1 | °C | mean observed temperature of day D−1 |
| temp_obs_mean_last_3d, temp_obs_mean_last_7d | °C | mean over days D−3 … D−1 / D−7 … D−1 |
| temp_obs_same_block_lag_2d, radiation_obs_same_block_lag_2d | °C, W/m² | same block of day D−1 |
| temp_obs_last_24h_mean | °C | the 24 hours ending at issue time − 1 h (D−1 09:00 → D 09:00 local) |
| temp_change_fc_vs_dm1 (+ `_obs`, `_fc`, `_fc_jma`) | K | block temperature (hybrid / oracle / ICON / JMA) − temp_obs_same_block_lag_2d |

## Solar, EVs

| column | unit | source | rule |
|---|---|---|---|
| solar_ch_mw_lag_2d_same_block | MW | swiss_power_hourly.solar_mw | same block of day D−1 |
| solar_ch_day_mean_lag_2d | MW | same | day D−1 mean |
| ev_count_city | cars | ev_daily.ev_count_city_known | last published 30 Sept count + last published yearly growth |
| charging_kw_zh | kW | ev_daily.charging_kw_zh_known | last published BFE month; NaN before 2020-12-15 |
| stations_zh_count | count | ev_daily.stations_zh_count_known | same; NaN before 2020-12-15 |

## Calendar (delivery date unless stated; known in advance)

| column | unit | rule |
|---|---|---|
| weekday, month, day_of_year, is_weekend, is_holiday, is_half_holiday, is_bridge_day, is_school_holiday, is_christmas_period, days_to_next_holiday, days_since_last_holiday, is_dst_change_day | – | from calendar_features_daily (see docs/data_dictionary_calendar.md) |
| school_holiday_type | code | 0 none, 1 christmas, 2 sport, 3 spring, 4 summer, 5 autumn, 6 school_free_day |
| school_holiday_type_name | text | same as text (not a model input) |
| event_size, n_events | 0–3, count | events_daily |
| home_game | 0/1 | FC Zürich / Grasshoppers home game |
| kickoff_hour_local | h | earliest kick-off (Swiss time); **0 = no home game** |
| covid_stringency | 0–100 | OxCGRT `covid_stringency_filled` (0 outside 2020–2022) |
| week_of_year | – | ISO week |
| year_frac | years | year + (day_of_year − 1) / days in year (trend) |
| sin_doy, cos_doy | – | sin / cos(2π · day_of_year / 365.25) |
| daylight_hours | h | astronomical day length at 47.378° N: declination 23.44°·sin(2π(284+doy)/365), 2·arccos(−tanφ·tanδ)/15° |
| is_holiday_prev_day, is_holiday_next_day | 0/1 | is_holiday of day D / of delivery + 1 |
| lag2d_was_holiday, lag7d_was_holiday, lag2d_is_weekend | 0/1 | is_holiday / is_weekend of the lag day delivery−2 / delivery−7 |
| is_working_day | 0/1 | not weekend and not holiday |

## CH price features (all hours of day D known)

| column | unit | rule |
|---|---|---|
| price_lag_1d_same_block, price_lag_2d_same_block, price_lag_7d_same_block, price_lag_14d_same_block | EUR/MWh | same block k days before delivery (1 = day D, 7 = D−6, same weekday) |
| price_mean_day_D, price_min_day_D, price_max_day_D, price_std_day_D | EUR/MWh | mean / min / max / std (ddof 1) of the hourly prices of day D |
| price_spread_day_D | EUR/MWh | price_max_day_D − price_min_day_D |
| price_dD_block_0 … price_dD_block_5 | EUR/MWh | the six block means of day D |
| price_mean_last_7d, price_std_last_7d | EUR/MWh | hourly mean / std over days D−6 … D |
| price_mean_last_28d | EUR/MWh | hourly mean over days D−27 … D |
| price_block_vs_day_ratio_last_7d | EUR/MWh | mean over the last 7 days (D−6 … D) of (block price − day mean price) – a difference despite the name |
| price_neg_hours_day_D, price_neg_hours_last_7d | hours | number of hours with price < 0 on day D / days D−6 … D |
| price_lag_7d_day_mean | EUR/MWh | day mean of delivery−7 |

## Neighbour prices (day D)

| column | unit | rule |
|---|---|---|
| price_de_day_D_same_block, price_fr_day_D_same_block, price_at_day_D_same_block, price_it_day_D_same_block | EUR/MWh | same block of day D, DE-LU / FR / AT / IT-North |
| price_de_mean_day_D, price_fr_mean_day_D, price_at_mean_day_D, price_it_mean_day_D | EUR/MWh | day D mean |
| spread_ch_de_day_D, spread_ch_fr_day_D, spread_ch_at_day_D, spread_ch_it_day_D | EUR/MWh | CH day-D mean − neighbour day-D mean |
| spread_ch_de_mean_7d, spread_ch_fr_mean_7d, spread_ch_at_mean_7d, spread_ch_it_mean_7d | EUR/MWh | mean of the daily spreads over days D−6 … D |
| price_de_lag_7d_same_block | EUR/MWh | DE same block of delivery−7 |

## Fuels, FX, hydro (as-of `available_from_utc` ≤ issue time)

| column | unit | rule |
|---|---|---|
| gas_ttf_d_1 | EUR/MWh | latest TTF front-month close (Yahoo `TTF=F`, unofficial) published by the issue time (= close of D−1 or earlier) |
| gas_ttf_change_5d | EUR/MWh | gas_ttf_d_1 − the close 5 trading rows earlier |
| gas_ttf_mean_20d | EUR/MWh | mean of the last 20 published closes |
| co2_eua_d_1 | EUR/t | latest EEX EUA primary-auction price published by the issue time (auction results come at 12:00, so this is an auction on D−1 or earlier) |
| co2_staleness_days | days | day D − date of that auction (large in the January auction break) |
| eurchf_d_1 | CHF per EUR | latest ECB reference rate (≤ D−1) |
| clean_gas_cost | EUR/MWh_el | gas_ttf_d_1 / 0.5 + 0.37 × co2_eua_d_1 (CCGT short-run cost proxy, 50 % efficiency, 0.37 tCO₂/MWh_el) |
| reservoir_fill_pct | % | latest published Swiss reservoir fill (BFE, level of Sunday night, counted as public from Thursday 23:59) |
| reservoir_vs_median_pct | %-points | same row: fill − median of the same ISO week in earlier years |
| reservoir_change_1w | %-points | reservoir_fill_pct − previous published week |

## Swiss system (Energy-Charts, known up to end of D−1)

| column | unit | rule |
|---|---|---|
| swiss_load_lag_2d_same_block | MW | Swiss load, same block of D−1 (`load_bad` hours = NaN) |
| swiss_load_day_mean_lag_2d | MW | Swiss load, day D−1 mean |
| swiss_nuclear_mw_lag_2d, swiss_hydro_ror_mw_lag_2d, swiss_hydro_storage_mw_lag_2d, swiss_hydro_pumped_mw_lag_2d | MW | day D−1 mean of nuclear / run-of-river / reservoir hydro / pumped-storage generation |
| swiss_solar_mw_lag_2d_same_block | MW | solar, same block of D−1 (= solar_ch_mw_lag_2d_same_block) |
| swiss_residual_load_lag_2d_same_block | MW | hourly load − solar − wind − run-of-river, same block of D−1 |
| swiss_net_import_mw_lag_2d | MW | cross-border trading, day D−1 mean (sign as Energy-Charts; positive mostly in winter = import) |

## Unverified (not default features)

| column | unit | rule |
|---|---|---|
| unverified_de_solar_fc, unverified_de_wind_onshore_fc, unverified_de_wind_offshore_fc, unverified_de_load_fc | MW | Energy-Charts German day-ahead forecasts, delivery-block mean. Publication time unverified (legal deadline wind/solar D 18:00, after our forecast) |
| unverified_de_solar_fc_day, unverified_de_wind_onshore_fc_day, unverified_de_wind_offshore_fc_day, unverified_de_load_fc_day | MW | same, delivery-day mean |
| unverified_ch_solar_fc, unverified_ch_solar_fc_day | MW | Energy-Charts Swiss solar day-ahead forecast, block / day mean; scale changes over the years and publication time unverified |

## European weather forecasts (optional)

| column | unit | rule |
|---|---|---|
| eu_<c> | as in source | for every numeric column `<c>` of `weather_europe_forecast_hourly.parquet` (if the file exists): mean over the delivery block. The file is leakage-safe by construction (other agent); only delivery-day rows are used |
| eu_<c>_day | as in source | same, mean over the delivery day |

## `data/processed/hourly_actuals.parquet`

One row per UTC hour of local days 2019-01-01 → 2026-11-01 (23/25 rows on DST days).

| column | unit | rule |
|---|---|---|
| timestamp_utc | UTC | start of the hour |
| local_time | Europe/Zurich | same instant in local time |
| delivery_date | local date | local day of the hour |
| hour_local | 0–23 | local clock hour (hour 2 appears twice on autumn DST days, missing in spring) |
| block | 0–5 | hour_local // 4 |
| demand_mw | MW | ewz hourly load (actual) |
| price_eur_mwh | EUR/MWh | CH day-ahead price (actual) |
| eurchf | CHF per EUR | ECB rate of the local day, or the last rate before it |
