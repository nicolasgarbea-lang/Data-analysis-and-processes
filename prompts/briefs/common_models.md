# Common brief for the modelling agents (Phase 3)

Repo root: `/Users/lorik/Documents/Business analytics Group Project` (macOS; venv `.venv/bin/python`, Python 3.11,
scikit-learn, lightgbm, optuna, statsmodels installed; add packages with `uv pip install --python .venv/bin/python X`
and append to `requirements.in`). Work yourself, no subagents. Do NOT run git. Do not edit `config.yaml`,
`src/data/*`, `src/features/*`, `src/optimisation/*`, `src/decision/*`, `src/backtest/*` or other agents' files.

Read first: `prompts/end_to_end_build_prompt.md` (§1–3 and Phase 3), `config.yaml`, `src/features/feature_sets.py`,
`docs/data_dictionary_features.md`, `docs/assumptions_features.md`, `reports/data_checks/features.md`.

## Data
`data/processed/features.parquet`: one row per (delivery_date, block 0..5), 2019-01-15 → 2026-11-01. Forecast is made on
day D (= delivery_date − 1) at 10:00 local. All columns in `DEMAND_FEATURES` / `PRICE_FEATURES` are leakage-safe
(tested). NEVER use `*_obs`, `actual_*`, `unverified_*` or the other target's same-row value as inputs (except in a
clearly labelled "oracle" sensitivity run). Weather columns are a hybrid: observed before 2024-01-21, real ICON forecast
after (`weather_is_forecast`). The feature table can be rebuilt with `.venv/bin/python -m src.features.build_features`
(it may gain `eu_*` columns later — always take the feature list from `feature_sets.py` at run time, don't hard-code).

## Protocol (do not deviate — the test month is touched ONCE)
- Train: delivery dates ≤ 2026-08-31. Validation: September 2026. Test: October 2026 (31 days × 6 blocks = 186 rows).
- Tune hyper-parameters with `TimeSeriesSplit(n_splits=5)` on the training period (GridSearchCV / small manual grid /
  optuna with a modest budget). Choose model family, feature subset, target transform, weighting, ensembling etc. using
  September 2026 ONLY (and the CV). Do all exploration without looking at October. When everything is frozen, refit the
  chosen configuration on train+validation (≤ 2026-09-30) and evaluate ONCE on October. Do not go back and change
  anything after seeing October numbers (report them as they are, even if a simpler model wins in October).
- Required ladder, all evaluated the same way: `naive` (same block 7 days earlier = `*_lag_7d_same_block`),
  `linear` (scaled linear regression; ridge allowed), `rf` (random forest), `gbm` (gradient boosting, LightGBM),
  plus `best` = whatever wins on validation (may be an ensemble or an enhanced variant).
- Walk-forward is allowed and encouraged if it wins on September: for the test month the model may be refit each day
  with all rows whose delivery_date ≤ D−1 for demand targets / ≤ D for price targets (i.e. only actuals already known at
  forecast time). Be careful: when forecasting delivery day T, the latest usable demand TARGET row is T−2 and the latest
  price TARGET row is T−1.
- Extra robustness evidence (not the headline): a rolling-origin backtest with the frozen configuration over
  2025-10-01 → 2026-08-31, refit at the start of each month on all earlier data (split = "rolling"). Also the optional
  winter test month January 2026 comes out of this for free.
- Metrics per model, per split and per block + overall: MAE, RMSE, MAPE (demand), sMAPE (price), bias; skill vs naive.
  Add day-clustered bootstrap 95% CIs (resample whole days, 1000 draws) for MAE of each model on the test month, and a
  Diebold–Mariano-style test on daily mean absolute errors: best vs naive and best vs gbm.

## Outputs (exact contract — other modules depend on it)
- `src/models/<target>.py` with `train(...)`, `evaluate(...)`, `main()` CLI (`.venv/bin/python -m src.models.<target>`)
  that reproduces everything deterministically (seed from config) in a reasonable time (aim < 10 min for `main()` using
  the frozen hyper-parameters stored in `models/<target>_best_params.json`; the expensive search goes behind a
  `--tune` flag).
- `models/<target>_best.joblib`: one object with a method `predict(df) -> np.ndarray` that takes rows of
  features.parquet (it selects its own columns) — define the wrapper class in `src/models/common.py` so `joblib.load`
  works from the Streamlit app (`import src.models.common`). Keep the file < 20 MB. Also save
  `models/<target>_ladder.joblib` (dict name → fitted model for naive/linear/rf/gbm) if < 30 MB total (shrink the RF:
  limited depth / n_estimators) — else skip RF from the saved ladder.
- `reports/predictions_<target>.parquet`: columns `delivery_date, block, split` ("rolling" | "val" | "test"), `y_true`,
  `pred_naive`, `pred_linear`, `pred_rf`, `pred_gbm`, `pred_best`, and (if you build quantile models)
  `pred_q10, pred_q50, pred_q90`. "val" predictions come from the model fit on train only; "test" from the refit ≤ Sep 30
  (or walk-forward); "rolling" as described.
- `reports/metrics_<target>.csv` (long format: `target, split, model, block` ("all" or 0..5), `mae, rmse, mape_or_smape,
  bias, n, mae_ci_low, mae_ci_high`) and `reports/model_tests_<target>.csv` (DM tests).
- Figures in `reports/figures/`: `<target>_test_forecast_vs_actual.png` (186 points, best + naive vs actual),
  `<target>_error_by_block.png`, `<target>_permutation_importance.png` (permutation importance of the best model on the
  validation+test months, top 20) and `reports/importance_<target>.csv`; `<target>_model_ladder.png` (MAE bars per split).
- `reports/model_notes_<target>.md`: plain-language summary — what was tried, what won on validation and why, final
  test table, top-10 drivers with ONE sentence each, limitations. Simple language, no unexplained jargon.
- `tests/test_models_<target>.py`: fast tests (saved model loads and predicts finite values on October rows; predictions
  file has 186 test rows, no NaN; the feature list of the saved model contains no forbidden columns; metrics file agrees
  with a recomputation from the predictions file).
- `notebooks/0X_<target>_model.ipynb`: a short, executed notebook that loads the outputs and shows the key tables and
  plots (it must run top to bottom; generate it with nbformat + nbconvert --execute). Keep it light.

Code must stay readable for students: plain functions, docstrings in simple English, no clever abstractions.

Final message: validation and test tables (MAE/RMSE/MAPE or sMAPE per model, overall), what `best` is, CI and DM results,
top drivers, runtime of `main()`, surprises and limitations.
