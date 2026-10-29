"""Signal value-added analysis: signal switch-off, conventions, costs, independence, reconciliation, reproducibility."""
import ast
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from native_backtest.framework import metrics as M
from native_backtest.framework.accounting import static_portfolio_records
from native_backtest.framework.market import load_config, load_market, months_between
from native_backtest.framework.records import read_jsonl
from native_backtest.scripts import audit_signal_value as AV
from native_backtest.scripts import signal_value_added as SV

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "native_backtest/out/signal_value"
FILES = ("signal_value_v1.json", "monthly_v1.csv", "jev_native_signal_on_off_engine.json")


@pytest.fixture(scope="module")
def run():
    """Run the analysis and the independent check once; outputs must come back byte-identical."""
    before = {f: hashlib.sha256((OUT / f).read_bytes()).hexdigest() for f in FILES if (OUT / f).exists()}
    assert SV.main([]) == 0
    after = {f: hashlib.sha256((OUT / f).read_bytes()).hexdigest() for f in FILES}
    assert AV.main() == 0
    return {"before": before, "after": after, "res": json.loads((OUT / "signal_value_v1.json").read_text()),
            "mon": pd.read_csv(OUT / "monthly_v1.csv", dtype={"decision_month": str})}


@pytest.fixture(scope="module")
def built():
    cfg = load_config()
    dev = months_between(*cfg["windows"]["development"])
    mk = load_market(cfg)
    return cfg, SV.build(cfg, mk, dev)


def test_reproducible_and_independently_confirmed(run):
    assert run["before"] == {} or run["before"] == run["after"], "outputs changed on a rerun"
    chk = json.loads((OUT / "independent_check_v1.json").read_text())
    assert chk["failures"] == [] and chk["checks"] >= 200 and chk["largest_difference"] <= 1e-12


def test_independent_check_imports_no_project_accounting_code():
    tree = ast.parse((ROOT / "native_backtest/scripts/audit_signal_value.py").read_text())
    mods = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} | {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert mods <= {"__future__", "json", "math", "pathlib", "numpy", "pandas", "native_backtest.scripts"}
    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module == "native_backtest.scripts" for a in n.names}
    assert imported == {"audit_portfolio_integrity"}   # itself independent of the framework (test_portfolio_integrity)


def test_signals_are_disabled_and_nothing_else_changes(built):
    cfg, b = built
    S, recs = b["sims"], b["records"]
    for s in ("AP1", "AP2B"):
        w0 = cfg["systems"][s]["native_neutral_weights"]
        on, off = S[f"{s}_ON"], S[f"{s}_OFF"]
        assets = list(w0)
        assert list(recs[s][0].universe) == assets                       # same universe as the strategy
        assert [c for c in off.columns if c.startswith("w_")] == [f"w_{a}" for a in assets]
        for a in assets:
            assert (off[f"w_{a}"] == w0[a]).all()                          # the tilt is gone in every month
        assert any((on[f"w_{a}"] != w0[a]).any() for a in assets)           # and the strategy did tilt
        for c in ("decision_month", "entry_date", "exit_date", "rf_return"):
            assert (on[c] == off[c]).all()                                 # same dates and cash
        st = static_portfolio_records("X", w0, recs[s])
        assert all(r.forecast is None and r.target_weights == w0 and r.decision_time == q.decision_time for r, q in zip(st, recs[s]))


def test_native_engines_with_signals_switched_off_hold_the_fixed_mix(run):
    nat = run["res"]["sensitivities"]["jev_native_engine"]
    assert nat["max_abs_spy_weight_off_minus_60pct"] < 1e-12 and nat["max_abs_prior_weight_minus_60pct"] < 1e-12
    assert nat["max_abs_nav_off_minus_engine_fixed_60_40"] < 1e-12 and nat["max_abs_weight_on_minus_decision_records"] == 0.0
    assert nat["last_as_of"] <= "2022-12-30" and nat["months"] == 46
    s2 = run["res"]["sensitivities"]["stage2_native_deterministic"]
    assert s2["max_abs_diff_net_return_static_vs_signals_off"] < 1e-12 and s2["max_abs_diff_net_return_A_vs_signals_on"] < 1e-12


def test_costs_and_turnover(built):
    cfg, b = built
    cost = cfg["costs"]["cost_per_dollar_traded"]
    for s in ("AP1", "AP2B"):
        for k in (f"{s}_ON", f"{s}_OFF"):
            d = b["sims"][k]
            assert np.allclose(d["cost"], cost * d["traded_notional"], rtol=0, atol=1e-18)
            assert d["traded_notional"].iloc[0] == pytest.approx(1.0)      # first month from cash
            assert np.allclose(d["one_way_turnover"], 0.5 * d["traded_notional"], rtol=0, atol=1e-18)
        off, ar = b["sims"][f"{s}_OFF"], b["asset_returns"]
        w0 = cfg["systems"][s]["native_neutral_weights"]
        w, r = np.array(list(w0.values())), ar[list(w0)].to_numpy()
        drifted = w * (1 + r[:-1]) / (w * (1 + r[:-1])).sum(axis=1, keepdims=True)
        assert np.allclose(off["traded_notional"].iloc[1:], np.abs(w - drifted).sum(axis=1), rtol=0, atol=1e-15)   # rebalancing back from drift
        bh = b["sims"][f"{s}_OFF_BUY_AND_HOLD"]
        assert bh["traded_notional"].iloc[1:].abs().max() < 1e-12          # the sensitivity really is buy-and-hold


def test_return_series_are_distinct(built):
    _, b = built
    S = b["sims"]
    x = {k: v["net_excess_return"].to_numpy() for k, v in S.items()}
    for s in ("AP1", "AP2B"):
        a = x[f"{s}_ON"] - x[f"{s}_OFF"]
        assert (np.abs(a) > 1e-9).sum() >= 40 and np.corrcoef(x[f"{s}_ON"], x[f"{s}_OFF"])[0, 1] < 1 - 1e-6
    assert np.abs(x["AP1_OFF"] - x["AP2B_OFF"]).min() > 0 and np.abs(x["AP1_ON"] - x["AP2B_ON"]).min() > 0


def test_attribution_reconciles_exactly(run):
    att, ret = run["res"]["attribution_net_cer"], run["res"]["attribution_mean_return"]
    assert abs(att["four_parts_residual"]) < 1e-12 and abs(att["two_by_two_residual"]) < 1e-12
    assert abs(att["trading_costs_split"]["residual"]) < 1e-12
    assert abs(att["mix_net_shapley_residual"]) < 1e-12 and abs(att["mix_before_costs_shapley_residual"]) < 1e-12
    for s, p in att["per_system"].items():
        assert abs(p["residual"]) < 1e-12
    assert ret["max_abs_monthly_residual"] < 1e-15 and ret["max_abs_mix_identity_residual"] < 1e-15
    assert abs(sum(ret["parts_annualised"].values()) - ret["annualised_mean_difference"]) < 1e-12
    q = run["res"]["questions"]
    assert abs(q["jev_minus_deterministic_total"]["point"] - (q["no_signal_mix_difference"]["point"] + q["q3_jev_vs_deterministic_after_allocation"]["point"])) < 1e-12


def test_previously_reported_results_are_reproduced_exactly(run):
    for k, c in run["res"]["reproduces_previous_results"].items():
        assert c["max_abs_difference"] == 0.0, k
    assert run["res"]["information_checks"]["problems"] == []


def test_joint_bootstrap_equals_the_frozen_paired_bootstrap(built):
    cfg, b = built
    P = SV.frozen(cfg)
    on, off = b["sims"]["AP2B_ON"], b["sims"]["AP2B_OFF"]
    j = SV.joint_bootstrap({"a": on["net_excess_return"].to_numpy(), "b": off["net_excess_return"].to_numpy()}, {"d": lambda c: c["a"] - c["b"]}, P)["d"]
    f = M.paired_cer_contrast(on, off)
    assert (j["point"], j["ci95"], j["ci90"], j["p_two_sided_bootstrap"]) == (f["cer_difference"], f["ci95"], f["ci90"], f["p_two_sided_bootstrap"])


def test_cer_identity_on_a_hand_checked_example():
    x0 = np.array([0.01, -0.02, 0.03, 0.00, 0.015])
    t = np.array([0.001, 0.002, -0.001, 0.0, 0.0005])
    lhs = M.cer(x0 + t) - M.cer(x0)
    rhs = 12 * t.mean() - 6 * 2.5 * t.var(ddof=1) - 12 * 2.5 * np.cov(x0, t, ddof=1)[0, 1]
    assert lhs == pytest.approx(rhs, abs=1e-15)


def test_only_development_months_and_no_new_rules(run):
    res = run["res"]
    assert res["months"] == ["2019-03", "2022-12", 46]
    assert res["safeguards"]["protected_window_scored"] is False and res["safeguards"]["model_calls"] == 0
    assert "monthly rebalancing" in res["conventions"]["rebalancing"] and "sensitivity" in res["conventions"]["rebalancing"]
    cfg = json.loads((ROOT / "native_backtest/config/framework_config_v1.json").read_text())
    assert cfg["systems"]["AP1"]["native_neutral_weights"] == {"SPY": 0.45, "IEF": 0.35, "LQD": 0.2}
    assert cfg["systems"]["AP2B"]["native_neutral_weights"] == {"SPY": 0.6, "TLT": 0.4}
    assert set(cfg["systems"]) == {"AP1", "AP2A", "AP2B", "AP3"}       # no new approach was added
