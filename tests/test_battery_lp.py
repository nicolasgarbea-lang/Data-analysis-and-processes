"""Unit tests for the battery optimiser (src/optimisation/battery_lp.py)."""
import numpy as np
import pytest

from src.optimisation.battery_lp import BatteryParams, label_option, solve_battery_plan

BAT = BatteryParams(
    power_mw=20, capacity_mwh=40, soc_min_frac=0.1, soc_max_frac=0.9, soc_start_frac=0.5,
    round_trip_efficiency=0.9, max_cycles_per_day=1, wear_cost_eur_per_mwh=5.0,
)
DEMAND = np.array([800.0, 900.0, 1300.0, 1300.0, 1250.0, 1000.0])  # MWh per 4-hour block


def check_physics(plan, bat=BAT, soc_start=None):
    """Checks that must hold for every plan."""
    soc0 = bat.soc_start if soc_start is None else soc_start
    eta = np.sqrt(bat.round_trip_efficiency)
    max_e = bat.power_mw * plan["hours"].to_numpy()
    assert (plan["charge_mwh"] <= max_e + 1e-6).all()
    assert (plan["discharge_mwh"] <= max_e + 1e-6).all()
    assert (plan["soc_mwh"] >= bat.soc_min - 1e-6).all()
    assert (plan["soc_mwh"] <= bat.soc_max + 1e-6).all()
    assert (plan[["buy_mwh", "charge_mwh", "discharge_mwh", "sell_mwh"]] >= -1e-9).all().all()
    # no charging and discharging in the same block
    assert ((plan["charge_mwh"] > 1e-6) & (plan["discharge_mwh"] > 1e-6)).sum() == 0
    # charge level follows the flows
    prev = soc0
    for r in plan.itertuples():
        assert r.soc_mwh == pytest.approx(prev + eta * r.charge_mwh - r.discharge_mwh / eta, abs=1e-5)
        prev = r.soc_mwh
    # energy balance
    lhs = plan["buy_mwh"] - plan["sell_mwh"]
    rhs = plan["demand_mwh"] + plan["charge_mwh"] - plan["discharge_mwh"]
    assert np.allclose(lhs, rhs, atol=1e-5)
    # one cycle per day at most
    assert plan["discharge_mwh"].sum() <= bat.max_cycles_per_day * bat.usable_mwh + 1e-6


def test_flat_prices_battery_idle():
    plan = solve_battery_plan(DEMAND, [80.0] * 6, battery=BAT)
    check_physics(plan)
    assert plan["charge_mwh"].sum() == pytest.approx(0, abs=1e-6)
    assert plan["discharge_mwh"].sum() == pytest.approx(0, abs=1e-6)
    assert (plan["option"] == "buy").all()
    assert plan.attrs["saving_eur"] == pytest.approx(0, abs=1e-3)


def test_cheap_night_expensive_evening():
    prices = [30.0, 40.0, 90.0, 80.0, 150.0, 100.0]
    plan = solve_battery_plan(DEMAND, prices, battery=BAT)
    check_physics(plan)
    assert plan.loc[0, "charge_mwh"] > 1  # charges in the cheapest block
    assert plan.loc[4, "discharge_mwh"] > 1  # discharges in the most expensive block
    assert plan.loc[0, "option"] == "buy_and_store"
    assert plan.loc[4, "option"] == "use_storage_and_buy"
    assert plan.attrs["saving_eur"] > 0
    assert plan.loc[5, "soc_mwh"] == pytest.approx(BAT.soc_start, abs=1e-5)


def test_never_exceeds_power_or_capacity():
    rng = np.random.default_rng(0)
    small = BatteryParams(power_mw=3, capacity_mwh=40, wear_cost_eur_per_mwh=0.0)
    for _ in range(25):
        prices = rng.normal(80, 60, 6)  # includes negative prices
        demand = rng.uniform(600, 1400, 6)
        for bat in (BAT, small):
            plan = solve_battery_plan(demand, prices, battery=bat)
            check_physics(plan, bat)
            # the optimiser can never be worse than doing nothing
            assert plan.attrs["cost_eur"] <= plan.attrs["cost_no_battery_eur"] + 1e-3


def test_small_spread_battery_idle():
    # Buying 1 MWh at 80 returns 0.9 MWh worth 0.9*85 = 76.5, minus wear -> a loss.
    prices = [80.0, 80.0, 82.0, 83.0, 85.0, 82.0]
    plan = solve_battery_plan(DEMAND, prices, battery=BAT)
    check_physics(plan)
    assert plan["charge_mwh"].sum() == pytest.approx(0, abs=1e-6)
    assert plan["discharge_mwh"].sum() == pytest.approx(0, abs=1e-6)


def test_dst_day_with_three_hour_block():
    hours = [3.0, 4.0, 4.0, 4.0, 4.0, 4.0]  # spring: the night block has only 3 hours
    demand = np.array([200.0, 225.0, 325.0, 325.0, 312.0, 250.0]) * np.array(hours)
    weak = BatteryParams(power_mw=5, capacity_mwh=40)
    plan = solve_battery_plan(demand, [10.0, 60.0, 90.0, 80.0, 200.0, 100.0], hours=hours, battery=weak)
    check_physics(plan, weak)
    assert plan.loc[0, "charge_mwh"] <= 5 * 3 + 1e-6  # 5 MW for 3 hours
    assert plan.loc[0, "charge_mwh"] == pytest.approx(15.0, abs=1e-4)
    # autumn: 5-hour block also works
    plan5 = solve_battery_plan(demand, [10.0, 60.0, 90.0, 80.0, 200.0, 100.0],
                               hours=[5.0, 4, 4, 4, 4, 4], battery=weak)
    check_physics(plan5, weak)


def test_negative_prices_no_simultaneous_charge_and_discharge():
    prices = [-50.0, -20.0, 40.0, 10.0, 120.0, 90.0]
    plan = solve_battery_plan(DEMAND, prices, battery=BAT)
    check_physics(plan)
    assert plan.loc[0, "charge_mwh"] > 0


def test_allow_sell_and_low_demand():
    # demand lower than the battery power: without selling, discharge is capped by demand
    demand = np.array([10.0] * 6)
    prices = [10.0, 10.0, 10.0, 10.0, 300.0, 10.0]
    no_sell = solve_battery_plan(demand, prices, battery=BAT)
    check_physics(no_sell)
    assert no_sell["sell_mwh"].sum() == 0
    assert no_sell.loc[4, "discharge_mwh"] <= 10.0 + 1e-6
    assert no_sell.loc[4, "option"] == "use_storage"
    with_sell = solve_battery_plan(demand, prices, battery=BAT, allow_sell=True)
    check_physics(with_sell)
    assert with_sell.loc[4, "sell_mwh"] > 0
    assert with_sell.attrs["cost_eur"] < no_sell.attrs["cost_eur"]


def test_hourly_periods_and_custom_soc():
    prices = np.r_[np.full(6, 20.0), np.full(12, 70.0), np.full(4, 160.0), np.full(2, 60.0)]
    demand = np.full(24, 250.0)
    plan = solve_battery_plan(demand, prices, hours=np.ones(24), battery=BAT, soc_start_mwh=4.0, soc_end_mwh=4.0)
    check_physics(plan, soc_start=4.0)
    assert plan["discharge_mwh"].sum() == pytest.approx(BAT.usable_mwh * np.sqrt(0.9), abs=1e-3)


def test_labels():
    assert label_option(100, 0, 0) == "buy"
    assert label_option(120, 20, 0) == "buy_and_store"
    assert label_option(80, 0, 20) == "use_storage_and_buy"
    assert label_option(0, 0, 20) == "use_storage"


def test_bad_input():
    with pytest.raises(ValueError):
        solve_battery_plan([1, 2], [1, 2, 3])
    with pytest.raises(ValueError):
        solve_battery_plan([1, np.nan], [1, 2])


def test_start_level_outside_limits_is_rejected():
    with pytest.raises(ValueError):
        solve_battery_plan(DEMAND, [50.0] * 6, battery=BAT, soc_start_mwh=3.0)
    with pytest.raises(ValueError):
        solve_battery_plan(DEMAND, [50.0] * 6, battery=BAT, soc_start_mwh=37.0)


def test_exact_optimum_with_large_demand_bill():
    # The city's bill is ~1000x the battery saving; the solver must still find the exact best plan.
    demand = DEMAND * 10
    prices = [30.0, 40.0, 90.0, 80.0, 150.0, 100.0]
    plan = solve_battery_plan(demand, prices, battery=BAT)
    eta = np.sqrt(0.9)
    # best plan by hand: fill from 20 to 36 MWh at 30, empty to 4 MWh at 150, refill to 20 at the
    # cheapest later price (100): only if worth it -> it must refill because the end level is fixed
    discharged = 32 * eta          # MWh delivered from 36 -> 4
    charged_first = 16 / eta       # MWh bought to go 20 -> 36
    refill = 16 / eta              # MWh bought to go 4 -> 20
    expected_saving = discharged * 150 - charged_first * 30 - refill * 100 - 5.0 * discharged
    assert plan.attrs["saving_eur"] == pytest.approx(expected_saving, abs=0.01)
