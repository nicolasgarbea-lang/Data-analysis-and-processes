# 4 Repository map

<div class="inshort" markdown="1">

The code is a plain Python package `src/` with one folder per step (data → features → models → optimisation →
decision → backtest → export), run in order by `src/pipeline.py`. Settings live in `config.yaml`. Results go to
`reports/`, trained models to `models/`, the web app's data to `web/public/data/`. A small FastAPI service in
`api/` lets the web app re-plan with another battery.

</div>

## Folders

| Folder / file | What it holds | Tracked in git? |
|---|---|---|
| `README.md` | install, run, results, licences | yes |
| `PITCH.md` | the pitch in plain words | yes |
| `day_ahead_planning.md` | the one-pager (v6) | yes |
| `config.yaml` | every setting: forecast time, periods, blocks, battery, bidding, imbalance, paths, seed | yes |
| `requirements.in` / `requirements.txt` | top-level packages / pinned versions | yes |
| `data/raw/` | downloads, one folder per source (cache) | no (`.gitignore`) |
| `data/manual/` | `events_zurich.csv`, the hand-made events table ({{n:n_events}} events on {{n:n_event_dates}} dates, one source URL each) | yes |
| `data/processed/` | clean tables (parquet, UTC), `features.parquet`, `hourly_actuals.parquet` | yes |
| `src/data/` | one loader per source, weather checks, target plots | yes |
| `src/features/` | the feature table and the model input lists | yes |
| `src/models/` | demand and price models, shared helpers | yes |
| `src/optimisation/` | the battery plan (mixed-integer program) | yes |
| `src/decision/` | from plan to hourly auction bids | yes |
| `src/backtest/` | settlement, strategies, tuning, sensitivities, notes | yes |
| `src/export/` | JSON files for the web app | yes |
| `src/pipeline.py` | runs every step | yes |
| `models/` | trained models (joblib) and their frozen settings (json) | yes |
| `reports/` | report, notes, metrics, predictions, backtest results, figures, data checks | yes |
| `notebooks/` | `01_eda`, `02_demand_model`, `03_price_model`, `04_backtest` | yes |
| `tests/` | pytest suite ({{n:n_test_files}} files, {{n:n_tests}} collected tests) | yes |
| `web/` | the web app (Bun + React + TanStack); `web/public/data/` is the exported JSON | yes (not `node_modules/`, `dist/`) |
| `api/` | `server.py`, the planning service for the web app | yes |
| `docs/` | sources, assumptions, data dictionary, auction timing, review log, TSO/DSO picture, this handover | yes |
| `prompts/` | the build prompt and the shared briefs given to agents | yes |

## Data flow

{{svg:dataflow|From the internet to the web app. Every arrow is one step of `src/pipeline.py` (data, features, models, backtest, metrics, export).}}

Read it left to right:

1. **Loaders** (`src/data/load_*.py`) download each source into `data/raw/<source>/` (cached; a re-run does not
   download again) and write one clean table per source to `data/processed/` (UTC timestamps, units in column names).
   Each loader also writes a short check file to `reports/data_checks/`.
2. **Features** (`src/features/build_features.py`) join everything into `data/processed/features.parquet`: one row
   per delivery day and block, with only values known at 10:00 on day D. It also writes
   `data/processed/hourly_actuals.parquet`, the real hourly prices and demand used to settle the backtest.
3. **Models** (`src/models/demand.py`, `src/models/price.py`) train the ladder and the best model, write
   `reports/predictions_<target>.parquet`, metrics, figures and notes, and save `models/*.joblib`.
4. **Backtest** (`src/backtest/run_backtest.py`) uses the optimiser and the bid builder for every day and strategy and
   settles with the actuals: `reports/backtest*.csv`, figures and `reports/backtest_notes.md`.
5. **Metrics** merge `metrics_demand.csv` + `metrics_price.csv` into `reports/metrics.csv` and the check files into
   `reports/data_checks.md`.
6. **Export** (`src/export/export_web.py`) writes the JSON files of the web app to `web/public/data/`.

## Which module depends on which

{{svg:dependencies|Import dependencies between the modules (from the import lines of each file). Everything reads its settings through `src/config.py`.}}

Rules that keep this simple:

- **Settings flow one way.** Every module reads `config.yaml` through `src/config.py` (`load_config()`, `path()`).
  Nothing writes the config.
- **Models never import the backtest, and the backtest never imports the models.** They meet through files:
  the models write `reports/predictions_*.parquet`; the backtest reads them. This is why a re-run of the backtest does
  not retrain anything.
- **The web app never imports Python.** It reads JSON files whose shapes are fixed in `web/src/data/types.ts`; only
  the "Try a battery" page calls the Python service `api/server.py`, which reuses `src/export/export_web.py`.
- `reports/make_report_tables.py` reads the result files and checks that every table in `reports/report.md` is
  current. This handover generator reuses it.

## What is stored where

**Clean tables in `data/processed/`** (all generated by the loaders and the feature builder):

{{t:processed_tables|Every processed table with its size, read from the parquet metadata.}}

**Raw downloads in `data/raw/`** (not in git, so a fresh clone has none; `python -m src.pipeline --data` fetches them again; chapter 16 shows what works without them):

{{t:raw_dirs|Raw folders on the build machine.}}

**Trained models in `models/`:**

{{t:models_files|`*_best.joblib` = the final model (one object with `predict(df)`); `*_ladder.joblib` = naive, linear, random forest and LightGBM; `*_best_params.json` = the frozen settings used by `--all`.}}

**Results in `reports/`:**

| File | Written by | Content |
|---|---|---|
| `reports/report.md` | R1 (tables by `make_report_tables.py`) | the graded report |
| `reports/model_notes_demand.md`, `reports/model_notes_price.md` | the model scripts | what was tried, what won, drivers, limitations |
| `reports/metrics_demand.csv`, `reports/metrics_price.csv`, `reports/metrics.csv` | model scripts, pipeline | MAE, RMSE, MAPE/sMAPE, bias, CI per model, split and block |
| `reports/model_tests_*.csv` | model scripts | Diebold–Mariano tests |
| `reports/predictions_*.parquet` | model scripts | every forecast (all ladder models, quantiles) |
| `reports/experiments_*.csv` | `--experiments` | the variant comparison |
| `reports/tuning_price.csv` | an earlier price `--tune` run (current code does not rewrite it) | the record of the price hyper-parameter search |
| `reports/importance_*.csv` | model scripts | permutation importance (single columns and groups) |
| `reports/decision_metrics_price.csv`, `reports/worst_blocks_price.csv` | price model | order-of-blocks metrics, worst misses |
| `reports/backtest.csv` | backtest | one row per day and strategy |
| `reports/backtest_summary.csv`, `reports/backtest_decomposition.csv` | backtest | totals per period and strategy; where the saving comes from |
| `reports/backtest_*sensitivity*.csv`, `reports/backtest_exceptions.csv` | backtest | battery size, price error, decision settings, block bootstrap, exception days |
| `reports/backtest_hourly_test.parquet` | backtest | hourly ledger of October |
| `reports/decision_tuning.csv` | backtest | every tuning candidate |
| `reports/backtest_notes.md` | backtest | plain-language notes (regenerated each run) |
| `reports/data_checks.md`, `reports/data_checks/` | loaders, pipeline | one check per processed table |
| `reports/figures/` | all steps | {{n:n_figures}} figures |
| `reports/Project_Handover_Report.pdf` | `docs/handover/build.py` | this document |
