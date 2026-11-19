# Assumptions (consolidated)

One line per assumption, with a one-line reason. Merged from the per-step fragments `docs/assumptions_*.md`, which
stay in place (the app reads them) and hold more detail. Stale statements from the fragments are corrected here and
marked *(updated)*.

## 1. Business set-up
- The DSO is fictional (*Limmat Energie AG*); its demand is the real ewz load of the city of Zurich. – Real open data, no confidential company data needed.
- The battery is fictional: 20 MW / 40 MWh, usable 10–90 %, 90 % round trip (√0.9 each way), ≤ 1 full cycle per day, start and end level 50 %, wear cost 5 EUR per MWh discharged (`config.yaml`). – Typical values for a 2-hour grid battery.
- The battery is not a demand feature; "usage" in the team's diagram means past demand. – A battery does not change how much the city consumes.
- The DSO does not sell energy back (`allow_sell: false`). – A DSO buys for its customers; a sensitivity run shows selling changes nothing for a 20 MW battery.
- The battery is a price taker: its bids do not move the auction price; charge bids clear fully or not at all. – 20 MW is small for the Swiss market; no order-book data.

## 2. Time rules
- Swiss day-ahead gate closure = 11:00 CET/CEST on D−1, results from ~11:10, unchanged 2019–2026. – EPEX SPOT brochures 2020–2024 and the EEX glossary (`docs/auction_timing.md`); single delayed days ignored.
- Forecast time = day D 10:00 Europe/Zurich (gate closure − 1 h), delivery day D+1. – Leaves one hour to plan and bid.
- Everything is stored in UTC; blocks (00–04 … 20–24) follow the local clock, so DST days have 3- or 5-hour blocks. – The auction and the DSO work in local time.
- Targets are mean MW per block; MWh = MW × `hours_in_block`. – Not distorted by 3- or 5-hour blocks.
- Zurich demand is known up to the end of D−1. – The DSO reads its own meters; the public ewz file lags ~1.5 days (sensitivity without D−1 demand in `reports/model_notes_demand.md`).
- CH and neighbour prices are known for all hours of day D, never for D+1. – CH auction for D+1 closes 11:00 on D; the EU-coupled auction (DE, FR, AT, IT-North) closes 12:00 with results ~12:45–13:00.
- Swiss Energy-Charts load and generation known up to the end of D−1. – Near real-time source, one day margin.
- Observed weather usable if the hour ends ≤ 09:00 local on D. – One hour publication margin.
- Gas close of day T known from T 18:00; CO₂ auction result from auction day 12:00; ECB EUR/CHF from date 16:00. – Settlement / publication times of each source.
- Reservoir level of Sunday 24:00 known from **Thursday 23:59**, first used on Friday *(updated: the D4 table in `docs/auction_timing.md` still says Wednesday 18:00; the code and the drivers fragment use Thursday after the Phase 1 review)*. – The federal energy dashboard states Thursday publication.
- Stadt Zürich EV count of 30 Sept of year Y public from 1 Aug of Y+1; BFE monthly charging data of month M public from the 15th of M+1. – Observed update dates plus a safety margin.
- EV and charging features are joined **as of the forecast day D** using the `_known` columns *(updated after the Phase 1 review; before they were joined by delivery day)*. – Only values published by D may be used.
- Calendar, holidays, school holidays, events and football fixtures are known in advance. – Announced months ahead.
- COVID stringency is treated as known on the day. – Measures were announced before they started; only 2020–2022 training rows are affected.

## 3. Demand data (ewz)
- ewz Bruttolastgang time stamps mark the END of the 15-min interval (local time) → converted to UTC and shifted −15 min. – Matches the documented Netzebenen file (correlation 0.999993 at shift 0).
- Autumn DST duplicate labels are matched to Netzebenen values, not taken in file order. – The file order is wrong in 27 of 32 pairs.
- The two missing days of 2021 (30 May, 7 Aug) are filled with Netzebenen NE5 + NE7 and flagged. – Same quantity from the same utility (median difference 1.9 kWh).
- All values are kept although none is final (W); all are E (substitute) or F (not yet checked: June 2020, Nov 2026). – E is ewz's corrected value; dropping it would drop everything.
- 2019's higher level (~4 % above later years) is real and not corrected. – COVID and efficiency trend.

## 4. Prices and price drivers
- Energy-Charts CH price = EPEX SPOT day-ahead, EUR/MWh, UTC start of the hour. – API documentation.
- 15-min prices (CH from 4 Nov 2026, neighbours from 1 Oct 2025) are averaged to hourly with a simple mean. – One hourly grid for all years; equal to the volume-weighted price for a flat profile.
- Gas = Yahoo `TTF=F` front-month future, marked UNOFFICIAL. – HSG LSEG/Bloomberg export was not available.
- CO₂ = EEX EUA primary-auction clearing price (volume-weighted per day), carried forward on days without auction. – Official and free; close to the secondary market.
- Reservoir fill = Swiss total GWh ÷ Swiss maximum GWh of the same week; the median of the same ISO week uses only earlier years. – Maximum changes over time; no look-ahead.
- `clean_gas_cost` = gas / 0.5 + 0.37 × CO₂. – Short-run cost proxy of a modern gas plant.
- German TSO day-ahead forecasts and the Swiss solar forecast are stored but not used as features (`unverified_*`). – Publication time not verified (German wind/solar legally due D 18:00, after our forecast); the Swiss solar forecast scale changes over the years.
- Swiss load is flagged bad after 16 Nov 2026, when constant ≥ 6 h or outside 50–200 % of a centred 7-day median; wind above 500 MW is flagged. – Known Energy-Charts glitches; the centred window is used only for the flag (a replay changed no feature).

## 5. Weather
- MeteoSwiss hourly stamp = end of the hour → shifted −1 h; Open-Meteo stamps also shifted −1 h. – Checked against the solar noon and the station radiation.
- `_previous_dayN` = latest run initialised at or before valid time − N × 24 h; leakage-safe lead = day1 only if that run was published by D 10:00, else day2. – Verified with the Open-Meteo single-runs API; publication delays assumed ICON 4 h, ECMWF 8 h, JMA 6 h.
- Archived previous-runs values equal what was available in real time. – Cannot be verified retroactively.
- Main forecast = ICON-seamless (real archive from 2024-01-19); JMA kept as the only real forecast back to 2018. – Lowest error (temperature MAE 1.10 °C before correction).
- Temperature bias correction per calendar month × local hour, fitted only before 2026-09-01. – Out of sample for September and October; small look-ahead for the rolling 2025–26 run (documented).
- Before 21 Jan 2024 the hybrid weather input is OBSERVED weather (training rows only); `weather_is_forecast` tells the model which regime a row is in. – No forecast archive exists; validation and test use real forecasts only.
- Heating degree base 15 °C, cooling degree base 22 °C. – Common Swiss/European conventions.
- European weather: 9 representative points, unweighted regional means, wind power proxy min(v, 25)³. – Simple and transparent; wind power ∝ v³ below rated speed.

## 6. Calendar, EVs, events
- Public holidays = `holidays.Switzerland(subdiv="ZH")` + Berchtoldstag; Sechseläuten and Knabenschiessen Mondays are half-holidays (dates from the Stadt Zürich school calendar). – Matches how the city works.
- Bridge day = working day between a holiday and a weekend/holiday. – Usual definition.
- School-calendar end dates are exclusive. – Verified with single-day entries.
- Electric cars = battery-electric only; after the last count the stock is extrapolated with the last published yearly growth. – Hybrids charge little; a flat carry-forward would be stale.
- BFE charging figures are for the canton of Zurich, not the city. – No city level exists.
- Only events with a confirmed date and a source URL are in `data/manual/events_zurich.csv`; others are in `docs/events_unverified.md`. – No invented data.
- Event size 1–3 from visitor numbers; cancelled COVID years are absent. – Rough judgement, documented per event.
- Football: Super League home games of FC Zürich and Grasshoppers only; `Time` in the file is UK time (+1 h). – Only source with full history; kick-off times confirm the shift.

## 7. Models
- Ladder naive (same block 7 days earlier) → ridge → random forest → LightGBM → best. – Required by the brief; shows what each step adds.
- Train ≤ 31 Aug 2026, choose on September 2026 (+ 5-fold time-series CV), test once on October 2026. – No random splits; October untouched until the end.
- Demand models are refit up to 30 Aug (validation) / 29 Sep (test) *(updated after the Phase 3 review; before 31 Aug / 30 Sep)*. – Demand of the last day is not known at the first forecast of the month.
- Price models are refit up to 31 Aug / 30 Sep and then every 7 days during the month. – The price of day D is known at 10:00 on D.
- Best models predict the change from a known reference (demand: log ratio to the same block on D−1; price: difference to day-D mean + 7-day block shape). – Trees cannot extrapolate levels (crisis).
- Rolling-origin backtest Oct 2025 – Aug 2026 with monthly refits, using the settings chosen on September 2026. – Robustness check; slightly optimistic because the settings were chosen later.
- 95 % intervals = bootstrap of whole days; Diebold–Mariano test on daily mean absolute errors. – Errors within a day are correlated.

## 8. Decision, bids and backtest
- The plan is solved as a small mixed-integer program (SciPy/HiGHS) with a yes/no variable per period against simultaneous charge and discharge, zero optimality gap. – Prevents "burning" energy at negative prices; exact solution.
- Chosen planning mode `hourly_shape`: hourly price = block forecast + mean within-block shape of the last 7 days of the same day type (workday vs weekend/holiday), re-centred to the block forecast. – A 2-hour battery fits inside one block; won the tuning clearly.
- Hourly demand forecast = block forecast × last week's hourly shape of the same block. – Known at forecast time.
- Demand bids are price-independent; planned discharge is spread over the block's hours with a cap of min(need, power), block totals conserved. – The city must be supplied; demand bids are never negative.
- Charge bids are limit bids at expected discharge price × 0.9 − wear cost. – Only buy energy to store if it will pay off.
- Decision rules tuned once on 2025-10-01 → 2026-08-31 plus 1–29 Sept 2026; a candidate replaces the default only if it wins with a 95 % paired-bootstrap interval above zero. – October never used; 29 Sept is the last day settled by 30 Sept 10:00.
- Settlement uses actual hourly prices and demand; a missing or non-finite value stops the run. – Never settle with forecasts or with silent zeros.
- Imbalance: shortage costs p + 0.2·|p|, surplus earns p − 0.2·|p| (p = actual DA price). – Assumption (not Swissgrid prices); |p| keeps it a penalty at negative prices.
- CHF = hourly EUR × ECB EUR/CHF of the delivery date (last earlier rate on non-publication days). – Official daily rate.
- Ceiling = one hourly perfect-foresight plan over the whole period with matched start and end level. – A true lower bound on cost.
- Inventory-adjusted cost = raw cost − (end − start stock) × discharge efficiency × period mean actual price × mean EUR/CHF. – Strategies end with different stored energy.
- The actual end-of-day battery level is carried into the next day. – Known at forecast time.
- Sensitivities (battery size, price noise, imbalance factors, limit factor, wear cost, selling) are run on October for information only. – Nothing is chosen from the test month.
