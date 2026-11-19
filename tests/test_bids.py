"""Tests for the hourly auction bids (src/decision/bids.py)."""
import numpy as np
import pandas as pd
import pytest

from src.backtest.run_backtest import DecisionParams, plan_day
from src.decision.bids import (
    add_protection, allocate_discharge, at_risk_discharge, bids_table, block_hour_shares,
    charge_limit_prices, hourly_plan,
)
from src.optimisation.battery_lp import BatteryParams

BLOCK = DecisionParams(plan_resolution="block")
HOURLY = DecisionParams(plan_resolution="hourly_shape", shape_daytype=True)


def test_shares_follow_reference_shape_and_sum_to_one():
    ref = pd.DataFrame({"hour_local": [0, 1, 2, 3], "demand_mw": [100.0, 200.0, 300.0, 400.0]})
    s = block_hour_shares([0, 1, 2, 3], ref)
    assert s.sum() == pytest.approx(1.0)
    assert s == pytest.approx([0.1, 0.2, 0.3, 0.4])


def test_shares_flat_when_reference_missing():
    assert block_hour_shares([0, 1, 2, 3], None) == pytest.approx([0.25] * 4)
    empty = pd.DataFrame({"hour_local": [], "demand_mw": []})
    assert block_hour_shares([0, 1, 2, 3], empty) == pytest.approx([0.25] * 4)


def test_shares_dst_blocks():
    ref = pd.DataFrame({"hour_local": [0, 1, 2, 3], "demand_mw": [100.0, 200.0, 300.0, 400.0]})
    # autumn: 5 hours, hour 2 twice
    s5 = block_hour_shares([0, 1, 2, 2, 3], ref)
    assert len(s5) == 5 and s5.sum() == pytest.approx(1.0)
    assert s5[2] == pytest.approx(s5[3])
    # spring: 3 hours, no hour 2
    s3 = block_hour_shares([0, 1, 3], ref)
    assert s3 == pytest.approx(np.array([100, 200, 400]) / 700)


def _plan(price, charge, dis):
    return pd.DataFrame({"price_eur_mwh": price, "charge_mwh": charge, "discharge_mwh": dis})


def test_limit_price_uses_discharge_weighted_price():
    p = _plan([40, 50, 60, 70, 150, 100], [20, 0, 0, 0, 0, 0], [0, 0, 0, 0, 10, 10])
    lim = charge_limit_prices(p, 0.9, 5.0)
    assert lim[0] == pytest.approx(125 * 0.9 - 5)  # (150*10 + 100*10) / 20 = 125
    assert np.isnan(lim[1:]).all()


def test_limit_price_charge_after_discharge_and_refill():
    # discharge in block 1, charge later in block 4: use the day's discharge price
    p = _plan([40, 150, 60, 70, 30, 100], [0, 0, 0, 0, 10, 0], [0, 9, 0, 0, 0, 0])
    assert charge_limit_prices(p, 0.9, 5.0)[4] == pytest.approx(150 * 0.9 - 5)
    # no discharge at all (refill to the target level): limit = highest forecast price
    p = _plan([40, 150, 60, 70, 30, 100], [5, 0, 0, 0, 0, 0], [0] * 6)
    assert charge_limit_prices(p, 0.9, 5.0)[0] == pytest.approx(150)


def test_quantile_rule_caps_the_limit():
    p = _plan([40, 50, 60, 70, 150, 100], [20, 0, 0, 0, 0, 0], [0, 0, 0, 0, 10, 10])
    lim = charge_limit_prices(p, 0.9, 5.0, price_q90=[55, 60, 70, 80, 170, 120])
    assert lim[0] == pytest.approx(55)        # min(107.5, q90 = 55)
    lim = charge_limit_prices(p, 0.9, 5.0, price_q90=[500] * 6)
    assert lim[0] == pytest.approx(107.5)     # cap not binding


def test_allocate_discharge_hand_example():
    # even split 12.5 would exceed the first hour's need of 5 -> 5, the rest evenly
    out = allocate_discharge(50.0, [5.0, 20.0, 20.0, 20.0])
    assert out == pytest.approx([5.0, 15.0, 15.0, 15.0])
    assert allocate_discharge(40.0, [20.0] * 4) == pytest.approx([10.0] * 4)   # not binding: even
    assert allocate_discharge(65.0, [5.0, 20.0, 20.0, 20.0]) == pytest.approx([5, 20, 20, 20])
    with pytest.raises(ValueError):
        allocate_discharge(66.0, [5.0, 20.0, 20.0, 20.0])


def test_low_load_hour_bid_conservation():
    """One block of 4 hours with a very low first hour: the planned discharge is never above
    an hour's need, demand bids are never negative and the block totals are conserved."""
    plan = pd.DataFrame({"demand_mwh": [100.0], "charge_mwh": [0.0], "discharge_mwh": [60.0], "option": ["use_storage_and_buy"]})
    hours = pd.DataFrame({"delivery_date": ["2026-10-14"] * 4, "timestamp_utc": pd.date_range("2026-10-13 22:00", periods=4, freq="h", tz="UTC"),
                          "local_time": pd.date_range("2026-10-14 00:00", periods=4, freq="h", tz="Europe/Zurich"),
                          "hour_local": [0, 1, 2, 3], "block": 0, "period": 0, "share": [0.05, 0.25, 0.35, 0.35]})
    hp = hourly_plan(plan, hours, None, power_mw=20.0)
    assert (hp["planned_discharge_mwh"] <= hp["need_mwh"] + 1e-9).all()
    assert (hp["planned_discharge_mwh"] <= 20 + 1e-9).all()
    assert (hp["demand_bid_mwh"] >= 0).all()
    assert hp["planned_discharge_mwh"].sum() == pytest.approx(60.0)
    assert hp["demand_bid_mwh"].sum() == pytest.approx(100.0 - 60.0)
    assert hp["planned_discharge_mwh"].iloc[0] == pytest.approx(5.0)   # first hour needs only 5 MWh


def test_low_load_with_huge_battery_in_plan_day():
    """A 300 MW battery is larger than the city's night load: the optimiser is limited to
    sum over hours of min(need, power) per block, so the bids still add up exactly."""
    big = BatteryParams.from_config(power_mw=300.0, capacity_mwh=600.0)
    for day in ["2026-10-14", "2026-10-25", "2026-03-29"]:
        r = plan_day(day, "ml_battery", battery=big, decision=BLOCK, settle=False)
        hp, plan = r["hourly"], r["plan"]
        assert (hp["planned_discharge_mwh"] <= hp["need_mwh"] + 1e-6).all()
        assert (hp["demand_bid_mwh"] >= 0).all()
        per_block = hp.groupby("block")[["planned_discharge_mwh", "demand_bid_mwh", "charge_bid_mwh"]].sum()
        assert np.allclose(per_block["planned_discharge_mwh"], plan["discharge_mwh"], atol=1e-6)
        assert np.allclose(per_block["demand_bid_mwh"] + per_block["charge_bid_mwh"], plan["buy_mwh"], atol=1e-6)


def test_at_risk_volume_hand_example():
    # start 20 MWh, min 4 -> (20-4)*0.9 = 14.4 MWh surely deliverable (eta_d = 0.9 here)
    hp = pd.DataFrame({"charge_bid_mwh": [10.0, 0, 0, 0], "charge_limit_eur_mwh": [50.0, np.nan, np.nan, np.nan],
                       "planned_discharge_mwh": [0.0, 10.0, 10.0, 0.0], "demand_bid_mwh": [100.0, 90, 90, 100]})
    risk = at_risk_discharge(hp, 20.0, 4.0, 1.0, 0.9)
    assert risk == pytest.approx([0, 0, 5.6, 0])
    # a price-independent charge always clears -> it counts as sure energy
    hp2 = hp.assign(charge_limit_eur_mwh=np.nan)
    assert at_risk_discharge(hp2, 20.0, 4.0, 1.0, 0.9) == pytest.approx([0, 0, 0, 0])
    prot = add_protection(hp, 20.0, 4.0, 1.0, 0.9)
    assert prot["demand_bid_mwh"].sum() == pytest.approx(380 + 5.6)


@pytest.mark.parametrize("decision", [BLOCK, HOURLY], ids=["block", "hourly_shape"])
@pytest.mark.parametrize("day,first_block_hours", [("2026-10-14", 4), ("2026-10-25", 5), ("2026-03-29", 3)])
def test_bid_volumes_per_block_sum_to_plan(day, first_block_hours, decision):
    r = plan_day(day, "ml_battery", decision=decision, settle=False)
    plan, bids = r["plan"], r["bids"]
    assert len(plan) == 6                                  # always the 6-block decision table
    dem = bids[bids.bid_type == "demand"]
    assert len(dem) == 24 - 4 + first_block_hours
    assert (dem.groupby("block").size().loc[0]) == first_block_hours
    if decision.plan_resolution == "hourly_shape":
        assert len(r["plan_periods"]) == 24 - 4 + first_block_hours
    per_block = bids.groupby("block")["volume_mwh"].sum()
    at_risk = r["hourly"].groupby("block")["at_risk_bid_mwh"].sum()
    assert np.allclose(per_block.to_numpy(), plan["buy_mwh"].to_numpy() + at_risk.to_numpy(), atol=1e-6)
    chg = bids[bids.bid_type == "charge"].groupby("block")["volume_mwh"].sum()
    for b, v in chg.items():
        assert v == pytest.approx(plan.loc[b, "charge_mwh"])
    assert (bids["volume_mwh"] >= 0).all()
    # never more than the battery power per hour
    assert (bids.loc[bids.bid_type == "charge", "volume_mwh"] <= 20 + 1e-9).all()
    assert (r["hourly"]["planned_discharge_mwh"] <= 20 + 1e-9).all()
    # demand bids are price-independent
    assert dem["limit_price_eur_mwh"].isna().all()
    assert set(plan["option"]) <= {"buy", "buy_and_store", "use_storage", "use_storage_and_buy"}


def test_bids_table_one_row_per_hour():
    r = plan_day("2026-10-25", "ml_battery", settle=False)
    t = bids_table(r["bids"])
    assert len(t) == 25
    limits = t["Charge limit EUR/MWh"]
    assert ((limits == "-") == (t["Charge bid MWh"] == 0)).all()  # "-" exactly where there is no charge bid
    at_risk = r["hourly"]["at_risk_bid_mwh"].sum()
    assert t["Total bid MWh"].sum() == pytest.approx(r["plan"]["buy_mwh"].sum() + at_risk, abs=0.05)
    # the doubled 02:00 hour is shown with two different UTC offsets
    assert {"02:00 (UTC+02)", "02:00 (UTC+01)"}.issubset(set(t["Hour (local)"]))
