# Assumptions – price drivers (agent D4)

One line per assumption, with the reason.

- **Swiss day-ahead gate closure = 11:00 CET/CEST on D−1, results ~11:10, unchanged 2019–2026.** EPEX brochures 2020–2024 and EEX glossary say so; no change found (see `docs/auction_timing.md`).
- **Neighbour (SDAC) prices for D+1 are not usable; prices for all of day D are.** SDAC closes 12:00 and publishes ~12:45–13:00, after our 10:00 forecast time.
- **Neighbour hourly price `available_from_utc` rule (not stored as a column, hourly table): delivery date − 1 day at 13:00 Europe/Zurich.** SDAC final results are out by ~13:01; using 13:00 is fine since our forecast is at 10:00 anyway.
- **15-min neighbour prices (from 1 Oct 2025) are averaged to hourly with an unweighted mean of the 4 quarter-hours.** Keeps one hourly grid for all years; the hourly mean equals the energy-weighted price for a flat profile.
- **Gas: Yahoo Finance `TTF=F` is used as an UNOFFICIAL fallback.** The HSG LSEG/Bloomberg export was not available; Yahoo data licence is for personal/educational use only.
- **Yahoo `TTF=F` is the NYMEX "Dutch TTF Natural Gas Calendar Month" future (front month), EUR/MWh.** Close tracks the ICE Endex TTF front-month settlement closely; it is not the ICE contract itself.
- **Gas trading day = date of the Yahoo bar; days missing on US holidays (NYMEX calendar, ~73 weekdays in 2019–2026) are not filled.** The feature builder does an as-of join, so the previous close is used.
- **Gas close of day T is known from T 18:00 Europe/Zurich.** ICE Endex settles ~16:30–17:30 CET; at 10:00 on D only closes ≤ D−1 are used either way.
- **Yahoo had to be called through `curl_cffi` (Chrome impersonation).** Plain `requests`/`curl` get HTTP 429 from Yahoo; this is how the `yfinance` package works too.
- **CO₂: EEX primary-market auction clearing price is used as the daily EUA price (official, free), 2019 → 2026-11-19, from one source only.** The 2026 xlsx is on EEX's site, so no second source had to be combined; `source` column = `EEX_primary_auction`.
- **Several auctions on one day → volume-weighted mean price.** One number per day; auctions on the same day clear within a few cents of each other.
- **CO₂ has no value on non-auction days (most Fridays, weekends, parts of August) and in the year-end break (~3–7 weeks, longest 2020-12-14 → 2021-01-29 = 46 days at the start of EU ETS Phase 4).** We do not fill; the feature builder carries the last auction forward (stale values in January).
- **CO₂ auction result known from auction day 12:00 Europe/Zurich.** Bidding closes 11:00, results within 15 minutes (EU Auctioning Regulation).
- **Primary auction prices are a proxy for the secondary EUA market (ICE futures).** Auction prices clear close to secondary spot; secondary-market data would need LSEG/ICE access.
- **Reservoir `measure_date` (Mondays in the file) = level on the preceding Sunday at 24:00.** opendata.swiss title "Füllungsgrad der Speicherseen, Sonntag 24h"; all file dates are Mondays.
- **Reservoir value known from Wednesday 18:00 Europe/Zurich (measure_date + 2 days).** Only one observation of the release time (file Last-Modified Tue 17 Nov 2026 15:22 CET); Wednesday evening adds a safety margin. First used by the Thursday 10:00 forecast.
- **`reservoir_fill_pct` = Swiss total GWh ÷ Swiss maximum GWh of the same row.** The maximum changes over time (8,500 → 8,900 GWh) as dams are raised.
- **`reservoir_median_pct_same_week` uses only years strictly before the row's ISO year, same ISO week (week 53 → week 52 if no history).** Avoids look-ahead; the year 2000 has no history (NaN), from 2001 it is filled.
- **EUR/CHF ECB rate of date T known from T 16:00 Europe/Zurich.** ECB publishes the reference rate around 16:00 CET; no rates on weekends/TARGET holidays (as-of join).
- **Energy-Charts DE day-ahead forecasts (solar, wind on/offshore, load; 2019 → 2026-11-18) are stored but flagged `publication_time_unverified=True`.** The API gives no issue time and we cannot tell whether historical values are the first-issued forecast.
- **By law (Reg. 543/2013) the DE day-ahead load forecast is due 2 h before SDAC gate closure (10:00 CET on D for D+1) and wind/solar forecasts by 18:00 CET on D.** So for delivery D+1, wind/solar are not guaranteed at our 10:00 forecast time; the load forecast is borderline. Safe use: the forecasts for delivery day D (known on D−1) or only as a sensitivity test.
