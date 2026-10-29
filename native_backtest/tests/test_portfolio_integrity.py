"""Regression tests for the portfolio return integrity audit (development window only)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from native_backtest.scripts import audit_portfolio_integrity as A

ROOT = Path(__file__).resolve().parents[2]


def test_audit_is_independent_of_the_project_accounting_code():
    import ast
    tree = ast.parse(Path(A.__file__).read_text())
    mods = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} | {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not any(m and (m.startswith("native_backtest") or m.startswith("stage2")) for m in mods), mods


def test_independent_reconstruction_matches_evaluator_stage2_and_dashboard():
    assert A.main() == 0                                     # no findings
    r = json.loads((ROOT / "native_backtest/out/audit/portfolio_integrity_v1.json").read_text())
    for s, v in r["reconciliation"]["vs_shared_evaluator"].items():
        assert v["months_equal"] and v["entry_exit_equal"], s
        assert v["max_abs_diff_net_return"] < 1e-12 and v["max_abs_diff_weights"] < 1e-12 and v["max_abs_diff_rf"] < 1e-12, s
    assert r["reconciliation"]["vs_stage2_saved_system_A"]["max_abs_diff_net_return"] < 1e-12
    for key in ("det", "jev"):
        d = r["reconciliation"]["vs_dashboard"][key]
        assert d["max_abs_diff_wealth"] <= 5e-7 and d["max_abs_diff_monthly_net"] <= 5e-7      # 6-decimal display rounding
        assert d["wealth_matches_other_system"] is False                                      # no series swapped or reused
    assert r["reconciliation"]["vs_dashboard"]["det"]["source_system"] == "AP1"
    assert r["reconciliation"]["vs_dashboard"]["jev"]["source_system"] == "AP2B"
    assert r["integrity"]["look_ahead_and_date_problems"] == []
    assert r["decisions"]["AP1"]["distinct_weight_vectors"] == 46 and r["decisions"]["AP2B"]["distinct_weight_vectors"] == 46


def test_accounting_rules_on_a_hand_checked_example():
    idx = pd.to_datetime(["2019-03-29", "2019-04-01", "2019-04-30", "2019-05-01", "2019-05-31", "2019-06-03"])
    prices = {"X": pd.Series([100, 100, 105, 110, 108, 99.0], index=idx), "Y": pd.Series([50, 50, 50, 50, 51, 55.0], index=idx)}
    cal = A.calendar(prices)
    dtb = pd.Series([0.0, 0.0], index=pd.to_datetime(["2019-03-29", "2019-04-30"]))
    df = A.simulate({"2019-03": {"X": 0.5, "Y": 0.5}, "2019-04": {"X": 0.5, "Y": 0.5}}, ["2019-03", "2019-04"], prices, cal, dtb)
    # month 1: from cash, traded 1.0, cost 0.0005; X +10%, Y 0% -> gross 5%
    assert df.loc[0, "traded"] == 1.0 and abs(df.loc[0, "gross"] - 0.05) < 1e-15 and abs(df.loc[0, "net"] - 0.0495) < 1e-15
    # month 2: drifted pre-trade weights 0.55/0.45 (X grew) -> traded 0.1, cost 0.00005
    assert abs(df.loc[1, "traded"] - (abs(0.5 - 0.55 / 1.05) + abs(0.5 - 0.5 / 1.05))) < 1e-15
    assert abs(df.loc[1, "gross"] - (0.5 * (99 / 110 - 1) + 0.5 * (55 / 50 - 1))) < 1e-15
    assert df.loc[0, "entry"] == "2019-04-01" and df.loc[0, "exit"] == "2019-05-01"
