"""Battery plan for one delivery day (the "optimal blend" box in the team's diagram).

Given a demand forecast and a price forecast for each period of tomorrow (normally the
6 four-hour blocks, but any number of periods works, e.g. 24 hours), the optimiser decides
for every period how much energy to

* buy at the auction,
* put into the battery (charge),
* take out of the battery (discharge),

so that the total expected cost is as low as possible and demand is always covered.

It is a small mixed-integer linear program solved with SciPy (HiGHS solver). One yes/no
variable per period forbids charging and discharging in the same period. Without it the
solver could "burn" energy through the battery losses when prices are negative.

All energy values are in MWh per period, prices in EUR/MWh.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Sequence

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp

from src.config import load_config

TOL = 1e-6  # numbers smaller than this count as zero


@dataclass(frozen=True)
class BatteryParams:
    """Technical data of the battery. Defaults come from config.yaml."""

    power_mw: float = 20.0
    capacity_mwh: float = 40.0
    soc_min_frac: float = 0.10
    soc_max_frac: float = 0.90
    soc_start_frac: float = 0.50
    round_trip_efficiency: float = 0.90
    max_cycles_per_day: float = 1.0
    wear_cost_eur_per_mwh: float = 5.0

    @classmethod
    def from_config(cls, **overrides) -> "BatteryParams":
        cfg = load_config()["battery"]
        keys = cls.__dataclass_fields__.keys()
        base = cls(**{k: cfg[k] for k in keys if k in cfg})
        return replace(base, **overrides)

    @property
    def eta_charge(self) -> float:
        return float(np.sqrt(self.round_trip_efficiency))

    @property
    def eta_discharge(self) -> float:
        return float(np.sqrt(self.round_trip_efficiency))

    @property
    def soc_min(self) -> float:
        return self.soc_min_frac * self.capacity_mwh

    @property
    def soc_max(self) -> float:
        return self.soc_max_frac * self.capacity_mwh

    @property
    def soc_start(self) -> float:
        return self.soc_start_frac * self.capacity_mwh

    @property
    def usable_mwh(self) -> float:
        return self.soc_max - self.soc_min


def label_option(buy: float, charge: float, discharge: float, tol: float = 1e-3) -> str:
    """Name the decision of one block with the options from the team's diagram.

    * ``buy``                 only buy what the city needs
    * ``buy_and_store``       buy demand plus extra energy that goes into the battery
    * ``use_storage_and_buy`` cover part of demand from the battery, buy the rest
    * ``use_storage``         cover (almost) all demand from the battery, buy nothing

    "Store without buying" cannot happen: the battery can only be filled with bought
    energy, and the city always needs energy too.
    """
    if charge > tol:
        return "buy_and_store"
    if discharge > tol:
        return "use_storage" if buy <= tol else "use_storage_and_buy"
    return "buy"


def solve_battery_plan(
    demand_mwh: Sequence[float],
    price_eur_mwh: Sequence[float],
    hours: Sequence[float] | None = None,
    battery: BatteryParams | None = None,
    allow_sell: bool = False,
    soc_start_mwh: float | None = None,
    soc_end_mwh: float | None = None,
) -> pd.DataFrame:
    """Find the cheapest buy / charge / discharge plan for one day.

    Parameters
    ----------
    demand_mwh : demand per period in MWh (mean MW x hours of the period).
    price_eur_mwh : expected auction price per period.
    hours : length of every period in hours (default 4). On daylight-saving days one
        block has 3 or 5 hours.
    battery : battery data (default: config.yaml).
    allow_sell : if True the DSO may also sell energy back to the market.
    soc_start_mwh : charge level at the start of the day (default 50 %).
    soc_end_mwh : required charge level at the end of the day (default = start level, so
        every day stands on its own).

    Cycle definition (from the project brief): the energy DELIVERED to the grid by
    discharging over one day is capped at ``max_cycles_per_day x (soc_max - soc_min)``,
    i.e. one cycle = 32 MWh delivered per day for the default 40 MWh battery. Because of
    the discharge losses, emptying the full usable stored energy (32 MWh) delivers only
    32 x eta_discharge = 30.36 MWh, so this cap allows about 5 % more than one physical
    full cycle. We keep the brief's definition; a physical cap would lower the October
    battery saving by about CHF 1,000 (see docs/assumptions_backtest.md).

    Returns
    -------
    DataFrame with one row per period and the columns ``hours, demand_mwh, price_eur_mwh,
    buy_mwh, charge_mwh, discharge_mwh, sell_mwh, soc_mwh, option``. Extra information is
    in ``plan.attrs``: ``status, cost_eur, cost_no_battery_eur, saving_eur, cycles``.
    """
    battery = battery or BatteryParams.from_config()
    d = np.asarray(demand_mwh, dtype=float)
    p = np.asarray(price_eur_mwh, dtype=float)
    n = len(d)
    h = np.full(n, 4.0) if hours is None else np.asarray(hours, dtype=float)
    if not (len(p) == n == len(h)):
        raise ValueError("demand, price and hours must have the same length")
    if np.isnan(d).any() or np.isnan(p).any():
        raise ValueError("demand and price must not contain missing values")
    if (d < 0).any():
        raise ValueError("demand must not be negative")

    soc0 = battery.soc_start if soc_start_mwh is None else float(soc_start_mwh)
    soc_end = soc0 if soc_end_mwh is None else float(soc_end_mwh)
    if not (battery.soc_min - 1e-6 <= soc0 <= battery.soc_max + 1e-6):
        raise ValueError(
            f"start charge level {soc0:.2f} MWh is outside the allowed range "
            f"{battery.soc_min:.2f}-{battery.soc_max:.2f} MWh"
        )
    soc0 = min(max(soc0, battery.soc_min), battery.soc_max)
    eta_c, eta_d = battery.eta_charge, battery.eta_discharge
    max_e = battery.power_mw * h  # most energy the battery can move in each period

    # Variables, stacked in one vector x:
    #   buy[n], sell[n], charge[n], discharge[n], soc[n], is_charging[n] (0 or 1)
    BUY, SELL, CH, DIS, SOC, BIN = (slice(i * n, (i + 1) * n) for i in range(6))
    nvar = 6 * n
    eye = np.eye(n)

    # Objective: money paid at the auction (minus sales) plus battery wear.
    # A tiny extra cost on charging breaks ties, so the battery stays idle when it cannot earn.
    c = np.zeros(nvar)
    c[BUY] = p
    c[SELL] = -p
    c[DIS] = battery.wear_cost_eur_per_mwh
    c[CH] = 1e-4

    lower = np.zeros(nvar)
    upper = np.full(nvar, np.inf)
    upper[SELL] = np.inf if allow_sell else 0.0
    lower[SOC], upper[SOC] = battery.soc_min, battery.soc_max
    upper[BIN] = 1.0
    integrality = np.zeros(nvar)
    integrality[BIN] = 1

    rows, lo, hi = [], [], []

    def add(block: np.ndarray, lb, ub) -> None:
        rows.append(block)
        lo.append(np.broadcast_to(lb, (block.shape[0],)).astype(float))
        hi.append(np.broadcast_to(ub, (block.shape[0],)).astype(float))

    # charge level: soc[b] - soc[b-1] - eta_c*charge[b] + discharge[b]/eta_d = 0
    # (what goes in loses a little, what comes out loses a little)
    A = np.zeros((n, nvar))
    A[:, SOC] = eye - np.eye(n, k=-1)
    A[:, CH] = -eta_c * eye
    A[:, DIS] = eye / eta_d
    rhs = np.zeros(n)
    rhs[0] = soc0
    add(A, rhs, rhs)

    # energy balance: buy - sell - charge + discharge = demand
    A = np.zeros((n, nvar))
    A[:, BUY], A[:, SELL], A[:, CH], A[:, DIS] = eye, -eye, -eye, eye
    add(A, d, d)

    # power limit, and never charge and discharge in the same period
    A = np.zeros((n, nvar))
    A[:, CH] = eye
    A[:, BIN] = -np.diag(max_e)
    add(A, -np.inf, 0.0)  # charge <= max * is_charging
    A = np.zeros((n, nvar))
    A[:, DIS] = eye
    A[:, BIN] = np.diag(max_e)
    add(A, -np.inf, max_e)  # discharge <= max * (1 - is_charging)

    # charge level at the end of the day
    A = np.zeros((1, nvar))
    A[0, SOC.start + n - 1] = 1.0
    add(A, soc_end, soc_end)

    # at most N cycles per day; one cycle = (soc_max - soc_min) MWh DELIVERED to the grid (the
    # brief's definition, about 5 % more than one physical full cycle of stored energy)
    A = np.zeros((1, nvar))
    A[0, DIS] = 1.0
    add(A, -np.inf, battery.max_cycles_per_day * battery.usable_mwh)

    res = milp(
        c,
        constraints=LinearConstraint(np.vstack(rows), np.concatenate(lo), np.concatenate(hi)),
        bounds=Bounds(lower, upper),
        integrality=integrality,
        # solve to (practically) exact optimality: the battery saving is tiny next to the
        # city's whole purchase bill, so the default 0.01 % gap would be too loose
        options={"mip_rel_gap": 0.0},
    )
    if not res.success:
        raise RuntimeError(f"battery plan could not be solved: {res.message}")
    status = "Optimal"
    x = np.where(np.abs(res.x) < TOL, 0.0, res.x)
    buy, sell, charge, discharge, soc = x[BUY], x[SELL], x[CH], x[DIS], x[SOC]

    def val(v: np.ndarray) -> np.ndarray:
        return v

    plan = pd.DataFrame(
        {
            "hours": h,
            "demand_mwh": d,
            "price_eur_mwh": p,
            "buy_mwh": val(buy),
            "charge_mwh": val(charge),
            "discharge_mwh": val(discharge),
            "sell_mwh": val(sell),
            "soc_mwh": val(soc),
        }
    )
    plan["option"] = [
        label_option(r.buy_mwh, r.charge_mwh, r.discharge_mwh) for r in plan.itertuples()
    ]
    cost = float((p * (plan["buy_mwh"] - plan["sell_mwh"])).sum()
                 + battery.wear_cost_eur_per_mwh * plan["discharge_mwh"].sum())
    cost_no_battery = float((p * d).sum())
    plan.attrs.update(
        status=status,
        cost_eur=cost,
        cost_no_battery_eur=cost_no_battery,
        saving_eur=cost_no_battery - cost,
        cycles=float(plan["discharge_mwh"].sum() / battery.usable_mwh) if battery.usable_mwh > 0 else 0.0,
        soc_start_mwh=soc0,
    )
    return plan


def describe_plan(plan: pd.DataFrame, block_names: Sequence[str] | None = None) -> str:
    """One plain sentence that sums up the plan (used in the app)."""
    names = list(block_names) if block_names is not None else [f"block {i + 1}" for i in range(len(plan))]
    ch = plan["charge_mwh"].to_numpy()
    dis = plan["discharge_mwh"].to_numpy()
    if ch.sum() < 1e-3 and dis.sum() < 1e-3:
        return "Battery stays idle: the price gap between blocks does not cover losses and wear."
    ch_txt = ", ".join(names[i] for i in np.where(ch > 1e-3)[0])
    dis_txt = ", ".join(names[i] for i in np.where(dis > 1e-3)[0])
    return (
        f"Charge {ch.sum():.0f} MWh in {ch_txt}; use {dis.sum():.0f} MWh in {dis_txt}. "
        f"Expected saving: EUR {plan.attrs.get('saving_eur', 0):,.0f}."
    )
