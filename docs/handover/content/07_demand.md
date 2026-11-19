# 7 Demand model

<div class="inshort" markdown="1">

The demand model forecasts the mean Zurich load of each block of D+1. The winner does not predict the level: it
predicts **how much higher or lower** each block will be than the same block on D−1 (a log ratio), with five LightGBM
runs averaged and blended 85/15 with a ridge regression. October error: {{n:dem_test_mae_best}} MW ({{n:dem_test_pct_best}} %), a third of the naive
rule. Weak spots: days two days after a holiday, and Christmas.

</div>

## The ladder and the protocol

The brief required a **ladder** from simple to complex, all evaluated the same way:

| Rung | Model | Idea |
|---|---|---|
| naive | same block 7 days earlier | what a utility could do without any model |
| linear | ridge regression (scaled) | block × weekday-type and block × month dummies, per-block slopes for temperature, degrees, radiation and the main lags |
| rf | random forest | non-linear, no tuning of a target transform |
| gbm | LightGBM on the level | the standard gradient-boosting model |
| best | the winner on September | see below |

**Protocol (do not deviate – the test month is touched once).**

- **Train** on delivery dates up to 31 August 2026 (demand models: up to **30 August**, the last day whose demand is
  known when the first September forecast is made).
- **Choose** model family, features, target transform, weighting and ensembling on **September 2026** together with a
  5-fold time-series cross-validation on the training period (`TimeSeriesSplit`). October is not looked at.
- **Refit** the frozen configuration on data up to **29 September** and evaluate **once** on **October 2026**
  (31 days × 6 blocks = 186 forecasts).
- **Rolling-origin backtest** (robustness, not the headline): refit at the start of each month from October 2025 to
  August 2026 and forecast that month.
- **Metrics:** MAE (average size of the miss), RMSE, MAPE, bias (forecast − actual), skill versus naive; 95 %
  intervals by bootstrapping whole days (1,000 draws); Diebold–Mariano test on daily mean absolute errors.

## Results

{{t:demand_metrics|Demand model ladder. MAE in MW; bias = forecast − actual; 95 % CI = bootstrap over whole days. Source: `reports/metrics_demand.csv`.}}

{{fig:demand_model_ladder.png|MAE per model and period.}}

{{fig:demand_test_forecast_vs_actual.png|October 2026: the 186 block forecasts of the best model and the naive rule against the actual demand.}}

## What was tried, and what won

All rows below are single LightGBM runs unless stated. "CV" = mean MAE over the 5 time-series folds; "last 2" = the two
most recent folds. October values exist only for the sensitivity rows (S0–S5), which were run **after** the settings
were frozen and never used for a choice.

{{t:experiments_demand|Every demand experiment. Source: `reports/experiments_demand.csv`.}}

**Why the winner won** (decided on September + CV, before October was looked at):

- **The target transform is the big step.** LightGBM on the level: CV {{e:demand:A0:cv_mae}} MW, September {{e:demand:A0:val_mae}}. The same LightGBM
  predicting log(demand ÷ same block on D−1): CV {{e:demand:A:cv_mae}}, September {{e:demand:A:val_mae}}. Trees cannot extrapolate a level they have
  not seen, but "a bit higher or lower than the last known day" they predict well. The D−1 reference beats the 7-day
  reference (CV {{e:demand:A1:cv_mae}}) and the 4-week same-weekday mean (CV {{e:demand:A3:cv_mae}}) because it carries the most recent level
  (school holidays, weather spells). A plain difference was equal in CV ({{e:demand:A2:cv_mae}}) but worse on September ({{e:demand:A2:val_mae}}).
- **Loss.** L1 and Huber were not better in CV ({{e:demand:B1:cv_mae}} / {{e:demand:B2:cv_mae}}). Huber looked good on September alone
  ({{e:demand:B2:val_mae}}), but five folds were trusted more than one month – squared error kept.
- **Weighting.** Recency weights (half-life 1–3 years) and a lower weight for the COVID lockdown made CV equal or worse;
  all history counts equally.
- **Weather source.** The ICON/observed hybrid won. JMA forecasts for all years were clearly worse (September
  {{e:demand:D2:val_mae}}, CV {{e:demand:D2:cv_mae}}) because JMA has no radiation. The **oracle** with observed weather of the delivery day (not achievable)
  reaches {{e:demand:D4:val_mae}} on September: the weather-forecast error costs a few tenths of a MW.
- **Extra features.** Forecast minus observed temperature/radiation of the reference day helped a little
  (September {{e:demand:E1:val_mae}} without them).
- **Ensemble.** Five seeds ({{e:demand:F1:val_mae}}) and 15 % ridge on the same log ratio ({{e:demand:F2:val_mae}}) helped; 30 % ridge was slightly worse
  ({{e:demand:F3:val_mae}}). One-seed results move by about ±0.1 MW between seeds, so smaller differences are noise.
- **Daily walk-forward refit** ({{e:demand:G1:val_mae}} vs {{e:demand:G0:val_mae}}) – a gain smaller than the seed noise and about 30× slower, so the
  model is fitted once per month.
- **Hyper-parameters.** An optuna search (16 trials; score: mean MAE of all five CV folds) did not beat the starting values, which were kept.

The final settings are frozen in `models/demand_best_params.json` (table in chapter 8's last section).

## Errors per block and on special days

{{fig:demand_error_by_block.png|October MAE per block: the day-time blocks are hardest, the night is easy.}}

{{t:special_days|Error on special days, rolling period + October (MAE in MW). Source: `reports/model_notes_demand.md`.}}

The best model handles holidays themselves well, but **on delivery days two days after a holiday** (when the reference
day D−1 was a holiday, `lag2d_was_holiday`) and around **Christmas** it is slightly worse than the level LightGBM and
forecasts too low. Blending in the level model on such days is the obvious next step (not done, to keep October
untouched).

## Drivers

{{t:importance_demand|Permutation importance of input groups on September + October 2026: how much the MAE grows (MW) when the group is shuffled. Source: `reports/importance_groups_demand.csv`.}}

{{fig:demand_permutation_importance.png|The 20 most important single columns.}}

One honest sentence per driver the brief asked about:

- **EVs** add nothing measurable to the 4-hour forecast: without them the single-model October error was
  {{e:demand:S2:test_mae}} instead of {{e:demand:S0:test_mae}} MW. Their slow growth is already in the recent demand.
- **Weather** is the fourth most important group: without it the October error rises from {{e:demand:S0:test_mae}} to {{e:demand:S4:test_mae}} MW. Radiation
  matters more than temperature in this mild season.
- **Solar:** lagged Swiss solar production adds almost nothing; the solar effect enters through the radiation
  forecast of the delivery day.
- **Holidays** are essential (see the special-days table).
- **Events** (Street Parade, Züri Fäscht, concerts, home games) add little incremental predictive value in this model:
  without them the single-seed October error was {{e:demand:S3:test_mae}} instead of {{e:demand:S0:test_mae}} MW, within the seed noise. This is not a
  statement about whether events change the load.

## Uncertainty and significance

{{t:bands|Share of actual values inside the 10–90 % band of the quantile models (target 80 %). The demand band is slightly too narrow.}}

The best model is significantly better than plain LightGBM in all three periods (Diebold–Mariano p = {{n:dm_dem_val_gbm_p}} in September,
{{n:dm_dem_test_gbm_p}} in October, {{n:dm_dem_roll_gbm_p}} over the rolling period); full table in chapter 11.

## Weaknesses and sensitivities

- **Weather in training is partly observed** (before 2024): the model may trust the weather a little too much. Test
  errors are honest because the test uses real forecasts.
- **If D−1 demand were not available** (only D−2, as in the public file) the single-model October error would rise
  from {{e:demand:S0:test_mae}} to {{e:demand:S1:test_mae}} MW.
- **One test month** gives a 95 % interval of the October MAE of {{n:dem_test_ci_low}}–{{n:dem_test_ci_high}} MW.
- **Days after holidays, Christmas and half-holidays** are the weakest cases.
- **Permutation importance** splits the credit between related columns (weekday, `is_working_day`, `is_weekend`), so
  read single numbers together with the group table.
