# Final independent review (Q1) – findings and the orchestrator's decisions

Verified OK by the reviewer: clean Python 3.11 rebuild with `--all --skip-download` (12.6 min) reproduces both metric
CSVs (max abs diff ~1e-14) and both backtest CSVs byte-identically; pytest 154/154; leakage suite 5/5; table checker
20/20; all four notebooks execute; mermaid renders; 5 features recomputed by hand for 15 and 25 Oct match; the 25 Oct
settlement replay (25 hours) matches CHF 1,394,378.66; headline numbers reproduce; app starts, 4 app tests pass, all
app inputs are tracked in git.

## Major

M1. October influenced the choice of the temperature-correction METHOD. `docs/assumptions_weather.md:27` says the
    method (month-by-hour offsets vs one linear fit) was chosen using September AND October weather errors (the
    coefficients are fitted on data before September). On September alone the single linear correction wins by a hair
    (0.8929 °C vs 0.8942 °C for the shipped month-by-hour correction); with October included the order flips
    (0.9407 vs 0.9288). DECISION: do NOT retrain. Disclose precisely in report §8 (critical evaluation), in
    `docs/review_log.md` (correct the Phase 1 row that calls October "clean": coefficients are clean, the method choice
    saw October weather; difference between the two methods ~0.001–0.01 °C), in `docs/assumptions.md`, and soften
    "everything chosen before October" in report §1 to say: all model and decision choices were made before October;
    one weather pre-processing choice saw October weather data (not October demand or prices), see §8.
M2. Headline savings need the imbalance-price assumption NEXT to them everywhere. The assumed imbalance penalty explains
    CHF 181,033 of CHF 226,499 (~80%). With ±10% instead of ±20%: total CHF 135,998 = 90,517 demand + 45,481 battery
    (`reports/backtest_decision_sensitivity.csv`). Swissgrid moved to quarter-hourly single-price imbalance settlement
    in 2026, where a deviation can even help the system – so the assumed multipliers do not prove that demand
    forecasting is worth more than the battery under real settlement. Fix: put this caveat alongside the numbers in the
    README headline, the one-pager results, slide titles/notes, and the app's savings callout (Month backtest tab), and
    in the report summary box. Label CHF 2,382,678 as "sum over the rolling period (used for tuning the decision
    rules) plus September (validation) – not an out-of-sample test". Put the one-month scope and the fictional battery
    next to the October result.
M3. "4-hour blocks cost CHF 31,670" mixes two things: strategy 5 resets the battery level daily, strategy 6 (ceiling)
    can move energy between days. Reviewer's matched run: battery value CHF 28,305 (block rules, daily reset),
    CHF 55,307 (hourly, daily reset), CHF 59,975 (hourly, whole period). So ~CHF 27,002 is finer dispatch and ~CHF 4,668
    is inter-day flexibility. Fix: add the "hourly perfect foresight with daily reset" variant to the backtest outputs
    (an extra information strategy/row; do not change existing strategy numbers), add the two parts to
    `backtest_decomposition.csv` (new rows; keep the old `block_rule_cost_chf` row), regenerate, and update report,
    one-pager, slide 10 and the "forecast hourly" next-step recommendation with numbers from the regenerated files.
M4. Cycle definition. The optimiser caps discharge DELIVERED to the grid at 32 MWh/day and counts 32 MWh as one cycle;
    a full swing of the usable stored energy delivers only 30.36 MWh after discharge losses, so on 27 of 31 October days
    the battery does slightly more than one physical full cycle (30.8 grid-side cycles = 32.46 full equivalents of
    stored energy). Applying the physical cap would lower October battery savings by ~CHF 1,049. DECISION: keep the
    original brief's definition (Σ discharge ≤ soc_max − soc_min, taken from the brief) and state it clearly: "one
    cycle = 32 MWh delivered to the grid per day (the brief's definition); this is about 5% more than one physical
    full cycle; effect about CHF 1,000 per month" in report (methods + critical evaluation), `docs/assumptions.md`,
    `docs/assumptions_backtest.md`, the docstring of `solve_battery_plan` and the app slider help text.
M5. The 95% interval CHF 158,868–306,077 assumes independent days; October daily savings have lag-1 autocorrelation
    0.57; a 7-day block bootstrap gives roughly CHF 130,031–354,447. Fix: compute the block-bootstrap interval in code
    (add to `backtest_summary.csv` as extra columns or to a small CSV `reports/backtest_ci_sensitivity.csv`), state the
    independence assumption beside the interval and show the wider one.
M6. `--require-ml` can silently shorten the evaluation period (if predictions for a day are missing, the date filter
    drops the day). Fix: with `require_ml=True`, validate that every delivery date of the requested period has six
    finite predictions per target before tuning/settlement; raise an error naming the date and target. Add a test.
M7. Licensing before any PUBLIC push/deployment: Yahoo Finance data (gas) is for personal/educational use, EEX data for
    research use; processed series and feature columns derived from them are tracked in git and the app plots the gas
    series. DECISION: do not change files; add a clear "Before you publish" note to README and app/README.md (the repo
    is not pushed; the team must decide; the fix would be to replace gas with an HSG LSEG/Bloomberg export).

## Minor (all are text fixes; take each number from the files)

m1. Report ~l.579/674: "98% of charge bids" is by volume: 98.31% of offered MWh; by count 87 of 91 bids (95.60%). Say
    which. When restating the limit rule include the wear deduction.
m2. "0.50% of the month's purchase cost": the denominator is the baseline's TOTAL cost incl. imbalance
    (CHF 45,685,820); name it so.
m3. Holiday numbers: 4.49 vs 52.54 MW is for the six public holidays OUTSIDE 24 Dec–2 Jan; all ten public holidays
    give 5.60 vs 48.32 MW. The 6.60 MW result is for delivery two days after a holiday (`lag2d_was_holiday`). Name both
    cohorts correctly (report ~l.356, ~l.514; one-pager ~l.59).
m4. Driver statements: weather is the FOURTH demand input group (7.01 MW) behind lags, weekday/weekend and holidays;
    lagged solar importance is 0.0129 MW (not 0.03); "without events" improved the single-seed October MAE from 3.629
    to 3.472 – say "little incremental predictive value in this model", not a causal claim, and that single-seed
    differences are within noise (one-pager ~l.56, report ~l.516, slides ~l.14; also `reports/model_notes_demand.md`
    ~l.238 – fix the text in the notes file AND in the generator string in `src/models/demand.py` if it is there).
m5. Gas "~72 to ~97 EUR/MWh" is 30 Sep → 26 Oct; October's first and last trading closes were 73.94 and 103.94. Date
    the comparison. For 8 and 10 Oct say "Swiss and German prices diverged"; full interconnectors is a guess.
    (report ~l.413, ~l.778; `reports/model_notes_price.md` ~l.147 and its generator string in `src/models/price.py`).
m6. CHF 475 per 1 EUR/MWh is the fitted slope of the October random-noise experiment with PERFECT demand; the real ML
    forecast lost CHF 610 at 10.99 EUR/MWh under those rules. Add that qualifier wherever the slope appears (report
    ~l.40, one-pager ~l.94, slides ~l.18, app ~l.482). Battery size: CHF 1,134–1,138 per MWh of capacity for the tested
    two-hour systems – "nearly proportional", no causal explanation beyond the price-taker assumption.
m7. One-pager ~l.50, report ~l.749, app ~l.808: the full ICON forecast archive starts January 2024 (coarser JMA
    forecasts exist back to 2018); weather forecasts are those "available by 10:00 under the assumed release delays"
    (for most hours the run from the day before), not "issued on day D".
m8. App: tiles/table labelled "Imbalance cost" show the PENALTY (October product: penalty CHF 49,798 vs imbalance cost
    CHF 133,812 – check columns `imbalance_penalty_chf` vs `imbalance_cost_chf`); relabel correctly and show the
    formula p ± 0.2·|p|. The toggle "Show what really happened" still shows realised cost and hourly actuals when off:
    either hide all realised fields when off or rename the toggle to say it only affects the forecast charts. Add
    `reports/model_notes_*.md` to the file inventory in `app/README.md`.
m9. Report ~l.425/786, slides ~l.12: p-values shown as 0.000 → "<0.001". Qualify the smart-meter consent sentence
    (depends on purpose and legal basis). Report training effort as elapsed time (energy use was not measured). Slide
    outline has two bare figure filenames → `figures/demand_test_forecast_vs_actual.png`,
    `figures/price_permutation_importance.png`.

## Brief compliance notes
- The leakage test replays from PROCESSED inputs (truncation + poisoning), not from raw downloads: describe that scope
  honestly in report §5/§8 and README.
- `python -m src.pipeline --all` uses frozen model parameters; experiments (`--experiments`, `--tune`), report tables
  (`reports/make_report_tables.py --fill`) and the EDA notebook are separate commands: document them in README.
- The brief's "run python with -I" does not work with `python -m src...` (ModuleNotFoundError): say in README that
  modules are run without `-I` from the repo root.
