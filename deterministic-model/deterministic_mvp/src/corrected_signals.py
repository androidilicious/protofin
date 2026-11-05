"""Rerun isolated signal additions using the frozen corrected model's rules.

This separate development runner preserves all primary code and artifacts.
Run from deterministic_mvp: python3 src/corrected_signals.py
"""
from __future__ import annotations

import json
import platform
from datetime import datetime, timezone

import numpy as np
import pandas as pd

import research_backtest as rb
from corrected_primary import digest, primary_spec, verify_freeze
from research_diagnostics import research_diagnostics, forecast_diagnostics

SPEC = rb.ROOT / "research/corrected_signals_spec.json"


def extension_forecasts(panel, extra, primary):
    """Same chronological Ridge algorithm; add columns without changing frozen code.

    research_backtest.forecasts intentionally rejects extensions to its frozen
    primary feature set. Reuse its fold-level fitter here and verify the no-extra
    path against the saved frozen run before accepting any extension results.
    """
    columns = primary["features"] + extra
    valid = panel[rb.REQUIRED_SIGNAL_FEATURES].notna().all(axis=1)
    if not valid.equals(panel[[*rb.REQUIRED_SIGNAL_FEATURES, *extra]].notna().all(axis=1)):
        raise ValueError("Added inputs change training eligibility; specify a new matched study")
    if (panel.holding_month > primary["evaluation"]["development_last_holding_month"]).any():
        raise ValueError("Reserved outcomes cannot enter this development experiment")
    predictions = []
    for idx, row in panel[valid].iterrows():
        train = panel[(panel.exit <= row.decision_date) & valid]
        if len(train) < primary["training"]["min_completed_outer_targets"]:
            continue
        x, y = train[columns].to_numpy(float), np.stack(train.asset_returns)
        if any((train[f"{c}__source"] > train.decision_date).any() for c in rb.POLICY_FEATURES):
            raise ValueError("Policy source exceeds its historical cutoff")
        sources = np.column_stack([train[f"{c}__source"].to_numpy(dtype="datetime64[ns]") if c in rb.POLICY_FEATURES
                                   else np.full(len(train), np.datetime64("NaT", "ns")) for c in columns])
        alphas, errors = primary["ridge"]["alphas"], []
        for alpha in alphas:
            squared = []
            for end in range(max(24, len(train) // 2), len(train)):
                available = train.iloc[:end].exit <= train.iloc[end].decision_date
                pred = rb.fit_predict(x[:end][available], y[:end][available], x[end:end+1], alpha,
                                      feature_names=columns, primary=primary,
                                      policy_sources=sources[:end][available])[0]
                squared.append((pred - y[end]) ** 2)
            errors.append(np.mean(squared, axis=0))
        chosen = np.array(alphas)[np.argmin(np.array(errors), axis=0)]
        q, audit = np.empty(len(rb.ASSETS)), {}
        for j, asset in enumerate(rb.ASSETS):
            pred, info = rb.fit_predict(x, y, row[columns].to_numpy(float)[None, :], chosen[j], details=True,
                                        feature_names=columns, primary=primary, policy_sources=sources)
            q[j] = pred[0, j]
            contributions = info["contributions"][:, j]
            if not np.isclose(q[j], info["intercept"][j] + contributions.sum(), atol=1e-10, rtol=0):
                raise AssertionError("Forecast decomposition failed")
            if np.any(contributions[~info["supported"]] != 0):
                raise AssertionError("Disabled features must contribute zero")
            audit[asset] = {"intercept": info["intercept"][j], "features": [
                {"feature": c, "contribution": contributions[i],
                 "standardized_input": info["standardized_input"][i],
                 "observed_training_rows": int(info["observed_training_rows"][i]),
                 "training_scale": info["training_scale"][i],
                 "input_clipped": bool(info["input_clipped"][i]), "enabled": bool(info["supported"][i])}
                for i, c in enumerate(columns)]}
        predictions.append({"idx": idx, "date": row.date, "decision_date": row.decision_date,
                            "exit": row.exit, "q": q, "actual": row.asset_returns, "alpha": chosen,
                            "training_rows": len(train), "audit": audit, "last_training_exit": train.exit.max()})
    return predictions


def reproduce(actual, expected, fields):
    if len(actual) != len(expected):
        raise AssertionError("Frozen baseline coverage changed")
    for a, b in zip(actual, expected):
        if rb.serializable(a["date"]) != b["date"]:
            raise AssertionError("Frozen baseline dates changed")
        for field in fields:
            if not np.allclose(a[field], b[field], atol=1e-10, rtol=0):
                raise AssertionError(f"Frozen baseline failed to reproduce: {a['date']} {field}")


def forecast_scores(rows, mean_rows, base_rows):
    if [p["date"] for p in rows] != [p["date"] for p in mean_rows] or [p["date"] for p in rows] != [p["date"] for p in base_rows]:
        raise AssertionError("Forecast scoring dates differ")
    q, y = np.stack([p["q"] for p in rows]), np.stack([p["actual"] for p in rows])
    m, b = np.stack([p["q"] for p in mean_rows]), np.stack([p["q"] for p in base_rows])
    e, me, be = q-y, m-y, b-y
    return {"months": len(rows), "asset_months": q.size, "largest_absolute_forecast": float(np.abs(q).max()),
            "extreme_asset_months": int((np.abs(q) > .20).sum()),
            "assets": {a: {"mae": float(np.abs(e[:, j]).mean()), "rmse": float(np.sqrt((e[:, j]**2).mean())),
                            "oos_r2_vs_historical_mean": float(1-(e[:, j]**2).sum()/(me[:, j]**2).sum()),
                            "mae_change_vs_baseline": float(np.abs(e[:, j]).mean()-np.abs(be[:, j]).mean()),
                            "rmse_change_vs_baseline": float(np.sqrt((e[:, j]**2).mean())-np.sqrt((be[:, j]**2).mean()))}
                       for j, a in enumerate(rb.ASSETS)}}


def main():
    freeze = verify_freeze()
    original_path = rb.OUT / "research_results.json"
    if digest(original_path) != freeze["development_results_sha256"]:
        raise ValueError("Original frozen development artifact changed")
    original = json.loads(original_path.read_text())
    original_forecasts = json.loads((rb.OUT / "research_forecasts.json").read_text())
    spec, primary = json.loads(SPEC.read_text()), primary_spec()
    prices = rb.adjusted_prices()
    panel, monthly = rb.make_panel(prices)
    predictions, decisions = {}, {}
    for key, meta in spec["variants"].items():
        predictions[key] = extension_forecasts(panel, meta["extra"], primary)
        decisions[key] = rb.monthly_allocation(panel, monthly, predictions[key], primary=primary)
        if key == "baseline":
            reproduce(predictions[key], original_forecasts["corrected"], ["q", "alpha", "actual", "training_rows"])
            reproduce(decisions[key], original["development"]["results"]["corrected"]["decisions"],
                      ["forecast", "posterior", "weights", "actual", "view_error_variance", "turnover", "cost", "net_return"])
        print(key, len(predictions[key]), "forecasts;", len(decisions[key]), "holdings", flush=True)
    predictions["historical_mean"] = rb.forecasts(panel, [], historical_mean=True)
    decisions["historical_mean"] = rb.monthly_allocation(panel, monthly, predictions["historical_mean"], primary=primary)
    decisions["prior_only"] = rb.monthly_allocation(panel, monthly, predictions["baseline"], use_views=False, primary=primary)
    common = {d["date"] for d in decisions["baseline"]}
    forecast_dates = [p["date"] for p in predictions["baseline"]]
    for rows in decisions.values():
        if [d["date"] for d in rows] != [d["date"] for d in decisions["baseline"]]:
            raise AssertionError("Portfolio dates differ; no silent trimming")
    for rows in predictions.values():
        if [p["date"] for p in rows] != forecast_dates:
            raise AssertionError("Forecast dates differ; no silent trimming")
    for key, meta in rb.PASSIVE.items():
        decisions[key] = rb.passive_decisions(panel, meta["weights"], common)
    report = {"study_id": spec["id"], "generated_at": datetime.now(timezone.utc).isoformat(),
              "environment": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__},
              "specification": spec, "specification_sha256": digest(SPEC), "runner_sha256": digest(rb.ROOT / "src/corrected_signals.py"),
              "parent_freeze": freeze, "original_results_sha256": digest(original_path),
              "baseline_reproduction": {"passed": True, "absolute_tolerance": 1e-10},
              "reserved_test": {"evaluated": False}, "signal_observations": original["signal_observations"],
              "sources": original["sources"], "settings": original["settings"],
              "variants": {**{k: {**m, "kind": "model"} for k, m in spec["variants"].items()},
                           **{k: {**m, "kind": "model_reference"} for k, m in rb.MODEL_REFERENCES.items()},
                           **{k: {"name": m["name"], "color": m["color"], "kind": "reference"} for k, m in rb.PASSIVE.items()}}}
    report.update(research_diagnostics(decisions, predictions, prices, common, rb.summarize,
                                      spec["variants"], panel, rb.PERIODS, original["specification"]))
    report["periods"] = []
    for period in rb.PERIODS:
        results = {}
        for key, rows in decisions.items():
            chosen = [d for d in rows if pd.Timestamp(period["start"]) <= d["holding_month"] <= pd.Timestamp(period["end"])]
            stats, path = rb.summarize(chosen, prices)
            preds = [p for p in predictions.get(key, []) if p["date"] in {d["date"] for d in chosen}]
            results[key] = {"stats": stats, "path": path, "decisions": chosen, "forecast_diagnostics": forecast_diagnostics(preds)}
        for value in results.values():
            value["stats"]["difference_vs_baseline"] = value["stats"]["cumulative_return"]-results["baseline"]["stats"]["cumulative_return"]
        report["periods"].append({**period, "results": results})
    report["rolling_windows"] = []
    months = [d["holding_month"] for d in decisions["baseline"]]
    for end in range(11, len(months)):
        first, last = months[end-11], months[end]
        results = {k: rb.summarize([d for d in rows if first <= d["holding_month"] <= last], prices)[0] for k, rows in decisions.items()}
        report["rolling_windows"].append({"start": first, "end": last, "results": results})
    report["forecast_cohorts"] = {}
    for cohort in ["all_forecasts", "portfolio_dates"]:
        selected = {k: [p for p in rows if cohort == "all_forecasts" or p["date"] in common] for k, rows in predictions.items()}
        report["forecast_cohorts"][cohort] = {k: forecast_scores(rows, selected["historical_mean"], selected["baseline"]) for k, rows in selected.items()}
    bounds = np.array(primary["portfolio"]["bounds"])
    report["allocation_limits"] = {k: {"months": len(rows), "any_limit_months": int(np.any(np.isclose(np.stack([d["weights"] for d in rows]), bounds[:, 0]) | np.isclose(np.stack([d["weights"] for d in rows]), bounds[:, 1]), axis=1).sum())} for k, rows in decisions.items() if k not in rb.PASSIVE}
    verify_freeze()
    if digest(original_path) != freeze["development_results_sha256"]:
        raise AssertionError("Original results changed during run")
    for name, value in [("results", report), ("forecasts", predictions), ("decisions", decisions)]:
        (rb.OUT / f"corrected_signals_{name}.json").write_text(json.dumps(rb.serializable(value), indent=2, allow_nan=False)+"\n")
    print("Saved corrected_signals_results.json; primary freeze and original results preserved", flush=True)


if __name__ == "__main__":
    main()
