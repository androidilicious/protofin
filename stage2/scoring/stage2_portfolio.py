"""Frozen Stage-2 Black–Litterman portfolio layer (secondary evidence).

Implements Freeze v2 §8–10 with the open details fixed in
stage2/methodology/Stage2_Portfolio_Conventions_v1.md. Every frozen value below
is a constant; nothing here is tuned.
"""
from __future__ import annotations

import itertools
import json
import math
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from scipy.optimize import brentq
from sklearn.covariance import LedoitWolf

ASSETS: Tuple[str, ...] = ("SPY", "IEF", "LQD")

# Frozen allocator constants (Freeze v2 §8).
TAU = 0.05
DELTA = 2.5
PRIOR_WEIGHTS = np.array([0.45, 0.35, 0.20])
LOWER = np.array([0.20, 0.15, 0.10])
UPPER = np.array([0.70, 0.60, 0.40])
COV_WINDOW = 36
COST_PER_DOLLAR = 0.0005
CER_DELTA = 2.5

BENCH_HISTMEAN = "BENCH_HISTMEAN_ALLOCATOR"
BENCH_STATIC = "BENCH_STATIC_45_35_20"
_BOUND_TOL = 1e-12


class PortfolioError(RuntimeError):
    pass


# -----------------------------------------------------------------------------
# Estimation
# -----------------------------------------------------------------------------


def ledoit_wolf_cov(returns: np.ndarray) -> np.ndarray:
    """Ledoit–Wolf (2004) shrinkage covariance, sample mean removed (convention 1)."""
    x = np.asarray(returns, dtype=float)
    if x.ndim != 2 or x.shape[1] != len(ASSETS) or not np.isfinite(x).all():
        raise PortfolioError(f"Covariance input must be finite T x {len(ASSETS)}")
    return LedoitWolf(assume_centered=False).fit(x).covariance_


def omega_from_errors(errors_by_asset: Mapping[str, Sequence[float]]) -> np.ndarray:
    """Diagonal Ω: sample variance (ddof=1) of A's development OOS errors (convention 3)."""
    diag = []
    for a in ASSETS:
        e = np.asarray(errors_by_asset[a], dtype=float)
        if len(e) < 2 or not np.isfinite(e).all():
            raise PortfolioError(f"Need finite errors for {a} to estimate Omega")
        diag.append(float(np.var(e, ddof=1)))
    return np.array(diag)


def bl_posterior(sigma: np.ndarray, q: np.ndarray, omega_diag: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (pi, mu_BL, Sigma_BL) with P = I (conventions 2 and 4)."""
    sigma = np.asarray(sigma, dtype=float)
    q = np.asarray(q, dtype=float)
    pi = DELTA * sigma @ PRIOR_WEIGHTS
    ts_inv = np.linalg.inv(TAU * sigma)
    om_inv = np.diag(1.0 / np.asarray(omega_diag, dtype=float))
    m = np.linalg.inv(ts_inv + om_inv)
    mu = m @ (ts_inv @ pi + om_inv @ q)
    return pi, mu, sigma + m


def optimal_weights(mu: np.ndarray, sigma: np.ndarray) -> np.ndarray:
    """Exact bounded, fully invested mean-variance optimum (convention 5).

    Enumerates which assets sit at their lower or upper bound. For each case the
    remaining weights solve the equality-constrained problem in closed form; the
    best feasible candidate is the global optimum because the objective is strictly
    concave.
    """
    mu = np.asarray(mu, dtype=float)
    sigma = np.asarray(sigma, dtype=float)
    n = len(mu)
    best_w, best_u = None, -math.inf
    for states in itertools.product((0, 1, 2), repeat=n):  # 0 free, 1 lower, 2 upper
        w = np.zeros(n)
        free = [i for i, s in enumerate(states) if s == 0]
        fixed = [i for i, s in enumerate(states) if s != 0]
        for i in fixed:
            w[i] = LOWER[i] if states[i] == 1 else UPPER[i]
        remaining = 1.0 - w[fixed].sum()
        if not free:
            if abs(remaining) > 1e-12:
                continue
        else:
            s_ff = sigma[np.ix_(free, free)]
            b = mu[free] - DELTA * sigma[np.ix_(free, fixed)] @ w[fixed] if fixed else mu[free].copy()
            inv = np.linalg.inv(s_ff)
            ones = np.ones(len(free))
            lam = (ones @ inv @ b - DELTA * remaining) / (ones @ inv @ ones)
            w[free] = inv @ (b - lam * ones) / DELTA
        if (w < LOWER - _BOUND_TOL).any() or (w > UPPER + _BOUND_TOL).any():
            continue
        u = float(w @ mu - 0.5 * DELTA * w @ sigma @ w)
        if u > best_u + 1e-15:
            best_u, best_w = u, w.copy()
    if best_w is None:
        raise PortfolioError("No feasible weights; check bounds")
    best_w = np.clip(best_w, LOWER, UPPER)
    return best_w / best_w.sum()


# -----------------------------------------------------------------------------
# Simulation
# -----------------------------------------------------------------------------


def simulate(
    weights: Mapping[str, np.ndarray],
    months: Sequence[str],
    asset_returns: Mapping[str, np.ndarray],
    rf: Mapping[str, float],
    cost_per_dollar: float = COST_PER_DOLLAR,
) -> pd.DataFrame:
    """Drift-aware rebalancing with costs (conventions 6–8). Starts from cash."""
    pre = np.zeros(len(ASSETS))
    rows = []
    for m in months:
        w = np.asarray(weights[m], dtype=float)
        r = np.asarray(asset_returns[m], dtype=float)
        notional = float(np.abs(w - pre).sum())
        cost = cost_per_dollar * notional
        gross_total = float(w @ r)
        rows.append(
            {
                "decision_month": m,
                **{f"w_{a}": float(w[i]) for i, a in enumerate(ASSETS)},
                **{f"pretrade_w_{a}": float(pre[i]) for i, a in enumerate(ASSETS)},
                "traded_notional": notional,
                "one_way_turnover": 0.5 * notional,
                "cost": cost,
                "rf_return": float(rf[m]),
                "gross_total_return": gross_total,
                "gross_excess_return": gross_total - float(rf[m]),
                "net_total_return": gross_total - cost,
                "net_excess_return": gross_total - float(rf[m]) - cost,
            }
        )
        grown = w * (1.0 + r)
        pre = grown / grown.sum()
    return pd.DataFrame(rows)


# -----------------------------------------------------------------------------
# Metrics (conventions 9–14)
# -----------------------------------------------------------------------------


def cer(net_excess: Sequence[float]) -> float:
    x = np.asarray(net_excess, dtype=float)
    return float(12.0 * (x.mean() - 0.5 * CER_DELTA * x.var(ddof=1)))


def max_drawdown(net_total: Sequence[float]) -> float:
    wealth = np.cumprod(1.0 + np.asarray(net_total, dtype=float))
    wealth = np.concatenate([[1.0], wealth])
    peak = np.maximum.accumulate(wealth)
    return float((wealth / peak - 1.0).min())


def metrics_row(sim: pd.DataFrame) -> Dict[str, float]:
    x = sim["net_excess_return"].to_numpy(float)
    ann_ret = 12.0 * float(x.mean())
    ann_vol = math.sqrt(12.0) * float(x.std(ddof=1))
    turn = float(sim["one_way_turnover"].mean())
    return {
        "n_months": len(sim),
        "net_annualized_excess_return": ann_ret,
        "annualized_volatility": ann_vol,
        "net_sharpe": ann_ret / ann_vol if ann_vol > 0 else float("nan"),
        "max_drawdown": max_drawdown(sim["net_total_return"]),
        "cer_delta_2_5": cer(x),
        "mean_one_way_turnover_per_rebalance": turn,
        "annualized_one_way_turnover": 12.0 * turn,
        "total_cost": float(sim["cost"].sum()),
    }


def _cer_at_cost(sim: pd.DataFrame, c: float) -> float:
    return cer(sim["gross_excess_return"].to_numpy(float) - c * sim["traded_notional"].to_numpy(float))


def break_even_cost(sim: pd.DataFrame, comparator: pd.DataFrame) -> Dict[str, Any]:
    """Cost per dollar traded at which the two net CERs are equal (convention 14)."""
    f = lambda c: _cer_at_cost(sim, c) - _cer_at_cost(comparator, c)
    gap0 = f(0.0)
    if gap0 <= 0:
        return {"break_even_cost_per_dollar": None, "status": "not defined: no CER gain at zero cost", "cer_gap_at_zero_cost": gap0}
    if f(1.0) > 0:
        return {"break_even_cost_per_dollar": None, "status": "above 100% per dollar traded", "cer_gap_at_zero_cost": gap0}
    c = brentq(f, 0.0, 1.0, xtol=1e-12)
    return {"break_even_cost_per_dollar": c, "break_even_cost_bps": 1e4 * c, "status": "defined", "cer_gap_at_zero_cost": gap0}


# -----------------------------------------------------------------------------
# Orchestration
# -----------------------------------------------------------------------------


def run_portfolio_layer(
    predictions: pd.DataFrame,
    targets: pd.DataFrame,
    systems: Sequence[str],
    score_months: Sequence[Any],
    omega_diag: np.ndarray,
    macro_start: Any,
) -> Dict[str, Any]:
    months = [str(m) for m in score_months]
    tg = targets.copy()
    tg["decision_month"] = tg["decision_month"].astype(str)
    labels = tg.pivot(index="decision_month", columns="asset", values="actual_excess_return")[list(ASSETS)].sort_index()
    total = tg.pivot(index="decision_month", columns="asset", values="asset_total_return")[list(ASSETS)]
    rf = tg.drop_duplicates("decision_month").set_index("decision_month")["rf_return"]
    asset_returns = {m: total.loc[m].to_numpy(float) for m in months}

    pidx = pd.PeriodIndex(labels.index, freq="M")
    sigma_by_month: Dict[str, np.ndarray] = {}
    for m in months:
        end = pd.Period(m, freq="M") - 2
        window = labels[(pidx >= pd.Period(str(macro_start), freq="M")) & (pidx <= end)].tail(COV_WINDOW)
        if len(window) < COV_WINDOW:
            raise PortfolioError(f"Only {len(window)} completed labels for the {m} covariance; need {COV_WINDOW}")
        sigma_by_month[m] = ledoit_wolf_cov(window.to_numpy(float))

    def q_for(system: str, col: str) -> Dict[str, np.ndarray]:
        p = predictions[predictions["system"] == system].copy()
        p["decision_month"] = p["decision_month"].astype(str)
        piv = p.pivot(index="decision_month", columns="asset", values=col)[list(ASSETS)]
        return {m: piv.loc[m].to_numpy(float) for m in months}

    strategies: Dict[str, Dict[str, np.ndarray]] = {s: q_for(s, "prediction_excess_return") for s in systems}
    strategies[BENCH_HISTMEAN] = q_for(systems[0], "benchmark_mean_excess_return")

    diag_rows: List[Dict[str, Any]] = []
    sims: Dict[str, pd.DataFrame] = {}
    for name, qs in strategies.items():
        weights = {}
        for m in months:
            pi, mu, sig_post = bl_posterior(sigma_by_month[m], qs[m], omega_diag)
            weights[m] = optimal_weights(mu, sig_post)
            diag_rows.append(
                {"strategy": name, "decision_month": m,
                 **{f"q_{a}": float(qs[m][i]) for i, a in enumerate(ASSETS)},
                 **{f"pi_{a}": float(pi[i]) for i, a in enumerate(ASSETS)},
                 **{f"mu_bl_{a}": float(mu[i]) for i, a in enumerate(ASSETS)},
                 **{f"w_{a}": float(weights[m][i]) for i, a in enumerate(ASSETS)}}
            )
        sims[name] = simulate(weights, months, asset_returns, rf.to_dict())
    sims[BENCH_STATIC] = simulate({m: PRIOR_WEIGHTS for m in months}, months, asset_returns, rf.to_dict())

    metric_rows = []
    for name, sim in sims.items():
        row = {"strategy": name, **metrics_row(sim)}
        comps = [("vs_histmean_allocator", BENCH_HISTMEAN), ("vs_static_45_35_20", BENCH_STATIC)]
        if name in systems and name != "A":
            comps.append(("vs_A", "A"))
        for label, comp in comps:
            if comp == name:
                continue
            be = break_even_cost(sim, sims[comp])
            row[f"break_even_{label}_bps"] = be.get("break_even_cost_bps")
            row[f"break_even_{label}_status"] = be["status"]
        metric_rows.append(row)

    returns = pd.concat([s.assign(strategy=n) for n, s in sims.items()], ignore_index=True)
    return {
        "returns": returns[["strategy"] + [c for c in returns.columns if c != "strategy"]],
        "bl_diagnostics": pd.DataFrame(diag_rows),
        "metrics": pd.DataFrame(metric_rows),
        "omega_diag": {a: float(omega_diag[i]) for i, a in enumerate(ASSETS)},
    }


def write_omega(path, omega_diag: np.ndarray, source: str) -> None:
    payload = {
        "description": "Frozen diagonal Black-Litterman Omega: sample variance (ddof=1) of System A development-period OOS forecast errors.",
        "source": source,
        "omega_diag": {a: float(omega_diag[i]) for i, a in enumerate(ASSETS)},
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")


def read_omega(path) -> np.ndarray:
    with open(path, encoding="utf-8") as f:
        d = json.load(f)["omega_diag"]
    return np.array([float(d[a]) for a in ASSETS])
