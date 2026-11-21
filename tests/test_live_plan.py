"""Tests for the live plan (src/live/plan.py) and the /api/live/* endpoints.

The live plan is run on a stored day (2026-10-15) with the input tables cut at that day's forecast
time, so it must reproduce the backtest:
* demand forecast = reports/predictions_demand.parquet (same saved model, same features)
* the battery plan = run_backtest.plan_day with the same forecasts (same planner, same rules)
The price forecast is NOT compared with the stored October predictions: those come from weekly
walk-forward refits, the live tab uses the saved model (trained until 2026-09-30).
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from src.backtest import run_backtest as rb
from src.config import ROOT

DAY = dt.date(2026, 10, 15)

pytestmark = pytest.mark.skipif(not (ROOT / "data" / "processed" / "features.parquet").exists(),
                                reason="processed data not built")


@pytest.fixture(scope="module")
def cut_tables():
    from src.features.build_features import load_tables
    from src.live import plan as lp
    from tests.test_no_leakage import truncate
    return truncate(load_tables(), pd.Timestamp(DAY), lp.issue_time_utc(DAY))


@pytest.fixture(scope="module")
def base_plan(cut_tables):
    from src.live import plan as lp
    return lp.live_plan(cut_tables, DAY)


def test_demand_forecast_matches_backtest(base_plan):
    p = pd.read_parquet(ROOT / "reports" / "predictions_demand.parquet")
    p["delivery_date"] = pd.to_datetime(p["delivery_date"]).dt.date
    p = p[p["delivery_date"] == DAY].drop_duplicates("block", keep="last").sort_values("block")
    live = np.array([b["demand_fc_mw"] for b in base_plan["blocks"]])
    assert np.allclose(live, p["pred_best"].to_numpy(), atol=0.006)   # live values are rounded to 0.01


def test_plan_matches_backtest_planner(base_plan):
    dem = [b["demand_fc_mw"] for b in base_plan["blocks"]]
    price = [b["price_fc"] for b in base_plan["blocks"]]
    r = rb.plan_day(DAY, rb.PRODUCT, settle=False, soc_start_mwh=base_plan["soc_start_mwh"],
                    demand_override_mw=dem, price_override=price)
    live_buy = np.array([b["buy_mwh"] for b in base_plan["blocks"]])
    assert np.allclose(live_buy, r["plan"]["buy_mwh"].to_numpy(), atol=0.05)
    assert [b["option"] for b in base_plan["blocks"]] == list(r["plan"]["option"])


def test_plan_is_complete(base_plan):
    assert len(base_plan["blocks"]) == 6 and len(base_plan["hours"]) == 24
    assert base_plan["bids"] and all(b["volume_mwh"] > 0 for b in base_plan["bids"])
    demand_bids = sum(b["volume_mwh"] for b in base_plan["bids"] if b["bid_type"] == "demand")
    charge_bids = sum(b["volume_mwh"] for b in base_plan["bids"] if b["bid_type"] == "charge")
    assert abs(demand_bids + charge_bids - base_plan["summary"]["energy_to_buy_mwh"]) < 0.5
    assert {i["key"] for i in base_plan["inputs"]} >= {"demand_lag_2d", "price_today", "temp_fc", "gas"}
    assert len(base_plan["recent"]) == 7


def test_overrides_move_the_forecast(cut_tables, base_plan):
    from src.live import plan as lp
    cold = lp.live_plan(cut_tables, DAY, overrides={"temp_shift_c": -8})
    hol = lp.live_plan(cut_tables, DAY, overrides={"is_holiday": True})
    scaled = lp.live_plan(cut_tables, DAY, overrides={"demand_scale_pct": 10})
    total = lambda p: sum(b["demand_fc_mw"] for b in p["blocks"])  # noqa: E731
    assert total(cold) > total(base_plan)          # colder October day -> more heating
    assert total(hol) < total(base_plan)           # holiday -> less demand
    assert abs(total(scaled) / total(base_plan) - 1.10) < 0.002
    assert cold["overrides"]["temp_shift_c"] == -8


def test_demand_gap_is_filled_and_flagged(cut_tables):
    from src.live import plan as lp
    t = dict(cut_tables)
    d = t["demand"]
    t["demand"] = d[d["timestamp_utc"] < lp.midnight_utc(DAY - dt.timedelta(days=2))]   # one day missing
    p = lp.live_plan(t, DAY)
    assert any("not published yet" in w for w in p["warnings"])
    assert next(i for i in p["inputs"] if i["key"] == "demand_lag_2d")["status"] == "estimated"


def test_api_rejects_bad_battery():
    from fastapi.testclient import TestClient
    from api.server import app
    bad = {"power_mw": 0, "capacity_mwh": 40, "soc_min_frac": 0.1, "soc_max_frac": 0.9, "soc_start_frac": 0.5,
           "round_trip_efficiency": 0.9, "max_cycles_per_day": 1, "wear_cost_eur_per_mwh": 5}
    with TestClient(app) as c:
        r = c.post("/api/live/plan", json={"battery": bad})
    assert r.status_code == 422 and "power_mw" in r.json()["detail"]
