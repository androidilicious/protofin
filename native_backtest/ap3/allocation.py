"""AP3 allocation: Black-Litterman with AP3's own Q and Omega, through Stage 2's validated code.

Same conventions as AP1 (stage2_portfolio): prior 45/35/20, tau 0.05, delta 2.5, P = I,
Ledoit-Wolf covariance of the 36 most recent completed excess-return labels (t-37..t-2), exact
bounded optimiser. Omega is the diagonal variance of AP3's OWN development-period forecast errors.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, Mapping, Sequence

import numpy as np
import pandas as pd

_S2 = Path(__file__).resolve().parents[2] / "stage2" / "scoring"
if str(_S2) not in sys.path:
    sys.path.insert(0, str(_S2))
import stage2_portfolio as s2p  # noqa: E402

ASSETS = ("SPY", "IEF", "LQD")


def omega_from_development_errors(pred: pd.DataFrame, labels: pd.DataFrame, dev_months: Sequence[str]) -> np.ndarray:
    errs = {a: [] for a in ASSETS}
    for r in pred[pred["decision_month"].isin(set(dev_months))].itertuples():
        errs[r.asset].append(float(labels.loc[pd.Period(r.decision_month, "M"), r.asset]) - float(r.prediction_excess_return))
    return s2p.omega_from_errors(errs)


def weights_for_months(pred: pd.DataFrame, labels: pd.DataFrame, months: Sequence[str], omega_diag: np.ndarray,
                       macro_start: str = "2015-02") -> Dict[str, Dict[str, float]]:
    piv = pred.pivot(index="decision_month", columns="asset", values="prediction_excess_return")[list(ASSETS)]
    pidx = labels.index
    out = {}
    for m in months:
        end = pd.Period(m, "M") - 2
        window = labels[(pidx >= pd.Period(macro_start, "M")) & (pidx <= end)][list(ASSETS)].tail(s2p.COV_WINDOW)
        if len(window) < s2p.COV_WINDOW:
            raise ValueError(f"only {len(window)} labels for the {m} covariance")
        sigma = s2p.ledoit_wolf_cov(window.to_numpy(float))
        _, mu, sig_post = s2p.bl_posterior(sigma, piv.loc[m].to_numpy(float), omega_diag)
        w = s2p.optimal_weights(mu, sig_post)
        out[m] = {a: float(w[i]) for i, a in enumerate(ASSETS)}
    return out
