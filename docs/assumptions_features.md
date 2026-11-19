# Assumptions – feature table (agent F1)

One line per assumption, with the reason.

## Time and availability
- Forecast issue time = day D 10:00 Europe/Zurich (`auction.forecast_time_local`), delivery day D+1 – gate closure 11:00 minus 1 h (docs/auction_timing.md).
- Blocks follow the local clock (00–04 … 20–24); DST days give 3- or 5-hour blocks (`hours_in_block`) – the auction and the DSO plan in local time.
- Zurich demand is known up to the end of D−1 – the DSO has its own meter data (orchestrator decision); the public ewz file is ~1.5 days late, which would only matter for an outside user.
- CH and neighbour prices are known for all hours of day D, never for D+1 – CH auction for D+1 closes 11:00 on D, SDAC 12:00 with results ~12:45–13:00.
- Swiss Energy-Charts load/generation is known up to the end of D−1 – near real-time source, one day margin.
- Hours flagged `load_bad`, `wind_bad`, `solar_bad` are treated as NaN – known glitches (frozen or impossible values).
- Observed weather: an hour is usable if it ENDS at or before issue time − 1 h (09:00 local) – one hour publication margin for the MeteoSwiss "now" data; the stricter reading of "≤ issue time − 1 h".
- Gas, CO₂, EUR/CHF and reservoirs use a strict as-of lookup on `available_from_utc` ≤ issue time – publication times documented by agent D4.
- Calendar, holidays, school holidays, events and football fixtures of D+1 (and D+2) are known in advance – announced months ahead.
- EV and charging features use only the `_known` columns – the plain columns are interpolated with values published later.

## Weather
- Weather of D+1 can only be a forecast; we use the D2 leakage-safe columns (`*_fc_safe*`), never `_fc_day0/1/2` – these are the only columns proven to be published before 10:00 on D.
- Main forecast = ICON-seamless (`temp_c_fc_safe_corr` for temperature, `<var>_fc_safe` otherwise) – lowest error (D2 check).
- Single missing ICON hours are filled from the ECMWF safe column – only the 23-h radiation/cloud gap of 2026-04-10/11 is affected; both are forecasts.
- ICON block/day values are NaN unless every hour of the block/day has a forecast – 2024-01-20 is only partly covered (day2 forecasts start 11:00 UTC), a partial mean would be biased.
- Hybrid model input `<var>` = ICON forecast where available, else OBSERVED weather – there is no ICON archive before 2024-01-20; this is a documented limitation: models trained before 2024 see perfect weather, so test-month errors with forecasts may be larger than in training.
- `weather_is_forecast` (0/1) tells the model which regime a row is in – lets it learn a different weight for forecast vs observed weather.
- Hybrid `cloud_pct` falls back to the JMA forecast instead of observations – MeteoSwiss SMA has no cloud cover; JMA is a real forecast back to 2019.
- JMA forecasts (`*_fc_jma`) are kept as an alternative weather source back to 2019 – the only real forecast archive for the full period (no radiation/sunshine).
- Observed delivery-day weather is stored only as `*_obs` (oracle) and never in the default feature lists – for "perfect weather" benchmarks only.
- Block weather is the mean over the hours of the block (precipitation and sunshine as mm or min per hour) – scale stays the same for 3-, 4- and 5-hour blocks; day sunshine is a sum.
- Heating degree base 15 °C, cooling degree base 22 °C – common Swiss/European conventions for building heating/cooling.

## Features
- Lags are named relative to the delivery date (`_lag_{k}d` = same block k days before delivery) – one convention for all sources.
- Multi-day means are means of hourly values over whole local days (NaN hours ignored) – robust to DST days.
- `demand_trend_7d` = mean of the last 7 known days ÷ mean of the 7 days before – simple level-change signal.
- `price_block_vs_day_ratio_last_7d` is a difference (block − day mean), averaged over D−6 … D – the brief defines it as a difference; a ratio breaks near 0 or negative prices.
- `clean_gas_cost` = gas / 0.5 + 0.37 × CO₂ – CCGT with 50 % efficiency and 0.37 tCO₂/MWh_el (≈ 0.2 t/MWh_th ÷ 0.5 ≈ 0.4; 0.37 is the usual value for modern CCGTs); a proxy, not a plant cost.
- `gas_ttf_change_5d` and `gas_ttf_mean_20d` count published trading rows, not calendar days – the Yahoo series has no weekend/holiday rows.
- `co2_staleness_days` = day D − date of the last auction used – CO₂ auctions pause around New Year (up to 46 days), the model can discount stale values.
- `reservoir_change_1w` = latest published fill − the previous published week – both were public at issue time.
- `swiss_residual_load_lag_2d_same_block` = load − solar − wind − run-of-river (own definition) – the Energy-Charts residual load does not remove run-of-river.
- `kickoff_hour_local` = 0 on days without a home game – models cannot use NaN; `home_game` tells the two cases apart.
- `school_holiday_type` is an integer code (0 none, 1 christmas, 2 sport, 3 spring, 4 summer, 5 autumn, 6 school_free_day) with a text copy – fixed codes so they never change between runs.
- `covid_stringency` = OxCGRT `covid_stringency_filled` (0 outside 2020–2022) – policy was announced before it applied; models may drop it.
- `daylight_hours` uses a simple declination formula for 47.378° N – accurate to a few minutes, enough as a seasonal feature.
- German day-ahead forecasts and the Swiss solar forecast are stored only as `unverified_*` – publication time not verified (German wind/solar legally due D 18:00, after our forecast); Swiss solar forecast scale changes over the years.
- Targets are block means only if all hours of the block exist – otherwise NaN, so a missing hour can never shrink a target.
- `actual_eurchf` = ECB rate of the delivery date, or the last earlier rate – for converting EUR results to CHF in the backtest.
- European weather forecasts (`eu_*`) are added generically from `weather_europe_forecast_hourly.parquet` if it exists – the file is built by another agent and is leakage-safe per target hour; only delivery-day rows are used.

## Tests
- The leakage test compares rebuilt features for exact equality – every feature is computed only from the values inside its own time window, so truncating or poisoning data outside the window cannot change the result, not even by rounding.
- On rows with `weather_is_forecast` = 0, hybrid weather columns are only checked for "= `_fc` if present, else `_obs`" – they intentionally use observed weather there (documented limitation).
