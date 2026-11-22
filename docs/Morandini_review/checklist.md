# Morandini review: checklist

Merged list from the full review of the day-ahead planning project and the teammate review. Numbers come from the files in `reports/`.

| Verdict | Meaning |
|---|---|
| **DO** | cheap, clearly improves the project or the presentation |
| **DECLARE** | not worth fixing now; state it openly in the report and have an answer ready |
| **FUTURE** | goes into the recommendations section |

## Strengths to lead with

- **Leakage is tested, not just claimed.** Features only use data published by 10:00 on day D, and a test plants fake future values to prove it.
- **Strong baselines.** Naive rule, ML without battery, battery on a simple rule, and three perfect-foresight ceilings. The saving is split into "better demand forecast" and "battery".
- **Models clearly beat naive in every one of 13 out-of-sample months.** October: demand MAE 3.34 vs 9.58 MW, price 10.99 vs 23.47 EUR/MWh.
- **Real business problem.** Real ewz load, real Swiss prices, real 11:00 auction close, result in CHF.
- **Reproducible.** One pipeline command, a config file, frozen model settings, data checks, review log.

## Summary

| # | Point | Verdict | Effort |
|---|---|---|---|
| | **Presentation-critical** | | |
| 1 | No explicit research question | DO | 15 min |
| 2 | Imbalance price is assumed (±20 %) | DECLARE | none |
| 3 | Battery payback is missing | DO | 1–2 h |
| 4 | Results shown for October only | DO | about 1 h |
| 5 | Settings chosen looking at the rolling months | DECLARE | none, or 2–3 h (A) / up to one day (B) |
| 6 | Price forecast too low on average in October | DECLARE | none |
| 7 | AI policy and team ownership | DO | team time |
| | **Product and method** | | |
| 8 | Show forecast reliability next to the recommendation | DO | about 1 h |
| 9 | Demand uncertainty band too narrow | DO or DECLARE | about 1 h |
| 10 | Six 4-hour blocks instead of hours | DECLARE | none |
| 11 | Hourly model, 15-minute market | DECLARE + FUTURE | none |
| 12 | Automatic monthly retraining | FUTURE | none |
| 13 | Adaptive choice of settings | FUTURE | none |
| | **Before submitting** | | |
| 14 | Data licences (gas, CO₂) in a public repo | DO | team decision |
| 15 | Length and scope vs course limits | DO | depends |
| 16 | Repository clean-up | DO | about 1 h |

## Presentation-critical

### 1. Write the research question · DO

Neither the report nor the one-pager states an explicit research question; the early "Route A vs Route B" framing is gone. Write one sentence and put it on slide 1 and at the top of the report. A possible wording:

> How much can a Zurich DSO save on day-ahead purchases by forecasting tomorrow's demand and price with machine learning and planning a grid battery on top, compared with a simple rule?

### 2. The imbalance price is an assumption · DECLARE

When actual demand differs from what was bought, Swissgrid settles the difference. We had no real imbalance prices and assumed shortage = price +20 %, surplus = price −20 %.

- About **72 % of the 11-month saving** (CHF 1.57 M of 2.18 M) and **80 % of October** (CHF 181,033 of 226,499) is avoided penalty under this assumption.
- With ±10 % the October saving drops from CHF 226,499 to 135,998.
- The battery part (CHF 45,466 in October) does not depend on it.

Biggest uncertainty in the project. Keep it next to the headline number. Redo only if real Swissgrid imbalance prices can be obtained.

> Most of the saving is avoided imbalance penalty under an assumed ±20 % price; with real Swissgrid prices it could be larger or smaller. The battery saving does not depend on this assumption.

### 3. Add a battery payback slide · DO

The report says the investment is "outside this project" (`reports/report.md:816`), but in a business course it is the first question. The battery adds about CHF 45,000 in October and CHF 607,000 over the 11 rolling months, so roughly **CHF 0.7 M per year**.

- Take the investment cost of a 20 MW / 40 MWh grid battery from a cited source. The CHF 10–15 M in the teammate review is a guess and is not checked.
- Show a payback range. With these numbers it is likely long, close to the battery's lifetime.
- Say what is missing: the project only counts day-ahead arbitrage with at most one cycle a day. Real grid batteries earn much of their money from balancing services for Swissgrid, which are not modelled. CHF 0.7 M per year is a **lower bound**, not the full value.

> From the day-ahead market alone the battery earns about CHF 0.7 M a year, not enough to pay for itself. A real business case would add balancing services, which this project does not model.

### 4. Show results month by month, not only October · DO

The headline numbers come from October 2026 only. We already have 13 months each forecast without seeing the future (Oct 2025 – Oct 2026). Add one table, one row per month.

- Saving is **positive in all 13 months**, CHF 87,246 to 326,827; rolling average about CHF 198,000 per month.
- October is an easy month for demand (3.3 MW). Present the year-round figure: **about 4.65 MW, 1.5 %**, not 1.1 %.
- Price error 4–7 EUR/MWh in winter, 16–17 in April–May.
- The battery earns most in spring and summer (CHF 77,000–110,000 per month), little in winter (10,000–13,000).
- Quote the 11-month rolling total as **CHF 2.18 M**. The CHF 2.4 M figure is rolling plus September, the number used to tune the battery rules; do not quote it as a result.

### 5. Settings were chosen looking at the rolling months · DECLARE

Training month by month on past data only is correct, so the rolling forecasts are out-of-sample. The issue: the model settings (chosen with data up to Aug 2026 plus Sept 2026) and the battery rules (tuned on the rolling months plus September) were picked while looking at the months we report. Only October 2026 is fully clean.

- Estimated optimism: battery rules **under 1 %** (top variants differ by less than CHF 10,000 of 2.18 M); model settings about 1.5 %. Total roughly **1–3 %**. A rough estimate, not a measurement.
- The big choices are real: hourly plan vs block plan +CHF 117,000; predicting the change vs two days earlier cut the CV error from 6.41 to 4.61 MW.
- October confirms it: the tuned rules earned more there (about CHF 600 per day vs 350 in the rolling months).

If time allows: option A re-tunes only the battery rules on Oct 2024 – Sept 2025, then tests 13 clean months (2–3 h). Option B also redoes the model selection with data up to Sept 2025 (half to one day; results expected slightly worse).

### 6. Price forecast too low on average in October · DECLARE

In October the price forecast is on average 6.54 EUR/MWh too low, and every model errs the same way (naive −19.7, LightGBM −12.2). Prices rose during the month and a forecast anchored on today's price follows about one day late; spikes such as 29 October (451 EUR, forecast 319) are not caught. It is in the report; have the answer ready.

### 7. AI policy and team ownership · DO

`prompts/end_to_end_build_prompt.md` and `prompts/briefs/` show the project was built with Claude agents, and the ethics chapter says so. That is honest; check the course's AI policy before submitting.

The bigger risk is the exam: **every teammate must explain without notes** the battery optimiser (mixed-integer program, one charge-or-discharge switch per period), how the block plan becomes hourly bids, and how leakage is prevented and tested.

## Product and method

### 8. Show forecast reliability next to the recommendation · DO

- Demand: very reliable, about 1.5 % error all year.
- Cheapest and most expensive block: right about 85 days out of 100.
- Price level: 4–6 % error in winter, 16–20 % in spring.

Show it as information for the person deciding, not as an automatic rule. Being cautious automatically (protection bids, minimum price margins) lowered the saving from CHF 2.18 M to 2.10 M over 11 months.

### 9. Demand uncertainty band too narrow · DO or DECLARE

The 10–90 % band should contain the actual demand 80 % of the time; month by month it does so 68–81 % of the time. Widen it with a factor chosen on past data, as already done for price (factor 1.4). If there is no time, state it.

### 10. Six 4-hour blocks · DECLARE

Wording: we forecast **once a day at 10:00 for six 4-hour blocks**, not "every 4 hours". The Swiss auction runs once a day (closes 11:00) for all hours of the next day; our bids are hourly, using last week's hourly shape. Cost to state: with perfect foresight, block planning loses about CHF 27,000 in October against hourly planning.

### 11. Hourly model, 15-minute market · DECLARE + FUTURE

Swiss day-ahead prices are 15-minute from 4 November 2026 and Swissgrid settles imbalances per quarter hour. The test month is before the change, so the backtest is consistent; real use today needs a 15-minute version.

### 12. Automatic monthly retraining · FUTURE

In real use, retrain every month on all data up to the day before (the price model every 7 days), as the backtest already does. It only needs scheduling.

### 13. Adaptive choice of settings · FUTURE

Before each month, the system re-chooses its settings using only data from before that month, with the candidate list, comparison window and update frequency fixed in advance. Every month then becomes a clean out-of-sample test, and the system adapts to market changes such as the spring solar effect. Not done now: redoing the full settings search 13 times costs a lot of time and compute for an uncertain gain. A lighter version would re-tune only the battery rules each month.

## Before submitting

### 14. Data licences · DO

The repository is public and contains Yahoo Finance gas data (TTF=F, personal/educational use only) and EEX CO₂ auction data (research use). The app plots the gas series. Make the repository private or replace the gas series, for example with an HSG LSEG/Bloomberg export.

### 15. Length and scope · DO

A 1,008-line report, a PDF handover, a web app and a planning service. Check the course's page and length limits. A tight story beats volume: research question, method, monthly results, limitations, recommendation.

### 16. Repository clean-up · DO

- `.git` is 103 MB, with 34 MB of models and 40 MB of parquet files committed. Check any submission size limit.
- The web app uses bun (`web/bun.lock`). If someone ran `npm install` locally, do not commit `web/package-lock.json`; add it to `.gitignore`.

## Answer to have ready on stage

> The models were evaluated on 13 months without ever seeing the future and beat the naive forecast in every month. Only October 2026 is fully clean, because the other months were also used to choose settings; we estimate the resulting optimism at 1–3 %. The biggest uncertainty is the assumed imbalance price: most of the saving is avoided penalty under a ±20 % assumption. The battery saving does not depend on it, but from the day-ahead market alone it does not pay back the investment.
