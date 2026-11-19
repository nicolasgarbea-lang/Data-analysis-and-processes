# 13 Decision register

<div class="inshort" markdown="1">

One table with every significant decision of the project: what was decided, which alternatives were considered, why,
where the evidence is and where it lives in the code. If a lecturer asks "why did you do X?", the answer starts here.
Decisions are grouped by area; "R" numbers point to the review log in chapter 12.

</div>

## Business set-up and time rules

<div class="tbl tbl-decisions" markdown="1">

| ID | Decision | Alternatives considered | Why | Evidence | Where in code |
|---|---|---|---|---|---|
| D01 | Fictional DSO *Limmat Energie AG* with the **real** ewz city load | a real utility; a national load | real open data, no confidential data needed; demand is local, price national | `docs/data_sources.md` | – |
| D02 | Swiss gate closure **{{c:auction.gate_closure_local}}**, forecast at **{{c:auction.forecast_time_local}}** on D | 12:00 (the brief's first assumption) | EPEX brochures 2020–2024, EEX glossary; 12:00 is the EU-coupled auction | `docs/auction_timing.md` | `config.yaml` `auction` |
| D03 | Six local-clock 4-hour blocks; targets = **mean MW** per block | MWh per block; UTC blocks | the auction and the DSO work in local time; mean MW is not distorted by 3/5-hour blocks | `docs/assumptions.md` §2 | `config.yaml` `blocks`, `src/features/build_features.py` |
| D04 | Store everything in UTC, start-of-interval stamps | local time | no duplicates or gaps at clock changes | `prompts/briefs/common_data.md` | all loaders |
| D05 | Demand known to the **end of D−1** at 10:00 | D−2 (as the public file) | the DSO reads its own meters; public file lagged 1.5–2 days | S1 sensitivity: {{e:demand:S0:test_mae}} → {{e:demand:S1:test_mae}} MW | `src/features/build_features.py` cut-offs |
| D06 | Neighbour prices only for day D, never D+1 | use D+1 neighbour prices | their auction closes 12:00, results ~12:45 | `docs/auction_timing.md` | `neighbour_features` |
| D07 | Reservoir level known Thursday 23:59 | Wednesday 18:00 | federal energy dashboard says Thursday | review R02 (Phase 1) | `src/data/load_reservoirs.py` |
| D08 | EV/charging values joined **as of day D** with `_known` columns | join by delivery day | only published values may be used | review (Phase 1) | `src/data/load_ev.py`, `solar_and_ev_features` |
| D09 | Weather of D+1 = freshest run **published by 10:00** (day1 or day2 per hour) | `_previous_day1` for all hours (the brief) | day1 runs for daytime hours are published after 10:00 | `docs/assumptions_weather.md` | `safe_lead_days` in `src/data/load_openmeteo_forecast.py` |
| D10 | Hybrid weather: observed before 2024-01-21 (training only) + `weather_is_forecast` | JMA forecasts for all years; drop pre-2024 rows | no full forecast archive before 2024; JMA has no radiation and was worse (Sept {{e:demand:D2:val_mae}} vs {{e:demand:A:val_mae}}) | `reports/experiments_demand.csv` D2 | `delivery_weather_features` (fallback), `src/features/feature_sets.py` |
| D11 | Temperature bias correction per month × hour, fitted before Sept 2026 | one linear fit; no correction | lower out-of-sample error (choice saw Sept + Oct weather, disclosed) | review M1 | `src/data/check_weather_forecast.py` |

</div>

## Data

<div class="tbl tbl-decisions" markdown="1">

| ID | Decision | Alternatives considered | Why | Evidence | Where in code |
|---|---|---|---|---|---|
| D12 | ewz stamps = **end** of the interval → UTC − 15 min | start of the interval | Netzebenen correlation {{n:ewz_corr_0}} at shift 0 vs {{n:ewz_corr_p15}} at 15 min | `reports/data_checks/demand_ewz_crosscheck.md` | `src/data/load_ewz_demand.py` |
| D13 | Autumn duplicates matched to Netzebenen values | take file order | file order wrong in {{n:dst_wrong}} of {{n:dst_pairs}} pairs | same file | `src/data/load_ewz_demand.py` |
| D14 | Two missing 2021 days filled from Netzebenen and flagged | leave missing; interpolate | same quantity, same utility | `reports/data_checks.md` | `load_ewz_demand.py` |
| D15 | Keep all ewz values although none is final (W) | drop E/F values | dropping E would drop everything | `docs/assumptions_targets.md` | – |
| D16 | Gas from Yahoo `TTF=F` (unofficial) via `curl_cffi` | wait for the HSG LSEG/Bloomberg export; no gas | export not available while the user was away; plain requests got HTTP 429 | `docs/assumptions_drivers.md` | `src/data/load_gas.py` |
| D17 | CO₂ = EEX primary-auction price, carried forward | secondary market (needs LSEG/ICE) | official, free, close to the market | `docs/assumptions_drivers.md` | `src/data/load_co2.py` |
| D18 | Add European weather forecasts (D5): 9 points DE/FR/IT/CH | Zurich weather only; German TSO forecasts | the Swiss price follows German wind/solar and French temperature; TSO forecast publication time unverified | `docs/assumptions_weather_europe.md` | `src/data/load_openmeteo_europe.py` |
| D19 | German TSO and Swiss solar forecasts stored as `unverified_*`, never used | use them | publication time unknown (German wind/solar legally due D 18:00); Swiss solar scale unstable | `docs/data_sources.md` | `unverified_features` |
| D20 | Events table only with a confirmed date **and** a source URL | include likely dates | no invented data; the rest listed | `docs/events_unverified.md` | `data/manual/events_zurich.csv` |
| D21 | Swiss load quality flags (frozen, out of range, after 16 Nov 2026) | use as published | known Energy-Charts glitches | `docs/assumptions_targets.md` | `src/data/load_swiss_power.py` |

</div>

## Features and leakage

<div class="tbl tbl-decisions" markdown="1">

| ID | Decision | Alternatives considered | Why | Evidence | Where in code |
|---|---|---|---|---|---|
| D22 | Every feature = a statistic over a time window with a per-source cut-off | ad-hoc lags | one rule that a test can check | chapter 6 | `src/features/build_features.py` |
| D23 | Leakage test = rebuild 200 rows from **processed** inputs + poison test | replay from raw downloads (the brief) | fast and exact; raw → processed covered by loader tests | `tests/test_no_leakage.py` | – |
| D24 | Storage capacity is **not** a demand feature; "usage" = past demand | follow the diagram literally | a battery does not change how much the city consumes | build prompt §2 | `src/features/feature_sets.py` |
| D25 | `price_block_vs_day_ratio_last_7d` as a difference, not a ratio | a ratio | prices can be ≤ 0 | `docs/assumptions_features.md` | `price_features` |
| D26 | Feature lists from `feature_sets.py` at run time; `eu_*` added automatically | hard-coded lists | the European file was added later | `src/features/feature_sets.py` | – |

</div>

## Models

<div class="tbl tbl-decisions" markdown="1">

| ID | Decision | Alternatives considered | Why | Evidence | Where in code |
|---|---|---|---|---|---|
| D27 | Ladder naive → ridge → RF → LightGBM → best | only the best model | required by the brief; shows what each step adds | chapter 7 | `src/models/` |
| D28 | Train ≤ Aug, choose on **September** + 5-fold CV, test **once** on October | random splits; choose on October | no future in model choice | `prompts/briefs/common_models.md` | `split_frame` |
| D29 | Demand refit up to 30 Aug / **29 Sep** | 31 Aug / 30 Sep | the last day's demand is not known at the first forecast | review (Phase 3): {{n:dem_old_oct_mae}} → {{n:dem_test_mae_best}} MW | `train_rows_known_at` |
| D30 | Demand: predict **log(demand ÷ same block on D−1)** | level; 7-day reference; difference | CV {{e:demand:A:cv_mae}} vs {{e:demand:A0:cv_mae}} (level) | `reports/experiments_demand.csv` | `src/models/demand.py` |
| D31 | Demand: {{n:demand_seeds}} LightGBM seeds + {{n:demand_linear_pct}} % ridge, fitted once per month | 1 seed; 30 % ridge; daily refit | Sept {{e:demand:F2:val_mae}}; daily refit gain smaller than seed noise, 30× slower | F/G rows | `models/demand_best_params.json` |
| D32 | Demand: L2 loss, equal weights | L1, Huber, recency, COVID down-weighting | not better in CV | B/C rows | – |
| D33 | Price: predict the change vs **day-D mean + 7-day block shape** | level; other references; asinh; two-stage | CV {{e:price:A3:cv_mae}} vs {{e:price:A0:cv_mae}} (level); best on Sept | `reports/experiments_price.csv` | `src/models/price.py` |
| D34 | Price: recency half-life 1 year | none; 0.5/1.5/2 y; train only 2023+ | best on September; long history needed | B rows | `price_best_params.json` |
| D35 | Price: drop ICON `eu_*` columns, keep JMA `eu_*_jma` | keep all | better on Sept and CV; ICON has only 2.5 years | D2 row | `drop_features` |
| D36 | Price: {{n:price_seeds}} seeds + {{n:price_linear_pct}} % LEAR ridge, weekly walk-forward refit | single fit; daily refit; other blends | G1 {{e:price:G1:val_mae}} vs G0 {{e:price:G0:val_mae}}; daily not better | E/G rows | `walk_forward_best` |
| D37 | Default hyper-parameters kept after optuna | the search's best | better CV but worse on September | `reports/tuning_price.csv` | `--tune` |
| D38 | Quantile band widened ×{{n:price_band_factor}} (price) | raw quantiles | ~80 % coverage on September | chapter 8 | `ScaledQuantile` |
| D39 | Uncertainty: bootstrap over whole days; Diebold–Mariano on daily errors | row bootstrap | errors within a day are correlated | Gemini idea | `src/models/common.py` |
| D40 | Rolling-origin backtest Oct 2025 – Aug 2026 with monthly refits | only one test month | robustness evidence | chapter 11 | `rolling_backtest` |

</div>

## Optimiser, bids and backtest

<div class="tbl tbl-decisions" markdown="1">

| ID | Decision | Alternatives considered | Why | Evidence | Where in code |
|---|---|---|---|---|---|
| D41 | SciPy `milp` (HiGHS) | PuLP/CBC; `linprog` | CBC binary failed on macOS ARM | Phase 0 | `src/optimisation/battery_lp.py` |
| D42 | Binary per period: never charge and discharge together | plain LP | prevents burning energy at negative prices | test | `solve_battery_plan` |
| D43 | `mip_rel_gap = 0` (exact) | default gap | the default gap can exceed a day's battery saving | review (Phase 4) | `solve_battery_plan` |
| D44 | One cycle = {{n:usable_mwh}} MWh **delivered** | physical cap ({{n:full_swing_mwh}} MWh) | the brief's definition; ~CHF {{n:cycle_cap_cost}} effect in October, disclosed | review M4 | `solve_battery_plan` |
| D45 | Plan every day back to the configured {{n:soc_start_pct}} %; carry the **actual** end level into the next day; relax the target to the day's opening level only if it is infeasible | free end level; reset to {{n:soc_start_pct}} % every morning | no hidden borrowing between days, and a missed charge has a real cost the next day | `docs/assumptions_backtest.md` | `plan_day`, `_solve`, `run_strategy` |
| D46 | No selling back (`allow_sell: false`) | allow selling | a DSO buys for its customers; selling changes nothing for this battery | decision sensitivity | `config.yaml` |
| D47 | Demand bids price-independent; charge bids with a limit = expected discharge price × 0.9 − wear | all price-independent; quantile caps | only buy to store if it pays; 0.9 kept by tuning | `reports/decision_tuning.csv` | `charge_limit_prices` |
| D48 | Discharge spread by water filling, capped at min(need, power) | even split | no negative demand bids in low-load hours | review (Phase 4) | `allocate_discharge` |
| D49 | **Hourly shape** planning (7 days, same day type) | block plan; 14 days; all day types | gain CHF {{n:tune_gain}} with CI above 0 | `reports/decision_tuning.csv` | `hourly_price_forecast` |
| D50 | Tune once on rolling + 1–29 Sept; replace a default only on a **clear** win | tune on October; take the best point estimate | no test-month leakage; avoid noise-chasing | `check_tuning_dates` | `src/backtest/analysis.py` |
| D51 | Settle with actual prices and demand; stop on any missing value | fill with 0 or forecasts | never settle with silent zeros | review (Phase 4) | `settle_hours` |
| D52 | Assumed imbalance p ± 0.2·&#124;p&#124; | p × 1.2 / 0.8; real Swissgrid prices | &#124;p&#124; keeps a penalty at negative prices; real prices not collected | sensitivity 1.1/0.9 and 1.5/0.5 | `config.yaml` `imbalance` |
| D53 | Benchmark ("ceiling") = one hourly perfect-foresight plan over the whole period, minimising EUR with matched opening and closing stock | block-rule perfect foresight (5) | 5 was beaten by the product; 6 was the cheapest strategy in every evaluated period (but is not a proof of a bound in CHF) | review (Phase 4) | `solve_period_oracle` |
| D54 | Strategy 5b added (hourly, daily reset) | report only 5 → 6 | split dispatch vs inter-day | review M3 | `run_backtest.py` |
| D55 | Inventory-adjusted costs for all savings | raw costs only | strategies end with different stock | `docs/assumptions_backtest.md` | `adj_cost` |
| D56 | Report a {{n:ci_blocklen}}-day block-bootstrap interval next to the day bootstrap | day bootstrap only | daily savings are autocorrelated ({{n:autocorr_test}}) | review M5 | `ci_sensitivity` |
| D57 | `--require-ml` checks coverage of every day | silent date filter | a missing day must not shorten a period | review M6 | `check_ml_coverage` |
| D58 | Sensitivities run on October for information only | choose from them | nothing may be chosen with the test month | `reports/backtest_notes.md` | `run_sensitivities` |

</div>

## Process, app and publication

<div class="tbl tbl-decisions" markdown="1">

| ID | Decision | Alternatives considered | Why | Evidence | Where in code |
|---|---|---|---|---|---|
| D59 | Independent reviewer from another AI company, given code not conclusions | self-review | a reviewer handed the hypothesis tends to confirm it | chapter 3 | – |
| D60 | Temperature-correction method **not** retrained after M1 | retrain everything | effect 0.001–0.01 °C; never saw October demand or prices | review M1 | – |
| D61 | Do not change the licensed data before publishing; add a "Before you publish" note | replace now | needs the HSG export; team decision | review M7 | `README.md` |
| D62 | Replace Streamlit by a Bun + React + TanStack web app with a JSON contract | keep Streamlit | user's request; static hosting; clear data contract | commit `7b101dd` | `web/`, `src/export/export_web.py` |
| D63 | Custom battery starts each day at the same **share** of capacity as the default battery had | same MWh | bigger batteries are not penalised by starting empty | chapter 15 | `api/server.py` |
| D64 | One colour per concept in the app (stored, used, price, demand/saving) | per-chart colours | the reader learns the code once | `web/README.md` | `web/src/styles.css` |
| D65 | Run modules without `python -I` | the brief's `-I` | `-I` breaks `python -m src…` | README | – |

</div>
