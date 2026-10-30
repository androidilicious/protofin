"""Forecast-to-allocation sensitivity: the properties the experiment must satisfy.

The experiment rescales each approach's investment view at the one point where a number enters its native
allocator and leaves everything else alone. These tests check the claims that make the results interpretable:
the transformation is the pre-registered affine blend, 1x reproduces what was already archived, 0x is genuinely
signal-neutral, the native position limits still bind, no decision can see a realised return, the accounting is
internally consistent, each approach keeps its own distinct pipeline, Causal RAG is never reported as computed,
and nothing frozen moved.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "native_backtest/out/sensitivity"
REPORT = OUT / "forecast_to_allocation_sensitivity.json"
PREREG = ROOT / "native_backtest/config/forecast_to_allocation_sensitivity_preregistration_v1.json"
SCEN = ("0x", "0.5x", "1x", "2x")
LAM = {"0x": 0.0, "0.5x": 0.5, "1x": 1.0, "2x": 2.0}
ASSETS = {"AP1": ("SPY", "IEF", "LQD"), "AP2B": ("SPY", "TLT"), "AP2A": ("SPY", "TLT")}
COMPUTED = ("AP1", "AP2B", "AP2A")

pytestmark = pytest.mark.skipif(not REPORT.exists(), reason="run python -m native_backtest.scripts.forecast_to_allocation")


@pytest.fixture(scope="module")
def rep():
    return json.loads(REPORT.read_text())


@pytest.fixture(scope="module")
def traces():
    return {s: pd.read_csv(OUT / f"{s.lower()}_transmission_trace.csv") for s in COMPUTED}


@pytest.fixture(scope="module")
def returns():
    return {s: pd.read_csv(OUT / f"{s.lower()}_scenario_returns.csv") for s in COMPUTED}


def part(df, scenario):
    return df[df["scenario"] == scenario].sort_values("decision_month").reset_index(drop=True)


# ------------------------------------------------------------------------------------------------- the algebra
def test_the_scenarios_are_the_pre_registered_ones(rep):
    pre = json.loads(PREREG.read_text())
    assert [float(x) for x in pre["scenarios"]["lambda_values"]] == [0.0, 0.5, 1.0, 2.0]
    assert set(rep["scenarios"]) == set(SCEN)
    assert rep["preregistration"]["file"].endswith("forecast_to_allocation_sensitivity_preregistration_v1.json")


def test_the_view_transformation_is_the_pre_registered_affine_blend(traces):
    """adjusted view = prior + lambda x (original - prior), at the allocator's own entry point."""
    for s in ("AP1", "AP2A"):
        a = ASSETS[s]
        base = part(traces[s], "1x")
        q1 = base[[f"q_adj_{x}" for x in a]].to_numpy(float)
        for sc in SCEN:
            g = part(traces[s], sc)
            pi = g[[f"pi_{x}" for x in a]].to_numpy(float)
            want = pi + LAM[sc] * (q1 - pi)
            assert np.abs(g[[f"q_adj_{x}" for x in a]].to_numpy(float) - want).max() < 1e-12, (s, sc)
    for sc in SCEN:                                   # JEV scales the signal part of its edge, not a return vector
        g = part(traces["AP2B"], sc)
        want = LAM[sc] * g["offset_original"].to_numpy(float) * g["confidence"].to_numpy(float)
        assert np.abs(g["weighted_offset"].to_numpy(float) - want).max() < 1e-12, sc
        assert np.abs(g["edge"].to_numpy(float) - (g["base_edge"].to_numpy(float) + want)).max() < 1e-12, sc


def test_the_intermediate_weight_matches_the_native_optimizer_when_no_bound_binds():
    """The Deterministic intermediate stage is the native optimizer's own all-free candidate, not an invention."""
    import sys
    sys.path.insert(0, str(ROOT / "stage2/scoring"))
    import stage2_portfolio as P
    from native_backtest.scripts.forecast_to_allocation import fully_invested
    rng = np.random.default_rng(7)
    checked = 0
    for _ in range(40):
        x = rng.normal(size=(60, 3)) * 0.02
        sigma = P.ledoit_wolf_cov(x)
        mu = P.DELTA * sigma @ P.PRIOR_WEIGHTS + rng.normal(size=3) * 1e-4
        w = P.optimal_weights(mu, sigma)
        u = fully_invested(mu, sigma, P.DELTA)
        assert abs(u.sum() - 1.0) < 1e-12
        if ((u >= P.LOWER - 1e-9) & (u <= P.UPPER + 1e-9)).all():
            assert np.abs(u - w).max() < 1e-9
            checked += 1
    assert checked > 0, "no unconstrained case was exercised"


# ------------------------------------------------------------------------------------- 1x and 0x, as pre-declared
def test_1x_reproduces_the_archived_results_for_every_approach(rep):
    tol = json.loads(PREREG.read_text())["policies"]["reproduction_tolerance"]["lambda_1_vs_archived"]
    for s in COMPUTED:
        r = rep["approaches"][s]["reproduction_of_1x"]
        assert r["within_tolerance"] is True, (s, r)
        assert r["tolerance"] == tol
        for k, v in r.items():
            if k.startswith("max_abs"):
                assert v <= tol, (s, k, v)


def test_0x_is_a_legitimate_signal_neutral_configuration(rep, traces):
    for s in ("AP1", "AP2A"):
        a = ASSETS[s]
        g = part(traces[s], "0x")
        pi = g[[f"pi_{x}" for x in a]].to_numpy(float)
        assert np.abs(g[[f"q_adj_{x}" for x in a]].to_numpy(float) - pi).max() < 1e-15
    assert float(np.abs(part(traces["AP2B"], "0x")["weighted_offset"]).max()) == 0.0
    z = rep["approaches"]["AP1"]["zero_scenario_checks"]
    assert z["mu_bl_equals_pi_max_abs"] < 1e-15           # no incremental information reaches the optimizer


def test_0x_is_compared_with_the_native_control_rather_than_assumed_equal(rep):
    """JEV and the Committee land exactly on their 60/40 control; the Deterministic model does not, and says why."""
    for s in ("AP2B", "AP2A"):
        z = rep["approaches"][s]["zero_scenario_checks"]
        assert z["equals_native_neutral"] is True
        assert z["max_abs_weight_difference_vs_native_neutral"] < 1e-9
    z = rep["approaches"]["AP1"]["zero_scenario_checks"]["vs_native_neutral_static_weights"]
    assert z["max_abs_weight_difference"] > 1e-6          # a real difference, not noise
    assert "Sigma_post" in z["why"] and "45/35/20" in z["why"]
    assert "histmean" in json.dumps(rep["approaches"]["AP1"]["zero_scenario_checks"])


# ------------------------------------------------------------------------------- constraints, timing, accounting
def test_the_native_position_limits_hold_in_every_scenario(rep, traces):
    for s in COMPUTED:
        bounds = rep["approaches"][s]["allocator"]["bounds"]
        assert bounds, s
        for sc in SCEN:
            g = part(traces[s], sc)
            for a, (lo, hi) in bounds.items():
                assert (g[f"w_{a}"] >= lo - 1e-9).all() and (g[f"w_{a}"] <= hi + 1e-9).all(), (s, sc, a)
            assert np.allclose(g[[f"w_{a}" for a in ASSETS[s]]].sum(axis=1), 1.0, atol=1e-12), (s, sc)


def test_binding_constraints_are_recorded_not_hidden(rep, traces):
    for s in COMPUTED:
        for sc in SCEN:
            g = part(traces[s], sc)
            pub = rep["approaches"][s]["transmission"]["per_scenario_vs_1x"][sc]
            assert int((g["n_bounds_binding"] > 0).sum()) == pub["months_with_any_binding_bound"]
            assert pub["share_of_months_with_any_binding_bound"] == pytest.approx(float((g["n_bounds_binding"] > 0).mean()))


def test_no_decision_can_see_a_realised_return(traces, rep):
    outcome = {"r_spy", "r_tlt", "actual_excess_return", "next", "gross_total_return", "net_total_return", "realised"}
    for s in COMPUTED:
        assert not (set(traces[s].columns) & outcome), s
    for s in ("AP2B", "AP2A"):
        removed = rep["approaches"][s]["allocator"]
        assert removed  # the harness records which outcome fields it deletes before calling decide()
    raw = json.loads((OUT / "ap2b_native_scenarios.json").read_text())
    assert set(raw["outcome_fields_removed_before_decide"]) == {"r_spy", "r_tlt", "next"}


def test_the_accounting_and_costs_are_consistent_in_every_scenario(returns, rep):
    cost = rep["accounting"]["cost_per_dollar_traded"]
    for s in COMPUTED:
        a = ASSETS[s]
        for sc in SCEN:
            g = part(returns[s], sc)
            assert len(g) == rep["window"]["n_months"]
            assert np.allclose(g["cost"], cost * g["traded_notional"], atol=1e-15), (s, sc)
            assert np.allclose(g["one_way_turnover"], 0.5 * g["traded_notional"], atol=1e-15)
            assert np.allclose(g["net_excess_return"], g["gross_excess_return"] - g["cost"], atol=1e-15)
            assert np.allclose(g["net_total_return"], g["gross_total_return"] - g["cost"], atol=1e-15)
            assert np.allclose(g["gross_excess_return"], g["gross_total_return"] - g["rf_return"], atol=1e-15)
            first = g.iloc[0]
            assert np.allclose([first[f"pretrade_w_{x}"] for x in a], 0.0)      # starts from cash
            assert first["traded_notional"] == pytest.approx(1.0)


def test_the_protected_window_is_never_touched(rep):
    start = rep["window"]["protected_window_start"]
    assert rep["window"]["development"][1] < start
    assert rep["window"]["protected_window_touched"] is False
    for s in COMPUTED:
        for f in (f"{s.lower()}_scenario_returns.csv", f"{s.lower()}_transmission_trace.csv"):
            m = pd.read_csv(OUT / f)["decision_month"].astype(str)
            assert (m < start).all(), f


# --------------------------------------------------------------------------------- the pipelines stay distinct
def test_each_approach_keeps_its_own_native_pipeline(rep):
    a1 = rep["approaches"]["AP1"]["allocator"]
    jev = rep["approaches"]["AP2B"]["allocator"]
    cmte = rep["approaches"]["AP2A"]["allocator"]
    assert "stage2_portfolio.py" in a1["entry_point"] and "bl_posterior" in a1["entry_point"]
    assert "livebacktest.js" in jev["entry_point"] and "baseEdge" in jev["entry_point"]
    assert "allocation.js" in cmte["entry_point"]
    assert "Black-Litterman" not in jev["kind"], "JEV must not be routed through the Deterministic allocator"
    assert jev["entry_point"] != a1["entry_point"] != cmte["entry_point"]
    assert list(rep["approaches"]["AP1"]["universe"]) == ["SPY", "IEF", "LQD"]
    assert list(rep["approaches"]["AP2B"]["universe"]) == ["SPY", "TLT"]
    assert rep["approaches"]["AP2B"]["native_neutral_weights"] == {"SPY": 0.6, "TLT": 0.4}
    assert rep["approaches"]["AP1"]["native_neutral_weights"] == {"SPY": 0.45, "IEF": 0.35, "LQD": 0.2}
    mech = rep["cross_approach"]["mechanisms_examined"]
    assert "not_attributable_to_Black_Litterman_alone" in mech
    assert "capped tilt" in mech["not_attributable_to_Black_Litterman_alone"]


def test_causal_rag_is_never_reported_as_validated(rep):
    """Causal RAG may be computed once genuine outputs exist, but only as a labelled exploratory diagnostic."""
    a3 = rep["approaches"]["AP3"]
    if "performance" not in a3:                       # still pending
        assert a3["status"] == "PENDING GENUINE AGENT OUTPUTS"
        assert "transmission" not in a3 and a3["blockers"]
        assert "EXPLORATORY" in a3["designation_if_run_on_current_outputs"]
        assert "categor" in a3["explicit_prohibition"].lower()
        return
    assert "EXPLORATORY" in a3["status"] and a3["designation"].startswith("EXPLORATORY")
    assert a3["validated"] is False
    assert a3["gates_failed"], "it is exploratory precisely because a gate failed"
    assert all(v is False for v in a3["gates"].values()), "the gate outcomes are unchanged"
    assert "never scaled" in a3["categorical_note"], "the categories are never treated as magnitudes"
    assert a3["agent_months"] == 95
    # the scaling happened at its own native entry point, not through another approach's allocator
    assert "ap3/allocation.py" in a3["allocator"]["entry_point"]
    assert a3["reproduction_of_1x"]["within_tolerance"] is True
    for s in COMPUTED:
        assert rep["approaches"][s]["status"] == "computed"


def test_no_scenario_result_is_called_statistically_clear_without_an_interval_that_excludes_zero(rep):
    for s in COMPUTED:
        for name, v in rep["approaches"][s]["statistics"].items():
            if name.startswith("_"):
                continue
            excludes = v["ci95"][0] > 0 or v["ci95"][1] < 0
            if v["p_two_sided_bootstrap"] < 0.05:
                assert excludes or abs(v["point"]) < 1e-12, (s, name, v)


def test_the_stronger_scenario_is_labelled_a_stress_test(rep):
    assert "2x" in rep["scenarios"] and "Stronger" in rep["scenarios"]["2x"]
    joined = " ".join(rep["limitations"])
    assert "stress test" in joined and "not a recommendation" in joined
    assert "transmission" in joined and "predictive quality" in joined


def test_frozen_artifacts_and_earlier_results_are_unchanged():
    from native_backtest.scripts import release_manifest as R
    assert R.check() == [], "run: python -m native_backtest.scripts.release_manifest"
    earlier = ROOT / "native_backtest/out/signal_value/signal_value_added.json"
    if earlier.exists():
        d = json.loads(earlier.read_text())
        assert d, "the Signal Value-Added results must still be readable and untouched"


def test_the_independent_audit_passes():
    f = OUT / "audit_forecast_to_allocation.json"
    if not f.exists():
        pytest.skip("run python -m native_backtest.scripts.audit_forecast_to_allocation")
    a = json.loads(f.read_text())
    assert a["n_failed"] == 0, a["failed"][:5]
    assert a["n_checks"] > 300
    assert a["imports"] == ["numpy", "pandas"]
