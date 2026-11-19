# 6 The no-future rule and the feature table

<div class="inshort" markdown="1">

A forecast made at 10:00 on day D may only use what was published by then. The feature table has one row per
delivery day and 4-hour block ({{n:feat_rows}} rows, {{n:feat_cols}} columns) and every column is computed from a time window that ends
before 10:00 on D. An automated test rebuilds 200 rows from data cut at that moment and "poisons" everything later; a
reviewer recomputed 966 values by hand. What the test cannot catch is listed at the end.

</div>

## What is known at 10:00 on day D

{{svg:known_at|The no-future rule on a time axis. Bars show the data each input may use for a forecast made at 10:00 on day D (plum line) for delivery day D+1 (green area).}}

The most important consequences:

- The **latest demand** is the full day D−1, i.e. **two days before delivery**. So "the same block yesterday" for
  delivery day D+1 is the lag `demand_lag_2d_same_block`, not a 1-day lag.
- The **latest price** is all of day D (the auction for D ran on D−1), i.e. **one day before delivery**:
  `price_lag_1d_same_block`, `price_mean_day_D`.
- **Weather of D+1 can only be a forecast.** The rule picks, for every target hour, the freshest model run that was
  published by 10:00 on D. For the night hours of D+1 that is a run from D itself; for daytime hours it is the run from
  the day before (two days ahead), because the morning run of D is not out by 10:00.
- **Before 21 January 2024 there is no forecast archive** with all variables. In those years the weather columns
  contain *observed* weather (training rows only); the column `weather_is_forecast` tells the model which regime a row is
  in. Validation, test and the rolling run use real forecasts only. {{n:feat_fc_share}} % of all rows have real forecasts.

## The feature table

`data/processed/features.parquet` has one row per (delivery date, block): {{n:feat_days}} delivery days × 6 blocks =
{{n:feat_rows}} rows, from {{n:feat_first}} to {{n:feat_last}}. Every row carries `delivery_date` (D+1) and
`forecast_issue_time_utc` (D 10:00 in UTC), the two targets `demand_mw` and `price_eur_mwh` (mean of the block,
NaN if any hour is missing), `hours_in_block`, and the actuals used for the backtest (prefixed `actual_`, never inputs).

**How every feature is computed.** In `src/features/build_features.py` every time-series feature is "a statistic
(mean, max …) of one hourly column over one time window [start, end) in UTC". Windows are built from the **local**
clock, so clock-change days come out right. A guard in `Ctx.window()` stops the build with an error if a window breaks
its family's rule; the rule differs per family:

| Feature family | Rule enforced for a forecast made on D at 10:00 |
|---|---|
| Zurich demand, Swiss load/generation | window ends by the end of D−1 |
| CH and neighbour prices | window ends by the end of D (auctions ran on D−1) |
| Observed weather | hours ending by 09:00 on D (issue time − 1 h) |
| Weather forecasts (Zurich, Europe) | window inside the **delivery day** D+1 (valid times); that the run itself was published by 10:00 is ensured separately by the loaders (`safe_lead_days`) |
| Gas, CO₂, EUR/CHF, reservoirs | latest value with `available_from_utc` ≤ issue time (as-of lookup) |
| Calendar, holidays, events, football | describe the **delivery day** itself (known in advance) |
| EVs and charging stations | values as published on day D (`_known` columns, `solar_and_ev_features`) |

{{t:feature_groups|Feature groups as used by the models (`src/features/feature_sets.py`). The demand model uses {{n:n_demand_features}} default inputs, the price model {{n:n_price_features}} (including {{n:n_eu_features}} European weather columns, of which the price model later drops the ICON ones).}}

Columns that are **never** model inputs: `*_obs` (observed weather of the delivery day, only for "oracle" benchmarks),
`actual_*` (for settlement), `unverified_*` (German TSO and Swiss solar forecasts with unknown publication time), and
the other target of the same row. `tests/test_no_leakage.py` checks that the default lists contain none of them.

A few definitions worth knowing (more in `docs/data_dictionary_features.md`):

| Column | Definition |
|---|---|
| `demand_lag_2d_same_block` | demand of the same block on D−1 – the reference of the demand model |
| `demand_dm1_block_0` … `_5` | all six blocks of D−1 (yesterday's shape) |
| `price_block_vs_day_ratio_last_7d` | mean over D−6 … D of (block price − day mean); a difference, not a ratio, because prices can be ≤ 0 |
| `clean_gas_cost` | gas ÷ 0.5 + 0.37 × CO₂: short-run cost of a gas plant (50 % efficiency, 0.37 t CO₂/MWh) |
| `heating_degree`, `cooling_degree` | max(0, 15 − T), max(0, T − 22) |
| `lag2d_was_holiday` | the reference day (D−1) was a holiday – the demand model's weak spot |
| `co2_staleness_days` | days since the last CO₂ auction used (auctions pause around New Year) |
| `weather_is_forecast` | 1 = real ICON forecast, 0 = observed weather (before 2024-01-21, training only) |

## How leakage is tested

`tests/test_no_leakage.py` has five tests:

1. **Rebuild.** For 200 sampled rows, every input table is cut down to what was known at that row's
   `forecast_issue_time_utc`. The cut rules are written **again, independently** of the feature code. The delivery date is
   rebuilt with `build_features()` and every default feature must be **exactly** equal to the stored value.
2. **Poison.** Every value *not yet known* at the issue time gets +1,000,000. If any feature used a future value, it
   would change. None does.
3. **Hand checks.** Five features for delivery 2026-10-15, block 08–12, recomputed with plain pandas.
4. **Clean lists.** The default feature lists contain no oracle, actual, unverified or target column.
5. **Sample check.** The sample contains the rows it must (both clock changes, the test month).

In addition, the Phase 2 reviewer recomputed **966 feature values** (23 features, 7 dates including both clock
changes) with independent code; all matched. The final reviewer recomputed 5 features for 15 and 25 October.

## What the test cannot catch

| Gap | Why it is not covered | How it is handled |
|---|---|---|
| Raw → processed step | the test starts from the processed tables, not the raw downloads | loader tests, data checks, reviewers' hand checks (stated in README and report) |
| Wrong publication-time *assumption* | the test enforces the rule we wrote; if the rule itself is too optimistic, the test agrees | rules documented with sources (`docs/auction_timing.md`, `docs/assumptions.md`) |
| Demand known to D−1 | an assumption (DSO reads its own meters); the public file lags | sensitivity: without D−1 demand the October single-model error rises from {{e:demand:S0:test_mae}} to {{e:demand:S1:test_mae}} MW |
| Archived forecasts = real-time forecasts | cannot be verified after the fact | stated as an assumption |
| Observed weather in training before 2024 | intended (no archive) | `weather_is_forecast`; only training rows |
| Temperature bias correction | coefficients fitted on data before September 2026 are applied to earlier years too (small look-ahead for the rolling run); the **method** was chosen with September + October weather | disclosed (chapter 12, finding M1) |
| Centred 7-day window in the Swiss load quality flag | it looks a few days ahead | only a flag; a replay of all forecast days changed no feature value |
| COVID index of the day | measures were sometimes announced only hours before | training rows 2020–2022 only; 0 in validation and test |
| New columns in the European weather file | would enter the price model without an explicit check | the file contains only safe columns today; maintenance risk |
