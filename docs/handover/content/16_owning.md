# 16 Owning the project

<div class="inshort" markdown="1">

Install Python 3.11 and the pinned packages. A fresh clone has no raw downloads (`data/raw/` is not in git), so pick
one of three paths: work from the committed processed data and results, rebuild from a raw snapshot someone hands you,
or download everything again. This chapter lists every command, what to re-run after which change, how to move the
project to new data or a new test month, the errors you are likely to meet, the data licences, and what to check
before anything is made public.

</div>

## Install

**macOS**

```bash
brew install libomp                      # LightGBM needs OpenMP on macOS
python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt
# or with uv (a uv venv has no pip of its own):
uv venv --python 3.11 .venv && uv pip install --python .venv/bin/python -r requirements.txt
# web app (optional): install Bun from https://bun.sh, then
cd web && bun install
```

**Windows** (the build prompt assumed Windows; the build itself ran on macOS)

```bat
py -3.11 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

Use `.venv\Scripts\python` wherever this report writes `.venv/bin/python`. LightGBM wheels for Windows include OpenMP.
The `api` script in `web/package.json` calls `.venv/bin/python`; on Windows run the API by hand
(`.venv\Scripts\python -m uvicorn api.server:app --port 8000`) and the web app with `bun run dev`.

**This handover report** needs `markdown`, `playwright` and `pypdf` (pinned in `requirements.txt`) and a Chromium
browser for Playwright (`.venv/bin/python -m playwright install chromium`).

**Always run from the project folder, and without `python -I`** (it stops `python -m src…` from finding the package).

## Three ways to start

| Path | When | Commands | What works |
|---|---|---|---|
| **(a) Committed data only** (fresh clone, no `data/raw/`) | you want to re-run models, backtest, app or this PDF | `.venv/bin/python -m src.pipeline --features --models --backtest --export` (any subset) | everything from `data/processed/` onwards. **Not** `--data` and **not** `--all` (with or without `--skip-download`): the first loader stops with `ValueError: No objects to concatenate` because its raw files are missing |
| **(b) Raw snapshot** | someone gives you a copy of the build machine's `data/raw/` (not in git) | put it at `data/raw/`, then `.venv/bin/python -m src.pipeline --all --skip-download` | the full rebuild without internet, 12.6–13.2 min in the two clean rebuilds |
| **(c) First full download** | no snapshot, internet available | `.venv/bin/python -m src.pipeline --all` | downloads not timed: allow well over an hour (rate limits); sources may have revised or removed old values, so numbers can move slightly |

Path (a) was tested on a copy of the project without `data/raw/`, `.git` and `.venv`: `--features` rebuilt a feature
table identical to the committed one, `--backtest` reproduced `reports/backtest_summary.csv` and
`reports/backtest_decomposition.csv` exactly, `--export` wrote the same app files (only the time stamp in `meta.json`
differs), `--models` ran through, and this PDF builds (the raw-folder table in chapter 4 then says "raw cache
unavailable").

## Every command

| Command | What it does | Time (build machine) |
|---|---|---|
| `… -m src.pipeline --all [--skip-download]` | data, features, models, backtest, metrics, export | see "Three ways to start" |
| `… -m src.pipeline --data` / `--features` / `--models` / `--backtest` / `--metrics` / `--export` | single steps (combine as needed; `--data` needs `data/raw/` or internet) | – |
| `.venv/bin/python -m src.data.load_<source> [--skip-download] [--force]` | one loader (`--force` downloads cached chunks again) | – |
| `.venv/bin/python -m src.models.demand` | demand model with the **frozen** settings in `models/demand_best_params.json` | {{n:rt_demand}} min (last run) |
| `.venv/bin/python -m src.models.price` | price model with the frozen settings | {{n:rt_price}} min (last run) |
| `.venv/bin/python -m src.backtest.run_backtest --require-ml` | backtest, tuning, sensitivities, notes | prints its own duration |
| `.venv/bin/python -m src.export.export_web` | JSON for the web app | – |
| `.venv/bin/python -m pytest` | all tests ({{n:n_tests}} collected) | a few minutes |
| `.venv/bin/python reports/make_report_tables.py --check reports/report.md` | do the report tables match the result files? (`--fill` rewrites them) | seconds |
| `.venv/bin/jupyter nbconvert --to notebook --execute --inplace notebooks/01_eda.ipynb` | re-run a notebook | – |
| `cd web && bun run start` | API + web app, http://localhost:5173 | seconds |
| `cd web && bun run build` | static site in `web/dist/` | – |
| `.venv/bin/python docs/handover/build.py` | rebuild this PDF | under a minute |

`--all` and the two model commands without flags use the frozen settings; they reproduce the shipped models.

<div class="caveat" markdown="1">

**`--experiments --tune` overwrites the shipped settings – run it only in a copy of the project.**
`python -m src.models.demand --experiments --tune` (same for price) first runs the hyper-parameter search and writes
its winner into `models/<target>_best_params.json`, then redoes the variant comparison
(`reports/experiments_<target>.csv`), and then retrains with the **new** settings, replacing the models, predictions,
metrics, tests, importance, figures and notes of that target. The CLI does not know that the search's winners were
**rejected** (chapters 7 and 8, D37): the demand search scores the mean MAE of all five CV folds, the price search the
mean MAE of the **two most recent** folds, and the shipped settings were kept because they did better on September. To
get the shipped models back, restore the two params files and run the two model commands without flags.
`reports/tuning_price.csv` is a record of the earlier price search and is not rewritten by current code.

</div>

## What to re-run after changing X

The commands above **replay the shipped evaluation window** (rolling Oct 2025 – Aug 2026, September and October
2026). For new data or a different test month see the next section.

| You changed … | Re-run | Then check |
|---|---|---|
| a loader or a raw file | that loader → `--features --models --backtest --metrics --export` | `tests/test_loaders_*.py`, `reports/data_checks.md` |
| `config.yaml` `auction.forecast_time_local` | the two weather-forecast loaders (`load_openmeteo_forecast`, `load_openmeteo_europe`; the run chosen per hour depends on this time, both leads are cached), then everything from `--features` | leakage tests; a loader stops if even the older run is not published in time |
| `config.yaml` `periods` | see the next section – dates are also fixed in code | **the test month must stay untouched** |
| `config.yaml` `battery`, `bidding` or `imbalance` | `--backtest --export` (models unchanged) | `reports/backtest_notes.md` |
| a feature in `build_features.py` or `feature_sets.py` | `--features --models --backtest --metrics --export` | `tests/test_no_leakage.py`, `tests/test_features.py` |
| model settings (`models/*_best_params.json`) | `--models --backtest --metrics --export` | only with September/CV evidence, never October |
| the optimiser or `bids.py` | `--backtest --export` | `tests/test_battery_lp.py`, `tests/test_bids.py`, `tests/test_backtest.py` |
| the export or `types.ts` | `--export`, `bun run build`, restart the API | `tests/test_export_web.py` |
| any result | `reports/make_report_tables.py --fill reports/report.md`, update the one-pager and README by hand, rebuild this PDF | `--check` |

## Refreshing with new data or a new test month

Changing `periods` alone is **not** enough: several end dates are written in the code. To evaluate a new month
(e.g. November 2026) or to extend the data:

1. **Decide the windows first** and freeze them before looking at any result of the new month: `raw_end`,
   `train_end`, `val_start/end`, `test_start/end`, `rolling_start` in `config.yaml`. The training cut-offs move with
   them, so the new test month can never be in training.
2. **Move the end dates in the code:** `END_DATE` in `src/data/load_openmeteo_forecast.py` (also used by
   `src/data/load_openmeteo_europe.py`) and `src/data/load_openmeteo_archive.py`; the year loops
   `range(…, 2027)` in those three loaders; `PERIOD2` in `src/data/load_gas.py`; `DAILY_END` in
   `src/data/_utils_calendar.py` (calendar, EVs, events); the school-holiday dates per year in
   `src/data/load_calendar.py`; new events in `data/manual/events_zurich.csv`; `LAST_DELIVERY` in
   `src/features/build_features.py`; the `rolling_backtest(start=…, end=…)` defaults in `src/models/demand.py` and
   `src/models/price.py` (they are called without arguments, so they must match `rolling_start`/`train_end`).
   Titles and notes that say "October 2026" are text only, but should be updated.
3. **Download the new days.** Loaders reuse every cached chunk in `data/raw/<source>/`; the chunk that covers the new
   days (e.g. the 2026 year file of each Open-Meteo loader) must be fetched again with
   `python -m src.data.load_<source> --force`, or the new days stay missing.
4. **Check coverage** before modelling: `reports/data_checks.md` (gaps, last date per source), the last delivery date
   and `weather_is_forecast` share in `reports/data_checks/features.md`. The backtest with `--require-ml` stops if any day lacks
   predictions (`check_ml_coverage`).
5. **Re-run** `--features --models --backtest --metrics --export`. The decision-tuning cut-off moves with
   `test_start` by itself (two days before it).
6. **Restart the planning API** (it caches the backtest inputs in memory), rebuild the web app, rebuild this PDF.

A second **independent** test (for example a winter month) needs exactly this: a window that has not been used for
any choice, with model settings and decision rules frozen before it and the cut-offs set accordingly. January 2026
does not qualify; it is inside the rolling run and the decision tuning (chapter 17, step 7).

## How to extend the project

**Add a data source.** Write `src/data/load_<source>.py` with `main(skip_download=False)` and a CLI
(`--skip-download`, `--force`), cache downloads in `data/raw/<source>/`, write `data/processed/<name>.parquet` with a
tz-aware UTC `timestamp_utc` (or a local `date`) and units in the column names, write a check file to
`reports/data_checks/`, add it to `DATA_STEPS` in `src/pipeline.py`, add tests, and document the **publication time** in
the data dictionary and assumptions. The publication time decides whether the source can be used at all.

**Add a feature.** Add a table to `TABLE_FILES` and an availability cut-off in `build_features.py`, compute the
feature as a statistic over a window that ends before the cut-off, add it to a list in `feature_sets.py`, add the cut
rule to the independent rules in `tests/test_no_leakage.py`, and run the leakage tests.

**Add or change a model.** Follow the protocol in `prompts/briefs/common_models.md`: choose on September + CV only, add
the variant to `experiments()` so it is recorded in `reports/experiments_<target>.csv`, keep the output contract
(`reports/predictions_<target>.parquet` with `pred_best`), and keep `models/<target>_best.joblib` loadable via
`src.models.common`.

**Add a strategy.** Add it to `run_backtest.py` (a forecast source + decision parameters), to the summary order in
`analysis.py` and to `STRAT_ORDER` in `reports/make_report_tables.py`; if the app should show it, to the export.
Remember inventory adjustment and the bootstrap.

**Real imbalance prices.** Replace the factor formula in `settle_hours` with a lookup of Swissgrid prices per
quarter-hour; keep the factors as a sensitivity.

## Common errors and fixes

| Symptom | Cause | Fix |
|---|---|---|
| `ValueError: No objects to concatenate` in `load_ewz_demand` | `--data` or `--all` without `data/raw/` | path (a), (b) or (c) above |
| `OSError` loading LightGBM on macOS | OpenMP missing | `brew install libomp` |
| `ModuleNotFoundError: src` | run with `python -I`, or not from the project folder | run `python -m src…` from the project folder, without `-I` |
| HTTP 429 from Energy-Charts / Open-Meteo | rate limits | loaders retry with back-off; re-run later; cached chunks are not fetched again |
| HTTP 429 from Yahoo | Yahoo blocks plain requests | `curl_cffi` is used; if it still fails, use an official gas export |
| HTTP 504 / timeouts from Open-Meteo previous-runs | service down | retry later (the loader retries with long pauses) |
| `ValueError` naming an hour in the backtest | a missing or non-finite price, demand or exchange rate | fix the input data; never fill with 0 |
| error naming a day and target with `--require-ml` | predictions missing for a day | re-run the model step |
| model tests fail on a fresh clone | they need the model outputs | run `python -m src.models.demand` / `price` once |
| "planning service not running" on the battery page | API not started | `bun run start` or `bun run api` |
| the battery page shows old numbers after a re-run | the API caches its inputs | restart the API |
| web app not reachable on `localhost` | IPv4/IPv6 | the dev server listens on both since commit `78c5b51`; try http://127.0.0.1:5173 |

## Data licences

| Source | Licence / terms |
|---|---|
| Energy-Charts (Fraunhofer ISE) | CC BY 4.0 – "Data: Energy-Charts.info" |
| Stadt Zürich open data (ewz load, Netzebenen, car stock, school holidays) | open government data, attribution |
| MeteoSwiss open data | open data, attribution required |
| Open-Meteo (previous runs, ERA5) | CC BY 4.0 – "Weather data by Open-Meteo.com" |
| BFE (reservoirs, charging stations) | opendata.swiss, attribution |
| ECB EUR/CHF | free reuse with attribution |
| EEX EUA auction results | **research use** |
| Yahoo Finance `TTF=F` | **unofficial, personal/educational use only** |
| OxCGRT COVID index | CC BY 4.0 |
| football-data.co.uk | personal/research use |
| `holidays` package | MIT |
| Archivo font (web app, this PDF) | SIL Open Font License (`docs/handover/fonts/LICENSE-Archivo.txt`) |

## Before you publish

- **Status today.** The repository is **public on GitHub**; the web app is **not deployed**.
- **Licensed data is already in it.** Tracked files contain or derive from the Yahoo gas and EEX CO₂ series:
  `data/processed/gas_ttf_daily.parquet`, `data/processed/co2_eua_daily.parquet`, `data/processed/features.parquet`,
  the trained price models in `models/`, and the exported app file `web/public/data/drivers.json` (the gas series
  the app plots). The team must decide: make the repository private, or replace gas (and if needed CO₂) with a feed
  whose **redistribution rights are verified** (e.g. an HSG LSEG/Bloomberg export, if its terms allow publishing) and
  rebuild. A rebuild only changes the current files; **earlier git revisions still contain the old data**, so removing
  it from a public repository needs a history rewrite or a fresh repository.
- **Caveats travel with numbers.** Any slide, post or page with the CHF saving must carry the assumed-penalty caveat
  and the interval.
- **Fictional company.** Keep the "fictional DSO, real data, simulated money" line on every public page.
- **AI use.** State how the project was built (chapter 3).
