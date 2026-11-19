# Assumptions – decision, auction bids and backtest (agents B1, B2)

One line each, with the reason. Code: `src/decision/bids.py`, `src/backtest/run_backtest.py`, `src/backtest/analysis.py`.

## Planning (decision options, `config.yaml` → `bidding`)
- The user always sees the 6-block decision table (option labels per block); the bids are hourly anyway, so the optimiser may plan per block (`plan_resolution: block`) or per hour (`hourly_shape`).
- `hourly_shape`: hourly price forecast = block price forecast + typical within-block hourly shape; shape of local hour h = mean over the last `shape_days` days STRICTLY before the delivery day (T−1 = day D, prices known since the D−1 auction) of (hourly price − that day's block mean); re-centred so each block keeps its forecast mean. Reason: a 2-hour battery fits inside a 4-hour block, so block averages hide most of the spread.
- `shape_daytype: true` uses only past days of the same type (workday vs weekend/holiday, from `is_weekend`/`is_holiday`), within the last 8 weeks.
- Hourly demand forecast = block forecast × last week's hourly shape of the same block (the same shares used for the bids).
- DST: the shape uses the local clock hour; on the 25-hour day both 02:00 hours get the same shape value, on the 23-hour day hour 2 simply does not exist; the optimiser then plans 25 or 23 periods.
- Option label of a block in hourly mode = label of the block sums; if a block both charges and discharges, the net direction decides (`buy_and_store` or `use_storage_and_buy`).
- `min_spread_eur_mwh` is added to the wear cost in the plan only (cycle only if the expected spread covers losses + wear + margin); the real wear is billed.
- End-of-day target = config start level (50 %); the target is relaxed to "end at the day's start level" ONLY if the optimiser reports the problem as infeasible (flag `soc_target_relaxed`); any other solver failure stops the run.

## Bids
- Bids are hourly (one demand bid + at most one charge bid per hour); 15-minute products are not modelled, because our price data is hourly.
- Demand bid per hour = forecast need of the hour − planned discharge of the hour; price-independent ("market"), because the city must be supplied.
- Hour shares = actual hourly demand of the same block on delivery date − 7 days (known at forecast time); flat split if that week is missing; a target hour missing from the reference week gets the reference block mean; shares are renormalised to 1.
- Planned discharge of a block is spread over its hours as evenly as possible but never above min(hour's forecast need, battery power) (water filling); block totals are conserved exactly, so demand bids are never negative.
- To guarantee this, the block optimiser gets the block demand capped at Σ_h min(need_h, power); the rest of the block is bought price-independently outside the optimisation (a constant cost, so the plan is unchanged except for this extra limit).
- Planned charge is split evenly over the block's hours (≤ power, because the block charge ≤ power × hours).
- Charge limit = expected discharge price × `charge_limit_factor` − wear cost (expected discharge price = discharge-weighted forecast price of the planned discharge periods after the charge period, else of all discharge periods of the day); pure refill (no discharge planned) → limit = highest forecast price of the day; `use_limit: false` → price-independent charge bids.
- `limit_rule: quantile` additionally caps the limit at the q90 price forecast of the charge period (only when `pred_q90` exists in the price predictions).
- `protect: at_risk_bid`: planned discharge not covered by the energy surely available (start stock above minimum + price-independent charges) is added to the price-independent demand bid; if not needed it is sold back as surplus.
- Oracles (5, 5b, 6) bid charge energy without a limit, use physical wear only, no margin, no protection.

## Settlement
- Settlement uses ACTUAL hourly day-ahead prices and ACTUAL hourly Zurich demand (`data/processed/hourly_actuals.parquet`), never forecasts.
- Every delivery day must have 23/24/25 consecutive hours; a missing or non-finite actual price, demand or EUR/CHF value (and a non-finite bid) stops the run with a ValueError naming the hour – it is never summed as 0.
- A charge bid clears fully if actual price ≤ limit, otherwise not at all (price taker, no partial clearing).
- The battery follows the cleared plan hour by hour: efficiency √0.9 each way, power ≤ `power_mw` per hour, charge level inside [10 %, 90 %]; planned discharge that is impossible is not delivered (becomes shortage); cleared charge that does not fit goes to the city.
- Imbalance price (p = actual hourly DA price): shortage costs `p + (shortage_factor − 1)·|p|` per MWh, surplus earns `p − (1 − surplus_factor)·|p|` per MWh (factors 1.2/0.8 from config `imbalance`); |p| keeps it a penalty at negative prices. Real Swissgrid imbalance prices are not used.
- "Imbalance penalty" in the outputs = only the extra over the DA price; total cost = DA purchases + imbalance cost + wear; CHF = hourly EUR × ECB EUR/CHF of the delivery date.
- The actual end-of-day charge level is carried into the next day (known at forecast time); drift ≤ 1e-6 MWh is clipped, anything larger is an error.

## Strategies, ceiling and inventory
- Strategies: 1 baseline (naive demand, no battery), 2 ML demand no battery, 3 naive forecasts + battery (tuned rules), 4 product = ML + battery with the tuned rules, 4b ML + battery with the plain block plan and config defaults, 5 perfect foresight with the same 4-hour block rules, 5b perfect foresight with an hourly plan per day and the same end-of-day target as 5 (added after the final review), 6 ceiling, 7 perfect demand without battery.
- Decomposition (`reports/backtest_decomposition.csv`): `block_rule_cost_chf` = C5 − C6 = `finer_dispatch_part_chf` (C5 − C5b) + `interday_flexibility_part_chf` (C5b − C6); October: CHF 31,670 = 27,002 + 4,668.
- Cycle definition (from the brief): Σ discharge delivered to the grid ≤ `max_cycles_per_day` × (soc_max − soc_min) = 32 MWh per day. A full swing of the usable stored energy delivers only 32 × √0.9 = 30.36 MWh, so this allows about 5 % more than one physical full cycle (on 27 of 31 October days the product uses this margin; physical cap ≈ −CHF 1,000 of October battery saving). Kept as in the brief.
- Ceiling (6) = ONE hourly perfect-foresight MILP over all hours of the period: power, charge limits, ≤ 1 cycle per delivery day, discharge ≤ hourly demand, end-of-period charge level = start level (matched inventory); simultaneous charge/discharge forbidden by a binary in negative-price hours (elsewhere it never pays and is netted out). It is a true lower bound; single-day comparisons with it are not meaningful (it shifts energy between days).
- `plan_day` for strategy 6 on a single day (app) solves that day alone with end level = start level.
- Every evaluation period starts at 50 %. Inventory adjustment (reported next to the raw numbers): adjusted cost = raw cost − (end − start charge level) × discharge efficiency × the period's mean actual DA price × mean EUR/CHF. Reason: a strategy that ends emptier used energy it did not pay for in the period.
- "% of ceiling" and battery values use the adjusted costs.
- Naive = same block 7 days earlier (`*_lag_7d_same_block` or `pred_naive`); ML = `pred_best` from `reports/predictions_<target>.parquet`, picked up automatically; dates not in a file have no ML forecast (error, no silent fallback); `--require-ml` fails if a file is missing, and (after the final review) also if any calendar day of the tuning, validation, test or rolling period lacks input data or six finite predictions per target (`check_ml_coverage`; the error names the day and the target).
- STAND-IN (only while a prediction file does not exist, labelled "standin" in every output and in the notes): demand = 4-week same-weekday block mean, price = same block on day D.

## Tuning and sensitivities
- The decision rules for the test month are tuned ONCE on the rolling period (2025-10-01 → 2026-08-31, `periods.rolling_start`) plus September up to 2026-09-29 (test start − 2 days: the last day whose settlement is known on 30 Sept 10:00); October is never used; `check_tuning_dates` enforces this.
- Objective = product's inventory-adjusted saving vs baseline, rolling + September (both recorded separately and combined in `reports/decision_tuning.csv`).
- Stage 1: plan resolution (block; hourly shape 7 d, 7 d same day type, 14 d) × margin {0, 5, 10, 20}; stage 2 on the winner: limit factor {0.8, 0.9, 1.0, 1.1, none} (+ q90 rule if available) × protection {none, at_risk_bid}.
- A candidate replaces the stage reference only if it clearly wins: higher combined saving AND 95 % paired day-bootstrap interval of the improvement above 0; otherwise the defaults are kept.
- Strategy 3 uses the same tuned rules as the product (isolates forecast quality).
- Sensitivities (battery size 5/10 … 100/200, price-forecast noise, imbalance factors, charge limit factor, wear cost, allow_sell) are run on October for information only.
- Price-error sensitivity: perfect demand, zero-mean normal noise per block on the true block prices (σ ∈ {0,5,10,20,30,45,60,80}, 5 seeds), the product's rules; reference = the zero-noise run with the SAME rules (lost saving = cost(σ) − cost(0)); the zero-noise run's gap to the ceiling / block oracle is reported separately as the policy cost.
- Bootstrap CI: whole days resampled with replacement (paired: same days for both strategies), 1000 draws, seed from config; the inventory adjustment enters as a constant shift. This assumes independent days.
- Block-bootstrap CI (`reports/backtest_ci_sensitivity.csv`, `analysis.ci_sensitivity`): circular moving-block bootstrap with 7-day blocks of the product's daily saving vs the baseline, 1000 draws, same seed, same inventory shift; reported with the lag-1 autocorrelation of the daily savings (October 0.57 → CHF 129,685 to 354,460 instead of 158,868 to 306,077).
