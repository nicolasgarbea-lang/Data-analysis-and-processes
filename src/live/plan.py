"""Live plan: forecast and plan delivery day D+1 from the data known today.

Uses the same code as the backtest:

* inputs   - ``src.features.build_features.build_features(tables, [delivery_date])``
* models   - ``models/demand_best.joblib`` and ``models/price_best.joblib`` (``ForecastModel``)
* plan     - ``src.backtest.run_backtest.plan_day(..., settle=False)``, with the tuned decision rules.
  ``plan_day`` reads its inputs through ``run_backtest.load_data`` and ``run_backtest._forecast_index``;
  ``live_context`` replaces both for the duration of one call (guarded by a lock).

What-if overrides are applied to the INPUT TABLES before the features are built, so every feature
that depends on them (day means, derived temperatures, holiday neighbours, gas averages) stays
consistent:

* ``temp_shift_c``      added to every temperature forecast column for the hours of the delivery day
* ``is_holiday``        True/False sets the calendar row of the delivery day (None = calendar)
* ``gas_eur_mwh``       replaces the latest gas price known at the forecast time
* ``demand_scale_pct``  scales the final demand forecast (manual correction, e.g. for an event)

Known gaps are filled and flagged:

* Zurich demand - the public ewz file is ~1.5 days late; hours missing before day D are filled
  with the same hour 7 days earlier (flag ``estimated``).
"""
from __future__ import annotations

import datetime as dt
import json
import threading
from contextlib import contextmanager
from functools import lru_cache

import joblib
import numpy as np
import pandas as pd

from src.backtest import run_backtest as rb
from src.config import ROOT, load_config
from src.features import build_features as bf
from src.optimisation.battery_lp import BatteryParams

TZ = "Europe/Zurich"
LIVE_DIR = ROOT / "data" / "live"
LOG_DIR = LIVE_DIR / "log"
HISTORY_DAYS = 60          # hourly history handed to the planner (price shape, demand shape)
_LOCK = threading.Lock()
BATTERY_FIELDS = ["power_mw", "capacity_mwh", "soc_min_frac", "soc_max_frac", "soc_start_frac",
                  "round_trip_efficiency", "max_cycles_per_day", "wear_cost_eur_per_mwh"]


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def tomorrow_local(now: pd.Timestamp | None = None) -> dt.date:
    now = pd.Timestamp.now(tz=TZ) if now is None else pd.Timestamp(now).tz_convert(TZ)
    return (now + pd.Timedelta(days=1)).date()


def midnight_utc(day) -> pd.Timestamp:
    return pd.Timestamp(str(day)).tz_localize(TZ).tz_convert("UTC")


def issue_time_utc(delivery: dt.date) -> pd.Timestamp:
    hh, mm = map(int, load_config()["auction"]["forecast_time_local"].split(":"))
    local = pd.Timestamp(str(delivery)) - pd.Timedelta(days=1) + pd.Timedelta(hours=hh, minutes=mm)
    return local.tz_localize(TZ).tz_convert("UTC")


def _f(x, nd=2):
    """JSON number: rounded float or None."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return round(v, nd) if np.isfinite(v) else None


def _ts(t) -> str | None:
    if t is None or pd.isna(t):
        return None
    return pd.Timestamp(t).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


@lru_cache(maxsize=1)
def load_models() -> dict:
    folder = ROOT / load_config()["paths"]["models"]
    return {"demand": joblib.load(folder / "demand_best.joblib"),
            "price": joblib.load(folder / "price_best.joblib")}


def battery_params(settings: dict) -> BatteryParams:
    return BatteryParams(**{k: float(settings[k]) for k in BATTERY_FIELDS})


def default_battery() -> dict:
    b = load_config()["battery"]
    out = {k: float(b[k]) for k in BATTERY_FIELDS}
    out["allow_sell"] = bool(b.get("allow_sell", False))
    return out


# ---------------------------------------------------------------------------
# gap filling and overrides (on copies of the tables)
# ---------------------------------------------------------------------------
def fill_demand_gap(tables: dict, delivery: dt.date) -> tuple[dict, pd.DataFrame]:
    """Fill hourly Zurich demand missing between the last published hour and the start of day D
    (= what the model may use) with the same hour 7 days earlier. Returns (tables, filled rows)."""
    d = tables["demand"].sort_values("timestamp_utc").copy()
    d["timestamp_utc"] = d["timestamp_utc"].dt.as_unit("ns")
    cutoff = midnight_utc(delivery - dt.timedelta(days=1))          # start of day D
    known = d.loc[d["load_mw"].notna(), "timestamp_utc"]
    last = known.max()
    if last + pd.Timedelta(hours=1) >= cutoff:
        return tables, d.iloc[:0]
    need = pd.date_range(last + pd.Timedelta(hours=1), cutoff, freq="h", inclusive="left").as_unit("ns")
    series = d.set_index("timestamp_utc")["load_mw"]
    vals = []
    for t in need:                                                 # chained: a filled hour may feed the next week
        v = series.get(t - pd.Timedelta(days=7), np.nan)
        series.loc[t] = v
        vals.append(v)
    fill = pd.DataFrame({"timestamp_utc": need, "load_mw": vals})
    for col in d.columns:
        if col not in fill:
            fill[col] = 1.0 if col in ("share_non_final", "share_status_f") else (0 if col.startswith("n_") else np.nan)
    d = pd.concat([d[~d["timestamp_utc"].isin(need)], fill[d.columns]], ignore_index=True)
    d = d.sort_values("timestamp_utc").reset_index(drop=True)
    return {**tables, "demand": d}, fill


def apply_overrides(tables: dict, delivery: dt.date, ov: dict) -> dict:
    t = dict(tables)
    shift = float(ov.get("temp_shift_c") or 0.0)
    if shift:
        w = t["weather_fc"].copy()
        s, e = midnight_utc(delivery), midnight_utc(delivery + dt.timedelta(days=1))
        m = (w["timestamp_utc"] >= s) & (w["timestamp_utc"] < e)
        cols = [c for c in w.columns if c.startswith("temp_c_fc") and pd.api.types.is_numeric_dtype(w[c])]
        w.loc[m, cols] = w.loc[m, cols] + shift
        t["weather_fc"] = w
        if "weather_europe" in t:
            eu = t["weather_europe"].copy()
            me = (eu["timestamp_utc"] >= s) & (eu["timestamp_utc"] < e)
            ecols = [c for c in eu.columns if c.startswith("temp_c_") and pd.api.types.is_numeric_dtype(eu[c])]
            eu.loc[me, ecols] = eu.loc[me, ecols] + shift
            t["weather_europe"] = eu
    hol = ov.get("is_holiday")
    if hol is not None:
        cal = t["calendar"].copy()
        m = pd.to_datetime(cal["date"]).dt.date == delivery
        if not m.any():
            raise ValueError(f"no calendar row for {delivery}")
        cal.loc[m, "is_holiday"] = int(bool(hol))
        if "is_working_day" in cal:
            cal.loc[m, "is_working_day"] = int((not bool(hol)) and not bool(cal.loc[m, "is_weekend"].iloc[0]))
        if "holiday_name" in cal and bool(hol) and not isinstance(cal.loc[m, "holiday_name"].iloc[0], str):
            cal.loc[m, "holiday_name"] = "Manual holiday"
        t["calendar"] = cal
    gas = ov.get("gas_eur_mwh")
    if gas is not None:
        g = t["gas"].copy().sort_values("date")
        known = g[pd.to_datetime(g["available_from_utc"], utc=True) <= issue_time_utc(delivery)]
        if len(known):
            g.loc[known.index[-1], "gas_ttf_eur_mwh"] = float(gas)
        t["gas"] = g
    return t


# ---------------------------------------------------------------------------
# features, forecasts and the planner context
# ---------------------------------------------------------------------------
def build_rows(tables: dict, delivery: dt.date) -> pd.DataFrame:
    rows = bf.build_features(tables, [delivery])
    rows["delivery_date"] = pd.to_datetime(rows["delivery_date"])
    return rows.sort_values("block").reset_index(drop=True)


def forecast(rows: pd.DataFrame, demand_scale_pct: float = 0.0) -> pd.DataFrame:
    m = load_models()
    k = 1.0 + float(demand_scale_pct or 0.0) / 100.0
    out = pd.DataFrame({"delivery_date": rows["delivery_date"].dt.date, "block": rows["block"]})
    out["demand_ml_mw"] = m["demand"].predict(rows) * k
    qd = m["demand"].predict_quantiles(rows)
    out["demand_q10_mw"] = qd["pred_q10"].to_numpy() * k
    out["demand_q90_mw"] = qd["pred_q90"].to_numpy() * k
    out["price_ml_eur_mwh"] = m["price"].predict(rows)
    qp = m["price"].predict_quantiles(rows)
    out["price_q10_eur_mwh"] = qp["pred_q10"].to_numpy()
    out["price_q90_eur_mwh"] = qp["pred_q90"].to_numpy()
    out["demand_naive_mw"] = rows["demand_lag_7d_same_block"].to_numpy()
    out["price_naive_eur_mwh"] = rows["price_lag_7d_same_block"].to_numpy()
    out["split"] = "live"
    out["demand_source"] = "ml"
    out["price_source"] = "ml"
    return out


def hourly_frame(tables: dict, first: dt.date, last: dt.date) -> pd.DataFrame:
    """Hourly demand / price / EUR-CHF rows for local days first..last (NaN where unknown)."""
    old = (bf.ACTUALS_FIRST_DAY, bf.LAST_DELIVERY)
    try:
        bf.ACTUALS_FIRST_DAY, bf.LAST_DELIVERY = pd.Timestamp(str(first)), pd.Timestamp(str(last))
        return bf.build_hourly_actuals(tables)
    finally:
        bf.ACTUALS_FIRST_DAY, bf.LAST_DELIVERY = old


def planner_data(tables: dict, rows: pd.DataFrame, delivery: dt.date) -> dict:
    """Same structure as ``run_backtest.load_data()``, built from the live tables."""
    hourly = hourly_frame(tables, delivery - dt.timedelta(days=HISTORY_DAYS), delivery)
    hourly["delivery_date"] = pd.to_datetime(hourly["delivery_date"]).dt.date
    hourly = hourly.sort_values("timestamp_utc").reset_index(drop=True)
    hourly["price_dev"] = hourly["price_eur_mwh"] - hourly.groupby(["delivery_date", "block"])["price_eur_mwh"].transform("mean")
    dev = hourly.dropna(subset=["price_dev"]).groupby(["delivery_date", "hour_local"])["price_dev"].mean()
    price_dev = {d: g.droplevel(0).to_dict() for d, g in dev.groupby(level=0)}
    cal = tables["calendar"].copy()
    cal["date"] = pd.to_datetime(cal["date"]).dt.date
    cal = cal.set_index("date")
    daytype = {d: ("free" if (bool(r.is_weekend) or bool(r.is_holiday)) else "workday")
               for d, r in cal[["is_weekend", "is_holiday"]].iterrows()}
    feats = rows.copy()
    feats["delivery_date"] = feats["delivery_date"].dt.date
    hours = {d: g.drop(columns="price_dev").reset_index(drop=True) for d, g in hourly.groupby("delivery_date")}
    return {"features": feats, "blocks": {delivery: feats.reset_index(drop=True)}, "hours": hours,
            "dates": sorted(hours), "daytype": daytype, "price_dev": price_dev}


@contextmanager
def live_context(data: dict, fc: pd.DataFrame):
    """Point the backtest planner at live inputs for the duration of the block."""
    idx = {d: g.sort_values("block").reset_index(drop=True) for d, g in fc.groupby("delivery_date")}
    with _LOCK:
        old = (rb.load_data, rb._forecast_index)
        rb.load_data = lambda: data
        rb._forecast_index = lambda require_ml=False: idx
        try:
            yield
        finally:
            rb.load_data, rb._forecast_index = old


# ---------------------------------------------------------------------------
# the plan
# ---------------------------------------------------------------------------
def _block_labels() -> list[str]:
    return [f"{a:02d}–{b:02d}" for a, b in load_config()["blocks"]]


def _inputs(rows: pd.DataFrame, tables: dict, filled: pd.DataFrame, delivery: dt.date) -> list[dict]:
    def per_block(col):
        return [_f(v) for v in rows[col]] if col in rows else [None] * 6

    est_days = sorted({t.tz_convert(TZ).date() for t in filled["timestamp_utc"]}) if len(filled) else []
    lag2_day = delivery - dt.timedelta(days=2)
    lag2_status = "estimated" if lag2_day in est_days else "ok"
    wx_ok = bool(rows["weather_is_forecast"].all()) if "weather_is_forecast" in rows else False

    def last(key, col, tcol="timestamp_utc"):
        t = tables[key]
        s = t.loc[t[col].notna(), tcol]
        return None if s.empty else str(pd.Timestamp(s.max()).date())

    out = [
        {"key": "demand_lag_2d", "label": f"Zurich demand on {lag2_day:%a %d %b} (same block)", "unit": "MW",
         "values": per_block("demand_lag_2d_same_block"), "status": lag2_status, "source": "ewz",
         "as_of": last("demand", "load_mw")},
        {"key": "demand_lag_7d", "label": "Zurich demand one week before (same block)", "unit": "MW",
         "values": per_block("demand_lag_7d_same_block"), "status": "ok", "source": "ewz",
         "as_of": last("demand", "load_mw")},
        {"key": "price_today", "label": f"Swiss price today, {delivery - dt.timedelta(days=1):%a %d %b}", "unit": "EUR/MWh",
         "values": per_block("price_lag_1d_same_block"), "status": "ok" if rows["price_lag_1d_same_block"].notna().all() else "missing",
         "source": "Energy-Charts", "as_of": last("price", "price_eur_mwh")},
        {"key": "temp_fc", "label": "Temperature forecast for tomorrow", "unit": "°C",
         "values": per_block("temp_c"), "status": "ok" if wx_ok else "stale", "source": "Open-Meteo",
         "as_of": None},
        {"key": "sunshine_fc", "label": "Sunshine forecast for tomorrow", "unit": "min per hour",
         "values": per_block("sunshine_min"), "status": "ok" if wx_ok else "stale", "source": "Open-Meteo",
         "as_of": None},
        {"key": "gas", "label": "Gas price (TTF, latest close)", "unit": "EUR/MWh",
         "values": [_f(rows["gas_ttf_d_1"].iloc[0])], "status": "ok", "source": "Yahoo Finance (unofficial)",
         "as_of": last("gas", "gas_ttf_eur_mwh", "date")},
        {"key": "co2", "label": "CO₂ price (EUA, latest auction)", "unit": "EUR/t",
         "values": [_f(rows["co2_eua_d_1"].iloc[0])], "status": "ok", "source": "EEX",
         "as_of": last("co2", "co2_eua_eur_t", "date")},
        {"key": "reservoir", "label": "Swiss reservoirs (fill level)", "unit": "%",
         "values": [_f(rows["reservoir_fill_pct"].iloc[0], 1)], "status": "ok", "source": "BFE",
         "as_of": last("reservoir", "reservoir_fill_pct", "measure_date")},
        {"key": "eurchf", "label": "EUR/CHF", "unit": "CHF per EUR",
         "values": [_f(rows["eurchf_d_1"].iloc[0], 4)], "status": "ok", "source": "ECB",
         "as_of": last("eurchf", "chf_per_eur", "date")},
        {"key": "holiday", "label": "Holiday / school holiday tomorrow", "unit": "",
         "values": [int(rows["is_holiday"].iloc[0]), int(rows["is_school_holiday"].iloc[0])], "status": "ok",
         "source": "Calendar", "as_of": None},
    ]
    for item in out:
        if item["status"] == "ok" and any(v is None for v in item["values"]):
            item["status"] = "missing"
    return out


def _recent(hourly: pd.DataFrame, delivery: dt.date, n: int = 7) -> list[dict]:
    out = []
    for k in range(n, 0, -1):
        d = delivery - dt.timedelta(days=k)
        g = hourly[hourly["delivery_date"] == d]
        dem = g.groupby("block")["demand_mw"].mean().reindex(range(6))
        pr = g.groupby("block")["price_eur_mwh"].mean().reindex(range(6))
        out.append({"date": str(d), "demand_mw": [_f(v) for v in dem], "price": [_f(v) for v in pr]})
    return out


def live_plan(tables: dict, delivery: dt.date | None = None, battery: dict | None = None,
              soc_start_mwh: float | None = None, overrides: dict | None = None,
              sources: list[dict] | None = None) -> dict:
    """LivePlan (see web/src/data/types.ts) for ``delivery`` (default: tomorrow in Zurich)."""
    delivery = delivery or tomorrow_local()
    battery = {**default_battery(), **(battery or {})}
    ov = {"temp_shift_c": 0.0, "is_holiday": None, "gas_eur_mwh": None, "demand_scale_pct": 0.0, **(overrides or {})}
    bat = battery_params(battery)
    soc0 = bat.soc_start if soc_start_mwh is None else float(np.clip(soc_start_mwh, bat.soc_min, bat.soc_max))
    warnings = []

    t, filled = fill_demand_gap(tables, delivery)
    if len(filled):
        days = sorted({x.tz_convert(TZ).date() for x in filled["timestamp_utc"]})
        warnings.append(f"Zurich demand for {', '.join(f'{d:%d %b}' for d in days)} is not published yet "
                        f"({len(filled)} hours); estimated with the same hours one week earlier.")
    t = apply_overrides(t, delivery, ov)
    rows = build_rows(t, delivery)
    fc = forecast(rows, ov["demand_scale_pct"])
    for col, what in [("demand_ml_mw", "demand"), ("price_ml_eur_mwh", "price")]:
        if not np.isfinite(fc[col]).all():
            raise ValueError(f"the {what} forecast for {delivery} could not be computed (inputs missing)")
    used = set()
    for mdl in load_models().values():
        used.update(c for c in mdl.input_columns if c in rows.columns)
    missing = sorted(c for c in used if rows[c].isna().all())
    if missing:
        shown = ", ".join(missing[:6]) + (f" and {len(missing) - 6} more" if len(missing) > 6 else "")
        warnings.append(f"{len(missing)} of {len(used)} model inputs are not published yet and were left empty "
                        f"(the models handle gaps, but the forecast is less sure): {shown}.")
    if "weather_is_forecast" in rows and not rows["weather_is_forecast"].all():
        warnings.append("The weather forecast for tomorrow is incomplete; the model fell back to other weather inputs.")
    trained = load_models()["price"].info.get("trained_until")
    warnings.append(f"Models were trained on data until {trained}; they have not seen the most recent weeks.")

    data = planner_data(t, rows, delivery)
    with live_context(data, fc):
        r = rb.plan_day(delivery, rb.PRODUCT, battery=bat, soc_start_mwh=soc0, settle=False,
                        allow_sell=bool(battery.get("allow_sell", False)))
    plan, pp, hp = r["plan"], r["plan_periods"], r["hourly"]
    labels = _block_labels()

    blocks = []
    for i in range(6):
        p = plan.iloc[i]
        hrs = float(rows["hours_in_block"].iloc[i])
        blocks.append({
            "block": i, "label": labels[i], "hours": int(round(hrs)),
            "demand_fc_mw": _f(fc["demand_ml_mw"].iloc[i]),
            "demand_q10_mw": _f(fc["demand_q10_mw"].iloc[i]), "demand_q90_mw": _f(fc["demand_q90_mw"].iloc[i]),
            "demand_naive_mw": _f(fc["demand_naive_mw"].iloc[i]),
            "price_fc": _f(fc["price_ml_eur_mwh"].iloc[i]),
            "price_q10": _f(fc["price_q10_eur_mwh"].iloc[i]), "price_q90": _f(fc["price_q90_eur_mwh"].iloc[i]),
            "price_naive": _f(fc["price_naive_eur_mwh"].iloc[i]),
            "buy_mwh": _f(p["buy_mwh"]), "charge_mwh": _f(p["charge_mwh"]),
            "discharge_mwh": _f(p["discharge_mwh"]), "sell_mwh": _f(p.get("sell_mwh", 0.0)),
            "soc_end_mwh": _f(p["soc_mwh"]), "option": str(p["option"]),
            "charge_limit_eur_mwh": _f(p["charge_limit_eur_mwh"]),
        })

    hourly_mode = pp.attrs.get("plan_resolution") == "hourly" and len(pp) == len(hp)
    price_h = (pp["price_eur_mwh"].to_numpy(float) if hourly_mode
               else fc["price_ml_eur_mwh"].to_numpy(float)[hp["block"].to_numpy(int)])
    soc = soc0
    hours = []
    for h in range(len(hp)):
        x = hp.iloc[h]
        soc = soc + float(x["charge_bid_mwh"]) * bat.eta_charge - float(x["planned_discharge_mwh"]) / bat.eta_discharge
        hours.append({
            "utc": _ts(x["timestamp_utc"]), "hour": f"{pd.Timestamp(x['local_time']):%H:%M}", "block": int(x["block"]),
            "demand_fc_mw": _f(x["need_mwh"]), "price_fc": _f(price_h[h]),
            "demand_bid_mwh": _f(x["demand_bid_mwh"]), "charge_bid_mwh": _f(x["charge_bid_mwh"]),
            "charge_limit_eur_mwh": _f(x["charge_limit_eur_mwh"]) if x["charge_bid_mwh"] > 1e-9 else None,
            "planned_discharge_mwh": _f(x["planned_discharge_mwh"]), "soc_mwh": _f(soc),
        })
    bids = []
    for b in r["bids"].sort_values(["timestamp_utc", "bid_type"], kind="stable").itertuples():
        if abs(b.volume_mwh) <= 1e-9:
            continue
        bids.append({"hour": f"{pd.Timestamp(b.local_time):%H:%M}", "utc": _ts(b.timestamp_utc), "block": int(b.block),
                     "bid_type": str(b.bid_type), "volume_mwh": _f(b.volume_mwh, 3),
                     "limit_price_eur_mwh": _f(b.limit_price_eur_mwh)})

    fx = float(rows["eurchf_d_1"].iloc[0])
    at = pp.attrs
    cal = t["calendar"].copy()
    cal["date"] = pd.to_datetime(cal["date"]).dt.date
    crow = cal[cal["date"] == delivery]
    hol_name = None
    if len(crow) and bool(crow["is_holiday"].iloc[0]):
        n = crow["holiday_name"].iloc[0] if "holiday_name" in crow else None
        hol_name = n if isinstance(n, str) and n else "Holiday"
    ev = None
    if len(crow) and "event_name" in crow and isinstance(crow["event_name"].iloc[0], str) and crow["event_name"].iloc[0]:
        ev = crow["event_name"].iloc[0]
    issue = issue_time_utc(delivery).tz_convert(TZ)
    return {
        "made_at_utc": _ts(pd.Timestamp.now(tz="UTC")),
        "delivery_date": str(delivery),
        "issue_time_local": f"{issue:%Y-%m-%d %H:%M}",
        "weekday": f"{delivery:%A}",
        "is_holiday": bool(len(crow) and bool(crow["is_holiday"].iloc[0])),
        "holiday_name": hol_name,
        "event_name": ev,
        "battery": {**{k: float(battery[k]) for k in BATTERY_FIELDS}, "allow_sell": bool(battery.get("allow_sell", False))},
        "soc_start_mwh": _f(soc0),
        "blocks": blocks,
        "hours": hours,
        "bids": bids,
        "summary": {
            "energy_to_buy_mwh": _f(plan["buy_mwh"].sum(), 1),
            "charged_mwh": _f(plan["charge_mwh"].sum(), 1),
            "discharged_mwh": _f(plan["discharge_mwh"].sum(), 1),
            "expected_cost_chf": _f(at.get("cost_eur", np.nan) * fx, 0),
            "expected_battery_saving_chf": _f(at.get("saving_eur", np.nan) * fx, 0),
            "eurchf": _f(fx, 4),
        },
        "inputs": _inputs(rows, t, filled, delivery),
        "recent": _recent(data_hourly(data), delivery),
        "sources": sources or [],
        "overrides": {"temp_shift_c": float(ov["temp_shift_c"] or 0.0),
                      "is_holiday": None if ov["is_holiday"] is None else bool(ov["is_holiday"]),
                      "gas_eur_mwh": None if ov["gas_eur_mwh"] is None else float(ov["gas_eur_mwh"]),
                      "demand_scale_pct": float(ov["demand_scale_pct"] or 0.0)},
        "warnings": warnings,
    }


def data_hourly(data: dict) -> pd.DataFrame:
    return pd.concat(list(data["hours"].values()), ignore_index=True)


def is_default(overrides: dict | None, soc_start_mwh, battery: dict | None) -> bool:
    ov = overrides or {}
    no_ov = (not ov.get("temp_shift_c")) and ov.get("is_holiday") is None and ov.get("gas_eur_mwh") is None \
        and not ov.get("demand_scale_pct")
    bat = battery or {}
    default = default_battery()
    same_bat = all(abs(float(bat.get(k, default[k])) - default[k]) < 1e-9 for k in BATTERY_FIELDS)
    return no_ov and soc_start_mwh is None and same_bat


# ---------------------------------------------------------------------------
# log of live plans (track record)
# ---------------------------------------------------------------------------
def save_log(plan: dict) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    entry = {"delivery_date": plan["delivery_date"], "made_at_utc": plan["made_at_utc"],
             "blocks": [{"label": b["label"], "demand_fc_mw": b["demand_fc_mw"], "price_fc": b["price_fc"]}
                        for b in plan["blocks"]],
             "summary": {"energy_to_buy_mwh": plan["summary"]["energy_to_buy_mwh"],
                         "expected_cost_chf": plan["summary"]["expected_cost_chf"]}}
    (LOG_DIR / f"{plan['delivery_date']}.json").write_text(json.dumps(entry, indent=1), encoding="utf-8")


def read_log(tables: dict | None) -> list[dict]:
    """Saved live plans, newest first, with block actuals where the tables already have them."""
    if not LOG_DIR.exists():
        return []
    entries = [json.loads(f.read_text(encoding="utf-8")) for f in sorted(LOG_DIR.glob("*.json"))]
    if tables and entries:
        days = [dt.date.fromisoformat(e["delivery_date"]) for e in entries]
        h = hourly_frame(tables, min(days), max(days))
        h["delivery_date"] = pd.to_datetime(h["delivery_date"]).dt.date
        for e, d in zip(entries, days):
            g = h[h["delivery_date"] == d]
            n = g.groupby("block").size().reindex(range(6))
            dem = g.groupby("block")["demand_mw"].agg(lambda s: s.mean() if s.notna().all() else np.nan).reindex(range(6))
            pr = g.groupby("block")["price_eur_mwh"].agg(lambda s: s.mean() if s.notna().all() else np.nan).reindex(range(6))
            for i, b in enumerate(e["blocks"]):
                ok = bool(n.iloc[i] > 0)
                b["demand_actual_mw"] = _f(dem.iloc[i]) if ok else None
                b["price_actual"] = _f(pr.iloc[i]) if ok else None
    else:
        for e in entries:
            for b in e["blocks"]:
                b.setdefault("demand_actual_mw", None)
                b.setdefault("price_actual", None)
    return sorted(entries, key=lambda e: e["delivery_date"], reverse=True)
