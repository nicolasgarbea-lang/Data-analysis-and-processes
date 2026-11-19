"""Extra analyses on top of the backtest: decision tuning (validation only),
sensitivity runs, plausibility checks, figures and the plain-language notes.

Everything here is called from ``src.backtest.run_backtest.main``.
"""
from __future__ import annotations

import textwrap
from dataclasses import replace

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from src.backtest.run_backtest import (  # noqa: E402
    BASELINE, FIGURES, LABELS, NO_BATTERY_PAIR, PRODUCT, REPORTS, STRATEGIES,
    DecisionParams, ImbalanceParams, load_data, load_forecasts, run_strategy,
)
from src.config import load_config  # noqa: E402
from src.optimisation.battery_lp import BatteryParams  # noqa: E402

# Fixed colour per strategy (categorical palette, fixed order, never cycled)
COLORS = {
    "baseline_naive_no_battery": "#8a8a85",
    "ml_no_battery": "#eb6834",
    "naive_battery": "#1baf7a",
    "ml_battery": "#2a78d6",
    "perfect_foresight_battery": "#6250d6",
    "perfect_foresight_hourly_battery": "#e87ba4",
    "perfect_demand_no_battery": "#eda100",
}
INK, MUTED, GRID = "#222222", "#6b6b66", "#e4e3df"


def _style(ax, title=None, xlabel=None, ylabel=None):
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color(MUTED)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    if title:
        ax.set_title(title, loc="left", fontsize=11, color=INK)
    if xlabel:
        ax.set_xlabel(xlabel, color=MUTED, fontsize=9)
    if ylabel:
        ax.set_ylabel(ylabel, color=MUTED, fontsize=9)


def _cost(daily: pd.DataFrame, strategy: str) -> float:
    return float(daily.loc[daily["strategy"] == strategy, "total_cost_chf"].sum())


# ---------------------------------------------------------------------------
# Decision tuning: VALIDATION ONLY
# ---------------------------------------------------------------------------
def tune_decision(val_dates, extra_dates=None, battery=None, require_ml=False,
                  factors=(0.8, 0.9, 1.0, 1.1, None), spreads=(0.0, 5.0, 10.0, 20.0)):
    """Try decision rules for the product (ml_battery) on the validation days only.

    ``factors``: charge limit factor (None = no limit, charge at any price).
    ``spreads``: minimum expected spread margin (EUR/MWh) before cycling.
    The objective is the total CHF cost of ml_battery over ``val_dates`` (+
    ``extra_dates``, e.g. the rolling period when real predictions exist). The config
    default is kept unless another setting is strictly cheaper.
    Returns (table, chosen DecisionParams, kept_default flag).
    """
    default = DecisionParams.from_config()
    rows = []
    for f in factors:
        for m in spreads:
            dec = replace(default, charge_limit_factor=f if f is not None else default.charge_limit_factor,
                          use_limit=f is not None, min_spread_eur_mwh=m)
            r = {"charge_limit_factor": "none" if f is None else f, "min_spread_eur_mwh": m}
            for name, dates in [("val", val_dates), ("rolling", extra_dates)]:
                if not dates:
                    continue
                d, _ = run_strategy(dates, PRODUCT, battery, dec, require_ml=require_ml)
                r[f"cost_{name}_chf"] = d["total_cost_chf"].sum()
                r[f"cycles_{name}"] = d["cycles"].sum()
            r["objective_chf"] = sum(v for k, v in r.items() if k.startswith("cost_"))
            r["is_default"] = (f == default.charge_limit_factor and m == default.min_spread_eur_mwh
                               and default.use_limit)
            rows.append(r)
    tab = pd.DataFrame(rows)
    base = float(tab.loc[tab["is_default"], "objective_chf"].iloc[0])
    tab["vs_default_chf"] = tab["objective_chf"] - base
    best = tab.loc[tab["objective_chf"].idxmin()]
    kept_default = not (best["objective_chf"] < base - 1e-6)
    if kept_default:
        chosen = default
        tab["chosen"] = tab["is_default"]
    else:
        f = best["charge_limit_factor"]
        chosen = replace(default, charge_limit_factor=default.charge_limit_factor if f == "none" else float(f),
                         use_limit=f != "none", min_spread_eur_mwh=float(best["min_spread_eur_mwh"]))
        tab["chosen"] = tab.index == best.name
    return tab, chosen, kept_default


# ---------------------------------------------------------------------------
# Sensitivities (test month; information only, nothing is chosen from them)
# ---------------------------------------------------------------------------
SIZES = [(5, 10), (10, 20), (20, 40), (50, 100), (100, 200)]


def battery_size_sensitivity(dates, decision, require_ml=False):
    """Battery value and saving vs baseline for several battery sizes (ML and perfect)."""
    rows = []
    fixed = {s: _cost(run_strategy(dates, s, decision=decision, require_ml=require_ml)[0], s)
             for s in [BASELINE, "ml_no_battery", "perfect_demand_no_battery"]}
    for p, e in SIZES:
        bat = BatteryParams.from_config(power_mw=p, capacity_mwh=e)
        for s in [PRODUCT, "perfect_foresight_battery"]:
            d, _ = run_strategy(dates, s, bat, decision, require_ml=require_ml)
            c = _cost(d, s)
            rows.append({"power_mw": p, "capacity_mwh": e, "strategy": s, "total_cost_chf": c,
                         "battery_value_chf": fixed[NO_BATTERY_PAIR[s]] - c,
                         "saving_vs_baseline_chf": fixed[BASELINE] - c,
                         "cycles": d["cycles"].sum(),
                         "share_charge_cleared": d["charge_cleared_mwh"].sum() / max(d["charge_bid_mwh"].sum(), 1e-9)})
    return pd.DataFrame(rows)


def price_error_sensitivity(dates, decision, sigmas=(0, 5, 10, 20, 30, 45, 60, 80), seeds=5,
                            require_ml=False, seed=None):
    """CHF lost per 1 EUR/MWh of price-forecast error.

    Demand is perfect (actual block demand + actual hourly shape, so no imbalance);
    the plan uses true block prices + zero-mean normal noise of size sigma (per block
    and day). Settlement uses actual hourly prices. Lost saving = cost - cost of perfect
    foresight. The naive and ML price forecasts are run the same way for comparison.
    """
    seed = load_config().get("random_seed", 42) if seed is None else seed
    blocks = load_data()["blocks"]
    true = {d: blocks[d]["price_eur_mwh"].to_numpy(float) for d in dates}
    ref, _ = run_strategy(dates, "perfect_foresight_battery", decision=decision, require_ml=require_ml)
    c_ref = _cost(ref, "perfect_foresight_battery")
    nob, _ = run_strategy(dates, "perfect_demand_no_battery", decision=decision)
    c_nob = _cost(nob, "perfect_demand_no_battery")
    rows = []
    spec = dict(demand="actual", price="custom", battery=True, hourly=False, name="noisy_price")
    for sigma in sigmas:
        for k in range(1 if sigma == 0 else seeds):
            rng = np.random.default_rng(seed + 1000 * k + int(sigma))
            over = {d: true[d] + rng.normal(0, sigma, size=len(true[d])) for d in dates}
            mae = float(np.mean(np.concatenate([np.abs(over[d] - true[d]) for d in dates])))
            dd, _ = run_strategy(dates, spec, decision=decision, price_overrides=over)
            c = dd["total_cost_chf"].sum()
            rows.append({"forecast": "noise", "sigma": sigma, "seed": k, "price_mae_eur_mwh": mae,
                         "total_cost_chf": c, "lost_saving_chf": c - c_ref, "battery_value_chf": c_nob - c})
    fc = load_forecasts(require_ml)
    for which in ["naive", "ml"]:
        spec2 = dict(demand="actual", price=which, battery=True, hourly=False, name=f"{which}_price")
        sub = fc[fc["delivery_date"].isin(dates)].sort_values(["delivery_date", "block"])
        tr = np.concatenate([true[d] for d in dates])
        mae = float(np.mean(np.abs(sub[f"price_{which}_eur_mwh"].to_numpy() - tr)))
        dd, _ = run_strategy(dates, spec2, decision=decision, require_ml=require_ml)
        c = dd["total_cost_chf"].sum()
        rows.append({"forecast": which, "sigma": np.nan, "seed": np.nan, "price_mae_eur_mwh": mae,
                     "total_cost_chf": c, "lost_saving_chf": c - c_ref, "battery_value_chf": c_nob - c})
    tab = pd.DataFrame(rows)
    noise = tab[tab["forecast"] == "noise"]
    slope, intercept = np.polyfit(noise["price_mae_eur_mwh"], noise["lost_saving_chf"], 1)
    tab.attrs.update(slope_chf_per_eur=float(slope), intercept_chf=float(intercept),
                     perfect_battery_value_chf=c_nob - c_ref, days=len(dates))
    return tab


def decision_sensitivity(dates, decision, require_ml=False):
    """Imbalance factors, charge limit factor and wear cost (one at a time)."""
    rows = []
    # imbalance factors
    for fs, fu in [(1.1, 0.9), (1.2, 0.8), (1.5, 0.5)]:
        imb = ImbalanceParams(shortage_factor=fs, surplus_factor=fu)
        c = {s: _cost(run_strategy(dates, s, decision=decision, imbalance=imb, require_ml=require_ml)[0], s)
             for s in [BASELINE, "ml_no_battery", PRODUCT, "perfect_foresight_battery", "perfect_demand_no_battery"]}
        rows.append({"parameter": "imbalance_factors", "value": f"{fs}/{fu}",
                     "saving_ml_battery_vs_baseline_chf": c[BASELINE] - c[PRODUCT],
                     "demand_forecast_part_chf": c[BASELINE] - c["ml_no_battery"],
                     "battery_value_ml_chf": c["ml_no_battery"] - c[PRODUCT],
                     "battery_value_perfect_chf": c["perfect_demand_no_battery"] - c["perfect_foresight_battery"]})
    nob = {s: _cost(run_strategy(dates, s, decision=decision, require_ml=require_ml)[0], s)
           for s in [BASELINE, "ml_no_battery", "perfect_demand_no_battery"]}
    # charge limit factor
    for f in [0.7, 0.8, 0.9, 1.0, 1.1, None]:
        dec = replace(decision, charge_limit_factor=f if f is not None else decision.charge_limit_factor,
                      use_limit=f is not None)
        r = {"parameter": "charge_limit_factor", "value": "none" if f is None else str(f)}
        for s in ["naive_battery", PRODUCT]:
            d, _ = run_strategy(dates, s, decision=dec, require_ml=require_ml)
            r[f"battery_value_{s}_chf"] = nob[NO_BATTERY_PAIR[s]] - _cost(d, s)
            r[f"share_cleared_{s}"] = d["charge_cleared_mwh"].sum() / max(d["charge_bid_mwh"].sum(), 1e-9)
        rows.append(r)
    # wear cost
    for w in [0.0, 2.5, 5.0, 10.0, 20.0]:
        bat = BatteryParams.from_config(wear_cost_eur_per_mwh=w)
        r = {"parameter": "wear_cost_eur_per_mwh", "value": str(w)}
        for s in [PRODUCT, "perfect_foresight_battery"]:
            d, _ = run_strategy(dates, s, bat, decision, require_ml=require_ml)
            r[f"battery_value_{s}_chf"] = nob[NO_BATTERY_PAIR[s]] - _cost(d, s)
            r[f"cycles_{s}"] = d["cycles"].sum()
        rows.append(r)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Plausibility checks ("numbers add up")
# ---------------------------------------------------------------------------
def day_exceptions(daily: pd.DataFrame, tol_chf: float = 0.01) -> pd.DataFrame:
    """Days where perfect foresight is NOT cheaper than ml_battery, or ml_battery is NOT
    cheaper than the baseline, each with a plain-language reason."""
    rows = []
    for (split, d), g in daily.groupby(["split", "delivery_date"]):
        s = g.set_index("strategy")
        need = [BASELINE, "ml_no_battery", PRODUCT, "perfect_foresight_battery"]
        if not all(k in s.index for k in need):
            continue
        c = s["total_cost_chf"]
        ml, pf = s.loc[PRODUCT], s.loc["perfect_foresight_battery"]
        if c[PRODUCT] > c[BASELINE] + tol_chf:
            demand_part = c["ml_no_battery"] - c[BASELINE]  # > 0: ML demand forecast worse than naive
            battery_part = c[PRODUCT] - c["ml_no_battery"]  # > 0: battery lost money
            if demand_part >= battery_part:
                reason = "demand forecast: the ML demand forecast was further off than the naive one (more imbalance)"
            elif not ml["plan_has_discharge"] and ml["charged_mwh"] > 1e-3:
                reason = "battery refill: the battery was refilled to its target level (cost today, value on later days)"
            elif ml["share_charge_cleared"] < 0.999 if pd.notna(ml["share_charge_cleared"]) else False:
                reason = "limit bid not (fully) cleared: less energy stored, planned discharge partly not delivered"
            else:
                reason = "price forecast: the forecast spread between blocks did not happen (wrong block order or too small)"
            rows.append({"split": split, "delivery_date": d, "check": "ml_battery > baseline",
                         "excess_chf": c[PRODUCT] - c[BASELINE], "demand_part_chf": demand_part,
                         "battery_part_chf": battery_part, "reason": reason})
        if c["perfect_foresight_battery"] > c[PRODUCT] + tol_chf:
            net_ml = ml["soc_start_mwh"] - ml["soc_end_mwh"]
            net_pf = pf["soc_start_mwh"] - pf["soc_end_mwh"]
            if net_ml > net_pf + 0.5:
                reason = ("charge-level carry-over: ml_battery took more energy out of the battery than it put in "
                          "(energy bought on an earlier day), perfect foresight did not")
            else:
                reason = ("hourly prices inside the blocks: the perfect plan is optimal for 4-hour AVERAGE prices; "
                          "ml_battery happened to charge/discharge in better single hours")
            rows.append({"split": split, "delivery_date": d, "check": "perfect_foresight > ml_battery",
                         "excess_chf": c["perfect_foresight_battery"] - c[PRODUCT], "demand_part_chf": np.nan,
                         "battery_part_chf": np.nan, "reason": reason})
    return pd.DataFrame(rows, columns=["split", "delivery_date", "check", "excess_chf",
                                       "demand_part_chf", "battery_part_chf", "reason"])


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------
def fig_cumulative(daily: pd.DataFrame, path, title_suffix=""):
    piv = daily.pivot_table(index="delivery_date", columns="strategy", values="total_cost_chf")
    sav = piv.sub(piv[BASELINE], axis=0).mul(-1).cumsum() / 1000
    fig, ax = plt.subplots(figsize=(9, 5))
    for s in [k for k in STRATEGIES if k != BASELINE and k in sav]:
        lw = 2.6 if s == PRODUCT else 1.6
        ax.plot(pd.to_datetime(sav.index.astype(str)), sav[s], color=COLORS[s], lw=lw, label=LABELS[s])
        ax.annotate(f"{sav[s].iloc[-1]:,.0f}", (pd.to_datetime(str(sav.index[-1])), sav[s].iloc[-1]),
                    xytext=(4, 0), textcoords="offset points", fontsize=8, color=INK, va="center")
    ax.axhline(0, color=MUTED, lw=0.8)
    _style(ax, f"Cumulative saving vs baseline (naive forecast, no battery){title_suffix}",
           None, "thousand CHF")
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def fig_cost_breakdown(summary: pd.DataFrame, path, split="test", title_suffix=""):
    """Extra cost of each strategy over 'perfect demand, no battery' (the pure cost of
    serving the city), split into energy & arbitrage, imbalance penalty and wear."""
    g = summary[summary["split"] == split].set_index("strategy")
    ref = g.loc["perfect_demand_no_battery"]
    order = [s for s in STRATEGIES if s in g.index]
    pen = g.loc[order, "imbalance_penalty_chf"] / 1000
    wear = g.loc[order, "wear_cost_chf"] / 1000
    total = (g.loc[order, "total_cost_chf"] - ref["total_cost_chf"]) / 1000
    energy = total - pen - wear
    fig, ax = plt.subplots(figsize=(9, 5))
    x = np.arange(len(order))
    parts = [("Imbalance penalty", pen, "#eb6834"), ("Battery wear", wear, "#eda100"),
             ("Energy purchase & arbitrage", energy, "#2a78d6")]
    pos_base, neg_base = np.zeros(len(order)), np.zeros(len(order))
    for name, v, col in parts:
        v = v.to_numpy()
        base = np.where(v >= 0, pos_base, neg_base)
        ax.bar(x, v, 0.6, bottom=base, color=col, label=name, edgecolor="white", linewidth=1)
        pos_base += np.where(v >= 0, v, 0)
        neg_base += np.where(v < 0, v, 0)
    ax.scatter(x, total, color=INK, zorder=3, s=30, label="Total extra cost")
    for i, t in enumerate(total):
        ax.annotate(f"{t:,.0f}", (x[i], t), xytext=(8, 0), textcoords="offset points", fontsize=8, color=INK, va="center")
    ax.axhline(0, color=MUTED, lw=0.8)
    ax.set_xticks(x, [textwrap.fill(LABELS[s], 13) for s in order], fontsize=7)
    _style(ax, f"Extra cost over 'perfect demand, no battery' ({split}){title_suffix}", None, "thousand CHF")
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def fig_battery_size(tab: pd.DataFrame, path, title_suffix=""):
    fig, ax = plt.subplots(figsize=(8, 4.8))
    for s in [PRODUCT, "perfect_foresight_battery"]:
        t = tab[tab["strategy"] == s]
        ax.plot(t["capacity_mwh"], t["battery_value_chf"] / 1000, marker="o", ms=6, lw=2, color=COLORS[s], label=LABELS[s])
        for _, r in t.iterrows():
            ax.annotate(f"{r.power_mw:.0f}/{r.capacity_mwh:.0f}", (r.capacity_mwh, r.battery_value_chf / 1000),
                        xytext=(4, 6 if s != PRODUCT else -12), textcoords="offset points", fontsize=7, color=MUTED)
    ax.set_xscale("log")
    ax.set_xticks([10, 20, 40, 100, 200], ["10", "20", "40", "100", "200"])
    _style(ax, f"Battery value in the test month by battery size (MW/MWh){title_suffix}",
           "battery capacity (MWh, power = capacity / 2)", "thousand CHF")
    ax.axhline(0, color=MUTED, lw=0.8)
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def fig_price_error(tab: pd.DataFrame, path, title_suffix=""):
    noise = tab[tab["forecast"] == "noise"]
    fig, ax = plt.subplots(figsize=(8, 4.8))
    ax.scatter(noise["price_mae_eur_mwh"], noise["lost_saving_chf"] / 1000, s=22, color="#8a8a85",
               label="true block price + random noise (5 seeds per size)")
    xs = np.linspace(0, noise["price_mae_eur_mwh"].max() * 1.05, 50)
    slope, icpt = tab.attrs["slope_chf_per_eur"], tab.attrs["intercept_chf"]
    ax.plot(xs, (icpt + slope * xs) / 1000, color=INK, lw=1.2,
            label=f"fit: {slope:,.0f} CHF lost per 1 EUR/MWh of MAE (month)")
    for which, col, lab in [("naive", "#1baf7a", "naive price forecast"), ("ml", "#2a78d6", "ML price forecast")]:
        r = tab[tab["forecast"] == which]
        if len(r):
            r = r.iloc[0]
            ax.axvline(r.price_mae_eur_mwh, color=col, lw=1, ls="--")
            ax.scatter([r.price_mae_eur_mwh], [r.lost_saving_chf / 1000], s=60, color=col, zorder=3,
                       label=f"{lab} (MAE {r.price_mae_eur_mwh:.1f})")
    ax.axhline(tab.attrs["perfect_battery_value_chf"] / 1000, color="#6250d6", lw=1, ls=":",
               label="whole perfect-foresight battery value")
    _style(ax, f"Battery saving lost because of price-forecast error (test month){title_suffix}",
           "MAE of the block price forecast (EUR/MWh)", "lost saving, thousand CHF")
    ax.legend(frameon=False, fontsize=7.5, loc="lower right")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def fig_decision_sensitivity(tab: pd.DataFrame, path, title_suffix=""):
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.2))
    t = tab[tab["parameter"] == "imbalance_factors"]
    x = np.arange(len(t))
    for i, (col, lab, c) in enumerate([("demand_forecast_part_chf", "demand forecast part", "#eb6834"),
                                       ("battery_value_ml_chf", "battery part (ML)", "#2a78d6"),
                                       ("saving_ml_battery_vs_baseline_chf", "total saving 4 vs 1", INK)]):
        axes[0].bar(x + (i - 1) * 0.26, t[col] / 1000, 0.24, color=c, label=lab)
    axes[0].set_xticks(x, t["value"])
    axes[0].axhline(0, color=MUTED, lw=0.8)
    _style(axes[0], "Imbalance factors (shortage/surplus)", None, "thousand CHF")
    axes[0].legend(frameon=False, fontsize=7)
    t = tab[tab["parameter"] == "charge_limit_factor"]
    for s in ["naive_battery", PRODUCT]:
        axes[1].plot(t["value"], t[f"battery_value_{s}_chf"] / 1000, marker="o", color=COLORS[s], label=LABELS[s])
    _style(axes[1], "Charge limit factor", "factor ('none' = no limit)", "battery value, thousand CHF")
    axes[1].legend(frameon=False, fontsize=7)
    t = tab[tab["parameter"] == "wear_cost_eur_per_mwh"]
    for s in [PRODUCT, "perfect_foresight_battery"]:
        axes[2].plot(t["value"].astype(float), t[f"battery_value_{s}_chf"] / 1000, marker="o", color=COLORS[s], label=LABELS[s])
    _style(axes[2], "Wear cost", "EUR per MWh discharged", "battery value, thousand CHF")
    axes[2].legend(frameon=False, fontsize=7)
    fig.suptitle(f"Sensitivity of the test-month result{title_suffix}", x=0.01, ha="left", fontsize=11)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Notes (plain language, regenerated with every run)
# ---------------------------------------------------------------------------
def md_table(df: pd.DataFrame, floatfmt: str = ",.0f") -> str:
    """Small markdown table without extra packages."""
    def fmt(v):
        if isinstance(v, (bool, np.bool_)):
            return "yes" if v else ""
        if isinstance(v, (float, np.floating, int, np.integer)):
            if np.isnan(v):
                return ""
            return format(v, ".2f") if abs(v) < 10 and v != int(v) else format(v, floatfmt)
        return str(v)
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join(fmt(r[c]) for c in cols) + " |")
    return "\n".join(lines)


SUMMARY_COLS = {
    "label": "strategy", "total_cost_chf": "total cost CHF", "saving_vs_baseline_chf": "saving vs 1 CHF",
    "saving_ci_low_chf": "CI low", "saving_ci_high_chf": "CI high", "pct_perfect_captured": "% of perfect",
    "battery_value_chf": "battery value CHF", "pct_battery_value_captured": "% of perfect battery value",
    "imbalance_penalty_chf": "imbalance penalty CHF", "wear_cost_chf": "wear CHF", "cycles": "cycles",
    "days_battery_idle": "idle days", "share_charge_cleared": "charge cleared",
}


def summary_md(summary: pd.DataFrame, split: str) -> str:
    g = summary[summary["split"] == split]
    t = g[list(SUMMARY_COLS)].rename(columns=SUMMARY_COLS).copy()
    t["charge cleared"] = t["charge cleared"].map(lambda v: "" if pd.isna(v) else f"{100 * v:.0f}%")
    t["cycles"] = t["cycles"].map(lambda v: f"{v:.1f}")
    for c in ["% of perfect", "% of perfect battery value"]:
        t[c] = t[c].map(lambda v: "" if pd.isna(v) else f"{v:.0f}%")
    return md_table(t)


def write_notes(path, source, summary, decomp, exceptions, tuning_tab, chosen, kept_default,
                price_tab=None, size_tab=None, sens_tab=None):
    stand_in = source != "ml"
    L = ["# Backtest notes (agent B1)", ""]
    if stand_in:
        L += ["> **STAND-IN FORECASTS.** The ML prediction files (`reports/predictions_demand.parquet`, "
              "`reports/predictions_price.parquet`) were not available when this file was written "
              f"(source: {source}). Strategies 2 and 4 use honest stand-in forecasts instead: demand = "
              "mean of the same block on the same weekday over the last 4 weeks, price = the same block on day D "
              "(already known from D-1's auction). Re-run `.venv/bin/python -m src.backtest.run_backtest` "
              "when the files exist; this note is regenerated.", ""]
    else:
        L += ["Forecasts: real ML predictions (`pred_best`) from `reports/predictions_*.parquet`.", ""]
    L += ["All money in CHF (hourly EUR x ECB EUR/CHF). Costs = day-ahead purchases + imbalance settlement "
          "+ battery wear. Saving = cost of strategy 1 minus cost of the strategy. CI = 95% day-bootstrap "
          "interval (1000 draws) of the saving vs strategy 1.", ""]
    for split, title in [("test", "Test month (October 2026)"), ("val", "Validation month (September 2026)"),
                         ("rolling", "Rolling period (2025-10-01 to 2026-08-31)")]:
        if (summary["split"] == split).any():
            L += [f"## {title}", "", summary_md(summary, split), ""]
            d = decomp[decomp["split"] == split]
            if len(d):
                r = d.iloc[0]
                L += [f"- Saving of the product (4) vs baseline (1): **CHF {r.total_saving_chf:,.0f}** = "
                      f"better demand forecast (1-2) CHF {r.demand_forecast_part_chf:,.0f} + battery (2-4) "
                      f"CHF {r.battery_part_chf:,.0f}.",
                      f"- Perfect foresight (5) would save CHF {r.perfect_total_saving_chf:,.0f}; the product captures "
                      f"**{r.pct_perfect_captured_total:.0f}%** of it. Of the perfect battery value (7-5 = CHF "
                      f"{r.perfect_battery_value_chf:,.0f}) the ML battery captures **{r.pct_perfect_battery_value_captured:.0f}%**.",
                      f"- Cost of forecast errors (vs perfect demand, no battery): naive CHF "
                      f"{r.forecast_error_cost_naive_chf:,.0f}, ML CHF {r.forecast_error_cost_ml_chf:,.0f}.",
                      f"- Planning in 4-hour blocks instead of hours costs CHF {r.get('block_simplification_cost_chf', np.nan):,.0f} "
                      "of battery value under perfect foresight (5 vs 6).", ""]
    if split_has(summary, "val"):
        L += ["Note: the decision rules were tuned on September, so the September numbers are in-sample for "
              "those rules (the forecasts are not).", ""]

    L += ["## Decision tuning (validation only)", ""]
    L += [f"Grid: charge limit factor x minimum expected spread margin, objective = total cost of ml_battery on "
          f"September 2026{' + rolling period' if 'cost_rolling_chf' in tuning_tab else ''}. "
          + ("**Nothing beat the config defaults, so the defaults are kept.**" if kept_default else
             f"**Chosen: charge_limit_factor = {'none' if not chosen.use_limit else chosen.charge_limit_factor}, "
             f"min_spread_eur_mwh = {chosen.min_spread_eur_mwh:g}** (used for the test run)."),
          "", md_table(tuning_tab.drop(columns=["forecast_source"], errors="ignore")
                       .sort_values("objective_chf").head(8)), ""]

    L += ["## Checks: do the numbers add up?", "",
          "Energy conservation per hour (bought + discharged + shortage - surplus = demand + stored) and the "
          "charge-level limits are asserted in code for every hour of every run; all runs passed.", ""]
    for split in ["test", "val", "rolling"]:
        if not split_has(summary, split):
            continue
        n = int(summary.loc[(summary["split"] == split) & (summary["strategy"] == PRODUCT), "days"].iloc[0])
        e = exceptions[exceptions["split"] == split]
        a = e[e["check"] == "perfect_foresight > ml_battery"]
        b = e[e["check"] == "ml_battery > baseline"]
        L += [f"### {split}: {n} days", "",
              f"- perfect foresight (5) <= ml_battery (4): holds on {n - len(a)} of {n} days ({len(a)} exceptions).",
              f"- ml_battery (4) <= baseline (1): holds on {n - len(b)} of {n} days ({len(b)} exceptions).", ""]
        if len(e):
            cnt = e.groupby(["check", "reason"]).size().reset_index(name="days")
            L += ["Reasons:", "", md_table(cnt), ""]
        if split == "test" and len(e):
            t = e[["delivery_date", "check", "excess_chf", "demand_part_chf", "battery_part_chf", "reason"]]
            L += ["Exception days (test):", "", md_table(t), ""]
    L += ["How to read the reasons:",
          "- *demand forecast*: on that day the ML demand forecast missed more than the naive one, so the "
          "imbalance penalty was higher. One month of daily forecasts always has such days.",
          "- *price forecast*: the battery cycled because the forecast showed a price gap between blocks, but the "
          "actual gap was smaller (or reversed), so losses + wear cost more than the gain.",
          "- *limit bid not cleared*: the actual price was above the charge limit, the battery stayed emptier and "
          "some planned discharge could not be delivered; the city then had to buy that energy as shortage.",
          "- *battery refill*: after a day with an uncleared charge bid, the battery is refilled to its target "
          "level; the cost appears today, the value on later days.",
          "- *charge-level carry-over / hourly prices*: perfect foresight works with block averages and always "
          "ends the day at the target level, so on single days a forecast strategy can be cheaper.", ""]

    if price_tab is not None:
        a = price_tab.attrs
        r_n = price_tab[price_tab["forecast"] == "naive"]
        r_m = price_tab[price_tab["forecast"] == "ml"]
        L += ["## Sensitivities (test month, information only)", "",
              f"- **Price-forecast error:** about **CHF {a['slope_chf_per_eur']:,.0f} of battery saving lost per "
              f"1 EUR/MWh of block-price MAE** over the month (CHF {a['slope_chf_per_eur'] / a['days']:,.0f} per day; "
              f"perfect demand, noise on true block prices, limit rule active). Perfect battery value: "
              f"CHF {a['perfect_battery_value_chf']:,.0f}."]
        for lab, r in [("naive", r_n), ("ML", r_m)]:
            if len(r):
                r = r.iloc[0]
                L += [f"  - {lab} price forecast: MAE {r.price_mae_eur_mwh:.1f} EUR/MWh, lost CHF {r.lost_saving_chf:,.0f}."]
    if size_tab is not None:
        t = size_tab.pivot_table(index=["power_mw", "capacity_mwh"], columns="strategy", values="battery_value_chf").reset_index()
        L += ["- **Battery size** (battery value CHF):", "", md_table(t), ""]
    if sens_tab is not None:
        L += ["- **Imbalance factors, charge limit factor, wear cost** (one at a time; "
              "`reports/backtest_decision_sensitivity.csv`, `reports/figures/backtest_decision_sensitivity.png`):", ""]
        for par in ["imbalance_factors", "charge_limit_factor", "wear_cost_eur_per_mwh"]:
            t = sens_tab[sens_tab["parameter"] == par].dropna(axis=1, how="all").drop(columns="parameter")
            L += [f"{par}:", "", md_table(t.rename(columns={"value": par})), ""]
        t = sens_tab[sens_tab["parameter"] == "charge_limit_factor"].set_index("value")
        key = "none" if not chosen.use_limit else str(chosen.charge_limit_factor)
        dkey = str(DecisionParams.from_config().charge_limit_factor)
        if key in t.index and dkey in t.index and key != dkey:
            a_, b_ = t.loc[key, f"battery_value_{PRODUCT}_chf"], t.loc[dkey, f"battery_value_{PRODUCT}_chf"]
            L += [f"Honest remark: the factor chosen on September ({key}) gives a test-month battery value of "
                  f"CHF {a_:,.0f}; the config default ({dkey}) would have given CHF {b_:,.0f}. We keep the "
                  "September choice for the headline (October is never used for choices).", ""]
    L += ["## Limitations", "",
          "- Imbalance prices are assumed (actual DA price x 1.2 / x 0.8), not the real Swissgrid prices.",
          "- The battery is fictional; it does not change prices (price taker).",
          "- Hourly demand shape inside a block is taken from last week; perfect foresight uses the actual shape.",
          "- Each period starts with the battery at the configured start level; the end-of-period level differs a "
          "little between strategies (value of that energy not counted).",
          "- One test month; the bootstrap CI shows how uncertain the monthly totals are."]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


def split_has(summary, split):
    return bool((summary["split"] == split).any())
