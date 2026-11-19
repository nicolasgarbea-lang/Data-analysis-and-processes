# Review of the handover PDF – findings to fix (all confirmed by the orchestrator)

The reviewer verified: headline numbers, bootstrap intervals, 115 TOC entries, 655 links, offline rebuild (103 pages,
identical text). Fix every item below in `docs/handover/` sources/generator, then rebuild.

## Major
1. Fresh-checkout instructions (ch. 16, pp. 19–20, 82–83): `--all --skip-download` fails without `data/raw/` (git-ignored;
   ewz loader raises `ValueError: No objects to concatenate`); the PDF build also fails with FileNotFoundError when
   `data/raw/` is missing (build.py ~l.638). macOS block pairs `uv venv` with `.venv/bin/pip`, which a uv venv does not
   have. Fix: give three clearly separated paths – (a) use the committed processed data / results only (no pipeline
   data step: features, models, backtest, export can run from `data/processed/`; verify which steps really work without
   data/raw and say so), (b) rebuild from a supplied raw snapshot (`--skip-download`), (c) first full download
   (`--all`, needs internet). Use `uv pip install --python .venv/bin/python -r requirements.txt` on the uv path. Make
   build.py print "raw cache unavailable" and continue when `data/raw/` is missing.
2. Runbook understates what changes when data or timing changes (pp. 16–18, 83, 89–91): changing `auction` times needs
   the weather loaders re-run (forecast run selection depends on the issue time); extending `periods` alone does not
   extend the feature table (date bounds in `src/features/build_features.py` ~l.32), Open-Meteo downloads (end dates in
   the loaders), or the model rolling windows (`src/models/price.py` ~l.373 and demand equivalent); cached chunks are
   reused unless `--force`. Add a "Refreshing with new data / a new test month" procedure listing every place to change,
   which loaders to force, coverage checks, re-exporting the web JSON, restarting the API (it caches inputs). Label the
   current runbook as a replay of the shipped evaluation window.
3. January 2026 is not an independent second test (pp. 15, 71, 86, 89): `test2_*` keys only define a mask; January is
   inside the rolling evaluation and the decision tuning; moving `test_start` to January without moving the training
   cut-offs would put January in training. Relabel January as a winter slice of the rolling replay; for a second
   independent test describe a NEW untouched window with settings and rules frozen before it and cut-offs set
   accordingly.
4. Battery 50 % target presented as an invariant (pp. 9, 44, 68, 90): optimiser default end = start, separate end target
   accepted; backtest starts each split at the configured level, carries the ACTUAL settled level forward, plans back to
   the configured target, and relaxes the target to the day's opening level only if infeasible (example: October
   product ended 8 Oct at 9.082 MWh and started 9 Oct there – verify in `reports/backtest.csv`). Update the formulation
   (ch. 9), decision D45, the `soc_start_frac` config row; include the `1e-4 × charge` tie-breaker in the shown objective.
5. Ceiling described as a mathematical bound (pp. 7, 48, 59, 65, 87, 101): strategy 6 minimises EUR with matched
   opening/closing stock while the comparison is in CHF with an inventory adjustment (review found CHF 653 gap). Replace
   "no strategy can be cheaper" / "as it must be" with "strategy 6 was the cheapest in every evaluated period"; describe
   60.43 % and 75.81 % as shares of that named benchmark and state its objective and inventory convention.
6. Experiment command can overwrite frozen settings (pp. 40, 68, 83): `--experiments --tune` runs tuning first, writes
   `models/*_best_params.json`, then regenerates results; the CLI does not encode the historical decision to keep the
   shipped settings. Tell the reader to run it only in a copy, list which files it replaces, and give the separate
   command that reproduces the shipped models (`python -m src.models.demand` / `price` with no flags). For price, say
   Optuna's objective is MAE over the two most recent CV folds (verify in `src/models/price.py` ~l.557).
7. Publication caveat (pp. 15, 85–86): the repo IS public on GitHub (README says so now; app not deployed). State the
   current status, list the affected tracked and exported artifacts (processed gas/CO₂ parquet, features.parquet,
   web/public/data/drivers.json, models), say a replacement feed needs verified redistribution rights, and that a
   rebuild changes current files while earlier git revisions still contain the old data.

## Minor
- Ch. 12: the historical m8 quotation swaps settlement and penalty – keep the quote but add a correction (product
  October: net imbalance settlement CHF 49,798, penalty CHF 133,812 – read from `reports/backtest_summary.csv`). The
  Markdown table parser in build.py (~l.100) splits row R42 at the pipes in `|p|` – escape or parse properly so the full
  decision text appears.
- Ch. 10 bid/settlement branches missing: charge with no later discharge uses all discharge that day for the limit;
  a pure refill uses the day's max forecast price directly (no factor, wear deduction or q90 cap); stage-2 tuning tests
  q90 caps with both 0.9 and 1.0; undelivered discharge can reduce an existing surplus before creating shortage; the
  hourly shape looks back at most eight weeks to find seven matching day types. Verify each in `src/decision/bids.py`,
  `src/backtest/analysis.py` (~l.86), `src/backtest/run_backtest.py` (~l.437, ~l.546) and describe.
- Data/feature descriptions: demand target is mean MW, price mean EUR/MWh (fix any "MWh" mislabels); the availability
  guard allows delivery-day valid times for weather forecasts (vintage checked separately) and calendar features
  describe the delivery day – describe the rule per feature family; D10 should point to `delivery_weather_features`
  (fallback implemented there), D08 to `solar_and_ev_features`; CH 15-min switch = 3 Nov 2026 23:00 UTC / 4 Nov 00:00
  Zurich (state both, reconcile chronology and data chapter); events file has 183 rows on 182 dates.
- Results/Appendix E: monthly refit applies to the rolling price run; September/October best price model uses 7-day
  refits. Figure 28 caption says "each strategy" but omits 5b – fix caption. Appendix E: cite the decomposition CSV for
  `total_saving_chf` (or use the summary's `saving_vs_baseline_adj_chf`). Ch. 14: qualify "October is clean" with the
  temperature-method exception consistently.
- Web chapter: Python tests check JSON against hand-mirrored Pydantic models, the browser just casts JSON to TS types –
  they can drift; say both must be updated together. The inventory shows zero fields for `PlanRequest`/`MonthRequest`
  (regex misses inline interfaces, build.py ~l.544) – fix. Daily API scales the stored morning charge share; month API
  starts at the configured share and carries its own settlement forward – document both.
- Housekeeping list (pp. 82, 84, 86) contains already-done items: README test count 172, four routes, API docstring,
  PuLP removed, handover packages – remove them (check current files). Note: `markdown`, `playwright`, `pypdf` are in
  requirements.in; make sure they are pinned in requirements.txt (`uv pip freeze`), and that pulp/plotly are gone.
- Layout: page 46 has only two optimiser-test rows, page 70 one decision row – keep short table tails with the
  preceding table (or rebalance). The Results screenshot split across pages cuts the sensitivity charts – crop
  screenshots at section boundaries.
