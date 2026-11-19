"""The web-app JSON export matches the contract in web/src/data/types.ts and the stored backtest.

The pydantic models below mirror types.ts field for field (extra keys are an error, required keys must
be present, nullable fields are ``X | None``).
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Literal

import pandas as pd
import pytest
from pydantic import BaseModel, ConfigDict, StrictBool

from src.config import ROOT
from src.export import export_web as ex

Num = float
Split = Literal["val", "test"]
Option = Literal["buy", "buy_and_store", "use_storage_and_buy", "use_storage"]


class M(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=False)


class BatterySettings(M):
    power_mw: Num
    capacity_mwh: Num
    soc_min_frac: Num
    soc_max_frac: Num
    soc_start_frac: Num
    round_trip_efficiency: Num
    max_cycles_per_day: Num
    wear_cost_eur_per_mwh: Num
    allow_sell: StrictBool


class Imb(M):
    shortage_price_factor: Num
    surplus_price_factor: Num


class Dec(M):
    description: str
    plan_resolution: str
    charge_limit_factor: Num


class MetaDay(M):
    date: str
    split: Split
    weekday: str
    is_holiday: StrictBool
    is_weekend: StrictBool
    hours: int


class Meta(M):
    generated_at: str
    company: str
    forecast_time_local: str
    gate_closure_local: str
    battery: BatterySettings
    imbalance: Imb
    decision: Dec
    demand_source: str
    price_source: str
    days: list[MetaDay]
    block_labels: list[str]


class BlockRow(M):
    block: int
    label: str
    hours: int
    demand_fc_mw: Num
    demand_q10_mw: Num | None
    demand_q90_mw: Num | None
    demand_actual_mw: Num
    demand_naive_mw: Num
    price_fc: Num
    price_q10: Num | None
    price_q90: Num | None
    price_actual: Num
    price_naive: Num
    buy_mwh: Num
    charge_mwh: Num
    discharge_mwh: Num
    sell_mwh: Num
    soc_end_mwh: Num
    option: Option
    charge_limit_eur_mwh: Num | None


class HourRow(M):
    utc: str
    hour: str
    block: int
    demand_fc_mw: Num
    demand_actual_mw: Num
    price_fc: Num | None
    price_actual: Num
    demand_bid_mwh: Num
    charge_bid_mwh: Num
    charge_limit_eur_mwh: Num | None
    planned_discharge_mwh: Num
    charge_cleared_mwh: Num
    charge_actual_mwh: Num
    discharge_actual_mwh: Num
    soc_mwh: Num
    shortage_mwh: Num
    surplus_mwh: Num
    da_cost_chf: Num
    imbalance_cost_chf: Num
    imbalance_penalty_chf: Num
    wear_cost_chf: Num


class BidRow(M):
    hour: str
    utc: str
    block: int
    bid_type: Literal["demand", "charge"]
    volume_mwh: Num
    limit_price_eur_mwh: Num | None


class DaySummary(M):
    soc_start_mwh: Num
    soc_end_mwh: Num
    energy_to_buy_mwh: Num
    charged_mwh: Num
    discharged_mwh: Num
    cycles: Num
    expected_cost_chf: Num
    expected_battery_saving_chf: Num
    realised_cost_chf: Num
    realised_battery_saving_chf: Num
    realised_saving_vs_baseline_chf: Num
    baseline_cost_chf: Num
    imbalance_penalty_chf: Num
    imbalance_cost_chf: Num
    wear_cost_chf: Num
    share_charge_cleared: Num | None
    eurchf: Num


class DayPlan(M):
    date: str
    split: Literal["val", "test", "custom"]
    weekday: str
    is_holiday: StrictBool
    holiday_name: str | None
    event_name: str | None
    battery: BatterySettings
    blocks: list[BlockRow]
    hours: list[HourRow]
    bids: list[BidRow]
    summary: DaySummary


class StrategyRow(M):
    key: str
    name: str
    note: str
    kind: Literal["baseline", "product", "reference", "ceiling"]
    total_cost_chf: Num
    saving_vs_baseline_chf: Num
    saving_ci_low_chf: Num | None
    saving_ci_high_chf: Num | None
    imbalance_penalty_chf: Num
    wear_cost_chf: Num
    cycles: Num
    pct_of_ceiling: Num | None


class Decomp(M):
    total_saving_chf: Num
    demand_forecast_part_chf: Num
    battery_part_chf: Num
    block_default_battery_part_chf: Num
    tuning_and_shaping_part_chf: Num
    ceiling_total_saving_chf: Num
    ceiling_battery_value_chf: Num
    pct_ceiling_captured_total: Num
    pct_ceiling_battery_value_captured: Num
    finer_dispatch_part_chf: Num | None
    interday_flexibility_part_chf: Num | None


class CI(M):
    independent_low: Num
    independent_high: Num
    block_low: Num
    block_high: Num
    lag1_autocorr: Num


class Series(M):
    key: str
    name: str
    values: list[Num]


class Cumulative(M):
    dates: list[str]
    series: list[Series]


class DailyPart(M):
    date: str
    demand_part_chf: Num
    battery_part_chf: Num


class BacktestSplit(M):
    split: Literal["test", "val", "rolling"]
    label: str
    out_of_sample: StrictBool
    days: int
    strategies: list[StrategyRow]
    decomposition: Decomp
    ci: CI | None
    cumulative: Cumulative
    daily: list[DailyPart]


class SizeRow(M):
    power_mw: Num
    capacity_mwh: Num
    ml_battery_value_chf: Num
    ceiling_battery_value_chf: Num


class PEPoint(M):
    mae_eur_mwh: Num
    lost_chf: Num


class PriceError(M):
    points: list[PEPoint]
    slope_chf_per_eur: Num
    ml: PEPoint
    naive: PEPoint


class ImbRow(M):
    shortage_factor: Num
    surplus_factor: Num
    total_saving_chf: Num
    demand_part_chf: Num
    battery_part_chf: Num


class Backtest(M):
    splits: list[BacktestSplit]
    battery_size: list[SizeRow]
    price_error: PriceError
    imbalance: list[ImbRow]


class LadderRow(M):
    model: Literal["naive", "linear", "rf", "gbm", "best"]
    name: str
    val_mae: Num
    test_mae: Num
    test_ci_low: Num
    test_ci_high: Num
    test_pct: Num
    rolling_mae: Num | None


class ByBlock(M):
    block: int
    label: str
    best_mae: Num
    naive_mae: Num


class Imp(M):
    feature: str
    label: str
    value: Num


class Group(M):
    group: str
    value: Num


class SeriesRow(M):
    date: str
    block: int
    actual: Num
    best: Num
    naive: Num
    q10: Num | None
    q90: Num | None


class ModelInfo(M):
    target: Literal["demand", "price"]
    unit: str
    pct_metric: Literal["MAPE", "sMAPE"]
    best_description: str
    ladder: list[LadderRow]
    by_block: list[ByBlock]
    importance: list[Imp]
    groups: list[Group]
    test_series: list[SeriesRow]


class Models(M):
    demand: ModelInfo
    price: ModelInfo


class TempPt(M):
    temp_c: Num
    demand_mw: Num
    n: int


class TempBlock(M):
    block: int
    label: str
    points: list[TempPt]


class RadPt(M):
    radiation_wm2: Num
    demand_mw: Num
    n: int


class Profile(M):
    daytype: Literal["Working day", "Saturday", "Sunday", "Public holiday"]
    hours: list[int]
    demand_mw: list[Num]


class EvRow(M):
    year: int
    ev_count: Num
    night_demand_mw: Num


class LabelProfile(M):
    label: str
    hours: list[int]
    demand_mw: list[Num]


class Heat(M):
    months: list[str]
    blocks: list[str]
    values: list[list[Num]]


class WindRow(M):
    wind_bin: str
    price_vs_recent_eur: Num
    n: int


class GasRow(M):
    month: str
    gas_eur_mwh: Num
    price_eur_mwh: Num


class NegRow(M):
    year: int
    hours: int


class Drivers(M):
    temp_demand: list[TempBlock]
    radiation_demand: list[RadPt]
    profile: list[Profile]
    ev: list[EvRow]
    street_parade: list[LabelProfile]
    school_holiday: list[LabelProfile]
    price_heatmap: Heat
    wind_price: list[WindRow]
    gas_price: list[GasRow]
    negative_hours: list[NegRow]


class Source(M):
    input: str
    source: str
    step: str
    note: str


class TimeRule(M):
    input: str
    known: str


class Limitation(M):
    title: str
    text: str


class Review(M):
    phase: str
    finding: str
    decision: str


class Method(M):
    sources: list[Source]
    time_rules: list[TimeRule]
    limitations: list[Limitation]
    reviews: list[Review]


# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def out(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("web_data")
    ex.main(["--out", str(d)])
    return d


def load(out: Path, name: str):
    return json.loads((out / name).read_text(encoding="utf-8"))


def _no_nan(obj, where="") -> None:
    if isinstance(obj, float):
        assert math.isfinite(obj), f"non-finite number at {where}"
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _no_nan(v, f"{where}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _no_nan(v, f"{where}[{i}]")


def test_files_and_no_nan(out):
    files = sorted(p.relative_to(out).as_posix() for p in out.rglob("*.json"))
    for f in ["meta.json", "backtest.json", "models.json", "drivers.json", "method.json"]:
        assert f in files
    total = 0
    for f in out.rglob("*.json"):
        txt = f.read_text(encoding="utf-8")
        total += len(txt.encode())
        for bad in ["NaN", "Infinity"]:
            assert bad not in txt, f"{bad} in {f.name}"
        _no_nan(json.loads(txt), f.name)
    assert total < 5 * 1024 * 1024


def test_meta_and_days(out):
    meta = Meta.model_validate(load(out, "meta.json"))
    assert len(meta.days) == 61
    assert {d.split for d in meta.days} == {"val", "test"}
    assert sum(d.split == "test" for d in meta.days) == 31
    assert {d.hours for d in meta.days} <= {23, 24, 25}
    assert len(meta.block_labels) == 6
    day_files = sorted(p.stem for p in (out / "days").glob("*.json"))
    assert day_files == [d.date for d in meta.days]

    bt = pd.read_csv(ROOT / "reports" / "backtest.csv")
    bt = bt[(bt["strategy"] == "ml_battery") & bt["split"].isin(["val", "test"])].set_index("delivery_date")
    for md in meta.days:
        p = DayPlan.model_validate(load(out, f"days/{md.date}.json"))
        assert len(p.blocks) == 6 and [b.block for b in p.blocks] == list(range(6))
        assert len(p.hours) == md.hours == sum(b.hours for b in p.blocks)
        assert p.split == md.split
        r = bt.loc[md.date]
        assert abs(p.summary.realised_cost_chf - r["total_cost_chf"]) <= 0.01
        assert abs(p.summary.soc_start_mwh - r["soc_start_mwh"]) <= 1e-3
        assert abs(sum(h.da_cost_chf + h.imbalance_cost_chf + h.wear_cost_chf for h in p.hours)
                   - p.summary.realised_cost_chf) < 0.05 * len(p.hours)
    p = DayPlan.model_validate(load(out, "days/2026-10-25.json"))
    assert len(p.hours) == 25 and p.blocks[0].hours == 5
    assert [h.hour for h in p.hours[2:4]] == ["02:00", "02:00"] and p.hours[2].utc != p.hours[3].utc


def test_october_saving_equals_decomposition(out):
    meta = Meta.model_validate(load(out, "meta.json"))
    total = sum(load(out, f"days/{d.date}.json")["summary"]["realised_saving_vs_baseline_chf"]
                for d in meta.days if d.split == "test")
    dec = pd.read_csv(ROOT / "reports" / "backtest_decomposition.csv").set_index("split").loc["test"]
    assert abs(total - dec["total_saving_chf"]) < 1.0


def test_backtest(out):
    b = Backtest.model_validate(load(out, "backtest.json"))
    by = {s.split: s for s in b.splits}
    assert set(by) == {"test", "val", "rolling"}
    assert by["test"].out_of_sample and not by["val"].out_of_sample and not by["rolling"].out_of_sample
    keys = [s.key for s in by["test"].strategies]
    assert keys[0] == "baseline_naive_no_battery" and len(keys) == 9
    assert {"ml_battery_block_default", "perfect_foresight_hourly_daily_battery",
            "perfect_demand_no_battery"} <= set(keys)
    t = by["test"]
    assert len(t.cumulative.dates) == t.days == len(t.daily)
    prod = next(s for s in t.cumulative.series if s.key == "ml_battery")
    assert abs(prod.values[-1] - sum(d.demand_part_chf + d.battery_part_chf for d in t.daily)) < 1.0
    ref = next(r for r in b.imbalance if r.shortage_factor == 1.2 and r.surplus_factor == 0.8)
    assert abs(ref.total_saving_chf - t.decomposition.total_saving_chf) < 1.0
    assert abs(ref.battery_part_chf - t.decomposition.battery_part_chf) < 1.0
    assert len(b.imbalance) == 3


def test_models(out):
    m = Models.model_validate(load(out, "models.json"))
    for info in (m.demand, m.price):
        assert len(info.test_series) == 186 and len(info.by_block) == 6
        assert [r.model for r in info.ladder] == ["naive", "linear", "rf", "gbm", "best"]
        assert len(info.importance) == 15
        for i in info.importance:
            assert i.label and i.label != i.feature and "_" not in i.label


def test_drivers_and_method(out):
    d = Drivers.model_validate(load(out, "drivers.json"))
    assert len(d.temp_demand) == 6 and len(d.profile) == 4
    assert len(d.price_heatmap.months) == 24 and all(len(r) == 6 for r in d.price_heatmap.values)
    assert len(d.street_parade) == 2 and len(d.school_holiday) == 2
    m = Method.model_validate(load(out, "method.json"))
    assert 8 <= len(m.time_rules) <= 10
    assert 8 <= len(m.limitations) <= 12
    assert m.sources and m.reviews and all(r.phase for r in m.reviews)
    imb = m.limitations[0].text
    half = pd.read_csv(ROOT / "reports" / "backtest_decision_sensitivity.csv")
    half = half[(half["parameter"] == "imbalance_factors") & (half["value"] == "1.1/0.9")].iloc[0]
    assert f"{half['saving_ml_battery_vs_baseline_chf']:,.0f}" in imb
