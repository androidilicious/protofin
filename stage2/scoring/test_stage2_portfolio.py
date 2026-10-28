import numpy as np
import pandas as pd
import pytest
from scipy.optimize import minimize

import stage2_portfolio as p


def test_frozen_constants():
    assert p.TAU == 0.05 and p.DELTA == 2.5 and p.CER_DELTA == 2.5
    assert np.allclose(p.PRIOR_WEIGHTS, [0.45, 0.35, 0.20])
    assert np.allclose(p.LOWER, [0.20, 0.15, 0.10]) and np.allclose(p.UPPER, [0.70, 0.60, 0.40])
    assert p.COV_WINDOW == 36 and p.COST_PER_DOLLAR == 0.0005


def test_ledoit_wolf_is_convex_combination_of_sample_cov_and_scaled_identity():
    rng = np.random.default_rng(0)
    x = rng.normal(size=(36, 3)) @ np.array([[1.0, 0.3, 0.2], [0.0, 0.5, 0.1], [0.0, 0.0, 0.4]]) * 0.02
    lw = p.ledoit_wolf_cov(x)
    s = np.cov(x, rowvar=False, ddof=0)
    mu = np.trace(s) / 3
    off = ~np.eye(3, dtype=bool)
    shrink = 1 - lw[off] / s[off]
    assert np.allclose(shrink, shrink[0])  # one common shrinkage intensity
    assert 0 <= shrink[0] <= 1
    assert np.allclose(lw, (1 - shrink[0]) * s + shrink[0] * mu * np.eye(3))


def test_bl_posterior_limits():
    sigma = np.diag([0.002, 0.0004, 0.0006])
    q = np.array([0.01, -0.002, 0.003])
    pi, mu_vague, _ = p.bl_posterior(sigma, q, np.full(3, 1e6))
    assert np.allclose(mu_vague, pi, atol=1e-9)
    _, mu_sharp, _ = p.bl_posterior(sigma, q, np.full(3, 1e-12))
    assert np.allclose(mu_sharp, q, atol=1e-8)
    _, _, post = p.bl_posterior(sigma, q, np.full(3, 1e-4))
    assert np.allclose(post, post.T)


def test_optimizer_matches_scipy_and_respects_constraints():
    rng = np.random.default_rng(1)
    for _ in range(200):
        a = rng.normal(size=(3, 3)) * 0.03
        sigma = a @ a.T + np.eye(3) * 1e-4
        mu = rng.normal(scale=0.01, size=3)
        w = p.optimal_weights(mu, sigma)
        assert abs(w.sum() - 1) < 1e-12
        assert (w >= p.LOWER - 1e-12).all() and (w <= p.UPPER + 1e-12).all()
        obj = lambda v: -(v @ mu - 0.5 * p.DELTA * v @ sigma @ v)
        res = minimize(obj, p.PRIOR_WEIGHTS, method="SLSQP", bounds=list(zip(p.LOWER, p.UPPER)),
                       constraints=[{"type": "eq", "fun": lambda v: v.sum() - 1}], options={"ftol": 1e-15, "maxiter": 500})
        assert -obj(w) >= -res.fun - 1e-12


def test_simulation_drift_and_costs():
    months = ["2020-01", "2020-02"]
    w = {m: np.array([0.5, 0.3, 0.2]) for m in months}
    r = {"2020-01": np.array([0.10, 0.0, 0.0]), "2020-02": np.array([0.0, 0.0, 0.0])}
    sim = p.simulate(w, months, r, {"2020-01": 0.001, "2020-02": 0.001})
    assert sim.loc[0, "traded_notional"] == pytest.approx(1.0)  # starts from cash
    assert sim.loc[0, "cost"] == pytest.approx(0.0005)
    assert sim.loc[0, "net_excess_return"] == pytest.approx(0.05 - 0.001 - 0.0005)
    drifted = np.array([0.55, 0.3, 0.2]) / 1.05
    assert sim.loc[1, "traded_notional"] == pytest.approx(np.abs(w["2020-02"] - drifted).sum())
    assert sim.loc[1, "one_way_turnover"] == pytest.approx(0.5 * np.abs(w["2020-02"] - drifted).sum())


def test_metric_formulas():
    x = np.array([0.01, -0.02, 0.03, 0.00])
    assert p.cer(x) == pytest.approx(12 * (x.mean() - 1.25 * x.var(ddof=1)))
    # wealth 1.00 -> 1.10 -> 0.88 -> 0.924; peak-to-trough = 0.88 / 1.10 - 1
    assert p.max_drawdown([0.10, -0.20, 0.05]) == pytest.approx(0.88 / 1.10 - 1.0)


def test_break_even_cost_equalises_cer():
    a = pd.DataFrame({"gross_excess_return": [0.02, 0.01, 0.015, -0.005], "traded_notional": [1.0, 0.5, 0.5, 0.5]})
    b = pd.DataFrame({"gross_excess_return": [0.01, 0.005, 0.01, -0.006], "traded_notional": [1.0, 0.0, 0.0, 0.0]})
    out = p.break_even_cost(a, b)
    assert out["status"] == "defined"
    c = out["break_even_cost_per_dollar"]
    assert p._cer_at_cost(a, c) == pytest.approx(p._cer_at_cost(b, c), abs=1e-10)
    assert p.break_even_cost(b, a)["status"].startswith("not defined")
