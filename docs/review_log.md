# Review log

Independent reviewers (a different AI model with a fresh context, read-only) checked each phase.
This file lists what they found and what we did about it.

## Phase 1 – data loaders

| Finding | Decision |
|---|---|
| The public ewz file was two days behind on the day we downloaded it, but our features use demand up to the end of yesterday (D−1). | **Kept, as an assumption.** Our fictional DSO is the grid operator and reads its own meters, so it does not wait for the public file. The demand model notes include a sensitivity run without any D−1 demand feature. |
| Reservoir levels were treated as known from Wednesday 18:00; the federal energy dashboard says Thursday. | **Fixed.** Known from Thursday 23:59, first used in Friday's forecast. |
| EV and charging figures were joined by delivery day instead of the day the forecast is made. | **Fixed.** Joined as of day D. |
| The temperature bias correction of the weather forecast is fitted once on all data up to August 2026 and applied to earlier years too. | **Kept, documented.** For the validation month (September) and the test month (October) the **coefficients** are clean: they only use data from the training period. For the rolling 2025–26 robustness run it is a small look-ahead (the correction lowers the temperature error of the main forecast only from 1.10 to 1.04 °C). *Corrected after the final review:* the choice of the correction **method** (month × hour offsets vs one linear fit) did see October weather, because it compared errors on September and October; the two methods differ by about 0.001–0.01 °C (see "Final review", M1). |
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

## Final review (whole project, after all phases)

A last independent reviewer rebuilt the project from the raw files on Python 3.11 (12.6 min) and reproduced both
metric files (max difference about 1e-14), both backtest files byte for byte, all 154 tests, the leakage suite, the
20 report tables, the four notebooks, five features by hand, the 25 October settlement (CHF 1,394,378.66) and the
headline numbers. Models and forecasts were **not** retrained for the fixes below; the existing backtest numbers are
unchanged (checked: maximum difference 0), the fixes only add outputs.

| Finding | Decision |
|---|---|
| M1 The choice of the temperature-correction method used September and October weather errors (the coefficients use data before September only). On September alone the single linear fit wins by a hair (0.8929 vs 0.8942 °C); with October the shipped month × hour method wins (0.9288 vs 0.9407 °C). | **Kept, disclosed.** Not retrained: the difference is about 0.001–0.01 °C and the choice never saw October demand or prices. Stated in report §1 and §8, `docs/assumptions.md` and the Phase 1 row above. |
| M2 The headline saving needs the imbalance assumption next to it: the assumed penalty explains CHF 181,033 of CHF 226,499 (about 80 %); with ±10 % the saving is CHF 135,998. Real Swissgrid settlement is quarter-hourly with a single price since 2026. The 365-day number mixes the tuning period and September. | **Fixed (text).** Caveat next to the numbers in the README, one-pager, slides, app (Month backtest tab) and the report summary box and §7; CHF 2,382,678 labelled "sum over the rolling period (used for tuning) plus September (validation) – not an out-of-sample test". |
| M3 "4-hour blocks cost CHF 31,670" mixes finer dispatch with moving energy between days. | **Fixed.** New information strategy 5b (hourly perfect foresight, daily reset) and new columns `hourly_daily_battery_value_chf`, `finer_dispatch_part_chf`, `interday_flexibility_part_chf` in `reports/backtest_decomposition.csv`: October CHF 27,002 finer dispatch + CHF 4,668 inter-day flexibility. Old `block_rule_cost_chf` kept. Test added. |
| M4 The optimiser counts 32 MWh delivered as one cycle; a full swing of the usable stored energy delivers only 30.36 MWh, so the battery does slightly more than one physical cycle on 27 of 31 October days (about CHF 1,049 of battery saving). | **Kept, documented.** The brief's definition stays; stated in report §5.3 and §8, the assumptions files, the docstring of `solve_battery_plan` and the app slider help. |
| M5 The 95 % interval assumes independent days, but daily savings have lag-1 autocorrelation 0.57. | **Fixed.** 7-day circular block bootstrap in code (`reports/backtest_ci_sensitivity.csv`): October CHF 129,685 to 354,460 (vs 158,868 to 306,077); shown next to the interval in the report, README, one-pager, slides and app. Test added. |
| M6 `--require-ml` could silently shorten a period if a day had no predictions. | **Fixed.** Every calendar day of the tuning, validation, test and rolling periods must have input data and six finite predictions per target, else the run stops naming the day and target (`check_ml_coverage`). Test added. |
| M7 Yahoo Finance (gas) and EEX data are for personal/educational and research use; derived series are tracked in git and the app plots gas. | **Kept, documented.** No files changed; "Before you publish" note in README and `app/README.md` (the repo is not pushed; the fix would be an HSG LSEG/Bloomberg export). |
| m1 "98 % of charge bids" is by volume. | **Fixed (text):** 98.31 % of the offered MWh, 87 of 91 hourly bids (95.60 %); the limit rule is restated with the wear deduction. |
| m2 "0.50 % of the month's purchase cost" – the denominator is the baseline's total cost incl. imbalance. | **Fixed (text).** |
| m3 Holiday numbers name the wrong cohort. | **Fixed (text):** 4.49 vs 52.54 MW = six public holidays outside 24 Dec – 2 Jan; all ten: 5.60 vs 48.32 MW; 6.60 MW = delivery two days after a holiday (report, one-pager, model notes). |
| m4 Driver statements: weather is the fourth group; lagged solar 0.013 MW; events "little incremental predictive value", single-seed differences within noise. | **Fixed (text)** in report, one-pager, slides, app, `reports/model_notes_demand.md` and its generator string. |
| m5 Gas "72 to 97" undated; "interconnectors were full" is a guess. | **Fixed (text):** dated 30 Sep → 26 Oct (first/last October close 73.94 / 103.94); "Swiss and German prices diverged" (report, `reports/model_notes_price.md` and generator). |
| m6 The CHF 475 slope is from the random-noise experiment with perfect demand; battery value per MWh is "nearly proportional". | **Fixed (text)** wherever the slope appears (report, one-pager, slides, app); CHF 1,134–1,138 per MWh, only the price-taker assumption as explanation. |
| m7 Forecast archive and availability wording. | **Fixed (text):** full ICON archive from January 2024, coarser JMA back to 2018; forecasts "available by 10:00 under the assumed release delays". |
| m8 App: "Imbalance cost" showed the penalty; the "what really happened" toggle did not hide all actuals; app README file list incomplete. | **Fixed.** Relabelled "Imbalance penalty" with the formula p ± 0.2·|p|, extra "Imbalance settlement" column; toggle renamed "Show actual values in the forecast charts" with help text; model notes added to the file list. |
| m9 p-values shown as 0.000; consent sentence too absolute; training "energy" was elapsed time; two bare figure names in the slide outline. | **Fixed (text).** "<0.001"; consent depends on purpose and legal basis; elapsed time, energy not measured; full figure paths. |
| Brief compliance: the leakage test replays from processed inputs, not raw downloads. | **Kept, documented** in report §4.4/§8 and the README. |
| Brief compliance: `--all` uses frozen parameters; experiments, tuning, report tables and the EDA notebook are separate commands. | **Fixed (docs):** listed in the README and report Appendix A. |
| Brief compliance: "run python with -I" breaks `python -m src...`. | **Kept, documented:** modules run without `-I` from the project folder (README, Appendix A). |

