# 2 Business background for non-experts

<div class="inshort" markdown="1">

The national grid operator (TSO) keeps the grid in balance; the city grid operator (DSO) buys the energy its
customers use. It buys most of it one day ahead in an auction that closes at {{c:auction.gate_closure_local}}. Any gap between what was
bought and what was used is an imbalance, settled at a worse price. A battery can buy energy in cheap hours and use
it in dear hours, within limits on power, size, losses and cycles.

</div>

## Who is who

{{img:docs/architecture_tso_dso.svg|From the national grid (TSO) to the city grid (DSO) to homes. The DSO forecasts its demand and buys the energy (`docs/architecture_tso_dso.svg`, drawn by the team). Where the figure says "MWh per 4-hour block", the models actually forecast the **mean MW** of each block (demand) and the **mean EUR/MWh** (price).|92%}}

- The **TSO** (transmission system operator; in Switzerland *Swissgrid*) runs the high-voltage grid and keeps supply
  and demand in balance every second.
- The **DSO** (distribution system operator) runs a city's local grid and supplies its homes and businesses. In this
  project it is the fictional *Limmat Energie AG* for the city of Zurich. Its demand is the **real** grid load that
  ewz, the Zurich utility, publishes every 15 minutes as open data.
- **Homes and businesses** use the energy. They do not appear individually: the data is the total load of the city.

## The day-ahead auction

The DSO buys most of its energy one day ahead on the **day-ahead auction** run by the exchange EPEX SPOT. Every
buyer and seller sends bids for every hour of tomorrow; the exchange sets **one price per hour** for the whole of
Switzerland (one bidding zone, "CH").

- The **Swiss** auction closes at **{{c:auction.gate_closure_local}}** on the day before delivery and publishes results from about 11:10. The
  original project brief assumed 12:00, which is the closing time of the coupled EU auction (Germany, France, Austria,
  Italy), not the Swiss one. This was checked in EPEX SPOT trading brochures from 2020 to 2024
  (`docs/auction_timing.md`).
- Our forecast time is therefore **{{c:auction.forecast_time_local}} on day D**, one hour before gate closure, for delivery on day D+1.
- Side effect: the German and French prices for D+1 are set at 12:00 and published around 12:45, so they are **not**
  known when we forecast. Only their prices for day D are.
- There are two kinds of bid in this project: a **price-independent** bid ("buy this volume at any price") and a
  **limit** bid ("buy this volume only if the price is at or below X").

{{svg:day_timeline|Timeline of one planning day. The forecast is made at 10:00 on day D, bids go in before 11:00, energy flows on D+1 and the imbalance is settled afterwards.}}

## Imbalance

If the DSO later uses more or less energy than it bought, the difference is an **imbalance**. The TSO settles it at an
**imbalance price**. In this project the imbalance price is an **assumption** (`config.yaml`, section `imbalance`):

| Case | What happens | Price per MWh (p = actual auction price of the hour) |
|---|---|---|
| **Shortage** (used more than bought) | the missing energy is bought from the TSO | p + {{n:imb_short_pct}} % × &#124;p&#124; (factor {{c:imbalance.shortage_price_factor}}) |
| **Surplus** (used less than bought) | the extra energy is sold back to the TSO | p − {{n:imb_surplus_pct}} % × &#124;p&#124; (factor {{c:imbalance.surplus_price_factor}}) |

The **absolute value |p|** matters when prices are negative: with a plain "p × 1.2" a shortage at −50 EUR/MWh
would cost −60, i.e. it would *earn* money. With p + 0.2·|p| it costs −40, which is still worse than the auction price.

The real Swiss settlement is different: since 2026 Swissgrid settles every quarter-hour with a single imbalance price,
and a deviation that helps the system can even earn money. That is why every money figure in this report carries the
caveat that the imbalance prices are assumed.

## Battery terms

| Term | Meaning | Value in this project |
|---|---|---|
| **Power** | how fast the battery can charge or discharge (MW). 20 MW for one hour = 20 MWh. | {{c:battery.power_mw}} MW |
| **Capacity** | how much energy fits in (MWh). Capacity ÷ power = "a 2-hour battery". | {{c:battery.capacity_mwh}} MWh |
| **State of charge (SoC)** | energy stored right now, in MWh or % of capacity | allowed between {{n:soc_min_pct}} % and {{n:soc_max_pct}} %, each period starts at {{n:soc_start_pct}} %; each day plans back to {{n:soc_start_pct}} %, the actual end level carries over |
| **Round-trip efficiency** | share of the energy put in that comes out again. Split equally: √0.9 ≈ 0.949 on the way in and on the way out. | {{n:rte_pct}} % |
| **Cycle** | one full use of the battery. **Our definition** (from the project brief): {{n:usable_mwh}} MWh *delivered to the grid* = (90 % − 10 %) × 40 MWh. | at most {{c:battery.max_cycles_per_day}} per day |
| **Wear cost** | a cost per MWh discharged that stands for battery ageing | {{c:battery.wear_cost_eur_per_mwh}} EUR/MWh |
| **Selling back** | whether the DSO may sell energy to the market | not allowed (`allow_sell: false`) |
| **Price taker** | the battery's bids never change the auction price | assumed |

A note on the cycle: because the stored energy loses about {{n:cycle_excess_pct}} % on the way out, emptying the full usable range delivers only
{{n:full_swing_mwh}} MWh to the grid. Capping *delivered* energy at 32 MWh therefore allows about {{n:cycle_excess_pct}} % more than one physical full
cycle. The final review flagged this; it was kept as the brief's definition and disclosed (chapters 9 and 12).

## What the four options mean

The team's diagram names the decision for each block. The code labels every block with one of them
(`label_option` in `src/optimisation/battery_lp.py`):

| Option | Meaning |
|---|---|
| `buy` | only buy what the city needs |
| `buy_and_store` | buy the city's need plus extra energy that goes into the battery |
| `use_storage_and_buy` | cover part of the need from the battery and buy the rest |
| `use_storage` | cover (almost) all of the need from the battery |

Plain "store without buying" cannot happen: the battery can only be filled with bought energy, and the city always
needs energy too.

## A day in numbers

On an average October 2026 day Zurich used {{n:oct_daily_mwh}} MWh. The battery can deliver at most {{n:usable_mwh}} MWh a day, i.e.
{{n:battery_share_of_day}} % of the day. Its value therefore comes from **when** it moves energy (from cheap midday or night hours to the dear evening),
not from how much. The demand forecast, in contrast, touches every MWh of the day: one MW of error over 24 hours is
24 MWh of imbalance.
