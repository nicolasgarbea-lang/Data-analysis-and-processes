"""Plotly figures used by the app. Every figure gets its axis titles and units here."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from app.style import COLORS, STRATEGY_COLORS, STRATEGY_NAMES, layout


def _rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


# ---------------------------------------------------------------------------
# Tomorrow
# ---------------------------------------------------------------------------
def forecast_chart(df: pd.DataFrame, value: str, lo: str, hi: str, actual: str, color: str,
                   y_title: str, name: str, show_actual: bool, unit: str) -> go.Figure:
    x = df["block_name"]
    fig = go.Figure()
    if df[lo].notna().all() and df[hi].notna().all():
        fig.add_trace(go.Scatter(x=x, y=df[hi], mode="lines", line=dict(width=0), showlegend=False,
                                 hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=x, y=df[lo], mode="lines", line=dict(width=0), fill="tonexty",
                                 fillcolor=_rgba(color, 0.18), name="10-90% band",
                                 hovertemplate=f"%{{y:,.1f}} {unit}"))
    fig.add_trace(go.Scatter(x=x, y=df[value], mode="lines+markers", name=f"{name} forecast",
                             line=dict(color=color, width=2), marker=dict(size=8),
                             hovertemplate=f"%{{y:,.1f}} {unit}"))
    if show_actual:
        fig.add_trace(go.Scatter(x=x, y=df[actual], mode="lines+markers", name="What really happened",
                                 line=dict(color=COLORS["actual"], width=2, dash="dot"),
                                 marker=dict(size=8, symbol="diamond"),
                                 hovertemplate=f"%{{y:,.1f}} {unit}"))
    return layout(fig, "Block of the delivery day (Swiss local time)", y_title, height=330)


def battery_chart(plan: pd.DataFrame, names, soc_start: float, soc_min: float, soc_max: float,
                  x_title: str = "Block of the delivery day (Swiss local time)", height: int = 340) -> go.Figure:
    """Charge (up) / discharge (down) per period and the charge level at the end of each period.
    All in MWh, so one axis is enough."""
    x = list(names)
    fig = go.Figure()
    fig.add_trace(go.Bar(x=x, y=plan["charge_mwh"], name="Charge (into battery)",
                         marker_color=COLORS["charge"], hovertemplate="%{y:,.1f} MWh"))
    fig.add_trace(go.Bar(x=x, y=-plan["discharge_mwh"], name="Discharge (used for the city)",
                         marker_color=COLORS["discharge"], hovertemplate="%{y:,.1f} MWh"))
    if "sell_mwh" in plan and plan["sell_mwh"].abs().sum() > 1e-6:
        fig.add_trace(go.Bar(x=x, y=-plan["sell_mwh"], name="Sold back to the market",
                             marker_color=COLORS["sell"], hovertemplate="%{y:,.1f} MWh"))
    fig.add_trace(go.Scatter(x=["start"] + x, y=[soc_start] + list(plan["soc_mwh"]), mode="lines+markers",
                             name="Charge level at the end", line=dict(color=COLORS["soc"], width=2, shape="linear"),
                             marker=dict(size=8), hovertemplate="%{y:,.1f} MWh"))
    for yv, label in [(soc_min, "min"), (soc_max, "max")]:
        fig.add_hline(y=yv, line=dict(color=COLORS["soc"], width=1, dash="dot"), opacity=0.6,
                      annotation_text=f"{label} charge level", annotation_position="top left",
                      annotation_font_size=10)
    fig.update_layout(barmode="relative")
    fig.update_xaxes(categoryorder="array", categoryarray=["start"] + x)
    return layout(fig, x_title, "Energy (MWh)", height=height)


def buy_chart(plan: pd.DataFrame, names) -> go.Figure:
    x = list(names)
    fig = go.Figure()
    fig.add_trace(go.Bar(x=x, y=plan["buy_mwh"], name="Buy at the auction", marker_color=COLORS["buy"],
                         hovertemplate="%{y:,.0f} MWh"))
    fig.add_trace(go.Scatter(x=x, y=plan["demand_mwh"], mode="markers", name="Forecast demand",
                             marker=dict(color=COLORS["demand"], size=12, symbol="line-ew-open",
                                         line=dict(width=3, color=COLORS["demand"])),
                             hovertemplate="%{y:,.0f} MWh"))
    return layout(fig, "Block of the delivery day (Swiss local time)", "Energy per block (MWh)", height=300)


# ---------------------------------------------------------------------------
# Month backtest
# ---------------------------------------------------------------------------
def cumulative_chart(daily: pd.DataFrame, strategies) -> go.Figure:
    base = daily[daily["strategy"] == "baseline_naive_no_battery"].set_index("delivery_date")["total_cost_chf"]
    fig = go.Figure()
    for s in strategies:
        g = daily[daily["strategy"] == s].set_index("delivery_date")["total_cost_chf"]
        if g.empty:
            continue
        sav = (base.reindex(g.index) - g).cumsum()
        fig.add_trace(go.Scatter(x=pd.to_datetime(sav.index), y=sav.values, mode="lines",
                                 name=STRATEGY_NAMES.get(s, s), line=dict(color=STRATEGY_COLORS.get(s), width=2),
                                 hovertemplate="CHF %{y:,.0f}"))
    return layout(fig, "Delivery day", "Cumulative saving vs baseline (CHF)", height=380)


def decomposition_chart(row: pd.Series) -> go.Figure:
    parts = [("Better demand forecast", row.get("demand_forecast_part_chf"), COLORS["demand"]),
             ("Battery: simple block plan", row.get("block_default_battery_part_chf"), COLORS["charge"]),
             ("Battery: tuned hourly rules", row.get("tuning_and_shaping_part_chf"), COLORS["soc"])]
    parts = [p for p in parts if p[1] is not None and np.isfinite(p[1])]
    fig = go.Figure()
    for name, val, col in parts:
        fig.add_trace(go.Bar(y=["Saving of our product"], x=[val], name=name, orientation="h",
                             marker_color=col, hovertemplate=f"{name}: CHF %{{x:,.0f}}<extra></extra>"))
    fig.update_layout(barmode="relative")
    return layout(fig, "Saving vs baseline over the period (CHF)", "", height=200, hover="closest")


def battery_size_chart(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for s, g in df.groupby("strategy", sort=False):
        g = g.sort_values("capacity_mwh")
        labels = [f"{p:g} MW / {c:g} MWh" for p, c in zip(g["power_mw"], g["capacity_mwh"])]
        fig.add_trace(go.Scatter(x=labels, y=g["battery_value_chf"], mode="lines+markers",
                                 name=STRATEGY_NAMES.get(s, s), line=dict(color=STRATEGY_COLORS.get(s), width=2),
                                 marker=dict(size=8), hovertemplate="CHF %{y:,.0f}"))
    return layout(fig, "Battery size (power / capacity)", "Saving from the battery alone (CHF per month)",
                  height=360)


def price_error_chart(df: pd.DataFrame) -> go.Figure:
    noise = df[df["forecast"] == "noise"]
    g = noise.groupby("sigma").agg(mae=("price_mae_eur_mwh", "mean"), mean=("lost_saving_chf", "mean"),
                                   lo=("lost_saving_chf", "min"), hi=("lost_saving_chf", "max")).reset_index()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=g["mae"], y=g["hi"], mode="lines", line=dict(width=0), showlegend=False,
                             hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=g["mae"], y=g["lo"], mode="lines", line=dict(width=0), fill="tonexty",
                             fillcolor=_rgba(COLORS["price"], 0.18), name="range over 5 random runs",
                             hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=g["mae"], y=g["mean"], mode="lines+markers", name="Random price errors (mean)",
                             line=dict(color=COLORS["price"], width=2), marker=dict(size=8),
                             hovertemplate="error %{x:.1f} EUR/MWh: CHF %{y:,.0f}<extra></extra>"))
    for key, label, sym in [("naive", "Naive price forecast (last week)", "square"),
                            ("ml", "Price forecast used in the backtest", "star")]:
        r = df[df["forecast"] == key]
        if len(r):
            fig.add_trace(go.Scatter(x=r["price_mae_eur_mwh"], y=r["lost_saving_chf"], mode="markers+text",
                                     name=label, text=[label], textposition="top center",
                                     marker=dict(size=13, symbol=sym, color=COLORS["actual"]),
                                     hovertemplate="error %{x:.1f} EUR/MWh: CHF %{y:,.0f}<extra></extra>"))
    return layout(fig, "Average price forecast error (MAE, EUR/MWh)", "Battery saving lost (CHF per month)",
                  height=380, hover="closest")


# ---------------------------------------------------------------------------
# Drivers
# ---------------------------------------------------------------------------
def importance_chart(df: pd.DataFrame, color: str, unit: str, n: int = 15) -> go.Figure:
    d = df.sort_values("mae_increase", ascending=False).head(n).iloc[::-1]
    fig = go.Figure(go.Bar(x=d["mae_increase"], y=d["feature"], orientation="h", marker_color=color,
                           error_x=dict(type="data", array=d["std"], thickness=1, width=3,
                                        color=COLORS["actual"]) if "std" in d else None,
                           hovertemplate=f"%{{x:.2f}} {unit}<extra></extra>"))
    return layout(fig, f"Forecast error increase when shuffled (MAE, {unit})", "", height=30 * len(d) + 80,
                  legend=False, hover="closest")


def binned_line(x: pd.Series, y: pd.Series, bins: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    cut = pd.cut(x, bins)
    g = y.groupby(cut, observed=True).agg(["mean", "size"])
    g = g[g["size"] >= 10]
    mids = np.array([iv.mid for iv in g.index])
    return mids, g["mean"].to_numpy()
