"""Shared performance metrics and paired contrasts.

Single-system metrics reuse stage2_portfolio.metrics_row and cer unchanged. Contrasts between two
systems are differences in net CER on identical months, with a paired circular block bootstrap
(the same block scheme and seed as Stage 2) and Holm adjustment across a family.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Dict, List, Mapping, Sequence

import numpy as np
import pandas as pd

_S2 = Path(__file__).resolve().parents[2] / "stage2" / "scoring"
if str(_S2) not in sys.path:
    sys.path.insert(0, str(_S2))
import stage2_portfolio as s2p  # noqa: E402


def metrics(sim: pd.DataFrame) -> Dict[str, float]:
    return s2p.metrics_row(sim)


def cer(x: Sequence[float], delta: float = 2.5) -> float:
    x = np.asarray(x, dtype=float)
    return float(12.0 * (x.mean() - 0.5 * delta * x.var(ddof=1)))


def _block_indices(T: int, block: int, rng: np.random.Generator) -> np.ndarray:
    nblocks = math.ceil(T / block)
    starts = rng.integers(0, T, size=nblocks)
    idx = [(int(s) + k) % T for s in starts for k in range(block)]
    return np.array(idx[:T], dtype=int)


def paired_cer_contrast(a: pd.DataFrame, b: pd.DataFrame, *, delta: float = 2.5, block: int = 6, reps: int = 5000, seed: int = 20261027) -> Dict:
    """CER(a) - CER(b) on the months both cover, with a paired circular block bootstrap."""
    m = a[["decision_month", "net_excess_return"]].merge(
        b[["decision_month", "net_excess_return"]], on="decision_month", suffixes=("_a", "_b"), validate="one_to_one"
    ).sort_values("decision_month")
    if len(m) != len(a) or len(m) != len(b):
        raise ValueError("contrast systems must cover identical months")
    xa, xb = m["net_excess_return_a"].to_numpy(), m["net_excess_return_b"].to_numpy()
    point = cer(xa, delta) - cer(xb, delta)
    rng = np.random.default_rng(seed)
    draws = np.empty(reps)
    for i in range(reps):
        idx = _block_indices(len(m), block, rng)
        draws[i] = cer(xa[idx], delta) - cer(xb[idx], delta)
    p_two_sided = float(min(1.0, 2.0 * min(np.mean(draws <= 0.0), np.mean(draws >= 0.0))))
    return {
        "cer_difference": point,
        "ci90": [float(np.percentile(draws, 5)), float(np.percentile(draws, 95))],
        "ci95": [float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))],
        "p_two_sided_bootstrap": p_two_sided,
        "n_months": int(len(m)),
        "first_month": str(m["decision_month"].iloc[0]),
        "last_month": str(m["decision_month"].iloc[-1]),
        "block_months": block, "replications": reps, "seed": seed,
    }


def holm(pvalues: Mapping[str, float], alpha: float = 0.05) -> Dict[str, Dict]:
    items = sorted(pvalues.items(), key=lambda kv: kv[1])
    k = len(items)
    out: Dict[str, Dict] = {}
    running = 0.0
    still_rejecting = True
    for i, (name, p) in enumerate(items):
        adj = min(1.0, (k - i) * p)
        running = max(running, adj)
        reject = still_rejecting and p <= alpha / (k - i)
        if not reject:
            still_rejecting = False
        out[name] = {"p": p, "holm_adjusted_p": running, "reject_at_alpha": bool(reject)}
    return out
