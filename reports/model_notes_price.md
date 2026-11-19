# Price model – notes (agent M2)

**Target:** `price_eur_mwh` = mean Swiss day-ahead price (EPEX CH) of each 4-hour block of the delivery day,
EUR/MWh. Prices can be near zero or negative, so the percentage error is the symmetric MAPE (sMAPE), not MAPE.
**Forecast time:** day D 10:00, for the six blocks of D+1. All CH and neighbour prices of day D are known (the
auction for D ran on D−1); no price of D+1 is known.

**Best model in one sentence:** we start from a price we already know – *the mean CH price of day D plus the
usual difference of this block from the day mean over the last 7 days* (`ref_shape7`) – and LightGBM learns how
much tomorrow's block will differ from it; recent days count more (weight halves every year), three LightGBM
seeds are averaged and blended 65 / 35 with a LEAR-style ridge regression that learns the same change, and the
model is refit every 7 days during the month with all prices known at that time. A quantile LightGBM (10/50/90 %)
gives a band, widened by a factor 1.4 chosen on September so that ~80 % of actual prices fall inside it.

Settings: `{"transform": "diff", "reference_col": "ref_shape7", "asinh_scale": 50.0, "weather": "hybrid", "drop_features": "EU_ICON", "add_features": [], "use_extras": true, "gbm_params": {"learning_rate": 0.03, "n_estimators": 1000, "num_leaves": 31, "min_child_samples": 20, "subsample": 0.8, "subsample_freq": 1, "colsample_bytree": 0.5, "reg_lambda": 0.0}, "n_seeds": 3, "objective": "l2", "huber_alpha": 20.0, "half_life_years": 1.0, "start_date": null, "linear_weight": 0.35, "linear_alpha": 30.0, "linear_windows_years": [null], "walk_forward": true, "refit_every_days": 7, "quantiles": [0.1, 0.5, 0.9], "band_factor": 1.4, "quantile_params": {"learning_rate": 0.03, "n_estimators": 600, "num_leaves": 15, "min_child_samples": 40, "subsample": 0.8, "subsample_freq": 1, "colsample_bytree": 0.5}}`

(`drop_features: "EU_ICON"` = the ICON-based European weather columns `eu_*_safe` are left out, see "What was tried".)

## Validation (September 2026, models fit on data ≤ 31 Aug 2026)

| model   |   mae |   rmse |   smape_% |   bias |   mae_ci_low |   mae_ci_high |   skill_vs_naive_% |
|:--------|------:|-------:|----------:|-------:|-------------:|--------------:|-------------------:|
| naive   | 23.54 |  29.83 |     20.97 |  -7.60 |        19.29 |         28.36 |               0.00 |
| linear  | 15.16 |  21.32 |     14.74 |   2.14 |        12.88 |         17.57 |              35.61 |
| rf      | 19.01 |  26.09 |     16.98 |  -1.82 |        16.27 |         21.63 |              19.26 |
| gbm     | 16.23 |  21.97 |     15.16 |  -1.00 |        13.70 |         18.63 |              31.07 |
| best    | 13.62 |  17.98 |     13.58 |  -1.44 |        11.49 |         15.74 |              42.14 |


Decision metrics (September):

| model   |   rank_corr |   hit_cheapest |   hit_dearest |   shape_mae |   daymean_mae |   n_days |
|:--------|------------:|---------------:|--------------:|------------:|--------------:|---------:|
| naive   |       0.893 |          0.933 |         0.900 |      12.642 |        19.635 |       30 |
| linear  |       0.914 |          0.933 |         0.933 |      11.156 |        12.563 |       30 |
| rf      |       0.893 |          0.933 |         0.833 |      14.495 |        14.729 |       30 |
| gbm     |       0.918 |          0.900 |         0.867 |      11.439 |        12.363 |       30 |
| best    |       0.933 |          0.933 |         0.967 |       8.485 |        11.709 |       30 |


## Test (October 2026, refit on data ≤ 30 Sep 2026, evaluated once)

| model   |   mae |   rmse |   smape_% |   bias |   mae_ci_low |   mae_ci_high |   skill_vs_naive_% |
|:--------|------:|-------:|----------:|-------:|-------------:|--------------:|-------------------:|
| naive   | 23.47 |  33.80 |     12.89 | -19.71 |        18.36 |         29.46 |               0.00 |
| linear  | 12.77 |  18.79 |      6.34 |  -7.22 |        10.57 |         15.14 |              45.59 |
| rf      | 16.73 |  23.03 |      7.99 | -11.73 |        14.08 |         19.85 |              28.70 |
| gbm     | 16.82 |  21.86 |      8.08 | -12.15 |        14.15 |         19.83 |              28.30 |
| best    | 10.99 |  16.46 |      5.28 |  -6.54 |         9.02 |         13.18 |              53.16 |


95 % CI = day-clustered bootstrap (1000 draws of whole days).


Decision metrics (October):

| model   |   rank_corr |   hit_cheapest |   hit_dearest |   shape_mae |   daymean_mae |   n_days |
|:--------|------------:|---------------:|--------------:|------------:|--------------:|---------:|
| naive   |       0.771 |          0.645 |         0.742 |      14.091 |        20.503 |       31 |
| linear  |       0.891 |          0.774 |         0.839 |       8.768 |        10.704 |       31 |
| rf      |       0.827 |          0.742 |         0.806 |      10.045 |        13.840 |       31 |
| gbm     |       0.878 |          0.839 |         0.839 |       8.501 |        15.288 |       31 |
| best    |       0.889 |          0.839 |         0.871 |       7.370 |         8.956 |       31 |


`rank_corr` = Spearman correlation of the 6 block prices inside a day (1 = perfect order),
`hit_cheapest` / `hit_dearest` = share of days where the model picks the right cheapest / most expensive block
(this is what the battery plan needs), `shape_mae` = MAE of (block − day mean), `daymean_mae` = MAE of the daily
mean price (the level, used by the limit bids).


### Test MAE per block (EUR/MWh)

|   block |   best |   gbm |   naive |
|--------:|-------:|------:|--------:|
|       0 |   8.93 | 14.52 |   14.47 |
|       1 |   9.28 | 14.96 |   16.43 |
|       2 |  10.13 | 15.21 |   26.17 |
|       3 |  15.43 | 21.69 |   36.43 |
|       4 |  15.30 | 22.73 |   30.41 |
|       5 |   6.88 | 11.83 |   16.88 |


## Rolling-origin backtest (Oct 2025 – Aug 2026, monthly refit)

| model   |   mae |   rmse |   smape_% |   bias |   mae_ci_low |   mae_ci_high |   skill_vs_naive_% |
|:--------|------:|-------:|----------:|-------:|-------------:|--------------:|-------------------:|
| naive   | 21.24 |  34.39 |     25.50 |  -0.76 |          nan |           nan |               0.00 |
| linear  | 12.26 |  18.79 |     16.47 |   1.96 |          nan |           nan |              42.26 |
| rf      | 12.12 |  20.48 |     16.26 |  -0.57 |          nan |           nan |              42.91 |
| gbm     | 10.17 |  16.79 |     14.43 |   0.32 |          nan |           nan |              52.12 |
| best    |  9.88 |  16.23 |     14.29 |   0.00 |          nan |           nan |              53.49 |


| model   |   rank_corr |   hit_cheapest |   hit_dearest |   shape_mae |   daymean_mae |   n_days |
|:--------|------------:|---------------:|--------------:|------------:|--------------:|---------:|
| naive   |       0.850 |          0.836 |         0.833 |      13.322 |        18.437 |      335 |
| linear  |       0.891 |          0.875 |         0.854 |       8.510 |         9.431 |      335 |
| rf      |       0.890 |          0.887 |         0.872 |       8.786 |         9.671 |      335 |
| gbm     |       0.915 |          0.896 |         0.875 |       7.325 |         8.007 |      335 |
| best    |       0.914 |          0.884 |         0.866 |       7.364 |         7.583 |      335 |


## Diebold–Mariano tests (daily mean absolute error; negative = best is better)

| split   | model_a   | model_b   |   mean_diff |   dm_stat |   p_value |   n_days |
|:--------|:----------|:----------|------------:|----------:|----------:|---------:|
| val     | best      | naive     |      -9.918 |    -3.520 |     0.001 |       30 |
| val     | best      | gbm       |      -2.606 |    -3.658 |     0.001 |       30 |
| test    | best      | naive     |     -12.474 |    -4.229 |     0.000 |       31 |
| test    | best      | gbm       |      -5.832 |    -4.488 |     0.000 |       31 |
| rolling | best      | naive     |     -11.359 |    -8.427 |     0.000 |      335 |
| rolling | best      | gbm       |      -0.290 |    -0.988 |     0.324 |      335 |


## Prediction band (quantile LightGBM 10 % / 90 %)

| split   |   inside_10_90 |   below_q10 |   above_q90 |   mean_width_eur |
|:--------|---------------:|------------:|------------:|-----------------:|
| rolling |          0.784 |       0.101 |       0.115 |           40.147 |
| test    |          0.866 |       0.022 |       0.113 |           50.385 |
| val     |          0.806 |       0.100 |       0.094 |           59.447 |


## The 10 worst test blocks (largest |error| of the best model)

| delivery_date   | block     |   y_true |   pred_best |   error |   pred_naive |   price_lag_1d_same_block |   pred_q10 |   pred_q90 | what_happened                                                                                                         |
|:----------------|:----------|---------:|------------:|--------:|-------------:|--------------------------:|-----------:|-----------:|:----------------------------------------------------------------------------------------------------------------------|
| 2026-10-29      | 4 (16–20) |    450.6 |       319.1 |  -131.5 |        246.2 |                     329.2 |      270.2 |      364.2 | Thu; forecast too low; price jumped 121 EUR vs same block on day D; large swing inside the block; evening spike       |
| 2026-10-10      | 3 (12–16) |    185.0 |       139.1 |   -46.0 |         59.6 |                     180.0 |       86.6 |      178.0 | Sat; forecast too low                                                                                                 |
| 2026-10-28      | 4 (16–20) |    329.2 |       286.7 |   -42.6 |        260.2 |                     268.0 |      247.3 |      308.3 | Wed; forecast too low; price jumped 61 EUR vs same block on day D                                                     |
| 2026-10-01      | 4 (16–20) |    243.4 |       209.0 |   -34.5 |        217.4 |                     212.1 |      194.2 |      231.0 | Thu; forecast too low; large swing inside the block                                                                   |
| 2026-10-08      | 3 (12–16) |    213.9 |       181.3 |   -32.6 |        169.8 |                     168.8 |      105.8 |      197.9 | Thu; forecast too low; price jumped 45 EUR vs same block on day D                                                     |
| 2026-10-11      | 3 (12–16) |     88.7 |       120.1 |    31.3 |         78.6 |                     185.0 |       71.8 |      183.8 | Sun; forecast too high; price fell 96 EUR vs same block on day D; large swing inside the block; deep solar midday dip |
| 2026-10-01      | 3 (12–16) |    169.8 |       139.1 |   -30.7 |        150.8 |                     128.1 |       71.4 |      149.9 | Thu; forecast too low; price jumped 42 EUR vs same block on day D                                                     |
| 2026-10-28      | 3 (12–16) |    270.1 |       240.6 |   -29.5 |        244.5 |                     228.3 |      212.2 |      259.7 | Wed; forecast too low; price jumped 42 EUR vs same block on day D                                                     |
| 2026-10-01      | 2 (08–12) |    207.8 |       178.9 |   -28.9 |        172.8 |                     177.9 |      142.4 |      181.8 | Thu; forecast too low                                                                                                 |
| 2026-10-26      | 2 (08–12) |    220.3 |       248.9 |    28.6 |        261.9 |                     207.3 |      233.8 |      270.5 | Mon; forecast too high                                                                                                |


**What happened (after-the-fact look at the data, incl. the German price of the delivery day):**

1. **Thu 29 Oct, 16–20 – the biggest miss (−131 EUR).** A cold, almost wind-still evening in Germany (JMA wind
   index ≈ 1, German price of that block ≈ 470 EUR, one CH hour at ≈ 600 EUR). The model forecast 319 (same block
   on day D: 329, naive: 246); a block price of 451 EUR is far above anything since 2023 (the 2024 – Sep 2026
   maximum was 282 EUR), so the trees had no similar case to learn from. The 10–90 % band (270–364) missed it too.
2. **Sat 10 Oct, 12–16 (−46).** The model expected the usual sunny-weekend midday dip (139). Germany did crash to
   ≈ 0 EUR (windy and sunny), but Switzerland stayed at 185 – Swiss and German prices diverged (full
   interconnectors would be one explanation, but that is a guess: we have no capacity data). The naive forecast (60) was even worse.
3. **Wed 28 Oct, 16–20 (−43)** and **Wed 28 Oct, 12–16 (−30).** The start of the same cold, low-wind spell:
   the whole day rose by ≈ 30 EUR vs day D and the evening ramp was steeper than ever before.
4. **Thu 1 Oct, 08–12 / 12–16 / 16–20 (−29 to −35).** First day of the test month: the day-mean price rose by
   ≈ 21 EUR vs 30 Sep (180 → 201) without a matching move in gas; a model that learns changes vs day D
   under-shoots such sudden level jumps.
5. **Thu 8 Oct, 12–16 (−33).** Windy in Germany (German price ≈ 107), the model expected a midday dip; Switzerland
   stayed at ≈ 214 – again Swiss and German prices diverged.
6. **Sun 11 Oct, 12–16 (+31, the only "too high" miss in the top 6).** A real sunny-Sunday solar dip (89 EUR;
   Germany 34). The model went down from 185 on Saturday to 120, but not far enough.
7. **Mon 26 Oct, 08–12 (+29).** Windy Monday morning after the autumn clock change (German price ≈ 99); the
   model expected a normal Monday morning ramp.

**Pattern:** 8 of the 10 worst blocks are forecasts that were *too low*, all in the day-time and evening blocks
(08–20) of a month in which prices rose by ≈ 30 % (gas TTF from ≈ 72 EUR/MWh on 30 Sep to ≈ 97 EUR/MWh on 26 Oct; first and last October closes 73.94
and 103.94). The model is anchored on day D, so it
follows a trend with a lag of about one day; the mean October bias is −6.5 EUR/MWh. The two "too high" misses are
weekend/Monday blocks with much more wind or sun than usual. There were no negative prices in October 2026.



## What was tried (September 2026 + 5-fold time-series CV on the training period)

Single LightGBM with the final settings unless stated; `cv_mae` = mean over the 5 folds (the first folds are dominated by the 2021–2022 crisis), `cv_mae_last2` = the two most recent folds. Sensitivity rows also show October (reporting only, never used for choices).

| experiment                                                             | kind         |   val_mae |   val_smape |   val_bias |   val_rank_corr |   val_shape_mae |   cv_mae |   cv_mae_last2 |   test_mae |   test_smape |
|:-----------------------------------------------------------------------|:-------------|----------:|------------:|-----------:|----------------:|----------------:|---------:|---------------:|-----------:|-------------:|
| A0 LightGBM on the level, equal weights                                | target       |    15.416 |      14.822 |     -1.067 |           0.924 |          10.193 |   40.993 |         11.183 |    nan     |      nan     |
| A1 change vs same block of day D                                       | target       |    15.327 |      14.681 |     -3.653 |           0.928 |           9.572 |   12.798 |         10.969 |    nan     |      nan     |
| A2 change vs day-D mean price                                          | target       |    14.750 |      13.624 |     -2.568 |           0.939 |           9.337 |   13.082 |         11.188 |    nan     |      nan     |
| A3 change vs day-D mean + 7-day block shape                            | target       |    13.888 |      12.952 |     -2.921 |           0.947 |           8.551 |   12.605 |         11.311 |    nan     |      nan     |
| A4 asinh change vs day-D mean + 7-day shape                            | target       |    14.525 |      14.127 |     -5.279 |           0.947 |           8.870 |   14.092 |         11.242 |    nan     |      nan     |
| A5 asinh change vs same block of day D                                 | target       |    15.056 |      15.037 |     -6.127 |           0.924 |           9.499 |   15.914 |         10.797 |    nan     |      nan     |
| B0 no recency weights                                                  | recency      |    14.122 |      13.221 |     -3.077 |           0.939 |           9.139 |   12.655 |         11.469 |    nan     |      nan     |
| B1 recency half-life 0.5 y                                             | recency      |    14.644 |      13.306 |     -3.941 |           0.943 |           8.925 |   12.999 |         11.290 |    nan     |      nan     |
| B2 recency half-life 1.5 y                                             | recency      |    14.031 |      12.360 |     -3.304 |           0.939 |           8.786 |   12.708 |         11.361 |    nan     |      nan     |
| B3 recency half-life 2 y                                               | recency      |    14.366 |      13.012 |     -3.541 |           0.937 |           8.677 |   12.536 |         11.133 |    nan     |      nan     |
| B4 train 2023+ only                                                    | recency      |    14.522 |      13.591 |     -4.565 |           0.928 |           8.999 |  nan     |        nan     |    nan     |      nan     |
| B5 train 2024+ only (ICON era)                                         | recency      |    15.209 |      14.024 |     -8.753 |           0.933 |           8.621 |  nan     |        nan     |    nan     |      nan     |
| C1 L1 loss                                                             | loss         |    15.609 |      14.679 |     -2.702 |           0.929 |           9.258 |   13.256 |         11.211 |    nan     |      nan     |
| C2 Huber loss (delta 20 EUR)                                           | loss         |    14.041 |      13.069 |     -3.489 |           0.941 |           8.713 |   12.860 |         11.271 |    nan     |      nan     |
| D1 no derived features                                                 | features     |    15.134 |      14.393 |     -2.750 |           0.945 |           8.708 |   13.171 |         11.598 |    nan     |      nan     |
| D2 with ICON eu_* columns (drop nothing)                               | features     |    14.178 |      13.673 |     -4.302 |           0.954 |           8.263 |   12.754 |         11.682 |    nan     |      nan     |
| D3 without Zurich weather                                              | features     |    15.077 |      14.267 |     -5.601 |           0.931 |           8.966 |   12.834 |         11.541 |    nan     |      nan     |
| D4 without Zurich demand lags                                          | features     |    14.236 |      13.135 |     -3.871 |           0.933 |           8.606 |   12.774 |         11.452 |    nan     |      nan     |
| E1 3 seeds                                                             | ensemble     |    14.024 |      12.994 |     -3.777 |           0.943 |           8.277 |  nan     |        nan     |    nan     |      nan     |
| E2 3 seeds + LEAR ridge 20 %                                           | ensemble     |    13.740 |      12.653 |     -3.119 |           0.943 |           8.361 |  nan     |        nan     |    nan     |      nan     |
| E2 3 seeds + LEAR ridge 35 %                                           | ensemble     |    13.670 |      13.467 |     -2.626 |           0.939 |           8.531 |  nan     |        nan     |    nan     |      nan     |
| E2 3 seeds + LEAR ridge 50 %                                           | ensemble     |    13.642 |      13.534 |     -2.133 |           0.937 |           8.822 |  nan     |        nan     |    nan     |      nan     |
| E3 3 seeds + ridge 35 %, ridge averaged over 3 windows (all, 2 y, 1 y) | ensemble     |    13.927 |      13.607 |     -3.958 |           0.937 |           8.526 |  nan     |        nan     |    nan     |      nan     |
| E4 LEAR ridge alone                                                    | ensemble     |    14.085 |      13.826 |     -0.489 |           0.926 |          10.157 |   16.657 |         13.076 |    nan     |      nan     |
| E5 two-stage: day-mean change + within-day shape (2 LightGBMs)         | target       |    15.960 |      15.129 |     -4.446 |           0.939 |           9.235 |   13.185 |         11.306 |    nan     |      nan     |
| G0 final config, fit once on train                                     | walk-forward |    13.670 |      13.467 |     -2.626 |           0.939 |           8.531 |  nan     |        nan     |    nan     |      nan     |
| G1 final config, weekly walk-forward refit                             | walk-forward |    13.620 |      13.582 |     -1.436 |           0.933 |           8.485 |  nan     |        nan     |    nan     |      nan     |
| G2 final config, daily walk-forward refit                              | walk-forward |    13.867 |      13.725 |     -1.355 |           0.931 |           8.562 |  nan     |        nan     |    nan     |      nan     |
| S0 sensitivity base (1 seed, all features)                             | sensitivity  |    13.888 |      12.952 |     -2.921 |           0.947 |           8.551 |  nan     |        nan     |     13.068 |        6.214 |
| S1 without European weather (all eu_*)                                 | sensitivity  |    15.597 |      14.168 |     -4.781 |           0.928 |           9.274 |  nan     |        nan     |     13.815 |        6.538 |
| S2 without neighbour prices                                            | sensitivity  |    14.341 |      12.462 |     -4.201 |           0.935 |           8.438 |  nan     |        nan     |     14.398 |        6.813 |
| S3 without gas / CO2 / FX                                              | sensitivity  |    15.047 |      12.806 |     -3.271 |           0.937 |           8.545 |  nan     |        nan     |     13.199 |        6.268 |
| S4 ORACLE Zurich weather (observed, NOT achievable)                    | sensitivity  |    14.991 |      14.038 |     -4.081 |           0.937 |           8.899 |  nan     |        nan     |     14.119 |        6.841 |
| S5 + German TSO forecasts unverified_de_* (NOT allowed in product)     | sensitivity  |    13.461 |      12.943 |     -4.281 |           0.945 |           8.299 |  nan     |        nan     |     13.663 |        6.428 |


## Why this model won
* **Learn the change, not the level.** LightGBM on the price level (A0) has a CV MAE of ≈ 41 EUR because trees
  cannot predict a price level they have never seen (the 2021–2022 crisis); learning the change vs a known
  price cuts that to ≈ 12.6. Of the references, `ref_shape7` (day-D mean + 7-day block shape, A3) was best on
  September and on the CV. The asinh-scaled change (A4/A5) and a two-stage day-mean + shape model (E5) were worse.
* **Recency weights.** A half-life of 1 year beat no weights and 0.5 / 1.5 / 2 years on September (the CV is
  flat at 12.5–13.0). Training only on 2023+ or 2024+ (B4/B5) was worse: the model needs the long history.
* **L2 loss.** L1 and Huber (C1/C2) were not better on September or CV.
* **Features.** Leaving out the ICON European weather columns (`eu_*_safe`, which only exist from 2024) helped
  on September (13.9 vs 14.2) *and* on the CV (12.6 vs 12.8): with only 2.5 years of data the tree splits on them
  are noisy, while the JMA columns (`eu_*_jma_safe`, full history) carry the German wind / temperature signal.
  Derived columns (`PriceExtras`, e.g. day-D shape, weekday of day D, gas cost vs price, radiation × weekend)
  helped (D1: 15.1 without them).
* **Ensemble.** The LEAR-style ridge regression alone (E4) is close to a single LightGBM on September (14.1) but
  much worse on the CV (16.7); blended 35 % it lowers the September MAE from 14.0 to 13.7 and lowers the bias by about 30 % (from −3.8 to −2.6).
  Averaging the ridge over three calibration windows (E3) did not help.
* **Weekly walk-forward refit** (G1) beat a single fit (G0, 13.62 vs 13.67) and reduced the bias from −2.6 to −1.4
  EUR; a daily refit (G2) was not better.
* **Hyper-parameters.** An optuna search (15 trials, score = MAE of the two most recent CV folds,
  `reports/tuning_price.csv`) found settings with a slightly better CV score, but all of them were worse on
  September (14.6–16.9 vs 14.3), so the default LightGBM settings were kept. Differences between configurations
  are often within the seed noise (≈ ±0.3 EUR on September with one seed), which is why we average 3 seeds.



## Driver importance

Permutation importance on Sept + Oct 2026 (MAE increase in EUR/MWh when a column, or a whole group of columns, is shuffled).

### Groups

| feature                                        |   mae_increase |   std |
|:-----------------------------------------------|---------------:|------:|
| CH price of day D (lags, shape)                |         25.046 | 1.206 |
| calendar (block, weekday, holidays, season)    |         15.112 | 1.468 |
| Zurich weather (forecast + past observed)      |         14.131 | 1.320 |
| European weather forecasts JMA (eu_*_jma)      |          2.355 | 0.299 |
| neighbour prices DE/FR/AT/IT (day D)           |          1.890 | 0.153 |
| gas / CO2 / EUR-CHF                            |          1.431 | 0.076 |
| European weather forecasts ICON (eu_*)         |          0.747 | 0.174 |
| Zurich demand lags                             |          0.444 | 0.227 |
| Swiss system D−1 (load, hydro, nuclear, solar) |          0.281 | 0.097 |
| Swiss reservoirs                               |         -0.051 | 0.011 |


### Top 20 single columns

| feature                          |   mae_increase |   std |
|:---------------------------------|---------------:|------:|
| price_mean_day_D                 |         22.111 | 0.720 |
| radiation_wm2                    |         13.625 | 3.783 |
| price_block_vs_day_ratio_last_7d |          7.565 | 0.125 |
| block                            |          7.243 | 1.248 |
| weekday                          |          3.400 | 0.265 |
| is_weekend                       |          2.128 | 0.604 |
| clean_gas_cost                   |          0.962 | 0.125 |
| price_lag_1d_same_block          |          0.653 | 0.088 |
| eu_radiation_wm2_de_mean_safe    |          0.585 | 0.070 |
| price_de_mean_day_D              |          0.571 | 0.087 |
| spread_ch_de_day_D               |          0.532 | 0.110 |
| expected_demand_proxy            |          0.417 | 0.133 |
| price_lag_7d_same_block          |          0.338 | 0.102 |
| spread_ch_it_day_D               |          0.283 | 0.062 |
| sunshine_day_sum                 |          0.268 | 0.032 |
| price_lag_14d_same_block         |          0.256 | 0.042 |
| cloud_pct                        |          0.252 | 0.010 |
| price_spread_day_D               |          0.243 | 0.077 |
| is_working_day                   |          0.240 | 0.047 |
| gas_ttf_change_5d                |          0.238 | 0.024 |


## Top-10 drivers
Single columns, permutation importance on Sep + Oct 2026 (see the table above). Shuffling a column that is part
of the reference (`price_mean_day_D`, `price_block_vs_day_ratio_last_7d`) also breaks the reference itself, so
these two are inflated by construction.

1. **`price_mean_day_D`** – today's average CH price is the anchor: tomorrow's prices are mostly today's level plus a
   change.
2. **`radiation_wm2`** – the Zurich solar-radiation forecast for the block tells the model how deep the midday solar
   dip will be (more sun = cheaper 12–16 block).
3. **`price_block_vs_day_ratio_last_7d`** – the typical shape of the day over the last week (night cheap, evening
   expensive) is the second half of the reference.
4. **`block`** – the time of day itself: the evening block 16–20 and night block 20–24 are the most expensive,
   midday the cheapest.
5. **`weekday`** – Saturdays, Sundays and Mondays differ from day D in a predictable way (e.g. Sunday → Monday
   prices rise, Friday → Saturday prices fall).
6. **`is_weekend`** – weekend demand is lower, so weekend prices (especially midday) fall below the weekday level.
7. **`clean_gas_cost`** – the cost of a gas power plant (gas + CO₂) sets the price in many hours; when it is far above
   or below today's price, prices move towards it.
8. **`price_lag_1d_same_block`** – the price of the same block today adds detail the 7-day shape misses
   (e.g. a new evening peak).
9. **`eu_radiation_wm2_de_mean_safe`** – the German solar forecast (used through `rad_de_x_trend`, radiation × years
   since 2019): German solar build-out pushes the midday price down more every year.
10. **`price_de_mean_day_D`** – the German price of day D: Switzerland mostly imports the German price level, the
    CH–DE spread changes only slowly.

Group view: the CH price of day D (lags + shape), the calendar and the Zurich weather forecast are by far the most
important groups; the JMA European weather forecasts (German wind, French/German temperature), neighbour prices
and gas/CO₂ follow; Swiss reservoir fill and the Swiss system data of D−1 add almost nothing on these two months.



## Sensitivity runs (single LightGBM, for the notes only – not used for choosing the model)
See rows S0–S5 in "What was tried" (val = September, test = October, fit on data ≤ Aug 31 / ≤ Sep 30):
* Without any European weather forecast (S1): September MAE +1.7, October +0.7 EUR – the JMA German wind and
  temperature forecasts are worth keeping.
* Without neighbour prices (S2): +0.5 / +1.3 EUR.
* Without gas / CO₂ / FX (S3): +1.2 / +0.1 EUR (the CH price of day D already contains most of the fuel level).
* ORACLE Zurich weather (S4, observed weather of the delivery day, not achievable): *worse* (15.0 vs 13.9 on
  September). Training on observed weather before 2024 and on forecasts after makes the weather columns
  inconsistent; perfect Zurich weather is not what limits the price forecast.
* With the German TSO day-ahead wind/solar/load forecasts (S5, `unverified_de_*` – NOT allowed in the product,
  because they may be published after 10:00): September −0.4 EUR, October +0.6 EUR. Their value is small and not
  stable; the JMA wind forecast already carries most of the information.

## Limitations
* **Trends and spikes.** The model is anchored on day D, so in a month with a strong upward trend (October 2026:
  +30 %) it is too low on average (bias −6.5 EUR/MWh) and it misses scarcity spikes (29 Oct evening, 451 EUR).
  The 10–90 % band covers 87 % of October but its misses are almost all on the upper side.
* **One validation month.** September has only 30 days; many choices differ by less than the seed noise. The CV and
  the rolling backtest (Oct 2025 – Aug 2026) support the main choices, but the rolling backtest shows the best
  model is NOT significantly better than the plain LightGBM there (DM p ≈ 0.3) – the big gain vs gbm in
  September/October comes from months where the price level moves.
* **Weather history.** Zurich weather is observed before 2024 and forecast after; ICON European weather exists only
  from 2024 (left out), JMA has no radiation. Better European solar forecasts with a long history would help.
* **No cross-border capacity data.** Several misses are days where CH decoupled from Germany (possibly full interconnectors - this is a guess);
  we have no capacity or flow forecasts.
* **The saved model file is one fit.** `models/price_best.joblib` is the fit on data up to 30 Sep. The scored
  October forecast (`pred_best`) comes from weekly refits, so the file reproduces only the first 7 days exactly.
  Used alone for the whole of October the single fit scores an MAE of 12.35 EUR/MWh (checked by the independent
  reviewer); the battery result changes by about CHF 250.
* **One derived input still uses ICON data:** `rad_de_x_trend` (German radiation forecast x solar build-out trend)
  is kept although the raw ICON European columns are left out.
* **October sensitivity runs:** the "without X" runs were scored on October too, after the settings were frozen.
  The code does not enforce this order, so we state it here: no choice was made with October numbers.
* **Importance is from the fixed models** (fit ≤ Aug 31 / ≤ Sep 30), not from the weekly walk-forward refits that
  produce `pred_best`; the drivers are the same, the numbers slightly differ.



_`main()` runtime of this run: 4.7 min._
