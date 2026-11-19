# 17 Next steps (prioritised)

<div class="inshort" markdown="1">

The most valuable next step is to replace the assumed imbalance prices with Swissgrid's real ones, because they drive
most of the saving. Then add an intraday correction, move to hourly (and 15-minute) forecasts, fix the known weak spots
of the models, and settle the data licences of the (already public) repository.

</div>

| # | Step | Why | Effort | Evidence |
|---|---|---|---|---|
| 1 | **Real imbalance prices** from Swissgrid (quarter-hourly, single price) instead of p ± 0.2·&#124;p&#124; | about {{n:pct_demand_of_saving_test}} % of the October saving rests on the assumption; the ranking demand vs battery is unproven | medium | chapter 11 sensitivities |
| 2 | **Official gas and CO₂ data** (HSG LSEG/Bloomberg) and a licence check | the repository is public and contains derived series | small | chapter 16 |
| 3 | **Intraday correction**: re-forecast on the morning of D+1 and trade the difference | a real DSO would do this; it changes the value of every strategy | large | chapter 14 |
| 4 | **Hourly forecasts** instead of 4-hour blocks, then **15-minute** products (the Swiss auction moved to 15 min in Nov 2026) | with perfect foresight hourly dispatch is worth CHF {{n:finer_dispatch_part_chf_test}} more than block dispatch in October; multi-day planning at most CHF {{n:interday_flexibility_part_chf_test}} | large | chapter 11 |
| 5 | **Days after holidays and Christmas**: blend in the level model when the reference day was a holiday | the weakest demand cases | small | chapter 7 |
| 6 | **Price trends and spikes**: a trend-following term; better scarcity features (German wind, temperature) | October bias {{n:pri_test_bias_best}} EUR/MWh; 29 October miss | medium | chapter 8 |
| 7 | **A second, independent test month** (e.g. winter): a new window, untouched so far, with model settings and decision rules frozen before it | one month is a thin test; January 2026 is not independent (inside the rolling run and the tuning) | small–medium | chapter 16, "Refreshing with new data" |
| 8 | **Cross-border capacity** and German renewables forecasts with verified publication times | several price misses were Swiss/German divergences | medium | chapter 8 |
| 9 | **Battery business case**: yearly battery value against investment and operating cost by size; drop the price-taker assumption for large sizes | the battery value is only half the story | medium | chapter 11 |
