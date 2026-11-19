# 10 Bids, settlement and strategies

<div class="inshort" markdown="1">

The plan becomes hourly auction bids: a price-independent bid for the city's need and a limit bid for energy to store.
The backtest clears and settles these bids with the **actual** hourly prices and demand, adds the assumed imbalance
price and battery wear, and compares nine strategies – from "last week's demand, no battery" to a perfect-foresight
ceiling. The decision rules were tuned once on data before October; planning **hour by hour** inside the blocks won
clearly.

</div>

## From plan to hourly bids

The auction trades single hours, so `src/decision/bids.py` turns the period plan into hourly bids:

| Bid | Volume per hour | Price |
|---|---|---|
| **Demand bid** | forecast need of the hour − planned discharge of the hour | **price-independent** ("buy at any price"), because Zurich must be supplied |
| **Charge bid** | planned charging of the hour | **limit price** = expected discharge price × {{c:bidding.charge_limit_factor}} − wear cost; it clears only if the auction price is at or below it |
| (option) protection bid | discharge that depends on an uncleared charge bid | price-independent; tested and **not** chosen |

Details that matter:

- **Hourly need.** The block forecast is split into hours with the shape of the same block one week earlier (the
  actual demand of D+1 − 7 days, known at forecast time); a flat split if that week is missing.
- **No negative bids.** Planned discharge is spread over the block's hours as evenly as possible but never above
  min(hour's need, battery power) ("water filling"); block totals are conserved exactly. This was a review fix: in
  low-load hours the discharge could exceed the need.
- **Expected discharge price** (`charge_limit_prices`) = discharge-weighted forecast price of the planned discharge
  periods after the charge period. If no discharge comes later that day (an evening refill after a morning
  discharge), all of the day's planned discharge is used instead. A **pure refill** (no discharge planned at all) gets
  the day's highest forecast price as its limit **directly**: no factor, no wear deduction and no q90 cap.

## The hourly price shape (why the product plans hours)

A {{c:battery.power_mw}} MW / {{c:battery.capacity_mwh}} MWh battery fills or empties in two hours, so it fits *inside* one 4-hour block. Block averages
hide most of the spread it could use. The chosen planning mode `hourly_shape` therefore builds an hourly price
forecast: **block forecast + the average deviation of each hour from its block mean over the last 7 days of the same
day type** (workday or weekend/holiday; it looks back at most eight weeks to find seven such days), re-centred so
that each block keeps its forecast mean. Those past prices are
all known at 10:00 on D. The optimiser then plans 23/24/25 hours. The user still sees the six-block decision table with
the team's option labels.

## Settlement

{{svg:settlement|From bids to the bill, hour by hour, in the backtest (`src/backtest/run_backtest.py`).}}

For every day: forecast → plan → bids → settlement with the actual hourly price p and the actual hourly demand
(`data/processed/hourly_actuals.parquet`, {{n:hourly_actuals_rows}} hours):

1. A charge bid clears **fully** if p ≤ limit, otherwise not at all (price taker, no partial clearing).
2. The battery follows **what was really bought**, hour by hour, within its limits. Planned discharge that is now
   impossible is not delivered: it first reduces any surplus of that hour and only the rest becomes shortage; cleared
   charge that does not fit goes to the city.
3. The gap between delivered energy and actual demand is the **imbalance**: shortage costs
   p + {{n:imb_short_pct}} % × |p|, surplus earns p − {{n:imb_surplus_pct}} % × |p|. "Imbalance penalty" in the outputs is only the extra versus p;
   "imbalance settlement" is the whole amount.
4. **Total cost** = auction purchases + imbalance settlement + wear; EUR → CHF with the ECB rate of the delivery date.
5. The actual end-of-day charge level is carried into the next day.

Safety rules added after review: a missing or non-finite price, demand or exchange rate **stops the run** naming the
hour (it is never summed as 0); every day must have 23/24/25 consecutive hours; energy conservation, charge limits and
"never charge and discharge in the same hour" are asserted for every hour of every run. With `--require-ml`, every day
of every period must have six finite predictions per target, else the run stops naming the day (final review, M6).

## The strategies

| # | Strategy | Demand forecast | Price forecast | Battery |
|---|---|---|---|---|
| 1 | Baseline | naive (same block last week) | – | none |
| 2 | ML demand | ML | – | none |
| 3 | Naive + battery | naive | naive | tuned rules |
| 4 | **Product** | ML | ML | tuned rules (hourly shape) |
| 4b | Product, untuned | ML | ML | block plan, config defaults |
| 5 | Perfect foresight, block rules | actual | actual | the same 4-hour block rules, back to 50 % every evening |
| 5b | Perfect foresight, hourly, daily reset | actual | actual | hourly plan per day, back to 50 % every evening |
| 6 | **Ceiling** | actual | actual | one hourly plan over the whole period |
| 7 | Perfect demand | actual | – | none |

**Why a new ceiling.** The brief called strategy 5 the "upper limit". The first backtest review showed it is not: it
uses the coarse block rules, and the product (which plans hours) beat it on battery value. The ceiling (6) is one
hourly perfect-foresight plan over **all hours of the period**, with the same battery limits and the same end level as
start level. It minimises the **EUR** purchase cost with matched opening and closing stock, while the comparison is in
**CHF** with an inventory adjustment, so it is a named benchmark rather than a proven bound: it was the cheapest
strategy in {{n:ceiling_cheapest_periods}} evaluated periods, and "% of ceiling" means a share of this benchmark. Strategy 5b (added after the final review, M3) plans hours like the ceiling but must return to the start level
every evening like 5, which splits the gap 5 → 6 into **finer dispatch** (5 → 5b) and **moving energy between days**
(5b → 6).

**Inventory adjustment.** Strategies end the period with different amounts of energy in the battery. The adjusted cost
subtracts (end − start stock) × discharge efficiency × the period's mean actual price × the mean EUR/CHF rate. All
savings and "% of ceiling" use the adjusted numbers. The reviewer noted that the ceiling is optimised in EUR with a
fixed end level but compared in CHF with this credit; optimising exactly the reported figure would lower it by
CHF {{n:ceiling_eur_gap}} – kept and documented.

## Decision tuning (why "hourly shape" won)

The planning mode, a minimum spread margin, the charge-limit factor and the protection bid were tuned **once** for the
test month, on the rolling period ({{n:tune_days_roll}} days) plus 1–{{n:tune_days_sept}} September. 29 September is the last day whose
settlement is known at 10:00 on 30 September, when the first October day is planned; `check_tuning_dates` enforces this
cut-off ({{n:tune_cutoff}}). October was never used. A candidate replaced the default only if it **clearly** won: a higher combined
saving **and** a 95 % paired-bootstrap interval of the gain above zero.

- **Stage 1** ({{n:tune_n_stage1}} candidates): plan resolution (block; hourly shape from the last 7 days, 7 days of the same day type,
  14 days) × margin (0, 5, 10, 20 EUR/MWh).
- **Stage 2** ({{n:tune_n_stage2}} candidates): on the stage-1 winner, limit factor (0.8, 0.9, 1.0, 1.1, no limit, and the q90 cap
  combined with factor 0.9 and with 1.0) × protection bid.

**Chosen: {{n:tune_chosen}}.** The hourly shape beat the block plan by CHF {{n:tune_gain}} over the
tuning days (95 % interval {{n:tune_gain_lo}} to {{n:tune_gain_hi}}); no margin, the default limit factor and no protection bid stayed,
because every alternative was worse (the protection bid cost about CHF {{n:tune_protect_loss}}).

{{fig:backtest_decision_tuning.png|Decision tuning on the rolling period and 1–29 September.}}

{{t:tuning_all|Every tuning candidate. Source: `reports/decision_tuning.csv`.}}
