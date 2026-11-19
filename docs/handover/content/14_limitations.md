# 14 Limitations, what the results cannot tell you, and ethics

<div class="inshort" markdown="1">

The forecasts are honestly tested on one month that no model or decision choice saw (one weather pre-processing choice saw its weather, see below). The money is a simulation under assumed imbalance prices,
with a fictional battery that never moves the price and no intraday market. The results show that the method works
and roughly how its value splits; they do not show what a real DSO would save under Swissgrid's real settlement.

</div>

## What the results can and cannot tell you

| You **can** say | You **cannot** say |
|---|---|
| The demand forecast is about a third as wrong as the naive rule on a month no model or decision choice saw ({{n:dem_test_mae_best}} vs {{n:dem_test_mae_naive}} MW), and significantly better than plain LightGBM | that it would be as good in winter (January 2026 is part of the rolling run and the tuning, not an independent test) |
| The price forecast picks the cheapest and dearest blocks of a day well, which is what the battery needs | that it predicts spikes (29 October) or strong trends |
| Under the assumed penalty, avoiding imbalance is worth more than the battery | that this ranking holds under Swissgrid's single-price quarter-hourly settlement |
| Planning the battery hour by hour inside blocks matters much more than moving energy between days | what a real battery would earn after its own price impact |
| The product beat the baseline in every month of the rolling year | that the rolling sum (CHF {{n:year_saving}}) is an out-of-sample test – the rules were tuned on it |

## Limitations, one by one

- **Assumed imbalance prices.** Shortage p + 0.2·|p|, surplus p − 0.2·|p|. They explain CHF {{n:demand_forecast_part_chf_test}} of the
  CHF {{n:total_saving_chf_test}} October saving. With ±10 %: CHF {{n:imb_11_09_saving}}. Real settlement is quarter-hourly with one price, where a
  deviation in the helpful direction can earn money.
- **One test month, wide intervals.** CHF {{n:ciblock_low_test}} to {{n:ciblock_high_test}} with {{n:ci_blocklen}}-day blocks.
- **Rules and settings partly chosen with later data.** The decision rules were tuned on the rolling period and
  1–29 September; the model settings were chosen on September 2026, after the rolling months. Only October is clean
  of these choices, with the one exception in the next point.
- **One weather pre-processing choice saw October weather** (the temperature-correction method; the effect is about
  0.001–0.01 °C; no October demand or prices involved).
- **Observed weather in training before 2024.** The model may trust weather slightly too much. Test errors are honest.
- **Fictional battery and price taker.** Size, efficiency, wear and limits are assumptions; for 100 MW the linear
  scaling of battery value is too optimistic.
- **Cycle definition** allows about {{n:cycle_excess_pct}} % more than one physical cycle (about CHF {{n:cycle_cap_cost}} in October).
- **ewz status flags.** No value is final; ewz can revise values for up to six months.
- **Auction time** of 11:00 for the whole period; single delayed or decoupled days are ignored.
- **Demand availability.** The DSO is assumed to know its own demand to the end of D−1.
- **Unofficial gas data and licences.** Yahoo `TTF=F` (personal/educational use) and EEX (research use); derived
  series are in the (public) repository and the app plots gas (chapter 16, "Before you publish").
- **Scope of the leakage test.** It starts from processed inputs, not raw downloads.
- **No intraday market.** A real DSO would correct errors before delivery, which would shrink the demand saving of all
  strategies.
- **No grid constraints** (battery location, city grid limits).
- **Block simplification.** Forecasts are per 4-hour block; the hourly shape inside a block is a recent average.
- **No cross-border capacity data** for the days when Swiss and German prices diverged.
- **15-minute products.** The Swiss price series has 15-minute values from {{n:ch15_local}} ({{n:ch15_utc}}); the project is hourly.

## Ethics and fairness

- **No personal data.** All data is public and aggregated: city-wide load, national prices, weather, yearly car counts.
  No household can be identified.
- **Smart-meter privacy.** Extending the idea to household smart-meter data would reveal when people are at home,
  sleep or travel. Depending on purpose and legal basis this could need consent; in any case it would need aggregation,
  data minimisation and compliance with the Swiss Federal Act on Data Protection.
- **Who benefits.** The savings lower the DSO's purchase cost. Whether customers benefit depends on how tariffs pass
  costs on; for a public utility the fair choice would be to pass them on. Better forecasts also reduce imbalance in
  the national grid, which helps everyone.
- **Energy use of the models.** Training both models takes about {{n:rt_demand}} + {{n:rt_price}} minutes of elapsed time on a laptop
  (energy not measured) – negligible next to the {{n:oct_energy_gwh}} GWh the city used in October 2026.
- **Use of AI in the build.** The code, documents and reviews were produced by AI agents under the orchestration
  described in chapter 3. The team should say so openly when presenting the project, and must be able to explain every
  decision itself – which is the purpose of this report.
- **Transparency.** Every assumption is listed with a reason (`docs/assumptions.md`), every review finding with its
  decision (`docs/review_log.md`), and the code is reproducible.
