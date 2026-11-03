"""Matched one-month estimator comparison, separate from signal search.

Run from deterministic_mvp: python3 src/model_comparison.py
Only committed pre-2023 research data are used. No production model is selected.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import platform
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
import scipy
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import ElasticNet, LinearRegression, Ridge

from deterministic_mvp import ASSETS
from research_backtest import (
    ROOT, WORKBOOK, PERIODS, adjusted_prices, make_panel, monthly_allocation,
    passive_decisions, summarize, serializable, input_hashes, BENCHMARK,
)

SPEC_PATH = ROOT / "model_comparison/experiment_spec.json"
OUT = ROOT / "model_comparison/outputs"
METHODS = {
    "historical_mean": {"name": "Historical mean", "method": "mean", "stage": "core", "color": "#64748b"},
    "ols": {"name": "OLS", "method": "ols", "stage": "core", "color": "#c27535"},
    "ridge": {"name": "Ridge", "method": "ridge", "stage": "core", "color": "#008aa1"},
    "elastic_net": {"name": "Elastic Net", "method": "elastic_net", "stage": "core", "color": "#9261bd"},
    "ridge_lags": {"name": "Dynamic Ridge · lags only", "method": "ridge", "stage": "extension", "color": "#3b71d1"},
    "ridge_interactions": {"name": "Ridge · ANFCI interactions only", "method": "ridge", "stage": "extension", "color": "#b6516a"},
}


def build_comparison_panel(prices: pd.DataFrame, spec: dict):
    panel, covariance_returns = make_panel(prices)
    # Current calendar-close return is known by the decision, unlike the previous
    # forward holding return, which does not finish until the next entry close.
    for idx, row in panel.iterrows():
        known = prices.loc[prices.index <= row.decision_date]
        earlier = known.loc[known.index.to_period("M") < row.date.to_period("M")]
        if earlier.empty:
            continue
        returns = known.iloc[-1] / earlier.iloc[-1] - 1
        for asset in ASSETS:
            panel.at[idx, f"lag_{asset}_return"] = returns[asset]
        panel.at[idx, "lag_return_source_date"] = known.index[-1]
    for feature in ["growth_surprise", "inflation_surprise"]:
        panel[f"lag_{feature}"] = panel[feature].shift(1)
    panel["lag_macro_source_date"] = panel.decision_date.shift(1)
    required = spec["core_features"] + spec["lag_features"] + spec["interaction_features"]
    eligible = np.isfinite(panel[required].to_numpy(float)).all(axis=1)
    eligible &= panel.holding_month <= pd.Timestamp(spec["last_holding_month"])
    panel = panel.loc[eligible].copy().reset_index(drop=True)
    if panel.empty or (panel.lag_return_source_date > panel.decision_date).any():
        raise ValueError("Invalid comparison coverage or future lagged return")
    return panel, covariance_returns


def feature_columns(key: str, spec: dict) -> list[str]:
    columns = list(spec["core_features"])
    if key == "ridge_lags":
        columns += spec["lag_features"]
    if key == "ridge_interactions":
        columns += spec["interaction_features"]
    return columns


def prepare_fold(x, y, test, spec):
    """Fit every transformation solely on this fold's observed training rows."""
    x, y, test = np.asarray(x, float), np.asarray(y, float), np.asarray(test, float)
    medians = pd.DataFrame(np.where(np.isfinite(x), x, np.nan)).median().fillna(0).to_numpy()
    x = np.where(np.isfinite(x), x, medians)
    raw_test = test.copy()
    test = np.where(np.isfinite(test), test, medians)
    low, high = np.quantile(x, spec["preprocessing"]["quantiles"], axis=0)
    x, test = np.clip(x, low, high), np.clip(test, low, high)
    mean, scale = x.mean(axis=0), x.std(axis=0)
    scale[scale < spec["preprocessing"]["feature_scale_floor"]] = 1.
    target_mean, target_scale = y.mean(axis=0), y.std(axis=0)
    target_scale[target_scale < 1e-12] = 1.
    return {"x": (x-mean)/scale, "y": (y-target_mean)/target_scale,
            "test": (test-mean)/scale, "target_mean": target_mean, "target_scale": target_scale,
            "clipped": test[0] != raw_test[0], "training_rows": len(x),
            "raw_input": raw_test[0], "used_input": test[0], "feature_mean": mean,
            "feature_scale": scale, "clip_low": low, "clip_high": high}


def fit_method(fold: dict, method: str, spec: dict, alpha=None, l1_ratio=None):
    x, y, test = fold["x"], fold["y"], fold["test"]
    coefficients = np.zeros((len(ASSETS), x.shape[1]))
    standardized = np.zeros((len(test), len(ASSETS)))
    iterations = np.zeros(len(ASSETS), dtype=int)
    intercept = np.zeros(len(ASSETS))
    if method == "ols":
        estimator = LinearRegression(fit_intercept=True).fit(x, y)
        standardized = estimator.predict(test)
        coefficients = estimator.coef_
        intercept = estimator.intercept_
    elif method == "ridge":
        estimator = Ridge(alpha=float(alpha)*len(x), fit_intercept=True, solver="svd").fit(x, y)
        standardized = estimator.predict(test)
        coefficients = estimator.coef_
        intercept = estimator.intercept_
    elif method == "elastic_net":
        for j in range(len(ASSETS)):
            with warnings.catch_warnings():
                warnings.simplefilter("error", ConvergenceWarning)
                estimator = ElasticNet(alpha=float(alpha), l1_ratio=float(l1_ratio), fit_intercept=True,
                                       max_iter=spec["elastic_net"]["max_iter"], tol=spec["elastic_net"]["tol"],
                                       selection="cyclic").fit(x, y[:, j])
            standardized[:, j] = estimator.predict(test)
            coefficients[j] = estimator.coef_
            iterations[j] = estimator.n_iter_
            intercept[j] = estimator.intercept_
    elif method != "mean":
        raise ValueError(f"Unknown method: {method}")
    prediction = fold["target_mean"] + standardized*fold["target_scale"]
    if not np.isfinite(prediction).all():
        raise ValueError(f"Nonfinite {method} forecast")
    return prediction[0], {"nonzero": (np.abs(coefficients) > 1e-10).sum(axis=1),
                           "coefficients": coefficients, "iterations": iterations,
                           "base_return": fold["target_mean"] + intercept*fold["target_scale"],
                           "contributions": coefficients*fold["test"][0]*fold["target_scale"][:, None]}


def parameter_grid(method: str, spec: dict):
    if method == "ridge":
        return [(a, None) for a in spec["ridge_alpha"]]
    if method == "elastic_net":
        return list(itertools.product(spec["elastic_net_alpha"], spec["elastic_net_l1_ratio"]))
    return [(None, None)]


def comparison_forecasts(panel: pd.DataFrame, key: str, spec: dict):
    method = METHODS[key]["method"]
    columns = feature_columns(key, spec)
    grid = parameter_grid(method, spec)
    folds, fits = {}, {}

    def past(row):
        return panel[panel.exit <= row.decision_date]

    def prepared(row):
        idx = int(row.name)
        if idx not in folds:
            train = past(row)
            folds[idx] = prepare_fold(train[columns].to_numpy(float), np.stack(train.asset_returns),
                                      row[columns].to_numpy(float)[None, :], spec)
        return folds[idx]

    def candidate(row, params):
        cache_key = (int(row.name), params)
        if cache_key not in fits:
            fits[cache_key] = fit_method(prepared(row), method, spec, *params)
        return fits[cache_key]

    predictions = []
    for idx, row in panel.iterrows():
        train = past(row)
        if len(train) < spec["min_train"]:
            continue
        chosen, cv_errors, validation_dates = [grid[0]]*len(ASSETS), None, []
        if len(grid) > 1:
            scores = []
            validation = [v for _, v in train.iterrows() if len(past(v)) >= spec["min_inner_train"]]
            if not validation:
                raise ValueError("No completed chronological validation folds")
            validation_dates = [v.decision_date for v in validation]
            for params in grid:
                errors = [(candidate(v, params)[0]-v.asset_returns)**2 for v in validation]
                scores.append(np.mean(errors, axis=0))
            scores = np.asarray(scores)
            positions = scores.argmin(axis=0)
            chosen = [grid[i] for i in positions]
            cv_errors = scores[positions, np.arange(len(ASSETS))]
        q, nonzero, coefficients, iterations, base_returns, contributions = [], [], [], [], [], []
        for j, params in enumerate(chosen):
            pred, info = candidate(row, params)
            q.append(pred[j]); nonzero.append(info["nonzero"][j])
            coefficients.append(info["coefficients"][j]); iterations.append(info["iterations"][j])
            base_returns.append(info["base_return"][j]); contributions.append(info["contributions"][j])
        fold = prepared(row)
        predictions.append({"idx": idx, "date": row.date, "decision_date": row.decision_date, "exit": row.exit,
                            "q": np.array(q), "actual": row.asset_returns, "training_rows": len(train),
                            "last_training_exit": train.exit.max(), "alpha": [p[0] for p in chosen],
                            "l1_ratio": [p[1] for p in chosen], "validation_mse": cv_errors,
                            "last_validation_exit": train.exit.max() if validation_dates else None,
                            "validation_folds": len(validation_dates), "feature_columns": columns,
                            "nonzero_features": nonzero, "coefficients": coefficients, "iterations": iterations,
                            "base_return": base_returns, "feature_contributions": contributions,
                            "preprocessing": {"raw_input": fold["raw_input"], "used_input": fold["used_input"],
                                              "standardized_input": fold["test"][0],
                                              "training_mean": fold["feature_mean"], "training_scale": fold["feature_scale"],
                                              "clip_low": fold["clip_low"], "clip_high": fold["clip_high"]},
                            "input_clipped": fold["clipped"].tolist(),
                            "max_abs_standardized_input": float(np.abs(fold["test"]).max()), "audit": {}})
    return predictions


def per_asset_metrics(rows, mean_rows):
    reference = {p["date"]: p for p in mean_rows}
    if not rows:
        return {}
    actual = np.stack([p["actual"] for p in rows]); predicted = np.stack([p["q"] for p in rows])
    mean = np.stack([reference[p["date"]]["q"] for p in rows])
    errors = predicted-actual; reference_errors = mean-actual
    result = {}
    for j, asset in enumerate(ASSETS):
        denominator = float(np.sum(reference_errors[:, j]**2))
        result[asset] = {"months": len(rows), "mae": float(np.abs(errors[:, j]).mean()),
                         "rmse": float(np.sqrt(np.mean(errors[:, j]**2))),
                         "oos_r2_vs_mean": float(1-np.sum(errors[:, j]**2)/denominator) if denominator > 0 else None,
                         "forecast_min": float(predicted[:, j].min()), "forecast_max": float(predicted[:, j].max()),
                         "over_20pct": int((np.abs(predicted[:, j]) > .2).sum()),
                         "mean_nonzero_features": float(np.mean([r["nonzero_features"][j] for r in rows]))}
    return result


def summarize_window(decisions, predictions, dates, prices, covariance_returns):
    results = {}
    means = predictions["historical_mean"]
    for key, rows in decisions.items():
        selected = []
        for decision in rows:
            if decision["date"] not in dates:
                continue
            covariance = covariance_returns.loc[covariance_returns.index <= decision["decision_date"]].tail(36).cov().to_numpy(float)
            # Match the exact regularized covariance used inside BL for predictive views.
            prior_cov = covariance + np.eye(len(ASSETS))*1e-8 if key != "prior_only" else covariance
            selected.append({**decision, "bl_prior": 2.5*prior_cov @ BENCHMARK, "covariance": covariance})
        stats, path = summarize(selected, prices)
        forecast_rows = [p for p in predictions.get(key, []) if p["date"] in dates]
        results[key] = {"portfolio": stats, "forecast": per_asset_metrics(forecast_rows, means), "path": path,
                        "decisions": selected,
                        "predictions": [{k: v for k, v in p.items() if k != "audit"} for p in forecast_rows]}
    return results


def main():
    spec = json.loads(SPEC_PATH.read_text())
    if sklearn.__version__ != "1.6.1":
        raise RuntimeError("Install requirements-comparison.txt: this experiment pins scikit-learn 1.6.1")
    prices = adjusted_prices(); panel, covariance_returns = build_comparison_panel(prices, spec)
    predictions, decisions = {}, {}
    for key in METHODS:
        predictions[key] = comparison_forecasts(panel, key, spec)
        decisions[key] = monthly_allocation(panel, covariance_returns, predictions[key])
        print(key, len(predictions[key]), "forecasts;", len(decisions[key]), "allocations", flush=True)
    common = set.intersection(*(set(d["date"] for d in rows) for rows in decisions.values()))
    forecast_common = set.intersection(*(set(p["date"] for p in rows) for rows in predictions.values()))
    if not common:
        raise ValueError("No common development decisions")
    decisions["fixed453520"] = passive_decisions(panel, BENCHMARK, common)
    decisions["prior_only"] = monthly_allocation(panel, covariance_returns, predictions["historical_mean"], use_views=False)
    all_meta = {**METHODS, "fixed453520": {"name": "Fixed 45 / 35 / 20", "stage": "reference", "color": "#8a959e"},
                "prior_only": {"name": "BL prior only", "stage": "reference", "color": "#86765c"}}
    windows = [{"id": "development", "name": "Full development history", "description": "All common eligible holding months. This is the primary comparison.",
                "results": summarize_window(decisions, predictions, common, prices, covariance_returns)}]
    for period in PERIODS:
        dates = {d["date"] for d in decisions["historical_mean"] if d["date"] in common and
                 pd.Timestamp(period["start"]) <= d["holding_month"] <= pd.Timestamp(period["end"])}
        if dates:
            windows.append({**period, "results": summarize_window(decisions, predictions, dates, prices, covariance_returns)})
    years = []
    for year in sorted({d["holding_month"].year for d in decisions["historical_mean"] if d["date"] in common}):
        dates = {d["date"] for d in decisions["historical_mean"] if d["date"] in common and d["holding_month"].year == year}
        result = summarize_window(decisions, predictions, dates, prices, covariance_returns)
        years.append({"year": year, "partial_year": result["ridge"]["portfolio"]["months"] < 12,
                      "results": {k: {"portfolio": v["portfolio"], "forecast": v["forecast"]} for k,v in result.items()}})
    sources = ["model_comparison.py", "research_backtest.py", "research_diagnostics.py", "research_inference.py", "deterministic_mvp.py"]
    output = {"generated_at": datetime.now(timezone.utc).isoformat(), "specification": spec,
              "specification_sha256": hashlib.sha256(SPEC_PATH.read_bytes()).hexdigest(),
              "code_hashes": {name: hashlib.sha256((ROOT/"src"/name).read_bytes()).hexdigest() for name in sources},
              "input_hashes": input_hashes(), "workbook_sha256": hashlib.sha256(WORKBOOK.read_bytes()).hexdigest(),
              "environment": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__, "scikit_learn": sklearn.__version__, "scipy": scipy.__version__},
              "models": all_meta, "windows": windows, "calendar_years": years,
              "all_forecast_metrics": {k: per_asset_metrics([p for p in rows if p["date"] in forecast_common], predictions["historical_mean"]) for k,rows in predictions.items()},
              "sample": {"common_forecast_months": len(forecast_common), "common_portfolio_months": len(common),
                         "first_holding_month": min(d["holding_month"] for d in decisions["ridge"]),
                         "last_holding_month": max(d["holding_month"] for d in decisions["ridge"]),
                         "first_training_month": panel.date.min(), "last_training_month": panel.date.max()},
              "lag_provenance": panel[["date", "decision_date", "holding_month", "lag_return_source_date", "lag_macro_source_date", *spec["lag_features"]]].to_dict("records"),
              "bvar": {"implemented": False, "reason": spec["stages"]["bvar"]},
              "limitations": ["Exploratory choices follow earlier research; no production selection.", "Revised histories and assumed publication lags; not real-time vintages.",
                              "Common clipping suppresses input extrapolation for all learners; comparison is conditional on that shared preprocessing.",
                              "Core features exclude sparse policy fields and existing interactions, so these numbers are a separate experiment from Signal Research.",
                              "Forecasts and BL views are decimal total returns; no risk-free series is supplied.", "No 2023-onward holding months are evaluated. January 3, 2023 only closes December 2022."]}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/"model_comparison_results.json").write_text(json.dumps(serializable(output), indent=2, allow_nan=False))
    (OUT/"model_comparison_forecasts.json").write_text(json.dumps(serializable(predictions), indent=2, allow_nan=False))
    print("Saved", OUT/"model_comparison_results.json")


if __name__ == "__main__":
    main()
