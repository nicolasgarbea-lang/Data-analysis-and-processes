# 8 Price model

<div class="inshort" markdown="1">

The price model forecasts the mean Swiss day-ahead price of each block of D+1. Like the demand model it predicts a
**change** – from "today's mean price plus the usual shape of this block over the last 7 days" – with recent years
weighted more, three LightGBM seeds blended 65/35 with a ridge regression, and a refit every 7 days. October error
{{n:pri_test_mae_best}} EUR/MWh (naive {{n:pri_test_mae_naive}}); it was too low on average in a month of rising prices, and it missed one scarcity spike.

</div>

## Set-up

Same ladder and protocol as the demand model (chapter 7), with two differences:

- The **percentage error** is the symmetric MAPE (sMAPE), because prices can be near zero or negative.
- At 10:00 on D **all prices of day D are known**, so the price model may be refit with data up to D. The best model
  is refit **every 7 days** during the month (walk-forward); the saved file `models/price_best.joblib` is the fit on
  data up to 30 September only.

## Results

{{t:price_metrics|Price model ladder. MAE in EUR/MWh. Source: `reports/metrics_price.csv`.}}

{{fig:price_model_ladder.png|MAE per model and period.}}

{{fig:price_test_forecast_vs_actual.png|October 2026: block price forecasts against the actual price.}}

**For the battery the order of the blocks matters more than the level.** The decision metrics measure this:

{{t:price_decision|Rank correlation = Spearman correlation of the six block prices within a day; "cheapest/dearest block right" = share of days where the model picks the right block; shape MAE = error of (block − day mean); day-mean MAE = error of the daily level. Source: `reports/decision_metrics_price.csv`.}}

## What was tried, and what won

{{t:experiments_price|Every price experiment (single LightGBM with the final settings unless stated). CV folds before 2023 are dominated by the 2021–2022 crisis, so the two most recent folds are shown separately. Source: `reports/experiments_price.csv`.}}

- **Learn the change, not the level.** LightGBM on the price level has a CV MAE of {{e:price:A0:cv_mae}} EUR/MWh because trees cannot predict a
  price level they have never seen; learning the change against a known price cuts that to about {{e:price:A3:cv_mae}}. Of the
  references, day-D mean + 7-day block shape (`ref_shape7`, A3) was best on September and on the CV. The asinh-scaled
  change (A4/A5) and a two-stage day-mean + shape model (E5) were worse.
- **Recency weights.** A half-life of 1 year beat no weights and 0.5 / 1.5 / 2 years on September; training only on
  2023+ or 2024+ was worse – the model needs the long history.
- **Loss.** L1 and Huber were not better.
- **Features.** Leaving out the ICON European weather columns (which exist only from 2024) helped on September and on
  the CV: with 2.5 years of data their tree splits are noisy, while the JMA columns (full history) carry the German wind
  and temperature signal. The derived columns (`PriceExtras`, e.g. day-D shape, gas cost vs price, radiation ×
  weekend) helped (D1 without them: September {{e:price:D1:val_mae}}).
- **Ensemble.** The LEAR-style ridge alone (E4) was close on September ({{e:price:E4:val_mae}}) but much worse on the CV ({{e:price:E4:cv_mae}}); blended
  35 % it lowered the September MAE and the bias.
- **Weekly walk-forward refit** (G1, {{e:price:G1:val_mae}}) beat a single fit (G0, {{e:price:G0:val_mae}}) and reduced the bias; a daily refit (G2) was not
  better.
- **Hyper-parameters.** An optuna search (score: mean MAE of the **two most recent** of five CV folds) found settings with a slightly better CV score but all were worse on September
  (`reports/tuning_price.csv`), so the defaults were kept. Differences between configurations are often within the seed
  noise, which is why three seeds are averaged.
- **Band.** A quantile LightGBM gives a 10/50/90 % band, widened by a factor of {{n:price_band_factor}} chosen on September so that about
  80 % of prices fall inside.

## Errors and the worst misses

{{fig:price_error_by_block.png|October MAE per block.}}

{{t:worst_blocks|The ten worst October blocks of the best model (EUR/MWh; error = forecast − actual). Source: `reports/worst_blocks_price.csv`.}}

**What happened** (after-the-fact look, from `reports/model_notes_price.md`):

- **29 October, 16–20, the biggest miss:** a cold, almost wind-still evening in Germany. The block price was far above
  anything since 2023, so the trees had no similar case; the 10–90 % band missed it too.
- **10 and 8 October, midday:** Germany's price dropped (windy and sunny), Switzerland's did not – Swiss and German
  prices diverged. Full interconnectors would be one explanation, but that is a guess: there is no capacity data.
- **1 October and 28 October:** sudden level jumps. A model anchored on day D follows a trend about one day late.
- **Pattern:** most of the worst misses are forecasts that were **too low**, in day-time and evening blocks of a month in
  which gas and power prices rose. The mean October bias is {{n:pri_test_bias_best}} EUR/MWh.

## Drivers

{{t:importance_price|Permutation importance of input groups on September + October 2026 (EUR/MWh). Source: `reports/importance_groups_price.csv`.}}

{{fig:price_permutation_importance.png|The 20 most important single columns. Columns that are part of the reference (`price_mean_day_D`, the 7-day shape) are inflated by construction: shuffling them breaks the reference itself.}}

Sensitivity runs (single LightGBM, September / October MAE, never used for a choice):

| Run | September | October |
|---|---|---|
| S0 base (all features) | {{e:price:S0:val_mae}} | {{e:price:S0:test_mae}} |
| S1 without European weather | {{e:price:S1:val_mae}} | {{e:price:S1:test_mae}} |
| S2 without neighbour prices | {{e:price:S2:val_mae}} | {{e:price:S2:test_mae}} |
| S3 without gas / CO₂ / FX | {{e:price:S3:val_mae}} | {{e:price:S3:test_mae}} |
| S4 oracle Zurich weather (not achievable) | {{e:price:S4:val_mae}} | {{e:price:S4:test_mae}} |
| S5 with German TSO forecasts (not allowed: may be published after 10:00) | {{e:price:S5:val_mae}} | {{e:price:S5:test_mae}} |

The oracle Zurich weather is *worse*: training on observed weather before 2024 and on forecasts after makes the weather
columns inconsistent; perfect Zurich weather is not what limits the price forecast.

## Significance and weaknesses

- The best model is clearly better than plain LightGBM in September (p = {{n:dm_pri_val_gbm_p}}) and October (p = {{n:dm_pri_test_gbm_p}}), but **not** over
  the rolling 11 months (p = {{n:dm_pri_roll_gbm_p}}). Its big October gain comes from a month in which the price level moved a lot.
- **Trends and spikes:** anchored on day D, it lags a strong trend and misses scarcity spikes.
- **The saved model file is one fit.** Used alone for all of October, the single fit scores {{n:price_single_fit_mae}} EUR/MWh instead of
  {{n:pri_test_mae_best}} (checked by the reviewer).
- **One derived input still uses ICON data** (`rad_de_x_trend`, German radiation × solar build-out trend), although the
  raw ICON European columns are dropped.
- **No cross-border capacity data.**

## The frozen settings of both models

{{t:best_params|Final settings, read from `models/demand_best_params.json` and `models/price_best_params.json`. `python -m src.pipeline --all` uses these; it does not repeat the searches.}}
