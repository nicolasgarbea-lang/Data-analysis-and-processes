# 1 The project in one page

<div class="inshort" markdown="1">

A fictional Zurich grid operator must buy tomorrow's electricity by 11:00 today without knowing tomorrow's demand or
price. We forecast both, plan a battery, bid hourly and settle the bids against reality. In October 2026 this saved
CHF {{n:total_saving_chf_test}} in simulation against "buy last week's demand, no battery" – but most of that is
avoided assumed penalty, the battery is fictional, and it is one month.

</div>

## The problem

**The user.** *Limmat Energie AG* is a fictional **DSO** (distribution system operator): the company that runs the
city grid and buys energy for the homes and businesses of Zurich. Its demand is the **real** ewz grid load of the city
(on average {{n:oct_mean_demand}} MW in October 2026). It also owns a fictional **{{c:battery.power_mw}} MW / {{c:battery.capacity_mwh}} MWh grid battery**.

**The daily decision.** Every day the DSO buys tomorrow's energy on the Swiss **day-ahead auction**, which closes at
**{{c:auction.gate_closure_local}}** the day before delivery. At that moment it knows neither tomorrow's demand nor tomorrow's price. For each of
the six 4-hour blocks of tomorrow (00–04, 04–08, 08–12, 12–16, 16–20, 20–24) it must decide:

1. **how much to buy**,
2. **how much to store** in the battery and when to use it,
3. **at what price to bid** for the energy it wants to store.

Buying too much or too little creates an **imbalance**, which is settled later at a worse price.

## What we built

{{svg:architecture|The team's diagram, turned into code. Green = demand, plum = price, blue = battery. The backtest box was added: it settles every bid with the real prices and demand.}}

At **{{c:auction.forecast_time_local}} on day D** the system (1) forecasts Zurich demand and the Swiss price for the six blocks of D+1, (2) plans
the battery with a mixed-integer optimisation, (3) turns the plan into hourly bids – a price-independent bid for the
city's need and a limit-price bid for energy to store – and (4) in the backtest settles the bids with the actual
hourly prices and demand. A web app shows every step for each day of September and October 2026.

## The headline results (test month October 2026)

<div class="kpis">
<div class="kpi g"><div class="v">{{n:dem_test_mae_best}} MW</div><div class="l">demand forecast error (MAE, {{n:dem_test_pct_best}} %); naive rule {{n:dem_test_mae_naive}} MW</div></div>
<div class="kpi p"><div class="v">{{n:pri_test_mae_best}}</div><div class="l">price forecast error, EUR/MWh (MAE); naive rule {{n:pri_test_mae_naive}}</div></div>
<div class="kpi g"><div class="v">CHF {{n:total_saving_chf_test}}</div><div class="l">simulated saving in the month vs "last week's demand, no battery"</div></div>
</div>

<div class="caveat" markdown="1">

**Read the money with care – these caveats belong next to the number.**

- **Assumed imbalance prices.** Shortage costs p + 0.2·&#124;p&#124;, surplus earns p − 0.2·&#124;p&#124; (p = actual auction price).
  The avoided penalty explains CHF {{n:demand_forecast_part_chf_test}} of the CHF {{n:total_saving_chf_test}} (about {{n:pct_demand_of_saving_test}} %). With half
  the penalty (±10 %) the saving is CHF {{n:imb_11_09_saving}} ({{n:imb_11_09_demand}} demand + {{n:imb_11_09_battery}} battery).
  Swissgrid really settles quarter-hourly with a single price since 2026, so the ranking "demand forecast worth more
  than the battery" is **not** proven for real settlement.
- **One test month.** The 95 % interval is CHF {{n:ciblock_low_test}} to {{n:ciblock_high_test}} when runs of {{n:ci_blocklen}} days are kept together
  (CHF {{n:s4_cilow_test}} to {{n:s4_cihigh_test}} if the days were independent, which they are not).
- **Fictional battery** that never moves the price (price taker).
- **The yearly figure is not a test.** CHF {{n:year_saving}} over {{n:year_days}} days (October 2025 – September 2026) is a sum over
  the period used to tune the decision rules plus the validation month.

</div>

| What | October 2026 |
|---|---|
| Saving of the product vs the simple rule (simulated) | **CHF {{n:total_saving_chf_test}}** = {{n:pct_saving_of_baseline_test}} % of the baseline's total cost (CHF {{n:s1_cost_test}}) |
| … from the better demand forecast (depends on the assumed penalty) | CHF {{n:demand_forecast_part_chf_test}} |
| … from the battery | CHF {{n:battery_part_chf_test}} |
| Share of the saving of the perfect-foresight benchmark (strategy 6, "ceiling") | {{n:pct_ceiling_captured_total_test}} % in total; battery alone {{n:pct_ceiling_battery_value_captured_test}} % |
| Days on which the product was cheaper than the baseline | {{n:s4_cheaper_test}} of {{n:s4_days_test}} |

**The main insight**, under the assumed penalty: a good demand forecast was worth about {{n:ratio_demand_battery_test}} times the battery in
October ({{n:ratio_demand_battery_roll}} times over the rolling period). The battery earns from the gap between cheap and dear hours of the same
day, which is why planning it **hour by hour** inside the blocks mattered (chapter 10).

## What makes the project trustworthy

- **A strict no-future rule.** Every input must be known at 10:00 on day D. An automated test rebuilds features from
  data cut at that time and "poisons" everything later; a reviewer recomputed 966 feature values by hand (chapter 6).
- **One clean test month.** All model and decision choices were made on data before October; October was evaluated
  once. One small weather pre-processing choice saw October weather (not demand or prices) and is disclosed (chapter 12).
- **Independent reviews** of every phase by a different AI model with a fresh context. Every finding is logged with
  the decision taken (chapter 12).
- **Reproducible.** One command rebuilds everything from the raw downloads (not in git; without them every step from the features on still runs, chapter 16); a clean rebuild reproduced the metrics to
  about 1e-14 and the backtest files byte for byte (chapter 3).
