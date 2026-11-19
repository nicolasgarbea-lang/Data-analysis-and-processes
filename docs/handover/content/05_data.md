# 5 Data

<div class="inshort" markdown="1">

All data is public, from 2019 to October 2026: Zurich demand every 15 minutes (ewz), Swiss and neighbour prices
(Energy-Charts), observed and forecast weather, gas, CO₂, exchange rate, reservoirs, calendar, EVs and events.
Everything is stored in UTC. The hardest problems were the ewz time stamps (they mark the **end** of the interval) and
the clock-change days; both were solved with a second ewz file in UTC.

</div>

## Sources

| Input | Source | Step | Used for | Loader |
|---|---|---|---|---|
| Zurich demand (target) | ewz "Bruttolastgang Stadt Zürich"; cross-check ewz "Stromabgabe Netzebenen" (UTC) | 15 min, local time | target, demand lags | `src/data/load_ewz_demand.py` |
| Swiss day-ahead price (target) | Energy-Charts API (Fraunhofer ISE), `bzn=CH` | 1 h (15 min from {{n:ch15_local_day}}) | target, price lags | `src/data/load_price_ch.py` |
| Neighbour prices | Energy-Charts, DE-LU, FR, AT, IT-North | 1 h (15 min from Oct 2025, averaged) | price features, day D only | `src/data/load_neighbour_prices.py` |
| Swiss load, solar, hydro, nuclear | Energy-Charts `public_power` | 1 h | price features (D−1), lagged solar | `src/data/load_swiss_power.py` |
| Observed weather | MeteoSwiss station Zürich-Fluntern (SMA) | 1 h | past weather; training stand-in before 2024 | `src/data/load_meteoswiss.py` |
| Weather forecasts, Zurich | Open-Meteo previous-runs API: ICON (from 2024-01-19), ECMWF, JMA (back to 2018) | 1 h | weather of D+1 | `src/data/load_openmeteo_forecast.py` |
| Weather forecasts, Europe | Open-Meteo previous-runs, 9 points in DE/FR/IT/CH (ICON, JMA) | 1 h | German wind/solar, French temperature | `src/data/load_openmeteo_europe.py` |
| Reanalysis | Open-Meteo archive (ERA5) | 1 h | cross-check only, never an input | `src/data/load_openmeteo_archive.py` |
| EVs | Stadt Zürich car stock by fuel (yearly); BFE charging stations, canton Zurich (monthly) | daily | demand features | `src/data/load_ev.py` |
| Calendar | `holidays` (ZH) + Berchtoldstag; Stadt Zürich school holidays; OxCGRT COVID index | daily | demand and price features | `src/data/load_calendar.py` |
| Events, football | hand-made `data/manual/events_zurich.csv`; football-data.co.uk Super League | daily | demand features | `src/data/load_events.py`, `src/data/load_football.py` |
| Gas | Yahoo `TTF=F` (**unofficial**) | daily | price features | `src/data/load_gas.py` |
| CO₂ | EEX EUA primary-auction results | auction days | price features | `src/data/load_co2.py` |
| EUR/CHF | ECB reference rate | daily | price feature; CHF conversion | `src/data/load_fx.py` |
| Reservoirs | BFE weekly fill of Swiss storage lakes | weekly | price features | `src/data/load_reservoirs.py` |
| German TSO forecasts | Energy-Charts `public_power_forecast?country=de` | 1 h | stored, **not used** (publication time unverified) | `src/data/load_de_forecasts.py` |

Full detail (endpoints, licences, what was verified): `docs/data_sources.md`; every column: `docs/data_dictionary.md`;
every assumption with its reason: `docs/assumptions.md`.

## Time conventions

- **Everything is stored in UTC**, as the start of the interval (`timestamp_utc`). Local Zurich time is used only to
  build blocks and calendar features.
- **Blocks follow the local clock.** On clock-change days the night block 00–04 has 3 hours (spring) or 5 hours
  (autumn), so the feature table keeps a column `hours_in_block`.
- **Targets are mean MW per block**, not MWh, so 3- and 5-hour blocks are comparable. Costs use MW × hours.
- Daily tables use a column `date` = the local Zurich calendar day (or the trading day, documented per table).

## The ewz time stamps: start or end of the interval?

The ewz demand file gives local time stamps without an offset, and the first value of 2019 is at 00:15 – a hint that
the stamp marks the **end** of the quarter-hour. A second ewz file, "Stromabgabe Netzebenen", is in UTC and its
documentation says the values refer to "the 15 minutes before this time". Demand = network levels NE5 + NE7 at the same
instant, so the two files must match exactly when the conventions are aligned. They were compared at shifts of
−60 to +60 minutes:

{{t:ewz_shift|Correlation of ewz demand (converted with the END rule) with Netzebenen, by shift. Source: `reports/data_checks/demand_ewz_crosscheck.md`.}}

Shift 0 is best by far ({{n:ewz_corr_0}} against {{n:ewz_corr_p15}} at +15 minutes). **Rule:** convert the local label to UTC
and subtract 15 minutes, so that `timestamp_utc` is the start of the interval.

## Clock-change days

On the autumn clock change the local labels 02:00–02:45 appear twice (once in summer time, once in winter time). The
natural guess – "the first row is the earlier one" – is wrong most of the time:

{{t:dst_pairs|Every autumn duplicate pair, 2019–2026. "file order chronological = False" means the file lists the winter-time value first. Each pair was assigned by matching it to the Netzebenen values.}}

The file order is chronological in only {{n:dst_right}} of {{n:dst_pairs}} pairs, so each pair was matched to Netzebenen
instead. After conversion there are no duplicates, and every year has exactly one 23-hour and one 25-hour day:

{{fig:eda_dst_check.png|Clock-change days: 23 and 25 hours, no doubled or missing values.}}

## Cleaning decisions per source, with the evidence

| Source | Decision | Evidence / reason |
|---|---|---|
| ewz demand | two missing days in 2021 (30 May, 7 Aug; {{n:ewz_filled_intervals}} quarter-hours) filled from Netzebenen NE5 + NE7 and flagged (`is_filled`) | same quantity from the same utility; median difference {{n:ewz_median_diff_kwh}} kWh per quarter-hour (`reports/data_checks/demand_ewz_crosscheck.md`) |
| ewz demand | all values kept although none has status W (final); all are E (substitute) or F (not yet checked: June 2020, November 2026) | E is ewz's corrected value; dropping it would drop everything. ewz can revise values for up to six months |
| ewz demand | 2019's level (about {{n:ewz_2019_above_pct}} % above the later years) kept | real (COVID, efficiency trend), see the yearly table below |
| CH price | 15-min prices (from {{n:ch15_local}}, = {{n:ch15_utc}}) averaged to the hour; negative prices kept | one hourly grid for all years; negative prices are real. No missing hour 2019 – Oct 2026 |
| Neighbour prices | 15-min (from 1 Oct 2025) averaged; only day D used | their auction for D+1 closes at 12:00 |
| Swiss load (Energy-Charts) | flagged bad after 16 Nov 2026, when constant ≥ 6 h or outside 50–200 % of a centred 7-day median; wind > 500 MW flagged | known glitches (e.g. a frozen value on 2023-02-17); the centred window is only a flag – a replay of all forecast days changed no feature |
| Swiss solar forecast | stored as `unverified_*`, not used | the forecast/actual ratio changes from year to year (`docs/assumptions_targets.md`); publication time undocumented |
| MeteoSwiss | stamp = end of the hour → shifted −1 h; one gap of about a day and a half (May 2021) left empty | June radiation peaks symmetrically around solar noon after the shift |
| Open-Meteo | stamps shifted −1 h; leakage-safe lead per hour (chapter 6); temperature bias correction per month × hour fitted before September 2026 | radiation error vs station {{n:rad_mae_shift}} W/m² with the shift, {{n:rad_mae_noshift}} without |
| Gas | Yahoo `TTF=F`, fetched with `curl_cffi`; US-holiday gaps not filled (as-of join) | HSG export not available; plain requests got HTTP 429 |
| CO₂ | volume-weighted mean of the day's auctions; no value on non-auction days (carried forward, `co2_staleness_days`) | official, free; close to the secondary market |
| Reservoirs | Sunday value known from Thursday 23:59; median of the same week from earlier years only | federal energy dashboard; no look-ahead |
| EVs | battery-electric cars only; after the last count extrapolated with the last published yearly growth; BFE data is for the canton | stock grows 20–50 % per year, a flat value would be stale |
| Events | only events with a confirmed date and a source URL; the rest listed in `docs/events_unverified.md` | "no invented data" |
| Football | `Time` is UK time (+1 h); only Super League home games of FC Zürich and Grasshoppers | kick-off times confirm the shift |

## Publication lags (what is known when)

| Input | Known from (Zurich time) | Basis |
|---|---|---|
| Zurich demand | end of D−1 at forecast time (assumption: the DSO reads its own meters) | the public file lagged about 1.5–2 days on 19 Nov 2026 |
| CH and neighbour prices | all of day D | auctions ran on D−1 |
| Swiss load / generation | end of D−1 | near real-time source, one day margin |
| Observed weather | hours ending ≤ 09:00 on D | one hour publication margin |
| Gas | trading day 18:00 | ICE Endex settlement 16:30–17:30 |
| CO₂ | auction day 12:00 | auction closes 11:00, results within 15 min |
| EUR/CHF | date 16:00 | ECB publishes about 16:00 |
| Reservoir level | Thursday 23:59 for the Sunday value | federal energy dashboard (changed from Wednesday after review) |
| EV count (30 Sept of year Y) | 1 August of Y+1 | observed update date plus margin |
| BFE charging (month M) | 15th of M+1 | observed plus margin |
| Weather forecast for D+1 | the latest run published by 10:00 under assumed delays (ICON 4 h, ECMWF 8 h, JMA 6 h) | checked against the single-runs API |
| Calendar, holidays, events, fixtures | known in advance | announced months ahead |

## What the data shows

{{t:price_years|Yearly overview from `data/processed/hourly_actuals.parquet` (local delivery days; 2026 up to 31 October).}}

{{fig:eda_demand_overview.png|Zurich demand: level, daily profile and the effect of temperature.}}

{{fig:eda_price_history.png|The Swiss day-ahead price 2019–2026: the 2021–2022 crisis and the later negative-price hours.}}

{{fig:eda_price_block_month.png|Block price minus the day mean, by month. The midday block is far below the mean in spring and summer (solar); this within-day gap is what the battery earns from.}}

{{fig:eda_missing_data.png|Missing data per input over time. Late starts are expected: ICON forecasts from 2024, charging data from late 2020.}}

{{fig:eda_weather_forecast_vs_observed.png|Weather forecast versus observed temperature: the forecast error that the models face in validation and test.}}

{{t:ewz_years|Yearly mean, minimum and maximum Zurich load (MW). Source: `reports/data_checks.md`.}}

## Quirks and gaps to know about

- **Swiss load after 16 Nov 2026** jumps to several times its real level (Energy-Charts glitch). Outside the test period; flagged.
- **ICON radiation** is missing for about a day around 10–11 April 2026 in the archive; filled from the ECMWF forecast.
- **ICON 100 m wind** for the European points starts only on 2024-02-16.
- **JMA precipitation** (Alps) has a gap of about two weeks in April 2026.
- **CO₂** has no auctions in the year-end break (several weeks, longest in 2020/21): stale values are flagged by
  `co2_staleness_days`.
- **BFE charging data** starts in November 2020 and July 2021 is missing in the source.
- **Football** data contains only league games, and Grasshoppers played in the second division in 2019/20–2020/21.
- **Züri Fäscht 2026 did not take place** (documented in `docs/events_unverified.md`).
