"""Smoke tests for the Streamlit app (streamlit.testing.v1.AppTest).

* the app runs without an exception and shows all five tabs,
* changing the delivery day and a battery slider re-runs without an exception,
* the "whole month" button works (fast: 31 days x 4 strategies, serial),
* the stand-in notice is shown exactly when the price prediction file is missing.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
APP = str(ROOT / "app" / "streamlit_app.py")
PRICE_FILE = ROOT / "reports" / "predictions_price.parquet"


def _run(at: AppTest) -> AppTest:
    at.run()
    assert not at.exception, [e.message for e in at.exception]
    return at


@pytest.fixture(scope="module")
def app() -> AppTest:
    return _run(AppTest.from_file(APP, default_timeout=120))


def test_app_starts_and_has_five_tabs(app):
    labels = [t.label for t in app.tabs]
    assert labels == ["Tomorrow", "Battery settings", "Month backtest", "What drives demand and price",
                      "Data and method"]
    assert not app.error, [e.value for e in app.error]
    # KPI tiles and the one-line verdict of the Tomorrow tab
    metric_labels = [m.label for m in app.metric]
    for lbl in ["Energy to buy", "Expected cost", "Expected battery saving", "Realised cost after settlement",
                "Imbalance cost"]:
        assert lbl in metric_labels
    assert any(m.value.startswith("####") and "Expected saving" in m.value for m in app.markdown)
    # every tab renders something
    for tab in app.tabs:
        assert len(tab.children) > 0


def test_price_fallback_notice_matches_files(app):
    notice = any("Price model not available yet" in w.value for w in app.warning)
    assert notice == (not PRICE_FILE.exists())


def test_change_date_and_slider(app):
    app.date_input(key="day").set_value(dt.date(2026, 9, 15))
    _run(app)
    assert "validation" in " ".join(m.value for m in app.sidebar.markdown)
    app.date_input(key="day").set_value(dt.date(2026, 10, 20))
    app.slider(key="bat_cap").set_value(80.0)
    app.slider(key="bat_power").set_value(40.0)
    app.checkbox(key="bat_sell").check()
    _run(app)
    assert not app.error, [e.value for e in app.error]
    app.toggle(key="show_actual").set_value(False)
    app.radio(key="bt_split").set_value("val")
    _run(app)


def test_whole_month_button(app):
    app.slider(key="bat_cap").set_value(60.0)
    app.button(key="month_btn").click()
    _run(app)
    assert not app.error, [e.value for e in app.error]
    assert any("With your battery our product saves" in s.value for s in app.success)
