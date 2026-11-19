"""Print every table and key number used in reports/report.md, straight from the result files.

Run from the project folder:

    .venv/bin/python reports/make_report_tables.py                 # print all tables
    .venv/bin/python reports/make_report_tables.py --check reports/report.md
    .venv/bin/python reports/make_report_tables.py --fill reports/report.md

Tables in the report sit between markers `<!-- table:NAME -->` and `<!-- /table -->`.
`--fill` replaces the text between the markers with fresh output, `--check` only reports differences
(exit code 1 if any table is out of date). Numbers in the running text are listed by the `keynums` block.

Reads only: reports/*.csv, reports/predictions_*.parquet and data/processed/*.parquet (never writes them).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / "reports"
P = ROOT / "data" / "processed"

STRAT_ORDER = [
    "baseline_naive_no_battery", "ml_no_battery", "naive_battery", "ml_battery",
    "ml_battery_block_default", "perfect_foresight_battery", "perfect_foresight_hourly_battery",
    "perfect_demand_no_battery",
]
MODEL_NAMES = {"naive": "Naive (same block 7 days earlier)", "linear": "Linear (ridge)",
               "rf": "Random forest", "gbm": "Gradient boosting (LightGBM)", "best": "Best (final model)"}
BLOCKS = ["00–04", "04–08", "08–12", "12–16", "16–20", "20–24"]


# ----------------------------------------------------------------------------- formatting helpers
def chf(x: float) -> str:
    return "–" if pd.isna(x) else f"{x:,.0f}"


def f1(x: float) -> str:
    return "–" if pd.isna(x) else f"{x:.1f}"


def f2(x: float) -> str:
    return "–" if pd.isna(x) else f"{x:.2f}"


def pct(x: float, d: int = 0) -> str:
    return "–" if pd.isna(x) else f"{x:.{d}f} %"


def md(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, r in df.iterrows():
        out.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    return "\n".join(out)


# ----------------------------------------------------------------------------- loaders
def metrics(target: str) -> pd.DataFrame:
    m = pd.read_csv(R / f"metrics_{target}.csv")
    return m


def summary() -> pd.DataFrame:
    return pd.read_csv(R / "backtest_summary.csv")


def decomposition() -> pd.DataFrame:
    return pd.read_csv(R / "backtest_decomposition.csv").set_index("split")


# ----------------------------------------------------------------------------- tables
def t_model_metrics(target: str) -> str:
    m = metrics(target)
    a = m[m.block.astype(str) == "all"].set_index(["split", "model"])
    err = "MAPE" if target == "demand" else "sMAPE"
    unit = "MW" if target == "demand" else "EUR/MWh"
    rows = []
    for mod in ["naive", "linear", "rf", "gbm", "best"]:
        te, va, ro = a.loc[("test", mod)], a.loc[("val", mod)], a.loc[("rolling", mod)]
        naive_te = a.loc[("test", "naive"), "mae"]
        rows.append({
            "model": MODEL_NAMES[mod],
            f"Sept MAE ({unit})": f2(va.mae),
            f"Oct MAE ({unit})": f2(te.mae),
            "Oct 95 % CI": f"{f2(te.mae_ci_low)}–{f2(te.mae_ci_high)}",
            "Oct RMSE": f2(te.rmse),
            f"Oct {err}": pct(te.mape_or_smape, 2),
            "Oct bias": f2(te.bias),
            "Oct skill vs naive": pct(100 * (1 - te.mae / naive_te), 0),
            f"Rolling MAE ({unit})": f2(ro.mae),
        })
    return md(pd.DataFrame(rows))


def t_blocks() -> str:
    d = metrics("demand")
    p = metrics("price")
    rows = []
    for b in range(6):
        def g(m, mod):
            return m[(m.split == "test") & (m.model == mod) & (m.block.astype(str) == str(b))].mae.iloc[0]
        rows.append({"block": BLOCKS[b],
                     "demand best (MW)": f2(g(d, "best")), "demand naive (MW)": f2(g(d, "naive")),
                     "price best (EUR/MWh)": f2(g(p, "best")), "price naive (EUR/MWh)": f2(g(p, "naive"))})
    return md(pd.DataFrame(rows))


def t_dm() -> str:
    rows = []
    for target in ["demand", "price"]:
        t = pd.read_csv(R / f"model_tests_{target}.csv")
        for _, r in t.iterrows():
            rows.append({"target": target, "period": {"val": "Sept 2026", "test": "Oct 2026",
                                                       "rolling": "Oct 2025–Aug 2026"}[r.split],
                         "comparison": f"{r.model_a} vs {r.model_b}",
                         "mean daily MAE difference": f"{r.mean_diff:.2f}",
                         "DM statistic": f"{r.dm_stat:.2f}", "p-value": f"{r.p_value:.3f}",
                         "days": int(r.n_days)})
    return md(pd.DataFrame(rows))


def t_bands() -> str:
    rows = []
    for target, unit in [("demand", "MW"), ("price", "EUR/MWh")]:
        p = pd.read_parquet(R / f"predictions_{target}.parquet")
        for split, name in [("val", "Sept 2026"), ("test", "Oct 2026"), ("rolling", "Oct 2025–Aug 2026")]:
            s = p[p.split == split].dropna(subset=["pred_q10", "pred_q90", "y_true"])
            inside = ((s.y_true >= s.pred_q10) & (s.y_true <= s.pred_q90)).mean()
            rows.append({"target": target, "period": name, "share inside 10–90 % band": pct(100 * inside, 0),
                         "mean band width": f"{(s.pred_q90 - s.pred_q10).mean():.1f} {unit}"})
    return md(pd.DataFrame(rows))


def t_price_decision() -> str:
    d = pd.read_csv(R / "decision_metrics_price.csv")
    rows = []
    for split, name in [("test", "Oct 2026"), ("rolling", "Oct 2025–Aug 2026")]:
        for mod in ["naive", "gbm", "best"]:
            r = d[(d.split == split) & (d.model == mod)].iloc[0]
            rows.append({"period": name, "model": mod, "rank correlation": f"{r.rank_corr:.2f}",
                         "cheapest block right": pct(100 * r.hit_cheapest), "dearest block right": pct(100 * r.hit_dearest),
                         "shape MAE (EUR/MWh)": f1(r.shape_mae), "day-mean MAE (EUR/MWh)": f1(r.daymean_mae)})
    return md(pd.DataFrame(rows))


def t_worst() -> str:
    w = pd.read_csv(R / "worst_blocks_price.csv")
    out = pd.DataFrame({"day": w.delivery_date, "block": w.block.astype(str).str.replace(r"^\d+ \((.*)\)$", r"\1", regex=True),
                        "actual": w.y_true.map(f1), "forecast": w.pred_best.map(f1), "error": w.error.map(f1),
                        "naive": w.pred_naive.map(f1), "10–90 % band": [f"{a:.0f}–{b:.0f}" for a, b in zip(w.pred_q10, w.pred_q90)]})
    return md(out)


def t_importance(target: str) -> str:
    g = pd.read_csv(R / f"importance_groups_{target}.csv")
    unit = "MW" if target == "demand" else "EUR/MWh"
    out = pd.DataFrame({"group of inputs": g.feature, f"MAE increase when shuffled ({unit})": g.mae_increase.map(f2)})
    return md(out)


def t_strategies(split: str = "test") -> str:
    s = summary()
    s = s[s.split == split].set_index("strategy").loc[STRAT_ORDER]
    rows = []
    for k, r in s.iterrows():
        rows.append({
            "strategy": r.label,
            "total cost (CHF)": chf(r.total_cost_chf),
            "saving vs 1 (CHF, adj.)": chf(r.saving_vs_baseline_adj_chf),
            "95 % CI": "–" if k == STRAT_ORDER[0] else f"{chf(r.saving_adj_ci_low_chf)} to {chf(r.saving_adj_ci_high_chf)}",
            "% of ceiling": pct(r.pct_perfect_captured),
            "battery value (CHF)": chf(r.battery_value_adj_chf),
            "imbalance penalty (CHF)": chf(r.imbalance_penalty_chf),
            "cycles": f1(r.cycles),
            "idle days": int(r.days_battery_idle),
        })
    return md(pd.DataFrame(rows))


def t_decomposition() -> str:
    d = decomposition()
    rows = []
    names = {"test": "Oct 2026 (test, 31 days)", "val": "Sept 2026 (validation, 30 days)",
             "rolling": "Oct 2025–Aug 2026 (rolling, 335 days)"}
    for split in ["test", "val", "rolling"]:
        r = d.loc[split]
        rows.append({"period": names[split],
                     "product saving (CHF)": chf(r.total_saving_chf),
                     "from better demand forecast": chf(r.demand_forecast_part_chf),
                     "from battery": chf(r.battery_part_chf),
                     "battery: block plan": chf(r.block_default_battery_part_chf),
                     "battery: hourly shaping + tuning": chf(r.tuning_and_shaping_part_chf),
                     "ceiling saving": chf(r.ceiling_total_saving_chf),
                     "% of ceiling": pct(r.pct_ceiling_captured_total),
                     "% of ceiling battery value": pct(r.pct_ceiling_battery_value_captured),
                     "cost of 4-hour block rule": chf(r.block_rule_cost_chf)})
    return md(pd.DataFrame(rows))


def _year():
    d = decomposition()
    s = summary().set_index(["split", "strategy"])
    days = {sp: int(s.loc[(sp, "ml_battery"), "days"]) for sp in ["test", "val", "rolling"]}
    cost = {sp: s.loc[(sp, "baseline_naive_no_battery"), "total_cost_chf"] for sp in ["test", "val", "rolling"]}
    year = {k: d.loc["rolling", k] + d.loc["val", k] for k in
            ["total_saving_chf", "demand_forecast_part_chf", "battery_part_chf", "ceiling_total_saving_chf",
             "ceiling_battery_value_chf"]}
    year_days = days["rolling"] + days["val"]
    year_cost = cost["rolling"] + cost["val"]
    return d, days, cost, year, year_days, year_cost


def t_year() -> str:
    d, days, cost, year, year_days, year_cost = _year()
    rows = [
        {"basis": f"Oct 2025–Sep 2026 = rolling ({days['rolling']} days) + Sept ({days['val']} days), {year_days} days",
         "product saving (CHF)": chf(year["total_saving_chf"]),
         "demand forecast part": chf(year["demand_forecast_part_chf"]),
         "battery part": chf(year["battery_part_chf"]),
         "saving as % of baseline cost": pct(100 * year["total_saving_chf"] / year_cost, 2),
         "baseline cost (CHF)": chf(year_cost)},
        {"basis": "for comparison only: 12 × October 2026",
         "product saving (CHF)": chf(12 * d.loc["test", "total_saving_chf"]),
         "demand forecast part": chf(12 * d.loc["test", "demand_forecast_part_chf"]),
         "battery part": chf(12 * d.loc["test", "battery_part_chf"]),
         "saving as % of baseline cost": pct(100 * d.loc["test", "total_saving_chf"] / cost["test"], 2),
         "baseline cost (CHF)": chf(12 * cost["test"])},
    ]
    return md(pd.DataFrame(rows))


def t_monthly() -> str:
    b = pd.read_csv(R / "backtest.csv")
    b["month"] = b.delivery_date.str[:7]
    piv = b.pivot_table(index="month", columns="strategy", values="total_cost_chf", aggfunc="sum")
    n = b[b.strategy == "ml_battery"].groupby("month").size()
    out = pd.DataFrame({
        "month": piv.index,
        "days": n.loc[piv.index].values,
        "saving product vs 1 (CHF)": (piv.baseline_naive_no_battery - piv.ml_battery).map(chf).values,
        "demand forecast part": (piv.baseline_naive_no_battery - piv.ml_no_battery).map(chf).values,
        "battery part": (piv.ml_no_battery - piv.ml_battery).map(chf).values,
        "ceiling battery value": (piv.perfect_demand_no_battery - piv.perfect_foresight_hourly_battery).map(chf).values,
    })
    return md(out)


def t_battery_size() -> str:
    s = pd.read_csv(R / "backtest_battery_sensitivity.csv")
    piv = s.pivot_table(index=["power_mw", "capacity_mwh"], columns="strategy", values="battery_value_chf")
    sav = s[s.strategy == "ml_battery"].set_index(["power_mw", "capacity_mwh"]).saving_vs_baseline_chf
    out = pd.DataFrame({
        "battery": [f"{int(p)} MW / {int(c)} MWh" for p, c in piv.index],
        "product battery value (CHF)": piv.ml_battery.map(chf).values,
        "per MWh of capacity (CHF)": (piv.ml_battery / piv.index.get_level_values(1)).map(chf).values,
        "block-rule oracle (CHF)": piv.perfect_foresight_battery.map(chf).values,
        "ceiling (CHF)": piv.perfect_foresight_hourly_battery.map(chf).values,
        "product total saving vs 1 (CHF)": sav.loc[piv.index].map(chf).values,
    })
    return md(out)


def t_price_error() -> str:
    p = pd.read_csv(R / "backtest_price_error_sensitivity.csv")
    noise = p[p.forecast == "noise"].groupby("sigma").agg(mae=("price_mae_eur_mwh", "mean"),
                                                          lost=("lost_saving_chf", "mean"))
    rows = [{"price forecast": f"random error, σ = {s:.0f} EUR/MWh (mean of 5 seeds)",
             "block-price MAE (EUR/MWh)": f1(r.mae), "battery saving lost vs perfect prices (CHF)": chf(r.lost)}
            for s, r in noise.iterrows() if s > 0]
    for k, name in [("naive", "naive price forecast"), ("ml", "our ML price forecast")]:
        r = p[p.forecast == k].iloc[0]
        rows.append({"price forecast": name, "block-price MAE (EUR/MWh)": f1(r.price_mae_eur_mwh),
                     "battery saving lost vs perfect prices (CHF)": chf(r.lost_saving_chf)})
    return md(pd.DataFrame(rows))


def t_decision_sens() -> str:
    d = pd.read_csv(R / "backtest_decision_sensitivity.csv")
    rows = []
    for _, r in d.iterrows():
        par = r.parameter
        if par == "imbalance_factors":
            rows.append({"what was changed": f"imbalance factors {r.value} (shortage/surplus)",
                         "product saving vs 1 (CHF)": chf(r.saving_ml_battery_vs_baseline_chf),
                         "demand forecast part (CHF)": chf(r.demand_forecast_part_chf),
                         "product battery value (CHF)": chf(r.battery_value_ml_chf)})
        elif par == "charge_limit_factor":
            rows.append({"what was changed": f"charge limit factor {r.value}",
                         "product saving vs 1 (CHF)": "",
                         "demand forecast part (CHF)": "",
                         "product battery value (CHF)": f"{chf(r.battery_value_ml_battery_chf)} (charge cleared {pct(100 * r.share_cleared_ml_battery)})"})
        elif par == "wear_cost_eur_per_mwh":
            rows.append({"what was changed": f"wear cost {float(r.value):g} EUR/MWh",
                         "product saving vs 1 (CHF)": "", "demand forecast part (CHF)": "",
                         "product battery value (CHF)": chf(r.battery_value_ml_battery_chf)})
    return md(pd.DataFrame(rows))


def t_exceptions() -> str:
    e = pd.read_csv(R / "backtest_exceptions.csv")
    s = summary().set_index(["split", "strategy"])
    g = e.groupby(["split", "check", "reason"]).size().reset_index(name="days")
    g["reason"] = g.reason.str.split(":").str[0]
    g["period days"] = [int(s.loc[(sp, "ml_battery"), "days"]) for sp in g.split]
    g["split"] = g.split.map({"test": "Oct 2026", "val": "Sept 2026", "rolling": "Oct 2025–Aug 2026"})
    return md(g.rename(columns={"split": "period", "check": "check that failed on the day"}))


def t_tuning() -> str:
    t = pd.read_csv(R / "decision_tuning.csv")
    t1 = t[t.stage == 1].sort_values("saving_combined_chf", ascending=False)
    keep = pd.concat([t1.head(3), t1[t1.is_default == True]])  # noqa: E712
    out = pd.DataFrame({"candidate (stage 1)": keep.candidate,
                        "saving rolling (CHF)": keep.saving_rolling_chf.map(chf),
                        "saving 1–29 Sept (CHF)": keep.saving_sept_chf.map(chf),
                        "gain vs block plan (CHF)": keep.vs_reference_chf.map(chf),
                        "95 % CI of gain": [f"{chf(a)} to {chf(b)}" for a, b in zip(keep.vs_reference_ci_low_chf, keep.vs_reference_ci_high_chf)]})
    return md(out)


def t_price_years() -> str:
    h = pd.read_parquet(P / "hourly_actuals.parquet")
    h["year"] = pd.to_datetime(h.delivery_date).dt.year
    h = h[(h.year >= 2019) & (pd.to_datetime(h.delivery_date) <= "2026-10-31")]
    g = h.groupby("year").agg(mean_price=("price_eur_mwh", "mean"), neg=("price_eur_mwh", lambda x: int((x < 0).sum())),
                              demand=("demand_mw", "mean"))
    out = pd.DataFrame({"year": g.index.astype(str), "mean CH price (EUR/MWh)": g.mean_price.map(f1),
                        "hours with negative price": g.neg, "mean Zurich demand (MW)": g.demand.map(f1)})
    out.loc[out.year == "2026", "year"] = "2026 (Jan–Oct)"
    return md(out)


def t_test_month_context() -> str:
    h = pd.read_parquet(P / "hourly_actuals.parquet")
    h["d"] = pd.to_datetime(h.delivery_date)
    rows = []
    for name, a, b in [("Sept 2026", "2026-09-01", "2026-09-30"), ("Oct 2026", "2026-10-01", "2026-10-31")]:
        s = h[(h.d >= a) & (h.d <= b)]
        day = s.groupby("d").price_eur_mwh.agg(["max", "min"])
        rows.append({"month": name, "mean price (EUR/MWh)": f1(s.price_eur_mwh.mean()),
                     "mean daily max − min (EUR/MWh)": f1((day["max"] - day["min"]).mean()),
                     "mean demand (MW)": f1(s.demand_mw.mean()),
                     "energy (GWh)": f1(s.demand_mw.sum() / 1000),
                     "mean EUR/CHF": f"{s.eurchf.mean():.4f}"})
    return md(pd.DataFrame(rows))


# ----------------------------------------------------------------------------- key numbers for the prose
def keynums() -> str:
    d = decomposition()
    s = summary().set_index(["split", "strategy"])
    dm, pm = metrics("demand"), metrics("price")

    def mae(m, split, mod, col="mae"):
        return m[(m.split == split) & (m.model == mod) & (m.block.astype(str) == "all")][col].iloc[0]

    pe = pd.read_csv(R / "backtest_price_error_sensitivity.csv")
    bs = pd.read_csv(R / "backtest_battery_sensitivity.csv")
    ds = pd.read_csv(R / "backtest_decision_sensitivity.csv")
    _, days, cost, year, year_days, year_cost = _year()
    ml = s.loc[("test", "ml_battery")]
    lines = [
        f"demand Oct MAE best {mae(dm,'test','best'):.2f} MW, MAPE {mae(dm,'test','best','mape_or_smape'):.2f} %, naive {mae(dm,'test','naive'):.2f} MW, gbm {mae(dm,'test','gbm'):.2f}",
        f"demand Sept MAE best {mae(dm,'val','best'):.2f}; rolling best {mae(dm,'rolling','best'):.2f}, naive {mae(dm,'rolling','naive'):.2f}",
        f"price Oct MAE best {mae(pm,'test','best'):.2f} EUR/MWh, sMAPE {mae(pm,'test','best','mape_or_smape'):.2f} %, naive {mae(pm,'test','naive'):.2f}, bias {mae(pm,'test','best','bias'):.2f}",
        f"price Sept MAE best {mae(pm,'val','best'):.2f}; rolling best {mae(pm,'rolling','best'):.2f}, gbm {mae(pm,'rolling','gbm'):.2f}, naive {mae(pm,'rolling','naive'):.2f}",
        f"Oct baseline cost CHF {chf(cost['test'])}; product cost CHF {chf(ml.total_cost_chf)}",
        f"Oct product saving CHF {chf(d.loc['test','total_saving_chf'])} = demand {chf(d.loc['test','demand_forecast_part_chf'])} + battery {chf(d.loc['test','battery_part_chf'])}",
        f"Oct saving share of baseline cost {100*d.loc['test','total_saving_chf']/cost['test']:.2f} %",
        f"Oct battery share of product saving {100*d.loc['test','battery_part_chf']/d.loc['test','total_saving_chf']:.0f} %",
        f"Oct ceiling saving CHF {chf(d.loc['test','ceiling_total_saving_chf'])}; % captured {d.loc['test','pct_ceiling_captured_total']:.0f} %; battery ceiling CHF {chf(d.loc['test','ceiling_battery_value_chf'])}, captured {d.loc['test','pct_ceiling_battery_value_captured']:.0f} %",
        f"Oct block-rule cost CHF {chf(d.loc['test','block_rule_cost_chf'])}; block oracle battery value CHF {chf(d.loc['test','block_perfect_battery_value_chf'])}",
        f"Oct forecast-error cost naive CHF {chf(d.loc['test','forecast_error_cost_naive_chf'])}, ML CHF {chf(d.loc['test','forecast_error_cost_ml_chf'])}",
        f"Oct CI product saving {chf(ml.saving_adj_ci_low_chf)} to {chf(ml.saving_adj_ci_high_chf)}; days cheaper than baseline {int(ml.days_cheaper_than_baseline)} of {int(ml.days)}",
        f"Oct charge cleared product {100*ml.share_charge_cleared:.0f} %, cycles {ml.cycles:.1f}",
        f"Oct per-day: saving CHF {chf(d.loc['test','total_saving_chf']/days['test'])}, battery CHF {chf(d.loc['test','battery_part_chf']/days['test'])}",
        f"Rolling per-day: saving CHF {chf(d.loc['rolling','total_saving_chf']/days['rolling'])}, battery CHF {chf(d.loc['rolling','battery_part_chf']/days['rolling'])}",
        f"Year (Oct 2025–Sep 2026, {year_days} days): saving CHF {chf(year['total_saving_chf'])}, demand {chf(year['demand_forecast_part_chf'])}, battery {chf(year['battery_part_chf'])}, ceiling {chf(year['ceiling_total_saving_chf'])}, ceiling battery {chf(year['ceiling_battery_value_chf'])}, baseline cost {chf(year_cost)}",
        f"Year battery share {100*year['battery_part_chf']/year['total_saving_chf']:.0f} %",
        f"price error slope CHF {pe.slope_chf_per_eur.iloc[0]:.0f} per EUR/MWh MAE per month; per day {pe.slope_chf_per_eur.iloc[0]/pe.days.iloc[0]:.0f}",
        f"policy gap to ceiling CHF {chf(pe.policy_gap_to_ceiling_chf.iloc[0])}; zero-noise battery value CHF {chf(pe.zero_noise_battery_value_chf.iloc[0])}",
        "battery size: " + "; ".join(f"{int(r.power_mw)}/{int(r.capacity_mwh)} -> {chf(r.battery_value_chf)}"
                                      for _, r in bs[bs.strategy == "ml_battery"].iterrows()),
        "imbalance: " + "; ".join(f"{r.value} -> saving {chf(r.saving_ml_battery_vs_baseline_chf)}, demand {chf(r.demand_forecast_part_chf)}"
                                   for _, r in ds[ds.parameter == "imbalance_factors"].iterrows()),
    ]
    for split in ["val", "rolling"]:
        lines.append(f"{split}: saving CHF {chf(d.loc[split,'total_saving_chf'])}, demand {chf(d.loc[split,'demand_forecast_part_chf'])}, battery {chf(d.loc[split,'battery_part_chf'])}, % ceiling {d.loc[split,'pct_ceiling_captured_total']:.0f} %, battery % {d.loc[split,'pct_ceiling_battery_value_captured']:.0f} %")
    ed = pd.read_csv(R / "experiments_demand.csv").set_index("experiment")
    for k in ed.index:
        if k.startswith(("S", "D4")):
            r = ed.loc[k]
            lines.append(f"demand exp '{k}': val {r.val_mae:.2f}, test {r.test_mae:.2f}")
    return "\n".join(lines)


TABLES = {
    "demand_metrics": lambda: t_model_metrics("demand"),
    "price_metrics": lambda: t_model_metrics("price"),
    "blocks": t_blocks,
    "dm_tests": t_dm,
    "bands": t_bands,
    "price_decision": t_price_decision,
    "worst_blocks": t_worst,
    "importance_demand": lambda: t_importance("demand"),
    "importance_price": lambda: t_importance("price"),
    "strategies_test": lambda: t_strategies("test"),
    "decomposition": t_decomposition,
    "year": t_year,
    "monthly": t_monthly,
    "battery_size": t_battery_size,
    "price_error": t_price_error,
    "decision_sens": t_decision_sens,
    "exceptions": t_exceptions,
    "tuning": t_tuning,
    "price_years": t_price_years,
    "test_month_context": t_test_month_context,
}

PAT = re.compile(r"(<!-- table:(\w+) -->\n)((?:(?!<!-- table:).)*?)(\n?<!-- /table -->)", re.S)


def process(path: Path, fill: bool) -> int:
    text = path.read_text(encoding="utf-8")
    cache: dict[str, str] = {}
    bad = 0

    def rep(m):
        nonlocal bad
        name = m.group(2)
        if name not in TABLES:
            print(f"{path.name}: unknown table '{name}'")
            bad += 1
            return m.group(0)
        new = cache.setdefault(name, TABLES[name]())
        if m.group(3).strip() != new.strip():
            bad += 1
            print(f"{path.name}: table '{name}' {'updated' if fill else 'DIFFERS from the result files'}")
        return m.group(1) + new + "\n<!-- /table -->"

    new_text = PAT.sub(rep, text)
    if fill and new_text != text:
        path.write_text(new_text, encoding="utf-8")
    found = len(PAT.findall(text))
    print(f"{path.name}: {found} tables checked, {bad} {'changed' if fill else 'out of date'}")
    return bad


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", nargs="*", default=None, help="markdown files whose tables are compared")
    ap.add_argument("--fill", nargs="*", default=None, help="markdown files whose tables are rewritten")
    a = ap.parse_args(argv)
    if a.check is None and a.fill is None:
        for name, f in TABLES.items():
            print(f"\n### {name}\n\n{f()}")
        print(f"\n### keynums\n\n{keynums()}")
        return 0
    bad = 0
    for p in a.fill or []:
        process(Path(p), fill=True)
    for p in a.check or []:
        bad += process(Path(p), fill=False)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
