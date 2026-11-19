"""Tests for the hourly auction bids (src/decision/bids.py)."""
import numpy as np
import pandas as pd
import pytest

from src.backtest.run_backtest import plan_day
from src.decision.bids import bids_table, block_hour_shares, charge_limit_prices


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


@pytest.mark.parametrize("day,first_block_hours", [("2026-10-14", 4), ("2026-10-25", 5), ("2026-03-29", 3)])
def test_bid_volumes_per_block_sum_to_plan(day, first_block_hours):
    r = plan_day(day, "ml_battery", settle=False)
    plan, bids = r["plan"], r["bids"]
    dem = bids[bids.bid_type == "demand"]
    assert len(dem) == 24 - 4 + first_block_hours
    assert (dem.groupby("block").size().loc[0]) == first_block_hours
    per_block = bids.groupby("block")["volume_mwh"].sum()
    assert np.allclose(per_block.to_numpy(), plan["buy_mwh"].to_numpy(), atol=1e-6)
    chg = bids[bids.bid_type == "charge"].groupby("block")["volume_mwh"].sum()
    for b, v in chg.items():
        assert v == pytest.approx(plan.loc[b, "charge_mwh"])
    assert (bids["volume_mwh"] >= 0).all()
    # never more than the battery power per hour
    assert (bids.loc[bids.bid_type == "charge", "volume_mwh"] <= 20 + 1e-9).all()
    # demand bids are price-independent
    assert dem["limit_price_eur_mwh"].isna().all()


def test_bids_table_one_row_per_hour():
    r = plan_day("2026-10-25", "ml_battery", settle=False)
    t = bids_table(r["bids"])
    assert len(t) == 25
    limits = t["Charge limit EUR/MWh"]
    assert ((limits == "-") == (t["Charge bid MWh"] == 0)).all()  # "-" exactly where there is no charge bid
    assert t["Total bid MWh"].sum() == pytest.approx(r["plan"]["buy_mwh"].sum(), abs=0.05)
    # the doubled 02:00 hour is shown with two different UTC offsets
    assert {"02:00 (UTC+02)", "02:00 (UTC+01)"}.issubset(set(t["Hour (local)"]))
