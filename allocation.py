"""Allocation math shared by the live server and the backtester.

Everything here is deterministic and free of I/O so the backtest exercises the exact
code path the dashboard uses.
"""
import numpy as np

# ---- Policy constants (fraction of portfolio in SPY; TLT is the remainder) ----
EQUILIBRIUM_SPY = 0.60          # market-equilibrium anchor for the Black-Litterman prior
MIN_SPY, MAX_SPY = 0.40, 0.80   # tilt band: never stray more than 20pp from equilibrium
NO_TRADE_BAND = 0.02            # targets within 2pp of current weights produce no trade
MAX_MOVE = 0.10                 # at most 10pp of reallocation per new-evidence run
DELTA = 2.5                     # risk aversion
TAU = 0.05                      # prior uncertainty scalar (cancels out when P = I)
OMEGA_SCALE = {"High": 0.5, "Medium": 1.0, "Low": 2.0}


def equilibrium_prior(sigma, w_eq=None):
    """Implied excess returns Pi = delta * Sigma * w_eq."""
    if w_eq is None:
        w_eq = np.array([EQUILIBRIUM_SPY, 1.0 - EQUILIBRIUM_SPY])
    return DELTA * sigma @ w_eq


def bl_posterior(pi, sigma, q_excess, confidence="Medium", tau=TAU):
    """Black-Litterman posterior with P = identity (one absolute view per asset).

    q_excess: view vector of EXCESS returns (decimal). Returns posterior excess returns.
    """
    omega = OMEGA_SCALE[confidence] * tau * sigma
    tau_sigma_inv = np.linalg.inv(tau * sigma)
    omega_inv = np.linalg.inv(omega)
    return np.linalg.solve(tau_sigma_inv + omega_inv, tau_sigma_inv @ pi + omega_inv @ q_excess)


def unconstrained_weights(mu, sigma):
    """Raw mean-variance weights (may be negative or leveraged); for transparency only."""
    return np.linalg.solve(DELTA * sigma, mu)


def constrained_spy_weight(mu, sigma, lo=MIN_SPY, hi=MAX_SPY):
    """Exact two-asset optimum of mu'w - DELTA/2 w'Sigma w with w=(x,1-x), x in [lo, hi]."""
    s00, s01, s11 = sigma[0, 0], sigma[0, 1], sigma[1, 1]
    x = ((mu[0] - mu[1]) / DELTA + s11 - s01) / (s00 + s11 - 2.0 * s01)
    return float(np.clip(x, lo, hi))


def apply_trade_policy(target_spy, previous_spy, band=NO_TRADE_BAND, max_move=MAX_MOVE):
    """No-trade band plus per-run move cap. Returns (final_spy, status)."""
    if previous_spy is None:
        return target_spy, "initial allocation"
    diff = target_spy - previous_spy
    if abs(diff) <= band:
        return previous_spy, f"held: target within {band*100:.0f}pp no-trade band"
    move = float(np.sign(diff) * min(abs(diff), max_move))
    capped = abs(diff) > max_move
    status = f"moved {move*100:+.1f}pp" + (f" (capped at {max_move*100:.0f}pp)" if capped else "")
    return previous_spy + move, status


def allocate(sigma, views_total_pct, confidence, rf_pct, previous_spy):
    """Full decision: views (total %, may be None) -> posterior -> constrained target -> policy.

    Returns a dict with every intermediate quantity.
    """
    pi = equilibrium_prior(sigma)
    if views_total_pct is not None:
        q_excess = (np.asarray(views_total_pct, dtype=float) - rf_pct) / 100.0
        er = bl_posterior(pi, sigma, q_excess, confidence)
    else:
        er = pi.copy()
    target = constrained_spy_weight(er, sigma)
    final, status = apply_trade_policy(target, previous_spy)
    return {"pi": pi, "er": er, "unconstrained": unconstrained_weights(er, sigma),
            "target_spy": target, "final_spy": final, "status": status}
