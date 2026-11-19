# 12 Every review: the decision log

<div class="inshort" markdown="1">

After every phase a reviewer from another AI company (OpenAI GPT-6.2 Sol) checked the work with a fresh context and
read-only access, and was given the code, not the builders' conclusions. Every finding was either **fixed** or
**kept** and documented. The {{n:n_review_findings}} findings below are read directly from `docs/review_log.md`; the final review's original
wording and the orchestrator's instruction for each finding follow from `prompts/briefs/final_review_findings.md`.

</div>

## How to read the log

- **Fixed** = the code or the data changed. **Kept** = the behaviour stayed, with the reason and the size of the
  effect stated. **Documented / stated** = only the text changed (a caveat, a clearer label).
- The rows are numbered R01, R02 … in the order of `docs/review_log.md`, so they can be cited.
- Phases reviewed: data loaders, feature table, demand model, price model, optimiser + bids + backtest (twice: once
  with stand-in forecasts, once with the final numbers), and a final end-to-end review.

## The log

{{t:review_log}}

## The final review: original findings and instructions

The final reviewer (Q1) first rebuilt the project in a clean Python 3.11 environment with
`--all --skip-download` (12.6 minutes) and reproduced both metric files (maximum difference about 1e-14), both backtest
files byte for byte, all 154 tests (the number at the time), the leakage suite, the report tables and the notebooks.
Its findings, with the orchestrator's instruction to the fixing agent FX:

{{t:final_findings|Source: `prompts/briefs/final_review_findings.md`. M = major, m = minor.}}

<div class="note" markdown="1">

**Correction to the m8 quotation.** The quote swaps the two amounts. For the October product the file says: imbalance
**penalty** CHF {{n:s4_penalty_test}} (`imbalance_penalty_chf`) and net imbalance **settlement** CHF {{n:s4_imbcost_test}}
(`imbalance_cost_chf`), both in `reports/backtest_summary.csv`. The fix itself (relabelling the app) is unaffected.

</div>

## What the reviews changed, in effect

| Area | Before the review | After | Effect on the numbers |
|---|---|---|---|
| Demand refit cut-off | trained through 30 Sept | through 29 Sept | October MAE {{n:dem_old_oct_mae}} → {{n:dem_test_mae_best}} MW |
| Ceiling | block-rule perfect foresight (5) called the upper limit | one hourly plan over the period (6), cheapest in every evaluated period | "% of ceiling" = share of this benchmark |
| Solver | default optimality gap | exact (`mip_rel_gap = 0`) | plans are optimal |
| Tuning window | one day too many | ends {{n:tune_cutoff}} (enforced in code) | October never seen |
| Missing data | could be summed as 0 | the run stops naming the hour | – (none found) |
| Reservoir availability | Wednesday 18:00 | Thursday 23:59 | features one day later |
| EV join | by delivery day | by forecast day D | leakage-safe |
| Block-rule cost (M3) | one number | split into finer dispatch and inter-day | CHF {{n:finer_dispatch_part_chf_test}} + {{n:interday_flexibility_part_chf_test}} |
| Interval (M5) | independent days | plus a {{n:ci_blocklen}}-day block bootstrap | CHF {{n:ciblock_low_test}} to {{n:ciblock_high_test}} |
| Coverage (M6) | a missing day could shorten a period | `check_ml_coverage` stops the run | – |
| Temperature correction method (M1) | chosen with Sept + Oct weather | **not retrained**, disclosed | methods differ by about 0.001–0.01 °C |
