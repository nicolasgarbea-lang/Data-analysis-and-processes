"""Extra analyses on top of the backtest: decision tuning (pre-October data only),
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
    BASELINE, BLOCK_ORACLE, CEILING, FIGURES, HOURLY_DAILY_ORACLE, LABELS, NO_BATTERY_PAIR, PERFECT_NO_BATTERY, PRODUCT,
    PRODUCT_DEFAULT, REPORTS, STRATEGIES, DecisionParams, ImbalanceParams, _as_date, _periods_cfg,
    block_bootstrap_index, bootstrap_sums, inventory_value_chf, lag1_autocorr, load_data, load_forecasts,
    paired_bootstrap_ci, run_tasks, source_text,
    tuning_cutoff,
)
from src.config import load_config  # noqa: E402
from src.optimisation.battery_lp import BatteryParams  # noqa: E402

# Fixed colour per strategy (categorical palette, fixed order, never cycled)
COLORS = {
    "baseline_naive_no_battery": "#8a8a85",
    "ml_no_battery": "#eb6834",
    "naive_battery": "#1baf7a",
    "ml_battery": "#2a78d6",
    "ml_battery_block_default": "#7fb0e8",
    "perfect_foresight_battery": "#6250d6",
    "perfect_foresight_hourly_daily_battery": "#b07fd6",
    "perfect_foresight_hourly_battery": "#e87ba4",
    "perfect_demand_no_battery": "#eda100",
}
INK, MUTED, GRID = "#222222", "#6b6b66", "#e4e3df"
# The figures keep the original eight strategies; 5b (hourly oracle with daily reset) is a
# diagnostic row in the tables and the decomposition only.
FIG_STRATEGIES = [s for s in STRATEGIES if s != HOURLY_DAILY_ORACLE]


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


def adj_cost(daily: pd.DataFrame, strategy: str | None = None) -> float:
    """Inventory-adjusted total cost (CHF) of one strategy's daily rows over one period."""
    g = daily if strategy is None else daily[daily["strategy"] == strategy]
    if len(g) == 0:
        return np.nan
    return float(g["total_cost_chf"].sum() - inventory_value_chf(g)[1])


def raw_cost(daily: pd.DataFrame, strategy: str | None = None) -> float:
    g = daily if strategy is None else daily[daily["strategy"] == strategy]
    return float(g["total_cost_chf"].sum())


# ---------------------------------------------------------------------------
# Decision tuning: data strictly before the test month
# ---------------------------------------------------------------------------
def check_tuning_dates(dates, cutoff=None) -> None:
    """Decision rules for the test month may only be tuned on days whose settlement was
    known when the first test day was planned (<= ``tuning_cutoff()``)."""
    cutoff = tuning_cutoff() if cutoff is None else _as_date(cutoff)
    test_start = _as_date(_periods_cfg()["test_start"])
    late = [d for d in dates if _as_date(d) > cutoff or _as_date(d) >= test_start]
    if late:
        raise ValueError(f"tuning may only use days up to {cutoff}; got {len(late)} later day(s), first {late[0]}")


def candidate_grid(stage: int, base: DecisionParams, has_quantiles: bool) -> list[DecisionParams]:
    """Stage 1: planning resolution / hourly shape x minimum spread margin (limit and
    protection at their defaults). Stage 2: on the stage-1 winner, charge limit rule x
    protection."""
    out = []
    if stage == 1:
        for res, days, same in [("block", base.shape_days, False), ("hourly_shape", 7, False),
                                ("hourly_shape", 7, True), ("hourly_shape", 14, False)]:
            for m in (0.0, 5.0, 10.0, 20.0):
                out.append(replace(base, plan_resolution=res, shape_days=days, shape_daytype=same, min_spread_eur_mwh=m))
    else:
        limits = [(f, True, "factor") for f in (0.8, 0.9, 1.0, 1.1)] + [(base.charge_limit_factor, False, "factor")]
        if has_quantiles:
            limits += [(0.9, True, "quantile"), (1.0, True, "quantile")]
        for f, use, rule in limits:
            for prot in ("none", "at_risk_bid"):
                out.append(replace(base, charge_limit_factor=f, use_limit=use, limit_rule=rule, protect=prot))
    seen, uniq = set(), []
    for c in out:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    return uniq


def tune_decision(rolling_dates, sept_dates, battery=None, require_ml=False, cutoff=None,
                  n_boot=1000, seed=None):
    """Choose the product's decision rules ONCE on data strictly before the test month.

    Periods: the rolling period (rolling_start -> train_end) and September up to the
    cutoff (test start - 2 days). Each candidate runs ml_battery over both periods (each
    period starts with the battery at the start level). Saving = inventory-adjusted saving
    vs the baseline (strategy 1). Candidates are ranked by the COMBINED saving. Two stages
    (see ``candidate_grid``); in each stage the best candidate replaces the stage reference
    only if it CLEARLY wins: combined improvement > 0 and the paired day-bootstrap 95 %
    interval of the improvement lies above 0. Otherwise the reference (config default in
    stage 1) is kept.

    Returns (table, chosen DecisionParams, kept_default flag).
    """
    seed = load_config().get("random_seed", 42) if seed is None else seed
    periods = {"rolling": list(rolling_dates or []), "sept": list(sept_dates or [])}
    for dates in periods.values():
        check_tuning_dates(dates, cutoff)
    periods = {k: v for k, v in periods.items() if v}
    if not periods:
        raise ValueError("no tuning days")
    fc = load_forecasts(require_ml)
    has_q = bool(fc["price_q90_eur_mwh"].notna().any())
    default = DecisionParams.from_config()

    base_tasks = [dict(tag=("base", k), dates=v, strategy=BASELINE, require_ml=require_ml) for k, v in periods.items()]
    base = {t[0][1]: t[1] for t in run_tasks(base_tasks)}
    cache: dict = {}

    def evaluate(cands):
        todo = [c for c in cands if c not in cache]
        tasks = [dict(tag=(i, k), dates=v, strategy=PRODUCT, decision=c, battery=battery, require_ml=require_ml)
                 for i, c in enumerate(todo) for k, v in periods.items()]
        for (i, k), d, _ in run_tasks(tasks):
            cache.setdefault(todo[i], {})[k] = d

    def stats(c):
        r = {}
        for k, d in cache[c].items():
            b = base[k]
            r[f"saving_{k}_chf"] = raw_cost(b) - adj_cost(d)
            r[f"saving_{k}_raw_chf"] = raw_cost(b) - raw_cost(d)
            r[f"cycles_{k}"] = float(d["cycles"].sum())
            r[f"shortage_{k}_mwh"] = float(d["shortage_mwh"].sum())
            bid = d["charge_bid_mwh"].sum()
            r[f"charge_cleared_{k}"] = float(d["charge_cleared_mwh"].sum() / bid) if bid > 1e-9 else np.nan
        r["saving_combined_chf"] = sum(r[f"saving_{k}_chf"] for k in cache[c])
        r["saving_combined_raw_chf"] = sum(r[f"saving_{k}_raw_chf"] for k in cache[c])
        return r

    def improvement_ci(c, ref):
        a = np.concatenate([cache[ref][k]["total_cost_chf"].to_numpy() for k in periods])
        b = np.concatenate([cache[c][k]["total_cost_chf"].to_numpy() for k in periods])
        shift = sum(inventory_value_chf(cache[c][k])[1] - inventory_value_chf(cache[ref][k])[1] for k in periods)
        return paired_bootstrap_ci(a, b, n_boot, seed, shift=shift)

    rows, ref, kept_any = [], default, True
    for stage in (1, 2):
        cands = candidate_grid(stage, ref, has_q)
        if ref not in cands:
            cands = [ref] + cands
        evaluate(cands)
        st = {c: stats(c) for c in cands}
        best = max(cands, key=lambda c: st[c]["saving_combined_chf"])
        gain = st[best]["saving_combined_chf"] - st[ref]["saving_combined_chf"]
        lo, hi = improvement_ci(best, ref) if best != ref else (0.0, 0.0)
        clear = best != ref and gain > 0 and lo > 0
        winner = best if clear else ref
        for c in cands:
            clo, chi = improvement_ci(c, ref) if c != ref else (0.0, 0.0)
            rows.append({"stage": stage, "candidate": c.describe(), **{k: v for k, v in c.__dict__.items()},
                         "charge_limit": c.limit_label, **st[c],
                         "vs_reference_chf": st[c]["saving_combined_chf"] - st[ref]["saving_combined_chf"],
                         "vs_reference_ci_low_chf": clo, "vs_reference_ci_high_chf": chi,
                         "is_reference": c == ref, "is_default": c == default, "stage_winner": c == winner})
        kept_any = kept_any and not clear
        ref = winner
    tab = pd.DataFrame(rows)
    tab["chosen"] = (tab["stage"] == 2) & tab["stage_winner"]
    tab["cutoff"] = str(tuning_cutoff() if cutoff is None else _as_date(cutoff))
    tab["days_rolling"] = len(periods.get("rolling", []))
    tab["days_sept"] = len(periods.get("sept", []))
    return tab, ref, ref == default


# ---------------------------------------------------------------------------
# Sensitivities (test month; information only, nothing is chosen from them)
# ---------------------------------------------------------------------------
SIZES = [(5, 10), (10, 20), (20, 40), (50, 100), (100, 200)]
SIGMAS = (0, 5, 10, 20, 30, 45, 60, 80)


def _noise_overrides(dates, sigma, k, seed):
    blocks = load_data()["blocks"]
    true = {d: blocks[d]["price_eur_mwh"].to_numpy(float) for d in dates}
    rng = np.random.default_rng(seed + 1000 * k + int(sigma))
    over = {d: true[d] + (rng.normal(0, sigma, size=len(true[d])) if sigma > 0 else 0.0) for d in dates}
    mae = float(np.mean(np.concatenate([np.abs(over[d] - true[d]) for d in dates])))
    return over, mae


def price_error_sensitivity(dates, decision, sigmas=SIGMAS, seeds=5, require_ml=False, seed=None):
    """CHF lost per 1 EUR/MWh of block-price forecast error, under the SAME policy.

    Demand is perfect (actual block demand + actual hourly shape, so no imbalance). The plan
    uses the true block prices + zero-mean normal noise of size sigma (per block and day),
    with the product's decision rules (``decision``). The REFERENCE is the zero-noise run
    with the same rules, so lost saving = cost(sigma) - cost(sigma = 0) measures only the
    price-forecast error. The zero-noise run's own gap to the ceiling (6) and to the
    block oracle (5) is the cost of the decision POLICY and reported separately.
    """
    seed = load_config().get("random_seed", 42) if seed is None else seed
    spec = dict(demand="actual", price="custom", battery=True, policy="given", name="noisy_price")
    tasks, meta = [], []
    for sigma in sigmas:
        for k in range(1 if sigma == 0 else seeds):
            over, mae = _noise_overrides(dates, sigma, k, seed)
            tasks.append(dict(tag=len(meta), dates=dates, strategy=spec, decision=decision, price_overrides=over))
            meta.append({"forecast": "noise", "sigma": sigma, "seed": k, "price_mae_eur_mwh": mae})
    fc = load_forecasts(require_ml)
    blocks = load_data()["blocks"]
    tr = np.concatenate([blocks[d]["price_eur_mwh"].to_numpy(float) for d in dates])
    sub = fc[fc["delivery_date"].isin(dates)].sort_values(["delivery_date", "block"])
    for which in ["naive", "ml"]:
        spec2 = dict(demand="actual", price=which, battery=True, policy="given", name=f"{which}_price")
        mae = float(np.mean(np.abs(sub[f"price_{which}_eur_mwh"].to_numpy() - tr)))
        tasks.append(dict(tag=len(meta), dates=dates, strategy=spec2, decision=decision, require_ml=require_ml))
        meta.append({"forecast": which, "sigma": np.nan, "seed": np.nan, "price_mae_eur_mwh": mae})
    for s in [CEILING, BLOCK_ORACLE, PERFECT_NO_BATTERY]:
        tasks.append(dict(tag=len(meta), dates=dates, strategy=s))
        meta.append({"forecast": s})
    res = run_tasks(tasks)
    costs = [adj_cost(d) for _, d, _ in res]
    m = pd.DataFrame(meta)
    m["total_cost_adj_chf"] = costs
    c_ceiling = float(m.loc[m["forecast"] == CEILING, "total_cost_adj_chf"].iloc[0])
    c_block = float(m.loc[m["forecast"] == BLOCK_ORACLE, "total_cost_adj_chf"].iloc[0])
    c_nob = float(m.loc[m["forecast"] == PERFECT_NO_BATTERY, "total_cost_adj_chf"].iloc[0])
    tab = m[m["forecast"].isin(["noise", "naive", "ml"])].copy()
    c_ref = float(tab.loc[(tab["forecast"] == "noise") & (tab["sigma"] == 0), "total_cost_adj_chf"].iloc[0])
    tab["lost_saving_chf"] = tab["total_cost_adj_chf"] - c_ref
    tab["battery_value_chf"] = c_nob - tab["total_cost_adj_chf"]
    noise = tab[tab["forecast"] == "noise"]
    slope, intercept = np.polyfit(noise["price_mae_eur_mwh"], noise["lost_saving_chf"], 1)
    tab.attrs.update(slope_chf_per_eur=float(slope), intercept_chf=float(intercept),
                     reference_cost_chf=c_ref, policy_gap_to_ceiling_chf=c_ref - c_ceiling,
                     policy_gap_to_block_oracle_chf=c_ref - c_block,
                     ceiling_battery_value_chf=c_nob - c_ceiling, zero_noise_battery_value_chf=c_nob - c_ref,
                     days=len(dates))
    return tab.reset_index(drop=True)


def battery_size_sensitivity(dates, decision, require_ml=False):
    """Battery value (inventory-adjusted) for several battery sizes: product, block oracle
    (5) and ceiling (6)."""
    tasks = [dict(tag=("fixed", s), dates=dates, strategy=s, require_ml=require_ml)
             for s in [BASELINE, "ml_no_battery", PERFECT_NO_BATTERY]]
    for p, e in SIZES:
        bat = BatteryParams.from_config(power_mw=p, capacity_mwh=e)
        for s in [PRODUCT, BLOCK_ORACLE, CEILING]:
            tasks.append(dict(tag=((p, e), s), dates=dates, strategy=s, battery=bat, decision=decision,
                              require_ml=require_ml))
    res = run_tasks(tasks)
    fixed = {t[1]: adj_cost(d) for t, d, _ in res if t[0] == "fixed"}
    rows = []
    for t, d, _ in res:
        if t[0] == "fixed":
            continue
        (p, e), s = t
        c = adj_cost(d)
        bid = d["charge_bid_mwh"].sum()
        rows.append({"power_mw": p, "capacity_mwh": e, "strategy": s, "total_cost_adj_chf": c,
                     "battery_value_chf": fixed[NO_BATTERY_PAIR[s]] - c, "saving_vs_baseline_chf": fixed[BASELINE] - c,
                     "cycles": d["cycles"].sum(), "share_charge_cleared": d["charge_cleared_mwh"].sum() / bid if bid > 1e-9 else np.nan})
    return pd.DataFrame(rows)


def decision_sensitivity(dates, decision, require_ml=False):
    """Imbalance factors, charge limit factor, wear cost and selling (one at a time)."""
    tasks = []
    for fs, fu in [(1.1, 0.9), (1.2, 0.8), (1.5, 0.5)]:
        imb = ImbalanceParams(shortage_factor=fs, surplus_factor=fu)
        for s in [BASELINE, "ml_no_battery", PRODUCT, CEILING, PERFECT_NO_BATTERY]:
            tasks.append(dict(tag=("imb", f"{fs}/{fu}", s), dates=dates, strategy=s, decision=decision,
                              imbalance=imb, require_ml=require_ml))
    for s in [BASELINE, "ml_no_battery", PERFECT_NO_BATTERY]:
        tasks.append(dict(tag=("nob", "", s), dates=dates, strategy=s, require_ml=require_ml))
    for f in [0.7, 0.8, 0.9, 1.0, 1.1, None]:
        dec = replace(decision, charge_limit_factor=f if f is not None else decision.charge_limit_factor,
                      use_limit=f is not None, limit_rule="factor")
        for s in ["naive_battery", PRODUCT]:
            tasks.append(dict(tag=("limit", "none" if f is None else str(f), s), dates=dates, strategy=s,
                              decision=dec, require_ml=require_ml))
    for w in [0.0, 2.5, 5.0, 10.0, 20.0]:
        bat = BatteryParams.from_config(wear_cost_eur_per_mwh=w)
        for s in [PRODUCT, CEILING]:
            tasks.append(dict(tag=("wear", str(w), s), dates=dates, strategy=s, battery=bat, decision=decision,
                              require_ml=require_ml))
    for sell in [False, True]:
        for s in [PRODUCT, BLOCK_ORACLE]:
            tasks.append(dict(tag=("sell", "on" if sell else "off", s), dates=dates, strategy=s, decision=decision,
                              allow_sell=sell, require_ml=require_ml))
    res = run_tasks(tasks)
    c = {t: adj_cost(d) for t, d, _ in res}
    clr = {t: (d["charge_cleared_mwh"].sum() / max(d["charge_bid_mwh"].sum(), 1e-9)) for t, d, _ in res}
    cyc = {t: d["cycles"].sum() for t, d, _ in res}
    nob = {s: c[("nob", "", s)] for s in [BASELINE, "ml_no_battery", PERFECT_NO_BATTERY]}
    rows = []
    for v in ["1.1/0.9", "1.2/0.8", "1.5/0.5"]:
        k = lambda s: c[("imb", v, s)]  # noqa: E731
        rows.append({"parameter": "imbalance_factors", "value": v,
                     "saving_ml_battery_vs_baseline_chf": k(BASELINE) - k(PRODUCT),
                     "demand_forecast_part_chf": k(BASELINE) - k("ml_no_battery"),
                     "battery_value_ml_chf": k("ml_no_battery") - k(PRODUCT),
                     "battery_value_ceiling_chf": k(PERFECT_NO_BATTERY) - k(CEILING)})
    for v in ["0.7", "0.8", "0.9", "1.0", "1.1", "none"]:
        r = {"parameter": "charge_limit_factor", "value": v}
        for s in ["naive_battery", PRODUCT]:
            r[f"battery_value_{s}_chf"] = nob[NO_BATTERY_PAIR[s]] - c[("limit", v, s)]
            r[f"share_cleared_{s}"] = clr[("limit", v, s)]
        rows.append(r)
    for v in ["0.0", "2.5", "5.0", "10.0", "20.0"]:
        r = {"parameter": "wear_cost_eur_per_mwh", "value": v}
        for s in [PRODUCT, CEILING]:
            r[f"battery_value_{s}_chf"] = nob[NO_BATTERY_PAIR[s]] - c[("wear", v, s)]
            r[f"cycles_{s}"] = cyc[("wear", v, s)]
        rows.append(r)
    for v in ["off", "on"]:
        r = {"parameter": "allow_sell", "value": v}
        for s in [PRODUCT, BLOCK_ORACLE]:
            r[f"battery_value_{s}_chf"] = nob[NO_BATTERY_PAIR[s]] - c[("sell", v, s)]
            r[f"cycles_{s}"] = cyc[("sell", v, s)]
        rows.append(r)
    return pd.DataFrame(rows)


def run_sensitivities(test_dates, dec, require_ml, tag) -> dict:
    size_tab = battery_size_sensitivity(test_dates, dec, require_ml)
    size_tab.to_csv(REPORTS / "backtest_battery_sensitivity.csv", index=False)
    fig_battery_size(size_tab, FIGURES / "backtest_battery_size_sensitivity.png", tag)
    price_tab = price_error_sensitivity(test_dates, dec, require_ml=require_ml)
    pt = price_tab.copy()
    for k, v in price_tab.attrs.items():
        pt[k] = v
    pt.to_csv(REPORTS / "backtest_price_error_sensitivity.csv", index=False)
    fig_price_error(price_tab, FIGURES / "backtest_price_error_sensitivity.png", tag)
    sens_tab = decision_sensitivity(test_dates, dec, require_ml)
    sens_tab.to_csv(REPORTS / "backtest_decision_sensitivity.csv", index=False)
    fig_decision_sensitivity(sens_tab, FIGURES / "backtest_decision_sensitivity.png", tag)
    return {"size": size_tab, "price": price_tab, "decision": sens_tab}


# ---------------------------------------------------------------------------
# How wide is the interval really? (day-to-day correlation of the savings)
# ---------------------------------------------------------------------------
CI_BLOCK_DAYS = 7


def ci_sensitivity(daily: pd.DataFrame, summary: pd.DataFrame, strategy: str = PRODUCT,
                   block_len: int = CI_BLOCK_DAYS, n_boot: int = 1000, seed: int | None = None) -> pd.DataFrame:
    """95 % interval of the product's inventory-adjusted saving vs the baseline per split,
    twice: with independent days (as in ``backtest_summary.csv``) and with a circular
    ``block_len``-day block bootstrap that keeps runs of consecutive days together. Also
    reports the lag-1 autocorrelation of the daily savings (if it is clearly above zero,
    the independent-day interval is too narrow)."""
    seed = load_config().get("random_seed", 42) if seed is None else seed
    rows = []
    for split, g in daily.groupby("split", sort=False):
        piv = g.pivot_table(index="delivery_date", columns="strategy", values="total_cost_chf").sort_index()
        if BASELINE not in piv or strategy not in piv:
            continue
        ok = piv[BASELINE].notna() & piv[strategy].notna()
        sav = (piv.loc[ok, BASELINE] - piv.loc[ok, strategy]).to_numpy()
        srow = summary[(summary["split"] == split) & (summary["strategy"] == strategy)].iloc[0]
        brow = summary[(summary["split"] == split) & (summary["strategy"] == BASELINE)].iloc[0]
        shift = float(srow["inventory_value_chf"] - brow["inventory_value_chf"])
        idx = block_bootstrap_index(len(sav), block_len, n_boot, seed)
        draws = bootstrap_sums(sav, idx) + shift
        rows.append({
            "split": split, "strategy": strategy, "days": int(len(sav)),
            "saving_vs_baseline_adj_chf": float(srow["saving_vs_baseline_adj_chf"]),
            "lag1_autocorr_daily_saving": lag1_autocorr(sav),
            "ci_independent_days_low_chf": float(srow["saving_adj_ci_low_chf"]),
            "ci_independent_days_high_chf": float(srow["saving_adj_ci_high_chf"]),
            "block_length_days": int(block_len),
            "ci_block_low_chf": float(np.percentile(draws, 2.5)),
            "ci_block_high_chf": float(np.percentile(draws, 97.5)),
            "n_boot": int(n_boot), "seed": int(seed),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Plausibility checks ("numbers add up")
# ---------------------------------------------------------------------------
EXC_COLS = ["split", "delivery_date", "check", "excess_chf", "demand_part_chf", "battery_part_chf", "reason"]


def day_exceptions(daily: pd.DataFrame, summary: pd.DataFrame | None = None, tol_chf: float = 0.01) -> pd.DataFrame:
    """Days where the product (4) is NOT cheaper than the baseline (1), or the block oracle
    (5) / the ceiling (6) is NOT cheaper than the product on that single day, each with a
    plain-language reason. Plus a PERIOD check: the ceiling's inventory-adjusted cost must
    be <= every strategy's over the whole period (should never fail)."""
    rows = []
    for (split, d), g in daily.groupby(["split", "delivery_date"]):
        s = g.set_index("strategy")
        need = [BASELINE, "ml_no_battery", PRODUCT, BLOCK_ORACLE]
        if not all(k in s.index for k in need):
            continue
        c = s["total_cost_chf"]
        ml = s.loc[PRODUCT]
        if c[PRODUCT] > c[BASELINE] + tol_chf:
            demand_part = c["ml_no_battery"] - c[BASELINE]  # > 0: ML demand forecast worse than naive
            battery_part = c[PRODUCT] - c["ml_no_battery"]  # > 0: battery lost money (today)
            if demand_part >= battery_part:
                reason = "demand forecast: the ML demand forecast was further off than the naive one (more imbalance)"
            elif ml["soc_end_mwh"] > ml["soc_start_mwh"] + 0.5:
                reason = "battery refill / stock-up: energy bought today is stored for later days (cost today, value later)"
            elif pd.notna(ml["share_charge_cleared"]) and ml["share_charge_cleared"] < 0.999:
                reason = "limit bid not (fully) cleared: less energy stored, planned discharge partly not delivered"
            elif ml.get("at_risk_bid_mwh", 0) > 1e-3:
                reason = "protection bid: the extra at-risk volume was not needed and was sold back below the price"
            else:
                reason = "price forecast: the forecast spread between hours/blocks did not happen (wrong order or too small)"
            rows.append({"split": split, "delivery_date": d, "check": "ml_battery > baseline",
                         "excess_chf": c[PRODUCT] - c[BASELINE], "demand_part_chf": demand_part,
                         "battery_part_chf": battery_part, "reason": reason})
        for oracle, lab in [(BLOCK_ORACLE, "block_oracle(5) > ml_battery"), (CEILING, "ceiling(6) > ml_battery")]:
            if oracle not in s.index or not (c[oracle] > c[PRODUCT] + tol_chf):
                continue
            pf = s.loc[oracle]
            net_ml = ml["soc_start_mwh"] - ml["soc_end_mwh"]
            net_pf = pf["soc_start_mwh"] - pf["soc_end_mwh"]
            if oracle == CEILING and net_pf < net_ml - 0.5:
                reason = ("inter-day shift: the ceiling plans the whole period at once and stored more energy on this "
                          "day (or used less) to save on another day")
            elif net_ml > net_pf + 0.5:
                reason = ("charge-level carry-over: ml_battery took more energy out of the battery than it put in "
                          "(energy bought on an earlier day)")
            elif oracle == BLOCK_ORACLE:
                reason = ("hourly prices inside the blocks: the block oracle is optimal for 4-hour AVERAGE prices; "
                          "ml_battery charged/discharged in better single hours")
            else:
                reason = "inter-day shift: the ceiling's day-by-day split of a period-optimal plan"
            rows.append({"split": split, "delivery_date": d, "check": lab, "excess_chf": c[oracle] - c[PRODUCT],
                         "demand_part_chf": np.nan, "battery_part_chf": np.nan, "reason": reason})
    if summary is not None:
        for split, g in summary.groupby("split"):
            t = g.set_index("strategy")["total_cost_adj_chf"]
            if CEILING not in t:
                continue
            for s, v in t.items():
                if t[CEILING] > v + tol_chf:
                    rows.append({"split": split, "delivery_date": "PERIOD", "check": f"PERIOD ceiling(6) > {s}",
                                 "excess_chf": t[CEILING] - v, "demand_part_chf": np.nan, "battery_part_chf": np.nan,
                                 "reason": "the ceiling is not the cheapest over the period - this should never happen"})
    return pd.DataFrame(rows, columns=EXC_COLS)


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------
def fig_cumulative(daily: pd.DataFrame, path, title_suffix=""):
    piv = daily.pivot_table(index="delivery_date", columns="strategy", values="total_cost_chf")
    sav = piv.sub(piv[BASELINE], axis=0).mul(-1).cumsum() / 1000
    fig, ax = plt.subplots(figsize=(9.5, 5.2))
    for s in [k for k in FIG_STRATEGIES if k != BASELINE and k in sav]:
        lw = 2.6 if s == PRODUCT else 1.5
        ls = "--" if s == PRODUCT_DEFAULT else "-"
        ax.plot(pd.to_datetime(sav.index.astype(str)), sav[s], color=COLORS[s], lw=lw, ls=ls, label=LABELS[s])
        ax.annotate(f"{sav[s].iloc[-1]:,.0f}", (pd.to_datetime(str(sav.index[-1])), sav[s].iloc[-1]),
                    xytext=(4, 0), textcoords="offset points", fontsize=8, color=INK, va="center")
    ax.axhline(0, color=MUTED, lw=0.8)
    _style(ax, f"Cumulative saving vs baseline, raw (test month){title_suffix}", None, "thousand CHF")
    ax.legend(frameon=False, fontsize=7.5, loc="upper left")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def fig_cost_breakdown(summary: pd.DataFrame, path, split="test", title_suffix=""):
    """Extra cost of each strategy over 'perfect demand, no battery' (the pure cost of
    serving the city), split into energy & arbitrage, imbalance penalty, wear and the
    end-of-period inventory adjustment (inventory-adjusted totals)."""
    g = summary[summary["split"] == split].set_index("strategy")
    ref = g.loc[PERFECT_NO_BATTERY]
    order = [s for s in FIG_STRATEGIES if s in g.index]
    pen = g.loc[order, "imbalance_penalty_chf"] / 1000
    wear = g.loc[order, "wear_cost_chf"] / 1000
    inv = -g.loc[order, "inventory_value_chf"] / 1000
    total = (g.loc[order, "total_cost_adj_chf"] - ref["total_cost_adj_chf"]) / 1000
    energy = total - pen - wear - inv
    fig, ax = plt.subplots(figsize=(10, 5.2))
    x = np.arange(len(order))
    parts = [("Imbalance penalty", pen, "#eb6834"), ("Battery wear", wear, "#eda100"),
             ("Inventory adjustment (end of period)", inv, "#8a8a85"),
             ("Energy purchase & arbitrage", energy, "#2a78d6")]
    pos_base, neg_base = np.zeros(len(order)), np.zeros(len(order))
    for name, v, col in parts:
        v = v.to_numpy()
        base = np.where(v >= 0, pos_base, neg_base)
        ax.bar(x, v, 0.6, bottom=base, color=col, label=name, edgecolor="white", linewidth=1)
        pos_base += np.where(v >= 0, v, 0)
        neg_base += np.where(v < 0, v, 0)
    ax.scatter(x, total, color=INK, zorder=3, s=30, label="Total extra cost (inventory-adjusted)")
    for i, t in enumerate(total):
        ax.annotate(f"{t:,.0f}", (x[i], t), xytext=(8, 0), textcoords="offset points", fontsize=8, color=INK, va="center")
    ax.axhline(0, color=MUTED, lw=0.8)
    ax.set_xticks(x, [textwrap.fill(LABELS[s], 13) for s in order], fontsize=7)
    _style(ax, f"Extra cost over 'perfect demand, no battery' ({split}){title_suffix}", None, "thousand CHF")
    ax.legend(frameon=False, fontsize=7.5)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def fig_tuning(tab: pd.DataFrame, path, title_suffix=""):
    t = tab.sort_values(["stage", "saving_combined_chf"])
    fig, ax = plt.subplots(figsize=(9.5, max(4.5, 0.22 * len(t) + 1.5)))
    y = np.arange(len(t))
    cols = np.where(t["chosen"], "#2a78d6", np.where(t["is_default"], "#eda100", "#b9b8b3"))
    ax.barh(y, t["saving_combined_chf"] / 1000, color=cols, height=0.7)
    ax.set_yticks(y, [f"S{s}: {c}" for s, c in zip(t["stage"], t["candidate"])], fontsize=6.5)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    _style(ax, f"Decision tuning: product saving vs baseline, rolling + Sept<=29 (inventory-adjusted){title_suffix}",
           "thousand CHF (blue = chosen, yellow = config default)", None)
    ax.grid(axis="y", visible=False)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def fig_battery_size(tab: pd.DataFrame, path, title_suffix=""):
    fig, ax = plt.subplots(figsize=(8, 4.8))
    for s in [PRODUCT, BLOCK_ORACLE, CEILING]:
        t = tab[tab["strategy"] == s]
        ax.plot(t["capacity_mwh"], t["battery_value_chf"] / 1000, marker="o", ms=6, lw=2, color=COLORS[s], label=LABELS[s])
        for _, r in t.iterrows():
            ax.annotate(f"{r.power_mw:.0f}/{r.capacity_mwh:.0f}", (r.capacity_mwh, r.battery_value_chf / 1000),
                        xytext=(4, 6 if s == CEILING else -12), textcoords="offset points", fontsize=7, color=MUTED)
    ax.set_xscale("log")
    ax.set_xticks([10, 20, 40, 100, 200], ["10", "20", "40", "100", "200"])
    _style(ax, f"Battery value in the test month by battery size (MW/MWh){title_suffix}",
           "battery capacity (MWh, power = capacity / 2)", "thousand CHF (inventory-adjusted)")
    ax.axhline(0, color=MUTED, lw=0.8)
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def fig_price_error(tab: pd.DataFrame, path, title_suffix=""):
    noise = tab[tab["forecast"] == "noise"]
    a = tab.attrs
    fig, ax = plt.subplots(figsize=(8, 4.8))
    ax.scatter(noise["price_mae_eur_mwh"], noise["lost_saving_chf"] / 1000, s=22, color="#8a8a85",
               label="true block price + random noise (5 seeds per size)")
    xs = np.linspace(0, max(noise["price_mae_eur_mwh"].max(), tab["price_mae_eur_mwh"].max()) * 1.05, 50)
    ax.plot(xs, (a["intercept_chf"] + a["slope_chf_per_eur"] * xs) / 1000, color=INK, lw=1.2,
            label=f"fit: {a['slope_chf_per_eur']:,.0f} CHF lost per 1 EUR/MWh of MAE (month)")
    for which, col, lab in [("naive", "#1baf7a", "naive price forecast"), ("ml", "#2a78d6", "product price forecast")]:
        r = tab[tab["forecast"] == which]
        if len(r):
            r = r.iloc[0]
            ax.scatter([r.price_mae_eur_mwh], [r.lost_saving_chf / 1000], s=60, color=col, zorder=3,
                       label=f"{lab} (MAE {r.price_mae_eur_mwh:.1f})")
    ax.axhline(a["zero_noise_battery_value_chf"] / 1000, color="#6250d6", lw=1, ls=":",
               label="battery value at zero noise (same rules)")
    _style(ax, f"Battery saving lost because of price-forecast error (test month){title_suffix}",
           "MAE of the block price forecast (EUR/MWh)", "lost saving vs zero noise, thousand CHF")
    ax.axhline(0, color=MUTED, lw=0.8)
    ax.legend(frameon=False, fontsize=7.5, loc="lower right")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def fig_decision_sensitivity(tab: pd.DataFrame, path, title_suffix=""):
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.2))
    t = tab[tab["parameter"] == "imbalance_factors"]
    x = np.arange(len(t))
    for i, (col, lab, c) in enumerate([("demand_forecast_part_chf", "demand forecast part", "#eb6834"),
                                       ("battery_value_ml_chf", "battery part (product)", "#2a78d6"),
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
    for s in [PRODUCT, CEILING]:
        axes[2].plot(t["value"].astype(float), t[f"battery_value_{s}_chf"] / 1000, marker="o", color=COLORS[s], label=LABELS[s])
    _style(axes[2], "Wear cost", "EUR per MWh discharged", "battery value, thousand CHF")
    axes[2].legend(frameon=False, fontsize=7)
    fig.suptitle(f"Sensitivity of the test-month result (inventory-adjusted){title_suffix}", x=0.01, ha="left", fontsize=11)
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
            if abs(v) < 0.005:
                return "0"
            return format(v, ".2f") if abs(v) < 10 and v != int(v) else format(v, floatfmt)
        return str(v)
    cols = list(df.columns)
    lines = ["| " + " | ".join(str(c) for c in cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join(fmt(r[c]) for c in cols) + " |")
    return "\n".join(lines)


SUMMARY_COLS = {
    "label": "strategy", "total_cost_chf": "total cost CHF", "saving_vs_baseline_chf": "saving vs 1 (raw)",
    "saving_vs_baseline_adj_chf": "saving vs 1 (adj.)", "saving_adj_ci_low_chf": "CI low",
    "saving_adj_ci_high_chf": "CI high", "pct_perfect_captured": "% of ceiling",
    "battery_value_adj_chf": "battery value (adj.)", "pct_battery_value_captured": "% of ceiling battery value",
    "imbalance_penalty_chf": "imbalance penalty", "inventory_change_mwh": "stock change MWh",
    "cycles": "cycles", "days_battery_idle": "idle days", "share_charge_cleared": "charge cleared",
}


def summary_md(summary: pd.DataFrame, split: str) -> str:
    g = summary[summary["split"] == split]
    t = g[list(SUMMARY_COLS)].rename(columns=SUMMARY_COLS).copy()
    t["charge cleared"] = t["charge cleared"].map(lambda v: "" if pd.isna(v) else f"{100 * v:.0f}%")
    t["cycles"] = t["cycles"].map(lambda v: f"{v:.1f}")
    t["stock change MWh"] = t["stock change MWh"].map(lambda v: f"{v:+.1f}")
    for c in ["% of ceiling", "% of ceiling battery value"]:
        t[c] = t[c].map(lambda v: "" if pd.isna(v) else f"{v:.0f}%")
    return md_table(t)


def _tuning_md(tab: pd.DataFrame) -> str:
    cols = ["stage", "candidate", "saving_rolling_chf", "saving_sept_chf", "saving_combined_chf",
            "vs_reference_chf", "vs_reference_ci_low_chf", "vs_reference_ci_high_chf", "is_default", "stage_winner", "chosen"]
    cols = [c for c in cols if c in tab]
    t = tab[cols].sort_values(["stage", "saving_combined_chf"], ascending=[True, False])
    return md_table(t.rename(columns={"saving_rolling_chf": "saving rolling", "saving_sept_chf": "saving Sept 1-29",
                                      "saving_combined_chf": "combined", "vs_reference_chf": "vs stage ref.",
                                      "vs_reference_ci_low_chf": "CI low", "vs_reference_ci_high_chf": "CI high"}))


def write_notes(path, sources, summary, decomp, exceptions, tuning_tab, chosen, kept_default, sens=None,
                ci_tab=None):
    sens = sens or {}
    bat = BatteryParams.from_config()
    imb = ImbalanceParams.from_config()
    L = ["# Backtest notes", "",
         "*Regenerated by `.venv/bin/python -m src.backtest.run_backtest` on every run. Do not edit by hand.*", ""]
    L += ["## Which forecasts were used", "",
          f"- **Demand forecast:** {'ML (`pred_best` from `reports/predictions_demand.parquet`)' if sources['demand'] == 'ml' else '**STAND-IN** (mean of the same block on the same weekday over the last 4 weeks) - the ML file was missing'}.",
          f"- **Price forecast:** {'ML (`pred_best` from `reports/predictions_price.parquet`)' if sources['price'] == 'ml' else '**STAND-IN** (the same block on day D, known since the D-1 auction) - `reports/predictions_price.parquet` did not exist when this file was written'}.",
          ""]
    if sources["price"] != "ml":
        L += ["> **The price numbers below use the STAND-IN price forecast, not the project's price model.** "
              "Strategies 3, 4 and 4b and the tuning depend on it. When `reports/predictions_price.parquet` "
              "exists, re-run `.venv/bin/python -m src.backtest.run_backtest --require-ml`; tuning, tables, "
              "figures and this note are all regenerated.", ""]
    L += ["## How the money is counted", "",
          "- All money in CHF (hourly EUR x ECB EUR/CHF rate of the day). Cost = day-ahead purchases + imbalance "
          "settlement + battery wear "
          f"({bat.wear_cost_eur_per_mwh:g} EUR per MWh discharged).",
          f"- **Imbalance price** (p = actual day-ahead price of the hour): a shortage costs "
          f"**p + {imb.shortage_factor - 1:.2f} x |p|** per MWh, a surplus is sold for **p - {1 - imb.surplus_factor:.2f} x |p|** "
          f"per MWh (shortage factor {imb.shortage_factor:g}, surplus factor {imb.surplus_factor:g}; |p| keeps it a "
          "penalty at negative prices). These are assumptions, not Swissgrid's real imbalance prices.",
          "- Every strategy starts each period with the battery at "
          f"{bat.soc_start:g} MWh. Because strategies end the period with different amounts of energy in the battery, "
          "we also report an **inventory-adjusted** cost: energy left in the battery at the end minus at the start "
          f"(MWh) x discharge efficiency ({bat.eta_discharge:.3f}) x the period's mean actual day-ahead price, "
          "subtracted from the cost. Savings are shown raw and adjusted; '% of ceiling' uses the adjusted numbers.",
          "- **Ceiling (6)** = one hourly perfect-foresight plan over the WHOLE period, ending with the same charge "
          "level it started with, physical wear only, no limits or margins. It is a true lower bound on cost: no "
          "strategy that follows the same battery rules can be cheaper over the period. **(5)** is perfect foresight "
          "with the same 4-hour block rules as the product (uniform dispatch inside a block, back to the start level "
          "every evening); it is NOT a ceiling.",
          "- **(5b)** is hourly perfect foresight planned day by day with the same end-of-day target as (5). "
          "It splits the gap between (5) and (6) into finer dispatch (5 -> 5b) and inter-day flexibility (5b -> 6).",
          "- CI = 95 % paired day-bootstrap interval (1000 draws) of the saving vs strategy 1. It treats the days as "
          "independent; see the block-bootstrap interval below for a wider, more honest one.", ""]
    titles = [("test", "Test month (October 2026)"), ("val", "Validation month (September 2026)"),
              ("rolling", f"Rolling period ({_periods_cfg()['rolling_start']} to {_periods_cfg()['train_end']})")]
    for split, title in titles:
        if not (summary["split"] == split).any():
            continue
        lab = {"ml": "ML", "standin": "STAND-IN"}
        L += [f"## {title}", "", f"Demand forecast: **{lab[sources['demand']]}**; price forecast: "
              f"**{lab[sources['price']]}**.", "", summary_md(summary, split), ""]
        d = decomp[decomp["split"] == split]
        if len(d):
            r = d.iloc[0]
            L += [f"- Saving of the product (4) vs baseline (1), inventory-adjusted: **CHF {r.total_saving_chf:,.0f}** "
                  f"(raw CHF {r.total_saving_raw_chf:,.0f}) = better demand forecast (1-2) CHF {r.demand_forecast_part_chf:,.0f} "
                  f"+ battery (2-4) CHF {r.battery_part_chf:,.0f}."]
            if "tuning_and_shaping_part_chf" in r:
                L += [f"  - of the battery part: plain block plan with defaults (2-4b) CHF {r.block_default_battery_part_chf:,.0f}, "
                      f"added by the tuned rules / hourly shaping (4b-4) CHF {r.tuning_and_shaping_part_chf:,.0f}."]
            L += [f"- The ceiling (6) would save CHF {r.ceiling_total_saving_chf:,.0f}; the product captures "
                  f"**{r.pct_ceiling_captured_total:.0f}%** of it. Of the ceiling's battery value (7-6 = CHF "
                  f"{r.ceiling_battery_value_chf:,.0f}) the product's battery captures **{r.pct_ceiling_battery_value_captured:.0f}%**.",
                  f"- Cost of demand-forecast errors (vs perfect demand, no battery): naive CHF "
                  f"{r.forecast_error_cost_naive_chf:,.0f}, ML CHF {r.forecast_error_cost_ml_chf:,.0f}."]
            if "block_rule_cost_chf" in r:
                L += [f"- Perfect foresight with 4-hour block rules (5) is CHF {r.block_rule_cost_chf:,.0f} short of the "
                      f"ceiling (6) (block-rule battery value CHF {r.block_perfect_battery_value_chf:,.0f})."]
            if "finer_dispatch_part_chf" in r and pd.notna(r.finer_dispatch_part_chf):
                L += [f"  - of this, CHF {r.finer_dispatch_part_chf:,.0f} is finer dispatch (5 -> 5b: hourly instead of "
                      f"4-hour blocks, still back to the start level every evening; battery value 5b CHF "
                      f"{r.hourly_daily_battery_value_chf:,.0f}) and CHF {r.interday_flexibility_part_chf:,.0f} is "
                      "inter-day flexibility (5b -> 6: moving energy between days, which the daily plans never do)."]
            L += [""]
    if ci_tab is not None and len(ci_tab):
        L += ["## How wide is the interval with correlated days?", "",
              f"Daily savings are correlated from one day to the next. The table compares the independent-day "
              f"interval with a circular {int(ci_tab['block_length_days'].iloc[0])}-day block bootstrap "
              "(`reports/backtest_ci_sensitivity.csv`, product (4) vs baseline (1), inventory-adjusted).", "",
              md_table(ci_tab[["split", "days", "saving_vs_baseline_adj_chf", "lag1_autocorr_daily_saving",
                               "ci_independent_days_low_chf", "ci_independent_days_high_chf", "ci_block_low_chf",
                               "ci_block_high_chf"]].rename(columns={
                  "saving_vs_baseline_adj_chf": "saving", "lag1_autocorr_daily_saving": "lag-1 autocorr.",
                  "ci_independent_days_low_chf": "CI low (indep.)", "ci_independent_days_high_chf": "CI high (indep.)",
                  "ci_block_low_chf": "CI low (block)", "ci_block_high_chf": "CI high (block)"}), floatfmt=",.2f"), ""]
    if (summary["split"] == "val").any():
        L += ["Note: the decision rules were tuned on the rolling period plus September 1-29, so the September and "
              "rolling numbers are in-sample for those rules (the forecasts themselves are out-of-sample). Only "
              "October is a clean test of the rules.", ""]

    co = tuning_tab["cutoff"].iloc[0] if "cutoff" in tuning_tab else str(tuning_cutoff())
    L += ["## Decision tuning (data before October only)", "",
          f"Tuned ONCE for the test month on the rolling period ({int(tuning_tab['days_rolling'].iloc[0])} days) plus "
          f"September up to {co} ({int(tuning_tab['days_sept'].iloc[0])} days): the settlement of these days was "
          "known when the first October day was planned (30 Sept, 10:00). October is never used. Objective = the "
          "product's inventory-adjusted saving vs the baseline, summed over both periods.",
          "",
          "Stage 1 compares the planning resolution (block plan vs hourly plan with a typical hourly price shape of "
          "the last 7 or 14 days, all days or same day type) x the minimum spread margin. Stage 2 takes the stage-1 "
          "winner and compares the charge-limit rule (factor 0.8-1.1, no limit"
          + (", q90 cap" if (tuning_tab.get("limit_rule", pd.Series(dtype=str)) == "quantile").any() else "")
          + ") x the protection bid. A candidate replaces the stage reference only if it CLEARLY wins (combined "
          "saving higher AND the 95 % paired-bootstrap interval of the improvement above zero).",
          "",
          ("**Nothing clearly beat the config defaults, so the defaults are kept.**" if kept_default else
           f"**Chosen: {chosen.describe()}.** Used for strategies 3 and 4 in all periods."),
          "", _tuning_md(tuning_tab), ""]

    L += ["## Checks: do the numbers add up?", "",
          "Energy conservation per hour (bought + discharged + shortage - surplus = demand + stored), the "
          "charge-level limits and 'never charge and discharge in the same hour' are asserted in code for every hour "
          "of every run; all runs passed. Missing or non-finite prices, demand or EUR/CHF values stop the run with an "
          "error naming the hour; every day must have 23/24/25 hours.", ""]
    per = exceptions[exceptions["delivery_date"].astype(str) == "PERIOD"]
    L += [f"- Period check 'ceiling (6) is the cheapest strategy (inventory-adjusted)': "
          + ("**holds in every period.**" if len(per) == 0 else f"**FAILED {len(per)} times** - see backtest_exceptions.csv."), ""]
    for split in ["test", "val", "rolling"]:
        if not (summary["split"] == split).any():
            continue
        n = int(summary.loc[(summary["split"] == split) & (summary["strategy"] == PRODUCT), "days"].iloc[0])
        e = exceptions[(exceptions["split"] == split) & (exceptions["delivery_date"].astype(str) != "PERIOD")]
        a5 = e[e["check"] == "block_oracle(5) > ml_battery"]
        a6 = e[e["check"] == "ceiling(6) > ml_battery"]
        b = e[e["check"] == "ml_battery > baseline"]
        L += [f"### {split}: {n} days", "",
              f"- ceiling (6) <= ml_battery (4) on the single day: holds on {n - len(a6)} of {n} days.",
              f"- block oracle (5) <= ml_battery (4): holds on {n - len(a5)} of {n} days.",
              f"- ml_battery (4) <= baseline (1): holds on {n - len(b)} of {n} days.", ""]
        if len(e):
            cnt = e.groupby(["check", "reason"]).size().reset_index(name="days")
            L += ["Reasons:", "", md_table(cnt), ""]
        if split == "test" and len(e):
            t = e[["delivery_date", "check", "excess_chf", "demand_part_chf", "battery_part_chf", "reason"]]
            L += ["Exception days (test):", "", md_table(t), ""]
    L += ["How to read the reasons:",
          "- *demand forecast*: on that day the ML demand forecast missed more than the naive one, so the "
          "imbalance penalty was higher.",
          "- *price forecast*: the battery cycled because the forecast showed a price gap, but the actual gap was "
          "smaller (or reversed), so losses + wear cost more than the gain.",
          "- *limit bid not cleared*: the actual price was above the charge limit, the battery stayed emptier and some "
          "planned discharge could not be delivered; that energy was bought as shortage.",
          "- *battery refill / stock-up*: energy is bought today and used on later days.",
          "- *inter-day shift / carry-over*: single-day comparisons with the ceiling are not meaningful - it optimises "
          "the whole period; only the period total must (and does) hold.", ""]

    pt, st, dt_ = sens.get("price"), sens.get("size"), sens.get("decision")
    if pt is not None or st is not None or dt_ is not None:
        L += ["## Sensitivities (test month, information only - nothing is chosen from them)", ""]
    if pt is not None:
        a = pt.attrs
        L += [f"- **Price-forecast error** (perfect demand, the product's decision rules, noise on the true block "
              f"prices; reference = the SAME rules with zero noise): about **CHF {a['slope_chf_per_eur']:,.0f} of "
              f"battery saving lost per 1 EUR/MWh of block-price MAE** over the month "
              f"(CHF {a['slope_chf_per_eur'] / a['days']:,.0f} per day).",
              f"  - The zero-noise run itself is CHF {a['policy_gap_to_ceiling_chf']:,.0f} more expensive than the ceiling "
              f"(6) and CHF {abs(a['policy_gap_to_block_oracle_chf']):,.0f} "
              f"{'more expensive' if a['policy_gap_to_block_oracle_chf'] > 0 else 'cheaper'} than the block oracle (5): "
              f"this gap is the cost of the decision POLICY (blocks / hourly shape, limits, daily target, hourly price "
              f"shape error), not of the block-price forecast. "
              f"Battery value at zero noise CHF {a['zero_noise_battery_value_chf']:,.0f}, ceiling CHF "
              f"{a['ceiling_battery_value_chf']:,.0f}."]
        for lab, which in [("naive", "naive"), (f"product ({sources['price']})", "ml")]:
            r = pt[pt["forecast"] == which]
            if len(r):
                r = r.iloc[0]
                L += [f"  - {lab} price forecast: MAE {r.price_mae_eur_mwh:.1f} EUR/MWh, lost CHF {r.lost_saving_chf:,.0f} "
                      "vs zero noise."]
        L += [""]
    if st is not None:
        t = st.pivot_table(index=["power_mw", "capacity_mwh"], columns="strategy", values="battery_value_chf").reset_index()
        t = t.rename(columns={PRODUCT: "4 product", BLOCK_ORACLE: "5 block oracle", CEILING: "6 ceiling"})
        L += ["- **Battery size** (battery value CHF, inventory-adjusted):", "", md_table(t), ""]
    if dt_ is not None:
        L += ["- **Imbalance factors, charge limit factor, wear cost, selling** (one at a time; "
              "`reports/backtest_decision_sensitivity.csv`):", ""]
        for par in ["imbalance_factors", "charge_limit_factor", "wear_cost_eur_per_mwh", "allow_sell"]:
            t = dt_[dt_["parameter"] == par].dropna(axis=1, how="all").drop(columns="parameter")
            L += [f"{par}:", "", md_table(t.rename(columns={"value": par})), ""]
        L += ["allow_sell is shown for information only: the DSO does not sell (config `allow_sell: false`). With a "
              "20 MW battery and a city load far above 20 MW the battery never needs to deliver more than the city "
              "uses, so selling changes (almost) nothing.", ""]
    L += ["## Limitations", "",
          "- Imbalance prices are assumed (see the formula above), not the real Swissgrid prices.",
          "- The battery is fictional and does not move prices (price taker); a charge bid clears fully or not at all.",
          "- Hourly demand inside a block follows last week's shape; the hourly price shape is a recent average.",
          "- Inventory adjustment uses one mean price per period; the true value of stored energy depends on the next days.",
          "- One test month; the bootstrap CI shows how uncertain the monthly totals are."]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
