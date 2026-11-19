# Data dictionary (consolidated)

Every processed table and every column of the feature table, with unit, source, time convention and when the value is
known. Merged from the per-step fragments `docs/data_dictionary_*.md` (kept in place; the app reads them). Corrections
made while merging are marked *(updated)*. Assumptions behind the rules: `docs/assumptions.md`; sources and URLs:
`docs/data_sources.md`.

**Conventions for all tables**

- `timestamp_utc` is tz-aware UTC and marks the **start** of the interval. Daily tables use `date` = local
  Europe/Zurich calendar day.
- Forecast time = day **D 10:00 Europe/Zurich**, delivery day **D+1** (Swiss gate closure 11:00 minus 1 hour).
- Blocks: 0 = 00–04, 1 = 04–08, 2 = 08–12, 3 = 12–16, 4 = 16–20, 5 = 20–24 local time; 3 or 5 hours on clock-change days.
- Units are in the column names where possible (`_mw`, `_mwh`, `_eur_mwh`, `_kwh_15min`, `_pct`, `_c`).

## Contents
1. Targets and Swiss system data (`demand_ewz*`, `price_ch_hourly`, `swiss_power_hourly`, `swiss_solar_forecast_hourly`)
2. Weather, Zurich (`weather_observed_hourly`, `weather_forecast_hourly`, `weather_archive_hourly`)
3. Weather, Europe (`weather_europe_forecast_hourly`)
4. Calendar, EVs, events, football (`calendar_features_daily` and its parts)
5. Price drivers (`price_neighbours_hourly`, gas, CO₂, reservoirs, EUR/CHF, German forecasts)
6. Feature table (`features.parquet`) and `hourly_actuals.parquet`
7. Result files (predictions, backtest)


## 1. Targets and Swiss system data

*From `docs/data_dictionary_targets.md`.*

All timestamps are tz-aware UTC (`datetime64[ns, UTC]`) and mark the **start** of the interval.
"Publication lag" = when the value can be known, as far as we could observe it (see `docs/assumptions_targets.md`).

### `data/processed/demand_ewz.parquet` (15 min)

| column | unit | source | time convention | publication lag |
|---|---|---|---|---|
| `timestamp_utc` | – | ewz Bruttolastgang `zeitpunkt` | source = local END label; converted to UTC, −15 min → start of the 15-min interval | – |
| `load_kwh_15min` | kWh per 15 min | ewz Bruttolastgang Stadt Zürich (data.stadt-zuerich.ch, CC0) | energy delivered in the interval | file updated daily; on 2026-11-19 09:05 it held data up to the end of 2026-11-17 (≈ 1.5 days). Values may be revised for up to 6 months. *(updated: the features assume the DSO knows its own demand up to the end of D−1)* |
| `status` | – | ewz | `E` substitute value, `F` not yet checked, `W` final (none present); NaN for filled rows | as above |
| `is_filled` | bool | – | True where the value did not come from the Bruttolastgang file | – |
| `fill_method` | – | – | `netzebenen` = taken from ewz Netzebenen NE5+NE7 (UTC file), `interpolated` = linear (gaps ≤ 1 h), empty = original | – |

### `data/processed/demand_ewz_hourly.parquet` (1 h)

| column | unit | source | time convention | publication lag |
|---|---|---|---|---|
| `timestamp_utc` | – | derived | start of the UTC hour | – |
| `load_mw` | MW | derived from `load_kwh_15min` | mean power over the hour = sum of 4 × kWh / 1000; NaN if fewer than 4 intervals | as 15-min file |
| `n_intervals` | count | derived | number of 15-min values in the hour (4 everywhere) | – |
| `share_non_final` | share 0–1 | derived | share of the 4 intervals with status ≠ W (1.0 everywhere, because no W exists) | – |
| `share_status_f` | share 0–1 | derived | share of the 4 intervals with status F (not yet checked) | – |
| `n_filled` | count | derived | intervals in the hour that were filled | – |

### `data/processed/price_ch_hourly.parquet` (1 h)

| column | unit | source | time convention | publication lag |
|---|---|---|---|---|
| `timestamp_utc` | – | Energy-Charts `price?bzn=CH` `unix_seconds` | start of the delivery hour, UTC | – |
| `price_eur_mwh` | EUR/MWh | Energy-Charts (CC BY 4.0), EPEX SPOT day-ahead CH | hourly price; from 2026-11-03 23:00 UTC (= 4 Nov 00:00 local) the mean of the four 15-min prices | prices for day D+1 are known after the CH day-ahead auction on day D (gate closure 11:00, results around noon). The file contains D+1 already (last row 2026-11-20 22:00 UTC) |
| `n_values` | count | derived | number of source values averaged (1 = hourly source, 4 = 15-min source) | – |

### `data/processed/swiss_power_hourly.parquet` (1 h)

Source: Energy-Charts `public_power?country=ch` (CC BY 4.0). All values are mean MW over the UTC hour starting at `timestamp_utc`. Near real-time; values for a past day are available on the same day.

| column | unit | description | notes |
|---|---|---|---|
| `timestamp_utc` | – | start of the hour, UTC | – |
| `load_mw` | MW | Swiss load | broken from 2026-11-16 (values up to 30 GW); bad days 2023-02-17 and 2024-12-05 → use `load_bad` |
| `residual_load_mw` | MW | load minus wind and solar | inherits load problems |
| `solar_mw` | MW | Swiss solar production (actual) | 0 at night |
| `wind_onshore_mw` | MW | Swiss wind | one spike of 11,000 MW on 2021-03-31 22:00 UTC (`wind_bad`) |
| `hydro_run_of_river_mw` | MW | run-of-river hydro | – |
| `hydro_water_reservoir_mw` | MW | reservoir (storage) hydro | – |
| `hydro_pumped_storage_mw` | MW | pumped-storage generation | consumption is not reported for CH |
| `nuclear_mw` | MW | nuclear | – |
| `others_mw` | MW | others | piecewise constant (2–11 distinct values per year, not measured hourly) – do not use as a feature |
| `cross_border_trading_mw` | MW | net cross-border exchange (sign as delivered by Energy-Charts; positive mostly in winter = import) | – |
| `load_bad` | bool | True = do not use `load_mw` | rule in the check file |
| `solar_bad` | bool | True = solar missing or constant > 0 for ≥ 6 h | – |
| `wind_bad` | bool | True = wind missing or > 500 MW | – |

### `data/processed/swiss_solar_forecast_hourly.parquet` (1 h)

| column | unit | source | time convention | publication lag |
|---|---|---|---|---|
| `timestamp_utc` | – | Energy-Charts `public_power_forecast?country=ch&production_type=solar&forecast_type=day-ahead` | start of the hour, UTC | not documented by Energy-Charts and not verified *(updated: therefore only stored as `unverified_ch_solar_fc*`, never a default feature)* |
| `solar_forecast_mw` | MW | same | day-ahead forecast of Swiss solar | **scale changes**: 5–21 % of actual solar 2019–2023, ≈ 100 % in 2024, 60–70 % in 2025–2026 (see check file) |

## 2. Weather, Zurich

*From `docs/data_dictionary_weather.md`.*

All files: one row per UTC hour, `timestamp_utc` = tz-aware UTC, **START** of the hour the value describes.
Built by `src/data/load_meteoswiss.py`, `src/data/load_openmeteo_forecast.py`, `src/data/load_openmeteo_archive.py`
(bias correction in `src/data/check_weather_forecast.py`).

### `data/processed/weather_observed_hourly.parquet` (MeteoSwiss SMA Zürich-Fluntern, 2018-12-01 → 2026-11-18)

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

### `data/processed/weather_forecast_hourly.parquet` (Open-Meteo previous-runs API, 2018-12-01 → 2026-11-03 22:00)

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

### `data/processed/weather_archive_hourly.parquet` (Open-Meteo archive, ERA5, 2018-12-01 → 2026-11-03 22:00)

| column | unit | source | time convention | publication lag |
|---|---|---|---|---|
| temp_c_era5, radiation_wm2_era5, sunshine_min_era5, wind_ms_era5, precip_mm_era5, cloud_pct_era5, humidity_pct_era5 | as above | Open-Meteo archive API, `models=era5`, 47.378 N 8.565 E | as forecast file (stamp −1 h) | ~5 days; reanalysis → **never a D+1 input**, cross-check / gap filler only |

## 3. Weather, Europe

*From `docs/data_dictionary_weather_europe.md`.*

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

### `data/processed/weather_europe_forecast_hourly.parquet`

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

### `data/processed/weather_europe_forecast_raw_hourly.parquet` (checks only, NOT a model input)

| column | meaning |
|---|---|
| timestamp_utc | as above |
| `<base>_<point>_day1[_jma]`, `<base>_<point>_day2[_jma]` | Open-Meteo `_previous_day1/2` values (converted units) |
| `safe_lead_days`, `safe_lead_days_jma` | lead (1 or 2) picked for `*_safe` (ICON, JMA) |

## 4. Calendar, EVs, events, football

*From `docs/data_dictionary_calendar.md`.*

All tables are **daily**, keyed by `date` = **local Europe/Zurich calendar day** (plain date, no time zone),
one row per day from **2018-12-01 to 2026-12-31**, no gaps. `calendar_features_daily.parquet` holds all columns below
in one table.

"Lag" = when the value is known. "In advance" = known long before the day (calendar, fixtures, announced events).
Columns marked **not for features** use information published later; use the `_known` column instead.

### calendar_daily.parquet (`src/data/load_calendar.py`)

| column | unit / values | source | time convention | publication lag |
|---|---|---|---|---|
| weekday | 0 = Mon … 6 = Sun | computed | local day | in advance |
| month | 1–12 | computed | local day | in advance |
| day_of_year | 1–366 | computed | local day | in advance |
| is_weekend | 0/1 (Sat, Sun) | computed | local day | in advance |
| is_holiday | 0/1 | `holidays.Switzerland(subdiv="ZH")` + Berchtoldstag 2 Jan | local day | in advance |
| holiday_name | text, empty on normal days | as above | local day | in advance |
| is_half_holiday | 0/1 (afternoon off in the city) | Sechseläuten Monday, Knabenschiessen Monday; dates from the Stadt Zürich school calendar | local day | in advance |
| half_holiday_name | text, empty on normal days | as above | local day | in advance |
| is_bridge_day | 0/1 | computed: working day with a holiday on one side and a weekend/holiday on the other | local day | in advance |
| is_school_holiday | 0/1 | Stadt Zürich `schulferien.csv` (end date exclusive) | local day | in advance |
| school_holiday_type | christmas / sport / spring / summer / autumn / school_free_day; empty otherwise | keyword on `summary` | local day | in advance |
| days_to_next_holiday | days (0 on a holiday) | computed from is_holiday | local day | in advance |
| days_since_last_holiday | days (0 on a holiday) | computed from is_holiday | local day | in advance |
| is_christmas_period | 0/1 (24 Dec – 2 Jan) | computed | local day | in advance |
| is_dst_change_day | 0/1 | tz database Europe/Zurich | local day | in advance |
| hours_in_day | 23 / 24 / 25 hours | tz database | local day | in advance |
| covid_stringency | index 0–100, NaN outside 2020-01-01..2022-12-31 | OxCGRT `OxCGRT_compact_national_v1.csv`, CHE, `StringencyIndex_Average` | daily (national) | historical index; for 2020–2022 policy was announced before it applied (treat as known on the day) |
| covid_stringency_filled | index 0–100 | as above, 0 before 2020 and after 2022 | daily | as above |

### ev_daily.parquet (`src/data/load_ev.py`)

| column | unit | source | time convention | publication lag |
|---|---|---|---|---|
| ev_count_city | electric cars (count), interpolated | Stadt Zürich VER200OD2001.csv, `Treibstoffart2Lang == "Elektrisch"`, summed over quarters & legal forms; points on 30 Sept, straight line between them; after 2025-09-30 extended with the last yearly slope | local day | **not for features** (uses values published up to ~10 months later) |
| ev_count_city_is_extrapolated | 0/1 | flag: date after the last 30 Sept point (2025-09-30) | local day | – |
| ev_count_city_known | electric cars (count) | same source; last published 30 Sept value + last published yearly growth (straight line) | local day | 30 Sept of year Y assumed public on **1 Aug of Y+1** |
| stations_zh_count | charging stations, canton Zurich | BFE `ich_tanke_strom_Kennzahlen_monatlich.csv`, `stations_ZH_count`; month value on last day of month, linear in between; NaN before 2020-11-30, held flat after 2026-10-31 | local day | **not for features** |
| stations_zh_count_known | charging stations | same, last published month carried forward | local day | month M public on the **15th of M+1** |
| charging_kw_zh | kW installed charging power, canton Zurich | BFE, `chargingPower_ZH_sum`; same handling as stations | local day | **not for features** |
| charging_kw_zh_known | kW | same, last published month carried forward | local day | month M public on the 15th of M+1 |
| charging_kw_zh_backcast | kW | observed (interpolated) where available; before 2020-11 a straight-line trend of the first 12 months, clipped at 0 (**synthetic**) | local day | **not for features** before 2020-12 (built with later data) |
| bfe_is_held_after_last_month | 0/1 | flag: date after the last BFE month (2026-10) | local day | – |

### events_daily.parquet (`src/data/load_events.py`, input `data/manual/events_zurich.csv`)

| column | unit | source | time convention | publication lag |
|---|---|---|---|---|
| event_size | 0 = none, 1 = small/medium, 2 = large (tens of thousands), 3 = huge (hundreds of thousands) – max over the day | hand-made table, one source URL per row | local day | in advance (events are announced months ahead) |
| n_events | count of distinct events that day | same | local day | in advance |
| event_name | names joined by " \| ", empty otherwise | same | local day | in advance |
| event_types | parade / festival / tradition / sport / concert / culture, joined by " \| " | same | local day | in advance |

`events_zurich.csv`: `date` (local day, one row per event day), `event`, `type`, `size` (1–3), `source_url`.

### football_daily.parquet (`src/data/load_football.py`)

| column | unit | source | time convention | publication lag |
|---|---|---|---|---|
| home_game | 0/1 | football-data.co.uk `SWZ.csv`, `Home` in {Zurich, Grasshoppers} | local day of kick-off | in advance (fixtures published weeks ahead) |
| n_home_games | count | same | local day | in advance |
| kickoff_hour_local | hour in Swiss local time, decimal (20.5 = 20:30), earliest game | `Time` column, which is **UK time** → converted to Europe/Zurich | local | in advance |
| home_team | Zurich / Grasshoppers | same | – | in advance |

### calendar_features_daily.parquet (`src/data/merge_calendar.py`)
Left join of the four tables above on `date`; same columns, one row per day.

## 5. Price drivers

*From `docs/data_dictionary_drivers.md`.*

Forecast time = day D 10:00 Europe/Zurich, delivery day D+1. Use a strict as-of join:
only rows with `available_from_utc <= forecast_issue_time` (daily/weekly tables).

| File | Column | Unit | Source | Time convention | Publication lag |
|---|---|---|---|---|---|
| price_neighbours_hourly | timestamp_utc | – | – | UTC, start of the hour, tz-aware | – |
| price_neighbours_hourly | price_de_eur_mwh | EUR/MWh | Energy-Charts `price?bzn=DE-LU` (SDAC/EPEX), CC BY 4.0 | hourly; mean of 4 quarter-hours from 1 Oct 2025 | delivery day − 1, ~13:00 CET → at D 10:00 only delivery hours up to end of local day D are known |
| price_neighbours_hourly | price_fr_eur_mwh | EUR/MWh | Energy-Charts `bzn=FR` | as above | as above |
| price_neighbours_hourly | price_at_eur_mwh | EUR/MWh | Energy-Charts `bzn=AT` | as above | as above |
| price_neighbours_hourly | price_it_north_eur_mwh | EUR/MWh | Energy-Charts `bzn=IT-North` | as above | as above |
| gas_ttf_daily | date | – | – | trading day (exchange calendar, NYMEX; US holidays missing) | – |
| gas_ttf_daily | gas_ttf_eur_mwh | EUR/MWh | Yahoo Finance `TTF=F` (**unofficial**) | daily close/settlement of front-month TTF | known from trading day 18:00 Zurich |
| gas_ttf_daily | available_from_utc | UTC timestamp | derived | date 18:00 Europe/Zurich in UTC | – |
| gas_ttf_daily | source | text | – | `yahoo_TTF=F_unofficial` | – |
| co2_eua_daily | date | – | – | auction day (only days with an auction) | – |
| co2_eua_daily | co2_eua_eur_t | EUR/tCO2 | EEX EUA primary-market auction reports (official) | volume-weighted mean clearing price of all auctions that day | known from auction day 12:00 Zurich (auction closes 11:00) |
| co2_eua_daily | n_auctions | count | EEX | auctions on that day | – |
| co2_eua_daily | available_from_utc | UTC timestamp | derived | date 12:00 Europe/Zurich in UTC | – |
| co2_eua_daily | source | text | – | `EEX_primary_auction` | – |
| reservoir_weekly | measure_date | – | BFE ogd17 `Datum` | Monday date = level on the preceding **Sunday 24:00** | – |
| reservoir_weekly | reservoir_gwh_ch | GWh | BFE | stored energy, all of Switzerland | known from measure_date + 3 days 23:59 Zurich (Thursday end of day) |
| reservoir_weekly | reservoir_max_gwh_ch | GWh | BFE | maximum storage capacity (changes over time) | same |
| reservoir_weekly | reservoir_fill_pct | % | derived | gwh_ch ÷ max_gwh_ch × 100 | same |
| reservoir_weekly | reservoir_gwh_{wallis,graubuenden,tessin,rest_ch} | GWh | BFE | regional stored energy | same |
| reservoir_weekly | reservoir_max_gwh_{region} | GWh | BFE | regional maximum | same |
| reservoir_weekly | reservoir_fill_pct_{region} | % | derived | regional gwh ÷ max × 100 | same |
| reservoir_weekly | iso_week | week no. | derived | ISO week of measure_date | – |
| reservoir_weekly | reservoir_median_pct_same_week | % | derived | median fill % of the same ISO week in years strictly before the row's ISO year (from 2000) | same |
| reservoir_weekly | reservoir_vs_median_pct | percentage points | derived | fill_pct − median | same |
| reservoir_weekly | available_from_utc | UTC timestamp | derived | measure_date + 3 d, 23:59 Zurich in UTC | – |
| eurchf_daily | date | – | – | ECB business day | – |
| eurchf_daily | chf_per_eur | CHF per EUR | ECB `EXR/D.CHF.EUR.SP00.A` | reference rate (14:15 CET concertation) | published ~16:00 CET same day |
| eurchf_daily | available_from_utc | UTC timestamp | derived | date 16:00 Europe/Zurich in UTC | – |
| de_forecasts_hourly | timestamp_utc | – | – | UTC, start of the hour | – |
| de_forecasts_hourly | solar_da_forecast_de_mw | MW (hourly mean) | Energy-Charts `public_power_forecast?country=de&production_type=solar&forecast_type=day-ahead` | mean of 4 quarter-hours | **unverified**; legal deadline D−1 18:00 CET (after our 10:00) |
| de_forecasts_hourly | wind_onshore_da_forecast_de_mw | MW | same, `wind_onshore` | as above | **unverified**; legal deadline D−1 18:00 CET |
| de_forecasts_hourly | wind_offshore_da_forecast_de_mw | MW | same, `wind_offshore` | as above | **unverified**; legal deadline D−1 18:00 CET |
| de_forecasts_hourly | load_da_forecast_de_mw | MW | same, `load` | as above | **unverified**; legal deadline D−1 10:00 CET (2 h before SDAC gate closure) |
| de_forecasts_hourly | publication_time_unverified | bool | – | always True | – |

## 6. Feature table

*From `docs/data_dictionary_features.md`.*

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

### Keys

| column | type | unit | rule |
|---|---|---|---|
| delivery_date | key | local date | delivery day D+1 |
| block | key / feature | 0–5 | local clock blocks 00–04, 04–08, 08–12, 12–16, 16–20, 20–24 |
| block_start_utc | key | UTC | start of the first hour of the block |
| hours_in_block | key / feature | h | 4; 3 (block 0 on spring DST day) or 5 (block 0 on autumn DST day) |
| forecast_issue_time_utc | key | UTC | D 10:00 Europe/Zurich (`auction.forecast_time_local`) |

### Targets and actuals (not features)

| column | type | unit | source | rule |
|---|---|---|---|---|
| demand_mw | target | MW | demand_ewz_hourly.load_mw | mean of the hourly values of the delivery block; NaN unless every hour is present |
| price_eur_mwh | target | EUR/MWh | price_ch_hourly | mean of the hourly CH prices of the block; NaN unless complete |
| actual_demand_mwh | actual | MWh | – | demand_mw × hours_in_block |
| actual_price_min_block, actual_price_max_block | actual | EUR/MWh | price_ch_hourly | min / max hourly price in the block |
| actual_cost_eur | actual | EUR | demand + price | Σ over hours of load_mw × price (cost of buying the actual demand at the actual hourly price) |
| actual_eurchf | actual | CHF per EUR | eurchf_daily | ECB rate of the delivery date, or the last rate before it (for CHF conversion of results) |

### Demand features (ewz, known up to end of D−1)

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

### Weather of the delivery block / day

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

### Past observed weather (known at issue time)

| column | unit | rule |
|---|---|---|
| temp_obs_mean_dm1 | °C | mean observed temperature of day D−1 |
| temp_obs_mean_last_3d, temp_obs_mean_last_7d | °C | mean over days D−3 … D−1 / D−7 … D−1 |
| temp_obs_same_block_lag_2d, radiation_obs_same_block_lag_2d | °C, W/m² | same block of day D−1 |
| temp_obs_last_24h_mean | °C | the 24 hours ending at issue time − 1 h (D−1 09:00 → D 09:00 local) |
| temp_change_fc_vs_dm1 (+ `_obs`, `_fc`, `_fc_jma`) | K | block temperature (hybrid / oracle / ICON / JMA) − temp_obs_same_block_lag_2d |

### Solar, EVs

| column | unit | source | rule |
|---|---|---|---|
| solar_ch_mw_lag_2d_same_block | MW | swiss_power_hourly.solar_mw | same block of day D−1 |
| solar_ch_day_mean_lag_2d | MW | same | day D−1 mean |
| ev_count_city | cars | ev_daily.ev_count_city_known | last published 30 Sept count + last published yearly growth |
| charging_kw_zh | kW | ev_daily.charging_kw_zh_known | last published BFE month; NaN before 2020-12-15 |
| stations_zh_count | count | ev_daily.stations_zh_count_known | same; NaN before 2020-12-15 |

### Calendar (delivery date unless stated; known in advance)

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

### CH price features (all hours of day D known)

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

### Neighbour prices (day D)

| column | unit | rule |
|---|---|---|
| price_de_day_D_same_block, price_fr_day_D_same_block, price_at_day_D_same_block, price_it_day_D_same_block | EUR/MWh | same block of day D, DE-LU / FR / AT / IT-North |
| price_de_mean_day_D, price_fr_mean_day_D, price_at_mean_day_D, price_it_mean_day_D | EUR/MWh | day D mean |
| spread_ch_de_day_D, spread_ch_fr_day_D, spread_ch_at_day_D, spread_ch_it_day_D | EUR/MWh | CH day-D mean − neighbour day-D mean |
| spread_ch_de_mean_7d, spread_ch_fr_mean_7d, spread_ch_at_mean_7d, spread_ch_it_mean_7d | EUR/MWh | mean of the daily spreads over days D−6 … D |
| price_de_lag_7d_same_block | EUR/MWh | DE same block of delivery−7 |

### Fuels, FX, hydro (as-of `available_from_utc` ≤ issue time)

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

### Swiss system (Energy-Charts, known up to end of D−1)

| column | unit | rule |
|---|---|---|
| swiss_load_lag_2d_same_block | MW | Swiss load, same block of D−1 (`load_bad` hours = NaN) |
| swiss_load_day_mean_lag_2d | MW | Swiss load, day D−1 mean |
| swiss_nuclear_mw_lag_2d, swiss_hydro_ror_mw_lag_2d, swiss_hydro_storage_mw_lag_2d, swiss_hydro_pumped_mw_lag_2d | MW | day D−1 mean of nuclear / run-of-river / reservoir hydro / pumped-storage generation |
| swiss_solar_mw_lag_2d_same_block | MW | solar, same block of D−1 (= solar_ch_mw_lag_2d_same_block) |
| swiss_residual_load_lag_2d_same_block | MW | hourly load − solar − wind − run-of-river, same block of D−1 |
| swiss_net_import_mw_lag_2d | MW | cross-border trading, day D−1 mean (sign as Energy-Charts; positive mostly in winter = import) |

### Unverified (not default features)

| column | unit | rule |
|---|---|---|
| unverified_de_solar_fc, unverified_de_wind_onshore_fc, unverified_de_wind_offshore_fc, unverified_de_load_fc | MW | Energy-Charts German day-ahead forecasts, delivery-block mean. Publication time unverified (legal deadline wind/solar D 18:00, after our forecast) |
| unverified_de_solar_fc_day, unverified_de_wind_onshore_fc_day, unverified_de_wind_offshore_fc_day, unverified_de_load_fc_day | MW | same, delivery-day mean |
| unverified_ch_solar_fc, unverified_ch_solar_fc_day | MW | Energy-Charts Swiss solar day-ahead forecast, block / day mean; scale changes over the years and publication time unverified |

### European weather forecasts (optional)

| column | unit | rule |
|---|---|---|
| eu_<c> | as in source | for every numeric column `<c>` of `weather_europe_forecast_hourly.parquet` (if the file exists): mean over the delivery block. The file is leakage-safe by construction (other agent); only delivery-day rows are used |
| eu_<c>_day | as in source | same, mean over the delivery day |

### `data/processed/hourly_actuals.parquet`

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

## 7. Result files

### `reports/predictions_demand.parquet`, `reports/predictions_price.parquet`

| column | unit | meaning |
|---|---|---|
| delivery_date, block | local date, 0–5 | key |
| split | – | `val` (Sept 2026), `test` (Oct 2026), `rolling` (Oct 2025 – Aug 2026, monthly refit) |
| y_true | MW / EUR/MWh | actual block mean |
| pred_naive, pred_linear, pred_rf, pred_gbm, pred_best | MW / EUR/MWh | forecasts of the model ladder; `pred_best` is used by the backtest |
| pred_q10, pred_q50, pred_q90 | MW / EUR/MWh | quantile forecasts (price band widened by factor 1.4, chosen on September) |

### `reports/backtest.csv` (one row per delivery day and strategy)

| column | unit | meaning |
|---|---|---|
| delivery_date, split, strategy, decision | – | key; `decision` = planning rule used (battery strategies) |
| demand_source, price_source | – | `ml`, `naive` or `actual` |
| n_hours | h | 23 / 24 / 25 |
| actual_price_mean_eur_mwh, eurchf_mean, eta_discharge | EUR/MWh, CHF per EUR, – | context of the day |
| forecast_demand_mwh, actual_demand_mwh | MWh | forecast and actual city demand of the day |
| demand_bid_mwh, at_risk_bid_mwh, charge_bid_mwh, charge_cleared_mwh, share_charge_cleared | MWh, share | bids and what cleared |
| energy_bought_mwh, charged_mwh, planned_discharge_mwh, discharged_mwh, discharge_not_delivered_mwh | MWh | energy flows |
| cycles, battery_idle, plan_has_discharge | count, bool | battery use |
| shortage_mwh, surplus_mwh | MWh | imbalance volumes |
| soc_start_mwh, soc_end_mwh, soc_target_relaxed | MWh, bool | battery level carried from day to day |
| da_cost_*, imbalance_cost_*, imbalance_penalty_*, wear_cost_*, total_cost_* | EUR and CHF | cost parts; penalty = extra over the DA price; CHF = hourly EUR × ECB rate |

`reports/backtest_summary.csv` sums these per period and strategy and adds inventory-adjusted costs, savings vs the
baseline with 95 % bootstrap intervals, % of the ceiling and battery values; `reports/backtest_decomposition.csv`
splits the product's saving into demand forecast and battery parts (definitions in `reports/backtest_notes.md`).

