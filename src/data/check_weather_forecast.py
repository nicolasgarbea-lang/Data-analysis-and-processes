"""Compare Open-Meteo forecasts (and ERA5) with MeteoSwiss SMA observations, and fit a temperature bias correction.

Writes:
- reports/data_checks/weather_forecast_vs_observed.md  (MAE and bias by year and month, station vs grid offset)
- reports/figures/weather_forecast_vs_observed.png

Bias correction (`add_bias_correction`, called by load_openmeteo_forecast.main):
    corrected = forecast + mean(observed - forecast) for the same calendar month and local hour of day,
    fitted ONLY on hours before the validation start (config periods.val_start), so September/October 2026
    are untouched by the fit. Chosen because it beat a per-month linear fit out of sample (see report).

Run: .venv/bin/python -m src.data.check_weather_forecast   (needs the three processed weather files)
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from src.config import ROOT, load_config, path  # noqa: E402

OBS_FILE = path("processed") / "weather_observed_hourly.parquet"
FC_FILE = path("processed") / "weather_forecast_hourly.parquet"
ERA5_FILE = path("processed") / "weather_archive_hourly.parquet"
REPORT = ROOT / "reports" / "data_checks" / "weather_forecast_vs_observed.md"
FIGURE = path("figures") / "weather_forecast_vs_observed.png"
END = pd.Timestamp("2026-11-01", tz="Europe/Zurich").tz_convert("UTC")  # end of October local time
TZ = "Europe/Zurich"
CORRECT = {"temp_c_fc_safe": "temp_c_fc_safe_corr", "temp_c_fc_safe_jma": "temp_c_fc_safe_jma_corr"}


# ----------------------------------------------------------------------------------------------------------
# bias correction
# ----------------------------------------------------------------------------------------------------------
def _month_hour(ts: pd.Series) -> tuple[pd.Series, pd.Series]:
    loc = ts.dt.tz_convert(TZ)
    return loc.dt.month, loc.dt.hour


def fit_offsets(fc: pd.Series, obs: pd.Series, ts: pd.Series) -> pd.Series:
    """Mean (observed - forecast) per (calendar month, local hour)."""
    month, hour = _month_hour(ts)
    diff = (obs - fc).rename("offset")
    frame = pd.DataFrame({"month": month.values, "hour": hour.values, "offset": diff.values}).dropna()
    return frame.groupby(["month", "hour"])["offset"].mean()


def apply_offsets(fc: pd.Series, ts: pd.Series, offsets: pd.Series) -> pd.Series:
    month, hour = _month_hour(ts)
    key = pd.MultiIndex.from_arrays([month.values, hour.values])
    off = offsets.reindex(key).fillna(0.0).to_numpy()
    return pd.Series(fc.to_numpy() + off, index=fc.index)


def add_bias_correction(fc_df: pd.DataFrame) -> pd.DataFrame:
    """Add `*_corr` columns to the forecast frame (fit on hours before val_start). Needs the observed file."""
    if not OBS_FILE.exists():
        raise FileNotFoundError(f"{OBS_FILE} missing, run load_meteoswiss first")
    obs = pd.read_parquet(OBS_FILE, columns=["timestamp_utc", "temp_c"])
    val_start = pd.Timestamp(load_config()["periods"]["val_start"], tz=TZ).tz_convert("UTC")
    m = fc_df[["timestamp_utc", *CORRECT]].merge(obs, on="timestamp_utc", how="left")
    train = m[m["timestamp_utc"] < val_start]
    for src, dst in CORRECT.items():
        offsets = fit_offsets(train[src], train["temp_c"], train["timestamp_utc"])
        fc_df[dst] = apply_offsets(fc_df[src], fc_df["timestamp_utc"], offsets).where(fc_df[src].notna())
    return fc_df


# ----------------------------------------------------------------------------------------------------------
# report
# ----------------------------------------------------------------------------------------------------------
def load_joined() -> pd.DataFrame:
    obs = pd.read_parquet(OBS_FILE)
    fc = pd.read_parquet(FC_FILE)
    era = pd.read_parquet(ERA5_FILE)
    d = obs.merge(fc, on="timestamp_utc", how="left").merge(era, on="timestamp_utc", how="left")
    d = d[d["timestamp_utc"] < END].copy()
    loc = d["timestamp_utc"].dt.tz_convert(TZ)
    d["year"], d["month"], d["hour"] = loc.dt.year, loc.dt.month, loc.dt.hour
    return d


def err_table(d: pd.DataFrame, obs: str, cols: list[str], by: str) -> pd.DataFrame:
    """MAE and bias (forecast - observed) of each column, grouped by `by`; only rows where all columns exist."""
    sub = d.dropna(subset=[obs, *cols])
    out = {}
    for c in cols:
        e = sub[c] - sub[obs]
        out[(c, "MAE")] = e.abs().groupby(sub[by]).mean()
        out[(c, "bias")] = e.groupby(sub[by]).mean()
    t = pd.DataFrame(out)
    t[("n_hours", "")] = sub.groupby(by).size()
    return t


def md_table(t: pd.DataFrame, digits: int = 2) -> str:
    cols = [f"{a} {b}" if b else a for a, b in (c if isinstance(c, tuple) else (c, "") for c in t.columns)]
    lines = ["| " + t.index.name + " | " + " | ".join(cols) + " |", "|" + "---|" * (len(cols) + 1)]
    for i in range(len(t)):
        vals = []
        for c in t.columns:
            v = t[c].iloc[i]
            is_count = (c[0] if isinstance(c, tuple) else c) == "n_hours"
            vals.append(str(int(v)) if is_count else f"{v:.{digits}f}" if isinstance(v, (float, np.floating)) else str(v))
        lines.append(f"| {t.index[i]} | " + " | ".join(vals) + " |")
    return "\n".join(lines)


def overall(d: pd.DataFrame, obs: str, cols: list[str], mask=None) -> pd.DataFrame:
    sub = d if mask is None else d[mask]
    rows = []
    for c in cols:
        s = sub.dropna(subset=[obs, c])
        e = s[c] - s[obs]
        rows.append({"column": c, "from": s["timestamp_utc"].min().date() if len(s) else None, "n_hours": len(s),
                     "MAE": e.abs().mean(), "bias": e.mean(), "corr": s[c].corr(s[obs])})
    return pd.DataFrame(rows).set_index("column")


def holdout_comparison(d: pd.DataFrame, col: str) -> dict:
    """Out-of-sample MAE of correction variants: fit before 2026-09-01, test Sep+Oct 2026."""
    cut = pd.Timestamp("2026-09-01", tz=TZ).tz_convert("UTC")
    s = d.dropna(subset=["temp_c", col])
    tr, te = s[s["timestamp_utc"] < cut], s[s["timestamp_utc"] >= cut]
    res = {"raw": (te[col] - te["temp_c"]).abs().mean()}
    b, a = np.polyfit(tr[col], tr["temp_c"], 1)
    res["one linear fit"] = (a + b * te[col] - te["temp_c"]).abs().mean()
    pred = pd.Series(np.nan, index=te.index)
    for mth, g in tr.groupby("month"):
        b, a = np.polyfit(g[col], g["temp_c"], 1)
        idx = te["month"] == mth
        pred[idx] = a + b * te.loc[idx, col]
    res["linear fit per month"] = (pred - te["temp_c"]).abs().mean()
    off = fit_offsets(tr[col], tr["temp_c"], tr["timestamp_utc"])
    res["offset per month x local hour (used)"] = (apply_offsets(te[col], te["timestamp_utc"], off)
                                                   - te["temp_c"]).abs().mean()
    return res


def make_figure(d: pd.DataFrame) -> None:
    """Monthly temperature MAE per forecast column + mean diurnal offset station vs grid."""
    colors = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]  # validated default categorical order (dataviz skill)
    d = d.copy()
    d["ym"] = d["timestamp_utc"].dt.tz_convert(TZ).dt.tz_localize(None).dt.to_period("M").dt.to_timestamp()
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.6), gridspec_kw={"width_ratios": [2.2, 1]})
    ax = axes[0]
    series = [("temp_c_fc_safe", "ICON safe"), ("temp_c_fc_safe_corr", "ICON safe, bias-corrected"),
              ("temp_c_fc_safe_jma", "JMA safe"), ("temp_c_fc_safe_jma_corr", "JMA safe, bias-corrected")]
    for (c, label), col in zip(series, colors):
        s = d.dropna(subset=["temp_c", c])
        m = (s[c] - s["temp_c"]).abs().groupby(s["ym"]).mean()
        ax.plot(m.index, m.values, color=col, lw=2, label=label)
    ax.axvspan(pd.Timestamp("2026-09-01"), pd.Timestamp("2026-11-01"), color="#999999", alpha=0.15, lw=0)
    ax.text(pd.Timestamp("2026-09-05"), ax.get_ylim()[1] * 0.95, "val + test\n(not used in fit)", fontsize=8,
            va="top", color="#52514e")
    ax.set_title("Temperature forecast error vs MeteoSwiss SMA (monthly MAE, °C)", fontsize=11, loc="left")
    ax.set_ylabel("MAE °C")
    ax.legend(frameon=False, fontsize=9, loc="upper left")
    ax2 = axes[1]
    for (c, label), col in zip([("temp_c_fc_day0", "ICON current run"), ("temp_c_era5", "ERA5"),
                                ("temp_c_fc_day0_jma", "JMA current run")], colors):
        s = d.dropna(subset=["temp_c", c])
        m = (s[c] - s["temp_c"]).groupby(s["hour"]).mean()
        ax2.plot(m.index, m.values, color=col, lw=2, marker="o", ms=4, label=label)
    ax2.axhline(0, color="#52514e", lw=0.8)
    ax2.set_title("Grid minus station, by local hour (°C)", fontsize=11, loc="left")
    ax2.set_xlabel("local hour (start)")
    ax2.set_xticks(range(0, 24, 3))
    ax2.legend(frameon=False, fontsize=9)
    for a in axes:
        a.grid(axis="y", color="#e5e5e5", lw=0.8)
        a.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    FIGURE.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURE, dpi=130)
    plt.close(fig)


def main() -> None:
    d = load_joined()
    temp_cols = ["temp_c_fc_day1", "temp_c_fc_day2", "temp_c_fc_safe", "temp_c_fc_safe_corr"]
    jma_cols = ["temp_c_fc_day1_jma", "temp_c_fc_day2_jma", "temp_c_fc_safe_jma", "temp_c_fc_safe_jma_corr"]
    rad_cols = ["radiation_wm2_fc_day1", "radiation_wm2_fc_day2", "radiation_wm2_fc_safe"]
    test = (d["timestamp_utc"] >= pd.Timestamp("2026-10-01", tz=TZ)) & (d["year"] == 2026) & (d["month"] == 10)

    all_temp = ["temp_c_fc_day0", *temp_cols, "temp_c_fc_safe_ecmwf", *jma_cols, "temp_c_era5"]
    all_rad = ["radiation_wm2_fc_day0", *rad_cols, "radiation_wm2_fc_safe_ecmwf", "radiation_wm2_era5"]
    other = [("sunshine_min", "sunshine_min_fc_safe"), ("wind_ms", "wind_ms_fc_safe"),
             ("precip_mm", "precip_mm_fc_safe"), ("humidity_pct", "humidity_pct_fc_safe"),
             ("sunshine_min", "sunshine_min_era5"), ("wind_ms", "wind_ms_era5")]

    lines = [
        "# Weather check: forecast vs observed (MeteoSwiss SMA Zürich-Fluntern)",
        "",
        "Error = forecast - observed, hourly, timestamp_utc = start of hour. Period up to 2026-10-31.",
        "Main forecast = Open-Meteo `icon_seamless`; `_ecmwf` = ecmwf_ifs025; `_jma` = JMA GSM (coarse, long history).",
        "`*_fc_safe` = freshest lead issued before D 10:00 Europe/Zurich (see docs/assumptions_weather.md).",
        "`*_corr` = bias-corrected (offset per month x local hour, fitted on hours before 2026-09-01);",
        "whole-period `_corr` numbers are therefore partly in-sample, the honest test is the last table and Oct 2026.",
        "",
        "## Temperature, whole period (°C)",
        "",
        md_table(overall(d, "temp_c", all_temp).rename_axis("column")),
        "",
        "## Temperature, test month October 2026 (°C)",
        "",
        md_table(overall(d, "temp_c", all_temp, test).rename_axis("column")),
        "",
        "## Radiation, whole period (W/m²)",
        "",
        md_table(overall(d, "radiation_wm2", all_rad).rename_axis("column"), 1),
        "",
        "## Radiation, October 2026 (W/m²)",
        "",
        md_table(overall(d, "radiation_wm2", all_rad, test).rename_axis("column"), 1),
        "",
        "## Other variables (safe ICON forecast and ERA5), whole period",
        "",
    ]
    rows = []
    for obs_c, c in other:
        s = d.dropna(subset=[obs_c, c])
        e = s[c] - s[obs_c]
        rows.append({"column": f"{c} vs {obs_c}", "n_hours": len(s), "MAE": e.abs().mean(), "bias": e.mean(),
                     "corr": s[c].corr(s[obs_c])})
    lines += [md_table(pd.DataFrame(rows).set_index("column")), ""]

    lines += ["## Temperature (ICON) by year", "", md_table(err_table(d, "temp_c", temp_cols, "year")), "",
              "## Temperature (ICON) by calendar month", "", md_table(err_table(d, "temp_c", temp_cols, "month")), "",
              "## Temperature (JMA, long history) by year", "", md_table(err_table(d, "temp_c", jma_cols, "year")), "",
              "## Radiation (ICON) by year", "", md_table(err_table(d, "radiation_wm2", rad_cols, "year"), 1), "",
              "## Radiation (ICON) by calendar month", "",
              md_table(err_table(d, "radiation_wm2", rad_cols, "month"), 1), ""]

    # station vs grid
    lines += ["## Station (SMA, 556 m) vs Open-Meteo grid point (47.378 N, 8.565 E, 557 m)", "",
              "Mean offset grid - station by calendar month (°C). `day0` = current run (shortest lead).", ""]
    off = {}
    for c in ["temp_c_fc_day0", "temp_c_era5", "temp_c_fc_day0_jma"]:
        s = d.dropna(subset=["temp_c", c])
        off[(c, "bias")] = (s[c] - s["temp_c"]).groupby(s["month"]).mean()
        off[(c, "corr")] = s.groupby("month").apply(lambda g, c=c: g[c].corr(g["temp_c"]), include_groups=False)
    lines += [md_table(pd.DataFrame(off).rename_axis("month")), ""]
    by_hour = {}
    for c in ["temp_c_fc_day0", "temp_c_era5"]:
        s = d.dropna(subset=["temp_c", c])
        by_hour[(c, "bias")] = (s[c] - s["temp_c"]).groupby(s["hour"]).mean()
    lines += ["Mean offset by local hour of day (°C):", "", md_table(pd.DataFrame(by_hour).rename_axis("hour")), ""]

    lines += ["## Bias correction: out-of-sample test (fit < 2026-09-01, evaluate Sep + Oct 2026, MAE °C)", "",
              "| variant | ICON temp_c_fc_safe | JMA temp_c_fc_safe_jma |", "|---|---|---|"]
    h1, h2 = holdout_comparison(d, "temp_c_fc_safe"), holdout_comparison(d, "temp_c_fc_safe_jma")
    for k in h1:
        lines.append(f"| {k} | {h1[k]:.3f} | {h2[k]:.3f} |")
    lines += ["", f"Figure: `{FIGURE.relative_to(ROOT)}`", ""]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    make_figure(d)
    print(f"wrote {REPORT} and {FIGURE}")


if __name__ == "__main__":
    main()
