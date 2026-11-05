"""Development forecast-horizon extension for the corrected model.

Run from deterministic_mvp:
  PYTHONPATH=/path/to/deps python3 src/forecast_horizons.py

This writes separate horizon artifacts and never changes the frozen one-month
primary or the earlier signal experiments.
"""
from __future__ import annotations

import json
import platform
from datetime import datetime, timezone

import numpy as np
import pandas as pd

import research_backtest as rb
from corrected_primary import digest, primary_spec, verify_freeze
from research_diagnostics import forecast_diagnostics

ROOT = rb.ROOT
OUT = rb.OUT
SPEC_PATH = ROOT / "research/horizons_spec.json"
HORIZONS = [3, 6]


def horizon_panel(prices: pd.DataFrame, months: int) -> pd.DataFrame:
    """Attach a cumulative H-month target to each point-in-time feature row."""
    base, _ = rb.make_panel(prices)
    rows = []
    for _, row in base.iterrows():
        target_month = pd.Timestamp(row.date) + pd.offsets.MonthEnd(months)
        exits = prices.index[prices.index > target_month]
        if len(exits) == 0:
            continue
        target_exit = exits[0]
        actual = prices.loc[target_exit].to_numpy(float) / prices.loc[row.entry].to_numpy(float) - 1
        record = row.to_dict()
        record.update(target_month=target_month, target_exit=target_exit,
                      target_return=actual, horizon_months=months)
        rows.append(record)
    result = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    # Keep the same development label as the one-month study. December 2022 is
    # the last holding month; its next-trading-day exit follows the same rule.
    return result[result.target_month <= pd.Timestamp("2022-12-31")].reset_index(drop=True)


def horizon_forecasts(panel: pd.DataFrame, primary: dict) -> list[dict]:
    columns = primary["features"]
    valid = panel[rb.REQUIRED_SIGNAL_FEATURES].notna().all(axis=1)
    result = []
    for idx, row in panel[valid].iterrows():
        train = panel[(panel.target_exit <= row.decision_date) & valid]
        if len(train) < primary["training"]["min_completed_outer_targets"]:
            continue
        x = train[columns].to_numpy(float)
        y = np.stack(train.target_return.to_numpy())
        sources = np.column_stack([
            train[f"{c}__source"].to_numpy(dtype="datetime64[ns]") if c in rb.POLICY_FEATURES
            else np.full(len(train), np.datetime64("NaT", "ns")) for c in columns
        ])
        errors = []
        for alpha in primary["ridge"]["alphas"]:
            squared = []
            for end in range(max(24, len(train) // 2), len(train)):
                available = train.iloc[:end].target_exit <= train.iloc[end].decision_date
                pred = rb.fit_predict(
                    x[:end][available], y[:end][available], x[end:end + 1], alpha,
                    feature_names=columns, primary=primary,
                    policy_sources=sources[:end][available],
                )[0]
                squared.append((pred - y[end]) ** 2)
            errors.append(np.mean(squared, axis=0))
        chosen = np.array(primary["ridge"]["alphas"])[np.argmin(np.array(errors), axis=0)]
        q = np.empty(len(rb.ASSETS))
        audit = {}
        for j, asset in enumerate(rb.ASSETS):
            pred, info = rb.fit_predict(
                x, y, row[columns].to_numpy(float)[None, :], chosen[j],
                details=True, feature_names=columns, primary=primary,
                policy_sources=sources,
            )
            q[j] = pred[0, j]
            contribution = info["contributions"][:, j]
            if not np.isclose(q[j], info["intercept"][j] + contribution.sum(), atol=1e-10, rtol=0):
                raise AssertionError("Horizon forecast decomposition failed")
            audit[asset] = {"intercept": info["intercept"][j], "features": [
                {"feature": c, "contribution": contribution[i],
                 "standardized_input": info["standardized_input"][i],
                 "enabled": bool(info["supported"][i])}
                for i, c in enumerate(columns)
            ]}
        result.append({"idx": idx, "date": row.date, "decision_date": row.decision_date,
                       "entry": row.entry, "target_month": row.target_month,
                       "target_exit": row.target_exit, "q": q,
                       "actual": row.target_return, "alpha": chosen,
                       "training_rows": len(train), "last_training_exit": train.target_exit.max(),
                       "audit": audit})
    return result


def historical_mean_forecasts(panel: pd.DataFrame, primary: dict) -> list[dict]:
    valid = panel[rb.REQUIRED_SIGNAL_FEATURES].notna().all(axis=1)
    result = []
    for idx, row in panel[valid].iterrows():
        train = panel[(panel.target_exit <= row.decision_date) & valid]
        if len(train) < primary["training"]["min_completed_outer_targets"]:
            continue
        result.append({"idx": idx, "date": row.date, "decision_date": row.decision_date,
                       "entry": row.entry, "target_month": row.target_month,
                       "target_exit": row.target_exit, "q": train.target_return.to_numpy().mean(axis=0),
                       "actual": row.target_return, "alpha": None,
                       "training_rows": len(train), "last_training_exit": train.target_exit.max(),
                       "audit": {}})
    return result


def score_forecasts(rows: list[dict], mean_rows: list[dict]) -> dict:
    if [r["date"] for r in rows] != [r["date"] for r in mean_rows]:
        raise AssertionError("Horizon and historical-mean forecast dates differ")
    q = np.stack([r["q"] for r in rows]); actual = np.stack([r["actual"] for r in rows]); mean = np.stack([r["q"] for r in mean_rows])
    error, mean_error = q - actual, mean - actual
    return {
        "months": len(rows), "asset_months": int(q.size),
        "largest_absolute_forecast": float(np.abs(q).max()),
        "extreme_asset_months": int((np.abs(q) > .20).sum()),
        "assets": {asset: {
            "mae": float(np.abs(error[:, j]).mean()),
            "rmse": float(np.sqrt(np.mean(error[:, j] ** 2))),
            "oos_r2_vs_historical_mean": float(1 - np.sum(error[:, j] ** 2) / np.sum(mean_error[:, j] ** 2)),
            "forecast_min": float(q[:, j].min()), "forecast_max": float(q[:, j].max()),
            "realized_min": float(actual[:, j].min()), "realized_max": float(actual[:, j].max()),
        } for j, asset in enumerate(rb.ASSETS)},
    }


def select_nonoverlapping(rows: list[dict]) -> list[dict]:
    selected, last_exit = [], None
    for row in rows:
        if last_exit is None or row["entry"] > last_exit:
            selected.append(row)
            last_exit = row["target_exit"]
    return selected


def portfolio_decisions(panel: pd.DataFrame, predictions: list[dict], prices: pd.DataFrame,
                        primary: dict, use_views: bool = True, fixed_weights: np.ndarray | None = None) -> list[dict]:
    selected = select_nonoverlapping(predictions)
    previous = np.array(primary["portfolio"]["starting_weights"], dtype=float)
    decisions = []
    bounds = primary["portfolio"]["bounds"]
    for pred in selected:
        row = panel.loc[pred["idx"]]
        past = [p for p in predictions if p["target_exit"] <= pred["decision_date"]]
        if len(past) < primary["portfolio"]["min_prior_errors"]:
            continue
        cov_rows = panel[panel.target_exit <= pred["decision_date"]].dropna(subset=["target_return"])
        cov_rows = cov_rows.tail(primary["portfolio"]["covariance_months"])
        if len(cov_rows) < 12:
            continue
        covariance = np.cov(np.stack(cov_rows.target_return.to_numpy()), rowvar=False, ddof=1)
        if use_views:
            errors = np.stack([p["q"] - p["actual"] for p in past])
            omega = errors.var(axis=0, ddof=1)
            expected = rb.black_litterman_posterior(
                covariance, pred["q"], omega, previous,
                tau=primary["portfolio"]["tau"], risk_aversion=primary["portfolio"]["risk_aversion"],
            )
        else:
            omega = None
            expected = primary["portfolio"]["risk_aversion"] * covariance @ previous
        target = fixed_weights if fixed_weights is not None else None
        weights = target.copy() if target is not None else rb.optimize_weights_grid(
            expected, covariance, previous, bounds=bounds,
            risk_aversion=primary["portfolio"]["risk_aversion"],
            turnover_penalty=primary["portfolio"]["turnover_penalty"],
            step=primary["portfolio"]["grid_step"],
        )
        actual = np.asarray(pred["actual"], dtype=float)
        turnover = float(np.abs(weights - previous).sum())
        gross = float(weights @ actual)
        cost = turnover * primary["portfolio"]["cost_bps_per_dollar_traded"] / 10000
        net = (1 - cost) * (1 + gross) - 1
        decisions.append({"date": pred["date"], "decision_date": pred["decision_date"],
                          "entry": pred["entry"], "target_month": pred["target_month"],
                          "exit": pred["target_exit"], "weights": weights,
                          "forecast": pred["q"] if use_views else None,
                          "posterior": expected, "actual": actual,
                          "view_error_variance": omega, "gross_return": gross,
                          "turnover": turnover, "cost": cost, "net_return": net,
                          "training_rows": pred["training_rows"],
                          "last_training_exit": pred["last_training_exit"]})
        previous = weights * (1 + actual) / (1 + gross)
    return decisions


def summarize_horizon(decisions: list[dict], prices: pd.DataFrame, months: int) -> tuple[dict, list[dict]]:
    if not decisions:
        raise ValueError("No non-overlapping horizon holdings")
    wealth, path = 100., [{"date": decisions[0]["entry"], "wealth": 100.}]
    for row in decisions:
        segment = prices.loc[row["entry"]:row["exit"]]
        opening = wealth * (1 - row["cost"])
        values = opening * ((segment / segment.iloc[0]).to_numpy() @ row["weights"])
        path.extend({"date": date, "wealth": float(value)} for date, value in zip(segment.index, values))
        wealth = float(values[-1])
    values = np.array([point["wealth"] for point in path])
    drawdowns = values / np.maximum.accumulate(values) - 1
    returns = np.array([row["net_return"] for row in decisions])
    annualized_volatility = float(returns.std(ddof=1) * np.sqrt(12 / months)) if len(returns) > 1 else None
    annualized_return = float((wealth / 100) ** (12 / (months * len(decisions))) - 1)
    stats = {"holding_periods": len(decisions), "horizon_months": months,
             "cumulative_return": wealth / 100 - 1, "annualized_return": annualized_return,
             "annualized_volatility": annualized_volatility,
             "maximum_drawdown": float(drawdowns.min()),
             "average_turnover": float(np.mean([d["turnover"] for d in decisions])),
             "cost_bps_sum": float(sum(d["cost"] for d in decisions) * 10000),
             "entry": decisions[0]["entry"], "exit": decisions[-1]["exit"], "end_value": wealth}
    return stats, path


def serializable(value):
    return rb.serializable(value)


def main():
    freeze = verify_freeze()
    primary = primary_spec()
    original = json.loads((OUT / "research_results.json").read_text())
    prices = rb.adjusted_prices()
    output = {"study_id": json.loads(SPEC_PATH.read_text())["id"],
              "generated_at": datetime.now(timezone.utc).isoformat(),
              "environment": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__},
              "specification": json.loads(SPEC_PATH.read_text()), "specification_sha256": digest(SPEC_PATH),
              "parent_freeze": freeze, "one_month_reference": original["primary"], "horizons": {},
              "reserved_test": {"evaluated": False}}
    for months in HORIZONS:
        panel = horizon_panel(prices, months)
        forecasts = horizon_forecasts(panel, primary)
        means = historical_mean_forecasts(panel, primary)
        if len(forecasts) != len(means) or not forecasts:
            raise AssertionError(f"Horizon {months} has no matched forecast sample")
        decisions = portfolio_decisions(panel, forecasts, prices, primary)
        mean_decisions = portfolio_decisions(panel, means, prices, primary)
        if not decisions or not mean_decisions or [d["date"] for d in decisions] != [d["date"] for d in mean_decisions]:
            raise AssertionError(f"Horizon {months} portfolio dates are not matched")
        fixed = {}
        for name, weights in rb.PASSIVE.items():
            fixed[name] = portfolio_decisions(panel, forecasts, prices, primary, fixed_weights=weights["weights"])
        portfolio = {"corrected": decisions, "historical_mean": mean_decisions, **fixed}
        portfolio_stats = {}
        paths = {}
        for key, rows in portfolio.items():
            portfolio_stats[key], paths[key] = summarize_horizon(rows, prices, months)
        base_return = portfolio_stats["corrected"]["cumulative_return"]
        for stats in portfolio_stats.values():
            stats["difference_vs_corrected"] = stats["cumulative_return"] - base_return
        output["horizons"][str(months)] = {
            "months": months, "forecast_dates": [r["date"] for r in forecasts],
            "target_first_month": forecasts[0]["target_month"], "target_last_month": forecasts[-1]["target_month"],
            "forecast_scores": score_forecasts(forecasts, means),
            "historical_mean_forecast_scores": score_forecasts(means, means),
            "portfolio_dates": [d["date"] for d in decisions],
            "portfolio_scores": {"corrected": forecast_diagnostics(forecasts), "historical_mean": forecast_diagnostics(means)},
            "portfolio_results": portfolio_stats, "portfolio_paths": paths,
            "forecasts": forecasts, "historical_mean_forecasts": means, "portfolio_decisions": portfolio,
        }
        print(months, len(forecasts), "monthly forecasts;", len(decisions), "non-overlapping holdings", flush=True)
    (OUT / "horizon_results.json").write_text(json.dumps(serializable(output), indent=2, allow_nan=False) + "\n")
    print("Saved", OUT / "horizon_results.json", "with one-month reference preserved")


if __name__ == "__main__":
    main()
