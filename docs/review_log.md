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

## Phase 3/4 – optimiser, bids, backtest

(see the end of this file; filled in after the fixes)
