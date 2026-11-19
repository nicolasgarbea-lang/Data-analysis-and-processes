# Day-ahead planning for a Zurich DSO

University group project (HSG, *Business Analytics & Data Science Applications*, HS 2026).

**Limmat Energie AG** is a fictional distribution system operator (DSO) that supplies the city of Zurich (its demand
is the real ewz grid load of the city) and owns a fictional 20 MW / 40 MWh grid battery. Every day at 10:00, one hour
before the Swiss day-ahead auction closes, the project

1. forecasts Zurich demand and the Swiss day-ahead price for the six 4-hour blocks of tomorrow,
2. plans the battery with a small mixed-integer optimisation model,
3. turns the plan into hourly auction bids, and
4. in the backtest, settles the bids with the actual prices and demand (imbalance included), in CHF.

Test month October 2026: demand MAE 3.34 MW, price MAE 10.99 EUR/MWh, CHF 226,499 saved against a naive rule without
battery (CHF 181,033 from the better demand forecast, CHF 45,466 from the battery).

- One-pager: [`day_ahead_planning.md`](day_ahead_planning.md)
- Full report: [`reports/report.md`](reports/report.md) · slide outline: [`reports/slide_outline.md`](reports/slide_outline.md)

## Folder layout

```
README.md                  this file
day_ahead_planning.md      one-pager
config.yaml                forecast time, periods, battery, bidding, imbalance factors, paths
requirements.txt           pinned versions (requirements.in = top-level packages)
data/raw/                  downloads (not committed)
data/manual/               events_zurich.csv (hand-made, one source URL per row)
data/processed/            clean tables (parquet), features.parquet, hourly_actuals.parquet
src/data/                  one loader per source (load_<source>.py), weather checks, target plots
src/features/              feature table + feature lists
src/models/                demand.py, price.py, common code
src/optimisation/          battery_lp.py – battery plan (mixed-integer program, SciPy/HiGHS)
src/decision/              bids.py – block plan → hourly auction bids
src/backtest/              run_backtest.py, analysis.py – settlement, strategies, tuning, sensitivities
src/pipeline.py            runs everything
notebooks/                 01_eda, 02_demand_model, 03_price_model, 04_backtest
models/                    trained models (joblib) and their settings (json)
app/                       Streamlit app (see app/README.md)
tests/                     pytest suite (loaders, leakage, optimiser, bids, backtest, app)
reports/                   report, metrics, predictions, backtest results, figures/, notes per step
docs/                      data sources, assumptions, data dictionary, auction timing, review log, TSO/DSO picture
```

## Install

Python **3.11**. On macOS, LightGBM needs OpenMP first: `brew install libomp`.

With pip:

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

With uv:

```bash
uv venv --python 3.11 .venv
uv pip install --python .venv -r requirements.txt
```

(On Windows use `.venv\Scripts\python` instead of `.venv/bin/python`.)

## Run

All commands from the project folder.

```bash
.venv/bin/python -m src.pipeline --all                  # download, features, models, backtest, metrics
.venv/bin/python -m src.pipeline --all --skip-download  # same, from the files already in data/raw/ (no internet)
```

Single steps (combine as needed): `--data`, `--features`, `--models`, `--backtest`, `--metrics`, e.g.

```bash
.venv/bin/python -m src.pipeline --features --models
.venv/bin/python -m src.models.demand        # demand model only
.venv/bin/python -m src.models.price         # price model only
.venv/bin/python -m src.backtest.run_backtest --require-ml
```

Tests (154 tests):

```bash
.venv/bin/python -m pytest
```

App:

```bash
.venv/bin/streamlit run app/streamlit_app.py      # then open http://localhost:8501
```

Report tables (check that every table in the report matches the result files):

```bash
.venv/bin/python reports/make_report_tables.py --check reports/report.md
```

### Expected run times (laptop)

| Step | Time |
|---|---|
| Demand model (`src.models.demand`) | 8.3 min in the last run (`reports/model_notes_demand.md`) |
| Price model (`src.models.price`) | 4.7 min in the last run (`reports/model_notes_price.md`) |
| Downloads (`--data`) | not timed; the APIs are called with pauses to respect rate limits (Energy-Charts, Open-Meteo), so allow well over an hour on a first run |
| Features, backtest | not timed in the result files; the backtest prints its own duration |
| App start | a few seconds; planning one day takes well under a second |

## Deploy the app on Streamlit Community Cloud

Push the repo to GitHub (without `data/raw/`), then on share.streamlit.io create a new app with main file
`app/streamlit_app.py` and Python 3.11. The app installs the slim `app/requirements.txt`. Step-by-step instructions
and the list of files the app needs: [`app/README.md`](app/README.md).

## Where the results are

| What | File |
|---|---|
| Report, one-pager, slides | `reports/report.md`, `day_ahead_planning.md`, `reports/slide_outline.md` |
| Model metrics (all models, per block, per period) | `reports/metrics.csv` (= `metrics_demand.csv` + `metrics_price.csv`) |
| Model notes (choices, experiments, drivers) | `reports/model_notes_demand.md`, `reports/model_notes_price.md` |
| Forecasts | `reports/predictions_demand.parquet`, `reports/predictions_price.parquet` |
| Backtest per day and strategy | `reports/backtest.csv` |
| Backtest summary, decomposition, sensitivities | `reports/backtest_summary.csv`, `backtest_decomposition.csv`, `backtest_*sensitivity*.csv`, `reports/backtest_notes.md` |
| Data checks | `reports/data_checks.md` |
| Figures | `reports/figures/` |
| Assumptions, data dictionary, sources | `docs/assumptions.md`, `docs/data_dictionary.md`, `docs/data_sources.md` |
| Independent reviews | `docs/review_log.md`, report Appendix B |

## Data licences and attribution

| Source | Licence / terms |
|---|---|
| Energy-Charts (Fraunhofer ISE): prices, Swiss power, forecasts | CC BY 4.0 – "Data: Energy-Charts.info" |
| Stadt Zürich open data: ewz grid load, ewz Netzebenen, car stock, school holidays | Open Government Data of the City of Zurich (open use with attribution) |
| MeteoSwiss open data (station Zürich-Fluntern) | Open data of the Federal Office of Meteorology and Climatology MeteoSwiss, attribution required |
| Open-Meteo (previous-runs forecasts, ERA5 archive) | CC BY 4.0 – "Weather data by Open-Meteo.com"; underlying models DWD ICON, ECMWF, JMA, Copernicus ERA5 |
| BFE (Swiss Federal Office of Energy): reservoir levels, EV charging stations | opendata.swiss, open use with source attribution |
| ECB EUR/CHF reference rates | ECB data, free reuse with source attribution |
| EEX EUA primary-auction results | EEX public auction reports, used for research only |
| Yahoo Finance `TTF=F` (gas) | **unofficial** fallback, personal/educational use only |
| OxCGRT COVID stringency index | Oxford COVID-19 Government Response Tracker, CC BY 4.0 |
| football-data.co.uk Swiss Super League results | free for personal/research use |
| `holidays` Python package | MIT licence |

Raw downloads are not committed; `python -m src.pipeline --data` fetches them again.
