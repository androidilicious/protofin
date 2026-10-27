import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import stage2_backtest as s2


def test_month_arithmetic_crosses_january_correctly():
    assert str(s2.month_add("2019-01", -2)) == "2018-11"
    assert str(s2.month_add("2019-01", -1)) == "2018-12"
    assert str(s2.month_add("2019-12", 2)) == "2020-02"


def test_first_development_training_window_is_48_calendar_months():
    months = s2.month_range("2015-02", "2019-01")
    assert len(months) == 48
    assert str(months[0]) == "2015-02"
    assert str(months[-1]) == "2019-01"


def test_scaler_uses_finite_training_values_and_missing_becomes_zero():
    X = np.array([[1.0, np.nan], [3.0, 5.0], [5.0, 7.0]])
    sc = s2.fit_scaler(X)
    z = s2.transform_with_scaler(np.array([np.nan, np.nan]), sc)
    assert np.allclose(z, [0.0, 0.0])
    assert np.allclose(sc.mean, [3.0, 6.0])


def test_inner_cv_has_one_month_purge():
    splits = s2.inner_splits(48, minimum_train=36, purge=1, stride=1)
    assert len(splits) == 11
    tr, val = splits[0]
    assert val == 37
    assert len(tr) == 36
    assert tr[-1] == 35
    assert 36 not in tr  # purged month immediately before validation


def test_dtb4wk_conversion_matches_formula():
    quote = 5.0
    d = quote / 100.0
    discount = d * 28.0 / 360.0
    expected = discount / (1.0 - discount)
    assert s2.dtb4wk_28d_effective_return(quote) == pytest.approx(expected)
    assert s2.accrue_dtb4wk(quote, 28) == pytest.approx(expected)


def test_macro_loader_retains_2019_01_missing_retail(tmp_path: Path):
    # Build a calendar-complete mini panel spanning the known shutdown month.
    months = pd.period_range("2018-12", "2019-02", freq="M")
    rows = []
    for m in months:
        row = {"month": str(m)}
        for c in s2.MACRO_FEATURES:
            row[c] = 0.5
        rows.append(row)
    rows[1]["retail_sales_z"] = np.nan
    p = tmp_path / "macro.csv"
    pd.DataFrame(rows).to_csv(p, index=False)
    out = s2.load_macro_panel({"path": str(p)})
    jan = out[out.month == pd.Period("2019-01", freq="M")].iloc[0]
    assert pd.isna(jan.retail_sales_z)


def test_macro_loader_rejects_dropped_whole_month(tmp_path: Path):
    rows = []
    for m in ["2015-02", "2015-04"]:
        row = {"month": m}
        row.update({c: 0.0 for c in s2.MACRO_FEATURES})
        rows.append(row)
    p = tmp_path / "macro.csv"
    pd.DataFrame(rows).to_csv(p, index=False)
    with pytest.raises(s2.IntegrityError, match="drops whole calendar months"):
        s2.load_macro_panel({"path": str(p)})


def test_historical_gate_is_locked_when_not_go(tmp_path: Path):
    p = tmp_path / "gate.json"
    p.write_text(json.dumps({"historical_test_status": "SEALED_NOT_SCORED"}))
    with pytest.raises(s2.HistoricalTestLocked):
        s2.assert_historical_go(p, "CONFIRM_HISTORICAL_TEST_GO")


def test_historical_gate_requires_explicit_token_even_if_go(tmp_path: Path):
    p = tmp_path / "gate.json"
    p.write_text(json.dumps({"historical_test_status": "GO"}))
    with pytest.raises(s2.HistoricalTestLocked):
        s2.assert_historical_go(p, None)


def test_ridge_intercept_only_is_training_mean():
    X = np.array([[1.0], [2.0], [3.0]])
    y = np.array([0.01, 0.02, 0.03])
    pred, norm = s2.ridge_fit_predict(X, y, np.array([99.0]), "INTERCEPT_ONLY")
    assert pred == pytest.approx(0.02)
    assert norm == 0.0


def test_bootstrap_is_deterministic():
    x = [0.1, -0.2, 0.3, 0.0, 0.05, -0.01, 0.02]
    a = s2.circular_block_bootstrap_mean(x, reps=100, seed=123)
    b = s2.circular_block_bootstrap_mean(x, reps=100, seed=123)
    assert a == b


def test_alpha_grid_exact_order_and_intercept_strongest():
    assert s2.ALPHAS == (1e-4, 1e-2, 1.0, 1e2, 1e4, 1e6, 1e8, 1e10, "INTERCEPT_ONLY")
    assert s2._alpha_strength("INTERCEPT_ONLY") > s2._alpha_strength(1e10)
