"""Explanatory diagnostics; never used to choose forecasts or portfolio weights."""
from __future__ import annotations

import numpy as np
from research_inference import inference_report

ASSETS = ["equity", "treasury", "ig_credit"]


def forecast_diagnostics(rows: list[dict]) -> dict:
    if not rows:
        return {}
    result = {}
    for j, asset in enumerate(ASSETS):
        q = np.array([p["q"][j] for p in rows])
        actual = np.array([p["actual"][j] for p in rows])
        error = q - actual
        worst = rows[int(np.argmax(np.abs(error)))]
        audit = worst.get("audit", {}).get(asset, {})
        features = sorted(audit.get("features", []), key=lambda f: abs(f["contribution"]), reverse=True)
        result[asset] = {
            "observations": len(rows), "rmse": float(np.sqrt(np.mean(error ** 2))),
            "mae": float(np.abs(error).mean()), "bias": float(error.mean()),
            "forecast_min": float(q.min()), "forecast_max": float(q.max()),
            "realized_min": float(actual.min()), "realized_max": float(actual.max()),
            "forecast_over_20pct_months": int((np.abs(q) > .20).sum()),
            "worst_decision": worst["decision_date"], "worst_forecast": worst["q"][j],
            "worst_realized": worst["actual"][j], "worst_error": worst["q"][j] - worst["actual"][j],
            "worst_intercept": audit.get("intercept"), "worst_features": features,
        }
    return result


def monthly_attribution(selected: list[dict], baseline: list[dict]) -> list[dict]:
    base_by_date = {d["date"]: d for d in baseline}
    result = []
    for d in selected:
        b = base_by_date[d["date"]]
        actual = np.asarray(d["actual"])
        weight_delta = np.asarray(d["weights"]) - b["weights"]
        contributions = weight_delta * actual
        cost_effect = -d["cost"] * (1 + d["gross_return"]) + b["cost"] * (1 + b["gross_return"])
        difference = d["net_return"] - b["net_return"]
        if not np.isclose(contributions.sum() + cost_effect, difference, atol=1e-12):
            raise AssertionError("Monthly attribution does not reconcile")
        result.append({
            "date": d["date"], "holding_month": d["holding_month"],
            "forecast_delta": np.asarray(d["forecast"]) - b["forecast"],
            "posterior_delta": np.asarray(d["posterior"]) - b["posterior"],
            "weight_delta": weight_delta, "asset_return_contribution": contributions,
            "cost_effect": cost_effect, "net_return_difference": difference,
        })
    return result


def research_diagnostics(all_decisions, all_forecasts, prices, common, summarize, variants, panel, periods, specification):

    decisions = {k: [d for d in rows if d["date"] in common] for k, rows in all_decisions.items()}
    primary = {}
    for key, rows in decisions.items():
        stats, path = summarize(rows, prices)
        preds = [p for p in all_forecasts.get(key, []) if p["date"] in common]
        primary[key] = {"stats": stats, "path": path, "forecast_diagnostics": forecast_diagnostics(preds), "decisions": rows}
    base_return = primary["baseline"]["stats"]["cumulative_return"]
    for result in primary.values():
        result["stats"]["difference_vs_baseline"] = result["stats"]["cumulative_return"] - base_return
    calendar_years = []
    for year in sorted({d["holding_month"].year for d in decisions["baseline"]}):
        results = {}
        for key, rows in decisions.items():
            selected = [d for d in rows if d["holding_month"].year == year]
            stats, _ = summarize(selected, prices)
            results[key] = stats
        calendar_years.append({"year": year, "partial_year": results["baseline"]["months"] != 12, "results": results})
    excluded = {}
    for key, rows in decisions.items():
        chosen = [d for d in rows if d["holding_month"].year != 2020]
        excluded[key] = {"months": len(chosen), "cumulative_return": float(np.prod([1+d["net_return"] for d in chosen])-1)}
    return {
        **inference_report(decisions, panel, periods, specification),
        "development": {"start": min(common), "end": max(common), "results": primary},
        "calendar_years": calendar_years,
        "excluding_2020": {"description": "Compound retained months from the continuous run; skip 2020 without retraining or restarting holdings. Disconnected intervals, not a tradable uninterrupted path.", "results": excluded},
        "monthly_attribution": {key: monthly_attribution(decisions[key], decisions["baseline"]) for key in variants if key != "baseline"},
        "unit_audit": {
            "targets": "Decimal total returns over entry-close to next rebalance-close; not percent points or annualized returns.",
            "covariance": "Monthly decimal calendar-close returns; no annualization before BL.",
            "prior_and_posterior": "Monthly decimal returns with tau 0.05 and risk aversion 2.5. No cash series is supplied: views are total returns, not cash-adjusted excess returns.",
            "warning_threshold": "Absolute forecast above 20% per holding month is flagged for inspection only; never clipped by this diagnostic.",
            "vintages": "Latest revised histories with assumed lags. These diagnostics do not reconstruct real-time vintages.",
        },
    }
