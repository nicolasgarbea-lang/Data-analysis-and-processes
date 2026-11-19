"""Simple plots of the two targets (Zurich demand, Swiss day-ahead price).

Writes reports/figures/demand_<year>.png, price_ch_<year>.png,
demand_oct2026.png and price_ch_oct2026.png. Plots use Zurich local time on the x axis.

Run:  .venv/bin/python -m src.data.plot_targets
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from src.config import path

TZ = "Europe/Zurich"
FIG = path("figures")


def _plot(df: pd.DataFrame, col: str, title: str, ylabel: str, out, color: str, daily_line: bool) -> None:
    fig, ax = plt.subplots(figsize=(12, 4))
    x = df["timestamp_utc"].dt.tz_convert(TZ).dt.tz_localize(None)
    ax.plot(x, df[col], lw=0.4 if daily_line else 1.0, color=color, alpha=0.6 if daily_line else 0.9, label="hourly")
    if daily_line:
        daily = df.set_index(x)[col].resample("D").mean()
        ax.plot(daily.index, daily.values, lw=1.2, color="black", label="daily mean")
        ax.legend(loc="upper right")
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.set_xlabel("local time (Europe/Zurich)")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, dpi=110)
    plt.close(fig)


def main(skip_download: bool = False) -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    dem = pd.read_parquet(path("processed") / "demand_ewz_hourly.parquet")
    pri = pd.read_parquet(path("processed") / "price_ch_hourly.parquet")
    for df, col, name, label, ylabel, color in [
        (dem, "load_mw", "demand", "Zurich demand (ewz)", "MW (hourly mean)", "tab:blue"),
        (pri, "price_eur_mwh", "price_ch", "Swiss day-ahead price (CH)", "EUR/MWh", "tab:red"),
    ]:
        local_year = df["timestamp_utc"].dt.tz_convert(TZ).dt.year
        for year in sorted(local_year.unique()):
            part = df[local_year == year]
            _plot(part, col, f"{label} – {year}", ylabel, FIG / f"{name}_{year}.png", color, daily_line=True)
        local = df["timestamp_utc"].dt.tz_convert(TZ)
        octo = df[(local >= pd.Timestamp("2026-10-01", tz=TZ)) & (local < pd.Timestamp("2026-11-01", tz=TZ))]
        _plot(octo, col, f"{label} – October 2026 (test month)", ylabel, FIG / f"{name}_oct2026.png",
              color, daily_line=False)
    print(f"figures written to {FIG}")


if __name__ == "__main__":
    main()
