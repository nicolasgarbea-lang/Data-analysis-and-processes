"""Fast tests for the price model outputs and helpers (src/models/price.py, src/models/price_common.py).

The output tests need `.venv/bin/python -m src.models.price` to have run once."""
import joblib
import numpy as np
import pandas as pd
import pytest

import src.models.common as common
from src.config import path
from src.features.feature_sets import PRICE_FEATURES
from src.models.price_common import AsinhTarget, PriceExtras

MODEL = path("models") / "price_best.joblib"
LADDER = path("models") / "price_ladder.joblib"
PRED = path("reports") / "predictions_price.parquet"
METRICS = path("reports") / "metrics_price.csv"
DECISION = path("reports") / "decision_metrics_price.csv"
needs_outputs = pytest.mark.skipif(not (MODEL.exists() and PRED.exists() and METRICS.exists()),
                                   reason="run `python -m src.models.price` first")


# ---------------------------------------------------------------- helpers (no files needed)
class _Const:
    """Tiny regressor that remembers the mean target (to test the asinh wrapper)."""

    def fit(self, X, z, sample_weight=None):
        self.z = float(np.mean(z))
        return self

    def predict(self, X):
        return np.full(len(X), self.z)


def test_asinh_wrapper_roundtrip_with_negative_prices():
    X = pd.DataFrame({"ref": [-20.0, 0.0, 50.0, 300.0]})
    y = X["ref"].to_numpy()                       # target = reference -> learned change is 0
    m = AsinhTarget(_Const(), "ref", scale=50.0).fit(X, y)
    assert np.allclose(m.predict(X), y)


def test_price_extras_only_uses_known_columns():
    pre = PriceExtras()
    assert common.forbidden_columns(pre.input_columns) == []
    assert all(c in PRICE_FEATURES for c in pre.input_columns)
    row = pd.DataFrame({c: [1.0] for c in pre.input_columns})
    row["weekday"] = 0                                # Monday -> day D was Sunday
    row["is_holiday"] = 0
    row["is_holiday_prev_day"] = 0
    out = pre.transform(row)
    assert set(pre.output_columns) <= set(out.columns)
    assert out["dD_weekday"].iloc[0] == 6 and out["dD_daytype"].iloc[0] == 2


def test_decision_scores_perfect_forecast():
    from src.models.price import decision_scores
    g = pd.DataFrame({"delivery_date": np.repeat(pd.date_range("2026-09-01", periods=3), 6),
                      "y_true": np.tile([50.0, 60, 40, 10, 90, 80], 3)})
    g["p"] = g["y_true"] + 5                          # same shape, level off by 5
    s = decision_scores(g, "p")
    assert s["rank_corr"] == pytest.approx(1.0) and s["hit_cheapest"] == 1.0 and s["hit_dearest"] == 1.0
    assert s["shape_mae"] == pytest.approx(0.0) and s["daymean_mae"] == pytest.approx(5.0)


# ---------------------------------------------------------------- outputs of the price run
@pytest.fixture(scope="module")
def october():
    return common.split_frame(common.load_features(), "test")


@needs_outputs
def test_saved_model_predicts_october(october):
    m = joblib.load(MODEL)
    p = m.predict(october)
    assert len(p) == 186 and np.isfinite(p).all()
    assert -100 < p.min() and p.max() < 1000             # EUR/MWh, plausible range
    q = m.predict_quantiles(october)
    assert (q["pred_q10"] <= q["pred_q50"]).all() and (q["pred_q50"] <= q["pred_q90"]).all()
    assert np.isfinite(q.to_numpy()).all()


@needs_outputs
def test_saved_model_has_no_forbidden_columns():
    m = joblib.load(MODEL)
    assert common.forbidden_columns(m.features) == []
    assert common.forbidden_columns(m.input_columns) == []
    assert m.weather_map == {}                            # product model: hybrid weather, no oracle
    derived = set(PriceExtras.output_columns)
    extra = [c for c in m.features if c not in PRICE_FEATURES and c not in derived]
    assert extra == [], extra
    assert all(c in PRICE_FEATURES for c in m.input_columns)


@needs_outputs
def test_ladder_loads_and_predicts(october):
    if not LADDER.exists():
        pytest.skip("ladder not saved")
    lad = joblib.load(LADDER)
    assert set(lad) == {"naive", "linear", "rf", "gbm"}
    for name, m in lad.items():
        assert np.isfinite(m.predict(october)).all(), name
    assert MODEL.stat().st_size < 20e6
    assert MODEL.stat().st_size + LADDER.stat().st_size < 50e6


@needs_outputs
def test_predictions_file():
    pr = pd.read_parquet(PRED)
    need = ["delivery_date", "block", "split", "y_true", "pred_naive", "pred_linear", "pred_rf", "pred_gbm",
            "pred_best", "pred_q10", "pred_q50", "pred_q90"]
    assert all(c in pr.columns for c in need)
    te = pr[pr["split"] == "test"]
    assert len(te) == 186 and te[need].notna().all().all()
    assert len(pr[pr["split"] == "val"]) == 180
    assert set(pr["split"]) <= {"rolling", "val", "test"}
    assert pd.to_datetime(te["delivery_date"]).dt.month.eq(10).all()
    assert not pr.duplicated(["delivery_date", "block"]).any()


@needs_outputs
def test_metrics_match_predictions():
    pr = pd.read_parquet(PRED)
    met = pd.read_csv(METRICS, dtype={"block": str})
    for split in ["val", "test"]:
        g = pr[pr["split"] == split]
        for m in ["naive", "linear", "rf", "gbm", "best"]:
            row = met[(met["split"] == split) & (met["model"] == m) & (met["block"] == "all")].iloc[0]
            assert row["mae"] == pytest.approx(common.mae(g["y_true"], g[f"pred_{m}"]), rel=1e-9)
            assert row["rmse"] == pytest.approx(common.rmse(g["y_true"], g[f"pred_{m}"]), rel=1e-9)
            assert row["mape_or_smape"] == pytest.approx(common.smape(g["y_true"], g[f"pred_{m}"]), rel=1e-9)
            assert row["n"] == len(g)
        b3 = g[g["block"] == 3]
        row = met[(met["split"] == split) & (met["model"] == "best") & (met["block"] == "3")].iloc[0]
        assert row["mae"] == pytest.approx(common.mae(b3["y_true"], b3["pred_best"]), rel=1e-9)


@needs_outputs
def test_decision_metrics_match_predictions():
    from src.models.price import decision_scores
    pr = pd.read_parquet(PRED)
    dec = pd.read_csv(DECISION)
    g = pr[pr["split"] == "test"]
    row = dec[(dec["split"] == "test") & (dec["model"] == "best")].iloc[0]
    s = decision_scores(g, "pred_best")
    for k in ["rank_corr", "hit_cheapest", "hit_dearest", "shape_mae", "daymean_mae"]:
        assert row[k] == pytest.approx(s[k], rel=1e-9)
