# 9 Battery optimiser

<div class="inshort" markdown="1">

For one delivery day the optimiser chooses, for each period (6 blocks or 24 hours), how much to buy, charge and
discharge so that the expected cost is lowest, demand is always covered and the battery stays within its limits. It
is a small mixed-integer program solved exactly with SciPy's HiGHS solver. One yes/no variable per period forbids
charging and discharging at the same time.

</div>

## In plain words

Given tomorrow's forecast need and forecast price for each period, the optimiser asks: *is it worth buying a little
more in a cheap period, storing it, and using it in a dear period?* It is worth it only if the price gap covers the
losses (10 % round trip) and the wear cost ({{c:battery.wear_cost_eur_per_mwh}} EUR per MWh discharged). It must respect the battery's power,
its allowed charge range and at most one cycle per day, and it must plan to end the day at a given **target level**.
In the backtest the target is always the configured {{n:soc_start_pct}} %; the day itself starts wherever the previous day really ended
(see "Start and end level" below).

{{svg:battery_flows|Energy flows of one period. What is bought either goes straight to the city or into the battery; what comes out of the battery replaces purchases.}}

## In small maths

For one delivery day with periods t = 1 … n (length h<sub>t</sub> hours), forecast need D<sub>t</sub> (MWh) and forecast price
P<sub>t</sub> (EUR/MWh), choose buy<sub>t</sub>, ch<sub>t</sub>, dis<sub>t</sub>, soc<sub>t</sub> ≥ 0 and a binary z<sub>t</sub> ∈ {0, 1}:

<div class="note" markdown="1">

**minimise** Σ<sub>t</sub> P<sub>t</sub> · buy<sub>t</sub> + w · Σ<sub>t</sub> dis<sub>t</sub> + 10<sup>−4</sup> · Σ<sub>t</sub> ch<sub>t</sub>  (w = {{c:battery.wear_cost_eur_per_mwh}} EUR/MWh; the last term only breaks ties)

**subject to**

- buy<sub>t</sub> = D<sub>t</sub> + ch<sub>t</sub> − dis<sub>t</sub>  (demand always covered, no selling back)
- soc<sub>t</sub> = soc<sub>t−1</sub> + η · ch<sub>t</sub> − dis<sub>t</sub> / η, with η = √{{c:battery.round_trip_efficiency}} = {{n:eta_one_way}}  (losses on the way in and out)
- {{n:soc_min_mwh}} MWh ≤ soc<sub>t</sub> ≤ {{n:soc_max_mwh}} MWh  ({{n:soc_min_pct}}–{{n:soc_max_pct}} % of {{c:battery.capacity_mwh}} MWh)
- ch<sub>t</sub> ≤ {{c:battery.power_mw}} MW × h<sub>t</sub> × z<sub>t</sub>,  dis<sub>t</sub> ≤ {{c:battery.power_mw}} MW × h<sub>t</sub> × (1 − z<sub>t</sub>)  (power limit; never both)
- Σ<sub>t</sub> dis<sub>t</sub> ≤ {{c:battery.max_cycles_per_day}} × {{n:usable_mwh}} MWh  (at most one cycle per day, see below)
- soc<sub>0</sub> = the given start level; soc<sub>n</sub> = the given end target (if no target is given: soc<sub>n</sub> = soc<sub>0</sub>)

</div>

The code (`solve_battery_plan` in `src/optimisation/battery_lp.py`) stacks these variables into one vector and calls
`scipy.optimize.milp` with `mip_rel_gap = 0`, i.e. it solves to the exact optimum. The tiny extra cost on charging
(1e-4 EUR/MWh) breaks ties so that the battery stays idle when it cannot earn. An optional `allow_sell` adds a sell
variable (off by default; a sensitivity run shows selling changes nothing for this battery). A start level outside
the allowed range raises an error.

## Start and end level

`solve_battery_plan` takes a start level and an optional end target (default: end = start). The backtest
(`plan_day` and `run_strategy` in `src/backtest/run_backtest.py`) uses it like this:

1. Each evaluation period (rolling run, September, October) starts at the configured {{n:soc_start_pct}} % ({{n:soc_start_mwh}} MWh).
2. Every day is planned **back to {{n:soc_start_mwh}} MWh** at its end.
3. The **actual** level after settlement is carried into the next day. If a charge bid did not clear, the day ends
   lower than planned and the next day starts there and plans a refill. Example: in October the product ended
   {{n:soc_ex_day}} at {{n:soc_ex_end}} MWh and started {{n:soc_ex_next}} at {{n:soc_ex_next_start}} MWh; in the test month {{n:soc_off_days_test}} of {{n:s4_days_test}} days ended off target.
4. Only if the target cannot be reached in one day (a very small battery) is it relaxed to "end at today's opening
   level" (`_solve`; flag `soc_target_relaxed`, used on {{n:soc_relaxed_all}} days in the shipped results).

So the daily end level is a **target**, not a guarantee; differences in stock at the end of a period are valued by the
inventory adjustment (chapter 10).

## Why the binary variable

Without z<sub>t</sub>, the problem is a plain linear program, and at **negative prices** the solver would "charge and
discharge at the same time": buying 1 MWh and putting it in, while taking 0.9 out, burns energy through the losses –
and at a negative price, buying more energy *earns* money. The yes/no variable forbids this. This was the first
design decision of the build (Phase 0), together with the move from PuLP/CBC to SciPy/HiGHS after the bundled CBC
binary failed on macOS ARM.

## Why `mip_rel_gap = 0`

The battery saving is tiny next to the whole purchase bill of the city (millions of CHF per month). A default relative
optimality gap of 0.01 % of the bill can be larger than the whole battery saving of a day, so the solver could stop
with a plan that is not really optimal. The backtest reviewer found this; the gap was set to zero and a test with a
large demand bill was added (`test_exact_optimum_with_large_demand_bill`).

## The cycle definition

One cycle is **{{n:usable_mwh}} MWh delivered to the grid** (= soc<sub>max</sub> − soc<sub>min</sub>, the project brief's definition).
Because energy leaves the battery with efficiency {{n:eta_one_way}}, emptying the full usable stored energy delivers only
{{n:full_swing_mwh}} MWh. The rule therefore allows about {{n:cycle_excess_pct}} % more than one physical full cycle. In October the product made
{{n:s4_cycles_test}} cycles by this definition, which is {{n:oct_cycles_full_swings}} full swings of stored energy. The final review (M4) estimated that a
physical cap would lower the October battery saving by about CHF {{n:cycle_cap_cost}}. The brief's definition was **kept** and stated
everywhere (docstring, assumptions, report, app help text).

## Blocks or hours

The function works for any number of periods. The plain plan uses the **six blocks**; the chosen planning mode
`hourly_shape` plans **23/24/25 hours** with an hourly price forecast (chapter 10). Clock-change days simply have 3- or
5-hour blocks (or 23/25 hours).

## Option labels

After solving, every period gets one of the team's labels (`label_option`): charge > 0 → `buy_and_store`; discharge > 0
and buy > 0 → `use_storage_and_buy`; discharge > 0 and buy ≈ 0 → `use_storage`; otherwise `buy`. In hourly mode a block's
label is the label of its sums (net direction decides if a block both charges and discharges).

## Tests

`tests/test_battery_lp.py` (written in Phase 0, extended after reviews):

| Test | What it checks |
|---|---|
| `test_flat_prices_battery_idle` | flat prices → the battery does nothing |
| `test_cheap_night_expensive_evening` | charge at night, discharge in the evening |
| `test_never_exceeds_power_or_capacity` | power and charge limits hold in every period |
| `test_small_spread_battery_idle` | a spread smaller than losses + wear → idle |
| `test_dst_day_with_three_hour_block` | a clock-change day with a 3-hour block works |
| `test_negative_prices_no_simultaneous_charge_and_discharge` | the binary variable works |
| `test_allow_sell_and_low_demand` | the optional sell variable |
| `test_hourly_periods_and_custom_soc` | 24 periods and a custom start/end level |
| `test_labels` | the option labels |
| `test_bad_input` | missing or negative inputs raise errors |
| `test_start_level_outside_limits_is_rejected` | added after review |
| `test_exact_optimum_with_large_demand_bill` | added after review (`mip_rel_gap = 0`) |
