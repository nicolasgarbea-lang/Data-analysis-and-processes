"""Run the whole project from raw downloads to the backtest with one command.

Examples (from the project folder):

    python -m src.pipeline --all                  # download, features, models, backtest
    python -m src.pipeline --all --skip-download  # same, but use the files already in data/raw/
    python -m src.pipeline --features --models    # only some steps

Steps
-----
data      download every source and write clean tables to data/processed/
features  build the feature table (one row per delivery day and 4-hour block)
models    train and evaluate the demand model and the price model
backtest  plan, bid and settle every day of the validation and test month
metrics   merge the two metrics files into reports/metrics.csv and the docs fragments into single files
"""
from __future__ import annotations

import argparse
import importlib
import time

import pandas as pd

from src.config import ROOT

# Order matters: the weather forecast loader needs the observed weather, the merge needs its four parts.
DATA_STEPS = [
    "src.data.load_ewz_demand",
    "src.data.load_price_ch",
    "src.data.load_swiss_power",
    "src.data.load_neighbour_prices",
    "src.data.load_de_forecasts",
    "src.data.load_gas",
    "src.data.load_co2",
    "src.data.load_reservoirs",
    "src.data.load_fx",
    "src.data.load_meteoswiss",
    "src.data.load_openmeteo_forecast",
    "src.data.load_openmeteo_archive",
    "src.data.load_openmeteo_europe",
    "src.data.merge_calendar",  # runs calendar, EV, events and football loaders, then merges them
]


def _run(name: str, func, *args, **kwargs):
    t0 = time.time()
    print(f"\n=== {name} ===", flush=True)
    out = func(*args, **kwargs)
    print(f"--- {name} done in {time.time() - t0:.0f} s", flush=True)
    return out


def step_data(skip_download: bool) -> None:
    for module_name in DATA_STEPS:
        module = importlib.import_module(module_name)
        _run(module_name, module.main, skip_download=skip_download)
    for module_name in ("src.data.check_weather_forecast", "src.data.plot_targets"):
        module = importlib.import_module(module_name)
        _run(module_name, module.main)


def step_features() -> None:
    from src.features import build_features

    _run("feature table", build_features.main)


def step_models() -> None:
    from src.models import demand, price

    _run("demand model", demand.main, [])
    _run("price model", price.main, [])


def step_backtest() -> None:
    from src.backtest import run_backtest

    _run("backtest", run_backtest.main, ["--require-ml"])


def step_metrics() -> None:
    """Merge per-target files into the single files named in the project brief."""
    reports = ROOT / "reports"
    parts = [pd.read_csv(f) for f in sorted(reports.glob("metrics_*.csv"))]
    if parts:
        pd.concat(parts, ignore_index=True).to_csv(reports / "metrics.csv", index=False)
        print(f"wrote reports/metrics.csv ({sum(len(p) for p in parts)} rows)")
    checks = sorted((reports / "data_checks").glob("*.md"))
    if checks:
        text = "# Data checks\n\nOne section per processed table, written by the loaders.\n"
        for f in checks:
            body = f.read_text(encoding="utf-8").strip()
            if not body.startswith("#"):
                body = f"## {f.stem}\n\n{body}"
            else:
                body = "#" + body  # push headings one level down
            text += f"\n\n{body}\n"
        (reports / "data_checks.md").write_text(text, encoding="utf-8")
        print(f"wrote reports/data_checks.md ({len(checks)} sections)")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--all", action="store_true", help="run every step")
    ap.add_argument("--data", action="store_true")
    ap.add_argument("--features", action="store_true")
    ap.add_argument("--models", action="store_true")
    ap.add_argument("--backtest", action="store_true")
    ap.add_argument("--metrics", action="store_true")
    ap.add_argument("--skip-download", action="store_true",
                    help="do not touch the internet; rebuild from files already in data/raw/")
    a = ap.parse_args(argv)
    if not (a.all or a.data or a.features or a.models or a.backtest or a.metrics):
        ap.error("choose --all or at least one step")

    t0 = time.time()
    if a.all or a.data:
        step_data(a.skip_download)
    if a.all or a.features:
        step_features()
    if a.all or a.models:
        step_models()
    if a.all or a.backtest:
        step_backtest()
    if a.all or a.metrics or a.models:
        step_metrics()
    print(f"\nPipeline finished in {(time.time() - t0) / 60:.1f} min")


if __name__ == "__main__":
    main()
