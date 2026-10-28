"""AP3's own calibration layer and its reliability checks (gate G4c).

Per asset, a Ridge model maps 11 columns (the 8 macro surprises plus F^S, F^C, F^I) to the
one-month expected excess return, walk-forward with labels through t-2. It reuses Stage 2's
validated estimation code unchanged (fit_scaler, choose_alpha with purged expanding inner CV and
the INTERCEPT_ONLY option, ridge_fit_predict). This is an AP3 component, not a shared setting.

The pre-declared fallback is a pooled panel Ridge: asset-specific intercepts and surprise effects,
status-feature coefficients shared across assets, alpha chosen by the same purged expanding CV run
over months.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Mapping, Sequence

import numpy as np
import pandas as pd

_S2 = Path(__file__).resolve().parents[2] / "stage2" / "scoring"
if str(_S2) not in sys.path:
    sys.path.insert(0, str(_S2))
import stage2_backtest as s2  # noqa: E402

MACRO = list(s2.MACRO_FEATURES)
STATUS = ["F_S", "F_C", "F_I"]
COLUMNS = MACRO + STATUS
ASSETS = ("SPY", "IEF", "LQD")


def ridge_coefficients(Xtr: np.ndarray, ytr: np.ndarray, alpha) -> np.ndarray:
    """Same algebra as s2.ridge_fit_predict, returning the coefficients on the scaled columns."""
    if alpha == "INTERCEPT_ONLY":
        return np.zeros(Xtr.shape[1])
    sc = s2.fit_scaler(Xtr)
    Xz = s2.transform_with_scaler(Xtr, sc)
    gram = Xz.T @ Xz + float(alpha) * np.eye(Xz.shape[1])
    try:
        return np.linalg.solve(gram, Xz.T @ (ytr - ytr.mean()))
    except np.linalg.LinAlgError:
        return np.linalg.lstsq(gram, Xz.T @ (ytr - ytr.mean()), rcond=None)[0]


def walk_forward(features: pd.DataFrame, labels: pd.DataFrame, score_months: Sequence[pd.Period],
                 *, start: pd.Period = s2.MACRO_START, min_labels: int = s2.MIN_OUTER_LABELS, rolling: int | None = None) -> pd.DataFrame:
    """features: index (month, asset) with COLUMNS; labels: index month, columns ASSETS (excess returns).
    Returns one row per (month, asset) with the prediction, alpha and coefficients."""
    rows: List[Dict] = []
    for asset in ASSETS:
        X_all = features.xs(asset, level="asset")[COLUMNS]
        for dm in score_months:
            last = dm - 2
            train = [m for m in X_all.index if start <= m <= last and m in labels.index and np.isfinite(labels.loc[m, asset])]
            train = sorted(train)
            if rolling:
                train = train[-rolling:]
            if len(train) < min_labels:
                raise ValueError(f"{asset} {dm}: {len(train)} labels < {min_labels}")
            Xtr = X_all.loc[train].to_numpy(float)
            ytr = labels.loc[train, asset].to_numpy(float)
            x = X_all.loc[dm].to_numpy(float)
            alpha, nf, _ = s2.choose_alpha(Xtr, ytr)
            pred, _ = s2.ridge_fit_predict(Xtr, ytr, x, alpha)
            beta = ridge_coefficients(Xtr, ytr, alpha)
            rows.append({"decision_month": str(dm), "asset": asset, "n_train": len(train), "alpha": str(alpha),
                         "prediction_excess_return": pred, "benchmark_mean_excess_return": float(ytr.mean()),
                         **{f"beta_{c}": float(b) for c, b in zip(COLUMNS, beta)}})
    return pd.DataFrame(rows)


def _pooled_design(features: pd.DataFrame, months: Sequence[pd.Period]) -> tuple:
    rows, idx = [], []
    for m in months:
        for k, a in enumerate(ASSETS):
            f = features.loc[(m, a)]
            surpr = np.zeros(len(MACRO) * len(ASSETS))
            surpr[k * len(MACRO):(k + 1) * len(MACRO)] = f[MACRO].to_numpy(float)
            rows.append(np.concatenate([surpr, f[STATUS].to_numpy(float)]))
            idx.append((m, a))
    return np.array(rows), idx


def _pooled_fit_predict(X: np.ndarray, y: np.ndarray, assets: List[str], x: np.ndarray, asset: str, alpha):
    """Asset intercepts unpenalised (per-asset centring on the training rows)."""
    Xc, yc = X.copy(), y.copy()
    means_x, means_y = {}, {}
    for a in set(assets):
        mask = np.array([b == a for b in assets])
        means_x[a] = np.nanmean(X[mask], axis=0)
        means_y[a] = float(y[mask].mean())
        Xc[mask] -= means_x[a]
        yc[mask] -= means_y[a]
    if alpha == "INTERCEPT_ONLY":
        return means_y[asset]
    sc = s2.fit_scaler(Xc)
    Xz = s2.transform_with_scaler(Xc, sc)
    xz = s2.transform_with_scaler(x - means_x[asset], sc)
    beta = np.linalg.lstsq(Xz.T @ Xz + float(alpha) * np.eye(Xz.shape[1]), Xz.T @ yc, rcond=None)[0]
    return float(means_y[asset] + xz @ beta)


def pooled_walk_forward(features: pd.DataFrame, labels: pd.DataFrame, score_months: Sequence[pd.Period],
                        *, start: pd.Period = s2.MACRO_START, min_labels: int = s2.MIN_OUTER_LABELS) -> pd.DataFrame:
    rows = []
    for dm in score_months:
        train_m = sorted(m for m in labels.index if start <= m <= dm - 2)
        if len(train_m) < min_labels:
            raise ValueError(f"{dm}: {len(train_m)} labels < {min_labels}")
        X, idx = _pooled_design(features, train_m)
        y = np.array([labels.loc[m, a] for m, a in idx])
        assets = [a for _, a in idx]
        # alpha: purged expanding inner CV over months (one-month purge), same grid as Stage 2
        losses = {a: [] for a in s2.ALPHAS}
        for tr_end, val in s2.inner_splits(len(train_m)):
            tr_months = set(train_m[i] for i in tr_end)
            vm = train_m[val]
            mask = np.array([m in tr_months for m, _ in idx])
            Xv, iv = _pooled_design(features, [vm])
            for al in s2.ALPHAS:
                for k, (_, a) in enumerate(iv):
                    p = _pooled_fit_predict(X[mask], y[mask], [b for b, keep in zip(assets, mask) if keep], Xv[k], a, al)
                    losses[al].append((labels.loc[vm, a] - p) ** 2)
        mean_loss = {a: float(np.mean(v)) for a, v in losses.items()}
        best = min(mean_loss.values())
        alpha = max([a for a, l in mean_loss.items() if l <= best + 1e-12 * max(1, abs(best))], key=s2._alpha_strength)
        Xd, idd = _pooled_design(features, [dm])
        for k, (_, a) in enumerate(idd):
            rows.append({"decision_month": str(dm), "asset": a, "alpha": str(alpha), "n_train_months": len(train_m),
                         "prediction_excess_return": _pooled_fit_predict(X, y, assets, Xd[k], a, alpha)})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ G4c reliability checks
def intercept_only_share(pred: pd.DataFrame) -> float:
    return float((pred["alpha"] == "INTERCEPT_ONLY").mean())


def sign_stability(pred: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    out = {}
    for a in ASSETS:
        p = pred[pred["asset"] == a]
        out[a] = {}
        for c in STATUS:
            b = p[f"beta_{c}"].to_numpy(float)
            nz = b[np.abs(b) > 1e-12]
            out[a][c] = float(max((nz > 0).mean(), (nz < 0).mean())) if len(nz) else float("nan")
    return out


def calibration_slope(pred: pd.DataFrame, labels: pd.DataFrame) -> float:
    y = np.array([labels.loc[pd.Period(m, "M"), a] for m, a in zip(pred["decision_month"], pred["asset"])])
    x = pred["prediction_excess_return"].to_numpy(float)
    x = x - x.mean()
    return float((x @ (y - y.mean())) / (x @ x)) if x @ x > 0 else float("nan")


def permutation_placebo(features: pd.DataFrame, labels: pd.DataFrame, score_months: Sequence[pd.Period], *, n: int = 200, seed: int = 20261027) -> Dict:
    """Permute the status-feature rows across months (jointly for the three assets) and refit.
    Returns the actual improvement over the surprises-only model and the placebo distribution."""
    def mse(pred):
        y = np.array([labels.loc[pd.Period(m, "M"), a] for m, a in zip(pred["decision_month"], pred["asset"])])
        return float(np.mean((y - pred["prediction_excess_return"].to_numpy(float)) ** 2))
    zero = features.copy()
    zero[STATUS] = 0.0
    base = mse(walk_forward(zero, labels, score_months))
    actual = base - mse(walk_forward(features, labels, score_months))
    rng = np.random.default_rng(seed)
    months = sorted(set(features.index.get_level_values("month")))
    draws = []
    for _ in range(n):
        perm = dict(zip(months, rng.permutation(months)))
        f = features.copy()
        for m in months:
            for a in ASSETS:
                f.loc[(m, a), STATUS] = features.loc[(perm[m], a), STATUS].to_numpy()
        draws.append(base - mse(walk_forward(f, labels, score_months)))
    return {"actual_improvement": actual, "percentile": float(np.mean(np.array(draws) < actual) * 100), "n": n}
