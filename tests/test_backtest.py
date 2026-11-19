"""Tests for the backtest settlement, the ceiling, tuning cutoff and statistics
(src/backtest/run_backtest.py, src/backtest/analysis.py)."""
import datetime as dt
import time

import numpy as np
import pandas as pd
import pytest

import src.backtest.run_backtest as rb
from src.backtest.run_backtest import (
    CEILING, HOURLY_DAILY_ORACLE, STRATEGIES, DecisionParams, ImbalanceParams, block_bootstrap_index, bootstrap_sums,
    carry_soc, decomposition, lag1_autocorr, paired_bootstrap_ci, plan_day, run_backtest, settle_hours, summarise,
)
from src.optimisation.battery_lp import BatteryParams

BAT = BatteryParams(power_mw=20, capacity_mwh=40, soc_min_frac=0.1, soc_max_frac=0.9, soc_start_frac=0.5,
                    round_trip_efficiency=0.9, max_cycles_per_day=1, wear_cost_eur_per_mwh=5.0)
IMB = ImbalanceParams(shortage_factor=1.2, surplus_factor=0.8)
HOURLY = DecisionParams(plan_resolution="hourly_shape", shape_daytype=True)


@pytest.fixture(autouse=True)
def _serial(monkeypatch):
    monkeypatch.setenv("BACKTEST_WORKERS", "1")  # no process pool inside the tests


def _hp(demand_bid, charge_bid, limit, dis):
    return pd.DataFrame({"demand_bid_mwh": demand_bid, "charge_bid_mwh": charge_bid,
                         "charge_limit_eur_mwh": limit, "planned_discharge_mwh": dis})


# --- settlement -------------------------------------------------------------------
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


# --- missing / non-finite data -------------------------------------------------------
@pytest.mark.parametrize("which", ["price", "fx", "demand"])
def test_settlement_rejects_missing_actuals(which):
    hp = _hp([100.0, 90.0], [0.0, 0.0], [np.nan, np.nan], [0.0, 0.0])
    hp["delivery_date"] = "2026-10-14"
    hp["local_time"] = pd.date_range("2026-10-14 00:00", periods=2, freq="h", tz="Europe/Zurich")
    d, p, fx = [100.0, 90.0], [40.0, 50.0], [0.93, 0.93]
    if which == "price":
        p = [40.0, np.nan]
    elif which == "fx":
        fx = [0.93, np.inf]
    else:
        d = [np.nan, 90.0]
    with pytest.raises(ValueError, match="2026-10-14 0[01]:00"):
        settle_hours(hp, d, p, fx, BAT, 20.0, IMB)


def _patched_hours(monkeypatch, day, fn):
    data = dict(rb.load_data())
    hours = dict(data["hours"])
    hours[day] = fn(hours[day].copy())
    data["hours"] = hours
    monkeypatch.setattr(rb, "load_data", lambda: data)


@pytest.mark.parametrize("col", ["price_eur_mwh", "eurchf", "demand_mw"])
def test_plan_day_rejects_missing_price_fx_demand(monkeypatch, col):
    day = dt.date(2026, 10, 14)

    def spoil(h):
        h.loc[17, col] = np.nan
        return h
    _patched_hours(monkeypatch, day, spoil)
    with pytest.raises(ValueError, match="2026-10-14 17:00"):
        plan_day(day, "baseline_naive_no_battery")
    with pytest.raises(ValueError, match="2026-10-14 17:00"):
        plan_day(day, "ml_battery")


def test_plan_day_rejects_wrong_hour_count(monkeypatch):
    day = dt.date(2026, 10, 25)  # 25-hour day
    _patched_hours(monkeypatch, day, lambda h: h.drop(index=3).reset_index(drop=True))
    with pytest.raises(ValueError, match="expected 25"):
        plan_day(day, "ml_battery")
    assert rb.expected_hours("2026-03-29") == 23 and rb.expected_hours("2026-10-14") == 24


# --- strategies ---------------------------------------------------------------------
@pytest.mark.parametrize("strategy", ["perfect_foresight_battery", "perfect_foresight_hourly_battery",
                                      HOURLY_DAILY_ORACLE, "perfect_demand_no_battery"])
def test_perfect_foresight_has_zero_imbalance(strategy):
    for day in ["2026-10-02", "2026-10-25", "2026-03-29"]:
        s = plan_day(day, strategy)["summary"]
        assert s["shortage_mwh"] == pytest.approx(0, abs=1e-6)
        assert s["surplus_mwh"] == pytest.approx(0, abs=1e-6)
        # charge limit is not binding under perfect foresight: every charge bid clears
        assert np.isnan(s["share_charge_cleared"]) or s["share_charge_cleared"] == pytest.approx(1.0)


def test_oracles_ignore_tuned_margin_and_limits():
    tuned = DecisionParams(min_spread_eur_mwh=50.0, charge_limit_factor=0.5)
    for s in ["perfect_foresight_battery", "perfect_foresight_hourly_battery", HOURLY_DAILY_ORACLE]:
        a = plan_day("2026-10-14", s, decision=tuned)
        b = plan_day("2026-10-14", s, decision=DecisionParams())
        assert a["summary"]["total_cost_chf"] == pytest.approx(b["summary"]["total_cost_chf"])
        assert a["plan"]["charge_limit_eur_mwh"].isna().all()


@pytest.mark.parametrize("strategy", [k for k, v in STRATEGIES.items() if not v["battery"]])
def test_no_battery_strategies_never_touch_battery(strategy):
    daily, _ = run_backtest("2026-10-01", "2026-10-05", strategies=[strategy], n_boot=0)
    assert (daily[["charge_bid_mwh", "charged_mwh", "discharged_mwh", "cycles"]] == 0).all().all()
    assert (daily["soc_end_mwh"] == daily["soc_start_mwh"]).all()


@pytest.mark.parametrize("decision", [DecisionParams(), HOURLY], ids=["block", "hourly_shape"])
def test_costs_add_up_and_charge_level_is_carried_over(decision):
    daily, summary = run_backtest("2026-10-01", "2026-10-07", strategies=["ml_battery", "baseline_naive_no_battery"],
                                  decision=decision, n_boot=0)
    total = daily["da_cost_eur"] + daily["imbalance_cost_eur"] + daily["wear_cost_eur"]
    assert np.allclose(total, daily["total_cost_eur"])
    ml = daily[daily.strategy == "ml_battery"].reset_index(drop=True)
    assert np.allclose(ml["soc_start_mwh"].iloc[1:].to_numpy(), ml["soc_end_mwh"].iloc[:-1].to_numpy())
    assert ml["soc_start_mwh"].iloc[0] == pytest.approx(BatteryParams.from_config().soc_start)
    bat = BatteryParams.from_config()
    assert ((ml["soc_end_mwh"] >= bat.soc_min) & (ml["soc_end_mwh"] <= bat.soc_max)).all()


def test_carried_soc_clips_drift_and_rejects_real_errors():
    bat = BatteryParams.from_config()
    assert carry_soc(bat.soc_max + 1e-9, bat) == bat.soc_max
    assert carry_soc(bat.soc_min - 1e-9, bat) == bat.soc_min
    with pytest.raises(AssertionError):
        carry_soc(bat.soc_max + 0.5, bat)
    with pytest.raises(AssertionError):
        carry_soc(np.nan, bat)


def test_end_target_fallback_only_on_infeasibility(monkeypatch):
    calls = []

    def fake(*a, soc_end_mwh=None, **k):
        calls.append(soc_end_mwh)
        if len(calls) == 1:
            raise RuntimeError(msg)
        return pd.DataFrame()
    monkeypatch.setattr(rb, "solve_battery_plan", fake)
    msg = "battery plan could not be solved: The problem is infeasible."
    _, relaxed = rb._solve([1.0], [1.0], [1.0], BAT, 30.0)
    assert relaxed and calls == [BAT.soc_start, 30.0]
    calls.clear()
    msg = "battery plan could not be solved: time limit reached"
    with pytest.raises(RuntimeError, match="time limit"):
        rb._solve([1.0], [1.0], [1.0], BAT, 30.0)


def test_ceiling_dominates_every_strategy_with_matched_inventory():
    """Over a period, the hourly ceiling's inventory-adjusted cost is <= every other strategy's,
    and it ends the period with exactly the charge level it started with."""
    daily, summary = run_backtest("2026-10-01", "2026-10-10", n_boot=0)
    t = summary.set_index("strategy")["total_cost_adj_chf"]
    for s, v in t.items():
        assert t[CEILING] <= v + 0.01, s
    c = daily[daily.strategy == CEILING].sort_values("delivery_date")
    assert c["soc_end_mwh"].iloc[-1] == pytest.approx(c["soc_start_mwh"].iloc[0], abs=1e-5)
    assert summary.set_index("strategy").loc[CEILING, "inventory_value_chf"] == pytest.approx(0, abs=0.05)
    # the ceiling is also at least as good as the block oracle without the adjustment
    assert t[CEILING] <= t["perfect_foresight_battery"] + 0.01


def test_hourly_daily_reset_oracle_sits_between_block_oracle_and_ceiling():
    """5b (hourly perfect foresight, back to the start level every evening) costs no more than
    the block oracle (5) and no less than the period ceiling (6); the two new decomposition
    parts add up to the old block_rule_cost."""
    strategies = ["baseline_naive_no_battery", "ml_no_battery", "ml_battery", "perfect_foresight_battery",
                  HOURLY_DAILY_ORACLE, CEILING, "perfect_demand_no_battery"]
    daily, summary = run_backtest("2026-10-01", "2026-10-07", strategies=strategies, n_boot=0)
    t = summary.set_index("strategy")["total_cost_adj_chf"]
    assert t[CEILING] <= t[HOURLY_DAILY_ORACLE] + 0.01
    assert t[HOURLY_DAILY_ORACLE] <= t["perfect_foresight_battery"] + 0.01
    d5b = daily[daily.strategy == HOURLY_DAILY_ORACLE]
    bat = BatteryParams.from_config()
    assert np.allclose(d5b["soc_end_mwh"], bat.soc_start, atol=1e-5)    # daily reset
    assert (d5b["discharged_mwh"] <= bat.max_cycles_per_day * bat.usable_mwh + 1e-6).all()
    dec = decomposition(summary).iloc[0]
    assert dec["finer_dispatch_part_chf"] >= -0.01 and dec["interday_flexibility_part_chf"] >= -0.01
    assert dec["finer_dispatch_part_chf"] + dec["interday_flexibility_part_chf"] == pytest.approx(
        dec["block_rule_cost_chf"])


def test_single_day_planning_is_fast():
    plan_day("2026-10-10", "ml_battery")  # warm-up (loads the data once)
    t = time.time()
    plan_day("2026-10-11", "ml_battery", decision=HOURLY)
    plan_day("2026-10-11", "ml_battery", decision=DecisionParams())
    plan_day("2026-10-11", "perfect_foresight_hourly_battery")
    assert (time.time() - t) / 3 < 0.5


# --- hourly price shape -------------------------------------------------------------
def test_price_shape_uses_only_earlier_days():
    day = dt.date(2026, 10, 14)
    shape = dict(rb.price_shape(day, 7, False))
    h = pd.concat([rb.load_data()["hours"][day - dt.timedelta(days=k)] for k in range(1, 8)])
    h["dev"] = h["price_eur_mwh"] - h.groupby(["delivery_date", "block"])["price_eur_mwh"].transform("mean")
    expect = h.groupby(["delivery_date", "hour_local"])["dev"].mean().groupby(level=1).mean()
    for hr, v in expect.items():
        assert shape[hr] == pytest.approx(v)
    # every block keeps its forecast mean after shaping
    hrs = rb.day_hours(day)
    hp = rb.hourly_price_forecast(np.arange(6) * 10.0, hrs, tuple(shape.items()))
    assert pd.Series(hp).groupby(hrs["block"].to_numpy()).mean().to_numpy() == pytest.approx(np.arange(6) * 10.0)


# --- tuning cutoff --------------------------------------------------------------------
def test_tuning_cutoff_and_periods():
    from src.backtest.analysis import check_tuning_dates, tune_decision
    assert rb.tuning_cutoff() == dt.date(2026, 9, 29)
    per = rb.tuning_periods()
    alld = per["rolling"] + per["september"]
    assert max(alld) == dt.date(2026, 9, 29) and min(alld) == dt.date(2025, 10, 1)
    assert not any(d >= dt.date(2026, 10, 1) for d in alld)
    check_tuning_dates(alld)                                  # fine
    for bad in [dt.date(2026, 9, 30), dt.date(2026, 10, 1), dt.date(2026, 10, 15)]:
        with pytest.raises(ValueError, match="2026-09-29"):
            check_tuning_dates([dt.date(2026, 9, 1), bad])
    with pytest.raises(ValueError):
        tune_decision([dt.date(2026, 8, 1)], [dt.date(2026, 10, 2)])


def test_tuned_decision_reads_the_chosen_row(monkeypatch, tmp_path):
    f = tmp_path / "tuning.csv"
    pd.DataFrame([
        {"chosen": False, "plan_resolution": "block", "shape_days": 7, "shape_daytype": False, "charge_limit_factor": 0.9,
         "use_limit": True, "limit_rule": "factor", "min_spread_eur_mwh": 0.0, "protect": "none"},
        {"chosen": True, "plan_resolution": "hourly_shape", "shape_days": 14, "shape_daytype": True,
         "charge_limit_factor": 1.0, "use_limit": False, "limit_rule": "factor", "min_spread_eur_mwh": 5.0,
         "protect": "at_risk_bid"},
    ]).to_csv(f, index=False)
    monkeypatch.setattr(rb, "TUNING_FILE", f)
    rb._TUNED_CACHE.clear()
    try:
        d = rb.tuned_decision()
        assert d == DecisionParams(plan_resolution="hourly_shape", shape_days=14, shape_daytype=True,
                                   charge_limit_factor=1.0, use_limit=False, min_spread_eur_mwh=5.0,
                                   protect="at_risk_bid")
    finally:
        rb._TUNED_CACHE.clear()


def test_small_tuning_run_records_all_periods():
    from src.backtest.analysis import tune_decision
    roll = rb.dates_between("2026-08-25", "2026-08-31")
    sept = rb.dates_between("2026-09-20", "2026-09-29")
    tab, chosen, kept = tune_decision(roll, sept, n_boot=100)
    for c in ["saving_rolling_chf", "saving_sept_chf", "saving_combined_chf"]:
        assert tab[c].notna().all()
    assert np.allclose(tab["saving_combined_chf"], tab["saving_rolling_chf"] + tab["saving_sept_chf"])
    assert tab["chosen"].sum() == 1
    assert (tab["cutoff"] == "2026-09-29").all()
    assert isinstance(chosen, DecisionParams)


# --- statistics -------------------------------------------------------------------------
def test_paired_bootstrap_hand_example():
    a, b = [10.0, 20.0], [9.0, 17.0]                 # daily savings 1 and 3
    idx = [[0, 0], [0, 1], [1, 0], [1, 1]]           # all 4 resamples of 2 days
    assert bootstrap_sums(np.subtract(a, b), idx) == pytest.approx([2, 4, 4, 6])
    lo, hi = paired_bootstrap_ci(a, b, idx=idx)
    # np.percentile (linear) of [2, 4, 4, 6]: 2.5 % -> 2 + 0.075 * 2, 97.5 % -> 4 + 0.925 * 2
    assert (lo, hi) == pytest.approx((2.15, 5.85))
    assert paired_bootstrap_ci(a, b, idx=idx, shift=1.0) == pytest.approx((3.15, 6.85))
    # many random draws converge to the exact interval of the sum (2 .. 6)
    lo, hi = paired_bootstrap_ci(a, b, n_boot=20000, seed=1)
    assert lo == pytest.approx(2.0) and hi == pytest.approx(6.0)


def test_block_bootstrap_hand_example():
    # 3 days, blocks of 2 days, circular: a draw with block starts [2, 0] takes days 2, 0 | 0, 1 -> cut to 3 days
    idx = block_bootstrap_index(3, block_len=2, n_boot=50, seed=1)
    assert idx.shape == (50, 3) and idx.min() >= 0 and idx.max() <= 2
    # within a block the days are consecutive (mod 3)
    assert ((idx[:, 1] - idx[:, 0]) % 3 == 1).all()
    np.testing.assert_array_equal(idx, block_bootstrap_index(3, block_len=2, n_boot=50, seed=1))   # reproducible
    assert not np.array_equal(idx, block_bootstrap_index(3, block_len=2, n_boot=50, seed=2))
    # every possible draw of [1, 2, 3] with 2-day blocks: start s gives (s, s+1, next start)
    x = np.array([1.0, 2.0, 3.0])
    sums = bootstrap_sums(x, idx)
    # possible sums: first block (1,2)=3,(2,3)=5,(3,1)=4 plus a first day of 1, 2 or 3 -> 4 .. 8
    assert set(np.round(sums, 9)) <= {4.0, 5.0, 6.0, 7.0, 8.0}
    # block length 1 = the ordinary day bootstrap; block length n = a rotation (sum always the total)
    assert np.allclose(bootstrap_sums(x, block_bootstrap_index(3, 3, 20, 0)), 6.0)
    assert lag1_autocorr([1.0, 2.0, 3.0, 4.0]) == pytest.approx(1.0)
    assert lag1_autocorr([1.0, -1.0, 1.0, -1.0]) == pytest.approx(-1.0)


def test_ci_sensitivity_is_reproducible_and_keeps_the_point_estimate():
    from src.backtest.analysis import ci_sensitivity
    daily, summary = run_backtest("2026-10-01", "2026-10-14", strategies=["baseline_naive_no_battery", "ml_battery"],
                                  n_boot=200)
    a = ci_sensitivity(daily, summary, n_boot=300, seed=5)
    b = ci_sensitivity(daily, summary, n_boot=300, seed=5)
    pd.testing.assert_frame_equal(a, b)
    r = a.iloc[0]
    assert r["days"] == 14 and r["block_length_days"] == 7
    assert r["ci_block_low_chf"] <= r["saving_vs_baseline_adj_chf"] <= r["ci_block_high_chf"]
    assert r["ci_independent_days_low_chf"] == pytest.approx(summary.set_index("strategy").loc["ml_battery",
                                                                                                "saving_adj_ci_low_chf"])


def test_summary_bootstrap_is_reproducible():
    daily, _ = run_backtest("2026-10-01", "2026-10-10", strategies=["baseline_naive_no_battery", "ml_battery"],
                            n_boot=0)
    a = summarise(daily, n_boot=200, seed=7)
    b = summarise(daily, n_boot=200, seed=7)
    pd.testing.assert_frame_equal(a, b)
    r = a.set_index("strategy").loc["ml_battery"]
    assert r["saving_vs_baseline_adj_chf"] == pytest.approx(r["saving_vs_baseline_chf"] + r["inventory_value_chf"])


def test_price_noise_sensitivity_zero_noise_reference():
    from src.backtest.analysis import price_error_sensitivity
    dates = rb.dates_between("2026-10-01", "2026-10-03")
    dec = DecisionParams()
    a = price_error_sensitivity(dates, dec, sigmas=(0, 20), seeds=2, seed=3)
    b = price_error_sensitivity(dates, dec, sigmas=(0, 20), seeds=2, seed=3)
    pd.testing.assert_frame_equal(a, b)
    zero = a[(a["forecast"] == "noise") & (a["sigma"] == 0)].iloc[0]
    assert zero["lost_saving_chf"] == 0.0                                  # reference = same policy, no noise
    assert zero["price_mae_eur_mwh"] == 0.0
    assert a.attrs["reference_cost_chf"] == pytest.approx(zero["total_cost_adj_chf"])
    assert a.attrs["policy_gap_to_ceiling_chf"] >= -0.01                   # the ceiling is never beaten
    # the zero-noise run equals planning with the true block prices under the same rules
    spec = dict(demand="actual", price="actual", battery=True, policy="given")
    d, _ = rb.run_strategy(dates, spec, decision=dec)
    from src.backtest.analysis import adj_cost
    assert adj_cost(d) == pytest.approx(zero["total_cost_adj_chf"])


# --- prediction files ---------------------------------------------------------------------
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
        if target == "price":
            p["pred_q10"], p["pred_q90"] = val - 10, val + 10
        p.to_parquet(tmp_path / f"pred_{target}.parquet")
    monkeypatch.setattr(rb, "PRED_FILES", {"demand": tmp_path / "pred_demand.parquet",
                                           "price": tmp_path / "pred_price.parquet"})
    rb.load_forecasts.cache_clear()
    rb._forecast_index.cache_clear()
    try:
        fc = rb.load_forecasts(require_ml=True)
        oct_ = fc[fc.split == "test"]
        assert len(oct_) == 186 and (oct_.demand_ml_mw == 250).all() and (oct_.price_ml_eur_mwh == 77).all()
        assert (oct_.demand_source == "ml").all() and (oct_.price_q90_eur_mwh == 87).all()
        r = plan_day("2026-10-14", "ml_battery", decision=DecisionParams(), require_ml=True)
        assert r["plan"]["price_eur_mwh"].eq(77).all()
        assert r["summary"]["forecast_demand_mwh"] == pytest.approx(250 * 24)
        q = plan_day("2026-10-14", "ml_battery", decision=DecisionParams(limit_rule="quantile"), require_ml=True)
        assert (q["plan_periods"]["charge_limit_eur_mwh"].dropna() <= 87 + 1e-9).all()
        # outside the file the ML forecast is missing -> loud error, no silent fallback
        with pytest.raises(ValueError, match="block 0"):
            plan_day("2026-09-14", "ml_battery", require_ml=True)
    finally:
        rb.load_forecasts.cache_clear()
        rb._forecast_index.cache_clear()


def test_require_ml_rejects_a_day_without_predictions(monkeypatch, tmp_path):
    """A delivery date with fewer than six finite predictions stops the run (no silent shortening)."""
    dates = pd.date_range("2026-10-01", "2026-10-05").date
    rows = pd.DataFrame([(d, b) for d in dates for b in range(6)], columns=["delivery_date", "block"])
    for target in ["demand", "price"]:
        p = rows.copy()
        p["split"], p["y_true"], p["pred_naive"], p["pred_best"] = "test", 0.0, 1.0, 100.0
        if target == "price":
            p = p[~((p.delivery_date == dt.date(2026, 10, 3)) & (p.block == 4))]   # one block missing
        p.to_parquet(tmp_path / f"pred_{target}.parquet")
    monkeypatch.setattr(rb, "PRED_FILES", {"demand": tmp_path / "pred_demand.parquet",
                                           "price": tmp_path / "pred_price.parquet"})
    rb.load_forecasts.cache_clear()
    rb._forecast_index.cache_clear()
    try:
        rb.check_ml_coverage([dt.date(2026, 10, 1), dt.date(2026, 10, 2)])          # complete days pass
        with pytest.raises(ValueError, match=r"2026-10-03 has 5 finite price predictions"):
            rb.check_ml_coverage(dates)
        with pytest.raises(ValueError, match="2026-10-03"):
            rb._ml_dates(list(dates), require_ml=True)
        with pytest.raises(ValueError, match="2026-10-06 has 0 finite demand"):
            rb.check_ml_coverage([dt.date(2026, 10, 6)])
    finally:
        rb.load_forecasts.cache_clear()
        rb._forecast_index.cache_clear()
