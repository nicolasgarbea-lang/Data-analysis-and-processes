# Demand model – notes (agent M1)

**Target:** `demand_mw` = mean MW of the Zurich city grid load (ewz) in each 4-hour block of the delivery day
(≈ 300 MW). **Forecast time:** day D 10:00, for all six blocks of D+1. The latest known demand is the full day
D−1, i.e. two days before delivery.

**Best model in one sentence:** LightGBM learns *how much higher or lower each block will be than the same block
two days earlier* (log ratio), five LightGBM runs with different seeds are averaged and blended 85 / 15 with a
ridge regression that learns the same ratio. Settings: `{"transform": "logratio", "reference_col": "demand_lag_2d_same_block", "weather": "hybrid", "extra_features": ["temp_vs_lag2", "rad_vs_lag2"], "drop_features": [], "gbm_params": {"learning_rate": 0.03, "n_estimators": 1500, "num_leaves": 31, "min_child_samples": 20, "subsample": 0.8, "subsample_freq": 1, "colsample_bytree": 0.7, "reg_lambda": 0.0}, "n_seeds": 5, "objective": "l2", "linear_weight": 0.15, "linear_alpha": 10.0, "half_life_years": null, "forecast_row_weight": 1.0, "covid_weight": 1.0, "walk_forward": false, "quantiles": [0.1, 0.5, 0.9], "quantile_params": {"learning_rate": 0.03, "n_estimators": 600, "num_leaves": 15, "min_child_samples": 40, "subsample": 0.8, "subsample_freq": 1, "colsample_bytree": 0.7}}`

## Validation (September 2026, models fit on data ≤ 30 Aug 2026)

| model   |   mae |   rmse |   mape_% |   bias |   mae_ci_low |   mae_ci_high |   skill_vs_naive_% |
|:--------|------:|-------:|---------:|-------:|-------------:|--------------:|-------------------:|
| naive   |  9.03 |  11.86 |     3.03 |   1.99 |         7.20 |         11.01 |               0.00 |
| linear  |  4.78 |   6.47 |     1.63 |   2.50 |         3.85 |          5.93 |              47.07 |
| rf      |  5.74 |   7.57 |     1.96 |   2.98 |         4.71 |          6.96 |              36.45 |
| gbm     |  3.80 |   4.81 |     1.32 |  -1.16 |         3.38 |          4.31 |              57.94 |
| best    |  3.24 |   4.32 |     1.09 |  -0.07 |         2.82 |          3.78 |              64.16 |


## Test (October 2026, refit on data ≤ 29 Sep 2026)

| model   |   mae |   rmse |   mape_% |   bias |   mae_ci_low |   mae_ci_high |   skill_vs_naive_% |
|:--------|------:|-------:|---------:|-------:|-------------:|--------------:|-------------------:|
| naive   |  9.58 |  13.50 |     3.13 |  -4.17 |         7.36 |         12.23 |               0.00 |
| linear  |  4.54 |   6.00 |     1.51 |   0.64 |         3.81 |          5.28 |              52.59 |
| rf      |  5.87 |   8.15 |     1.94 |  -1.69 |         4.92 |          7.03 |              38.70 |
| gbm     |  4.15 |   5.55 |     1.37 |   0.37 |         3.61 |          4.76 |              56.67 |
| best    |  3.34 |   4.65 |     1.11 |   0.55 |         2.88 |          3.91 |              65.18 |


95 % CI = day-clustered bootstrap (1000 draws of whole days).

### Test MAE per block (MW)

|   block |   best |   naive |
|--------:|-------:|--------:|
|       0 |   1.34 |    4.30 |
|       1 |   1.64 |    6.04 |
|       2 |   5.07 |   12.10 |
|       3 |   4.60 |   13.70 |
|       4 |   4.28 |   12.25 |
|       5 |   3.07 |    9.10 |


## Rolling-origin backtest (Oct 2025 – Aug 2026, monthly refit)

| model   |   mae |   rmse |   mape_% |   bias |   mae_ci_low |   mae_ci_high |   skill_vs_naive_% |
|:--------|------:|-------:|---------:|-------:|-------------:|--------------:|-------------------:|
| naive   | 15.05 |  22.92 |     4.96 |  -0.01 |          nan |           nan |               0.00 |
| linear  |  5.64 |   7.71 |     1.85 |   0.37 |          nan |           nan |              62.55 |
| rf      |  6.98 |   9.36 |     2.30 |  -0.02 |          nan |           nan |              53.62 |
| gbm     |  5.28 |   7.22 |     1.72 |   0.30 |          nan |           nan |              64.93 |
| best    |  4.65 |   6.45 |     1.51 |  -0.27 |          nan |           nan |              69.13 |


## Diebold–Mariano tests (daily mean absolute error; negative = best is better)

| split   | model_a   | model_b   |   mean_diff |   dm_stat |   p_value |   n_days |
|:--------|:----------|:----------|------------:|----------:|----------:|---------:|
| val     | best      | naive     |      -5.794 |    -4.768 |     0.000 |       30 |
| val     | best      | gbm       |      -0.562 |    -3.212 |     0.003 |       30 |
| test    | best      | naive     |      -6.245 |    -3.039 |     0.005 |       31 |
| test    | best      | gbm       |      -0.816 |    -2.314 |     0.028 |       31 |
| rolling | best      | naive     |     -10.408 |    -8.180 |     0.000 |      335 |
| rolling | best      | gbm       |      -0.633 |    -3.157 |     0.002 |      335 |


## Prediction band (quantile LightGBM 10 % / 90 %)

| split   |   inside_10_90 |   below_q10 |   above_q90 |   mean_width_mw |
|:--------|---------------:|------------:|------------:|----------------:|
| rolling |          0.729 |       0.133 |       0.138 |          19.443 |
| test    |          0.806 |       0.054 |       0.140 |          15.715 |
| val     |          0.778 |       0.161 |       0.061 |          15.900 |


## What was tried (September 2026 + 5-fold time-series CV on the training period)

Single LightGBM unless stated; `cv_mae` = mean over the 5 folds, `cv_mae_last2` = the two most recent folds (closest to the forecast era). Sensitivity rows also show October (reporting only, not used for choices).

| experiment                                       | kind         |   val_mae |   val_mape |   val_bias |   cv_mae |   cv_mae_last2 |   test_mae |   test_mape |
|:-------------------------------------------------|:-------------|----------:|-----------:|-----------:|---------:|---------------:|-----------:|------------:|
| A  LightGBM log-ratio vs 2-day lag (1 seed)      | variant      |     3.292 |      1.116 |     -0.239 |    4.606 |          4.613 |    nan     |     nan     |
| A0 LightGBM on the level                         | variant      |     3.848 |      1.338 |     -0.791 |    6.406 |          4.999 |    nan     |     nan     |
| A1 log-ratio vs 7-day lag                        | variant      |     3.898 |      1.363 |     -0.981 |    5.876 |          5.594 |    nan     |     nan     |
| A2 difference vs 2-day lag                       | variant      |     3.422 |      1.170 |     -0.348 |    4.593 |          4.629 |    nan     |     nan     |
| A3 difference vs 4-week same-weekday mean        | variant      |     3.947 |      1.409 |     -1.276 |    6.738 |          5.603 |    nan     |     nan     |
| B1 L1 loss                                       | variant      |     3.313 |      1.129 |     -0.329 |    4.883 |          4.948 |    nan     |     nan     |
| B2 Huber loss                                    | variant      |     3.187 |      1.082 |     -0.975 |    4.784 |          4.720 |    nan     |     nan     |
| C1 recency half-life 1 y                         | variant      |     4.064 |      1.400 |     -0.246 |    4.759 |          4.831 |    nan     |     nan     |
| C2 recency half-life 2 y                         | variant      |     3.450 |      1.169 |      0.082 |    4.664 |          4.687 |    nan     |     nan     |
| C3 recency half-life 3 y                         | variant      |     3.384 |      1.145 |      0.303 |    4.639 |          4.649 |    nan     |     nan     |
| C4 COVID lockdown weight 0.1                     | variant      |     3.385 |      1.143 |     -0.033 |    5.375 |          4.737 |    nan     |     nan     |
| D1 weather: forecast-era rows weight 2           | weather      |     3.390 |      1.145 |     -0.033 |    4.620 |          4.647 |    nan     |     nan     |
| D2 weather: JMA forecasts for all years          | weather      |     3.819 |      1.295 |     -0.276 |    4.980 |          4.834 |    nan     |     nan     |
| D3 weather: ICON hybrid + JMA columns            | weather      |     3.435 |      1.177 |     -0.966 |    4.638 |          4.592 |    nan     |     nan     |
| D4 ORACLE weather (observed, NOT achievable)     | weather      |     3.011 |      1.032 |     -0.185 |    4.258 |          3.752 |    nan     |     nan     |
| E1 no extra features (temp/radiation vs lag day) | variant      |     3.370 |      1.142 |     -0.263 |    4.631 |          4.599 |    nan     |     nan     |
| F1 5 seeds                                       | ensemble     |     3.243 |      1.095 |     -0.273 |  nan     |        nan     |    nan     |     nan     |
| F2 5 seeds + ridge 15 %                          | ensemble     |     3.202 |      1.078 |      0.081 |  nan     |        nan     |    nan     |     nan     |
| F3 5 seeds + ridge 30 %                          | ensemble     |     3.220 |      1.082 |      0.434 |  nan     |        nan     |    nan     |     nan     |
| G0 1 seed + ridge, fit once                      | walk-forward |     3.245 |      1.097 |      0.110 |  nan     |        nan     |    nan     |     nan     |
| G1 1 seed + ridge, daily walk-forward refit      | walk-forward |     3.178 |      1.072 |      0.379 |  nan     |        nan     |    nan     |     nan     |
| S0 sensitivity base (1 seed, all features)       | sensitivity  |     3.292 |      1.116 |     -0.239 |  nan     |        nan     |      3.629 |       1.202 |
| S1 demand one day later (no D−1 demand)          | sensitivity  |     3.933 |      1.357 |     -1.720 |  nan     |        nan     |      4.698 |       1.522 |
| S2 without EV features                           | sensitivity  |     3.156 |      1.058 |      0.064 |  nan     |        nan     |      3.529 |       1.168 |
| S3 without event/football features               | sensitivity  |     3.263 |      1.103 |     -0.107 |  nan     |        nan     |      3.472 |       1.151 |
| S4 without weather                               | sensitivity  |     7.411 |      2.481 |      4.989 |  nan     |        nan     |      6.494 |       2.124 |
| S5 without solar (lagged Swiss solar)            | sensitivity  |     3.255 |      1.111 |     -0.540 |  nan     |        nan     |      3.544 |       1.174 |


## Why this model won (decided on September 2026 + CV, before looking at October)
* **Target transform is the big step.** LightGBM on the demand level: CV MAE 6.41 MW, September 3.85. The same
  LightGBM predicting log(demand / same block two days earlier): CV 4.61, September 3.29. Trees cannot extrapolate
  a level, but "a bit higher or lower than the last known day" they predict well. The 2-day reference beats the
  7-day reference (CV 5.88) and the 4-week same-weekday mean (CV 6.74) because it carries the most recent level
  (school holidays, weather spells). A plain difference instead of the log ratio was equal in CV (4.59) but worse on
  September (3.42).
* **Loss:** L1 and Huber were not better in CV (4.88 / 4.78 vs 4.61); Huber looked good on September alone
  (3.19) but we trusted the 5 CV folds more than one month - kept squared error (L2).
* **Weighting:** recency weighting (half-life 1–3 years) and down-weighting the COVID lockdown made CV equal or
  worse - all history is used with equal weight; `covid_stringency` stays an input.
* **Weather source:** the ICON/observed hybrid won. JMA forecasts for all years were clearly worse (Sept 3.82, CV
  4.98) - JMA has no solar radiation, and radiation is the most useful weather input. ICON hybrid + JMA together:
  CV of the last two folds slightly better (4.59 vs 4.61) but September worse (3.44) - not adopted. Giving
  forecast-era rows double weight changed nothing. The ORACLE run with observed weather of the delivery day (NOT
  achievable in practice) reaches 3.01 on September and 3.75 in the last two CV folds: the error of the weather
  forecast costs about 0.3 MW (≈ 9 %) on September and ≈ 0.9 MW in the recent CV folds.
* **Extra features:** forecast minus observed temperature / radiation of the reference day helped a little
  (September 3.37 → 3.29). Ratio versions of all lags (each lag ÷ 2-day lag) and a holiday-"cleaned" reference
  (7-day lag when the 2-day lag day was a holiday) made CV worse and were dropped.
* **Ensemble:** averaging 5 LightGBM seeds (3.29 → 3.24) and blending with 15 % ridge regression on the same log
  ratio (→ 3.20) helped; 30 % ridge was slightly worse (3.22). One-seed LightGBM results move by about ±0.1 MW
  between seeds, so smaller differences on September are noise.
* **Daily walk-forward refit:** on September 3.245 → 3.178 MW (1 seed + ridge). This gain is smaller than the seed
  noise and makes `main()` about 30× slower for the test month, so the model is fit once (≤ 29 Sep) for October.
* **Hyper-parameters:** an optuna search (TimeSeriesSplit 5 folds on the training period, 16 trials) did not
  beat the starting values (learning rate 0.03, 1500 trees, 31 leaves; CV 4.615 vs best other 4.628), so those
  were kept. Ladder ridge/RF/LightGBM settings were set with small CV grids.
* **Per-block models** were not tried separately: `block` is the 2nd most important input of the pooled model
  and the pooled model already gets the per-block shape from `demand_dm1_block_*`.
* **Linear model:** ridge with one-hot block × weekday-type, block × month, per-block slopes for temperature,
  heating/cooling degrees, radiation and the main lags. Trending inputs (EV counts, charging power, year,
  COVID index) were left out: a straight line through them gave absurd forecasts in early CV folds
  (CV 20 → 5.1 MW without them). Missing early values (charging data before Dec 2020, 364-day lag in 2019) are
  filled with the training median plus a "was missing" flag.

### Error on special days (rolling Oct 2025–Aug 2026 + October 2026, MAE in MW)
| day type | rows | naive | gbm (level) | best | best bias |
|---|---|---|---|---|---|
| normal day | 1548 | 13.68 | 5.18 | 4.55 | −0.41 |
| school holiday | 492 | 12.12 | 4.93 | 4.00 | +0.69 |
| public holiday (the six outside 24 Dec–2 Jan) | 36 | 52.54 | 5.12 | 4.49 | +2.11 |
| delivery two days after a holiday (T−2 was a holiday, misleading reference) | 48 | 22.21 | 6.01 | 6.60 | −3.69 |
| Christmas period | 60 | 27.96 | 6.13 | 6.59 | −1.68 |
| bridge day | 6 | 8.47 | 5.50 | 5.34 | −0.06 |
| half holiday (e.g. Sechseläuten, Knabenschiessen) | 6 | 36.67 | 10.45 | 7.72 | +7.59 |

The best model handles holidays themselves well, but on delivery days two days *after* a holiday (when the
reference day T−2 was a holiday) and around Christmas it is slightly worse than the level LightGBM and forecasts too low. Blending in
the level model on such days is the obvious next improvement (not done, to keep the October test untouched).



## Driver importance

Permutation importance on Sept + Oct 2026 (MAE increase in MW when a column, or a whole group of columns, is shuffled).

### Groups

| feature                               |   mae_increase |   std |
|:--------------------------------------|---------------:|------:|
| past demand (all lags)                |         47.168 | 1.372 |
| weekday / weekend                     |         12.329 | 1.149 |
| holidays and school holidays          |          9.461 | 0.940 |
| weather (forecast + past observed)    |          7.010 | 0.498 |
| season (month, day of year, daylight) |          0.148 | 0.026 |
| Swiss solar (lagged)                  |          0.013 | 0.013 |
| EVs and charging                      |          0.002 | 0.001 |
| COVID stringency                      |          0.000 | 0.000 |
| events and football                   |         -0.012 | 0.003 |


### Top 20 single columns

| feature                                |   mae_increase |   std |
|:---------------------------------------|---------------:|------:|
| demand_lag_2d_same_block               |         42.507 | 1.619 |
| block                                  |          9.408 | 0.961 |
| is_working_day                         |          8.929 | 0.399 |
| weekday                                |          8.596 | 0.411 |
| radiation_wm2                          |          5.825 | 0.439 |
| demand_dm1_block_2                     |          4.672 | 0.456 |
| radiation_obs_same_block_lag_2d        |          4.058 | 0.146 |
| lag2d_is_weekend                       |          1.734 | 0.190 |
| demand_mean_same_block_same_weekday_4w |          1.100 | 0.027 |
| heating_degree                         |          0.471 | 0.063 |
| temp_change_fc_vs_dm1                  |          0.470 | 0.060 |
| temp_c                                 |          0.441 | 0.047 |
| temp_obs_same_block_lag_2d             |          0.436 | 0.043 |
| temp_c_sq                              |          0.246 | 0.019 |
| temp_obs_mean_last_3d                  |          0.239 | 0.055 |
| demand_day_min_lag_2d                  |          0.179 | 0.028 |
| demand_lag_8d_same_block               |          0.179 | 0.070 |
| humidity_pct                           |          0.155 | 0.014 |
| temp_obs_mean_last_7d                  |          0.148 | 0.008 |
| demand_lag_7d_same_block               |          0.146 | 0.044 |


## Top-10 drivers (single columns, permutation importance on Sept + Oct 2026)
1. **`demand_lag_2d_same_block`** – demand of the same block on the last known day (D−1); it is the reference the
   model scales, so shuffling it destroys the forecast.
2. **`block`** – time of day: the ratio to the reference day differs between night, office hours and evening.
3. **`is_working_day`** – whether delivery day is a working day (not weekend, not public holiday); offices and
   businesses drive the daytime load.
4. **`weekday`** – Monday vs Friday vs weekend; together with the reference day's weekday it tells how big the
   jump from the reference day is.
5. **`radiation_wm2`** – forecast solar radiation of the block; sunshine lowers the grid load in daytime blocks
   (rooftop solar behind the meter, less lighting).
6. **`demand_dm1_block_2`** – yesterday's 08–12 block: a clean measure of the most recent working-day level.
7. **`radiation_obs_same_block_lag_2d`** – how sunny the reference day was: a sunny reference day had lower load,
   so the model corrects upwards if tomorrow is cloudy (and vice versa).
8. **`lag2d_is_weekend`** – the reference day was a weekend day, so the ratio to a working day is large.
9. **`demand_mean_same_block_same_weekday_4w`** – typical level of this block on this weekday in the last 4 weeks;
   an anchor that is not affected by a single odd day.
10. **`heating_degree`** – how far the forecast temperature is below 15 °C; electric heating and heat pumps raise
    the load on cold days (small in October, more important in winter).

### The driver groups asked for in the brief
* **EVs:** the EV and charging columns add nothing measurable (group importance ≈ 0.00 MW; without them the
  single-LightGBM MAE was even slightly lower, 3.29 → 3.16 in Sept, 3.63 → 3.53 in Oct). They grow smoothly over
  years, and that slow trend is already in the recent demand lags.
* **Weather:** the fourth most important input group, after past demand, weekday/weekend and holidays (shuffling
  all weather columns adds 7.0 MW of MAE; without weather inputs the single LightGBM goes from 3.29 to 7.41 MW in September). Solar
  radiation matters most, temperature less in this mild season.
* **Solar:** the lagged Swiss solar production (Energy-Charts) adds almost nothing (0.013 MW); the solar effect on
  city load is captured through the radiation forecast for the delivery day.
* **Holidays:** essential - the holiday/school-holiday group adds 9.5 MW of MAE when shuffled. On public holidays
  outside 24 Dec–2 Jan (six days) the model's error is 4.5 MW against 52.5 MW for the naive forecast (all ten public
  holidays: 5.6 vs 48.3 MW); the weak spot is delivery two days after a holiday (6.6 MW).
* **Events:** big events and FC Zürich / GC home games add little incremental predictive value in this model
  (importance ≤ 0; without them the single-seed October MAE was 3.47 instead of 3.63 MW, a difference within the
  seed noise). This is not a causal statement about events and load.
* **Data delay:** if demand of D−1 were not yet available (only D−2), the MAE would rise from 3.29 to 3.93 MW in
  September and from 3.63 to 4.70 MW in October (single LightGBM).



## Limitations
* **Weather in training:** before 2024-01-21 the weather inputs are observed values (no forecast archive); only
  the last ~2.7 years use real ICON forecasts. The model therefore may trust the weather a little too much. The
  test months use real forecasts, so the reported test errors are honest.
* **Short test months:** one month = 30–31 days, so the 95 % CI of the test MAE is about ±0.5 MW. The DM test of
  best vs plain LightGBM is significant on September, on October (p ≈ 0.03) and in the 11-month rolling
  backtest.
* **Prediction band:** the 10–90 % band contains 73–78 % of the actuals instead of 80 % - slightly too narrow.
* **Refit dates:** the validation and test models are fit on data up to 30 Aug / 29 Sep, the last day whose
  demand is known when the first forecast of the month is made. (An earlier version used 31 Aug / 30 Sep; an
  independent review flagged it. The fix moved the October error from 3.36 to 3.34 MW.)
* **Days after holidays, Christmas and half-holidays** are the weakest cases (see table above).
* **Importance:** permutation importance splits the credit between related columns (e.g. `weekday`,
  `is_working_day`, `is_weekend`), so single numbers should be read together with the group table.



_`main()` runtime of this run: 8.3 min._
