# Data checks

One section per processed table, written by the loaders.


## Data check: calendar_daily

- rows: 2953
- first date: 2018-12-01  (local Europe/Zurich calendar day)
- last date: 2026-12-31
- duplicate dates removed: 0
- % missing overall: 18.59

| column | % missing |
|---|---|
| weekday | 0.0 |
| month | 0.0 |
| day_of_year | 0.0 |
| is_weekend | 0.0 |
| is_holiday | 0.0 |
| holiday_name | 97.22 |
| is_half_holiday | 0.0 |
| half_holiday_name | 99.49 |
| is_bridge_day | 0.0 |
| is_school_holiday | 0.0 |
| school_holiday_type | 75.04 |
| days_to_next_holiday | 0.0 |
| days_since_last_holiday | 0.0 |
| is_christmas_period | 0.0 |
| is_dst_change_day | 0.0 |
| hours_in_day | 0.0 |
| covid_stringency | 62.89 |
| covid_stringency_filled | 0.0 |

## Notes

- public holidays per year (incl. Berchtoldstag): {2018: 2, 2019: 10, 2020: 10, 2021: 10, 2022: 10, 2023: 10, 2024: 10, 2025: 10, 2026: 10}
- bridge days: 18; half-holidays: 15
- school-holiday days: 737; types: {'summer': 264, 'christmas': 107, 'spring': 104, 'sport': 96, 'autumn': 96, 'school_free_day': 70}
- DST days: 16 (hours_in_day values [np.int64(23), np.int64(24), np.int64(25)])
- holiday_name / half_holiday_name / school_holiday_type are empty on normal days (by design).
- covid_stringency is NaN outside 2020-01-01..2022-12-31 (OxCGRT coverage); use covid_stringency_filled (0 outside) in models.


## Data check: calendar_features_daily

- rows: 2953
- first date: 2018-12-01  (local Europe/Zurich calendar day)
- last date: 2026-12-31
- duplicate dates removed: 0
- % missing overall: 22.99

| column | % missing |
|---|---|
| weekday | 0.0 |
| month | 0.0 |
| day_of_year | 0.0 |
| is_weekend | 0.0 |
| is_holiday | 0.0 |
| holiday_name | 97.22 |
| is_half_holiday | 0.0 |
| half_holiday_name | 99.49 |
| is_bridge_day | 0.0 |
| is_school_holiday | 0.0 |
| school_holiday_type | 75.04 |
| days_to_next_holiday | 0.0 |
| days_since_last_holiday | 0.0 |
| is_christmas_period | 0.0 |
| is_dst_change_day | 0.0 |
| hours_in_day | 0.0 |
| covid_stringency | 62.89 |
| covid_stringency_filled | 0.0 |
| ev_count_city | 0.0 |
| ev_count_city_is_extrapolated | 0.0 |
| ev_count_city_known | 0.0 |
| stations_zh_count | 24.72 |
| stations_zh_count_known | 25.23 |
| charging_kw_zh | 24.72 |
| charging_kw_zh_known | 25.23 |
| charging_kw_zh_backcast | 0.0 |
| bfe_is_held_after_last_month | 0.0 |
| event_size | 0.0 |
| n_events | 0.0 |
| event_name | 93.84 |
| event_types | 93.84 |
| home_game | 0.0 |
| n_home_games | 0.0 |
| kickoff_hour_local | 91.3 |
| home_team | 91.3 |

## Notes

- merged from calendar_daily, ev_daily, events_daily, football_daily on `date` (local Zurich day); 35 value columns
- see the check files of the parts for details; text columns are empty on normal days by design


## Data check: co2_eua_daily

- source: EEX primary-market auction reports (archive zip 2012-2025 + 2026 xlsx), official
- auction rows read: 3043; successful used: 3039; duplicate auction rows dropped: 1
- rows (auction days): 1724; in 2019-01-01→2026-10-31: 1704
- first: 2018-12-03  last: 2026-11-19
- range: min 14.60, max 97.51 EUR/t
- gaps > 7 days without auction (date after gap, gap days): 2019-01-07(21), 2020-01-07(22), 2021-01-29(46), 2022-01-10(21), 2023-01-09(21), 2024-01-15(28), 2025-01-07(22), 2026-01-07(23)
- daily value = volume-weighted mean of all successful auctions that day
- no auctions on most Fridays/weekends, in parts of August and around New Year → as-of join with last value
- available_from_utc = auction day 12:00 Europe/Zurich (results published ~11:15)


## Data check: de_forecasts_hourly

- rows: 69095 hourly; first 2019-01-01 00:00:00+00:00 last 2026-11-18 22:00:00+00:00
- raw 15-min values averaged to hourly; duplicates between chunks dropped (keep last)
- solar_da_forecast_de_mw: missing 0.00% (2019-01-01→2026-11-01), first valid 2019-01-01 00:00:00+00:00, min 0, max 57896
- wind_onshore_da_forecast_de_mw: missing 0.00% (2019-01-01→2026-11-01), first valid 2019-01-01 00:00:00+00:00, min 161, max 48122
- wind_offshore_da_forecast_de_mw: missing 0.00% (2019-01-01→2026-11-01), first valid 2019-01-01 00:00:00+00:00, min 13, max 7387
- load_da_forecast_de_mw: missing 0.00% (2019-01-01→2026-11-01), first valid 2019-01-01 00:00:00+00:00, min 30545, max 77586
- PUBLICATION TIME UNVERIFIED: API gives no issue time. Legal deadlines: load D-1 10:00 CET (Art. 6 Reg. 543/2013, borderline for our 10:00 forecast), wind/solar D-1 18:00 CET (Art. 14, after our forecast time). Flag column publication_time_unverified=True.


## Check: demand_ewz.parquet / demand_ewz_hourly.parquet (ewz Bruttolastgang, Zurich)

- raw rows read: 276096; autumn DST label pairs resolved: 32 (none dropped)
- 15-min rows: 276288; first / last timestamp_utc (interval start): 2018-12-31 23:00:00+00:00 / 2026-11-17 22:45:00+00:00
- local time: 2019-01-01 00:00:00+01:00 → 2026-11-17 23:45:00+01:00 (interval start)
- duplicate UTC timestamps after conversion: 0
- missing 15-min intervals before filling: 192 (0.069%); after filling: 0
- filled intervals: 192 ({'netzebenen': 192})
- status counts (15-min): {'E': 272832, 'F': 3264, nan: 192}  (W = final, E = substitute, F = not yet checked; no W at all in the current files, so `share_non_final` is 1 everywhere — use `share_status_f`)
- hourly rows: 69072; hours with load_mw missing: 0; hours before 2026-11-01 UTC missing: 0
- load_mw range: min 182.8, max 463.1, mean 299.9 MW
- local days with ≠ 24 hours (should be only DST days, 23 / 25 h, plus partial first/last day): {'2019-03-31': 23, '2019-10-27': 25, '2020-03-29': 23, '2020-10-25': 25, '2021-03-28': 23, '2021-10-31': 25, '2022-03-27': 23, '2022-10-30': 25, '2023-03-26': 23, '2023-10-29': 25, '2024-03-31': 23, '2024-10-27': 25, '2025-03-30': 23, '2025-10-26': 25, '2026-03-29': 23, '2026-10-25': 25}

## Gaps in the raw data

| first interval start (UTC) | last interval start (UTC) | intervals | filled with |
|---|---|---|---|
| 2021-05-29 22:00:00+00:00 | 2021-05-30 21:45:00+00:00 | 96 | netzebenen |
| 2021-08-06 22:00:00+00:00 | 2021-08-07 21:45:00+00:00 | 96 | netzebenen |

## Status F by month (local time)

| month | intervals with F |
|---|---|
| 2020-06 | 1632 |
| 2026-11 | 1632 |

## Yearly mean load (MW, local calendar year)

| year | mean MW | min | max |
|---|---|---|---|
| 2019 | 312.9 | 193.5 | 463.1 |
| 2020 | 299.4 | 182.8 | 455.3 |
| 2021 | 301.1 | 190.0 | 458.1 |
| 2022 | 302.2 | 191.8 | 439.1 |
| 2023 | 295.1 | 184.8 | 436.6 |
| 2024 | 295.3 | 185.3 | 435.5 |
| 2025 | 295.9 | 186.0 | 435.7 |
| 2026 | 297.2 | 189.3 | 438.5 |


## Cross-check: ewz Bruttolastgang (local time) vs ewz Netzebenen NE5+NE7 (UTC)

Netzebenen metadata (data.stadt-zuerich.ch, field `Timestamp`): *"Die Werte der Bruttoenergie beziehen sich auf die 15 Minuten vor dieser Zeitangabe"* → its timestamps mark the END of the interval.

Below, Bruttolastgang was converted with our rule (local label = END, → UTC, −15 min = START) and compared with Netzebenen (UTC END label −15 min = START), shifting Netzebenen by k × 15 min.

| shift of Netzebenen | correlation | mean abs. diff (kWh/15 min) | n |
|---|---|---|---|
| -60 min | 0.957787 | 3483.1 | 275900 |
| -45 min | 0.975048 | 2717.9 | 275901 |
| -30 min | 0.988101 | 1920.4 | 275902 |
| -15 min | 0.996589 | 1022.0 | 275903 |
| +0 min | 0.999993 | 17.2 | 275904 |
| +15 min | 0.996584 | 1023.8 | 275905 |
| +30 min | 0.988091 | 1922.7 | 275906 |
| +45 min | 0.975034 | 2720.5 | 275907 |
| +60 min | 0.957770 | 3485.8 | 275908 |

Shift 0 is best by far → both files use the same convention, i.e. the ewz local timestamps are END labels too.
Further evidence: every ewz year file starts at 00:15 or ends with the 00:00 row of the next day (2019 starts 00:15; 2020–2026 start with the 00:00 row = last interval of the previous year; the 2026 file ends with a single 00:00 row of the next day; the missing 2021 days span exactly 00:15 → 00:00 of the next day).

- matched intervals: 275904
- abs. difference: median 1.86 kWh, mean 17.21 kWh, max 714.6 kWh (typical value ~60,000 kWh)
- intervals with > 1 % difference: 13 (days: 2026-07-19, 2026-08-02, 2026-08-23; likely later revisions of one file)
- Netzebenen covers 2016-12-31 23:00:00+00:00 → 2026-11-15 22:45:00+00:00 (interval starts, UTC)

## Autumn DST duplicates (local labels 02:00–02:45 appear twice)

`file_order_chronological` = True means the first of the two rows in the file is the summer-time (earlier) interval. The order is not consistent, so sorting by file order would be wrong in 27 of 32 pairs.

| local label | row 1 kWh | row 2 kWh | NE summer-time | NE winter-time | file order chronological | method |
|---|---|---|---|---|---|---|
| 2019-10-27 02:00:00 | 53795 | 54261 | 54264 | 53798 | False | matched to Netzebenen |
| 2019-10-27 02:15:00 | 56644 | 53118 | 56647 | 53121 | True | matched to Netzebenen |
| 2019-10-27 02:30:00 | 55956 | 52512 | 55958 | 52515 | True | matched to Netzebenen |
| 2019-10-27 02:45:00 | 54839 | 51621 | 54842 | 51624 | True | matched to Netzebenen |
| 2020-10-25 02:00:00 | 54999 | 54079 | 54999 | 54079 | True | matched to Netzebenen |
| 2020-10-25 02:15:00 | 53428 | 56880 | 56880 | 53428 | False | matched to Netzebenen |
| 2020-10-25 02:30:00 | 52974 | 56079 | 56079 | 52974 | False | matched to Netzebenen |
| 2020-10-25 02:45:00 | 51968 | 55137 | 55137 | 51968 | False | matched to Netzebenen |
| 2021-10-31 02:00:00 | 55986 | 56033 | 56033 | 55986 | False | matched to Netzebenen |
| 2021-10-31 02:15:00 | 55051 | 58562 | 58562 | 55051 | False | matched to Netzebenen |
| 2021-10-31 02:30:00 | 54495 | 57852 | 57852 | 54495 | False | matched to Netzebenen |
| 2021-10-31 02:45:00 | 53738 | 56837 | 56837 | 53738 | False | matched to Netzebenen |
| 2022-10-30 02:00:00 | 51852 | 52410 | 52410 | 51852 | False | matched to Netzebenen |
| 2022-10-30 02:15:00 | 50870 | 54478 | 54478 | 50870 | False | matched to Netzebenen |
| 2022-10-30 02:30:00 | 53689 | 50255 | 53690 | 50255 | True | matched to Netzebenen |
| 2022-10-30 02:45:00 | 49853 | 52670 | 52670 | 49853 | False | matched to Netzebenen |
| 2023-10-29 02:00:00 | 52376 | 53169 | 53184 | 52381 | False | matched to Netzebenen |
| 2023-10-29 02:15:00 | 51459 | 55343 | 55355 | 51463 | False | matched to Netzebenen |
| 2023-10-29 02:30:00 | 50936 | 54892 | 54903 | 50939 | False | matched to Netzebenen |
| 2023-10-29 02:45:00 | 50585 | 53756 | 53764 | 50587 | False | matched to Netzebenen |
| 2024-10-27 02:00:00 | 52344 | 53049 | 53049 | 52344 | False | matched to Netzebenen |
| 2024-10-27 02:15:00 | 51592 | 55603 | 55602 | 51592 | False | matched to Netzebenen |
| 2024-10-27 02:30:00 | 50761 | 54715 | 54715 | 50761 | False | matched to Netzebenen |
| 2024-10-27 02:45:00 | 49952 | 53544 | 53544 | 49952 | False | matched to Netzebenen |
| 2025-10-26 02:00:00 | 54251 | 55563 | 55560 | 54248 | False | matched to Netzebenen |
| 2025-10-26 02:15:00 | 53576 | 57365 | 57363 | 53573 | False | matched to Netzebenen |
| 2025-10-26 02:30:00 | 52625 | 56515 | 56513 | 52623 | False | matched to Netzebenen |
| 2025-10-26 02:45:00 | 51930 | 55172 | 55170 | 51928 | False | matched to Netzebenen |
| 2026-10-25 02:00:00 | 54843 | 55064 | 55064 | 54843 | False | matched to Netzebenen |
| 2026-10-25 02:15:00 | 53871 | 56924 | 56924 | 53871 | False | matched to Netzebenen |
| 2026-10-25 02:30:00 | 52996 | 56646 | 56646 | 52996 | False | matched to Netzebenen |
| 2026-10-25 02:45:00 | 52326 | 55677 | 55677 | 52326 | False | matched to Netzebenen |


## Data check: eurchf_daily

- rows: 2038; first 2018-12-03 last 2026-11-18; NaN dropped 0; duplicates dropped 0
- range: 0.9008 – 1.1470 CHF per EUR
- gaps > 4 days: 10 (Easter/Christmas TARGET holidays)
- available_from_utc = date 16:00 Europe/Zurich (ECB publishes ~16:00 CET)


## Data check: ev_daily

- rows: 2953
- first date: 2018-12-01  (local Europe/Zurich calendar day)
- last date: 2026-12-31
- duplicate dates removed: 0
- % missing overall: 11.10

| column | % missing |
|---|---|
| ev_count_city | 0.0 |
| ev_count_city_is_extrapolated | 0.0 |
| ev_count_city_known | 0.0 |
| stations_zh_count | 24.72 |
| stations_zh_count_known | 25.23 |
| charging_kw_zh | 24.72 |
| charging_kw_zh_known | 25.23 |
| charging_kw_zh_backcast | 0.0 |
| bfe_is_held_after_last_month | 0.0 |

## Notes

- EV stock points (30 Sept): 2017: 746, 2018: 887, 2019: 1467, 2020: 2023, 2021: 2979, 2022: 4373, 2023: 5991, 2024: 7571, 2025: 9743
- EV values after 2025-09-30 are extrapolated with the last yearly slope (ev_count_city_is_extrapolated = 1).
- BFE monthly data 2020-11 .. 2026-10 (71 months); monthly value placed on the last day of its month and interpolated linearly.
- stations_zh_count / charging_kw_zh are NaN before 2020-11-30 (series does not exist); the _known versions are NaN before 2020-12-15.
- charging_kw_zh_backcast fills the time before 2020-11 with a straight-line trend of the first 12 months (synthetic, clipped at 0).
- ev_count_city_known on 2026-10-01: 11921 vs interpolated truth 11921


## Data check: events_daily

- rows: 2953
- first date: 2018-12-01  (local Europe/Zurich calendar day)
- last date: 2026-12-31
- duplicate dates removed: 0
- % missing overall: 46.92

| column | % missing |
|---|---|
| event_size | 0.0 |
| n_events | 0.0 |
| event_name | 93.84 |
| event_types | 93.84 |

## Notes

- event rows in manual file: 183 on 182 days; events: 25
- days with event_size 3 / 2 / 1: 12 / 64 / 106
- rows outside the daily range (ignored): 0
- event_name / event_types are empty on days without an event (by design).
- Cancelled years (COVID 2020/2021) are simply absent: event_size = 0 on those days.


## Data check: features.parquet

- rows: 17088 (2848 delivery days x 6 blocks)
- columns: 292
- delivery dates: 2019-01-15 -> 2026-11-01 (local Europe/Zurich days)
- hours_in_block values: [3, 4, 5]
- built by `src/features/build_features.py`; column meaning in `docs/data_dictionary_features.md`
- weather_is_forecast = 1 on 35.7 % of rows (ICON forecasts from 2024-01-21; before, hybrid weather = observed, documented limitation)
- expected late starts: `*_fc` (ICON) before 2024-01-21, `charging_kw_zh`/`stations_zh_count` before 2020-12-15, `demand_lag_364d_same_block` before 2020-01, `eu_*` if the file is missing

## Columns with > 1 % NaN (whole table)

| column | NaN % | NaN % from 2019-02-15 |
|---|---|---|
| eu_wind_cubed_de_north_safe | 65.28 | 64.90 |
| eu_wind100_ms_de_north_safe | 65.28 | 64.90 |
| eu_wind_cubed_de_central_safe | 65.28 | 64.90 |
| eu_wind_cubed_de_northeast_safe | 65.28 | 64.90 |
| eu_wind100_ms_de_central_safe | 65.28 | 64.90 |
| eu_wind100_ms_de_northeast_safe | 65.28 | 64.90 |
| eu_wind_cubed_de_mean_safe | 65.28 | 64.90 |
| eu_wind100_ms_de_north_safe_day | 65.27 | 64.89 |
| eu_wind100_ms_de_northeast_safe_day | 65.27 | 64.89 |
| eu_wind_cubed_de_central_safe_day | 65.27 | 64.89 |
| eu_wind_cubed_de_northeast_safe_day | 65.27 | 64.89 |
| eu_wind_cubed_de_north_safe_day | 65.27 | 64.89 |
| eu_wind_cubed_de_mean_safe_day | 65.27 | 64.89 |
| eu_wind100_ms_de_central_safe_day | 65.27 | 64.89 |
| temp_day_mean_fc | 64.33 | 63.93 |
| eu_radiation_wm2_de_mean_safe | 64.33 | 63.93 |
| sunshine_day_sum_fc | 64.33 | 63.93 |
| radiation_day_mean_fc | 64.33 | 63.93 |
| eu_radiation_wm2_de_north_safe | 64.33 | 63.93 |
| temp_day_max_fc | 64.33 | 63.93 |
| temp_day_min_fc | 64.33 | 63.93 |
| eu_radiation_wm2_ch_bern_safe | 64.33 | 63.93 |
| eu_radiation_wm2_ch_alps_safe | 64.33 | 63.93 |
| eu_radiation_wm2_it_milan_safe | 64.33 | 63.93 |
| eu_radiation_wm2_de_south_safe | 64.33 | 63.93 |
| eu_radiation_wm2_de_central_safe | 64.33 | 63.93 |
| eu_radiation_wm2_de_northeast_safe | 64.33 | 63.93 |
| sunshine_min_fc | 64.30 | 63.91 |
| wind_ms_fc | 64.30 | 63.91 |
| radiation_wm2_fc | 64.30 | 63.91 |
| temp_c_fc | 64.30 | 63.91 |
| cloud_pct_fc | 64.30 | 63.91 |
| precip_mm_fc | 64.30 | 63.91 |
| cooling_degree_fc | 64.30 | 63.91 |
| temp_c_sq_fc | 64.30 | 63.91 |
| heating_degree_fc | 64.30 | 63.91 |
| temp_change_fc_vs_dm1_fc | 64.30 | 63.91 |
| humidity_pct_fc | 64.30 | 63.91 |
| eu_temp_c_fr_mean_safe | 64.30 | 63.90 |
| eu_temp_c_de_north_safe | 64.30 | 63.90 |
| eu_temp_c_de_northeast_safe | 64.30 | 63.90 |
| eu_precip_mm_ch_alps_safe | 64.30 | 63.90 |
| eu_temp_c_ch_bern_safe | 64.30 | 63.90 |
| eu_temp_c_ch_alps_safe | 64.30 | 63.90 |
| eu_temp_c_it_milan_safe | 64.30 | 63.90 |
| eu_temp_c_fr_lyon_safe | 64.30 | 63.90 |
| eu_temp_c_fr_paris_safe | 64.30 | 63.90 |
| eu_temp_c_de_south_safe | 64.30 | 63.90 |
| eu_temp_c_de_central_safe | 64.30 | 63.90 |
| eu_radiation_wm2_de_south_safe_day | 64.29 | 63.90 |
| eu_temp_c_it_milan_safe_day | 64.29 | 63.90 |
| eu_radiation_wm2_de_northeast_safe_day | 64.29 | 63.90 |
| eu_radiation_wm2_de_north_safe_day | 64.29 | 63.90 |
| eu_temp_c_de_northeast_safe_day | 64.29 | 63.90 |
| eu_temp_c_ch_bern_safe_day | 64.29 | 63.90 |
| eu_temp_c_fr_mean_safe_day | 64.29 | 63.90 |
| eu_radiation_wm2_ch_alps_safe_day | 64.29 | 63.90 |
| eu_temp_c_ch_alps_safe_day | 64.29 | 63.90 |
| eu_radiation_wm2_de_mean_safe_day | 64.29 | 63.90 |
| eu_temp_c_de_north_safe_day | 64.29 | 63.90 |
| eu_radiation_wm2_it_milan_safe_day | 64.29 | 63.90 |
| eu_temp_c_fr_lyon_safe_day | 64.29 | 63.90 |
| eu_temp_c_fr_paris_safe_day | 64.29 | 63.90 |
| eu_temp_c_de_south_safe_day | 64.29 | 63.90 |
| eu_temp_c_de_central_safe_day | 64.29 | 63.90 |
| eu_radiation_wm2_ch_bern_safe_day | 64.29 | 63.90 |
| eu_precip_mm_ch_alps_safe_day | 64.29 | 63.90 |
| eu_radiation_wm2_de_central_safe_day | 64.29 | 63.90 |
| stations_zh_count | 24.61 | 23.78 |
| charging_kw_zh | 24.61 | 23.78 |
| demand_lag_364d_same_block | 12.29 | 11.32 |

## NaN share per column

| column | NaN % | NaN % from 2019-02-15 |
|---|---|---|
| delivery_date | 0.000 | 0.000 |
| block | 0.000 | 0.000 |
| block_start_utc | 0.000 | 0.000 |
| hours_in_block | 0.000 | 0.000 |
| forecast_issue_time_utc | 0.000 | 0.000 |
| demand_mw | 0.000 | 0.000 |
| price_eur_mwh | 0.000 | 0.000 |
| actual_demand_mwh | 0.000 | 0.000 |
| actual_price_min_block | 0.000 | 0.000 |
| actual_price_max_block | 0.000 | 0.000 |
| actual_cost_eur | 0.000 | 0.000 |
| actual_eurchf | 0.000 | 0.000 |
| demand_lag_2d_same_block | 0.000 | 0.000 |
| demand_lag_3d_same_block | 0.000 | 0.000 |
| demand_lag_7d_same_block | 0.000 | 0.000 |
| demand_lag_8d_same_block | 0.000 | 0.000 |
| demand_lag_14d_same_block | 0.000 | 0.000 |
| demand_lag_21d_same_block | 0.246 | 0.000 |
| demand_lag_28d_same_block | 0.492 | 0.000 |
| demand_lag_364d_same_block | 12.289 | 11.324 |
| demand_mean_same_block_same_weekday_4w | 0.000 | 0.000 |
| demand_day_mean_lag_2d | 0.000 | 0.000 |
| demand_day_mean_lag_7d | 0.000 | 0.000 |
| demand_mean_last_7d | 0.000 | 0.000 |
| demand_mean_last_28d | 0.000 | 0.000 |
| demand_day_max_lag_2d | 0.000 | 0.000 |
| demand_day_min_lag_2d | 0.000 | 0.000 |
| demand_dm1_block_0 | 0.000 | 0.000 |
| demand_dm1_block_1 | 0.000 | 0.000 |
| demand_dm1_block_2 | 0.000 | 0.000 |
| demand_dm1_block_3 | 0.000 | 0.000 |
| demand_dm1_block_4 | 0.000 | 0.000 |
| demand_dm1_block_5 | 0.000 | 0.000 |
| demand_trend_7d | 0.000 | 0.000 |
| expected_demand_proxy | 0.000 | 0.000 |
| temp_c_obs | 0.047 | 0.047 |
| temp_c_fc | 64.302 | 63.910 |
| radiation_wm2_obs | 0.000 | 0.000 |
| radiation_wm2_fc | 64.302 | 63.910 |
| sunshine_min_obs | 0.000 | 0.000 |
| sunshine_min_fc | 64.302 | 63.910 |
| wind_ms_obs | 0.006 | 0.006 |
| wind_ms_fc | 64.302 | 63.910 |
| precip_mm_obs | 0.047 | 0.047 |
| precip_mm_fc | 64.302 | 63.910 |
| cloud_pct_fc | 64.302 | 63.910 |
| humidity_pct_obs | 0.047 | 0.047 |
| humidity_pct_fc | 64.302 | 63.910 |
| temp_c_fc_jma | 0.000 | 0.000 |
| wind_ms_fc_jma | 0.000 | 0.000 |
| precip_mm_fc_jma | 0.310 | 0.314 |
| cloud_pct_fc_jma | 0.076 | 0.077 |
| humidity_pct_fc_jma | 0.076 | 0.077 |
| temp_day_mean_obs | 0.035 | 0.035 |
| temp_day_mean_fc | 64.326 | 63.933 |
| temp_day_min_obs | 0.035 | 0.035 |
| temp_day_min_fc | 64.326 | 63.933 |
| temp_day_max_obs | 0.035 | 0.035 |
| temp_day_max_fc | 64.326 | 63.933 |
| radiation_day_mean_obs | 0.000 | 0.000 |
| radiation_day_mean_fc | 64.326 | 63.933 |
| sunshine_day_sum_obs | 0.000 | 0.000 |
| sunshine_day_sum_fc | 64.326 | 63.933 |
| temp_day_mean_fc_jma | 0.000 | 0.000 |
| temp_day_min_fc_jma | 0.000 | 0.000 |
| temp_day_max_fc_jma | 0.000 | 0.000 |
| temp_c | 0.047 | 0.047 |
| radiation_wm2 | 0.000 | 0.000 |
| sunshine_min | 0.000 | 0.000 |
| wind_ms | 0.000 | 0.000 |
| precip_mm | 0.047 | 0.047 |
| humidity_pct | 0.047 | 0.047 |
| temp_day_mean | 0.035 | 0.035 |
| temp_day_min | 0.035 | 0.035 |
| temp_day_max | 0.035 | 0.035 |
| radiation_day_mean | 0.000 | 0.000 |
| sunshine_day_sum | 0.000 | 0.000 |
| cloud_pct | 0.000 | 0.000 |
| weather_is_forecast | 0.000 | 0.000 |
| temp_c_sq_obs | 0.047 | 0.047 |
| heating_degree_obs | 0.047 | 0.047 |
| cooling_degree_obs | 0.047 | 0.047 |
| temp_c_sq_fc | 64.302 | 63.910 |
| heating_degree_fc | 64.302 | 63.910 |
| cooling_degree_fc | 64.302 | 63.910 |
| temp_c_sq_fc_jma | 0.000 | 0.000 |
| heating_degree_fc_jma | 0.000 | 0.000 |
| cooling_degree_fc_jma | 0.000 | 0.000 |
| temp_c_sq | 0.047 | 0.047 |
| heating_degree | 0.047 | 0.047 |
| cooling_degree | 0.047 | 0.047 |
| temp_obs_mean_dm1 | 0.035 | 0.035 |
| temp_obs_mean_last_3d | 0.000 | 0.000 |
| temp_obs_mean_last_7d | 0.000 | 0.000 |
| temp_obs_same_block_lag_2d | 0.047 | 0.047 |
| radiation_obs_same_block_lag_2d | 0.000 | 0.000 |
| temp_obs_last_24h_mean | 0.000 | 0.000 |
| temp_change_fc_vs_dm1 | 0.094 | 0.095 |
| temp_change_fc_vs_dm1_obs | 0.094 | 0.095 |
| temp_change_fc_vs_dm1_fc | 64.302 | 63.910 |
| temp_change_fc_vs_dm1_fc_jma | 0.047 | 0.047 |
| solar_ch_mw_lag_2d_same_block | 0.000 | 0.000 |
| solar_ch_day_mean_lag_2d | 0.000 | 0.000 |
| ev_count_city | 0.000 | 0.000 |
| charging_kw_zh | 24.614 | 23.784 |
| stations_zh_count | 24.614 | 23.784 |
| weekday | 0.000 | 0.000 |
| month | 0.000 | 0.000 |
| day_of_year | 0.000 | 0.000 |
| is_weekend | 0.000 | 0.000 |
| is_holiday | 0.000 | 0.000 |
| is_half_holiday | 0.000 | 0.000 |
| is_bridge_day | 0.000 | 0.000 |
| is_school_holiday | 0.000 | 0.000 |
| is_christmas_period | 0.000 | 0.000 |
| days_to_next_holiday | 0.000 | 0.000 |
| days_since_last_holiday | 0.000 | 0.000 |
| event_size | 0.000 | 0.000 |
| n_events | 0.000 | 0.000 |
| home_game | 0.000 | 0.000 |
| is_dst_change_day | 0.000 | 0.000 |
| school_holiday_type | 0.000 | 0.000 |
| school_holiday_type_name | 0.000 | 0.000 |
| kickoff_hour_local | 0.000 | 0.000 |
| covid_stringency | 0.000 | 0.000 |
| week_of_year | 0.000 | 0.000 |
| year_frac | 0.000 | 0.000 |
| sin_doy | 0.000 | 0.000 |
| cos_doy | 0.000 | 0.000 |
| daylight_hours | 0.000 | 0.000 |
| is_holiday_prev_day | 0.000 | 0.000 |
| is_holiday_next_day | 0.000 | 0.000 |
| lag2d_was_holiday | 0.000 | 0.000 |
| lag7d_was_holiday | 0.000 | 0.000 |
| lag2d_is_weekend | 0.000 | 0.000 |
| is_working_day | 0.000 | 0.000 |
| price_lag_1d_same_block | 0.000 | 0.000 |
| price_lag_2d_same_block | 0.000 | 0.000 |
| price_lag_7d_same_block | 0.000 | 0.000 |
| price_lag_14d_same_block | 0.000 | 0.000 |
| price_mean_day_D | 0.000 | 0.000 |
| price_min_day_D | 0.000 | 0.000 |
| price_max_day_D | 0.000 | 0.000 |
| price_spread_day_D | 0.000 | 0.000 |
| price_std_day_D | 0.000 | 0.000 |
| price_dD_block_0 | 0.000 | 0.000 |
| price_dD_block_1 | 0.000 | 0.000 |
| price_dD_block_2 | 0.000 | 0.000 |
| price_dD_block_3 | 0.000 | 0.000 |
| price_dD_block_4 | 0.000 | 0.000 |
| price_dD_block_5 | 0.000 | 0.000 |
| price_mean_last_7d | 0.000 | 0.000 |
| price_mean_last_28d | 0.000 | 0.000 |
| price_std_last_7d | 0.000 | 0.000 |
| price_block_vs_day_ratio_last_7d | 0.000 | 0.000 |
| price_neg_hours_day_D | 0.000 | 0.000 |
| price_neg_hours_last_7d | 0.000 | 0.000 |
| price_lag_7d_day_mean | 0.000 | 0.000 |
| price_de_day_D_same_block | 0.000 | 0.000 |
| price_de_mean_day_D | 0.000 | 0.000 |
| spread_ch_de_day_D | 0.000 | 0.000 |
| spread_ch_de_mean_7d | 0.000 | 0.000 |
| price_fr_day_D_same_block | 0.000 | 0.000 |
| price_fr_mean_day_D | 0.000 | 0.000 |
| spread_ch_fr_day_D | 0.000 | 0.000 |
| spread_ch_fr_mean_7d | 0.000 | 0.000 |
| price_at_day_D_same_block | 0.000 | 0.000 |
| price_at_mean_day_D | 0.000 | 0.000 |
| spread_ch_at_day_D | 0.000 | 0.000 |
| spread_ch_at_mean_7d | 0.000 | 0.000 |
| price_it_day_D_same_block | 0.000 | 0.000 |
| price_it_mean_day_D | 0.000 | 0.000 |
| spread_ch_it_day_D | 0.000 | 0.000 |
| spread_ch_it_mean_7d | 0.000 | 0.000 |
| price_de_lag_7d_same_block | 0.000 | 0.000 |
| gas_ttf_d_1 | 0.000 | 0.000 |
| gas_ttf_change_5d | 0.000 | 0.000 |
| gas_ttf_mean_20d | 0.000 | 0.000 |
| co2_eua_d_1 | 0.000 | 0.000 |
| co2_staleness_days | 0.000 | 0.000 |
| eurchf_d_1 | 0.000 | 0.000 |
| clean_gas_cost | 0.000 | 0.000 |
| reservoir_fill_pct | 0.000 | 0.000 |
| reservoir_vs_median_pct | 0.000 | 0.000 |
| reservoir_change_1w | 0.000 | 0.000 |
| swiss_load_lag_2d_same_block | 0.070 | 0.071 |
| swiss_load_day_mean_lag_2d | 0.070 | 0.071 |
| swiss_nuclear_mw_lag_2d | 0.000 | 0.000 |
| swiss_hydro_ror_mw_lag_2d | 0.000 | 0.000 |
| swiss_hydro_storage_mw_lag_2d | 0.000 | 0.000 |
| swiss_hydro_pumped_mw_lag_2d | 0.000 | 0.000 |
| swiss_solar_mw_lag_2d_same_block | 0.000 | 0.000 |
| swiss_residual_load_lag_2d_same_block | 0.070 | 0.071 |
| swiss_net_import_mw_lag_2d | 0.000 | 0.000 |
| unverified_de_solar_fc | 0.000 | 0.000 |
| unverified_de_solar_fc_day | 0.000 | 0.000 |
| unverified_de_wind_onshore_fc | 0.000 | 0.000 |
| unverified_de_wind_onshore_fc_day | 0.000 | 0.000 |
| unverified_de_wind_offshore_fc | 0.000 | 0.000 |
| unverified_de_wind_offshore_fc_day | 0.000 | 0.000 |
| unverified_de_load_fc | 0.000 | 0.000 |
| unverified_de_load_fc_day | 0.000 | 0.000 |
| unverified_ch_solar_fc | 0.000 | 0.000 |
| unverified_ch_solar_fc_day | 0.000 | 0.000 |
| eu_temp_c_de_north_safe | 64.297 | 63.904 |
| eu_temp_c_de_north_safe_day | 64.291 | 63.898 |
| eu_temp_c_de_northeast_safe | 64.297 | 63.904 |
| eu_temp_c_de_northeast_safe_day | 64.291 | 63.898 |
| eu_temp_c_de_central_safe | 64.297 | 63.904 |
| eu_temp_c_de_central_safe_day | 64.291 | 63.898 |
| eu_temp_c_de_south_safe | 64.297 | 63.904 |
| eu_temp_c_de_south_safe_day | 64.291 | 63.898 |
| eu_temp_c_fr_paris_safe | 64.297 | 63.904 |
| eu_temp_c_fr_paris_safe_day | 64.291 | 63.898 |
| eu_temp_c_fr_lyon_safe | 64.297 | 63.904 |
| eu_temp_c_fr_lyon_safe_day | 64.291 | 63.898 |
| eu_temp_c_it_milan_safe | 64.297 | 63.904 |
| eu_temp_c_it_milan_safe_day | 64.291 | 63.898 |
| eu_temp_c_ch_alps_safe | 64.297 | 63.904 |
| eu_temp_c_ch_alps_safe_day | 64.291 | 63.898 |
| eu_temp_c_ch_bern_safe | 64.297 | 63.904 |
| eu_temp_c_ch_bern_safe_day | 64.291 | 63.898 |
| eu_radiation_wm2_de_north_safe | 64.326 | 63.933 |
| eu_radiation_wm2_de_north_safe_day | 64.291 | 63.898 |
| eu_radiation_wm2_de_northeast_safe | 64.326 | 63.933 |
| eu_radiation_wm2_de_northeast_safe_day | 64.291 | 63.898 |
| eu_radiation_wm2_de_central_safe | 64.326 | 63.933 |
| eu_radiation_wm2_de_central_safe_day | 64.291 | 63.898 |
| eu_radiation_wm2_de_south_safe | 64.326 | 63.933 |
| eu_radiation_wm2_de_south_safe_day | 64.291 | 63.898 |
| eu_radiation_wm2_it_milan_safe | 64.326 | 63.933 |
| eu_radiation_wm2_it_milan_safe_day | 64.291 | 63.898 |
| eu_radiation_wm2_ch_alps_safe | 64.326 | 63.933 |
| eu_radiation_wm2_ch_alps_safe_day | 64.291 | 63.898 |
| eu_radiation_wm2_ch_bern_safe | 64.326 | 63.933 |
| eu_radiation_wm2_ch_bern_safe_day | 64.291 | 63.898 |
| eu_wind100_ms_de_north_safe | 65.280 | 64.898 |
| eu_wind100_ms_de_north_safe_day | 65.274 | 64.892 |
| eu_wind100_ms_de_northeast_safe | 65.280 | 64.898 |
| eu_wind100_ms_de_northeast_safe_day | 65.274 | 64.892 |
| eu_wind100_ms_de_central_safe | 65.280 | 64.898 |
| eu_wind100_ms_de_central_safe_day | 65.274 | 64.892 |
| eu_precip_mm_ch_alps_safe | 64.297 | 63.904 |
| eu_precip_mm_ch_alps_safe_day | 64.291 | 63.898 |
| eu_wind_cubed_de_north_safe | 65.280 | 64.898 |
| eu_wind_cubed_de_north_safe_day | 65.274 | 64.892 |
| eu_wind_cubed_de_northeast_safe | 65.280 | 64.898 |
| eu_wind_cubed_de_northeast_safe_day | 65.274 | 64.892 |
| eu_wind_cubed_de_central_safe | 65.280 | 64.898 |
| eu_wind_cubed_de_central_safe_day | 65.274 | 64.892 |
| eu_wind_cubed_de_mean_safe | 65.280 | 64.898 |
| eu_wind_cubed_de_mean_safe_day | 65.274 | 64.892 |
| eu_temp_c_fr_mean_safe | 64.297 | 63.904 |
| eu_temp_c_fr_mean_safe_day | 64.291 | 63.898 |
| eu_radiation_wm2_de_mean_safe | 64.326 | 63.933 |
| eu_radiation_wm2_de_mean_safe_day | 64.291 | 63.898 |
| eu_temp_c_de_north_jma_safe | 0.000 | 0.000 |
| eu_temp_c_de_north_jma_safe_day | 0.000 | 0.000 |
| eu_temp_c_de_northeast_jma_safe | 0.000 | 0.000 |
| eu_temp_c_de_northeast_jma_safe_day | 0.000 | 0.000 |
| eu_temp_c_de_central_jma_safe | 0.000 | 0.000 |
| eu_temp_c_de_central_jma_safe_day | 0.000 | 0.000 |
| eu_temp_c_de_south_jma_safe | 0.000 | 0.000 |
| eu_temp_c_de_south_jma_safe_day | 0.000 | 0.000 |
| eu_temp_c_fr_paris_jma_safe | 0.000 | 0.000 |
| eu_temp_c_fr_paris_jma_safe_day | 0.000 | 0.000 |
| eu_temp_c_fr_lyon_jma_safe | 0.000 | 0.000 |
| eu_temp_c_fr_lyon_jma_safe_day | 0.000 | 0.000 |
| eu_temp_c_it_milan_jma_safe | 0.000 | 0.000 |
| eu_temp_c_it_milan_jma_safe_day | 0.000 | 0.000 |
| eu_temp_c_ch_alps_jma_safe | 0.000 | 0.000 |
| eu_temp_c_ch_alps_jma_safe_day | 0.000 | 0.000 |
| eu_temp_c_ch_bern_jma_safe | 0.000 | 0.000 |
| eu_temp_c_ch_bern_jma_safe_day | 0.000 | 0.000 |
| eu_wind10_ms_de_north_jma_safe | 0.000 | 0.000 |
| eu_wind10_ms_de_north_jma_safe_day | 0.000 | 0.000 |
| eu_wind10_ms_de_northeast_jma_safe | 0.000 | 0.000 |
| eu_wind10_ms_de_northeast_jma_safe_day | 0.000 | 0.000 |
| eu_wind10_ms_de_central_jma_safe | 0.000 | 0.000 |
| eu_wind10_ms_de_central_jma_safe_day | 0.000 | 0.000 |
| eu_precip_mm_ch_alps_jma_safe | 0.310 | 0.314 |
| eu_precip_mm_ch_alps_jma_safe_day | 0.000 | 0.000 |
| eu_wind_cubed_de_north_jma_safe | 0.000 | 0.000 |
| eu_wind_cubed_de_north_jma_safe_day | 0.000 | 0.000 |
| eu_wind_cubed_de_northeast_jma_safe | 0.000 | 0.000 |
| eu_wind_cubed_de_northeast_jma_safe_day | 0.000 | 0.000 |
| eu_wind_cubed_de_central_jma_safe | 0.000 | 0.000 |
| eu_wind_cubed_de_central_jma_safe_day | 0.000 | 0.000 |
| eu_wind_cubed_de_mean_jma_safe | 0.000 | 0.000 |
| eu_wind_cubed_de_mean_jma_safe_day | 0.000 | 0.000 |
| eu_temp_c_fr_mean_jma_safe | 0.000 | 0.000 |
| eu_temp_c_fr_mean_jma_safe_day | 0.000 | 0.000 |


## Data check: football_daily

- rows: 2953
- first date: 2018-12-01  (local Europe/Zurich calendar day)
- last date: 2026-12-31
- duplicate dates removed: 0
- % missing overall: 45.65

| column | % missing |
|---|---|
| home_game | 0.0 |
| n_home_games | 0.0 |
| kickoff_hour_local | 91.3 |
| home_team | 91.3 |

## Notes

- file covers seasons 2012/2013 .. 2026/2027; last listed Zurich home game: 2026-11-07 (games after the download date are missing; the table is only complete up to then)
- home games in range: 257 (Zurich 146, Grasshoppers 111); missing kick-off times: 0
- days with 2 home games: 0
- Time column read as UK time and converted to Europe/Zurich (+1 h).
- Only Super League games: Swiss Cup and European home games are NOT included.
- kickoff_hour_local / home_team are empty on days without a home game (by design).


## Data check: gas_ttf_daily

- source: Yahoo Finance `TTF=F` (UNOFFICIAL fallback; HSG LSEG/Bloomberg export not available)
- rows: 2003 trading days (raw bars 2006, 3 with null close dropped, 0 duplicate dates dropped)
- first: 2018-12-03  last: 2026-11-18
- range: min 3.51, max 339.20 EUR/MWh (max on 2022-08-26)
- gaps > 4 calendar days (before date shown): 1 → 2024-04-02
- daily moves > 30%: 4 → 2019-09-30=16.4, 2022-02-24=134.3, 2022-03-02=165.5, 2026-03-02=44.5
- available_from_utc = trading day 18:00 Europe/Zurich (after ICE Endex settlement); use only rows with available_from_utc <= forecast time


## Check: price_ch_hourly.parquet (Energy-Charts day-ahead, bzn=CH)

- rows: 69144 hourly rows
- first / last timestamp_utc: 2018-12-31 23:00:00+00:00 / 2026-11-20 22:00:00+00:00
- missing hours (NaN price), whole file: 0 (0.0000%)
- missing hours 2019-01-01 → 2026-10-31 UTC: 0
- duplicate timestamps removed (overlap of yearly chunks): 0
- null prices in raw JSON: 0
- first 15-min value in source (UTC): 2026-11-03 23:00:00+00:00; hours after that are the mean of 4 quarter-hours
- incomplete hours in the 15-min era (<4 values): 0
- price range: min -463.68, max 871.61, mean 111.61 EUR/MWh
- hours with negative price: 1044

## Gaps (runs of missing hours)

none

## Mean price per year (EUR/MWh)

| year | mean | min | max |
|---|---|---|---|
| 2018 | 50.3 | 50.3 | 50.3 |
| 2019 | 40.9 | -39.5 | 108.1 |
| 2020 | 34.0 | -59.6 | 126.7 |
| 2021 | 114.9 | -79.4 | 532.2 |
| 2022 | 281.6 | -1.0 | 871.6 |
| 2023 | 107.5 | -142.9 | 268.8 |
| 2024 | 76.0 | -427.5 | 310.6 |
| 2025 | 101.7 | -262.2 | 318.0 |
| 2026 | 139.8 | -463.7 | 596.7 |


## Data check: price_neighbours_hourly

- file: `data/processed/price_neighbours_hourly.parquet`
- rows: 69095 (hourly, UTC, interval start)
- first: 2019-01-01 00:00:00+00:00  last: 2026-11-18 22:00:00+00:00
- duplicates removed: overlapping chunk timestamps dropped (keep last); 15-min averaged to hourly
- raw resolution: hourly until 2025-09-30 22:00 UTC, 15-min from 2025-09-30 22:00 UTC (SDAC 15-min MTU, delivery day 1 Oct 2025) → mean of 4 quarter-hours
- publication: delivery day D values known from D-1 ~13:00 Europe/Zurich (SDAC results); at forecast time D 10:00 only delivery hours up to end of local day D may be used
- price_de_eur_mwh: missing 0.000% in 2019-01-01→2026-11-01 (0 h), min -500.0, max 936.3, mean 96.9
- price_fr_eur_mwh: missing 0.000% in 2019-01-01→2026-11-01 (0 h), min -496.9, max 2987.8, mean 95.5
- price_at_eur_mwh: missing 0.000% in 2019-01-01→2026-11-01 (0 h), min -500.0, max 1965.9, mean 106.5
- price_it_north_eur_mwh: missing 0.000% in 2019-01-01→2026-11-01 (0 h), min 0.0, max 871.0, mean 128.0


## Data check: reservoir_weekly

- rows: 1403 weeks; first 2000-01-03 last 2026-11-16; duplicates dropped 0
- weekday of measure_date (0=Mon): {0: 1403}  (date = Monday 00:00 = Sunday 24h value)
- gaps != 7 days: 0
- fill % range: 8.3 – 96.2; max capacity changes over time: [8500.0, 8505.0, 8510.0, 8515.0, 8520.0, 8540.0, 8560.0, 8765.0, 8770.0, 8775.0, 8780.0, 8795.0, 8800.0, 8805.0, 8820.0, 8825.0, 8835.0, 8840.0, 8850.0, 8855.0, 8865.0, 8870.0, 8880.0, 8885.0, 8895.0, 8900.0]
- missing: {'reservoir_median_pct_same_week': 52, 'reservoir_vs_median_pct': 52} (median is NaN for year 2000: no earlier history)
- available_from_utc = measure_date (Monday) + 3 days at 23:59 Europe/Zurich = Thursday end of day (the federal energy dashboard states Thursday publication; file was last modified Tue 2026-11-17 14:22 GMT for the 2026-11-16 value)


## Check: swiss_power_hourly.parquet (Energy-Charts public_power, country=ch)

- rows: 69106 hourly rows
- first / last timestamp_utc: 2018-12-31 23:00:00+00:00 / 2026-11-19 08:00:00+00:00
- duplicate timestamps: 0
- source series names: Cross border electricity trading, Hydro Run-of-River, Hydro pumped storage, Hydro water reservoir, Load, Nuclear, Others, Renewable share of generation, Renewable share of load, Residual load, Solar, Wind onshore (the 'share' series are % and were dropped)
- load_bad hours: 130 (0.188%); before 2026-11-01: 48
- solar_bad hours: 1; wind_bad hours: 2 (['2021-03-31 22:00:00+00:00', '2026-11-19 08:00:00+00:00'])
- load_bad rule: missing, ≤ 0, constant ≥ 6 h, < 50 % or > 200 % of the centred 7-day median, or on/after 2026-11-16 (known Energy-Charts glitch); a local day with ≥ 6 bad hours is flagged completely

## Missing share and constant stretches per column

| column | % missing | hours with value 0 | hours in constant runs ≥ 6 h (value ≠ 0) | min | max |
|---|---|---|---|---|---|
| cross_border_trading_mw | 0.000% | 2 | 14 | -8812.9 | 6129.1 |
| nuclear_mw | 0.000% | 1 | 0 | 0.0 | 3333.1 |
| hydro_run_of_river_mw | 0.000% | 0 | 0 | 331.5 | 4682.1 |
| hydro_water_reservoir_mw | 0.000% | 0 | 0 | 55.8 | 7480.5 |
| hydro_pumped_storage_mw | 0.000% | 11 | 6 | 0.0 | 2833.1 |
| others_mw | 0.000% | 0 | 69106 | 337.5 | 487.5 |
| wind_onshore_mw | 0.001% | 1051 | 25 | 0.0 | 11000.0 |
| solar_mw | 0.001% | 31427 | 0 | 0.0 | 6630.1 |
| load_mw | 0.001% | 0 | 31 | 662.3 | 30073.3 |
| residual_load_mw | 0.001% | 0 | 0 | -4315.1 | 29942.6 |

## Load problems (runs of load_bad hours)

| first | last | hours |
|---|---|---|
| 2023-02-16 23:00:00+00:00 | 2023-02-17 22:00:00+00:00 | 24 |
| 2024-12-04 23:00:00+00:00 | 2024-12-05 22:00:00+00:00 | 24 |
| 2026-11-15 23:00:00+00:00 | 2026-11-19 08:00:00+00:00 | 82 |

## Solar problems (runs of solar_bad hours)

| first | last | hours |
|---|---|---|
| 2026-11-19 08:00:00+00:00 | 2026-11-19 08:00:00+00:00 | 1 |

## Yearly means (MW, local calendar year)

| year | cross_border_trading_mw | nuclear_mw | hydro_run_of_river_mw | hydro_water_reservoir_mw | hydro_pumped_storage_mw | others_mw | wind_onshore_mw | solar_mw | load_mw | residual_load_mw |
|---|---|---|---|---|---|---|---|---|---|---|
| 2019 | -558 | 2886 | 2021 | 2232 | 377 | 426 | 17 | 249 | 7492 | 7227 |
| 2020 | -539 | 2617 | 2009 | 2209 | 406 | 443 | 17 | 306 | 7374 | 7051 |
| 2021 | 450 | 2115 | 1936 | 2194 | 379 | 436 | 17 | 338 | 7691 | 7336 |
| 2022 | 562 | 2638 | 1768 | 1548 | 508 | 421 | 17 | 464 | 7751 | 7270 |
| 2023 | -614 | 2664 | 1997 | 2168 | 491 | 405 | 19 | 561 | 7574 | 6994 |
| 2024 | -1607 | 2616 | 2209 | 2855 | 439 | 410 | 19 | 679 | 7588 | 6890 |
| 2025 | -28 | 2098 | 1864 | 1939 | 476 | 405 | 18 | 907 | 7710 | 6785 |
| 2026 | 114 | 2241 | 1691 | 1355 | 447 | 412 | 17 | 1224 | 7934 | 6693 |

## Daily load and solar from 2026-11-01 (UTC days)

| day | load mean | load min | load max | load n | solar mean | solar max |
|---|---|---|---|---|---|---|
| 2026-11-01 | 7477 | 6826 | 7962 | 24 | 667 | 2756 |
| 2026-11-02 | 8602 | 7098 | 11160 | 24 | 542 | 2342 |
| 2026-11-03 | 8861 | 5628 | 11302 | 24 | 475 | 2055 |
| 2026-11-04 | 8871 | 6843 | 10210 | 24 | 529 | 2170 |
| 2026-11-05 | 8848 | 6968 | 10081 | 24 | 629 | 2708 |
| 2026-11-06 | 8568 | 5324 | 11532 | 24 | 237 | 1015 |
| 2026-11-07 | 7880 | 5618 | 11348 | 24 | 383 | 1754 |
| 2026-11-08 | 7531 | 6869 | 8517 | 24 | 642 | 2866 |
| 2026-11-09 | 8666 | 7001 | 10289 | 24 | 296 | 1242 |
| 2026-11-10 | 8524 | 4494 | 11175 | 24 | 479 | 2140 |
| 2026-11-11 | 8888 | 7534 | 10019 | 24 | 258 | 1036 |
| 2026-11-12 | 8623 | 5886 | 12095 | 24 | 163 | 787 |
| 2026-11-13 | 9190 | 6264 | 13072 | 24 | 550 | 2453 |
| 2026-11-14 | 8292 | 6568 | 10681 | 24 | 617 | 2660 |
| 2026-11-15 | 8286 | 7156 | 11227 | 24 | 450 | 2217 |
| 2026-11-16 | 9051 | 5088 | 25049 | 24 | 371 | 1958 |
| 2026-11-17 | 8569 | 662 | 24426 | 24 | 200 | 1106 |
| 2026-11-18 | 26862 | 23664 | 29655 | 24 | 447 | 2080 |
| 2026-11-19 | 27232 | 24631 | 30073 | 8 | 12 | 94 |


## Check: swiss_solar_forecast_hourly.parquet (Energy-Charts day-ahead solar forecast, CH)

- rows: 69120 hourly rows
- first / last timestamp_utc: 2018-12-31 23:00:00+00:00 / 2026-11-19 22:00:00+00:00
- first non-null value: 2018-12-31 23:00:00+00:00
- missing hours inside its range: 8 (0.012%)
- duplicate timestamps: 0

## Scale compared with actual solar (public_power Solar)

Ratio = sum of forecast / sum of actual over hours where both exist. Correlation = hourly Pearson correlation.

| year | hours | forecast mean MW | actual mean MW | ratio | forecast max | actual max | corr |
|---|---|---|---|---|---|---|---|
| 2019 | 8760 | 51 | 249 | 0.21 | 335 | 1584 | 0.973 |
| 2020 | 8784 | 37 | 306 | 0.12 | 229 | 1880 | 0.976 |
| 2021 | 8760 | 37 | 338 | 0.11 | 231 | 2283 | 0.966 |
| 2022 | 8760 | 33 | 464 | 0.07 | 232 | 2783 | 0.893 |
| 2023 | 8760 | 30 | 561 | 0.05 | 174 | 3552 | 0.910 |
| 2024 | 8784 | 696 | 679 | 1.02 | 4322 | 4661 | 0.962 |
| 2025 | 8757 | 649 | 908 | 0.71 | 4220 | 5773 | 0.957 |
| 2026 | 7732 | 735 | 1225 | 0.60 | 4288 | 6630 | 0.973 |

## By month (ratio forecast / actual)

| month | ratio | corr |
|---|---|---|
| 2019-01 | 0.21 | 0.924 |
| 2019-02 | 0.17 | 0.971 |
| 2019-03 | 0.18 | 0.979 |
| 2019-04 | 0.21 | 0.982 |
| 2019-05 | 0.20 | 0.979 |
| 2019-06 | 0.21 | 0.976 |
| 2019-07 | 0.20 | 0.981 |
| 2019-08 | 0.22 | 0.979 |
| 2019-09 | 0.22 | 0.953 |
| 2019-10 | 0.21 | 0.960 |
| 2019-11 | 0.22 | 0.956 |
| 2019-12 | 0.40 | 0.720 |
| 2020-01 | 0.13 | 0.947 |
| 2020-02 | 0.13 | 0.953 |
| 2020-03 | 0.13 | 0.968 |
| 2020-04 | 0.12 | 0.982 |
| 2020-05 | 0.12 | 0.981 |
| 2020-06 | 0.11 | 0.969 |
| 2020-07 | 0.12 | 0.983 |
| 2020-08 | 0.12 | 0.973 |
| 2020-09 | 0.11 | 0.979 |
| 2020-10 | 0.11 | 0.950 |
| 2020-11 | 0.13 | 0.933 |
| 2020-12 | 0.17 | 0.907 |
| 2021-01 | 0.20 | 0.835 |
| 2021-02 | 0.15 | 0.919 |
| 2021-03 | 0.12 | 0.969 |
| 2021-04 | 0.11 | 0.986 |
| 2021-05 | 0.10 | 0.966 |
| 2021-06 | 0.10 | 0.967 |
| 2021-07 | 0.10 | 0.964 |
| 2021-08 | 0.11 | 0.959 |
| 2021-09 | 0.10 | 0.983 |
| 2021-10 | 0.11 | 0.966 |
| 2021-11 | 0.14 | 0.900 |
| 2021-12 | 0.15 | 0.900 |
| 2022-01 | 0.11 | 0.958 |
| 2022-02 | 0.09 | 0.966 |
| 2022-03 | 0.09 | 0.973 |
| 2022-04 | 0.09 | 0.973 |
| 2022-05 | 0.07 | 0.937 |
| 2022-06 | 0.08 | 0.908 |
| 2022-07 | 0.06 | 0.926 |
| 2022-08 | 0.04 | 0.883 |
| 2022-09 | 0.08 | 0.920 |
| 2022-10 | 0.07 | 0.885 |
| 2022-11 | 0.05 | 0.886 |
| 2022-12 | 0.06 | 0.725 |
| 2023-01 | 0.08 | 0.718 |
| 2023-02 | 0.05 | 0.863 |
| 2023-03 | 0.05 | 0.849 |
| 2023-04 | 0.05 | 0.860 |
| 2023-05 | 0.04 | 0.904 |
| 2023-06 | 0.05 | 0.943 |
| 2023-07 | 0.05 | 0.908 |
| 2023-08 | 0.06 | 0.909 |
| 2023-09 | 0.05 | 0.959 |
| 2023-10 | 0.06 | 0.909 |
| 2023-11 | 0.07 | 0.837 |
| 2023-12 | 0.05 | 0.739 |
| 2024-01 | 1.47 | 0.818 |
| 2024-02 | 0.95 | 0.926 |
| 2024-03 | 0.91 | 0.915 |
| 2024-04 | 1.08 | 0.957 |
| 2024-05 | 0.95 | 0.966 |
| 2024-06 | 1.02 | 0.969 |
| 2024-07 | 1.00 | 0.981 |
| 2024-08 | 0.96 | 0.981 |
| 2024-09 | 0.99 | 0.966 |
| 2024-10 | 1.01 | 0.941 |
| 2024-11 | 1.43 | 0.906 |
| 2024-12 | 1.54 | 0.875 |
| 2025-01 | 1.17 | 0.933 |
| 2025-02 | 1.31 | 0.923 |
| 2025-03 | 0.95 | 0.972 |
| 2025-04 | 0.58 | 0.984 |
| 2025-05 | 0.66 | 0.984 |
| 2025-06 | 0.68 | 0.988 |
| 2025-07 | 0.74 | 0.975 |
| 2025-08 | 0.65 | 0.986 |
| 2025-09 | 0.62 | 0.980 |
| 2025-10 | 0.65 | 0.939 |
| 2025-11 | 0.55 | 0.955 |
| 2025-12 | 0.73 | 0.917 |
| 2026-01 | 0.68 | 0.915 |
| 2026-02 | 0.45 | 0.965 |
| 2026-03 | 0.48 | 0.956 |
| 2026-04 | 0.48 | 0.977 |
| 2026-05 | 0.64 | 0.986 |
| 2026-06 | 0.68 | 0.980 |
| 2026-07 | 0.68 | 0.988 |
| 2026-08 | 0.63 | 0.988 |
| 2026-09 | 0.60 | 0.988 |
| 2026-10 | 0.56 | 0.982 |
| 2026-11 | 0.46 | 0.974 |


## Data check: weather_archive_hourly (Open-Meteo archive, ERA5 reanalysis)

- Rows: 69,479; timestamp_utc 2018-12-01 00:00:00+00:00 -> 2026-11-03 22:00:00+00:00
- Duplicates removed: 0
- Time shift: Open-Meteo stamp -1 h -> START of hour. Units: sunshine min, wind m/s.
- Reanalysis = not available at forecast time. Cross-check / gap filler only.

| column | missing | missing % |
|---|---|---|
| temp_c_era5 | 0 | 0.000% |
| radiation_wm2_era5 | 0 | 0.000% |
| sunshine_min_era5 | 0 | 0.000% |
| wind_ms_era5 | 0 | 0.000% |
| precip_mm_era5 | 0 | 0.000% |
| cloud_pct_era5 | 0 | 0.000% |
| humidity_pct_era5 | 0 | 0.000% |


## Data check: weather_europe_forecast_hourly (Open-Meteo previous-runs API, 9 European points)

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


## Data check: weather_forecast_hourly (Open-Meteo previous-runs API)

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


## Weather check: forecast vs observed (MeteoSwiss SMA Zürich-Fluntern)

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


## Data check: weather_observed_hourly (MeteoSwiss SMA Zürich-Fluntern)

- Rows: 69,839 (hourly, complete UTC grid)
- First / last timestamp_utc: 2018-12-01 00:00:00+00:00 / 2026-11-18 22:00:00+00:00
- Duplicates removed after joining historical + recent files: 0
- Time shift: MeteoSwiss hourly stamp = END of interval -> shifted -1 h to START of hour.
- Gaps <= 3 h linearly interpolated (flag column `<col>_interpolated`), longer gaps left NaN.

| column | missing before fill | missing before fill % | filled (<=3 h) | still missing | still missing % | long gaps (>3 h) |
|---|---|---|---|---|---|---|
| temp_c | 33 | 0.047% | 0 | 33 | 0.047% | 1 |
| sunshine_min | 0 | 0.000% | 0 | 0 | 0.000% | 0 |
| radiation_wm2 | 0 | 0.000% | 0 | 0 | 0.000% | 0 |
| wind_ms | 7 | 0.010% | 0 | 7 | 0.010% | 1 |
| precip_mm | 34 | 0.049% | 0 | 34 | 0.049% | 1 |
| humidity_pct | 33 | 0.047% | 0 | 33 | 0.047% | 1 |

## Gaps longer than 3 h (left as NaN)

- `temp_c`: 2021-05-15 13:00:00+00:00 -> 2021-05-16 21:00:00+00:00 (33 h)
- `wind_ms`: 2026-08-17 06:00:00+00:00 -> 2026-08-17 12:00:00+00:00 (7 h)
- `precip_mm`: 2021-05-15 13:00:00+00:00 -> 2021-05-16 22:00:00+00:00 (34 h)
- `humidity_pct`: 2021-05-15 13:00:00+00:00 -> 2021-05-16 21:00:00+00:00 (33 h)

## Gaps of 1-3 h (interpolated)

- `temp_c`: 0 gaps, 0 hours
- `sunshine_min`: 0 gaps, 0 hours
- `radiation_wm2`: 0 gaps, 0 hours
- `wind_ms`: 0 gaps, 0 hours
- `precip_mm`: 0 gaps, 0 hours
- `humidity_pct`: 0 gaps, 0 hours
