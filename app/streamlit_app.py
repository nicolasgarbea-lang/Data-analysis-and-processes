"""Limmat Energie AG - day-ahead planning app.

Run from the repo root:  streamlit run app/streamlit_app.py
Everything is read from committed files at run time (see app/data.py for the list).
"""
from __future__ import annotations

import base64
import datetime as dt
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from app import charts  # noqa: E402
from app import data as D  # noqa: E402
from app.style import (COLORS, OPTION_WORDS, SPLIT_NAMES, STRATEGY_NAMES, chf,  # noqa: E402
                       layout, mwh, pct)

st.set_page_config(page_title="Limmat Energie - day-ahead planning", layout="wide",
                   initial_sidebar_state="expanded")

PRODUCT = D.rb.PRODUCT
BASELINE = D.rb.BASELINE
CEILING = D.rb.CEILING


def show(fig, key=None):
    st.plotly_chart(fig, width="stretch", theme="streamlit", key=key)


def note(text: str):
    st.caption(text)


# ---------------------------------------------------------------------------
# status notices
# ---------------------------------------------------------------------------
def price_notice(version, where: str = "live"):
    """Clear notice while the price model is not available. Disappears by itself when the
    prediction file (and the regenerated backtest) exist."""
    live = D.sources(version)
    if where == "live" and live.get("price") != "ml":
        st.warning("**Price model not available yet - showing stand-in forecast.** Until "
                   "`reports/predictions_price.parquet` exists, the price forecast is simply "
                   "*the same block on the auction day* (known when we plan). The plan and the bids "
                   "are therefore not the final ones.")
    if where == "live" and live.get("demand") != "ml":
        st.warning("**Demand model not available - showing stand-in forecast** (mean of the same block "
                   "on the same weekday over the last 4 weeks).")
    if where == "backtest":
        bs = D.backtest_sources(version)
        if bs.get("price") == "standin":
            if live.get("price") == "ml":
                st.info("The price model now exists, but the backtest files below were made **before** it "
                        "(stand-in price forecast). They will update when the backtest is re-run.")
            else:
                st.warning("**Price model not available yet - showing stand-in forecast.** The backtest "
                           "below uses the stand-in price forecast (same block on the auction day). Strategies "
                           "with a battery will change once the price model is in.")


# ---------------------------------------------------------------------------
# sidebar
# ---------------------------------------------------------------------------
def sidebar(version) -> dt.date | None:
    p = D.periods()
    dates = D.selectable_dates(version)
    st.sidebar.title("Limmat Energie AG")
    st.sidebar.caption("Day-ahead planning for the city of Zurich with a grid battery")
    if not dates:
        st.sidebar.error("No delivery day with forecasts found.")
        return None
    test_start = D.to_date(p["test_start"])
    default = test_start if test_start in dates else dates[0]
    d = st.sidebar.date_input(
        "Delivery day (D+1)", value=default, min_value=dates[0], max_value=dates[-1], key="day",
        format="DD.MM.YYYY",
        help="September 2026 = validation month (used to choose the model and the decision rules). "
             "October 2026 = test month (never used for any choice).")
    if isinstance(d, (tuple, list)):
        d = d[0] if d else default
    split = D.rb.split_of(d)
    tag = {"test": "test month", "val": "validation month"}.get(split, split)
    st.sidebar.markdown(f"**{d:%A, %d %B %Y}** · {tag}")
    st.sidebar.caption(f"Planned on {d - dt.timedelta(days=1):%d.%m.%Y} at "
                       f"{D.cfg()['auction']['forecast_time_local']} (Swiss time), auction closes at "
                       f"{D.cfg()['auction']['gate_closure_local']}.")
    if d not in dates:
        st.sidebar.error("No complete forecast for this day. Pick another day.")
        return None
    st.sidebar.divider()
    st.sidebar.markdown(
        "**How to read this**\n\n"
        "- A day has 6 **blocks** of 4 hours (00-04 ... 20-24, Swiss local time).\n"
        "- **Demand** = average power the city uses in the block (MW). Energy (MWh) = MW x hours.\n"
        "- **Price** = Swiss day-ahead auction price in EUR per MWh; all costs are shown in CHF.\n"
        "- **Charge level** = energy stored in the battery (MWh).\n"
        "- *What really happened* = the actual values, known only after the day.")
    st.sidebar.divider()
    colors = " ".join(
        f"<span style='color:{COLORS[k]}'>&#9632;</span> {lbl}" for k, lbl in
        [("demand", "demand"), ("price", "price"), ("buy", "buy"), ("charge", "charge"),
         ("discharge", "discharge"), ("soc", "charge level"), ("actual", "actual")])
    st.sidebar.markdown(f"<small>{colors}</small>", unsafe_allow_html=True)
    return d


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def battery_key(params: dict) -> tuple:
    return tuple(sorted((k, float(v)) for k, v in params.items()))


def block_list(names, idx) -> str:
    items = [names[i] for i in idx]
    if not items:
        return ""
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def verdict(pl: pd.DataFrame, exp_saving_chf: float, real_saving_chf: float | None) -> str:
    names = D.block_names()
    ch = pl["charge_mwh"].to_numpy(float)
    dis = pl["discharge_mwh"].to_numpy(float)
    real = "" if real_saving_chf is None else f"; realised {chf(real_saving_chf, signed=True)}"
    if ch.sum() < 0.5 and dis.sum() < 0.5:
        return ("Battery stays idle: the expected price gap between the blocks does not cover the losses and "
                f"the wear. Just buy the forecast demand. Expected saving {chf(exp_saving_chf, True)}{real}.")
    parts = []
    if ch.sum() >= 0.5:
        parts.append(f"Charge {ch.sum():,.0f} MWh in {block_list(names, np.where(ch > 0.5)[0])}")
    if dis.sum() >= 0.5:
        parts.append(f"use {dis.sum():,.0f} MWh in {block_list(names, np.where(dis > 0.5)[0])}")
    s = ", ".join(parts)
    return f"{s[0].upper() + s[1:]}. Expected saving {chf(exp_saving_chf, True)}{real}."


def plan_table(pl: pd.DataFrame) -> pd.DataFrame:
    t = pd.DataFrame({
        "Block": D.block_names()[: len(pl)],
        "Decision": [OPTION_WORDS.get(o, o) for o in pl["option"]],
        "Forecast demand (MWh)": pl["demand_mwh"].round(0),
        "Forecast price (EUR/MWh)": pl["price_eur_mwh"].round(1),
        "Buy at auction (MWh)": pl["buy_mwh"].round(0),
        "Charge (MWh)": pl["charge_mwh"].round(1),
        "Discharge (MWh)": pl["discharge_mwh"].round(1),
        "Charge level at end (MWh)": pl["soc_mwh"].round(1),
        "Charge limit price (EUR/MWh)": pl["charge_limit_eur_mwh"].round(1),
    })
    if "sell_mwh" in pl and pl["sell_mwh"].abs().sum() > 1e-6:
        t.insert(7, "Sell back (MWh)", pl["sell_mwh"].round(1))
    return t


def soc_start_for(date_str: str, version, battery: dict) -> tuple[float, str]:
    """Charge level at the start of the day: carried from the stored backtest (same share
    of capacity for a custom battery, kept inside its limits), else the config start level."""
    default = D.default_battery()
    carried = D.carried_soc(date_str, version)
    if carried is None:
        frac, src = battery["soc_start_frac"], "start level from config.yaml (no backtest value for this day)"
    else:
        frac, src = carried / default["capacity_mwh"], "carried over from the month backtest"
    frac = min(max(frac, battery["soc_min_frac"]), battery["soc_max_frac"])
    return frac * battery["capacity_mwh"], src


# ---------------------------------------------------------------------------
# Tab 1: Tomorrow
# ---------------------------------------------------------------------------
def tab_tomorrow(d: dt.date, version):
    ds = str(d)
    price_notice(version, "live")
    fc = D.day_forecasts(ds, version)
    bat = D.default_battery()
    soc0, soc_src = soc_start_for(ds, version, bat)
    allow_sell = bool(D.cfg()["battery"].get("allow_sell", False))
    try:
        r = D.plan(ds, PRODUCT, battery_key(bat), soc0, allow_sell, version)
        r0 = D.plan(ds, "ml_no_battery", battery_key(bat), soc0, allow_sell, version)
    except Exception as e:  # noqa: BLE001 - show the reason instead of a stack trace
        st.error(f"The plan for {d:%d.%m.%Y} could not be made: {e}")
        return
    pl, at = r["plan"], r["attrs"]
    fx = float(fc["eurchf_known"].iloc[0]) if np.isfinite(fc["eurchf_known"].iloc[0]) else np.nan
    exp_cost = at.get("cost_eur", np.nan) * fx
    exp_saving = at.get("saving_eur", np.nan) * fx
    summ, summ0 = r["summary"], r0["summary"]
    real_saving = None if summ is None or summ0 is None else summ0["total_cost_chf"] - summ["total_cost_chf"]

    st.subheader(f"Plan for {d:%A, %d %B %Y}")
    st.markdown(f"#### {verdict(pl, exp_saving, real_saving)}")
    k = st.columns(5)
    k[0].metric("Energy to buy", mwh(pl["buy_mwh"].sum()),
                help="Total planned purchase at the auction for the day: forecast demand, plus energy "
                     "that goes into the battery, minus energy that comes out of it.")
    k[1].metric("Expected cost", chf(exp_cost),
                help="Planned purchases x forecast prices + battery wear, converted with the last known "
                     "EUR/CHF rate.")
    k[2].metric("Expected battery saving", chf(exp_saving, True),
                help="Expected cost without battery minus expected cost with battery (same forecasts).")
    k[3].metric("Realised cost after settlement", chf(None if summ is None else summ["total_cost_chf"]),
                delta=None if real_saving is None else f"{chf(real_saving, True)} battery saving",
                delta_color="normal",
                help="What the day really cost: auction purchases at the real prices + imbalance + wear. "
                     "Battery saving = same ML demand forecast without battery, minus this.")
    k[4].metric("Imbalance cost", chf(None if summ is None else summ["imbalance_penalty_chf"]),
                help="Extra cost because actual demand differed from what we bought: shortfalls are bought "
                     f"at {D.cfg()['imbalance']['shortage_price_factor']:g} x the price, surpluses sold at "
                     f"{D.cfg()['imbalance']['surplus_price_factor']:g} x the price (assumed rule).")
    note(f"Battery {bat['power_mw']:g} MW / {bat['capacity_mwh']:g} MWh; charge level at the start of the day "
         f"{soc0:,.1f} MWh ({soc_src}). Decision rules: {r['decision']}.")

    st.divider()
    show_actual = st.toggle("Show what really happened", value=True, key="show_actual")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Demand forecast** (average MW per block)")
        show(charts.forecast_chart(fc, "demand_mw", "demand_q10", "demand_q90", "actual_demand_mw",
                                   COLORS["demand"], "Average demand (MW)", "Demand", show_actual, "MW"),
             key="fc_demand")
        mae = np.nanmean(np.abs(fc["demand_mw"] - fc["actual_demand_mw"]))
        note("The band shows where the real value should fall 8 times out of 10. "
             + (f"On this day the forecast was off by {mae:,.1f} MW on average." if show_actual else ""))
    with c2:
        st.markdown("**Price forecast** (Swiss day-ahead, EUR/MWh)")
        show(charts.forecast_chart(fc, "price", "price_q10", "price_q90", "actual_price", COLORS["price"],
                                   "Price (EUR/MWh)", "Price", show_actual, "EUR/MWh"), key="fc_price")
        mae_p = np.nanmean(np.abs(fc["price"] - fc["actual_price"]))
        note("The battery earns money from the gap between cheap and expensive blocks, so the order of the "
             "blocks matters more than the level. "
             + (f"Average error on this day: {mae_p:,.1f} EUR/MWh." if show_actual else ""))

    st.divider()
    st.markdown("**The plan per block**")
    c1, c2 = st.columns(2)
    with c1:
        show(charts.battery_chart(pl, D.block_names(), soc0, bat["soc_min_frac"] * bat["capacity_mwh"],
                                  bat["soc_max_frac"] * bat["capacity_mwh"]), key="plan_battery")
        note("Bars up = energy put into the battery, bars down = energy taken out for the city. "
             "The line is the charge level at the end of each block.")
    with c2:
        show(charts.buy_chart(pl, D.block_names()), key="plan_buy")
        note("Grey bars = what we buy at the auction. Blue marks = forecast demand. Buying above the mark "
             "means storing, below it means using the battery.")
    st.markdown("**Decision per block** - *buy* (only what the city needs) · *buy and store* (extra energy "
                "into the battery) · *use storage and buy* (part from the battery) · *use storage* (all from the "
                "battery)")
    st.dataframe(plan_table(pl), hide_index=True, width="stretch")
    note("Charge limit price = the highest price at which the extra energy for the battery is still bought. "
         "If the auction price is higher, the charge bid does not clear and the battery is not filled.")

    pp, ppa = r["plan_periods"], r["plan_periods_attrs"]
    with st.expander("Hourly plan"):
        hourly = r["hourly"]
        lbl = [f"{pd.Timestamp(t):%H:%M}" for t in hourly["local_time"]]
        if ppa.get("plan_resolution") == "hourly" and len(pp) == len(hourly):
            show(charts.battery_chart(pp, lbl, soc0, bat["soc_min_frac"] * bat["capacity_mwh"],
                                      bat["soc_max_frac"] * bat["capacity_mwh"],
                                      x_title="Hour of the delivery day (Swiss local time)", height=320),
                 key="plan_hourly")
            note("The optimiser plans the single hours (tuned rule); the block view above sums them up.")
        ht = pd.DataFrame({
            "Hour (local)": lbl,
            "Block": [D.block_names()[b] for b in hourly["block"]],
            "Forecast need (MWh)": hourly["need_mwh"].round(1),
            "Planned discharge (MWh)": hourly["planned_discharge_mwh"].round(1),
            "Demand bid (MWh)": hourly["demand_bid_mwh"].round(1),
            "Charge bid (MWh)": hourly["charge_bid_mwh"].round(1),
            "Charge limit (EUR/MWh)": hourly["charge_limit_eur_mwh"].round(1),
            "Decision": [OPTION_WORDS.get(o, o) for o in hourly["option"]],
        })
        st.dataframe(ht, hide_index=True, width="stretch")
        stt = r["settlement"]
        if stt is not None:
            st.markdown("**Settlement with the real prices and demand**")
            st.dataframe(pd.DataFrame({
                "Hour (local)": lbl,
                "Actual price (EUR/MWh)": stt["actual_price_eur_mwh"].round(1),
                "Actual demand (MWh)": stt["actual_demand_mwh"].round(1),
                "Charge bid cleared (MWh)": stt["charge_cleared_mwh"].round(1),
                "Discharged (MWh)": stt["discharged_mwh"].round(1),
                "Charge level (MWh)": stt["soc_end_mwh"].round(1),
                "Shortfall (MWh)": stt["shortage_mwh"].round(1),
                "Surplus (MWh)": stt["surplus_mwh"].round(1),
                "Total cost (CHF)": stt["total_cost_chf"].round(0),
            }), hide_index=True, width="stretch")

    st.markdown("**Hourly auction bids** (what we send to the exchange before gate closure)")
    bids = r["bids"]
    st.dataframe(bids, hide_index=True, width="stretch", height=320)
    st.download_button("Download bids as CSV", bids.to_csv(index=False).encode("utf-8"),
                       file_name=f"bids_{ds}.csv", mime="text/csv", key="dl_bids")
    note("Demand bids are price-independent (the city must be supplied). Charge bids carry a limit price "
         "('market' = no limit, '-' = no charge bid). Times are Swiss local time with the UTC offset.")


# ---------------------------------------------------------------------------
# Tab 2: Battery settings
# ---------------------------------------------------------------------------
def tab_battery(d: dt.date, version):
    ds = str(d)
    base = D.default_battery()
    st.subheader("Try another battery")
    st.markdown("Move the sliders: the plan for the selected day is re-calculated at once and compared "
                "with the default battery.")
    c = st.columns(4)
    power = c[0].slider("Power (MW)", 1.0, 100.0, float(base["power_mw"]), 1.0, key="bat_power",
                        help="How fast the battery can charge or discharge.")
    cap = c[1].slider("Capacity (MWh)", 2.0, 200.0, float(base["capacity_mwh"]), 2.0, key="bat_cap",
                      help="How much energy it can hold.")
    eff = c[2].slider("Round-trip efficiency (%)", 70, 100, int(round(base["round_trip_efficiency"] * 100)), 1,
                      key="bat_eff", help="Share of the stored energy you get back out.")
    wear = c[3].slider("Wear cost (EUR per MWh discharged)", 0.0, 30.0, float(base["wear_cost_eur_per_mwh"]), 0.5,
                       key="bat_wear", help="Ageing of the battery: every MWh taken out costs this much.")
    c = st.columns(4)
    lo, hi = c[0].slider("Usable charge level (% of capacity)", 0, 100,
                         (int(round(base["soc_min_frac"] * 100)), int(round(base["soc_max_frac"] * 100))), 5,
                         key="bat_range", help="The battery is kept between these levels to protect it.")
    cyc = c[1].slider("Max full cycles per day", 0.5, 3.0, float(base["max_cycles_per_day"]), 0.5, key="bat_cyc",
                      help="One cycle = the usable capacity once in and out.")
    allow_sell = c[2].checkbox("Allow selling back to the market", value=bool(D.cfg()["battery"].get("allow_sell")),
                               key="bat_sell", help="If on, the battery may also sell energy at the auction.")
    if hi <= lo:
        st.error("The maximum charge level must be above the minimum.")
        return
    custom = dict(base, power_mw=power, capacity_mwh=cap, round_trip_efficiency=eff / 100.0,
                  wear_cost_eur_per_mwh=wear, soc_min_frac=lo / 100.0, soc_max_frac=hi / 100.0,
                  max_cycles_per_day=cyc)
    custom["soc_start_frac"] = min(max(base["soc_start_frac"], custom["soc_min_frac"]), custom["soc_max_frac"])
    fc = D.day_forecasts(ds, version)
    fx = float(fc["eurchf_known"].iloc[0])
    cols = st.columns(2)
    default_sell = bool(D.cfg()["battery"].get("allow_sell", False))
    for col, (title, b, sell) in zip(cols, [("Default battery", base, default_sell),
                                            ("Your battery", custom, allow_sell)]):
        with col:
            soc0, _ = soc_start_for(ds, version, b)
            try:
                r = D.plan(ds, PRODUCT, battery_key(b), soc0, sell, version)
                r0 = D.plan(ds, "ml_no_battery", battery_key(b), soc0, sell, version)
            except Exception as e:  # noqa: BLE001
                st.error(f"{title}: no plan possible ({e})")
                continue
            at = r["attrs"]
            st.markdown(f"**{title}** - {b['power_mw']:g} MW / {b['capacity_mwh']:g} MWh, "
                        f"{b['round_trip_efficiency'] * 100:.0f}% efficiency")
            real = None if r["summary"] is None else r0["summary"]["total_cost_chf"] - r["summary"]["total_cost_chf"]
            m = st.columns(2)
            m[0].metric("Expected saving (day)", chf(at.get("saving_eur", np.nan) * fx, True))
            m[1].metric("Realised saving (day)", chf(real, True))
            show(charts.battery_chart(r["plan"], D.block_names(), soc0, b["soc_min_frac"] * b["capacity_mwh"],
                                      b["soc_max_frac"] * b["capacity_mwh"], height=320), key=f"bat_{title}")
            st.caption(verdict(r["plan"], at.get("saving_eur", np.nan) * fx, real))
    note("Saving = cost with the same ML demand forecast but no battery, minus cost with the battery. "
         "The charge level at the start of the day is the backtest value (same share of capacity for your "
         "battery, kept inside its limits).")

    st.divider()
    st.markdown("**Whole test month with your battery**")
    key = (battery_key(custom), allow_sell)
    if st.button("Re-run the whole month with these settings", key="month_btn", type="primary"):
        with st.spinner("Running 31 days x 4 strategies ..."):
            try:
                st.session_state["month_result"] = (key, D.month_rerun(key[0], allow_sell, version))
            except Exception as e:  # noqa: BLE001
                st.error(f"Month run failed: {e}")
    res = st.session_state.get("month_result")
    if res is not None and res[0] == key:
        summ = res[1]
        summ = summ[summ["split"] == "test"] if "test" in set(summ["split"]) else summ
        ref = D.read_csv("backtest_summary.csv", version)
        ref = None if ref is None else ref[ref["split"] == "test"].set_index("strategy")
        rows = []
        for _, rr in summ.iterrows():
            s = rr["strategy"]
            rows.append({
                "Strategy": STRATEGY_NAMES.get(s, s),
                "Saving vs baseline, your battery (CHF)": rr.get("saving_vs_baseline_adj_chf"),
                "Saving vs baseline, default battery (CHF)": (ref.loc[s, "saving_vs_baseline_adj_chf"]
                                                              if ref is not None and s in ref.index else np.nan),
                "Battery value, your battery (CHF)": rr.get("battery_value_adj_chf"),
                "% of best possible": rr.get("pct_perfect_captured"),
            })
        t = pd.DataFrame(rows)
        st.dataframe(t, hide_index=True, width="stretch", column_config={
            c: st.column_config.NumberColumn(format="localized") for c in t.columns if c != "Strategy"})
        prod = summ[summ["strategy"] == PRODUCT]
        if len(prod):
            st.success(f"With your battery our product saves **{chf(prod['saving_vs_baseline_adj_chf'].iloc[0], True)}** "
                       f"in the test month compared with the baseline; the battery alone adds "
                       f"{chf(prod['battery_value_adj_chf'].iloc[0], True)}.")
        note("'Battery value' = saving of the strategy compared with the same demand forecast without battery. "
             "Numbers include the inventory adjustment (energy left in the battery at the end of the month).")
    else:
        note("Runs the product, the baseline, ML without battery and the best possible plan for every day of "
             "October (a few seconds).")


# ---------------------------------------------------------------------------
# Tab 3: Month backtest
# ---------------------------------------------------------------------------
def tab_month(version):
    price_notice(version, "backtest")
    summ = D.read_csv("backtest_summary.csv", version)
    daily = D.read_csv("backtest.csv", version)
    if summ is None or daily is None:
        st.info("The backtest files (reports/backtest_summary.csv, reports/backtest.csv) do not exist yet.")
        return
    splits = [s for s in ["test", "val", "rolling"] if s in set(summ["split"])]
    split = st.radio("Period", splits, format_func=lambda s: SPLIT_NAMES.get(s, s), horizontal=True,
                     key="bt_split")
    if split == "rolling":
        st.info("**Robustness check.** The rolling year re-plans every day from October 2025 to August 2026 "
                "with models that are refitted monthly. It shows whether the result holds outside one month.")
    s = summ[summ["split"] == split].copy()
    s["order"] = s["strategy"].map({k: i for i, k in enumerate(STRATEGY_NAMES)})
    s = s.sort_values("order")
    t = pd.DataFrame({
        "Strategy": s["strategy"].map(lambda x: STRATEGY_NAMES.get(x, x)),
        "Days": s["days"],
        "Total cost (CHF)": s["total_cost_adj_chf"],
        "Saving vs baseline (CHF)": s["saving_vs_baseline_adj_chf"],
        "95% interval (CHF)": [f"{a:,.0f} to {b:,.0f}" for a, b in zip(s["saving_adj_ci_low_chf"],
                                                                    s["saving_adj_ci_high_chf"])],
        "% of perfect foresight": s["pct_perfect_captured"],
        "Of which battery (CHF)": s["battery_value_adj_chf"],
        "Imbalance cost (CHF)": s["imbalance_penalty_chf"],
        "Days cheaper than baseline": s["days_cheaper_than_baseline"],
    })
    st.dataframe(t, hide_index=True, width="stretch", column_config={
        "Total cost (CHF)": st.column_config.NumberColumn(format="localized"),
        "Saving vs baseline (CHF)": st.column_config.NumberColumn(format="localized"),
        "% of perfect foresight": st.column_config.NumberColumn(format="%.0f%%"),
        "Of which battery (CHF)": st.column_config.NumberColumn(format="localized"),
        "Imbalance cost (CHF)": st.column_config.NumberColumn(format="localized"),
    })
    prod = s[s["strategy"] == PRODUCT]
    if len(prod):
        p0 = prod.iloc[0]
        st.markdown(f"**Our product saves {chf(p0['saving_vs_baseline_adj_chf'], True)}** over {int(p0['days'])} days "
                    f"(95% interval {chf(p0['saving_adj_ci_low_chf'], True)} to {chf(p0['saving_adj_ci_high_chf'], True)}), "
                    f"that is **{pct(p0['pct_perfect_captured'])} of what perfect foresight could save**.")
    note("Baseline = buy last week's demand of the same block, no battery. Perfect foresight = knowing the "
         "real demand and prices in advance (hourly plan) - the best possible result, not reachable in practice. "
         "95% interval = range of the saving when the days are re-sampled (bootstrap). Costs include the "
         "inventory adjustment: energy left in the battery at the end is valued at the period's mean price.")

    st.markdown("**Saving over time**")
    dd = daily[daily["split"] == split]
    show(charts.cumulative_chart(dd, ["ml_no_battery", "naive_battery", PRODUCT, CEILING]), key="bt_cum")
    note("Each line adds up the daily saving against the baseline (without inventory adjustment). A steady "
         "climb means the saving comes from many days, not one lucky day. The perfect-foresight line moves "
         "energy between days, so only its end point is meaningful.")

    dec = D.read_csv("backtest_decomposition.csv", version)
    if dec is not None and split in set(dec["split"]):
        row = dec[dec["split"] == split].iloc[0]
        st.markdown("**Where does the saving come from?**")
        show(charts.decomposition_chart(row), key="bt_dec")
        note(f"Of the total saving of {chf(row['total_saving_chf'], True)}, "
             f"{chf(row['demand_forecast_part_chf'], True)} come from the better demand forecast (less imbalance) and "
             f"{chf(row['battery_part_chf'], True)} from the battery. The best possible battery would add "
             f"{chf(row['ceiling_battery_value_chf'], True)}; we capture {pct(row['pct_ceiling_battery_value_captured'])} of it.")

    c1, c2 = st.columns(2)
    with c1:
        bs = D.read_csv("backtest_battery_sensitivity.csv", version)
        st.markdown("**Bigger or smaller battery** (test month)")
        if bs is not None:
            show(charts.battery_size_chart(bs), key="bt_size")
            note("Saving from the battery alone for different sizes (all 2-hour batteries). The value grows less "
                 "than the size: the biggest price gaps of a day are used first."
                 + (" This sensitivity is computed for October only." if split != "test" else ""))
    with c2:
        pe = D.read_csv("backtest_price_error_sensitivity.csv", version)
        st.markdown("**How much does a price forecast error cost?** (test month)")
        if pe is not None:
            show(charts.price_error_chart(pe), key="bt_perr")
            note("We add random errors to the real prices and plan with them: the bigger the error, the more of the "
                 "battery saving is lost. The marked points show the real forecasts."
                 + (" This sensitivity is computed for October only." if split != "test" else ""))
    ds_ = D.read_csv("backtest_decision_sensitivity.csv", version)
    if ds_ is not None:
        with st.expander("More sensitivity runs (imbalance prices, charge limit, wear cost, selling back)"):
            st.dataframe(ds_, hide_index=True, width="stretch")
            note("Test month. 'imbalance_factors' changes the assumed penalty for being off; the other rows change "
                 "one decision rule at a time.")


# ---------------------------------------------------------------------------
# Tab 4: Drivers
# ---------------------------------------------------------------------------
MODEL_NAMES = {"naive": "1 Naive (copy a past value)", "linear": "2 Linear regression",
               "rf": "3 Random forest", "gbm": "4 Gradient boosting (LightGBM)", "best": "5 Best model (final)"}


def ladder_table(m: pd.DataFrame) -> pd.DataFrame:
    a = m[m["block"].astype(str) == "all"].copy()
    rows = []
    for split in ["val", "test", "rolling"]:
        g = a[a["split"] == split].set_index("model")
        if g.empty:
            continue
        naive = g["mae"].get("naive", np.nan)
        for mod in MODEL_NAMES:
            if mod in g.index:
                rows.append({"Period": SPLIT_NAMES.get(split, split).split(" (")[0],
                             "Model": MODEL_NAMES[mod], "MAE": g.loc[mod, "mae"], "RMSE": g.loc[mod, "rmse"],
                             "MAPE / sMAPE (%)": g.loc[mod, "mape_or_smape"], "Bias": g.loc[mod, "bias"],
                             "Better than naive (%)": 100 * (1 - g.loc[mod, "mae"] / naive) if naive else np.nan})
    return pd.DataFrame(rows).round(2)


@st.cache_data(show_spinner=False)
def driver_data(version):
    f = D.features_small(version)
    f = f[f["demand_mw"].notna()].copy()
    f["date"] = pd.to_datetime(f["delivery_date"])
    return f


def tab_drivers(version):
    st.subheader("What drives demand and price")
    st.markdown("**Permutation importance**: we shuffle one input at a time and measure how much worse the "
                "forecast gets. The bigger the bar, the more the model relies on that input.")
    c1, c2 = st.columns(2)
    for col, target, unit, color in [(c1, "demand", "MW", COLORS["demand"]), (c2, "price", "EUR/MWh", COLORS["price"])]:
        with col:
            st.markdown(f"**{target.capitalize()} model**")
            imp = D.read_csv(f"importance_{target}.csv", version)
            if imp is None:
                st.info(f"The {target} model is not available yet - its importance will appear here once "
                        f"`reports/importance_{target}.csv` exists.")
                continue
            show(charts.importance_chart(imp, color, unit), key=f"imp_{target}")
            grp = D.read_csv(f"importance_groups_{target}.csv", version)
            if grp is not None:
                with st.expander("Importance by group of inputs"):
                    show(charts.importance_chart(grp, color, unit, n=20), key=f"impg_{target}")
            notes = D.read_text(f"reports/model_notes_{target}.md")
            if notes:
                with st.expander(f"Full notes of the {target} model (what was tried, limitations)"):
                    st.markdown(notes)
            if target == "demand":
                note("Past demand (same block on the last known day) dominates, then weekday and holidays, "
                     "then weather (mainly solar radiation). EVs and events add nothing measurable to the "
                     "4-hour city load - see the notes below each chart further down.")
    st.markdown("**Model ladder** - from the simplest rule to the final model (error per block)")
    c1, c2 = st.columns(2)
    for col, target, unit in [(c1, "demand", "MW"), (c2, "price", "EUR/MWh")]:
        with col:
            m = D.read_csv(f"metrics_{target}.csv", version)
            st.markdown(f"**{target.capitalize()}** (MAE, RMSE, bias in {unit})")
            if m is None:
                st.info(f"`reports/metrics_{target}.csv` does not exist yet.")
                continue
            st.dataframe(ladder_table(m), hide_index=True, width="stretch")
    note("MAE = average absolute error; RMSE punishes large errors more; bias = average over- (+) or "
         "under-forecast (-). Validation = September 2026 (used to choose), test = October 2026 (untouched).")

    st.divider()
    st.markdown("### The data behind it")
    f = driver_data(version)
    names = D.block_names()
    recent = f[f["date"] >= f["date"].max() - pd.Timedelta(days=3 * 365)]

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Demand vs temperature** (last 3 years)")
        fig = go.Figure()
        sample = recent.dropna(subset=["temp_c_obs"]).sample(min(3000, len(recent)), random_state=1)
        fig.add_trace(go.Scattergl(x=sample["temp_c_obs"], y=sample["demand_mw"], mode="markers",
                                   marker=dict(size=4, color=COLORS["actual"], opacity=0.25),
                                   name="single blocks", hoverinfo="skip"))
        pal = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#6250d6"]
        for b in range(6):
            g = recent[(recent["block"] == b)].dropna(subset=["temp_c_obs"])
            x, y = charts.binned_line(g["temp_c_obs"], g["demand_mw"], np.arange(-15, 37, 2))
            fig.add_trace(go.Scatter(x=x, y=y, mode="lines", name=names[b], line=dict(color=pal[b], width=2),
                                     hovertemplate="%{x:.0f} °C: %{y:,.0f} MW"))
        show(layout(fig, "Observed temperature (°C)", "Average demand (MW)", height=380, hover="closest"),
             key="drv_temp")
        note("Lines = average demand per 2 °C step for each block. Demand is lowest at mild temperatures (about 15-20 °C), rises on cold days "
             "(heating, heat pumps) and rises again on hot days (cooling). Daytime blocks sit far above the night.")
    with c2:
        st.markdown("**Midday demand vs solar radiation** (block 12-16, working days)")
        g = recent[(recent["block"] == 3) & (recent["is_working_day"] == 1)].dropna(subset=["radiation_wm2_obs"])
        fig = go.Figure()
        fig.add_trace(go.Scattergl(x=g["radiation_wm2_obs"], y=g["demand_mw"], mode="markers",
                                   marker=dict(size=5, color=COLORS["demand"], opacity=0.35), name="working days",
                                   hovertemplate="%{x:.0f} W/m²: %{y:,.0f} MW<extra></extra>"))
        x, y = charts.binned_line(g["radiation_wm2_obs"], g["demand_mw"], np.arange(0, 1001, 50))
        fig.add_trace(go.Scatter(x=x, y=y, mode="lines", name="average", line=dict(color=COLORS["discharge"], width=2)))
        show(layout(fig, "Observed solar radiation, block mean (W/m²)", "Average demand 12-16 (MW)", height=380,
                    hover="closest"), key="drv_rad")
        note("Sunny afternoons have lower grid demand: rooftop solar covers part of the use behind the meter, and "
             "less light is needed. Part of the effect is the season (sunny days are also warm days).")

    c1, c2 = st.columns(2)
    ev = f.drop_duplicates("delivery_date")[["date", "ev_count_city"]].dropna()
    night = f[f["block"] == 0].set_index("date")["demand_mw"].resample("MS").mean()
    with c1:
        st.markdown("**Electric cars registered in Zurich**")
        fig = go.Figure(go.Scatter(x=ev["date"], y=ev["ev_count_city"], mode="lines",
                                   line=dict(color=COLORS["charge"], width=2), name="EVs",
                                   hovertemplate="%{y:,.0f} cars"))
        show(layout(fig, "Date", "Electric cars (count, as known at forecast time)", height=300, legend=False),
             key="drv_ev")
    with c2:
        st.markdown("**Night demand (00-04), monthly mean**")
        fig = go.Figure(go.Scatter(x=night.index, y=night.values, mode="lines",
                                   line=dict(color=COLORS["demand"], width=2), name="night demand",
                                   hovertemplate="%{y:,.0f} MW"))
        show(layout(fig, "Month", "Average demand 00-04 (MW)", height=300, legend=False), key="drv_night")
    note("The number of EVs grows steadily, but night demand shows no matching rise - it moves with the seasons. "
         "The model found **no measurable effect of the EV inputs**: their slow trend is already contained in "
         "recent demand, and removing them did not make the forecast worse.")

    h = D.hourly_actuals()
    days = f.drop_duplicates("delivery_date").set_index("delivery_date")
    last2 = h[pd.to_datetime(h["delivery_date"]) >= pd.to_datetime(f["date"].max()) - pd.Timedelta(days=730)].copy()
    hol = days["is_holiday"].astype(bool)
    wkd = days["is_weekend"].astype(bool)
    last2["daytype"] = np.where(last2["delivery_date"].map(hol).fillna(False), "Public holiday",
                                np.where(last2["delivery_date"].map(wkd).fillna(False), "Weekend", "Working day"))
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Average day: working day vs weekend vs public holiday** (last 2 years)")
        prof = last2.groupby(["daytype", "hour_local"])["demand_mw"].mean().reset_index()
        fig = go.Figure()
        for dtp, col in [("Working day", COLORS["demand"]), ("Weekend", COLORS["price"]),
                         ("Public holiday", COLORS["charge"])]:
            g = prof[prof["daytype"] == dtp]
            fig.add_trace(go.Scatter(x=g["hour_local"], y=g["demand_mw"], mode="lines", name=dtp,
                                     line=dict(color=col, width=2), hovertemplate="%{y:,.0f} MW"))
        show(layout(fig, "Hour of the day (Swiss local time)", "Average demand (MW)", height=340), key="drv_prof")
        note("Offices and shops make working days much higher in the daytime. Public holidays look like Sundays - "
             "that is why the holiday inputs matter so much for the model.")
    with c2:
        st.markdown("**Street Parade vs normal Saturdays**")
        sat = days[(days["weekday"] == 5) & (~hol)]
        sp = sat[(sat["event_size"] >= 3) & (sat["month"] == 8)].index
        if len(sp):
            others = [x for x in sat.index if x not in set(sp) and sat.loc[x, "event_size"] == 0
                      and any(abs((x - p).days) <= 21 for p in sp)]
            hh = h[h["delivery_date"].isin(set(sp) | set(others))].copy()
            hh["kind"] = np.where(hh["delivery_date"].isin(set(sp)), "Street Parade day", "Other Saturdays (±3 weeks)")
            prof = hh.groupby(["kind", "hour_local"])["demand_mw"].mean().reset_index()
            fig = go.Figure()
            for kind, col in [("Other Saturdays (±3 weeks)", COLORS["actual"]), ("Street Parade day", COLORS["price"])]:
                g = prof[prof["kind"] == kind]
                fig.add_trace(go.Scatter(x=g["hour_local"], y=g["demand_mw"], mode="lines", name=kind,
                                         line=dict(color=col, width=2), hovertemplate="%{y:,.0f} MW"))
            show(layout(fig, "Hour of the day (Swiss local time)", "Average demand (MW)", height=340),
                 key="drv_sp")
            note(f"Average over {len(sp)} Street Parade Saturdays and {len(others)} other Saturdays around them. "
                 "Even an event with almost a million visitors barely changes the city's total load - the model "
                 "found no measurable effect of events.")
        else:
            st.info("No Street Parade day in the feature table.")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**School holidays vs school weeks** (working days in October)")
        octo = f[(f["month"] == 10) & (f["is_working_day"] == 1)]
        g = octo.groupby(["is_school_holiday", "block"])["demand_mw"].mean().reset_index()
        fig = go.Figure()
        for v, lbl, col in [(0, "School weeks", COLORS["actual"]), (1, "Autumn school holidays", COLORS["demand"])]:
            gg = g[g["is_school_holiday"] == v]
            fig.add_trace(go.Bar(x=[names[b] for b in gg["block"]], y=gg["demand_mw"], name=lbl, marker_color=col,
                                 hovertemplate="%{y:,.0f} MW"))
        fig.update_layout(barmode="group")
        show(layout(fig, "Block (Swiss local time)", "Average demand (MW)", height=320), key="drv_school")
        note("During the autumn school holidays many families are away, so daytime demand is a little lower than "
             "in school weeks of the same month.")
    with c2:
        st.markdown("**Price by block and month**")
        years = sorted(f["date"].dt.year.unique())
        yr = st.selectbox("Year", years[::-1], index=0, key="heat_year")
        g = f[f["date"].dt.year == yr].pivot_table(index="month", columns="block", values="price_eur_mwh",
                                                   aggfunc="mean")
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        fig = go.Figure(go.Heatmap(z=g.values, x=[names[b] for b in g.columns], y=[months[m - 1] for m in g.index],
                                   colorscale="Oranges", colorbar=dict(title="EUR/MWh"),
                                   hovertemplate="%{y} %{x}: %{z:,.0f} EUR/MWh<extra></extra>"))
        fig.update_yaxes(autorange="reversed")
        show(layout(fig, "Block (Swiss local time)", "Month", height=320, legend=False, hover="closest"),
             key="drv_heat")
        note("From spring to autumn the 12-16 block is the cheapest (solar power across Europe), in winter the night. "
             "The evening (16-20, in summer 20-24) is the most expensive. These gaps are what the battery uses.")

    c1, c2 = st.columns(2)
    day = f.groupby("delivery_date").apply(
        lambda g: pd.Series({"price": np.average(g["price_eur_mwh"], weights=g["hours_in_block"])
                             if g["price_eur_mwh"].notna().all() else np.nan,
                             "gas": g["gas_ttf_d_1"].iloc[0] if "gas_ttf_d_1" in g else np.nan,
                             "ref": g["price_mean_last_28d"].iloc[0] if "price_mean_last_28d" in g else np.nan}),
        include_groups=False)
    wind_cols = [c for c in f.columns if c.startswith("eu_wind100_ms_de_")]
    if wind_cols:
        day["wind"] = f.drop_duplicates("delivery_date").set_index("delivery_date")[wind_cols].mean(axis=1)
    day.index = pd.to_datetime(day.index)
    with c1:
        st.markdown("**Swiss price vs German wind forecast** (daily)")
        if wind_cols:
            g = day.assign(dev=day["price"] - day["ref"]).dropna(subset=["wind", "dev"])
            g = g[g.index >= g.index.max() - pd.Timedelta(days=730)]
            fig = go.Figure()
            fig.add_trace(go.Scattergl(x=g["wind"], y=g["dev"], mode="markers",
                                       marker=dict(size=5, color=COLORS["price"], opacity=0.4), name="days",
                                       hovertemplate="%{x:.1f} m/s: %{y:+,.0f} EUR/MWh<extra></extra>"))
            x, y = charts.binned_line(g["wind"], g["dev"], np.arange(0, 20, 1))
            fig.add_trace(go.Scatter(x=x, y=y, mode="lines", name="average", line=dict(color=COLORS["soc"], width=2)))
            show(layout(fig, "Forecast wind speed at 100 m, northern/central Germany (m/s)",
                        "Day price minus mean of the last 4 weeks (EUR/MWh)", height=360, hover="closest"),
                 key="drv_wind")
            note("Windy days in Germany push cheap power into the European grid: the Swiss price is then below its "
                 "recent level, calm days are above it. We compare with the last 4 weeks because windy days are "
                 "mostly winter days, when power is expensive anyway - the raw prices alone show almost no link. "
                 "Last 2 years, wind forecasts known at planning time.")
    with c2:
        st.markdown("**Swiss price vs gas price** (monthly means)")
        mo = day.dropna(subset=["gas", "price"]).resample("MS").mean()
        fig = go.Figure(go.Scatter(x=mo["gas"], y=mo["price"], mode="markers",
                                   marker=dict(size=9, color=mo.index.year, colorscale="Blues", showscale=True,
                                               colorbar=dict(title="Year"), line=dict(width=1, color="white")),
                                   text=[f"{t:%b %Y}" for t in mo.index], name="months",
                                   hovertemplate="%{text}: gas %{x:.0f}, power %{y:.0f} EUR/MWh<extra></extra>"))
        show(layout(fig, "Gas price TTF, last known close (EUR/MWh)", "Swiss price, monthly mean (EUR/MWh)",
                    height=360, legend=False, hover="closest"), key="drv_gas")
        note("Gas plants often set the European power price, so the Swiss price moves with the gas price - "
             "most visibly in the 2022 energy crisis (the points far top right).")


# ---------------------------------------------------------------------------
# Tab 5: Data and method
# ---------------------------------------------------------------------------
def md_section(text: str | None, heading: str) -> str | None:
    if not text:
        return None
    m = re.search(rf"^##\s+{re.escape(heading)}\s*$(.*?)(?=^---|^##\s)", text, flags=re.M | re.S)
    return m.group(1).strip() if m else None


def tab_method(version):
    c = D.cfg()
    st.subheader("The business case")
    st.markdown(
        "**Limmat Energie AG** is a fictional distribution system operator (DSO) that supplies the city of Zurich. "
        "It sits below the national grid operator (TSO, Swissgrid) and above the homes and businesses it "
        "supplies. For its demand we use the real grid load of the city of Zurich (ewz open data). Every day it "
        "buys tomorrow's electricity at the **Swiss day-ahead auction** (EPEX SPOT, one price for all of "
        f"Switzerland). It owns a fictional grid battery of **{c['battery']['power_mw']:g} MW / "
        f"{c['battery']['capacity_mwh']:g} MWh**.\n\n"
        "**The daily question:** for each of the 6 four-hour blocks of tomorrow - how much do we buy, how much do "
        "we store, when do we use the stored energy, and at what price do we bid?")
    st.markdown("**Decision timeline**")
    tl = st.columns(4)
    tl[0].markdown(f"**Day D, {c['auction']['forecast_time_local']}**  \nForecast demand and price for the 6 blocks "
                   "of tomorrow, using only what is known now.")
    tl[1].markdown("**Day D, before the gate closes**  \nPlan the battery, turn the plan into hourly bids "
                   "(volume + limit price).")
    tl[2].markdown(f"**Day D, {c['auction']['gate_closure_local']}**  \nGate closure of the Swiss auction; results "
                   "follow shortly after.")
    tl[3].markdown("**Day D+1**  \nDelivery. The battery charges and discharges; differences between bought and "
                   "used energy are settled as imbalance.")

    svg = ROOT / "docs" / "architecture_tso_dso.svg"
    if svg.exists():
        st.markdown("**From the national grid to the homes**")
        b64 = base64.b64encode(svg.read_bytes()).decode()
        st.markdown(f"<div style='background:#ffffff;border-radius:8px;padding:8px;text-align:center'>"
                    f"<img src='data:image/svg+xml;base64,{b64}' style='max-width:100%;max-height:420px'/></div>",
                    unsafe_allow_html=True)
    st.markdown("**How the pieces fit together**")
    st.code("Demand model (Zurich, MW)   Price model (CH, EUR/MWh)   Battery limits\n"
            "              \\                     |                     /\n"
            "               -> optimiser: buy · buy and store · use storage and buy · use storage\n"
            "                              -> plan per block -> hourly bids -> auction\n"
            "                              -> settlement with the real prices and demand (backtest)",
            language=None)
    note("The battery does not change how much Zurich consumes, so it is not an input of the demand model - "
         "it only enters the optimiser.")

    st.subheader("Data sources")
    src = md_section(D.read_text("docs/data_sources.md"), "Summary")
    st.markdown(src or "See `docs/data_sources.md`.")

    st.subheader("Time rules: what is known when")
    st.markdown(f"""
| Input | Latest value we may use when planning on day D at {c['auction']['forecast_time_local']} |
|---|---|
| Zurich demand | up to the end of day D-1 (the grid operator reads its own meters) |
| Swiss and neighbouring day-ahead prices | all of day D (that auction was held on D-1) |
| Gas, CO₂, EUR/CHF | last close published before the forecast time |
| Reservoir levels | latest weekly value already published |
| Weather for D+1 | the **forecast** issued on day D (training before 2024 uses observed weather - a limitation) |
| Calendar, holidays, events | known in advance |
""")
    note("Times are Swiss local time; data is stored in UTC. On clock-change days a block has 3 or 5 hours. "
         "An automated test rebuilds features from raw data and checks that nothing from the future is used.")

    st.subheader("How the backtest settles a day")
    sf, uf = c["imbalance"]["shortage_price_factor"], c["imbalance"]["surplus_price_factor"]
    st.markdown(
        "1. The plan is turned into hourly bids. Demand bids always clear; a charge bid clears only if the real "
        "auction price is at or below its limit price.\n"
        "2. The battery follows the cleared bids hour by hour, inside its power and charge limits.\n"
        "3. The real demand of each hour is compared with the energy we had. A **shortfall** is bought at "
        f"**{sf:g} x** the auction price, a **surplus** is sold at **{uf:g} x** the auction price (assumed rule, "
        "not Swissgrid's real imbalance prices).\n"
        "4. Cost = auction purchases + imbalance + battery wear, converted to CHF with the daily ECB rate. The real "
        "charge level at the end of the day is carried into the next day.")

    st.subheader("Limitations and assumptions (in plain words)")
    st.markdown(
        "- **The battery and the company are fictional**; the demand and prices are real.\n"
        "- **Imbalance prices are assumed** (factors above), so the CHF value of a better demand forecast depends "
        "on them - see the sensitivity table in the Month backtest tab.\n"
        "- **Weather in older training years is observed**, not forecast (no forecast archive exists); the test "
        "months use real forecasts.\n"
        "- **One test month** (October 2026) gives wide uncertainty intervals; the rolling year is a robustness "
        "check.\n"
        "- **We are a price taker**: our bids do not move the auction price; a charge bid clears fully or not at all.\n"
        "- **Hourly bids only**; 15-minute products are not modelled.\n"
        "- The auction closing time (11:00) comes from EPEX documents; we assume it did not change in 2019-2026.\n"
        "- Recent ewz demand values can still be corrected by the publisher for some months.")
    for f in sorted((ROOT / "docs").glob("assumptions_*.md")):
        with st.expander(f"Full list: {f.stem.replace('_', ' ')}"):
            st.markdown(f.read_text(encoding="utf-8"))

    st.subheader("Independent review")
    rl = D.read_text("docs/review_log.md")
    if rl:
        fixed = len(re.findall(r"\*\*Fixed", rl))
        kept = len(re.findall(r"\*\*Kept", rl))
        st.markdown(f"Each phase was checked by an independent reviewer with a fresh context. So far "
                    f"**{fixed} findings were fixed** and **{kept} were kept as documented assumptions**.")
        with st.expander("Review log"):
            st.markdown(rl)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    version = D.data_version()
    d = sidebar(version)
    st.title("Day-ahead planning for Zurich")
    st.caption("Limmat Energie AG (fictional DSO) · forecast demand and price for tomorrow, plan the battery, "
               "bid at the Swiss day-ahead auction")
    tabs = st.tabs(["Tomorrow", "Battery settings", "Month backtest", "What drives demand and price",
                    "Data and method"])
    with tabs[0]:
        if d is not None:
            tab_tomorrow(d, version)
    with tabs[1]:
        if d is not None:
            tab_battery(d, version)
    with tabs[2]:
        tab_month(version)
    with tabs[3]:
        tab_drivers(version)
    with tabs[4]:
        tab_method(version)


main()
