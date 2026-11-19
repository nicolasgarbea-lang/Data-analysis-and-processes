# Assumptions – decision, auction bids and backtest (agent B1)

One line each, with the reason. Code: `src/decision/bids.py`, `src/backtest/run_backtest.py`, `src/backtest/analysis.py`.

## Bids
- Bids are hourly (one demand bid + at most one charge bid per hour); the auction's 15-minute products are not modelled, because our price data is hourly.
- Demand bid per hour = block demand forecast × hour share − planned discharge of the hour (never below 0); per block the demand bids sum to forecast − planned discharge, so demand + charge bids = the plan's `buy_mwh`.
- Hour shares = actual hourly demand of the same block on delivery date − 7 days (known at forecast time; data up to D−1 is available); flat split if that week is missing.
- DST: a target hour missing from the reference week (the extra 02:00 of a 25-hour day) gets the reference block mean; a missing hour in the target day (spring) simply drops out; shares are renormalised to 1.
- Planned discharge and planned charge are split evenly over the hours of the block (keeps each hour ≤ battery power).
- Demand bids are price-independent ("market"), because the city must be supplied.
- Charge limit = expected discharge price × `bidding.charge_limit_factor` − wear cost; expected discharge price = discharge-weighted forecast price of the planned discharge blocks after the charge block.
- If no discharge follows the charge block, the discharge-weighted price of all discharge blocks of the day is used.
- If the plan has no discharge at all (pure refill to the end-of-day target), the limit = highest forecast block price of the day: the energy replaces purchases on later days, so we accept up to the most expensive expected block.
- Perfect-foresight strategies bid charge energy without a limit ("charge limit not binding").

## Settlement
- Settlement uses ACTUAL hourly day-ahead prices and ACTUAL hourly Zurich demand (`data/processed/hourly_actuals.parquet`), never forecasts.
- A charge bid clears fully if actual price ≤ limit, otherwise not at all (no partial clearing; we are a price taker).
- The battery follows the cleared plan hour by hour: efficiency √0.9 each way, power ≤ `power_mw` per hour, charge level inside [10 %, 90 %].
- Planned discharge that is impossible (battery too empty because a charge bid did not clear) is not delivered; the missing energy becomes a shortage.
- Cleared charge energy that does not fit in the battery goes to the city (counts as available energy, usually becoming surplus).
- Energy for the city per hour = demand bid + actual discharge (+ overflow); imbalance = actual demand − available energy.
- Shortage is paid at `p + (shortage_factor − 1)·|p|`, surplus is sold at `p − (1 − surplus_factor)·|p|` (p = actual hourly DA price; factors 1.2/0.8 from config `imbalance`). The |p| keeps it a penalty at negative prices. Real Swissgrid imbalance prices are not used.
- "Imbalance cost" in the outputs = net money for the imbalance energy (included in the total); "imbalance penalty" = only the extra over the DA price (shortage·0.2·|p| + surplus·0.2·|p|).
- Battery wear = wear cost × MWh actually discharged.
- Total cost = DA purchases (demand + cleared charge) + imbalance cost + wear; CHF = hourly EUR × ECB EUR/CHF of the delivery date (CHF per EUR).
- The actual end-of-day charge level is carried into the next day's plan (known at forecast time: the battery follows only the cleared bids, and day D's auction results are known since D−1).
- End-of-day target = config start level (50 %); if the optimiser cannot reach it, the target is relaxed to "end at the start level of the day" (flag `soc_target_relaxed`; never needed with the default battery).
- Every evaluation period starts with the battery at 50 %; the small end-of-period differences between strategies are not valued.
- The battery does not change market prices (price taker); no selling to the market (`allow_sell: false`).

## Strategies and forecasts
- Naive = same block 7 days earlier (`demand_lag_7d_same_block`, `price_lag_7d_same_block`, or `pred_naive` from the prediction files).
- ML = `pred_best` from `reports/predictions_<target>.parquet`; picked up automatically when the files exist; `--require-ml` fails loudly if they are missing; dates not in the files have no ML forecast (error, no silent fallback).
- STAND-IN (only while the ML files do not exist, labelled "standin" everywhere): demand = 4-week same-weekday block mean, price = same block on day D.
- Perfect foresight = actual block demand and block mean price, actual hourly shape, no charge limit; the hourly variant plans 24 (23/25) hourly periods with actual hourly values.
- Strategy 7 (perfect demand, no battery) = the pure cost of serving the city; it separates forecast-error cost from battery value.

## Tuning and sensitivities
- Decision rules (charge limit factor ∈ {0.8, 0.9, 1.0, 1.1, none}, minimum spread margin ∈ {0, 5, 10, 20} EUR/MWh) are tuned on September 2026 only (+ the rolling period when real predictions exist); October is never used for choices.
- The minimum spread margin is added to the wear cost in the plan only (the battery cycles only if the expected spread covers losses + wear + margin).
- The config defaults are kept unless another setting is strictly cheaper on validation.
- Sensitivities (battery size, price-forecast noise, imbalance factors, charge limit factor, wear cost) are run on October for information only.
- Price-error sensitivity: perfect demand, zero-mean normal noise per block on the true block prices (σ ∈ {0,5,10,20,30,45,60,80}, 5 seeds), limit rule active; lost saving = cost − cost of perfect foresight; slope from a straight-line fit.
- Bootstrap CI: whole days resampled with replacement, 1000 draws, seed from config.
