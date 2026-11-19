# A Glossary

<div class="inshort" markdown="1">

Every technical term used in this report, in one sentence each, in alphabetical order.

</div>

| Term | Meaning |
|---|---|
| as-of join | take, for each row, the latest value of another table that was available at or before a given time |
| asinh transform | a log-like scaling that also works for zero and negative numbers; tried for prices, not used |
| backtest | replaying the past day by day with only the information available at each moment, and settling the result |
| bias | the average of (forecast − actual); negative = forecasts too low |
| bidding zone | an area with one market price; Switzerland is one zone ("CH") |
| block | one of the six 4-hour periods of a local day: 00–04 … 20–24 |
| block bootstrap | a bootstrap that resamples runs of consecutive days (here {{n:ci_blocklen}}) to keep their correlation |
| bootstrap interval | a range found by resampling the data many times; here whole days are resampled |
| bridge day | a working day between a holiday and a weekend |
| ceiling (strategy 6) | the perfect-foresight benchmark: one hourly plan over the whole period with the same battery limits, minimising the EUR purchase cost with the same stock at the end as at the start. It was the cheapest strategy in every evaluated period; savings are compared in CHF with an inventory adjustment, so it is a named benchmark, not a proven bound |
| charge limit | the highest auction price at which a charge bid still buys |
| clean gas cost | gas price ÷ 0.5 + 0.37 × CO₂ price: the fuel and carbon cost of a gas power plant |
| CO₂ / EUA | the EU carbon allowance price, EUR per tonne |
| cross-validation (time-series) | evaluating a model on several later periods, always training on earlier data |
| cycle | here: {{n:usable_mwh}} MWh delivered by the battery in a day |
| day D / D+1 | the day the forecast is made / the delivery day |
| day-ahead auction | the daily auction in which tomorrow's energy is bought, hour by hour |
| decomposition | splitting the product's saving into the demand-forecast part and the battery part |
| Diebold–Mariano test | a test of whether one forecast's errors are significantly smaller than another's |
| DSO | distribution system operator: runs a local grid and buys energy for its customers |
| DST | daylight saving time; clock changes create 23- and 25-hour days |
| ensemble | an average or blend of several models |
| EPEX SPOT | the power exchange that runs the Swiss day-ahead auction |
| ERA5 | a weather reanalysis; uses observations of the hour itself, so never a forecast input |
| feature | an input column of a model |
| forecast issue time | 10:00 Zurich time on day D, the moment the forecast is made |
| gate closure | the deadline for bids ({{c:auction.gate_closure_local}} for the Swiss auction) |
| gradient boosting / LightGBM | many small decision trees, each correcting the previous ones; LightGBM is a fast implementation |
| HiGHS | the open-source optimisation solver used through SciPy |
| hourly shape | the typical difference of each hour from its block mean over the last 7 days of the same day type |
| hybrid weather | real forecasts where available (from 2024), observed weather before (training only) |
| ICON / ECMWF / JMA | weather models of the German, European and Japanese weather services |
| imbalance | the difference between energy bought and energy used, settled with the TSO |
| imbalance penalty | the extra cost of an imbalance above the auction price (0.2·&#124;p&#124; per MWh here) |
| inventory adjustment | correcting a period's cost for the energy left in the battery at the end |
| lag | a past value; `_lag_2d` = the same block two days before delivery |
| leakage | using information in a forecast that was not available at forecast time |
| LEAR | "lasso-estimated autoregressive" – a linear price model style; here a ridge regression on the price change |
| limit bid | a bid that buys only if the price is at or below a set price |
| MAE | mean absolute error: the average size of the miss |
| MAPE / sMAPE | mean absolute percentage error / its symmetric version that works near zero prices |
| mixed-integer program (MILP) | an optimisation with some yes/no variables |
| naive forecast | the same block 7 days earlier |
| oracle | a run that uses information not available at forecast time, only as a benchmark |
| permutation importance | how much the error grows when one input (or group) is shuffled |
| poison test | adding a huge number to all future values and checking that no feature changes |
| previous-runs API | Open-Meteo service that returns what a weather model predicted 1 or 2 days before |
| price taker | a market participant too small to move the price |
| price-independent bid | a bid that buys its volume at any price |
| quantile model / band | a model of the 10 % and 90 % points of the forecast distribution |
| random forest | an average of many decision trees trained on random samples |
| recency weighting | giving recent training rows more weight (half-life in years) |
| ridge regression | linear regression with a penalty that keeps coefficients small |
| RMSE | root mean squared error: like MAE but punishes large misses more |
| rolling period / rolling-origin backtest | 1 Oct 2025 – 31 Aug 2026, models refit every month and tested on the next |
| round-trip efficiency | share of the energy put into the battery that comes out again ({{n:rte_pct}} %) |
| SDAC | the single day-ahead coupling of EU markets (closes 12:00); Switzerland is not part of it |
| seed | the starting number of a random process; several seeds are averaged to reduce noise |
| skill vs naive | 1 − model MAE ÷ naive MAE |
| state of charge (SoC) | the energy stored in the battery |
| strategy | a combination of forecasts and battery rules settled in the backtest (1–7, 4b, 5b) |
| test / validation month | October 2026 (evaluated once) / September 2026 (used for choices) |
| TSO | transmission system operator (Swissgrid): runs the national grid and settles imbalances |
| TTF | the Dutch gas hub price, the European gas benchmark |
| walk-forward refit | refitting a model regularly during the test period with the data known at that time |
| water filling | spreading an amount over hours as evenly as possible under per-hour caps |
| wear cost | an assumed cost per MWh discharged that stands for battery ageing ({{c:battery.wear_cost_eur_per_mwh}} EUR/MWh) |
