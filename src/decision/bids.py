"""Turn a battery plan (per planning period) into HOURLY bids for the day-ahead auction.

The optimiser (``src/optimisation/battery_lp.py``) plans per period: either the six
four-hour blocks of tomorrow (``plan_resolution = "block"``) or the 23/24/25 single
hours (``"hourly_shape"`` and the hourly perfect-foresight ceiling). The auction trades
single hours, so this module makes the hourly bids out of the period plan.

Two (optionally three) kinds of bid per hour
--------------------------------------------
* **demand** - the energy the city needs from the market in this hour. It is a
  *price-independent* bid ("buy at any price"), because Zurich must be supplied.
  Per hour: forecast need of the hour minus the planned battery discharge of the hour.
  The forecast need of the hour = period forecast x the hour's share of the period; in
  block mode the shares come from the actual hourly demand of the SAME block one week
  earlier (delivery date - 7 days, already known at forecast time).
* **charge** - extra energy that goes into the battery. It is a *limit* bid: we only buy it
  if the auction price is at or below the limit price
  ``limit = expected discharge price x charge_limit_factor - wear cost`` (or no limit).
* optional **protection** (decision option ``protect = "at_risk_bid"``): planned discharge
  that can only happen if an earlier *limit* charge bid clears is "at risk". Its volume is
  added to the price-independent demand bid; if the charge does clear, the extra energy is
  sold back as surplus in the imbalance settlement.

Planned discharge of a block is spread over the block's hours as evenly as possible but
never above the hour's forecast need or the battery power (``allocate_discharge``), so the
demand bid of an hour is never negative and the block totals are conserved exactly.

All energy values are MWh per hour, prices EUR/MWh.
"""
from __future__ import annotations

from typing import Sequence

import numpy as np
import pandas as pd

from src.config import load_config

DEMAND = "demand"
CHARGE = "charge"
TOL = 1e-9


def block_hour_shares(target_hours_local: Sequence[int], reference: pd.DataFrame | None) -> np.ndarray:
    """Share of the block's energy that falls into each hour of the block.

    Parameters
    ----------
    target_hours_local : local clock hour of every delivery hour of the block, in time
        order. On the autumn DST day block 0 has 5 hours (hour 2 twice), on the spring
        DST day it has 3 hours (no hour 2).
    reference : hourly rows of the same block one week earlier, with columns
        ``hour_local`` and ``demand_mw``. ``None`` or empty -> flat split.

    The reference value of each target hour is the reference demand at the same local
    hour (mean if the hour appears twice). A target hour that is missing in the
    reference (e.g. the extra hour of a 25-hour day) gets the mean of the reference.
    The shares always sum to 1.
    """
    hours = list(target_hours_local)
    n = len(hours)
    if n == 0:
        return np.zeros(0)
    flat = np.full(n, 1.0 / n)
    if reference is None or len(reference) == 0:
        return flat
    ref = reference.dropna(subset=["demand_mw"])
    if len(ref) == 0:
        return flat
    by_hour = ref.groupby("hour_local")["demand_mw"].mean()
    fill = float(by_hour.mean())
    weights = np.array([float(by_hour.get(h, fill)) for h in hours])
    if not np.isfinite(weights).all() or weights.sum() <= 0 or (weights < 0).any():
        return flat
    return weights / weights.sum()


def allocate_discharge(total: float, caps: Sequence[float]) -> np.ndarray:
    """Split a block's planned discharge over its hours: as even as possible, but never
    more than ``caps[h]`` (= min(forecast need of the hour, battery power)).

    The result always sums to ``total`` (block totals are conserved). Raises ValueError
    if ``total`` exceeds the sum of the caps (the optimiser is set up so that this cannot
    happen, see ``plan_day``).
    """
    caps = np.maximum(np.asarray(caps, dtype=float), 0.0)
    n = len(caps)
    out = np.zeros(n)
    if total <= TOL or n == 0:
        return out
    if total > caps.sum() + 1e-6:
        raise ValueError(f"planned discharge {total:.4f} MWh exceeds what the hours can take ({caps.sum():.4f} MWh)")
    remaining, left = float(total), n
    for i in np.argsort(caps, kind="stable"):  # smallest cap first: water filling
        give = min(caps[i], remaining / left)
        out[i] = give
        remaining -= give
        left -= 1
    # put any rounding rest (<= 1e-6) on the hour with the most room
    if abs(remaining) > 0:
        j = int(np.argmax(caps - out))
        out[j] += remaining
    return out


def charge_limit_prices(
    plan: pd.DataFrame,
    charge_limit_factor: float | None = None,
    wear_cost_eur_per_mwh: float = 5.0,
    price_q90: Sequence[float] | None = None,
) -> np.ndarray:
    """Limit price (EUR/MWh) for the charge bid of every period (NaN where no charging).

    Rule: ``limit = expected discharge price x charge_limit_factor - wear cost``.

    * expected discharge price = discharge-weighted forecast price of the planned
      discharge periods AFTER the charge period;
    * if there is no discharge after it (e.g. the battery refills in the evening after
      using the energy in the morning), we use the discharge-weighted price of all
      discharge periods of the day;
    * if the plan has no discharge at all, the charge only refills the battery to its
      end-of-day target (needed after a day when a charge bid did not clear). Then the
      limit is the highest forecast price of the day: we accept to pay up to the most
      expensive expected period, because tomorrow this energy replaces purchases.
    * ``price_q90`` (optional, "quantile" rule): the limit is in addition capped at the
      90 % quantile forecast of the charge period's price.
    """
    if charge_limit_factor is None:
        charge_limit_factor = load_config().get("bidding", {}).get("charge_limit_factor", 0.9)
    price = plan["price_eur_mwh"].to_numpy(dtype=float)
    charge = plan["charge_mwh"].to_numpy(dtype=float)
    dis = plan["discharge_mwh"].to_numpy(dtype=float)
    n = len(plan)
    limits = np.full(n, np.nan)
    for i in range(n):
        if charge[i] <= 1e-9:
            continue
        later = np.arange(n) > i
        if (dis[later] > 1e-9).any():
            w = dis * later
        elif (dis > 1e-9).any():
            w = dis
        else:
            limits[i] = float(price.max())  # refill rule
            continue
        expected = float((w * price).sum() / w.sum())
        limits[i] = expected * charge_limit_factor - wear_cost_eur_per_mwh
        if price_q90 is not None and np.isfinite(price_q90[i]):
            limits[i] = min(limits[i], float(price_q90[i]))
    return limits


def hourly_plan(
    plan: pd.DataFrame,
    hours: pd.DataFrame,
    charge_limits: Sequence[float] | None,
    power_mw: float | None = None,
    cap_by_need: bool = True,
) -> pd.DataFrame:
    """Spread the period plan over the delivery hours.

    Parameters
    ----------
    plan : result of ``solve_battery_plan`` (one row per period, in period order).
    hours : one row per delivery hour, in time order, with columns ``delivery_date,
        timestamp_utc, local_time, hour_local, block, period`` (period = row number in
        ``plan``) and ``share`` (share of the period's forecast demand in this hour,
        from ``block_hour_shares``; the shares of one period sum to 1).
    charge_limits : limit price per period (NaN = price-independent).
    power_mw : battery power (MW = MWh per hour); default config.
    cap_by_need : True (no selling) = an hour's planned discharge is never above the
        hour's forecast need, so the demand bid is never negative.

    Returns one row per hour with ``need_mwh`` (forecast need), ``planned_discharge_mwh``
    (period discharge allocated by ``allocate_discharge``), ``demand_bid_mwh`` (need minus
    planned discharge), ``charge_bid_mwh`` (period charge split evenly; <= power because
    the period charge is <= power x hours), ``charge_limit_eur_mwh``, ``at_risk_bid_mwh``
    (0 here, see ``add_protection``) and ``option``.

    Per period the demand bids add up to ``demand - discharge`` and the charge bids to
    ``charge`` of the plan, i.e. to the plan's ``buy_mwh`` (``- sell_mwh``).
    """
    if power_mw is None:
        power_mw = float(load_config()["battery"]["power_mw"])
    hp = hours.copy().reset_index(drop=True)
    period = hp["period"].to_numpy(dtype=int)
    n_hours = hp.groupby("period")["period"].transform("size").to_numpy(dtype=float)
    demand = plan["demand_mwh"].to_numpy(dtype=float)[period]
    ch = plan["charge_mwh"].to_numpy(dtype=float)[period]
    limits = np.full(len(plan), np.nan) if charge_limits is None else np.asarray(charge_limits, float)

    need = demand * hp["share"].to_numpy(dtype=float)
    dis_h = np.zeros(len(hp))
    for k, d_k in enumerate(plan["discharge_mwh"].to_numpy(dtype=float)):
        m = period == k
        if not m.any():
            continue
        caps = np.minimum(need[m], power_mw) if cap_by_need else np.full(m.sum(), power_mw)
        dis_h[m] = allocate_discharge(d_k, caps)
    hp["need_mwh"] = need
    hp["planned_discharge_mwh"] = dis_h
    bid = need - dis_h
    if cap_by_need:
        assert (bid > -1e-6).all(), "demand bid below zero"
        bid = np.maximum(bid, 0.0)
    hp["demand_bid_mwh"] = bid
    hp["charge_bid_mwh"] = ch / n_hours
    hp["charge_limit_eur_mwh"] = np.where(hp["charge_bid_mwh"] > 1e-9, limits[period], np.nan)
    hp["at_risk_bid_mwh"] = 0.0
    hp["option"] = plan["option"].to_numpy()[period] if "option" in plan else "buy"
    return hp


def at_risk_discharge(hp: pd.DataFrame, soc_start_mwh: float, soc_min_mwh: float,
                      eta_charge: float, eta_discharge: float) -> np.ndarray:
    """Planned discharge per hour that depends on an earlier LIMIT charge bid clearing.

    Walk through the hours in time order with the energy the battery can surely deliver:
    the stock at the start of the day above the minimum level, plus price-independent
    charge bids (they always clear). Planned discharge covered by this sure stock is safe;
    the rest is "at risk". (Conservative: a cleared limit charge is never counted.)
    """
    sure = max(soc_start_mwh - soc_min_mwh, 0.0) * eta_discharge  # deliverable MWh
    ch = hp["charge_bid_mwh"].to_numpy(float)
    lim = hp["charge_limit_eur_mwh"].to_numpy(float)
    dis = hp["planned_discharge_mwh"].to_numpy(float)
    out = np.zeros(len(hp))
    for h in range(len(hp)):
        if ch[h] > TOL and np.isnan(lim[h]):
            sure += ch[h] * eta_charge * eta_discharge
        if dis[h] > TOL:
            covered = min(dis[h], sure)
            sure -= covered
            out[h] = dis[h] - covered
    out[out < 1e-9] = 0.0
    return out


def add_protection(hp: pd.DataFrame, soc_start_mwh: float, soc_min_mwh: float,
                   eta_charge: float, eta_discharge: float) -> pd.DataFrame:
    """Decision option ``protect = "at_risk_bid"``: add the at-risk discharge volume to the
    price-independent demand bid of the hour (column ``at_risk_bid_mwh``)."""
    hp = hp.copy()
    risk = at_risk_discharge(hp, soc_start_mwh, soc_min_mwh, eta_charge, eta_discharge)
    hp["at_risk_bid_mwh"] = risk
    hp["demand_bid_mwh"] = hp["demand_bid_mwh"].to_numpy(float) + risk
    return hp


def bids_from_hourly_plan(hp: pd.DataFrame) -> pd.DataFrame:
    """Tidy bid table: one row per hour and bid type.

    Columns: ``delivery_date, hour_local, local_time, timestamp_utc, block, bid_type``
    (demand | charge), ``volume_mwh, limit_price_eur_mwh`` (NaN = price-independent,
    shown as "market"). A demand row exists for every hour (it includes the at-risk
    protection volume, if any; a negative volume is a price-independent SELL offer and can
    only appear when selling is allowed); a charge row only where the plan charges.
    """
    keys = ["delivery_date", "hour_local", "local_time", "timestamp_utc", "block"]
    dem = hp[keys].copy()
    dem["bid_type"] = DEMAND
    dem["volume_mwh"] = hp["demand_bid_mwh"].to_numpy()
    dem["limit_price_eur_mwh"] = np.nan
    mask = hp["charge_bid_mwh"] > 1e-9
    chg = hp.loc[mask, keys].copy()
    chg["bid_type"] = CHARGE
    chg["volume_mwh"] = hp.loc[mask, "charge_bid_mwh"].to_numpy()
    chg["limit_price_eur_mwh"] = hp.loc[mask, "charge_limit_eur_mwh"].to_numpy()
    out = pd.concat([dem, chg], ignore_index=True)
    out["_order"] = (out["bid_type"] == CHARGE).astype(int)  # demand row first, then charge
    out = out.sort_values(["timestamp_utc", "_order"], kind="stable").drop(columns="_order")
    return out.reset_index(drop=True)


def bids_table(bids: pd.DataFrame) -> pd.DataFrame:
    """Simple table for the app (one row per hour), offered as CSV download.

    Columns: Date, Hour (local), Block, Demand bid MWh (price-independent),
    Charge bid MWh, Charge limit EUR/MWh ("market" = price-independent, "-" = no bid),
    Total bid MWh.
    """
    block_names = [f"{a:02d}-{b:02d}" for a, b in load_config()["blocks"]]
    rows = []
    for ts, g in bids.groupby("timestamp_utc", sort=True):
        first = g.iloc[0]
        lt = pd.Timestamp(first["local_time"])
        dem = g.loc[g["bid_type"] == DEMAND, "volume_mwh"].sum()
        chg_rows = g[g["bid_type"] == CHARGE]
        chg = chg_rows["volume_mwh"].sum()
        if len(chg_rows) == 0:
            limit = "-"
        elif chg_rows["limit_price_eur_mwh"].isna().all():
            limit = "market"
        else:
            limit = f"{chg_rows['limit_price_eur_mwh'].iloc[0]:.2f}"
        rows.append({
            "Date": str(first["delivery_date"]),
            "Hour (local)": f"{lt:%H:%M} (UTC{lt:%z}"[:-2] + ")",  # e.g. "02:00 (UTC+02)"
            "Block": block_names[int(first["block"])] if int(first["block"]) < len(block_names) else str(first["block"]),
            "Demand bid MWh (price-independent)": round(float(dem), 3),
            "Charge bid MWh": round(float(chg), 3),
            "Charge limit EUR/MWh": limit,
            "Total bid MWh": round(float(dem + chg), 3),
        })
    return pd.DataFrame(rows)
