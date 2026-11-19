# Backtest notes (agent B1)

> **STAND-IN FORECASTS.** The ML prediction files (`reports/predictions_demand.parquet`, `reports/predictions_price.parquet`) were not available when this file was written (source: standin). Strategies 2 and 4 use honest stand-in forecasts instead: demand = mean of the same block on the same weekday over the last 4 weeks, price = the same block on day D (already known from D-1's auction). Re-run `.venv/bin/python -m src.backtest.run_backtest` when the files exist; this note is regenerated.

All money in CHF (hourly EUR x ECB EUR/CHF). Costs = day-ahead purchases + imbalance settlement + battery wear. Saving = cost of strategy 1 minus cost of the strategy. CI = 95% day-bootstrap interval (1000 draws) of the saving vs strategy 1.

## Test month (October 2026)

| strategy | total cost CHF | saving vs 1 CHF | CI low | CI high | % of perfect | battery value CHF | % of perfect battery value | imbalance penalty CHF | wear CHF | cycles | idle days | charge cleared |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 Baseline: naive, no battery | 45,685,820 | 0.00 | 0 | 0 | 0% |  |  | 314,816 | 0 | 0.0 | 31 |  |
| 2 ML demand, no battery | 45,751,523 | -65,702 | -123,490 | -10,536 | -19% |  |  | 380,518 | 0 | 0.0 | 31 |  |
| 3 Naive + battery | 45,679,941 | 5,879 | -12,925 | 26,005 | 2% | 5,879 | 21% | 323,839 | 1,333 | 8.9 | 17 | 26% |
| 4 ML + battery (product) | 45,737,909 | -52,089 | -119,985 | 9,253 | -15% | 13,613 | 49% | 388,858 | 2,112 | 14.2 | 6 | 44% |
| 5 Perfect foresight + battery | 45,343,067 | 342,754 | 269,423 | 428,066 | 100% | 27,938 | 100% | 0.00 | 3,319 | 22.3 | 3 | 100% |
| 6 Perfect foresight, hourly plan | 45,316,379 | 369,441 | 296,974 | 455,346 | 108% | 54,626 | 196% | 0 | 4,384 | 29.5 | 0 | 100% |
| 7 Perfect demand, no battery | 45,371,004 | 314,816 | 240,757 | 403,725 | 92% |  |  | 0.00 | 0 | 0.0 | 31 |  |

- Saving of the product (4) vs baseline (1): **CHF -52,089** = better demand forecast (1-2) CHF -65,702 + battery (2-4) CHF 13,613.
- Perfect foresight (5) would save CHF 342,754; the product captures **-15%** of it. Of the perfect battery value (7-5 = CHF 27,938) the ML battery captures **49%**.
- Cost of forecast errors (vs perfect demand, no battery): naive CHF 314,816, ML CHF 380,518.
- Planning in 4-hour blocks instead of hours costs CHF 26,688 of battery value under perfect foresight (5 vs 6).

## Validation month (September 2026)

| strategy | total cost CHF | saving vs 1 CHF | CI low | CI high | % of perfect | battery value CHF | % of perfect battery value | imbalance penalty CHF | wear CHF | cycles | idle days | charge cleared |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 Baseline: naive, no battery | 32,883,845 | 0 | 0 | 0 | 0% |  |  | 209,071 | 0 | 0.0 | 30 |  |
| 2 ML demand, no battery | 32,917,392 | -33,547 | -84,009 | 16,737 | -12% |  |  | 242,619 | 0 | 0.0 | 30 |  |
| 3 Naive + battery | 32,820,441 | 63,404 | 47,112 | 83,152 | 23% | 63,404 | 93% | 206,535 | 3,298 | 21.8 | 0 | 78% |
| 4 ML + battery (product) | 32,851,575 | 32,270 | -27,191 | 90,574 | 12% | 65,817 | 96% | 238,819 | 3,420 | 22.7 | 1 | 76% |
| 5 Perfect foresight + battery | 32,606,356 | 277,489 | 239,583 | 318,946 | 100% | 68,418 | 100% | 0.00 | 4,152 | 27.5 | 0 | 100% |
| 6 Perfect foresight, hourly plan | 32,576,819 | 307,026 | 268,628 | 349,404 | 111% | 97,955 | 143% | 0 | 4,319 | 28.6 | 0 | 100% |
| 7 Perfect demand, no battery | 32,674,774 | 209,071 | 166,527 | 256,576 | 75% |  |  | 0.00 | 0 | 0.0 | 30 |  |

- Saving of the product (4) vs baseline (1): **CHF 32,270** = better demand forecast (1-2) CHF -33,547 + battery (2-4) CHF 65,817.
- Perfect foresight (5) would save CHF 277,489; the product captures **12%** of it. Of the perfect battery value (7-5 = CHF 68,418) the ML battery captures **96%**.
- Cost of forecast errors (vs perfect demand, no battery): naive CHF 209,071, ML CHF 242,619.
- Planning in 4-hour blocks instead of hours costs CHF 29,537 of battery value under perfect foresight (5 vs 6).

Note: the decision rules were tuned on September, so the September numbers are in-sample for those rules (the forecasts are not).

## Decision tuning (validation only)

Grid: charge limit factor x minimum expected spread margin, objective = total cost of ml_battery on September 2026. **Chosen: charge_limit_factor = 0.8, min_spread_eur_mwh = 0** (used for the test run).

| charge_limit_factor | min_spread_eur_mwh | cost_val_chf | cycles_val | objective_chf | is_default | vs_default_chf | chosen |
|---|---|---|---|---|---|---|---|
| 0.80 | 0 | 32,851,575 | 23 | 32,851,575 |  | -3,071 | yes |
| 0.80 | 5 | 32,852,121 | 23 | 32,852,121 |  | -2,526 |  |
| 0.80 | 10 | 32,852,121 | 23 | 32,852,121 |  | -2,526 |  |
| 0.90 | 5 | 32,854,639 | 26 | 32,854,639 |  | -7.30 |  |
| 0.90 | 10 | 32,854,639 | 26 | 32,854,639 |  | -7.30 |  |
| 0.90 | 0 | 32,854,646 | 26 | 32,854,646 | yes | 0 |  |
| none | 5 | 32,855,352 | 27 | 32,855,352 |  | 705 |  |
| none | 0 | 32,855,352 | 27 | 32,855,352 |  | 705 |  |

## Checks: do the numbers add up?

Energy conservation per hour (bought + discharged + shortage - surplus = demand + stored) and the charge-level limits are asserted in code for every hour of every run; all runs passed.

### test: 31 days

- perfect foresight (5) <= ml_battery (4): holds on 30 of 31 days (1 exceptions).
- ml_battery (4) <= baseline (1): holds on 17 of 31 days (14 exceptions).

Reasons:

| check | reason | days |
|---|---|---|
| ml_battery > baseline | demand forecast: the ML demand forecast was further off than the naive one (more imbalance) | 11 |
| ml_battery > baseline | limit bid not (fully) cleared: less energy stored, planned discharge partly not delivered | 3 |
| perfect_foresight > ml_battery | charge-level carry-over: ml_battery took more energy out of the battery than it put in (energy bought on an earlier day), perfect foresight did not | 1 |

Exception days (test):

| delivery_date | check | excess_chf | demand_part_chf | battery_part_chf | reason |
|---|---|---|---|---|---|
| 2026-10-02 | ml_battery > baseline | 1,813 | -694 | 2,508 | limit bid not (fully) cleared: less energy stored, planned discharge partly not delivered |
| 2026-10-06 | ml_battery > baseline | 1,204 | 330 | 874 | limit bid not (fully) cleared: less energy stored, planned discharge partly not delivered |
| 2026-10-15 | ml_battery > baseline | 1,107 | -1,877 | 2,984 | limit bid not (fully) cleared: less energy stored, planned discharge partly not delivered |
| 2026-10-16 | perfect_foresight > ml_battery | 298 |  |  | charge-level carry-over: ml_battery took more energy out of the battery than it put in (energy bought on an earlier day), perfect foresight did not |
| 2026-10-17 | ml_battery > baseline | 5,364 | 4,257 | 1,108 | demand forecast: the ML demand forecast was further off than the naive one (more imbalance) |
| 2026-10-18 | ml_battery > baseline | 1,599 | 2,354 | -755 | demand forecast: the ML demand forecast was further off than the naive one (more imbalance) |
| 2026-10-20 | ml_battery > baseline | 2,848 | 2,125 | 722 | demand forecast: the ML demand forecast was further off than the naive one (more imbalance) |
| 2026-10-24 | ml_battery > baseline | 9,759 | 6,310 | 3,449 | demand forecast: the ML demand forecast was further off than the naive one (more imbalance) |
| 2026-10-25 | ml_battery > baseline | 8,266 | 10,415 | -2,148 | demand forecast: the ML demand forecast was further off than the naive one (more imbalance) |
| 2026-10-26 | ml_battery > baseline | 12,251 | 11,492 | 760 | demand forecast: the ML demand forecast was further off than the naive one (more imbalance) |
| 2026-10-27 | ml_battery > baseline | 3,975 | 3,224 | 752 | demand forecast: the ML demand forecast was further off than the naive one (more imbalance) |
| 2026-10-28 | ml_battery > baseline | 18,499 | 17,575 | 924 | demand forecast: the ML demand forecast was further off than the naive one (more imbalance) |
| 2026-10-29 | ml_battery > baseline | 107 | 4,924 | -4,817 | demand forecast: the ML demand forecast was further off than the naive one (more imbalance) |
| 2026-10-30 | ml_battery > baseline | 20,387 | 17,771 | 2,616 | demand forecast: the ML demand forecast was further off than the naive one (more imbalance) |
| 2026-10-31 | ml_battery > baseline | 4,416 | 6,742 | -2,326 | demand forecast: the ML demand forecast was further off than the naive one (more imbalance) |

### val: 30 days

- perfect foresight (5) <= ml_battery (4): holds on 30 of 30 days (0 exceptions).
- ml_battery (4) <= baseline (1): holds on 19 of 30 days (11 exceptions).

Reasons:

| check | reason | days |
|---|---|---|
| ml_battery > baseline | demand forecast: the ML demand forecast was further off than the naive one (more imbalance) | 11 |

How to read the reasons:
- *demand forecast*: on that day the ML demand forecast missed more than the naive one, so the imbalance penalty was higher. One month of daily forecasts always has such days.
- *price forecast*: the battery cycled because the forecast showed a price gap between blocks, but the actual gap was smaller (or reversed), so losses + wear cost more than the gain.
- *limit bid not cleared*: the actual price was above the charge limit, the battery stayed emptier and some planned discharge could not be delivered; the city then had to buy that energy as shortage.
- *battery refill*: after a day with an uncleared charge bid, the battery is refilled to its target level; the cost appears today, the value on later days.
- *charge-level carry-over / hourly prices*: perfect foresight works with block averages and always ends the day at the target level, so on single days a forecast strategy can be cheaper.

## Sensitivities (test month, information only)

- **Price-forecast error:** about **CHF 431 of battery saving lost per 1 EUR/MWh of block-price MAE** over the month (CHF 14 per day; perfect demand, noise on true block prices, limit rule active). Perfect battery value: CHF 27,938.
  - naive price forecast: MAE 23.5 EUR/MWh, lost CHF 33,671.
  - ML price forecast: MAE 16.9 EUR/MWh, lost CHF 19,011.
- **Battery size** (battery value CHF):

| power_mw | capacity_mwh | ml_battery | perfect_foresight_battery |
|---|---|---|---|
| 5 | 10 | 3,128 | 6,607 |
| 10 | 20 | 6,967 | 13,821 |
| 20 | 40 | 13,613 | 27,938 |
| 50 | 100 | 30,796 | 70,493 |
| 100 | 200 | 54,623 | 140,985 |

- **Imbalance factors, charge limit factor, wear cost** (one at a time; `reports/backtest_decision_sensitivity.csv`, `reports/figures/backtest_decision_sensitivity.png`):

imbalance_factors:

| imbalance_factors | saving_ml_battery_vs_baseline_chf | demand_forecast_part_chf | battery_value_ml_chf | battery_value_perfect_chf |
|---|---|---|---|---|
| 1.1/0.9 | -15,068 | -32,851 | 17,783 | 27,938 |
| 1.2/0.8 | -52,089 | -65,702 | 13,613 | 27,938 |
| 1.5/0.5 | -163,152 | -164,256 | 1,104 | 27,938 |

charge_limit_factor:

| charge_limit_factor | battery_value_naive_battery_chf | share_cleared_naive_battery | battery_value_ml_battery_chf | share_cleared_ml_battery |
|---|---|---|---|---|
| 0.7 | 3,387 | 0.10 | 1.74 | 0.17 |
| 0.8 | 5,879 | 0.26 | 13,613 | 0.44 |
| 0.9 | 19,172 | 0.69 | 22,159 | 0.86 |
| 1.0 | 18,479 | 0.93 | 20,247 | 0.98 |
| 1.1 | 18,307 | 0.98 | 19,305 | 1 |
| none | 17,465 | 1 | 19,305 | 1 |

wear_cost_eur_per_mwh:

| wear_cost_eur_per_mwh | battery_value_ml_battery_chf | cycles_ml_battery | battery_value_perfect_foresight_battery_chf | cycles_perfect_foresight_battery |
|---|---|---|---|---|
| 0.0 | 18,574 | 16 | 31,874 | 26 |
| 2.5 | 14,544 | 14 | 29,780 | 24 |
| 5.0 | 13,613 | 14 | 27,938 | 22 |
| 10.0 | 11,350 | 11 | 24,476 | 21 |
| 20.0 | 10,561 | 9.37 | 18,388 | 14 |

Honest remark: the factor chosen on September (0.8) gives a test-month battery value of CHF 13,613; the config default (0.9) would have given CHF 22,159. We keep the September choice for the headline (October is never used for choices).

## Limitations

- Imbalance prices are assumed (actual DA price x 1.2 / x 0.8), not the real Swissgrid prices.
- The battery is fictional; it does not change prices (price taker).
- Hourly demand shape inside a block is taken from last week; perfect foresight uses the actual shape.
- Each period starts with the battery at the configured start level; the end-of-period level differs a little between strategies (value of that energy not counted).
- One test month; the bootstrap CI shows how uncertain the monthly totals are.
