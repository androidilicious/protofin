"""Controlled forecast-stability diagnostics, never an input to model selection.

Both cohorts use identical dates and expanding-mean forecasts as their error
reference. Diagnostics inspect uncapped forecasts, including the warm-up before
portfolio allocation. No post-2022 holding month is accepted.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from deterministic_mvp import ASSETS, REQUIRED_SIGNAL_FEATURES, _parse_excel_dates

STABILITY_KEYS = ["baseline", "supported_policy", "no_policy", "clip_only", "shrink_only", "robust", "historical_mean"]
BOUNDS = np.array([[.20, .70], [.15, .60], [.10, .40]])


def matched_metrics(rows, historical_mean, threshold=.20):
    """OOS R² uses matched expanding-mean SSE, not the evaluation-period mean."""
    if not rows:
        raise ValueError("Empty stability cohort")
    reference = {r["date"]: r for r in historical_mean}
    if len({r["date"] for r in rows}) != len(rows):
        raise ValueError("Duplicate forecast dates")
    for row in rows:
        np.testing.assert_allclose(row["actual"], reference[row["date"]]["actual"], rtol=0, atol=0)
    q, actual = np.array([r["q"] for r in rows]), np.array([r["actual"] for r in rows])
    mean = np.array([reference[r["date"]]["q"] for r in rows])
    error, mean_error = q - actual, mean - actual
    if not np.isfinite([q, actual, mean]).all():
        raise ValueError("Non-finite stability inputs")
    flagged = np.abs(q) > threshold
    assets = {}
    for j, asset in enumerate(ASSETS):
        sse, ref_sse = float((error[:, j] ** 2).sum()), float((mean_error[:, j] ** 2).sum())
        extreme = int(np.argmax(np.abs(q[:, j])))
        assets[asset] = {
            "mae": float(np.abs(error[:, j]).mean()), "rmse": float(np.sqrt(sse / len(rows))),
            "sse": sse, "historical_mean_sse": ref_sse,
            "oos_r2_vs_historical_mean": 1 - sse / ref_sse if ref_sse > 0 else None,
            "largest_absolute_forecast": float(abs(q[extreme, j])),
            "largest_forecast_signed": float(q[extreme, j]),
            "largest_forecast_decision": rows[extreme]["decision_date"],
            "extreme_count": int(flagged[:, j].sum()),
            "extreme_rate": float(flagged[:, j].mean()),
        }
    return {
        "months": len(rows), "asset_months": int(q.size), "assets": assets,
        "pooled_rmse": float(np.sqrt(np.mean(error ** 2))),
        "pooled_mae": float(np.abs(error).mean()),
        "largest_absolute_forecast": float(np.abs(q).max()),
        "extreme_asset_months": int(flagged.sum()),
        "extreme_asset_month_rate": float(flagged.mean()),
        "months_with_any_extreme": int(flagged.any(axis=1).sum()),
    }


def allocation_limits(rows):
    weights = np.array([r["weights"] for r in rows])
    lower = np.isclose(weights, BOUNDS[:, 0], rtol=0, atol=1e-8)
    upper = np.isclose(weights, BOUNDS[:, 1], rtol=0, atol=1e-8)
    return {
        "months": len(rows), "months_at_any_limit": int((lower | upper).any(axis=1).sum()),
        "fraction_at_any_limit": float((lower | upper).any(axis=1).mean()),
        "assets": {a: {"lower_count": int(lower[:, j].sum()), "upper_count": int(upper[:, j].sum())}
                   for j, a in enumerate(ASSETS)},
    }


def extreme_events(rows, threshold):
    events = []
    for row in rows:
        for j, asset in enumerate(ASSETS):
            if abs(row["q"][j]) <= threshold:
                continue
            features = row.get("audit", {}).get(asset, {}).get("features", [])
            dominant = max(features, key=lambda f: abs(f["contribution"])) if features else None
            events.append({"decision_date": row["decision_date"], "holding_month": row["date"] + pd.offsets.MonthEnd(1),
                           "asset": asset, "forecast": row["q"][j], "actual": row["actual"][j],
                           "dominant_feature": dominant})
    return sorted(events, key=lambda r: abs(r["forecast"]), reverse=True)


def january_trace(panel, all_forecasts, workbook):
    """Reproduce the January 2020 calculation from raw policy sheets and fits."""
    target = next(r for r in all_forecasts["baseline"] if r["decision_date"] == pd.Timestamp("2020-01-31"))
    current = panel.loc[target["idx"]]
    valid = panel[REQUIRED_SIGNAL_FEATURES].notna().all(axis=1)
    train = panel[(panel.exit <= current.decision_date) & valid]
    if len(train) != target["training_rows"]:
        raise AssertionError("January trace does not match fitted training rows")
    # Raw policy values retain sheet names, source dates and original units.
    raw = []
    for horizon in ["3m", "6m"]:
        frame = pd.read_excel(workbook, sheet_name=f"policy_{horizon}")
        frame["Date"] = _parse_excel_dates(frame["Date"])
        frame = frame[frame.Date <= current.decision_date].sort_values("Date")
        value_column = f"implied_policy_rate_{horizon}_pct"
        frame["change"] = pd.to_numeric(frame[value_column]).diff()
        raw.extend({"sheet": f"policy_{horizon}", "source_date": r["Date"],
                    "original_column": value_column, "level_percentage_points": r[value_column],
                    "change_percentage_points": r["change"]} for _, r in frame.iterrows())
        if horizon == "6m":
            np.testing.assert_allclose(frame.iloc[-1]["change"], current["policy_6m_change"], atol=1e-12)
    feature = "policy_6m_change"
    finite = train[feature].dropna()
    info = next(f for f in target["audit"]["equity"]["features"] if f["feature"] == feature)
    filled = train[feature].fillna(finite.median()).to_numpy(float)
    reconstructed_z = (current[feature] - filled.mean()) / filled.std(ddof=0)
    np.testing.assert_allclose(reconstructed_z, info["standardized_input"], atol=1e-10)
    calculations = {}
    for j, asset in enumerate(ASSETS):
        audit = target["audit"][asset]
        contribution_sum = sum(f["contribution"] for f in audit["features"])
        reconstructed = audit["intercept"] + contribution_sum
        np.testing.assert_allclose(reconstructed, target["q"][j], atol=1e-12)
        f = next(f for f in audit["features"] if f["feature"] == feature)
        np.testing.assert_allclose(f["coefficient"] * reconstructed_z, f["contribution"], atol=1e-12)
        calculations[asset] = {"forecast": target["q"][j], "realized": target["actual"][j],
                               "alpha": target["alpha"][j], "training_target_mean": audit["intercept"],
                               "sum_feature_contributions": contribution_sum,
                               "reconstructed_forecast": reconstructed,
                               "reconstruction_error": reconstructed - target["q"][j],
                               "policy_change_coefficient": f["coefficient"],
                               "policy_change_contribution": f["contribution"],
                               "features": sorted(audit["features"], key=lambda x: abs(x["contribution"]), reverse=True)}
    policy_training = train[train.policy_data_date.notna()]
    return {
        "decision_date": current.decision_date, "holding_month": current.holding_month,
        "entry": current.entry, "exit": current.exit, "training_rows": len(train),
        "last_training_exit": train.exit.max(), "raw_policy_snapshots": raw,
        "units": "Policy levels and differences are percentage points as labeled in the workbook; no percent-to-decimal conversion is applied to predictors. Targets/forecasts are monthly decimal total returns. No annualization or multiplication by 100 occurs in the fit.",
        "missing_data": "Before observed policy history, each training column uses its training median (zero only if wholly missing). Scaling uses all rows after imputation, population standard deviation (ddof=0). Finite-row counts include any carried-forward values; they are not independent releases.",
        "policy_training_rows": policy_training[["date", "policy_data_date", "exit", "policy_3m_level", "policy_6m_level", "policy_3m_change", "policy_6m_change"]].to_dict("records"),
        "feature": feature, "observed_values": finite.tolist(),
        "distinct_observed_values": int(finite.nunique()), "missing_training_rows": int(train[feature].isna().sum()),
        "imputation_median": float(finite.median()), "training_mean_after_imputation": float(filled.mean()),
        "training_std_after_imputation": float(filled.std(ddof=0)),
        "observed_only_std": float(finite.std(ddof=0)), "raw_decision_input": current[feature],
        "standardized_input": reconstructed_z, "assets": calculations,
        "same_decision_repairs": {key: next(r for r in rows if r["date"] == target["date"])["q"]
                                  for key, rows in all_forecasts.items() if key in STABILITY_KEYS},
        "conclusion": "Reproduced sparse-feature extrapolation: two almost identical observed policy changes, plus median-imputed earlier rows, produce a tiny fitted scale. January's opposite-signed change becomes an enormous standardized input. The coefficient times that input reconstructs the dominant forecast contribution. This confirms the numerical mechanism in the supplied workbook, not the external correctness or historical availability of the workbook values.",
    }


def stability_report(panel, all_forecasts, all_decisions, common, workbook, specification):
    config = specification["stability_evaluation"]
    threshold = config["absolute_monthly_forecast_warning"]
    forecast_dates = set.intersection(*({r["date"] for r in all_forecasts[k]} for k in STABILITY_KEYS))
    if not set(common) <= forecast_dates:
        raise ValueError("Allocation dates missing from stability forecasts")
    # Explicit guard here as well as in the panel builder and site bundler.
    if any(r["date"] + pd.offsets.MonthEnd(1) >= pd.Timestamp("2023-01-01")
           for k in STABILITY_KEYS for r in all_forecasts[k]):
        raise ValueError("Reserved holding month in stability investigation")
    cohorts = {}
    for name, dates in [("all_forecasts", forecast_dates), ("portfolio_dates", common)]:
        matched = {k: [r for r in all_forecasts[k] if r["date"] in dates] for k in STABILITY_KEYS}
        cohorts[name] = {
            "first_decision": min(r["decision_date"] for r in matched["baseline"]),
            "last_decision": max(r["decision_date"] for r in matched["baseline"]),
            "results": {k: matched_metrics(rows, matched["historical_mean"], threshold) for k, rows in matched.items()},
            "extreme_events": {k: extreme_events(rows, threshold) for k, rows in matched.items()},
            "timeline": {k: [{"decision_date": r["decision_date"], "holding_month": r["date"] + pd.offsets.MonthEnd(1),
                               "q": r["q"], "actual": r["actual"]} for r in rows] for k, rows in matched.items()},
        }
    calendar = []
    for year in sorted({r["holding_month"].year for r in all_decisions["baseline"] if r["date"] in common}):
        dates = {r["date"] for r in all_decisions["baseline"] if r["date"] in common and r["holding_month"].year == year}
        selected = {k: [r for r in all_forecasts[k] if r["date"] in dates] for k in STABILITY_KEYS}
        calendar.append({"year": year, "partial_year": len(dates) != 12,
                         "results": {k: matched_metrics(rows, selected["historical_mean"], threshold) for k, rows in selected.items()}})
    return {
        "status": "Exploratory development investigation; original forecasts retained, no automatic production selection or reserved-test evaluation.",
        "threshold": threshold, "comparison_order": STABILITY_KEYS,
        "threshold_interpretation": "Inspection threshold fixed before this investigation. Zero flags does not establish forecast accuracy or a calibrated prediction interval. Returns are never capped.",
        "cohorts": cohorts, "calendar_years": calendar,
        "allocation_limits": {k: allocation_limits([r for r in all_decisions[k] if r["date"] in common]) for k in STABILITY_KEYS},
        "january_2020": january_trace(panel, all_forecasts, workbook),
        "evaluation_rules": config,
    }
