# Data dictionary – price drivers (agent D4)

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
