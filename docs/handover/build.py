"""Build the project handover report: reports/Project_Handover_Report.pdf.

Run from the project folder:

    .venv/bin/python docs/handover/build.py            # build the PDF
    .venv/bin/python docs/handover/build.py --html     # also keep the HTML in docs/handover/out/

How it works
------------
1. The prose lives in ``docs/handover/content/*.md`` (one file per chapter, read in file-name order).
   It is plain Markdown plus a few placeholders:

   ``{{n:key}}``                a number or short text computed from the result files (see ``numbers()``)
   ``{{c:battery.power_mw}}``   a value from config.yaml
   ``{{e:demand:A0:cv_mae}}``   one cell of reports/experiments_<target>.csv (experiment code, column)
   ``{{t:name}}`` or ``{{t:name|caption}}``   a whole table (see ``tables()``)
   ``{{fig:file.png|caption}}``  a figure from reports/figures/
   ``{{img:path|caption|width}}`` any image in the repo (path relative to the project folder)
   ``{{svg:name|caption}}``      a diagram drawn in ``diagrams.py``

   An unknown placeholder stops the build, so no number can be left out or typed in by mistake.
2. Every number and table is read from ``reports/``, ``data/processed/``, ``models/``, ``config.yaml``,
   ``docs/`` and the source files at build time. ``reports/make_report_tables.py`` is reused for the
   tables that also appear in ``reports/report.md``.
3. The HTML is printed to PDF with headless Chromium (Playwright). A first pass finds the page of every
   chapter and section; a second pass writes those page numbers into the table of contents.
4. Links to repo files are checked (the file must exist) and written into the PDF as relative paths
   (relative to ``reports/``, where the PDF lives).

Reads only; writes only ``reports/Project_Handover_Report.pdf`` (and ``docs/handover/out/`` with --html).
"""
from __future__ import annotations

import argparse
import ast
import datetime as dt
import html
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import logging

import markdown
import numpy as np
import pandas as pd
import yaml

logging.getLogger("pypdf").setLevel(logging.ERROR)
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
R = ROOT / "reports"
P = ROOT / "data" / "processed"
OUT_PDF = R / "Project_Handover_Report.pdf"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import diagrams  # noqa: E402  (docs/handover/diagrams.py)


def _load_report_tables():
    spec = importlib.util.spec_from_file_location("make_report_tables", R / "make_report_tables.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MRT = _load_report_tables()
chf, f1, f2, pct, md_table = MRT.chf, MRT.f1, MRT.f2, MRT.pct, MRT.md


# ----------------------------------------------------------------------------- small helpers
def md_esc(s) -> str:
    """Make a value safe inside a Markdown table cell."""
    s = "" if s is None or (isinstance(s, float) and np.isnan(s)) else str(s)
    return s.replace("|", "&#124;").replace("\n", " ")


def df_md(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    out = ["| " + " | ".join(md_esc(c) for c in cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, r in df.iterrows():
        out.append("| " + " | ".join(md_esc(r[c]) for c in cols) + " |")
    return "\n".join(out)


def md_tables_in(path: Path) -> list[tuple[str, pd.DataFrame]]:
    """All pipe tables of a Markdown file as (nearest heading, DataFrame)."""
    lines = path.read_text(encoding="utf-8").splitlines()
    out, heading, i = [], "", 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("#"):
            heading = ln.lstrip("#").strip()
        if ln.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|$", lines[i + 1].strip()):
            head = [c.strip() for c in ln.strip().strip("|").split("|")]
            rows = []
            i += 2
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if len(cells) > len(head):  # an unescaped "|" inside the text (e.g. |p|) belongs to the last cell
                    cells = cells[:len(head) - 1] + ["|".join(cells[len(head) - 1:])]
                rows.append(cells + [""] * (len(head) - len(cells)))
                i += 1
            out.append((heading, pd.DataFrame([r[:len(head)] for r in rows], columns=head)))
            continue
        i += 1
    return out


def md_table_after(path: Path, heading_start: str) -> pd.DataFrame:
    for h, df in md_tables_in(path):
        if h.startswith(heading_start):
            return df
    raise KeyError(f"no table under heading '{heading_start}' in {path}")


def rel(p: Path) -> str:
    return p.resolve().relative_to(ROOT).as_posix()


def cfg() -> dict:
    return yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))


def notes_runtime(path: Path) -> str:
    m = re.search(r"runtime of this run: ([\d.]+) min", path.read_text(encoding="utf-8"))
    return m.group(1) if m else "–"


# ----------------------------------------------------------------------------- numbers
def numbers() -> dict[str, str]:
    """Every number the prose uses, by key. All read from the result files."""
    N: dict[str, str] = {}
    C = cfg()
    dm, pm = MRT.metrics("demand"), MRT.metrics("price")

    def m(mm, split, mod, col="mae"):
        return mm[(mm.split == split) & (mm.model == mod) & (mm.block.astype(str) == "all")][col].iloc[0]

    for tgt, mm in [("dem", dm), ("pri", pm)]:
        for split, sk in [("test", "test"), ("val", "val"), ("rolling", "roll")]:
            for mod in ["naive", "linear", "rf", "gbm", "best"]:
                N[f"{tgt}_{sk}_mae_{mod}"] = f2(m(mm, split, mod))
                N[f"{tgt}_{sk}_pct_{mod}"] = f2(m(mm, split, mod, "mape_or_smape"))
                N[f"{tgt}_{sk}_bias_{mod}"] = f2(m(mm, split, mod, "bias"))
                N[f"{tgt}_{sk}_rmse_{mod}"] = f2(m(mm, split, mod, "rmse"))
            N[f"{tgt}_{sk}_skill"] = f"{100 * (1 - m(mm, split, 'best') / m(mm, split, 'naive')):.0f}"
        N[f"{tgt}_test_ci_low"] = f2(m(mm, "test", "best", "mae_ci_low"))
        N[f"{tgt}_test_ci_high"] = f2(m(mm, "test", "best", "mae_ci_high"))
    for tgt in ["demand", "price"]:
        t = pd.read_csv(R / f"model_tests_{tgt}.csv")
        for _, r in t.iterrows():
            k = f"dm_{tgt[:3]}_{ {'val': 'val', 'test': 'test', 'rolling': 'roll'}[r.split]}_{r.model_b}"
            N[k + "_p"] = MRT.pval(r.p_value)
            N[k + "_days"] = str(int(r.n_days))

    d = MRT.decomposition()
    for split, sk in [("test", "test"), ("val", "val"), ("rolling", "roll")]:
        for col in d.columns:
            v = d.loc[split, col]
            if isinstance(v, (float, np.floating, int, np.integer)):
                N[f"{col}_{sk}"] = f"{v:.0f}" if col.startswith("pct_") else chf(v)
    s = MRT.summary().set_index(["split", "strategy"])
    for split, sk in [("test", "test"), ("val", "val"), ("rolling", "roll")]:
        for strat in MRT.STRAT_ORDER:
            r = s.loc[(split, strat)]
            short = {"baseline_naive_no_battery": "s1", "ml_no_battery": "s2", "naive_battery": "s3",
                     "ml_battery": "s4", "ml_battery_block_default": "s4b", "perfect_foresight_battery": "s5",
                     "perfect_foresight_hourly_daily_battery": "s5b", "perfect_foresight_hourly_battery": "s6",
                     "perfect_demand_no_battery": "s7"}[strat]
            N[f"{short}_cost_{sk}"] = chf(r.total_cost_chf)
            N[f"{short}_saving_{sk}"] = chf(r.saving_vs_baseline_adj_chf)
            N[f"{short}_penalty_{sk}"] = chf(r.imbalance_penalty_chf)
            N[f"{short}_imbcost_{sk}"] = chf(r.imbalance_cost_chf)
            N[f"{short}_cycles_{sk}"] = f1(r.cycles)
            N[f"{short}_idle_{sk}"] = str(int(r.days_battery_idle))
            N[f"{short}_pctceil_{sk}"] = "–" if pd.isna(r.pct_perfect_captured) else f"{r.pct_perfect_captured:.0f}"
            N[f"{short}_cilow_{sk}"] = chf(r.saving_adj_ci_low_chf)
            N[f"{short}_cihigh_{sk}"] = chf(r.saving_adj_ci_high_chf)
            N[f"{short}_days_{sk}"] = str(int(r.days))
            N[f"{short}_cheaper_{sk}"] = str(int(r.days_cheaper_than_baseline))
            N[f"{short}_batval_{sk}"] = chf(r.battery_value_adj_chf)
            N[f"{short}_cleared_{sk}"] = "–" if pd.isna(r.share_charge_cleared) else f"{100 * r.share_charge_cleared:.2f}"
    N["s4_decision"] = str(s.loc[("test", "ml_battery"), "decision"])
    N["pct_saving_of_baseline_test"] = f"{100 * d.loc['test', 'total_saving_chf'] / s.loc[('test', 'baseline_naive_no_battery'), 'total_cost_chf']:.2f}"
    N["pct_demand_of_saving_test"] = f"{100 * d.loc['test', 'demand_forecast_part_chf'] / d.loc['test', 'total_saving_chf']:.0f}"
    N["ratio_demand_battery_test"] = f"{d.loc['test', 'demand_forecast_part_chf'] / d.loc['test', 'battery_part_chf']:.1f}"
    N["ratio_demand_battery_roll"] = f"{d.loc['rolling', 'demand_forecast_part_chf'] / d.loc['rolling', 'battery_part_chf']:.1f}"

    # charge bids by count
    hh = pd.read_parquet(R / "backtest_hourly_test.parquet")
    hb = hh[(hh.strategy == "ml_battery") & (hh.charge_bid_mwh > 1e-9)]
    N["charge_bids_n"] = str(len(hb))
    N["charge_bids_cleared"] = str(int((hb.charge_cleared_mwh > 1e-9).sum()))
    N["charge_bids_cleared_pct"] = f"{100 * (hb.charge_cleared_mwh > 1e-9).mean():.2f}"

    ci = pd.read_csv(R / "backtest_ci_sensitivity.csv").set_index("split")
    for split, sk in [("test", "test"), ("val", "val"), ("rolling", "roll")]:
        N[f"ciblock_low_{sk}"] = chf(ci.loc[split, "ci_block_low_chf"])
        N[f"ciblock_high_{sk}"] = chf(ci.loc[split, "ci_block_high_chf"])
        N[f"autocorr_{sk}"] = f2(ci.loc[split, "lag1_autocorr_daily_saving"])
    N["ci_nboot"] = str(int(ci.loc["test", "n_boot"]))
    N["ci_blocklen"] = str(int(ci.loc["test", "block_length_days"]))

    _, days, cost, year, year_days, year_cost = MRT._year()
    N["year_days"] = str(year_days)
    N["year_saving"] = chf(year["total_saving_chf"])
    N["year_demand"] = chf(year["demand_forecast_part_chf"])
    N["year_battery"] = chf(year["battery_part_chf"])
    N["year_cost"] = chf(year_cost)
    N["year_pct"] = f"{100 * year['total_saving_chf'] / year_cost:.2f}"
    N["year_12x_oct"] = chf(12 * d.loc["test", "total_saving_chf"])
    N["days_roll"], N["days_val"], N["days_test"] = str(days["rolling"]), str(days["val"]), str(days["test"])

    ds = pd.read_csv(R / "backtest_decision_sensitivity.csv")
    for _, r in ds[ds.parameter == "imbalance_factors"].iterrows():
        k = r.value.replace("/", "_").replace(".", "")
        N[f"imb_{k}_saving"] = chf(r.saving_ml_battery_vs_baseline_chf)
        N[f"imb_{k}_demand"] = chf(r.demand_forecast_part_chf)
        N[f"imb_{k}_battery"] = chf(r.battery_value_ml_chf)
    for _, r in ds[ds.parameter == "charge_limit_factor"].iterrows():
        N[f"limit_{str(r.value).replace('.', '')}_bat"] = chf(r.battery_value_ml_battery_chf)
        N[f"limit_{str(r.value).replace('.', '')}_cleared"] = f"{100 * r.share_cleared_ml_battery:.0f}"
    for _, r in ds[ds.parameter == "allow_sell"].iterrows():
        N[f"sell_{str(r.value).lower()}_bat"] = chf(r.battery_value_ml_battery_chf)

    pe = pd.read_csv(R / "backtest_price_error_sensitivity.csv")
    N["pe_slope"] = f"{pe.slope_chf_per_eur.iloc[0]:.0f}"
    N["pe_slope_day"] = f"{pe.slope_chf_per_eur.iloc[0] / pe.days.iloc[0]:.0f}"
    for k in ["ml", "naive"]:
        r = pe[pe.forecast == k].iloc[0]
        N[f"pe_{k}_mae"] = f1(r.price_mae_eur_mwh)
        N[f"pe_{k}_lost"] = chf(r.lost_saving_chf)
    N["pe_policy_gap"] = chf(pe.policy_gap_to_ceiling_chf.iloc[0])
    N["pe_zero_noise_bat"] = chf(pe.zero_noise_battery_value_chf.iloc[0])

    bs = pd.read_csv(R / "backtest_battery_sensitivity.csv")
    b4 = bs[bs.strategy == "ml_battery"]
    per = b4.battery_value_chf / b4.capacity_mwh
    N["bs_per_mwh_min"], N["bs_per_mwh_max"] = chf(per.min()), chf(per.max())
    N["bs_sizes"] = ", ".join(f"{int(p)}/{int(c)}" for p, c in zip(b4.power_mw, b4.capacity_mwh))

    pdec = pd.read_csv(R / "decision_metrics_price.csv")
    r = pdec[(pdec.split == "test") & (pdec.model == "best")].iloc[0]
    N["pri_test_shape_mae"], N["pri_test_daymean_mae"] = f1(r.shape_mae), f1(r.daymean_mae)
    N["pri_test_rank"] = f2(r.rank_corr)

    t = pd.read_csv(R / "decision_tuning.csv")
    ch = t[t.chosen == True].iloc[0]  # noqa: E712
    N["tune_chosen"] = ch.candidate
    N["tune_cutoff"] = str(ch.cutoff)
    N["tune_days_roll"], N["tune_days_sept"] = str(int(ch.days_rolling)), str(int(ch.days_sept))
    N["tune_n_stage1"] = str(int((t.stage == 1).sum()))
    N["tune_n_stage2"] = str(int((t.stage == 2).sum()))
    st1 = t[t.stage == 1]
    win = st1[st1.stage_winner == True].iloc[0]  # noqa: E712
    N["tune_gain"] = chf(win.vs_reference_chf)
    N["tune_gain_lo"], N["tune_gain_hi"] = chf(win.vs_reference_ci_low_chf), chf(win.vs_reference_ci_high_chf)
    prot = t[(t.stage == 2) & (t.protect == "at_risk_bid") & (t.charge_limit == "0.9")]
    N["tune_protect_loss"] = chf(-prot.vs_reference_chf.iloc[0]) if len(prot) else "–"

    # features
    import pyarrow.parquet as pq
    f = pq.ParquetFile(P / "features.parquet")
    fe = pd.read_parquet(P / "features.parquet", columns=["delivery_date", "block", "weather_is_forecast"])
    N["feat_rows"] = f"{f.metadata.num_rows:,}"
    N["feat_cols"] = str(f.metadata.num_columns)
    N["feat_days"] = f"{fe.delivery_date.nunique():,}"
    N["feat_first"] = str(pd.to_datetime(fe.delivery_date).min().date())
    N["feat_last"] = str(pd.to_datetime(fe.delivery_date).max().date())
    N["feat_fc_share"] = f"{100 * fe.weather_is_forecast.mean():.1f}"
    from src.features import feature_sets as fs
    N["n_demand_features"] = str(len(fs.DEMAND_FEATURES))
    N["n_price_features"] = str(len(fs.PRICE_FEATURES))
    N["n_eu_features"] = str(len(fs.EU_WEATHER_FEATURES))
    ha = pd.read_parquet(P / "hourly_actuals.parquet")
    N["hourly_actuals_rows"] = f"{len(ha):,}"
    hoct = ha[(pd.to_datetime(ha.delivery_date) >= C["periods"]["test_start"]) & (pd.to_datetime(ha.delivery_date) <= C["periods"]["test_end"])]
    N["oct_mean_demand"] = f1(hoct.demand_mw.mean())
    N["oct_energy_gwh"] = f1(hoct.demand_mw.sum() / 1000)
    N["oct_mean_price"] = f1(hoct.price_eur_mwh.mean())

    # ewz data checks
    cc = md_table_after(R / "data_checks" / "demand_ewz_crosscheck.md", "Cross-check")
    cc = cc.set_index("shift of Netzebenen")
    N["ewz_corr_0"] = cc.loc["+0 min", "correlation"]
    N["ewz_corr_p15"] = cc.loc["+15 min", "correlation"]
    N["ewz_corr_m15"] = cc.loc["-15 min", "correlation"]
    dst = md_table_after(R / "data_checks" / "demand_ewz_crosscheck.md", "Autumn DST")
    N["dst_pairs"] = str(len(dst))
    N["dst_wrong"] = str(int((dst["file order chronological"] == "False").sum()))
    gaps = md_table_after(R / "data_checks.md", "Gaps in the raw data")
    N["ewz_filled_intervals"] = str(sum(int(x) for x in gaps.intervals))
    N["ewz_filled_days"] = str(len(gaps))
    N["dst_right"] = str(len(dst) - int((dst["file order chronological"] == "False").sum()))
    cct = (R / "data_checks" / "demand_ewz_crosscheck.md").read_text(encoding="utf-8")
    N["ewz_median_diff_kwh"] = re.search(r"abs\. difference: median ([\d.]+) kWh", cct).group(1)
    yrs = md_table_after(R / "data_checks.md", "Yearly mean load")
    ym = yrs.set_index("year")["mean MW"].astype(float)
    N["ewz_2019_above_pct"] = f"{100 * (ym.loc['2019'] / ym.drop('2019').mean() - 1):.0f}"
    aw = (ROOT / "docs" / "assumptions_weather.md").read_text(encoding="utf-8")
    mm_ = re.search(r"MAE vs station is ([\d.]+) W/m² with this shift vs ([\d.]+) W/m²", aw)
    N["rad_mae_shift"], N["rad_mae_noshift"] = mm_.group(1), mm_.group(2)

    # runtimes and tests
    N["rt_demand"] = notes_runtime(R / "model_notes_demand.md")
    N["rt_price"] = notes_runtime(R / "model_notes_price.md")
    tl = test_inventory()
    N["n_tests"] = str(sum(x["n_collected"] for x in tl))
    N["n_test_funcs"] = str(sum(len(x["tests"]) for x in tl))
    N["n_test_files"] = str(len(tl))
    N["n_src_files"] = str(len([p for p in (ROOT / "src").rglob("*.py") if p.name != "__init__.py"]))
    N["n_src_lines"] = f"{sum(len(p.read_text(encoding='utf-8').splitlines()) for p in (ROOT / 'src').rglob('*.py')):,}"
    N["n_figures"] = str(len(list((R / "figures").glob("*.png"))))
    N["n_day_files"] = str(len(list((ROOT / "web" / "public" / "data" / "days").glob("*.json"))))
    N["n_events"] = str(len(pd.read_csv(ROOT / "data" / "manual" / "events_zurich.csv")))
    N["build_date"] = dt.date.today().isoformat()
    css = (ROOT / "web" / "src" / "styles.css").read_text(encoding="utf-8")
    for key, var in [("col_stored", "charge"), ("col_used", "use"), ("col_price", "price"),
                     ("col_saving", "saving"), ("col_demand", "demand")]:
        N[key] = re.search(rf"--{var}:\s*(#[0-9a-fA-F]{{6}})", css).group(1).upper()
    pbest = json.loads((ROOT / "models" / "price_best_params.json").read_text())["best"]
    dbest = json.loads((ROOT / "models" / "demand_best_params.json").read_text())["best"]
    N["price_band_factor"] = str(pbest["band_factor"])
    N["price_refit_days"] = str(pbest["refit_every_days"])
    N["price_linear_pct"] = f"{100 * pbest['linear_weight']:.0f}"
    N["demand_linear_pct"] = f"{100 * dbest['linear_weight']:.0f}"
    N["price_seeds"], N["demand_seeds"] = str(pbest["n_seeds"]), str(dbest["n_seeds"])
    rl = (ROOT / "docs" / "review_log.md").read_text(encoding="utf-8")
    N["dem_old_oct_mae"] = re.search(r"October error moved from ([\d.]+) to", rl).group(1)
    N["price_single_fit_mae"] = re.search(r"single fit alone scores ([\d.]+) EUR/MWh", rl).group(1)
    N["cycle_cap_cost"] = re.search(r"about CHF ([\d,]+) of battery saving", rl).group(1)
    N["ceiling_eur_gap"] = re.search(r"would lower it by CHF ([\d,]+)", rl).group(1)
    bat, imb = C["battery"], C["imbalance"]
    usable = (bat["soc_max_frac"] - bat["soc_min_frac"]) * bat["capacity_mwh"]
    eta = bat["round_trip_efficiency"] ** 0.5
    N["imb_short_pct"] = f"{100 * (imb['shortage_price_factor'] - 1):.0f}"
    N["imb_surplus_pct"] = f"{100 * (1 - imb['surplus_price_factor']):.0f}"
    N["soc_min_pct"], N["soc_max_pct"] = f"{100 * bat['soc_min_frac']:.0f}", f"{100 * bat['soc_max_frac']:.0f}"
    N["soc_start_pct"] = f"{100 * bat['soc_start_frac']:.0f}"
    N["soc_start_mwh"] = f"{bat['soc_start_frac'] * bat['capacity_mwh']:.0f}"
    N["soc_min_mwh"], N["soc_max_mwh"] = f"{bat['soc_min_frac'] * bat['capacity_mwh']:.0f}", f"{bat['soc_max_frac'] * bat['capacity_mwh']:.0f}"
    N["rte_pct"] = f"{100 * bat['round_trip_efficiency']:.0f}"
    N["eta_one_way"] = f"{eta:.3f}"
    N["usable_mwh"] = f"{usable:.0f}"
    N["full_swing_mwh"] = f"{usable * eta:.2f}"
    N["cycle_excess_pct"] = f"{100 * (1 / eta - 1):.0f}"
    n_oct_days = hoct.delivery_date.nunique()
    N["oct_daily_mwh"] = f"{hoct.demand_mw.sum() / n_oct_days:,.0f}"
    N["battery_share_of_day"] = f"{100 * usable / (hoct.demand_mw.sum() / n_oct_days):.2f}"
    N["oct_cycles_full_swings"] = f"{float(s.loc[('test', 'ml_battery'), 'discharged_mwh']) / (usable * eta):.2f}"

    # battery level carried from day to day (backtest.csv): the day of the test month that ended furthest from the target
    bt = pd.read_csv(R / "backtest.csv")
    target = bat["soc_start_frac"] * bat["capacity_mwh"]
    pr = bt[(bt.split == "test") & (bt.strategy == "ml_battery")].sort_values("delivery_date").reset_index(drop=True)
    off = (pr.soc_end_mwh - target).abs()
    k = int(off.idxmax())
    N["soc_ex_day"] = f"{pd.Timestamp(pr.delivery_date[k]):%-d %B %Y}"
    N["soc_ex_end"] = f"{pr.soc_end_mwh[k]:.3f}"
    N["soc_ex_next"] = f"{pd.Timestamp(pr.delivery_date[k + 1]):%-d %B}" if k + 1 < len(pr) else "–"
    N["soc_ex_next_start"] = f"{pr.soc_start_mwh[k + 1]:.3f}" if k + 1 < len(pr) else "–"
    N["soc_off_days_test"] = str(int((off > 1e-6).sum()))
    N["soc_relaxed_all"] = str(int(bt.soc_target_relaxed.astype(bool).sum()))
    # strategy 6 as the cheapest strategy (inventory-adjusted CHF) in each evaluated period
    sa = MRT.summary()
    per = [(sp, g.set_index("strategy")["total_cost_adj_chf"]) for sp, g in sa.groupby("split")]
    N["ceiling_cheapest_periods"] = f"{sum(int(t.idxmin() == 'perfect_foresight_hourly_battery') for _, t in per)} of {len(per)}"
    # CH 15-minute switch, from the loader's data check
    pc = (R / "data_checks" / "price_ch_hourly.md").read_text(encoding="utf-8")
    t15 = pd.Timestamp(re.search(r"first 15-min value in source \(UTC\): ([\d\- :+]+)", pc).group(1).strip())
    N["ch15_utc"] = f"{t15:%-d %b %Y %H:%M} UTC"
    N["ch15_local"] = f"{t15.tz_convert('Europe/Zurich'):%-d %b %Y %H:%M} Zurich time"
    N["ch15_local_day"] = f"{t15.tz_convert('Europe/Zurich'):%-d %B %Y}"
    ev = pd.read_csv(ROOT / "data" / "manual" / "events_zurich.csv")
    N["n_event_dates"] = str(ev["date"].nunique())
    return N


# ----------------------------------------------------------------------------- inventories
def test_inventory() -> list[dict]:
    """Every test file with its tests (docstring or readable name) and the collected count."""
    counts = {}
    try:
        out = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:warnings",
                              "-p", "no:cacheprovider"], cwd=ROOT, capture_output=True, text=True, timeout=300).stdout
        for ln in out.splitlines():
            mm = re.match(r"^(tests/\S+\.py): (\d+)$", ln.strip())
            if mm:
                counts[mm.group(1)] = int(mm.group(2))
    except Exception:  # pragma: no cover - collection is only for the counts
        pass
    res = []
    for fpath in sorted((ROOT / "tests").glob("test_*.py")):
        mod = ast.parse(fpath.read_text(encoding="utf-8"))
        tests = []
        for node in mod.body:
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                doc = ast.get_docstring(node)
                params = 0
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Call) and getattr(dec.func, "attr", "") == "parametrize" and len(dec.args) > 1:
                        try:
                            params = len(ast.literal_eval(dec.args[1]))
                        except Exception:
                            params = -1
                name = node.name[5:].replace("_", " ")
                tests.append({"name": node.name, "what": (doc.split("\n\n")[0].replace("\n", " ") if doc else name.capitalize()),
                              "params": params})
        doc = ast.get_docstring(mod) or ""
        res.append({"file": rel(fpath), "doc": doc.split("\n\n")[0].replace("\n", " "), "tests": tests,
                    "n_collected": counts.get(rel(fpath), len(tests))})
    return res


def src_inventory() -> list[dict]:
    files = sorted(p for p in (ROOT / "src").rglob("*.py") if "__pycache__" not in p.parts)
    files += [ROOT / "api" / "server.py", ROOT / "reports" / "make_report_tables.py"]
    res = []
    for fpath in files:
        text = fpath.read_text(encoding="utf-8")
        if not text.strip():
            continue
        mod = ast.parse(text)
        doc = (ast.get_docstring(mod) or "").strip()
        first = doc.split("\n\n")[0].replace("\n", " ")
        pub = [n.name for n in mod.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and not n.name.startswith("_")]
        res.append({"file": rel(fpath), "lines": len(text.splitlines()), "doc": first, "public": pub})
    return res


def module_cli(fpath: Path) -> str:
    return "python -m " + rel(fpath)[:-3].replace("/", ".")


# ----------------------------------------------------------------------------- tables
def tables(N: dict) -> dict:
    T = {name: fn for name, fn in MRT.TABLES.items()}
    C = cfg()

    def exp_table(target: str) -> str:
        e = pd.read_csv(R / f"experiments_{target}.csv")
        pcol = "val_mape" if target == "demand" else "val_smape"
        out = pd.DataFrame({
            "experiment": e.experiment, "kind": e.kind,
            "Sept MAE": e.val_mae.map(f2), "Sept bias": e.val_bias.map(f2),
            "CV MAE (5 folds)": e.cv_mae.map(f2), "CV MAE (last 2)": e.cv_mae_last2.map(f2),
            "Oct MAE (sensitivity only)": e.test_mae.map(f2),
        })
        return df_md(out)

    T["experiments_demand"] = lambda: exp_table("demand")
    T["experiments_price"] = lambda: exp_table("price")

    def special_days():
        return df_md(md_table_after(R / "model_notes_demand.md", "Error on special days"))
    T["special_days"] = special_days

    def ewz_shift():
        return df_md(md_table_after(R / "data_checks" / "demand_ewz_crosscheck.md", "Cross-check"))
    T["ewz_shift"] = ewz_shift

    def dst_pairs():
        dd = md_table_after(R / "data_checks" / "demand_ewz_crosscheck.md", "Autumn DST")
        return df_md(dd.drop(columns=[c for c in dd.columns if c == "method"]))
    T["dst_pairs"] = dst_pairs

    def ewz_years():
        return df_md(md_table_after(R / "data_checks.md", "Yearly mean load"))
    T["ewz_years"] = ewz_years

    def tuning_all():
        t = pd.read_csv(R / "decision_tuning.csv")
        out = pd.DataFrame({"stage": t.stage, "candidate": t.candidate,
                            "saving rolling + 1–29 Sept (CHF)": t.saving_combined_chf.map(chf),
                            "vs stage reference (CHF)": t.vs_reference_chf.map(chf),
                            "95 % CI": [f"{chf(a)} to {chf(b)}" for a, b in zip(t.vs_reference_ci_low_chf, t.vs_reference_ci_high_chf)],
                            "chosen": np.where(t.chosen, "yes", "")})
        return df_md(out)
    T["tuning_all"] = tuning_all

    def feature_groups():
        from src.features import feature_sets as fs
        groups = [("Calendar, events, football, COVID", fs.CALENDAR_FEATURES, "both"),
                  ("Demand lags (Zurich, up to end of D−1)", fs.DEMAND_LAG_FEATURES, "demand (some in price)"),
                  ("Weather of the delivery block/day (hybrid)", fs.WEATHER_FEATURES, "both"),
                  ("Past observed weather", fs.PAST_WEATHER_FEATURES, "both"),
                  ("Solar (lagged) and EVs", fs.SOLAR_EV_FEATURES, "demand (solar also price)"),
                  ("CH price of day D and history", fs.PRICE_LAG_FEATURES, "price"),
                  ("Neighbour prices DE/FR/AT/IT (day D)", fs.NEIGHBOUR_FEATURES, "price"),
                  ("Gas, CO₂, EUR/CHF, reservoirs", fs.FUEL_HYDRO_FEATURES, "price"),
                  ("Swiss system of D−1 (load, hydro, nuclear, solar)", fs.SWISS_SYSTEM_FEATURES, "price"),
                  ("European weather forecasts (eu_*)", fs.EU_WEATHER_FEATURES, "price")]
        rows = [{"group": g, "columns": len(cols), "used by": u,
                 "examples": ", ".join(f"`{c}`" for c in cols[:4]) + (" …" if len(cols) > 4 else "")} for g, cols, u in groups]
        return df_md(pd.DataFrame(rows))
    T["feature_groups"] = feature_groups

    def config_table():
        """config.yaml line by line: key, value, the file's own comment, our explanation, where it is read."""
        expl = yaml.safe_load((HERE / "content" / "config_explain.yaml").read_text(encoding="utf-8"))
        rows, stack = [], []
        src_text = {p: p.read_text(encoding="utf-8") for p in list((ROOT / "src").rglob("*.py")) + [ROOT / "api" / "server.py"]}
        for ln in (ROOT / "config.yaml").read_text(encoding="utf-8").splitlines():
            if not ln.strip() or ln.strip().startswith("#") or ln.strip().startswith("- ["):
                continue
            indent = len(ln) - len(ln.lstrip())
            body, _, comment = ln.strip().partition(" #")
            key, _, val = body.partition(":")
            level = indent // 2
            stack = stack[:level] + [key.strip()]
            full = ".".join(stack)
            val = val.strip()
            if full == "blocks":
                val = ", ".join(f"{a:02d}–{b:02d}" for a, b in C["blocks"])
            leaf = key.strip()
            used = sorted({rel(p).split("/")[-1] for p, t in src_text.items()
                           if re.search(rf"[\"']{re.escape(leaf)}[\"']", t)})
            rows.append({"key": f"`{full}`", "value": md_esc(val.strip('"')) or "(section)",
                         "comment in the file": md_esc(comment.strip()),
                         "what it means": md_esc(expl.get(full, "")),
                         "read in": ", ".join(used[:4]) + (" …" if len(used) > 4 else "")})
        return df_md(pd.DataFrame(rows))
    T["config"] = config_table

    def src_index():
        rows = []
        for x in src_inventory():
            pub = ", ".join(f"`{p}`" for p in x["public"][:8]) + (f" (+{len(x['public']) - 8})" if len(x["public"]) > 8 else "")
            doc = x["doc"]
            if len(doc) > 260:
                doc = doc[:257].rsplit(" ", 1)[0] + " …"
            rows.append({"file": f"`{x['file']}`", "lines": x["lines"], "what it does (module docstring)": doc,
                         "main functions / classes": pub})
        return df_md(pd.DataFrame(rows))
    T["src_index"] = src_index

    def tests_summary():
        rows = [{"file": f"`{x['file']}`", "tests (functions)": len(x["tests"]), "collected (with parameters)": x["n_collected"],
                 "what the file checks": x["doc"]} for x in test_inventory()]
        return df_md(pd.DataFrame(rows))
    T["tests_summary"] = tests_summary

    def tests_full():
        parts = []
        for x in test_inventory():
            rows = [{"test": f"`{t['name']}`", "what it checks": t["what"] + (f" ({t['params']} cases)" if t["params"] > 1 else "")}
                    for t in x["tests"]]
            parts.append(f"#### `{x['file']}`\n\n{x['doc']}\n\n" + df_md(pd.DataFrame(rows)))
        return "\n\n".join(parts)
    T["tests_full"] = tests_full

    def web_files():
        base = ROOT / "web" / "public" / "data"
        rows = []
        for fpath in sorted(base.glob("*.json")):
            rows.append({"file": f"`{rel(fpath)}`", "size (kB)": f"{fpath.stat().st_size / 1024:,.0f}"})
        days = sorted((base / "days").glob("*.json"))
        if days:
            rows.append({"file": f"`web/public/data/days/` ({len(days)} files, {days[0].stem} … {days[-1].stem})",
                         "size (kB)": f"{sum(p.stat().st_size for p in days) / 1024:,.0f} in total"})
        return df_md(pd.DataFrame(rows))
    T["web_files"] = web_files

    def web_types():
        text = (ROOT / "web" / "src" / "data" / "types.ts").read_text(encoding="utf-8")
        rows = []
        for mm in re.finditer(r"export (interface|type) (\w+)\s*(=\s*([^;]+);|\{)", text):
            kind, name = mm.group(1), mm.group(2)
            if kind == "type":
                desc = mm.group(4).strip()
                nf = "–"
            else:
                start = mm.end()
                depth, i = 1, start
                while depth and i < len(text):
                    depth += {"{": 1, "}": -1}.get(text[i], 0)
                    i += 1
                body = text[start:i - 1]
                if "\n" in body.strip():
                    fields = re.findall(r"^\s{2}(\w+)\??:", body, re.M)
                else:  # one-line interface, e.g. { date: string; battery: BatterySettings }
                    fields = re.findall(r"(\w+)\??\s*:", body)
                nf = str(len(fields))
                desc = ", ".join(fields[:7]) + (" …" if len(fields) > 7 else "")
            rows.append({"name": f"`{name}`", "kind": kind, "fields": nf, "first fields / definition": md_esc(desc)})
        return df_md(pd.DataFrame(rows))
    T["web_types"] = web_types

    def web_routes():
        rows = []
        for fpath in sorted((ROOT / "web" / "src" / "routes").glob("*.tsx")):
            rows.append({"file": f"`{rel(fpath)}`", "lines": len(fpath.read_text(encoding="utf-8").splitlines())})
        for sub in ["charts", "ui", "data", "lib"]:
            for fpath in sorted((ROOT / "web" / "src" / sub).glob("*.ts*")):
                rows.append({"file": f"`{rel(fpath)}`", "lines": len(fpath.read_text(encoding="utf-8").splitlines())})
        return df_md(pd.DataFrame(rows))
    T["web_routes"] = web_routes

    def review_tables():
        """docs/review_log.md, every finding with its decision split into a status word and the detail."""
        text = (ROOT / "docs" / "review_log.md").read_text(encoding="utf-8")
        parts, n = [], 0
        sections = re.split(r"^## ", text, flags=re.M)[1:]
        for sec in sections:
            title, _, body = sec.partition("\n")
            sub_tables = md_tables_in_text(body)
            parts.append(f"### {title.strip()}")
            for intro, df in sub_tables:
                if intro:
                    parts.append(intro)
                rows = []
                for _, r in df.iterrows():
                    n += 1
                    dec = r.iloc[1]
                    mm = re.match(r"^\*\*(.+?)\*\*\s*(.*)$", dec)
                    status, detail = (mm.group(1).rstrip(".:"), mm.group(2)) if mm else ("–", dec)
                    rows.append({"#": f"R{n:02d}", "finding": r.iloc[0], "decision": status, "why / effect": detail})
                parts.append(df_md(pd.DataFrame(rows)))
            checked = re.findall(r"^(Checked and found correct.*?)(?:\n\n|\Z)", body, re.S | re.M)
            for c in checked:
                parts.append("*" + c.replace("\n", " ").strip() + "*")
        N["n_review_findings"] = str(n)
        return "\n\n".join(parts)
    T["review_log"] = review_tables

    def final_findings():
        text = (ROOT / "prompts" / "briefs" / "final_review_findings.md").read_text(encoding="utf-8")
        rows = []
        for mm in re.finditer(r"^(M\d|m\d)\. (.*?)(?=^\S|\Z)", text, re.S | re.M):
            body = " ".join(x.strip() for x in mm.group(2).splitlines())
            dec = re.search(r"(DECISION:.*?)(?=Fix:|$)", body)
            fix = re.search(r"(Fix:.*)$", body)
            finding = re.split(r"DECISION:|Fix:", body)[0].strip()
            rows.append({"id": mm.group(1), "finding (as the reviewer reported it)": finding,
                         "orchestrator's instruction": ((dec.group(1) if dec else "") + " " + (fix.group(1) if fix else "")).strip()})
        return df_md(pd.DataFrame(rows))
    T["final_findings"] = final_findings

    def key_numbers():
        spec = yaml.safe_load((HERE / "content" / "key_numbers.yaml").read_text(encoding="utf-8"))
        rows = []
        for item in spec:
            files = item["file"] if isinstance(item["file"], list) else [item["file"]]
            rows.append({"number": item["label"], "value": N[item["key"]] + (" " + item.get("unit", "") if item.get("unit") else ""),
                         "source file": " + ".join(f"`{f_}`" for f_ in files), "column / how": md_esc(item["how"])})
        return df_md(pd.DataFrame(rows))
    T["key_numbers"] = key_numbers

    def sources_inventory():
        rows = []
        for fpath in sorted(P.glob("*.parquet")):
            try:
                import pyarrow.parquet as pq
                md_ = pq.ParquetFile(fpath).metadata
                rows.append({"processed table": f"`{rel(fpath)}`", "rows": f"{md_.num_rows:,}", "columns": md_.num_columns,
                             "size (kB)": f"{fpath.stat().st_size / 1024:,.0f}"})
            except Exception:
                pass
        return df_md(pd.DataFrame(rows))
    T["processed_tables"] = sources_inventory

    def raw_dirs():
        rows = []
        if not (ROOT / "data" / "raw").is_dir():
            if not getattr(raw_dirs, "warned", False):
                print("raw cache unavailable (data/raw/ is missing): the raw-folder table says so and the build continues")
                raw_dirs.warned = True
            return df_md(pd.DataFrame([{"raw folder": "`data/raw/` is not present on this machine (raw cache unavailable)",
                                        "files": "–", "size (MB)": "–"}]))
        for dpath in sorted((ROOT / "data" / "raw").iterdir()):
            if dpath.is_dir():
                fl = [p for p in dpath.rglob("*") if p.is_file()]
                rows.append({"raw folder": f"`{rel(dpath)}/`", "files": len(fl), "size (MB)": f"{sum(p.stat().st_size for p in fl) / 1e6:.1f}"})
        return df_md(pd.DataFrame(rows))
    T["raw_dirs"] = raw_dirs

    def models_files():
        rows = []
        for fpath in sorted((ROOT / "models").glob("*")):
            rows.append({"file": f"`{rel(fpath)}`", "size (kB)": f"{fpath.stat().st_size / 1024:,.0f}"})
        return df_md(pd.DataFrame(rows))
    T["models_files"] = models_files

    def best_params():
        rows = []
        for tgt in ["demand", "price"]:
            b = json.loads((ROOT / "models" / f"{tgt}_best_params.json").read_text())["best"]
            for k in ["transform", "reference_col", "weather", "n_seeds", "objective", "linear_weight", "linear_alpha",
                      "half_life_years", "walk_forward", "refit_every_days", "band_factor", "drop_features"]:
                if k in b:
                    rows.append({"model": tgt, "setting": f"`{k}`", "value": md_esc(json.dumps(b[k]))})
            g = b.get("gbm_params", {})
            rows.append({"model": tgt, "setting": "`gbm_params`",
                         "value": md_esc(", ".join(f"{k}={v}" for k, v in g.items()))})
        return df_md(pd.DataFrame(rows))
    T["best_params"] = best_params

    return T


def md_tables_in_text(body: str) -> list[tuple[str, pd.DataFrame]]:
    tmp = Path(tempfile.mkstemp(suffix=".md")[1])
    tmp.write_text(body, encoding="utf-8")
    out = []
    lines = body.splitlines()
    tabs = md_tables_in(tmp)
    tmp.unlink()
    # intro text = the non-table paragraph right before each table
    paras, cur = [], []
    for ln in lines:
        if ln.startswith("|"):
            if cur:
                paras.append(" ".join(cur))
                cur = []
            paras.append("<TABLE>")
        elif not ln.strip():
            if cur:
                paras.append(" ".join(cur))
                cur = []
        else:
            cur.append(ln.strip())
    intros, last = [], ""
    prev = None
    for ptxt in paras:
        if ptxt == "<TABLE>":
            if prev != "<TABLE>":
                intros.append(last)
            last = ""
        elif not ptxt.startswith("Checked and found correct"):
            last = ptxt
        prev = ptxt
    for i, (_, df) in enumerate(tabs):
        out.append((intros[i] if i < len(intros) else "", df))
    return out


# ----------------------------------------------------------------------------- placeholders
PH = re.compile(r"\{\{(\w+):(.*?)\}\}", re.S)
PH_SIMPLE = re.compile(r"\{\{([nce]):([^{}]*?)\}\}")


class Builder:
    def __init__(self, N, T, tmpdir: Path):
        self.N, self.T, self.tmp = N, T, tmpdir
        self.C = cfg()
        self.fig_no = 0
        self.tab_cache: dict[str, str] = {}
        self.missing_links: list[str] = []
        self.used_figs: list[str] = []

    def fig_html(self, src: str, caption: str, width: str = "100%") -> str:
        self.fig_no += 1
        cap = markdown.markdown(caption).removeprefix("<p>").removesuffix("</p>") if caption else ""
        return (f'\n<figure style="width:{width}"><img src="{src}" alt="">'
                f'<figcaption><b>Figure {self.fig_no}.</b> {cap}</figcaption></figure>\n')

    def repl(self, mm) -> str:
        kind, arg = mm.group(1), mm.group(2).strip()
        if kind == "n":
            if arg not in self.N:
                raise KeyError(f"unknown number key '{arg}'")
            return self.N[arg]
        if kind == "c":
            v = self.C
            for k in arg.split("."):
                v = v[k]
            return str(v)
        if kind == "e":
            tgt, code, col = arg.split(":")
            e = pd.read_csv(R / f"experiments_{tgt}.csv")
            row = e[e.experiment.str.split().str[0] == code]
            if row.empty:
                raise KeyError(f"unknown experiment {arg}")
            return f2(row[col].iloc[0])
        if kind == "t":
            name, _, caption = arg.partition("|")
            if name not in self.T:
                raise KeyError(f"unknown table '{name}'")
            if name not in self.tab_cache:
                self.tab_cache[name] = self.T[name]()
            capi = markdown.markdown(caption).removeprefix("<p>").removesuffix("</p>") if caption else ""
            cap = f'\n\n<p class="tcap">{capi}</p>\n' if caption else "\n"
            return f"\n\n<div class=\"tbl tbl-{name}\" markdown=\"1\">\n\n{self.tab_cache[name]}\n\n</div>{cap}\n"
        if kind == "fig":
            fname, _, caption = arg.partition("|")
            fpath = R / "figures" / fname
            if not fpath.exists():
                raise FileNotFoundError(fpath)
            self.used_figs.append(fname)
            caption = caption + f" <span class=\"src\">(`reports/figures/{fname}`)</span>"
            return self.fig_html(fpath.as_uri(), caption)
        if kind == "img":
            parts = arg.split("|")
            fpath = (ROOT / parts[0]) if not parts[0].startswith("tmp:") else self.tmp / parts[0][4:]
            if not fpath.exists():
                raise FileNotFoundError(fpath)
            width = parts[2] if len(parts) > 2 else "100%"
            return self.fig_html(fpath.as_uri(), parts[1] if len(parts) > 1 else "", width)
        if kind == "svg":
            name, _, caption = arg.partition("|")
            svg = getattr(diagrams, name)()
            self.fig_no += 1
            cap = markdown.markdown(caption).removeprefix("<p>").removesuffix("</p>")
            return (f'\n<figure class="svg">{svg}<figcaption><b>Figure {self.fig_no}.</b> {cap}</figcaption></figure>\n')
        raise KeyError(f"unknown placeholder kind '{kind}'")

    def render(self, text: str) -> str:
        # tables first (they may contain number placeholders), then everything else
        text = PH_SIMPLE.sub(self.repl, text)  # numbers first: they may sit inside a caption
        for _ in range(3):
            new = PH.sub(self.repl, text)
            if new == text:
                break
            text = new
        return text


LINKABLE = re.compile(r"^(src|docs|reports|tests|web|api|models|data|prompts|notebooks)/[\w./-]*$|"
                      r"^(config\.yaml|README\.md|PITCH\.md|day_ahead_planning\.md|requirements\.(in|txt)|pytest\.ini|\.gitignore)$")


def link_code(html_text: str, b: Builder) -> str:
    def rep(mm):
        inner = mm.group(1)
        raw = html.unescape(inner)
        if not LINKABLE.match(raw) or "*" in raw or "<" in raw:
            return mm.group(0)
        fpath = ROOT / raw.rstrip("/")
        if not fpath.exists():
            b.missing_links.append(raw)
            return mm.group(0)
        return f'<a class="repo" href="{fpath.as_uri()}"><code>{inner}</code></a>'
    # only inline code, not code blocks
    parts = re.split(r"(<pre>.*?</pre>)", html_text, flags=re.S)
    return "".join(p if p.startswith("<pre>") else re.sub(r"<code>([^<]+)</code>", rep, p) for p in parts)


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def build_html(N, T, tmpdir: Path, pages: dict | None) -> tuple[str, list, Builder]:
    b = Builder(N, T, tmpdir)
    files = sorted((HERE / "content").glob("*.md"))
    chapters, toc = [], []
    md_ext = ["tables", "fenced_code", "md_in_html", "attr_list", "sane_lists"]
    page_css = []
    for i, fpath in enumerate(files):
        text = b.render(fpath.read_text(encoding="utf-8"))
        first = text.lstrip().splitlines()[0]
        if not first.startswith("# "):
            raise ValueError(f"{fpath.name} must start with '# Title'")
        title = first[2:].strip()
        body = text.lstrip().split("\n", 1)[1]
        cls = "front" if fpath.name.startswith("00") else "chapter"
        cid = f"c{i:02d}"
        # section headings: add ids and page markers
        heads = []

        def h2(mm):
            t = mm.group(1).strip()
            hid = f"{cid}-{slug(t)}"[:60]
            heads.append((t, hid))
            return f'\n<h2 id="{hid}">{t}<span class="mk">@@{hid}@@</span></h2>\n'
        body = re.sub(r"^## (.+)$", h2, body, flags=re.M)
        hbody = markdown.markdown(body, extensions=md_ext)
        hbody = link_code(hbody, b)
        # short tables stay on one page; longer ones never leave a tail of one or two rows (style.css)
        hbody = re.sub(r"<table>(.*?)</table>",
                       lambda mt: ('<table class="keep">' if mt.group(1).count("<tr") <= 14 else "<table>") + mt.group(1) + "</table>",
                       hbody, flags=re.S)
        if cls == "front":
            chapters.append(f'<section class="front" id="{cid}">{hbody}</section>')
            continue
        mnum = re.match(r"^(\d+|[A-Z])\s+(.*)$", title)
        num, short = (mnum.group(1), mnum.group(2)) if mnum else ("", title)
        label = f"{num} · {short}" if num else short
        page_css.append(f'@page {cid} {{ @top-left {{ content: "{label}"; }} }}')
        chapters.append(f'<section class="chapter" id="{cid}" style="page:{cid}">'
                        f'<h1><span class="num">{num}</span>{short}<span class="mk">@@{cid}@@</span></h1>{hbody}</section>')
        toc.append((num, short, cid, heads))
    # table of contents
    def pg(i):
        return "" if not pages else str(pages.get(i, "?"))
    toc_html = ['<nav class="toc"><h1 class="toch">Contents</h1><ol>']
    for num, short, cid, heads in toc:
        toc_html.append(f'<li class="tc"><a href="#{cid}"><span class="tn">{num}</span>{short}</a><span class="tp">{pg(cid)}</span>')
        if heads:
            toc_html.append('<ol>' + "".join(f'<li><a href="#{h}">{t}</a><span class="tp">{pg(h)}</span></li>' for t, h in heads) + "</ol>")
        toc_html.append("</li>")
    toc_html.append("</ol></nav>")
    front = chapters[0].replace("<p>[[TOC]]</p>", "\n".join(toc_html))
    css = (HERE / "style.css").read_text(encoding="utf-8").replace("FONTDIR", (HERE / "fonts").as_uri())
    doc = f"""<!doctype html><html lang="en-GB"><head><meta charset="utf-8">
<title>Project handover report</title><style>{css}
{chr(10).join(page_css)}</style></head><body>
{front}
{''.join(chapters[1:])}
</body></html>"""
    # number the tables
    k = [0]

    def tnum(mm):
        k[0] += 1
        return f'<p class="tcap"><b>Table {k[0]}.</b> '
    doc = re.sub(r'<p class="tcap">', tnum, doc)
    return doc, toc, b


# ----------------------------------------------------------------------------- PDF
# Pixel rows of the section dividers above "Every strategy compared" and "Every model we tried" in
# img/app_results_open.png; the screenshot is cut just above them so that no section is split across pages.
RESULTS_SECTION_LINES = (2238, 3557)


def crop_screens(tmpdir: Path) -> None:
    """The long Results screenshot is cut into pieces that fit on a page, at section boundaries."""
    from PIL import Image
    im = Image.open(HERE / "img" / "app_results_open.png")
    w, h = im.size
    gray = im.convert("L")
    cuts = [0] + [y - 18 for y in RESULTS_SECTION_LINES] + [h]
    for y in cuts[1:-1]:  # a cut must fall on an empty row; if the screenshot changes, update the line numbers
        row = [gray.getpixel((x, y)) for x in range(30, w - 30, 7)]
        if max(row) - min(row) > 2:
            raise ValueError(f"screenshot cut at row {y} is not on an empty row; update RESULTS_SECTION_LINES")
    for i in range(3):
        im.crop((0, cuts[i], w, cuts[i + 1])).save(tmpdir / f"app_results_open_{i + 1}.png")


def render_pdf(html_path: Path, pdf_path: Path) -> None:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        br = p.chromium.launch()
        page = br.new_page()
        page.goto(html_path.as_uri(), wait_until="networkidle")
        page.emulate_media(media="print")
        page.pdf(path=str(pdf_path), prefer_css_page_size=True, print_background=True)
        br.close()


def find_markers(pdf_path: Path) -> dict:
    from pypdf import PdfReader
    rd = PdfReader(str(pdf_path))
    pages = {}
    for i, pg in enumerate(rd.pages, start=1):
        txt = (pg.extract_text() or "").replace("\n", "")
        for mm in re.finditer(r"@@([\w-]+?)@@", txt):
            pages.setdefault(mm.group(1), i)
    return pages, len(rd.pages)


def relativise_links(pdf_in: Path, pdf_out: Path) -> int:
    """Rewrite file:// links to repo files as paths relative to reports/ (where the PDF lives)."""
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import NameObject, TextStringObject
    rd = PdfReader(str(pdf_in))
    wr = PdfWriter(clone_from=rd)
    root_uri = ROOT.as_uri() + "/"
    n = 0
    for pg in wr.pages:
        for a in pg.get("/Annots", []) or []:
            a = a.get_object()
            act = a.get("/A")
            if act is None:
                continue
            act = act.get_object()
            uri = act.get("/URI")
            if uri and str(uri).startswith(root_uri):
                from urllib.parse import unquote
                relp = unquote(str(uri)[len(root_uri):])
                act[NameObject("/URI")] = TextStringObject("../" + relp)
                n += 1
    wr.add_metadata({"/Title": "Day-ahead planning for a Zurich DSO – Project handover report",
                     "/Subject": "Handover report", "/Creator": "docs/handover/build.py"})
    with open(pdf_out, "wb") as fh:
        wr.write(fh)
    return n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--html", action="store_true", help="keep the HTML in docs/handover/out/")
    a = ap.parse_args(argv)
    N = numbers()
    T = tables(N)
    T["review_log"]()  # also sets N['n_review_findings']
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        crop_screens(tmp)
        pages, prev = None, None
        for attempt in range(4):
            doc, toc, b = build_html(N, T, tmp, pages)
            hp = tmp / "report.html"
            hp.write_text(doc, encoding="utf-8")
            render_pdf(hp, tmp / "raw.pdf")
            found, npages = find_markers(tmp / "raw.pdf")
            if pages is not None and found == pages:
                break
            pages = found
        missing = [cid for _, _, cid, _ in toc if cid not in pages]
        if missing:
            print("WARNING: chapters without a page marker:", missing)
        n_links = relativise_links(tmp / "raw.pdf", OUT_PDF)
        if a.html:
            out = HERE / "out"
            out.mkdir(exist_ok=True)
            shutil.copy(hp, out / "report.html")
    print(f"wrote {rel(OUT_PDF)}: {npages} pages, {b.fig_no} figures, {n_links} repo links")
    if b.missing_links:
        print("WARNING: code paths that do not exist (not linked):", sorted(set(b.missing_links)))
    print("chapter pages:")
    for num, short, cid, _ in toc:
        print(f"  {num:>2} {short}: p. {pages.get(cid, '?')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
