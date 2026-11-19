"""Fast tests for the demand model outputs and the shared model helpers (src/models/common.py).

The output tests need `.venv/bin/python -m src.models.demand` to have run once."""
import joblib
import numpy as np
import pandas as pd
import pytest

import src.models.common as common
from src.config import path
from src.features.feature_sets import DEMAND_FEATURES

MODEL = path("models") / "demand_best.joblib"
LADDER = path("models") / "demand_ladder.joblib"
PRED = path("reports") / "predictions_demand.parquet"
METRICS = path("reports") / "metrics_demand.csv"
needs_outputs = pytest.mark.skipif(not (MODEL.exists() and PRED.exists() and METRICS.exists()),
                                   reason="run `python -m src.models.demand` first")


# ---------------------------------------------------------------- shared helpers (no files needed)
def test_target_transforms_roundtrip():
    y = np.array([280.0, 310.0, 295.5])
    ref = np.array([300.0, 300.0, 290.0])
    for t in ["level", "diff", "ratio", "logratio"]:
        z = common.make_target(y, ref, t)
        assert np.allclose(common.invert_target(z, ref, t), y)


def test_metrics_and_bootstrap():
    y = np.array([100.0, 200.0, 300.0, 400.0])
    p = np.array([110.0, 190.0, 300.0, 380.0])
    assert common.mae(y, p) == pytest.approx(10.0)
    assert common.bias(y, p) == pytest.approx(-5.0)
    assert common.mape(y, p) == pytest.approx(100 * np.mean([0.1, 0.05, 0.0, 0.05]))
    assert common.smape([0.0], [0.0]) == 0.0
    days = np.repeat(np.arange(50), 6)
    rng = np.random.default_rng(0)
    yy = rng.normal(300, 10, len(days))
    pp = yy + rng.normal(0, 3, len(days))
    lo, hi = common.bootstrap_mae_ci(yy, pp, days, n_draws=500)
    assert lo < common.mae(yy, pp) < hi


def test_dm_test_sign():
    rng = np.random.default_rng(1)
    days = np.repeat(np.arange(60), 6)
    y = rng.normal(300, 10, len(days))
    good = y + rng.normal(0, 2, len(days))
    bad = y + rng.normal(0, 8, len(days))
    r = common.dm_test(y, good, bad, days)
    assert r["mean_diff"] < 0 and r["p_value"] < 0.01 and r["n_days"] == 60


def test_linear_design_handles_nan_and_unseen():
    X = pd.DataFrame({"block": [0, 1, 0, 1], "x": [1.0, np.nan, 3.0, 4.0], "t": [10.0, 12.0, 8.0, 9.0]})
    ld = common.LinearDesign(numeric=["x", "t"], onehot=["block"], interactions=[("block", "t")]).fit(X)
    out = ld.transform(pd.DataFrame({"block": [2], "x": [np.nan], "t": [5.0]}))
    assert np.isfinite(out).all() and out.shape[1] == len(ld.feature_names_)


# ---------------------------------------------------------------- outputs of the demand run
@pytest.fixture(scope="module")
def october():
    return common.split_frame(common.load_features(), "test")


@needs_outputs
def test_saved_model_predicts_october(october):
    m = joblib.load(MODEL)
    p = m.predict(october)
    assert len(p) == 186 and np.isfinite(p).all()
    assert 150 < p.mean() < 450                      # MW, Zurich city load
    q = m.predict_quantiles(october)
    assert (q["pred_q10"] <= q["pred_q90"]).all() and np.isfinite(q.to_numpy()).all()


@needs_outputs
def test_saved_model_has_no_forbidden_columns():
    m = joblib.load(MODEL)
    assert common.forbidden_columns(m.features) == []
    assert common.forbidden_columns(m.input_columns) == []
    assert m.weather_map == {} or not any(v.endswith("_obs") for v in m.weather_map.values())
    derived = set(getattr(m.preprocess, "output_columns", []))
    extra = [c for c in m.features if c not in DEMAND_FEATURES and c not in derived]
    assert all(c.endswith("_fc_jma") for c in extra), extra


@needs_outputs
def test_ladder_loads_and_predicts(october):
    if not LADDER.exists():
        pytest.skip("ladder not saved")
    lad = joblib.load(LADDER)
    assert set(lad) == {"naive", "linear", "rf", "gbm"}
    for name, m in lad.items():
        p = m.predict(october)
        assert np.isfinite(p).all(), name
    assert MODEL.stat().st_size < 20e6
    assert MODEL.stat().st_size + LADDER.stat().st_size < 50e6


@needs_outputs
def test_predictions_file():
    pr = pd.read_parquet(PRED)
    need = ["delivery_date", "block", "split", "y_true", "pred_naive", "pred_linear", "pred_rf", "pred_gbm",
            "pred_best"]
    assert all(c in pr.columns for c in need)
    te = pr[pr["split"] == "test"]
    assert len(te) == 186 and te[need].notna().all().all()
    assert len(pr[pr["split"] == "val"]) == 180
    assert set(pr["split"]) <= {"rolling", "val", "test"}
    assert pd.to_datetime(te["delivery_date"]).dt.month.eq(10).all()


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
            assert row["mape_or_smape"] == pytest.approx(common.mape(g["y_true"], g[f"pred_{m}"]), rel=1e-9)
            assert row["n"] == len(g)
        b3 = g[g["block"] == 3]
        row = met[(met["split"] == split) & (met["model"] == "best") & (met["block"] == "3")].iloc[0]
        assert row["mae"] == pytest.approx(common.mae(b3["y_true"], b3["pred_best"]), rel=1e-9)
