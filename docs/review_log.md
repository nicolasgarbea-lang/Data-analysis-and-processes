# Review log

Independent reviewers (a different AI model with a fresh context, read-only) checked each phase.
This file lists what they found and what we did about it.

## Phase 1 – data loaders

| Finding | Decision |
|---|---|
| The public ewz file was two days behind on the day we downloaded it, but our features use demand up to the end of yesterday (D−1). | **Kept, as an assumption.** Our fictional DSO is the grid operator and reads its own meters, so it does not wait for the public file. The demand model notes include a sensitivity run without any D−1 demand feature. |
| Reservoir levels were treated as known from Wednesday 18:00; the federal energy dashboard says Thursday. | **Fixed.** Known from Thursday 23:59, first used in Friday's forecast. |
| EV and charging figures were joined by delivery day instead of the day the forecast is made. | **Fixed.** Joined as of day D. |
| The temperature bias correction of the weather forecast is fitted once on all data up to August 2026 and applied to earlier years too. | **Kept, documented.** For the validation month (September) and the test month (October) this is clean: the correction only uses data from the training period. For the rolling 2025–26 robustness run it is a small look-ahead (the correction lowers the temperature error of the main forecast only from 1.10 to 1.04 °C). |
| Quality flags for Swiss load use a centred 7-day median (looks a few days ahead). | **Kept, documented.** A replay of all 2,848 forecast days changed no feature value. |
| Hourly averages do not check that all four quarter-hours exist; football table is 0 after the last result in the feed. | **Kept.** No such case inside the project period (checked by the reviewer). |

Checked and found correct: local-time → UTC conversion of demand including all 16 daylight-saving days, units, the
ewz interval labelling, price series (2022 mean matches the regulator's report), weather time shifts, school holiday
end dates, event dates, availability stamps of gas, CO₂ and FX.

## Phase 2 – feature table

| Finding | Decision |
|---|---|
| Before 21 Jan 2024 the weather inputs are observed values, not forecasts (no forecast archive exists for those years). | **Known limitation from the project brief.** It only affects training rows. Validation, test and the rolling run use real forecasts only. The model notes compare this with a variant that uses real (coarser) forecasts for the whole history. |
| Temperature bias correction (see above). | Kept, documented. |
| The COVID stringency index of a day is used although the measures were sometimes announced only hours before. | **Kept, documented.** It only describes 2020–2022 training rows; it is constant (0) in validation and test. |
| New columns in the European weather file would enter the model without an explicit check. | **Kept.** The file contains only leakage-safe columns today (verified by the reviewer); noted as a maintenance risk. |
| Data dictionary still said "Wednesday 18:00" for reservoirs. | **Fixed** in the docs. |

Checked and found correct: 966 feature values recomputed by hand with independent code (23 features, 7 dates
including both clock changes) all matched; all 68,688 hourly actuals match the sources; no model input equals a
target or an "oracle" column.

## Phase 3 – demand model

| Finding | Decision |
|---|---|
| The October model was trained on data up to 30 September. The demand of 30 September is not yet known when the forecast for 1 October is made. | **Fixed.** Training now stops on 29 September (and 30 August for the validation month). October error moved from 3.36 to 3.34 MW. |
| The comparison of model variants on September also includes 30 September. | **Kept.** The reviewer re-scored the candidates up to 29 September; the same variant wins. |
| Cross-validation folds before 2024 are scored with observed weather. | **Kept, documented** (no forecast archive exists for those years). |
| Sensitivity runs ("without weather", "without EVs" …) were scored on October. | **Kept, stated openly.** They were run after the settings were frozen and are not used for any choice. |

Checked and found correct: the reviewer reproduced all 105 metric rows, the confidence intervals and the
significance tests, re-fitted the model and got the same October forecasts, and confirmed that the model has no
forbidden inputs.

## Phase 3 – price model

| Finding | Decision |
|---|---|
| The code does not enforce that October is only looked at after all choices are made (the sensitivity runs print October scores). | **Kept, stated openly** in the model notes and the report. The reviewer found no path from October numbers into the saved settings. |
| The saved model file is a single fit; the scored October forecast uses weekly refits. | **Documented.** The single fit alone scores 12.35 EUR/MWh on October instead of 10.99. |
| Some explanations in the notes were too confident (bias "halved", "interconnectors were full"). | **Fixed** in the notes. |

Checked and found correct: the reference price and all price inputs stop at day D; the five weekly refits only use
prices known at the time; all metrics, decision metrics, intervals and tests were reproduced.

## Phase 3/4 – optimiser, bids, backtest

First review (with stand-in forecasts):

| Finding | Decision |
|---|---|
| "Perfect foresight" in 4-hour blocks was not a true upper limit (the product could beat it on single days). | **Fixed.** The upper limit ("ceiling") is now one hourly perfect-foresight plan over the whole period, with the same battery level at the start and the end. Savings are also reported adjusted for energy left in the battery. |
| The solver stopped at a tolerance that was large next to the small battery saving. | **Fixed.** It now solves to the exact optimum. |
| The decision settings for 1 October were tuned with one day too many. | **Fixed.** Tuning uses the rolling year plus 1–29 September only; the code refuses later days. |
| The price-error chart mixed forecast error with the cost of the bidding rules. | **Fixed.** The reference is now the zero-error run under the same rules. |
| Missing prices or exchange rates could silently count as zero. | **Fixed.** The run stops and names the hour. |
| With very low demand the hourly bids could exceed the block plan. | **Fixed.** |
| The optimiser accepted a start level outside the battery limits. | **Fixed.** It raises an error. |

Second review (final numbers, with the real forecasts):

| Finding | Decision |
|---|---|
| The hourly ceiling is optimised in EUR with a fixed end level, but compared in CHF with a credit for energy left over; optimising exactly the reported figure would lower it by CHF 653. | **Kept, documented.** The effect is 0.2 % of the ceiling's saving. |
| The headline saving depends on the assumed imbalance prices: with ±10 % instead of ±20 % the October saving falls from CHF 226k to CHF 136k; the battery part stays at about CHF 45k. | **Stated in the report** as the main sensitivity. |

Checked and found correct: all October costs were recomputed from the hourly ledger and from the raw actuals and
match to the cent; the product uses exactly the two models' forecasts; the baseline uses exactly the 7-day lags;
tuning never saw October; the ceiling is the cheapest strategy in every period.
