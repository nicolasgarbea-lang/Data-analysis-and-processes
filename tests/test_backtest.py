"""Tests for the backtest settlement (src/backtest/run_backtest.py)."""
import time

import numpy as np
import pandas as pd
import pytest

import src.backtest.run_backtest as rb
from src.backtest.run_backtest import (
    STRATEGIES, ImbalanceParams, plan_day, run_backtest, settle_hours, summarise,
)
from src.optimisation.battery_lp import BatteryParams

BAT = BatteryParams(power_mw=20, capacity_mwh=40, soc_min_frac=0.1, soc_max_frac=0.9, soc_start_frac=0.5,
                    round_trip_efficiency=0.9, max_cycles_per_day=1, wear_cost_eur_per_mwh=5.0)
IMB = ImbalanceParams(shortage_factor=1.2, surplus_factor=0.8)


def _hp(demand_bid, charge_bid, limit, dis):
    return pd.DataFrame({"demand_bid_mwh": demand_bid, "charge_bid_mwh": charge_bid,
                         "charge_limit_eur_mwh": limit, "planned_discharge_mwh": dis})


def test_tiny_hand_computed_day():
    """Hour 0: buy 100 + charge 10 at 40 EUR (limit 50 -> clears), city uses 98 -> 2 MWh surplus.
    Hour 1: buy 90 at 100 EUR, discharge 9, city uses 101 -> 2 MWh shortage."""
    hp = _hp([100.0, 90.0], [10.0, 0.0], [50.0, np.nan], [0.0, 9.0])
    st, soc_end = settle_hours(hp, [98.0, 101.0], [40.0, 100.0], [0.9, 0.9], BAT, 20.0, IMB)
    da = 110 * 40 + 90 * 100            # 13 400
    surplus_rev = 2 * (40 - 0.2 * 40)   # 64
    shortage = 2 * (100 + 0.2 * 100)    # 240
    wear = 9 * 5                        # 45
    assert st["da_cost_eur"].sum() == pytest.approx(da)
    assert st["imbalance_cost_eur"].sum() == pytest.approx(shortage - surplus_rev)
    assert st["wear_cost_eur"].sum() == pytest.approx(wear)
    assert st["total_cost_eur"].sum() == pytest.approx(13621.0)
    assert st["total_cost_chf"].sum() == pytest.approx(13621.0 * 0.9)
    assert soc_end == pytest.approx(20.0)  # 10 * sqrt(.9) in, 9 / sqrt(.9) out
    assert st["imbalance_penalty_eur"].sum() == pytest.approx(2 * 0.2 * 40 + 2 * 0.2 * 100)


def test_uncleared_charge_gives_no_phantom_discharge():
    hp = _hp([100.0, 90.0], [10.0, 0.0], [50.0, np.nan], [0.0, 9.0])
    st, soc_end = settle_hours(hp, [100.0, 99.0], [60.0, 100.0], [1.0, 1.0], BAT, BAT.soc_min, IMB)
    assert st["charge_cleared_mwh"].sum() == 0          # 60 > limit 50
    assert st["discharged_mwh"].sum() == 0              # battery was empty
    assert st.loc[1, "discharge_not_delivered_mwh"] == pytest.approx(9.0)
    assert st.loc[1, "shortage_mwh"] == pytest.approx(9.0)
    assert soc_end == pytest.approx(BAT.soc_min)


def test_negative_price_imbalance_still_penalises():
    p = -50.0
    st, _ = settle_hours(_hp([10.0], [0.0], [np.nan], [0.0]), [11.0], [p], [1.0], BAT, 20.0, IMB)
    # shortage of 1 MWh: pay -40 (i.e. receive only 40 instead of 50 at day-ahead)
    assert st["imbalance_cost_eur"].sum() == pytest.approx(-40.0)
    assert st["imbalance_cost_eur"].sum() > 1 * p
    st, _ = settle_hours(_hp([10.0], [0.0], [np.nan], [0.0]), [9.0], [p], [1.0], BAT, 20.0, IMB)
    # surplus of 1 MWh at a negative price: we must pay 60 to get rid of it
    assert st["imbalance_cost_eur"].sum() == pytest.approx(60.0)
    assert st["imbalance_penalty_eur"].sum() == pytest.approx(10.0)


def test_soc_limits_and_energy_conservation_hold():
    hp = _hp([50.0] * 4, [20.0] * 4, [np.nan] * 4, [0.0] * 4)  # tries to overfill
    st, soc_end = settle_hours(hp, [50.0] * 4, [10.0] * 4, [1.0] * 4, BAT, 20.0, IMB)
    assert soc_end <= BAT.soc_max + 1e-9
    assert st["charge_overflow_mwh"].sum() > 0     # energy that did not fit goes to the city
    assert st["surplus_mwh"].sum() == pytest.approx(st["charge_overflow_mwh"].sum())


@pytest.mark.parametrize("strategy", ["perfect_foresight_battery", "perfect_foresight_hourly_battery",
                                      "perfect_demand_no_battery"])
def test_perfect_foresight_has_zero_imbalance(strategy):
    for day in ["2026-10-02", "2026-10-25", "2026-03-29"]:
        s = plan_day(day, strategy)["summary"]
        assert s["shortage_mwh"] == pytest.approx(0, abs=1e-6)
        assert s["surplus_mwh"] == pytest.approx(0, abs=1e-6)
        # charge limit is not binding under perfect foresight: every charge bid clears
        assert np.isnan(s["share_charge_cleared"]) or s["share_charge_cleared"] == pytest.approx(1.0)


@pytest.mark.parametrize("strategy", [k for k, v in STRATEGIES.items() if not v["battery"]])
def test_no_battery_strategies_never_touch_battery(strategy):
    daily, _ = run_backtest("2026-10-01", "2026-10-05", strategies=[strategy], n_boot=0)
    assert (daily[["charge_bid_mwh", "charged_mwh", "discharged_mwh", "cycles"]] == 0).all().all()
    assert (daily["soc_end_mwh"] == daily["soc_start_mwh"]).all()


def test_costs_add_up_and_charge_level_is_carried_over():
    daily, summary = run_backtest("2026-10-01", "2026-10-07", strategies=["ml_battery", "baseline_naive_no_battery"],
                                  n_boot=0)
    total = daily["da_cost_eur"] + daily["imbalance_cost_eur"] + daily["wear_cost_eur"]
    assert np.allclose(total, daily["total_cost_eur"])
    ml = daily[daily.strategy == "ml_battery"].reset_index(drop=True)
    assert np.allclose(ml["soc_start_mwh"].iloc[1:].to_numpy(), ml["soc_end_mwh"].iloc[:-1].to_numpy())
    assert ml["soc_start_mwh"].iloc[0] == pytest.approx(BatteryParams.from_config().soc_start)


def test_summary_bootstrap_is_reproducible():
    daily, _ = run_backtest("2026-10-01", "2026-10-10", strategies=["baseline_naive_no_battery", "ml_battery"],
                            n_boot=0)
    a = summarise(daily, n_boot=200, seed=7)
    b = summarise(daily, n_boot=200, seed=7)
    pd.testing.assert_frame_equal(a, b)


def test_price_noise_sensitivity_reproducible():
    from src.backtest.analysis import price_error_sensitivity
    from src.backtest.run_backtest import DecisionParams, dates_between
    dates = dates_between("2026-10-01", "2026-10-03")
    a = price_error_sensitivity(dates, DecisionParams(), sigmas=(0, 20), seeds=2, seed=3)
    b = price_error_sensitivity(dates, DecisionParams(), sigmas=(0, 20), seeds=2, seed=3)
    pd.testing.assert_frame_equal(a, b)


def test_single_day_planning_is_fast():
    plan_day("2026-10-10", "ml_battery")  # warm-up (loads the data once)
    t = time.time()
    plan_day("2026-10-11", "ml_battery")
    plan_day("2026-10-11", "perfect_foresight_hourly_battery")
    assert (time.time() - t) / 2 < 0.5


def test_require_ml_fails_loudly(monkeypatch, tmp_path):
    monkeypatch.setattr(rb, "PRED_FILES", {"demand": tmp_path / "nope_d.parquet", "price": tmp_path / "nope_p.parquet"})
    rb.load_forecasts.cache_clear()
    try:
        with pytest.raises(FileNotFoundError):
            rb.load_forecasts(require_ml=True)
    finally:
        rb.load_forecasts.cache_clear()


def test_real_prediction_files_are_picked_up(monkeypatch, tmp_path):
    dates = pd.date_range("2026-10-01", "2026-10-31").date
    rows = pd.DataFrame([(d, b) for d in dates for b in range(6)], columns=["delivery_date", "block"])
    for target, val in [("demand", 250.0), ("price", 77.0)]:
        p = rows.copy()
        p["split"] = "test"
        p["y_true"] = 0.0
        for c in ["pred_naive", "pred_linear", "pred_rf", "pred_gbm"]:
            p[c] = val - 1
        p["pred_best"] = val
        p.to_parquet(tmp_path / f"pred_{target}.parquet")
    monkeypatch.setattr(rb, "PRED_FILES", {"demand": tmp_path / "pred_demand.parquet",
                                           "price": tmp_path / "pred_price.parquet"})
    rb.load_forecasts.cache_clear()
    rb._forecast_index.cache_clear()
    try:
        fc = rb.load_forecasts(require_ml=True)
        oct_ = fc[fc.split == "test"]
        assert len(oct_) == 186 and (oct_.demand_ml_mw == 250).all() and (oct_.price_ml_eur_mwh == 77).all()
        assert (oct_.demand_source == "ml").all()
        r = plan_day("2026-10-14", "ml_battery", require_ml=True)
        assert r["plan"]["price_eur_mwh"].eq(77).all()
        assert r["summary"]["forecast_demand_mwh"] == pytest.approx(250 * 24)
        # outside the file the ML forecast is missing -> loud error, no silent fallback
        with pytest.raises(ValueError):
            plan_day("2026-09-14", "ml_battery", require_ml=True)
    finally:
        rb.load_forecasts.cache_clear()
        rb._forecast_index.cache_clear()
