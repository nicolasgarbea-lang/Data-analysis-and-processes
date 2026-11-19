# Data dictionary – targets and Swiss system data (agent D1)

All timestamps are tz-aware UTC (`datetime64[ns, UTC]`) and mark the **start** of the interval.
"Publication lag" = when the value can be known, as far as we could observe it (see `docs/assumptions_targets.md`).

## `data/processed/demand_ewz.parquet` (15 min)

| column | unit | source | time convention | publication lag |
|---|---|---|---|---|
| `timestamp_utc` | – | ewz Bruttolastgang `zeitpunkt` | source = local END label; converted to UTC, −15 min → start of the 15-min interval | – |
| `load_kwh_15min` | kWh per 15 min | ewz Bruttolastgang Stadt Zürich (data.stadt-zuerich.ch, CC0) | energy delivered in the interval | file updated daily; on 2026-11-19 09:05 it held data up to the end of 2026-11-17 (≈ 1.5 days). Values may be revised for up to 6 months |
| `status` | – | ewz | `E` substitute value, `F` not yet checked, `W` final (none present); NaN for filled rows | as above |
| `is_filled` | bool | – | True where the value did not come from the Bruttolastgang file | – |
| `fill_method` | – | – | `netzebenen` = taken from ewz Netzebenen NE5+NE7 (UTC file), `interpolated` = linear (gaps ≤ 1 h), empty = original | – |

## `data/processed/demand_ewz_hourly.parquet` (1 h)

| column | unit | source | time convention | publication lag |
|---|---|---|---|---|
| `timestamp_utc` | – | derived | start of the UTC hour | – |
| `load_mw` | MW | derived from `load_kwh_15min` | mean power over the hour = sum of 4 × kWh / 1000; NaN if fewer than 4 intervals | as 15-min file |
| `n_intervals` | count | derived | number of 15-min values in the hour (4 everywhere) | – |
| `share_non_final` | share 0–1 | derived | share of the 4 intervals with status ≠ W (1.0 everywhere, because no W exists) | – |
| `share_status_f` | share 0–1 | derived | share of the 4 intervals with status F (not yet checked) | – |
| `n_filled` | count | derived | intervals in the hour that were filled | – |

## `data/processed/price_ch_hourly.parquet` (1 h)

| column | unit | source | time convention | publication lag |
|---|---|---|---|---|
| `timestamp_utc` | – | Energy-Charts `price?bzn=CH` `unix_seconds` | start of the delivery hour, UTC | – |
| `price_eur_mwh` | EUR/MWh | Energy-Charts (CC BY 4.0), EPEX SPOT day-ahead CH | hourly price; from 2026-11-03 23:00 UTC (= 4 Nov 00:00 local) the mean of the four 15-min prices | prices for day D+1 are known after the CH day-ahead auction on day D (gate closure 11:00, results around noon). The file contains D+1 already (last row 2026-11-20 22:00 UTC) |
| `n_values` | count | derived | number of source values averaged (1 = hourly source, 4 = 15-min source) | – |

## `data/processed/swiss_power_hourly.parquet` (1 h)

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

## `data/processed/swiss_solar_forecast_hourly.parquet` (1 h)

| column | unit | source | time convention | publication lag |
|---|---|---|---|---|
| `timestamp_utc` | – | Energy-Charts `public_power_forecast?country=ch&production_type=solar&forecast_type=day-ahead` | start of the hour, UTC | not documented by Energy-Charts; a day-ahead forecast is normally published on D−1 (assumption, check before use) |
| `solar_forecast_mw` | MW | same | day-ahead forecast of Swiss solar | **scale changes**: 5–21 % of actual solar 2019–2023, ≈ 100 % in 2024, 60–70 % in 2025–2026 (see check file) |
