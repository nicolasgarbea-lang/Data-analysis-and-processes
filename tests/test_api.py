"""Live planning API (api/server.py)."""
from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api.server import app
from src.config import ROOT
from src.export import export_web as ex


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json() == {"ok": True}


def test_plan_default_equals_export(client):
    bat = ex.default_battery_settings()
    r = client.post("/api/plan", json={"date": "2026-10-14", "battery": bat})
    assert r.status_code == 200
    got = r.json()
    assert got["split"] == "custom"
    days = ex.export_days()  # carried charge level, as written to web/public/data/days
    want = days["2026-10-14"]
    assert {k: v for k, v in got.items() if k != "split"} == {k: v for k, v in want.items() if k != "split"}


def test_bigger_battery_changes_plan(client):
    bat = ex.default_battery_settings()
    a = client.post("/api/plan", json={"date": "2026-10-14", "battery": bat}).json()
    big = dict(bat, power_mw=60, capacity_mwh=120)
    b = client.post("/api/plan", json={"date": "2026-10-14", "battery": big}).json()
    assert b["battery"]["capacity_mwh"] == 120
    assert b["summary"]["discharged_mwh"] > a["summary"]["discharged_mwh"]
    assert len(b["blocks"]) == 6 and len(b["hours"]) == 24


@pytest.mark.parametrize("change", [
    {"power_mw": 500}, {"capacity_mwh": 0.5}, {"soc_min_frac": 0.9, "soc_max_frac": 0.5},
    {"round_trip_efficiency": 0.3}, {"max_cycles_per_day": 5}, {"wear_cost_eur_per_mwh": -1},
])
def test_invalid_battery_422(client, change):
    bat = dict(ex.default_battery_settings(), **change)
    r = client.post("/api/plan", json={"date": "2026-10-14", "battery": bat})
    assert r.status_code == 422
    assert isinstance(r.json()["detail"], str) and r.json()["detail"]


def test_invalid_date_422(client):
    r = client.post("/api/plan", json={"date": "2025-01-01", "battery": ex.default_battery_settings()})
    assert r.status_code == 422 and "2025-01-01" in r.json()["detail"]


def test_month_default_equals_decomposition(client):
    r = client.post("/api/month", json={"battery": ex.default_battery_settings()})
    assert r.status_code == 200
    m = r.json()
    dec = pd.read_csv(ROOT / "reports" / "backtest_decomposition.csv").set_index("split").loc["test"]
    assert m["days"] == 31
    assert abs(m["saving_vs_baseline_chf"] - dec["total_saving_chf"]) < 1.0
    assert abs(m["battery_value_chf"] - dec["battery_part_chf"]) < 1.0
    assert abs(m["ceiling_battery_value_chf"] - dec["ceiling_battery_value_chf"]) < 1.0
