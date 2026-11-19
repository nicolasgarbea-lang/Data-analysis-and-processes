# 11 Results

<div class="inshort" markdown="1">

In October 2026 the product saved CHF {{n:total_saving_chf_test}} against the baseline: CHF {{n:demand_forecast_part_chf_test}} from the better demand forecast
(fewer assumed penalties) and CHF {{n:battery_part_chf_test}} from the battery. That is {{n:pct_ceiling_captured_total_test}} % of the saving of the perfect-foresight benchmark (strategy 6,
the "ceiling"), and the battery reached {{n:pct_ceiling_battery_value_captured_test}} % of that benchmark's battery value. The product beat the baseline in every month of the rolling year. The result
rests on assumed imbalance prices and one test month; the honest interval is wide.

</div>

## The test month in context

{{t:test_month_context|September and October 2026 from `data/processed/hourly_actuals.parquet`. October had higher prices but smaller daily spreads.}}

{{fig:price_ch_oct2026.png|The Swiss day-ahead price in October 2026 (hourly).}}

{{fig:demand_oct2026.png|Zurich demand in October 2026 (hourly).}}

## Strategy comparison, October 2026

{{t:strategies_test|Total cost is raw; "saving vs 1" is inventory-adjusted; CI = 95 % paired bootstrap over days (treats days as independent); battery value = saving against the same strategy without battery (for 5, 5b and 6: against 7). Imbalance penalty = only the extra 0.2·&#124;p&#124; per MWh of deviation. Source: `reports/backtest_summary.csv`.}}

<div class="caveat" markdown="1">

**Simulation with assumed imbalance prices, a fictional battery and one test month.** The full imbalance settlement of
the product (penalty plus the deviation valued at p) is CHF {{n:s4_imbcost_test}}; the penalty part alone is CHF {{n:s4_penalty_test}}.

</div>

{{fig:backtest_cost_breakdown.png|Extra cost of each strategy over "perfect demand, no battery", October 2026 (all strategies except 5b, which the figure does not show; its numbers are in the table above).}}

{{fig:backtest_cumulative_savings_test.png|Cumulative saving against the baseline through October 2026.}}

## Where the saving comes from

{{t:decomposition|"From better demand forecast" = 1 − 2; "from battery" = 2 − 4, split into the plain block plan (2 − 4b) and the extra from hourly shaping and tuning (4b − 4). "Cost of 4-hour block rule" = battery value of 6 minus that of 5. Source: `reports/backtest_decomposition.csv`.}}

{{t:block_rule_split|The gap between the block rules (5) and the ceiling (6), split into finer dispatch (5 → 5b) and moving energy between days (5b → 6). Source: `reports/backtest_decomposition.csv`.}}

How to read this:

- **Demand forecast first.** The demand saving is exactly the drop in the imbalance penalty (CHF {{n:s1_penalty_test}} with the naive
  rule, CHF {{n:s2_penalty_test}} with ML). Most of the remaining gap to the ceiling is demand-forecast error that no battery can fix:
  perfect demand alone (7) would reach {{n:s7_pctceil_test}} % of the ceiling.
- **Battery second.** The product's battery made {{n:s4_cycles_test}} cycles in {{n:s4_days_test}} days, was idle on {{n:s4_idle_test}} days, and
  {{n:s4_cleared_test}} % of the offered charge **volume** cleared ({{n:charge_bids_cleared}} of {{n:charge_bids_n}} hourly charge bids, {{n:charge_bids_cleared_pct}} %).
- **Planning in 4-hour blocks costs a lot; moving energy between days costs little.** Even with perfect foresight the
  block rules earn CHF {{n:block_perfect_battery_value_chf_test}} from the battery against CHF {{n:ceiling_battery_value_chf_test}} for the ceiling. CHF {{n:finer_dispatch_part_chf_test}} of the
  gap is finer dispatch, only CHF {{n:interday_flexibility_part_chf_test}} is moving energy between days. Hourly shaping and tuning added
  CHF {{n:tuning_and_shaping_part_chf_test}} over the plain block plan.

## How wide is the interval really?

Daily savings are not independent: good and bad days come in runs (lag-1 autocorrelation {{n:autocorr_test}} in October).
Re-sampling whole {{n:ci_blocklen}}-day blocks keeps the runs together and gives a wider interval:

{{t:ci_sensitivity|Circular {{n:ci_blocklen}}-day block bootstrap, {{n:ci_nboot}} draws. Source: `reports/backtest_ci_sensitivity.csv`. The wider interval is the more honest one.}}

## Significance of the forecasts

{{t:dm_tests|Diebold–Mariano tests on daily mean absolute errors. Negative difference = the best model has smaller errors. Sources: `reports/model_tests_*.csv`.}}

{{t:blocks|October 2026 MAE per block, best model and naive rule. Source: `reports/metrics_*.csv`.}}

## Sensitivities (October; for information only, nothing was chosen from them)

**Battery size.** Battery value grows nearly in proportion to size (CHF {{n:bs_per_mwh_min}}–{{n:bs_per_mwh_max}} per MWh of capacity per month), because
the battery is assumed to be a price taker. A real large battery would flatten the price spreads it lives on.

{{t:battery_size|Source: `reports/backtest_battery_sensitivity.csv`.}}

{{fig:backtest_battery_size_sensitivity.png|Battery value against battery size.}}

**Price-forecast error.** With perfect demand and the product's rules, random errors were added to the true block
prices. The fitted slope is about CHF {{n:pe_slope}} of battery saving per month per 1 EUR/MWh of block-price MAE (CHF {{n:pe_slope_day}} a day)
– for random noise with perfect demand only. The real ML forecast (MAE {{n:pe_ml_mae}}) lost only CHF {{n:pe_ml_lost}} against perfect prices,
the naive forecast (MAE {{n:pe_naive_mae}}) CHF {{n:pe_naive_lost}}: the ML error is more in the daily level ({{n:pri_test_daymean_mae}}) than in the shape ({{n:pri_test_shape_mae}}), and the
battery needs the shape.

{{t:price_error|Source: `reports/backtest_price_error_sensitivity.csv`.}}

{{fig:backtest_price_error_sensitivity.png|Battery saving lost against the size of the price error.}}

**Imbalance price, charge limit and wear cost.**

{{t:decision_sens|Source: `reports/backtest_decision_sensitivity.csv`.}}

{{fig:backtest_decision_sensitivity.png|Decision sensitivities, October 2026.}}

The value of the demand forecast is **proportional to the assumed penalty** (CHF {{n:imb_11_09_demand}} at 1.1/0.9, CHF {{n:imb_15_05_demand}} at
1.5/0.5); the battery value hardly moves. A tighter charge limit (0.7) blocks most charging and destroys most of the
battery value.

## Robustness: the rolling year

The same model settings and the same decision rules over every day from October 2025 to October 2026. In the
rolling months both models are refit at the start of each month; in September and October the best price model is
refit every {{n:price_refit_days}} days (walk-forward) and the demand model once before each month:

{{t:monthly|Raw monthly costs from `reports/backtest.csv` (the battery carries energy over month ends, so single months are not inventory-adjusted). Oct 2025 – Aug 2026 = rolling period; Sept 2026 = validation; Oct 2026 = test.}}

The product beat the baseline in every month. The battery earns most from April to September, when solar makes the
midday price drop deep, and least in winter.

{{t:year|A careful extrapolation to one year: the backtest days that already form a full year, against 12 × October. Source: `reports/backtest_decomposition.csv`.}}

<div class="caveat" markdown="1">

**About CHF {{n:year_saving}} per year – a backtest sum, not a test.** It is the sum over the rolling period (used for tuning the
decision rules) plus September (validation). The forecasts are out of sample, but the rules were tuned on these days and
the model settings were chosen on September 2026, which comes after most of them. It holds only under the assumed
imbalance prices.

</div>

## Exceptions

{{t:exceptions|Days on which a check fails although the period total holds. "Inter-day shift": the ceiling plans the whole period and moves energy between days, so single-day comparisons with it are not meaningful. Source: `reports/backtest_exceptions.csv`.}}

The product was cheaper than the baseline on {{n:s4_cheaper_test}} of {{n:s4_days_test}} October days; on the other days the ML demand forecast missed
more than the naive one. Strategy 6 (the benchmark) was the cheapest strategy in {{n:ceiling_cheapest_periods}} evaluated periods, which the backtest
checks for every run.
