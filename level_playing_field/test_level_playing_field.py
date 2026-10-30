"""python -m pytest -q level_playing_field"""
import numpy as np
import pandas as pd

from level_playing_field.run import allocate, view_and_omega

MONTHS = pd.period_range("2015-02", "2019-03", freq="M")


def _data(seed=0):
    rng = np.random.default_rng(seed)
    y = pd.Series(rng.normal(0.006, 0.04, len(MONTHS)), index=MONTHS)
    X = pd.DataFrame(rng.normal(size=(len(MONTHS), 3)), index=MONTHS, columns=list("abc"))
    return X, y


def test_view_uses_only_labels_through_t_minus_2():
    X, y = _data()
    dm = pd.Period("2019-03", "M")
    base = view_and_omega(X, y, dm, MONTHS[0])
    y2 = y.copy()
    y2[dm - 1] = 9.9   # an unfinished label (t-1) and the outcome month itself must not matter
    y2[dm] = -9.9
    assert view_and_omega(X, y2, dm, MONTHS[0])[:2] == base[:2]
    assert base[3] == 48   # Feb 2015 .. Jan 2019


def test_placebo_is_the_historical_average():
    X, y = _data()
    dm = pd.Period("2019-03", "M")
    q, omega, alpha, n = view_and_omega(None, y, dm, MONTHS[0])
    assert alpha == "INTERCEPT_ONLY" and np.isclose(q, y.loc[MONTHS[0]:dm - 2].mean()) and omega > 0


def test_weights_sum_to_one_and_respect_bounds():
    sigma = np.array([[0.0012, -0.0003], [-0.0003, 0.0010]])
    prior = np.array([0.6, 0.4])
    lo, hi = prior - 0.2, prior + 0.2
    for q in ([0.05, -0.05], [-0.05, 0.05], [0.0, 0.0]):
        w, pi, mu = allocate(sigma, np.array(q), np.array([1e-6, 1e-6]), prior, lo, hi, 2.5, 0.05)
        assert np.isclose(w.sum(), 1.0) and (w >= lo - 1e-12).all() and (w <= hi + 1e-12).all()
    assert np.allclose(pi, 2.5 * sigma @ prior)


def test_sign_mapping_never_inverts_the_stated_direction():
    X, y = _data()
    dm = pd.Period("2019-03", "M")
    # a signal that is reliably WRONG: stated view moves opposite to the next-month return
    stated = -y.shift(0) + 0.0   # same month as the label it tries to predict, flipped
    X.attrs["stated"] = {"SPY": stated}
    q, omega, k, n = view_and_omega(X, y, dm, MONTHS[0], "SPY", "sign")
    assert k == "k=0" and np.isclose(q, y.loc[MONTHS[0]:dm - 2].mean())   # collapses to the placebo
    # a signal that is reliably RIGHT keeps its direction and scales up
    X.attrs["stated"] = {"SPY": y + 0.0}
    q2, _, k2, _ = view_and_omega(X, y, dm, MONTHS[0], "SPY", "sign")
    assert float(k2[2:]) > 0 and (q2 - y.loc[MONTHS[0]:dm - 2].mean()) * (y[dm] - y.loc[MONTHS[0]:dm - 2].mean()) > 0
