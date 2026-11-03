"""Exploratory dependence-aware comparisons, separate from model selection."""
from __future__ import annotations

import numpy as np
import pandas as pd


def paired_block_interval(selected, baseline, block_length=3, replications=3000, seed=20261102, confidence=.95):
    """Resample the same circular contiguous month blocks for both strategies.

    Estimates mean monthly net-return difference conditional on fitted paths.
    Does not refit models, correct for trying many variants, or estimate a
    compounded-return interval. Block lengths are fixed before the run.
    """
    selected, baseline = np.asarray(selected, float), np.asarray(baseline, float)
    if selected.ndim != 1 or selected.shape != baseline.shape or not np.isfinite([selected, baseline]).all():
        raise ValueError("Expected equal-length, finite monthly return vectors")
    n = len(selected)
    if not 1 <= block_length <= n or replications < 2 or not 0 < confidence < 1:
        raise ValueError("Invalid bootstrap settings or insufficient months")
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, n, size=(replications, int(np.ceil(n / block_length))))
    indices = ((starts[:, :, None] + np.arange(block_length)) % n).reshape(replications, -1)[:, :n]
    difference = selected - baseline
    draws = difference[indices].mean(axis=1)
    tail = (1 - confidence) / 2
    low, high = np.quantile(draws, [tail, 1-tail])
    return {"months": n, "block_length": block_length, "mean_monthly_difference": float(difference.mean()),
            "lower": float(low), "upper": float(high), "replications": replications,
            "seed": seed, "confidence": confidence}


def compound_rows(rows):
    return {"months": len(rows), "cumulative_return": float(np.prod([1+d["net_return"] for d in rows])-1)}


def episode_checks(decisions, periods, offsets):
    """Evaluate shifted windows and exclusions from existing continuous holdings."""
    coverage = {pd.Timestamp(d["holding_month"]).to_period("M") for d in decisions["baseline"]}
    boundaries, exclusions = [], []
    for period in periods:
        first, last = pd.Timestamp(period["start"]).to_period("M"), pd.Timestamp(period["end"]).to_period("M")
        results = {}
        for key, rows in decisions.items():
            kept = [d for d in rows if not first <= pd.Timestamp(d["holding_month"]).to_period("M") <= last]
            results[key] = compound_rows(kept)
        exclusions.append({"id": period["id"], "name": period["name"], "results": results})
        for start_offset in offsets:
            for end_offset in offsets:
                begin, end = first + start_offset, last + end_offset
                expected = set(pd.period_range(begin, end, freq="M")) if begin <= end else set()
                complete = bool(expected) and expected.issubset(coverage)
                results = {}
                if complete:
                    for key, rows in decisions.items():
                        chosen = [d for d in rows if pd.Timestamp(d["holding_month"]).to_period("M") in expected]
                        results[key] = compound_rows(chosen)
                boundaries.append({"episode": period["id"], "name": period["name"],
                                   "start_offset": start_offset, "end_offset": end_offset,
                                   "requested_start": str(begin), "requested_end": str(end),
                                   "complete": complete, "results": results,
                                   "reason": None if complete else "Requested window is outside common development coverage; not evaluated."})
    return {"episode_boundary_checks": boundaries, "leave_episode_out": exclusions}


def credit_shared_information(panel, common, min_train=24):
    """Descriptive shared information; no signal removal or performance selection.

    Regress credit level/change on known ANFCI level/change using *prior feature
    rows*, then measure fit on each later common decision. No return target is
    involved. Explaining a credit proxy does not prove it adds no return signal.
    """
    frame = panel.copy()
    frame["anfci_change"] = frame.anfci.diff()
    inputs, targets = ["anfci", "anfci_change"], ["credit_level", "credit_change_1m"]
    valid = frame[inputs+targets].notna().all(axis=1)
    sample = frame[frame.date.isin(common) & valid]
    residuals, mean_errors, predictions = [], [], []
    for _, row in sample.iterrows():
        train = frame[(frame.date < row.date) & valid]
        if len(train) < min_train:
            continue
        x, y = train[inputs].to_numpy(float), train[targets].to_numpy(float)
        mean, scale = x.mean(axis=0), x.std(axis=0)
        scale[scale < 1e-12] = 1.
        design = np.column_stack([np.ones(len(x)), (x-mean)/scale])
        beta = np.linalg.lstsq(design, y, rcond=None)[0]
        predicted = np.r_[1., (row[inputs].to_numpy(float)-mean)/scale] @ beta
        actual = row[targets].to_numpy(float)
        residuals.append(actual-predicted)
        mean_errors.append(actual-y.mean(axis=0))
        predictions.append({"date": row.date, "last_training_date": train.date.max(),
                            "training_rows": len(train), "predicted": predicted, "actual": actual})
    feature_results = {}
    for j, target in enumerate(targets):
        correlation = sample[target].corr(sample.anfci)
        r = np.array(residuals)[:, j] if residuals else np.array([])
        m = np.array(mean_errors)[:, j] if mean_errors else np.array([])
        denominator = float(m @ m)
        feature_results[target] = {"correlation_with_anfci_level": correlation,
                                   "out_of_sample_r2_vs_expanding_mean": float(1-(r @ r)/denominator) if denominator > 0 else None,
                                   "residual_rmse": float(np.sqrt(np.mean(r*r))) if len(r) else None}
    return {"months": len(predictions), "min_prior_feature_rows": min_train, "features": feature_results,
            "predictions": predictions,
            "interpretation": "Descriptive associations in revised histories. Past-only ANFCI projection of credit conditions is not a test of causal redundancy or asset-return predictability; the credit-versus-baseline forecast and portfolio comparisons remain necessary."}


def inference_report(decisions, panel, periods, specification):
    settings = specification["inference"]
    bootstrap = settings["bootstrap"]
    base = [d["net_return"] for d in decisions["baseline"]]
    results = {}
    base_dates = [d["date"] for d in decisions["baseline"]]
    for key, rows in decisions.items():
        if [d["date"] for d in rows] != base_dates:
            raise ValueError("Bootstrap requires identical ordered decision dates")
        results[key] = [paired_block_interval([d["net_return"] for d in rows], base,
                                             block_length=b, replications=bootstrap["replications"],
                                             seed=bootstrap["seed"], confidence=bootstrap["confidence"])
                        for b in bootstrap["block_lengths"]]
    return {"paired_block_bootstrap": {"settings": bootstrap, "results": results},
            "credit_shared_information": credit_shared_information(panel, set(base_dates)),
            **episode_checks(decisions, periods, settings["episode_boundary_offsets_months"])}
