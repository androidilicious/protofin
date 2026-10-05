"""Stochastic views and empirical view uncertainty (stochastic_views.py, allocation.view_omega)."""
import json
import statistics

import numpy as np
import pytest

import stochastic_views as sv
from allocation import OMEGA_SCALE, TAU, allocate, bl_posterior, equilibrium_prior, view_omega

# covariance from the 22 Sep 2026 run in docs/HOW_IT_WORKS.md
SIGMA = np.array([[0.01688, 0.00312], [0.00312, 0.00841]])
RF = 4.0


def runs(spy, tlt, conf="High"):
    confs = conf if isinstance(conf, list) else [conf] * len(spy)
    return [{"run": i, "seed": None, "valid": True, "problems": [], "spy_q": s, "tlt_q": t, "confidence": c}
            for i, (s, t, c) in enumerate(zip(spy, tlt, confs))]


SPY_RUNS = [5.8, 6.1, 5.9, 6.3, 5.7]
TLT_RUNS = [2.5, 2.4, 2.6, 2.5, 2.5]


# ------------------------------------------------------------------ 1-2. statistics
def test_mean_q():
    agg = sv.aggregate_views(runs(SPY_RUNS, TLT_RUNS))
    assert agg["assets"]["SPY"]["mean"] == pytest.approx(5.96)
    assert agg["assets"]["TLT"]["mean"] == pytest.approx(2.5)


def test_variance_std_min_max():
    agg = sv.aggregate_views(runs(SPY_RUNS, TLT_RUNS))
    spy = agg["assets"]["SPY"]
    assert spy["var"] == pytest.approx(statistics.variance(SPY_RUNS))    # sample variance, ddof = 1
    assert spy["std"] == pytest.approx(statistics.stdev(SPY_RUNS))
    assert (spy["min"], spy["max"]) == (5.7, 6.3)
    # Omega input is decimal^2: percent^2 / 1e4
    assert agg["empirical_var"][0] == pytest.approx(statistics.variance(SPY_RUNS) / 1e4)


def test_invalid_runs_are_excluded():
    rs = runs(SPY_RUNS, TLT_RUNS)
    rs.append({"run": 5, "seed": None, "valid": False, "problems": ["spy_q missing"],
               "spy_q": None, "tlt_q": 2.0, "confidence": "High"})
    agg = sv.aggregate_views(rs)
    assert (agg["n_runs"], agg["n_valid"]) == (6, 5)
    assert agg["assets"]["SPY"]["mean"] == pytest.approx(5.96)
    assert agg["invalid_runs"] == [{"run": 5, "problems": ["spy_q missing"]}]


# ------------------------------------------------------------------ 3-4. dispersion
def test_identical_views_give_zero_empirical_uncertainty():
    out = sv.decide_from_runs(SIGMA, runs([6.0] * 5, [2.5] * 5), RF, "combined")
    assert out["empirical_var"] == pytest.approx([0.0, 0.0], abs=1e-15)
    assert out["stability"]["SPY"]["dispersion_ratio"] == pytest.approx(0.0, abs=1e-12)
    # Omega collapses to the reported-confidence Omega, never to a singular matrix
    np.testing.assert_allclose(out["omega"], view_omega(SIGMA, "High"), atol=1e-15)
    assert np.all(np.isfinite(out["decision"]["er"]))


def test_dispersed_views_give_higher_empirical_uncertainty():
    tight = sv.aggregate_views(runs(SPY_RUNS, TLT_RUNS))
    wide = sv.aggregate_views(runs([1.0, 9.0, 3.0, 11.0, 5.8], [-3.0, 6.0, 2.5, 0.0, 7.0]))
    assert wide["empirical_var"][0] > tight["empirical_var"][0]
    assert wide["empirical_var"][1] > tight["empirical_var"][1]


def test_zero_variance_does_not_make_omega_singular():
    omega = view_omega(SIGMA, "High", empirical_var=[0.0, 0.0])
    assert np.linalg.cond(omega) < 1e6
    with pytest.raises(ValueError):
        view_omega(SIGMA, "High", empirical_var=[-1e-6, 0.0])
    with pytest.raises(ValueError):
        view_omega(SIGMA, "High", empirical_var=[np.nan, 0.0])


# ------------------------------------------------------------------ 5. influence in Black-Litterman
@pytest.mark.parametrize("conf", ["High", "Medium", "Low"])
def test_more_dispersion_means_less_view_influence(conf):
    pi = equilibrium_prior(SIGMA)
    q = np.array([0.08, -0.03])                       # far from the prior on both assets
    pulls = []
    for var in (0.0, 1e-4, 1e-3, 1e-2):
        er = bl_posterior(pi, SIGMA, q, conf, empirical_var=[var, var])
        pulls.append(np.abs(er - pi))                 # how far the view moved the prior
    for a, b in zip(pulls, pulls[1:]):
        assert np.all(b < a)
    # in the limit of huge dispersion the posterior returns to the prior
    er = bl_posterior(pi, SIGMA, q, conf, empirical_var=[1e6, 1e6])
    np.testing.assert_allclose(er, pi, atol=1e-6)


# ------------------------------------------------------------------ 6. reported confidence unchanged
@pytest.mark.parametrize("conf,view_weight", [("High", 2 / 3), ("Medium", 1 / 2), ("Low", 1 / 3)])
def test_reported_confidence_behaviour_unchanged(conf, view_weight):
    pi = equilibrium_prior(SIGMA)
    q = np.array([0.01, -0.015])
    er = bl_posterior(pi, SIGMA, q, conf)
    # Omega = c tau Sigma with P = I: posterior is a 1/(1+c) weighted average of view and prior
    np.testing.assert_allclose(er, view_weight * q + (1 - view_weight) * pi, atol=1e-14)
    np.testing.assert_allclose(view_omega(SIGMA, conf), OMEGA_SCALE[conf] * TAU * SIGMA)
    # empirical_var=None and the old call signature give identical results
    old = allocate(SIGMA, [5.0, 2.5], conf, RF, None)
    new = allocate(SIGMA, [5.0, 2.5], conf, RF, None, empirical_var=None)
    np.testing.assert_array_equal(old["er"], new["er"])
    assert old["target_spy"] == new["target_spy"]


def test_prior_only_path_unchanged():
    d = allocate(SIGMA, None, "Medium", RF, None)
    assert d["target_spy"] == pytest.approx(0.60)
    assert d["omega"] is None


# ------------------------------------------------------------------ 7. modes
def test_mode_reported_uses_mean_q_and_label_only():
    rs = runs(SPY_RUNS, TLT_RUNS, "High")
    out = sv.decide_from_runs(SIGMA, rs, RF, "reported")
    assert (out["effective_mode"], out["confidence_used"], out["empirical_var"]) == ("reported", "High", None)
    ref = allocate(SIGMA, [5.96, 2.5], "High", RF, None)
    np.testing.assert_allclose(out["decision"]["er"], ref["er"])


def test_mode_empirical_ignores_self_report():
    hi = sv.decide_from_runs(SIGMA, runs(SPY_RUNS, TLT_RUNS, "High"), RF, "empirical")
    lo = sv.decide_from_runs(SIGMA, runs(SPY_RUNS, TLT_RUNS, "Low"), RF, "empirical")
    assert hi["confidence_used"] == lo["confidence_used"] == "Medium"
    np.testing.assert_allclose(hi["decision"]["er"], lo["decision"]["er"])
    ev = hi["aggregate"]["empirical_var"]
    np.testing.assert_allclose(hi["omega"], TAU * SIGMA + np.diag(ev))


def test_mode_combined_uses_both_signals():
    out = sv.decide_from_runs(SIGMA, runs(SPY_RUNS, TLT_RUNS, "High"), RF, "combined")
    ev = out["aggregate"]["empirical_var"]
    assert out["confidence_used"] == "High"
    np.testing.assert_allclose(out["omega"], 0.5 * TAU * SIGMA + np.diag(ev))
    rep = sv.decide_from_runs(SIGMA, runs(SPY_RUNS, TLT_RUNS, "High"), RF, "reported")
    # The extra term pulls the allocation tilt back toward the prior's 60/40. With correlated Sigma and
    # uneven dispersion, individual posterior components need not each move toward the prior
    # (here SPY's does not); the SPY-TLT spread that sets the weight does.
    tilt = lambda d: abs(d["unconstrained"][0] - 0.6)   # before the 40-80% band clips both to 80%
    assert tilt(out["decision"]) < tilt(rep["decision"])
    spread = lambda er: er[0] - er[1]
    pi = equilibrium_prior(SIGMA)
    assert abs(spread(out["decision"]["er"]) - spread(pi)) < abs(spread(rep["decision"]["er"]) - spread(pi))
    # and the posterior uncertainty of the mean, [(tau Sigma)^-1 + Omega^-1]^-1, grows (Loewner order)
    post_cov = lambda om: np.linalg.inv(np.linalg.inv(TAU * SIGMA) + np.linalg.inv(np.array(om)))
    assert np.all(np.linalg.eigvalsh(post_cov(out["omega"]) - post_cov(rep["omega"])) >= -1e-15)


def test_regime_gate_applies_in_every_mode():
    rs = runs(SPY_RUNS, TLT_RUNS, "High")
    assert sv.decide_from_runs(SIGMA, rs, RF, "reported", regime="elevated")["confidence_used"] == "Medium"
    assert sv.decide_from_runs(SIGMA, rs, RF, "combined", regime="elevated")["confidence_used"] == "Medium"
    assert sv.decide_from_runs(SIGMA, rs, RF, "empirical", regime="elevated")["confidence_used"] == "Low"


def test_empirical_modes_fall_back_with_fewer_than_two_valid_runs():
    rs = runs([6.0], [2.5], "High")
    for mode in ("empirical", "combined"):
        out = sv.decide_from_runs(SIGMA, rs, RF, mode)
        assert out["effective_mode"] == "reported" and out["empirical_var"] is None
        assert "fell back" in out["note"]


def test_no_valid_runs_uses_prior_only():
    bad = [{"run": 0, "seed": None, "valid": False, "problems": ["spy_q missing"],
            "spy_q": None, "tlt_q": None, "confidence": None}] * 3
    out = sv.decide_from_runs(SIGMA, bad, RF, "combined")
    assert out["effective_mode"] == "prior_only"
    assert out["decision"]["target_spy"] == pytest.approx(0.60)


def test_unknown_mode_rejected():
    with pytest.raises(ValueError):
        sv.decide_from_runs(SIGMA, runs(SPY_RUNS, TLT_RUNS), RF, "vibes")


def test_modal_confidence_ties_go_to_lower():
    assert sv.modal_confidence(["High", "High", "Low", "Low", "Medium"])[0] == "Low"
    assert sv.modal_confidence(["High", "High", "Medium"])[0] == "High"


# ------------------------------------------------------------------ config, runner, audit record
def test_config_defaults_and_validation():
    cfg = sv.config_from_env({})
    assert (cfg.enabled, cfg.temperature, cfg.n_runs, cfg.seed, cfg.confidence_mode) == (False, 0.2, 5, None, "combined")
    cfg = sv.config_from_env({"STOCHASTIC_VIEWS": "1", "VIEW_TEMPERATURE": "0.7", "VIEW_N_RUNS": "8",
                              "VIEW_SEED": "100", "CONFIDENCE_MODE": "empirical"})
    assert (cfg.enabled, cfg.temperature, cfg.n_runs, cfg.run_seed(3), cfg.confidence_mode) == (True, 0.7, 8, 103, "empirical")
    assert sv.with_overrides(cfg, {"stochastic": "0", "n_runs": "3"}).n_runs == 3
    for bad in ({"n_runs": 1}, {"confidence_mode": "x"}, {"temperature": -0.1}):
        with pytest.raises(ValueError):
            sv.StochasticConfig(**bad)


def _reply(spy, tlt, conf):
    return (f"CIO_Decision: test.\nGrounding_Summary: test.\nSPY_Expected_Return_Percent: {spy}\n"
            f"TLT_Expected_Return_Percent: {tlt}\nCIO_Confidence: {conf}\n")


def test_runner_freezes_input_and_varies_only_sampling():
    prompts = {"economist": "E", "risk": "R", "cio": "C {ECONOMIST_VIEW} {RISK_VIEW}"}
    seen, cio_replies = [], iter([_reply(5.8, 2.5, "High"), _reply(6.2, 2.3, "Medium"), _reply(6.0, 2.7, "High")])

    def call(prompt, temperature, seed):
        seen.append((prompt[0], temperature, seed))
        return next(cio_replies) if prompt.startswith("C") else "Economist_View: x\nEconomist_SPY_Return_Percent: 6\nEconomist_TLT_Return_Percent: 2"

    cfg = sv.StochasticConfig(enabled=True, temperature=0.4, n_runs=3, seed=10)
    out = sv.run_stochastic_committee(prompts, call, cfg, parallel=False)
    assert len(out) == 3 and all(t == 0.4 for _, t, _ in seen)
    assert sorted({s for _, _, s in seen}) == [10, 11, 12]
    assert len({o["cio_prompt"] for o in out}) == 1               # identical input every run
    rv = [sv.run_view(o) for o in out]
    agg = sv.aggregate_views(rv)
    assert agg["assets"]["SPY"]["values"] == [5.8, 6.2, 6.0]
    assert agg["confidence_counts"] == {"Low": 0, "Medium": 1, "High": 2}

    res = sv.decide_from_runs(SIGMA, rv, RF, "combined")
    rec = sv.evaluation_record(cfg, "gpt-test", sv.snapshot_id(prompts), rv, res, fingerprint="fp")
    rec = json.loads(json.dumps(rec))                                # fully serialisable
    for key in ("model", "config", "snapshot_id", "runs", "q_mean_pct", "empirical_var", "omega", "timestamp"):
        assert rec[key] is not None
    assert rec["config"]["temperature"] == 0.4 and rec["config"]["n_runs"] == 3
    assert [r["confidence"] for r in rec["runs"]] == ["High", "Medium", "High"]
    assert len(rec["per_run_target_spy"]) == 3


def test_snapshot_id_depends_only_on_input():
    a = {"economist": "E", "risk": "R", "cio": "C"}
    assert sv.snapshot_id(a) == sv.snapshot_id(dict(reversed(list(a.items()))))
    assert sv.snapshot_id(a) != sv.snapshot_id({**a, "cio": "C2"})
