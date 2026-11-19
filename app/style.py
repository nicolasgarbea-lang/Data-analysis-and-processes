"""One colour per concept, number formats and a shared plotly layout for the whole app."""
from __future__ import annotations

import math

import plotly.graph_objects as go

# One colour per concept (mid-lightness steps, readable on light and dark backgrounds).
COLORS = {
    "demand": "#2a78d6",      # blue
    "price": "#eb6834",       # orange
    "buy": "#8a93a3",         # slate grey
    "charge": "#1baf7a",      # aqua green
    "discharge": "#d55181",   # magenta
    "sell": "#c98500",        # amber
    "soc": "#7b6be0",         # violet
    "actual": "#9a9a9a",      # neutral grey ("what really happened")
    "saving": "#0ca30c",      # green
    "other": "#b5b5b5",
}

# Strategies (fixed order, colour follows the strategy everywhere).
STRATEGY_NAMES = {
    "baseline_naive_no_battery": "Baseline: last week's demand, no battery",
    "ml_no_battery": "ML demand forecast, no battery",
    "naive_battery": "Naive forecasts + battery",
    "ml_battery": "Our product: ML forecasts + battery",
    "ml_battery_block_default": "ML + battery, simple 4-hour block plan",
    "perfect_foresight_battery": "Perfect foresight, 4-hour block rules",
    "perfect_foresight_hourly_daily_battery": "Perfect foresight, hourly, back to start level every day",
    "perfect_foresight_hourly_battery": "Perfect foresight, hourly (best possible)",
    "perfect_demand_no_battery": "Perfect demand forecast, no battery",
}
STRATEGY_COLORS = {
    "baseline_naive_no_battery": "#8a93a3",
    "ml_no_battery": "#2a78d6",
    "naive_battery": "#eda100",
    "ml_battery": "#0ca30c",
    "ml_battery_block_default": "#1baf7a",
    "perfect_foresight_battery": "#9085e9",
    "perfect_foresight_hourly_daily_battery": "#b07fd6",
    "perfect_foresight_hourly_battery": "#6250d6",
    "perfect_demand_no_battery": "#e87ba4",
}

OPTION_WORDS = {
    "buy": "buy",
    "buy_and_store": "buy and store",
    "use_storage_and_buy": "use storage and buy",
    "use_storage": "use storage",
}

SPLIT_NAMES = {"test": "Test month (October 2026)", "val": "Validation month (September 2026)",
               "rolling": "Rolling year Oct 2025 - Aug 2026 (robustness check)"}


def _ok(x) -> bool:
    try:
        return x is not None and math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


def chf(x, signed: bool = False) -> str:
    if not _ok(x):
        return "n/a"
    s = f"{abs(float(x)):,.0f}"
    if signed and float(x) < 0:
        return f"CHF -{s}"
    return f"CHF {s}" if float(x) >= 0 else f"CHF -{s}"


def mwh(x, digits: int = 0) -> str:
    return "n/a" if not _ok(x) else f"{float(x):,.{digits}f} MWh"


def num(x, digits: int = 0) -> str:
    return "n/a" if not _ok(x) else f"{float(x):,.{digits}f}"


def pct(x, digits: int = 0) -> str:
    return "n/a" if not _ok(x) else f"{float(x):.{digits}f}%"


def layout(fig: go.Figure, x_title: str = "", y_title: str = "", height: int = 360,
           legend: bool = True, hover: str = "x unified") -> go.Figure:
    """Same look for every chart: titles with units, legend above the plot, recessive grid."""
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=10, t=40, b=10),
        hovermode=hover,
        showlegend=legend,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, title_text=""),
        bargap=0.25,
    )
    fig.update_xaxes(title_text=x_title, showgrid=False)
    fig.update_yaxes(title_text=y_title, zeroline=True)
    return fig
