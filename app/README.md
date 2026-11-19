# Streamlit app – day-ahead planning for Limmat Energie AG

Five tabs: **Tomorrow** (forecast, battery plan, bids for one delivery day), **Battery settings**
(sliders, live re-plan, whole-month re-run), **Month backtest** (strategy comparison in CHF),
**What drives demand and price** (importance, model ladder, data charts) and **Data and method**.

The app needs no internet. It reads only committed files at run time and never writes outside
Streamlit's own memory cache.

## Run locally

From the repo root, with the project venv:

```bash
.venv/bin/streamlit run app/streamlit_app.py
```

Then open http://localhost:8501. Tests: `.venv/bin/python -m pytest tests/test_app.py` (about 5 s).

## Deploy on Streamlit Community Cloud

1. Push the repo to GitHub with the files listed below. `data/raw/` is not needed.
2. On share.streamlit.io: **New app** → pick the repo and branch → **Main file path:
   `app/streamlit_app.py`**.
3. **Advanced settings → Python version: 3.11** (the version the project uses).
4. Requirements: Community Cloud looks for a dependency file next to the entrypoint first, so it
   installs the slim **`app/requirements.txt`** (streamlit, plotly, pandas, numpy, scipy, pyarrow,
   pyyaml, same versions as the venv). The full `requirements.txt` at the root is for the whole project
   (models, notebooks) and is not needed for the app.
5. `.streamlit/config.toml` is picked up from the repo root (no fixed theme, so the app follows the
   viewer's light or dark setting).

Start-up takes a few seconds (reading the feature table and the backtest files); the planning of one
day takes well under a second.

## Files the app reads

| File | Used for |
|---|---|
| `config.yaml` | blocks, auction times, battery defaults, imbalance factors, periods |
| `data/processed/features.parquet` | block actuals, naive forecasts, EUR/CHF, data charts (via `src.backtest.run_backtest.load_data`) |
| `data/processed/hourly_actuals.parquet` | hourly actual demand and price, settlement, daily profiles |
| `reports/predictions_demand.parquet`, `reports/predictions_price.parquet` | ML forecasts and 10–90 % bands |
| `reports/decision_tuning.csv` | the tuned decision rules (`tuned_decision()`) |
| `reports/backtest.csv`, `backtest_summary.csv`, `backtest_decomposition.csv`, `backtest_battery_sensitivity.csv`, `backtest_price_error_sensitivity.csv`, `backtest_decision_sensitivity.csv` | Month backtest tab; charge level carried into each day |
| `reports/metrics_{demand,price}.csv`, `reports/importance_{demand,price}.csv`, `reports/importance_groups_{demand,price}.csv` | Drivers tab |
| `docs/architecture_tso_dso.svg`, `docs/data_sources.md`, `docs/assumptions_*.md`, `docs/review_log.md` | Data and method tab |

`models/*.joblib` are not loaded by the app: the forecasts come from the prediction files written by
the model scripts (same numbers, much faster start-up).

## While the price model is missing

If `reports/predictions_price.parquet` does not exist, the app shows the notice *"Price model not
available yet – showing stand-in forecast"* (stand-in = the same block on the auction day). When the
file appears the notice disappears by itself (the app watches the file stamps and clears its caches).
If the price model exists but the backtest files were made before it, the Month backtest tab says so
until the backtest is re-run.
