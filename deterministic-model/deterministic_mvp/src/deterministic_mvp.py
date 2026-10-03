#!/usr/bin/env python3
"""Deterministic macro-to-portfolio MVP.

The supplied workbook is sufficient for point-in-time macro signal construction.
Forecasting and portfolio construction run only when the missing monthly market
columns are supplied in a separate CSV. No data are synthesized.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


ASSETS = ["equity", "treasury", "ig_credit"]
RETURN_COLUMNS = [f"{asset}_return" for asset in ASSETS]
SUPPLEMENTAL_COLUMNS = ["anfci", "gpr", *RETURN_COLUMNS]


@dataclass(frozen=True)
class ReleaseSpec:
    name: str
    group: str
    ticker: str
    release_sheet: str
    reference_sheet: str


RELEASE_SPECS = (
    ReleaseSpec("nfp", "growth", "NFP TCH Index", "nfp_release_cleaned", "nfp_reference_raw"),
    ReleaseSpec("retail_sales", "growth", "RSTAMOM Index", "retail_sales_release_raw", "retail_sales_reference_raw"),
    ReleaseSpec("industrial_production", "growth", "IP CHNG Index", "industrial_production_release_r", "industrial_production_reference"),
    ReleaseSpec("ism_manufacturing", "growth", "NAPMPMI Index", "ism_manufacturing_release", "ism_manufacturing_reference"),
    ReleaseSpec("cpi", "inflation", "CPI CHNG Index", "cpi_release_raw", "cpi_reference_raw"),
    ReleaseSpec("core_cpi", "inflation", "CPUPXCHG Index", "core_cpi_release_raw", "core_cpi_reference_raw"),
    ReleaseSpec("ppi", "inflation", "FDIDFDMO Index", "ppi_release_raw", "ppi_reference_raw"),
    ReleaseSpec("ahe", "inflation", "AHE MOM% Index", "ahe_release_raw", "ahe_reference_raw"),
)

BASE_FEATURES = [
    "growth_surprise",
    "inflation_surprise",
    "policy_3m_level",
    "policy_6m_level",
    "policy_path_slope",
    "policy_3m_change",
    "policy_6m_change",
]
FULL_FEATURES = [
    *BASE_FEATURES,
    "anfci",
    "gpr",
    "growth_x_anfci",
    "inflation_x_anfci",
    "growth_x_gpr",
    "inflation_x_gpr",
]


def _month_end(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values).dt.to_period("M").dt.to_timestamp("M")


def _parse_yyyymmdd(values: pd.Series) -> pd.Series:
    cleaned = pd.to_numeric(values, errors="coerce").round().astype("Int64").astype("string")
    return pd.to_datetime(cleaned, format="%Y%m%d", errors="coerce")


def load_release_table(workbook: Path, spec: ReleaseSpec, min_history: int = 12) -> pd.DataFrame:
    release = pd.read_excel(workbook, sheet_name=spec.release_sheet)
    reference = pd.read_excel(workbook, sheet_name=spec.reference_sheet)

    release = release.rename(
        columns={
            "Release Date": "release_date",
            "Actual": "actual_first",
            "Median": "survey_median",
            "Average": "survey_average",
            "High": "survey_high",
            "Low": "survey_low",
            "Std. dev": "survey_std",
        }
    )
    release["release_date"] = pd.to_datetime(release["release_date"], errors="coerce")
    numeric = ["actual_first", "survey_median", "survey_average", "survey_high", "survey_low", "survey_std"]
    for column in numeric:
        release[column] = pd.to_numeric(release[column], errors="coerce")

    reference = reference.rename(
        columns={
            "Reference period date": "reference_period",
            "ECO release date": "eco_release_date",
            "Contributors": "survey_n",
        }
    )
    reference["reference_period"] = pd.to_datetime(reference["reference_period"], errors="coerce")
    reference["release_date"] = _parse_yyyymmdd(reference["eco_release_date"])
    reference = reference.sort_values(["release_date", "reference_period"])

    # Bloomberg occasionally maps two reference periods to one release date
    # (notably delayed 2025 releases). Preserve that ambiguity without
    # duplicating the single actual/consensus observation.
    reference_summary = (
        reference.groupby("release_date", as_index=False)
        .agg(
            reference_period=("reference_period", "max"),
            reference_period_count=("reference_period", "size"),
            survey_n=("survey_n", "max"),
            reference_periods=(
                "reference_period",
                lambda x: "|".join(pd.Series(x).dt.strftime("%Y-%m-%d")),
            ),
        )
    )

    clean = release.merge(reference_summary, on="release_date", how="left", validate="one_to_one")
    clean.insert(0, "variable", spec.name)
    clean.insert(1, "group", spec.group)
    clean.insert(2, "bloomberg_ticker", spec.ticker)
    clean["raw_surprise"] = clean["actual_first"] - clean["survey_median"]
    clean["survey_dispersion_surprise"] = clean["raw_surprise"] / clean["survey_std"].replace(0, np.nan)

    # Proposal definition: standardize by the historical forecast-error
    # distribution. shift(1) makes the scale point-in-time and prevents the
    # current observation from influencing its own z-score.
    prior_sigma = clean["raw_surprise"].expanding(min_periods=min_history).std(ddof=1).shift(1)
    clean["historical_surprise_sigma"] = prior_sigma
    clean["standardized_surprise"] = clean["raw_surprise"] / prior_sigma.replace(0, np.nan)
    clean["decision_month"] = _month_end(clean["release_date"])
    clean["reference_status"] = np.select(
        [clean["reference_period_count"].isna(), clean["reference_period_count"].gt(1)],
        ["missing", "ambiguous_multiple_periods"],
        default="matched",
    )
    return clean.sort_values("release_date").reset_index(drop=True)


def build_clean_releases(workbook: Path, min_history: int = 12) -> pd.DataFrame:
    tables = [load_release_table(workbook, spec, min_history=min_history) for spec in RELEASE_SPECS]
    combined = pd.concat(tables, ignore_index=True)
    return combined.sort_values(["release_date", "variable"]).reset_index(drop=True)


def build_monthly_features(workbook: Path, releases: pd.DataFrame) -> pd.DataFrame:
    monthly_indicator = (
        releases.groupby(["decision_month", "variable"], as_index=False)["standardized_surprise"]
        .mean()
        .pivot(index="decision_month", columns="variable", values="standardized_surprise")
    )
    monthly_indicator.columns.name = None

    group_map = {spec.name: spec.group for spec in RELEASE_SPECS}
    growth_cols = [name for name, group in group_map.items() if group == "growth"]
    inflation_cols = [name for name, group in group_map.items() if group == "inflation"]
    monthly_indicator["growth_surprise"] = monthly_indicator[growth_cols].mean(axis=1, skipna=True)
    monthly_indicator["inflation_surprise"] = monthly_indicator[inflation_cols].mean(axis=1, skipna=True)
    monthly_indicator["growth_indicator_count"] = monthly_indicator[growth_cols].notna().sum(axis=1)
    monthly_indicator["inflation_indicator_count"] = monthly_indicator[inflation_cols].notna().sum(axis=1)

    policy_3m = pd.read_excel(workbook, sheet_name="policy_3m").rename(
        columns={"Date": "policy_3m_date", "implied_policy_rate_3m_pct": "policy_3m_level"}
    )
    policy_6m = pd.read_excel(workbook, sheet_name="policy_6m").rename(
        columns={"Date": "policy_6m_date", "implied_policy_rate_6m_pct": "policy_6m_level"}
    )
    policy_3m["date"] = _month_end(policy_3m["policy_3m_date"])
    policy_6m["date"] = _month_end(policy_6m["policy_6m_date"])
    policy = policy_3m[["date", "policy_3m_date", "policy_3m_level"]].merge(
        policy_6m[["date", "policy_6m_date", "policy_6m_level"]], on="date", how="outer", validate="one_to_one"
    )
    policy["policy_data_date"] = policy[["policy_3m_date", "policy_6m_date"]].max(axis=1)
    policy = policy.drop(columns=["policy_3m_date", "policy_6m_date"]).sort_values("date")
    policy["policy_path_slope"] = policy["policy_6m_level"] - policy["policy_3m_level"]
    policy["policy_3m_change"] = policy["policy_3m_level"].diff()
    policy["policy_6m_change"] = policy["policy_6m_level"].diff()

    start = min(monthly_indicator.index.min(), policy["date"].min())
    end = max(monthly_indicator.index.max(), policy["date"].max())
    calendar = pd.DataFrame({"date": pd.date_range(start, end, freq="ME")})
    panel = calendar.merge(monthly_indicator.reset_index().rename(columns={"decision_month": "date"}), on="date", how="left")
    panel = panel.merge(policy, on="date", how="left")

    for column in [
        "policy_3m_level",
        "policy_6m_level",
        "policy_data_date",
        "policy_path_slope",
        "policy_3m_change",
        "policy_6m_change",
    ]:
        panel[column] = panel[column].ffill()
    panel["policy_age_months"] = (
        panel["date"].dt.to_period("M") - pd.to_datetime(panel["policy_data_date"]).dt.to_period("M")
    ).apply(lambda x: x.n if pd.notna(x) else np.nan)
    panel["macro_release_count"] = panel["date"].map(releases.groupby("decision_month").size()).fillna(0).astype(int)
    return panel.sort_values("date").reset_index(drop=True)


def build_quality_report(releases: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for spec in RELEASE_SPECS:
        data = releases[releases["variable"] == spec.name]
        rows.append(
            {
                "check": f"{spec.name}_release_rows",
                "status": "PASS" if len(data) > 0 else "FAIL",
                "value": len(data),
                "detail": f"{data['release_date'].min().date()} to {data['release_date'].max().date()}",
            }
        )
        rows.append(
            {
                "check": f"{spec.name}_reference_join",
                "status": "REVIEW" if data["reference_status"].ne("matched").any() else "PASS",
                "value": int(data["reference_status"].ne("matched").sum()),
                "detail": "release rows with missing or multi-period reference metadata",
            }
        )
    rows.extend(
        [
            {
                "check": "lookahead_safe_standardization",
                "status": "PASS",
                "value": 12,
                "detail": "each z-score uses only prior raw surprises; 12 prior observations required",
            },
            {
                "check": "complete_macro_months",
                "status": "PASS" if (features["growth_indicator_count"].eq(4) & features["inflation_indicator_count"].eq(4)).any() else "FAIL",
                "value": int((features["growth_indicator_count"].eq(4) & features["inflation_indicator_count"].eq(4)).sum()),
                "detail": "months with all four growth and all four inflation z-scores",
            },
            {
                "check": "required_model_inputs",
                "status": "BLOCKED",
                "value": 5,
                "detail": "workbook lacks ANFCI, GPR, and three asset-return series",
            },
        ]
    )
    return pd.DataFrame(rows)


def load_supplemental(path: Path) -> pd.DataFrame:
    supplemental = pd.read_csv(path)
    required = {"date", *SUPPLEMENTAL_COLUMNS}
    missing = sorted(required.difference(supplemental.columns))
    if missing:
        raise ValueError(f"Supplemental CSV is missing columns: {', '.join(missing)}")
    supplemental["date"] = _month_end(supplemental["date"])
    if supplemental["date"].duplicated().any():
        raise ValueError("Supplemental CSV must contain at most one row per month")
    for column in SUPPLEMENTAL_COLUMNS:
        supplemental[column] = pd.to_numeric(supplemental[column], errors="coerce")
    return supplemental.sort_values("date").reset_index(drop=True)


def add_model_features(panel: pd.DataFrame, supplemental: pd.DataFrame) -> pd.DataFrame:
    model = panel.merge(supplemental, on="date", how="left", validate="one_to_one")
    model["growth_x_anfci"] = model["growth_surprise"] * model["anfci"]
    model["inflation_x_anfci"] = model["inflation_surprise"] * model["anfci"]
    model["growth_x_gpr"] = model["growth_surprise"] * model["gpr"]
    model["inflation_x_gpr"] = model["inflation_surprise"] * model["gpr"]
    for target in RETURN_COLUMNS:
        model[f"next_{target}"] = model[target].shift(-1)
    return model


def _ridge_fit_predict(x_train: np.ndarray, y_train: np.ndarray, x_test: np.ndarray, alpha: float) -> np.ndarray:
    x_mean = x_train.mean(axis=0)
    x_std = x_train.std(axis=0, ddof=0)
    x_std[x_std == 0] = 1.0
    y_mean = y_train.mean()
    x_scaled = (x_train - x_mean) / x_std
    beta = np.linalg.solve(x_scaled.T @ x_scaled + alpha * np.eye(x_scaled.shape[1]), x_scaled.T @ (y_train - y_mean))
    return y_mean + ((x_test - x_mean) / x_std) @ beta


def _select_alpha(x: np.ndarray, y: np.ndarray, alphas: Iterable[float]) -> float:
    n = len(y)
    first = max(24, n // 2)
    if n <= first + 2:
        return 10.0
    scores: dict[float, float] = {}
    for alpha in alphas:
        errors = []
        for end in range(first, n):
            pred = _ridge_fit_predict(x[:end], y[:end], x[end : end + 1], alpha)[0]
            errors.append((pred - y[end]) ** 2)
        scores[float(alpha)] = float(np.mean(errors))
    return min(scores, key=scores.get)


def walk_forward_ridge(model: pd.DataFrame, min_train: int = 36) -> tuple[pd.DataFrame, dict[str, float]]:
    complete_x = model[FULL_FEATURES].notna().all(axis=1)
    predictions: list[dict[str, object]] = []
    latest_alphas: dict[str, float] = {}
    alpha_grid = [0.01, 0.1, 1.0, 10.0, 100.0]

    for asset, return_col in zip(ASSETS, RETURN_COLUMNS):
        target_col = f"next_{return_col}"
        for idx in model.index[complete_x]:
            train = model.loc[(model.index < idx) & complete_x & model[target_col].notna()]
            if len(train) < min_train:
                continue
            x_train = train[FULL_FEATURES].to_numpy(float)
            y_train = train[target_col].to_numpy(float)
            alpha = _select_alpha(x_train, y_train, alpha_grid)
            pred = float(_ridge_fit_predict(x_train, y_train, model.loc[[idx], FULL_FEATURES].to_numpy(float), alpha)[0])
            predictions.append(
                {
                    "date": model.at[idx, "date"],
                    "asset": asset,
                    "forecast_next_month": pred,
                    "realized_next_month": model.at[idx, target_col],
                    "alpha": alpha,
                    "training_rows": len(train),
                }
            )
            latest_alphas[asset] = alpha
    return pd.DataFrame(predictions), latest_alphas


def forecast_metrics(predictions: pd.DataFrame) -> pd.DataFrame:
    rows = []
    evaluated = predictions.dropna(subset=["realized_next_month"])
    for asset, data in evaluated.groupby("asset"):
        error = data["forecast_next_month"] - data["realized_next_month"]
        rows.append(
            {
                "asset": asset,
                "observations": len(data),
                "mae": error.abs().mean(),
                "rmse": math.sqrt(float((error**2).mean())),
                "directional_accuracy": ((data["forecast_next_month"] >= 0) == (data["realized_next_month"] >= 0)).mean(),
            }
        )
    return pd.DataFrame(rows)


def black_litterman_posterior(
    covariance: np.ndarray,
    forecast: np.ndarray,
    omega_diag: np.ndarray,
    benchmark: np.ndarray,
    tau: float = 0.05,
    risk_aversion: float = 2.5,
) -> np.ndarray:
    covariance = covariance + np.eye(len(benchmark)) * 1e-8
    prior = risk_aversion * covariance @ benchmark
    tau_cov_inv = np.linalg.pinv(tau * covariance)
    omega_inv = np.diag(1.0 / np.maximum(omega_diag, 1e-8))
    return np.linalg.solve(tau_cov_inv + omega_inv, tau_cov_inv @ prior + omega_inv @ forecast)


def optimize_weights_grid(
    expected: np.ndarray,
    covariance: np.ndarray,
    previous: np.ndarray,
    bounds: tuple[tuple[float, float], ...] = ((0.20, 0.70), (0.15, 0.60), (0.10, 0.40)),
    risk_aversion: float = 2.5,
    turnover_penalty: float = 0.00005,
    step: float = 0.01,
) -> np.ndarray:
    best_score = -np.inf
    best = previous.copy()
    equity_grid = np.arange(bounds[0][0], bounds[0][1] + step / 2, step)
    treasury_grid = np.arange(bounds[1][0], bounds[1][1] + step / 2, step)
    for equity in equity_grid:
        for treasury in treasury_grid:
            credit = 1.0 - equity - treasury
            if not bounds[2][0] - 1e-9 <= credit <= bounds[2][1] + 1e-9:
                continue
            weights = np.array([equity, treasury, credit])
            turnover = np.abs(weights - previous).sum()
            score = expected @ weights - 0.5 * risk_aversion * (weights @ covariance @ weights) - turnover_penalty * turnover
            if score > best_score:
                best_score = float(score)
                best = weights
    result = np.round(best / best.sum(), 12)
    result[2] = 1.0 - result[0] - result[1]
    return result


def portfolio_backtest(model: pd.DataFrame, predictions: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if predictions.empty:
        return pd.DataFrame(), pd.DataFrame()
    wide = predictions.pivot(index="date", columns="asset", values="forecast_next_month").dropna()
    benchmark = np.array([0.45, 0.35, 0.20])
    previous = benchmark.copy()
    rows = []
    evaluated_errors = predictions.dropna(subset=["realized_next_month"]).copy()
    evaluated_errors["error"] = evaluated_errors["forecast_next_month"] - evaluated_errors["realized_next_month"]

    for date, forecasts in wide.iterrows():
        history = model[(model["date"] <= date) & model[RETURN_COLUMNS].notna().all(axis=1)]
        if len(history) < 24:
            continue
        error_history = evaluated_errors[evaluated_errors["date"] < date]
        if error_history.groupby("asset").size().reindex(ASSETS, fill_value=0).min() < 12:
            continue
        covariance = history[RETURN_COLUMNS].tail(36).cov().to_numpy(float)
        omega = error_history.groupby("asset")["error"].var().reindex(ASSETS).to_numpy(float)
        q = forecasts.reindex(ASSETS).to_numpy(float)
        posterior = black_litterman_posterior(covariance, q, omega, benchmark)
        weights = optimize_weights_grid(posterior, covariance, previous)
        current = model.loc[model["date"] == date]
        if current.empty:
            continue
        realized = current[[f"next_{c}" for c in RETURN_COLUMNS]].iloc[0].to_numpy(float)
        turnover = float(np.abs(weights - previous).sum())
        gross = float(weights @ realized) if np.isfinite(realized).all() else np.nan
        benchmark_return = float(benchmark @ realized) if np.isfinite(realized).all() else np.nan
        cost = turnover * 5.0 / 10000.0
        rows.append(
            {
                "date": date,
                **{f"{asset}_weight": weights[i] for i, asset in enumerate(ASSETS)},
                **{f"{asset}_bl_return": posterior[i] for i, asset in enumerate(ASSETS)},
                "turnover": turnover,
                "gross_return": gross,
                "transaction_cost": cost,
                "net_return": gross - cost if np.isfinite(gross) else np.nan,
                "benchmark_return": benchmark_return,
            }
        )
        previous = weights

    backtest = pd.DataFrame(rows)
    if backtest.empty:
        return backtest, pd.DataFrame()
    returns = backtest["net_return"].dropna()
    benchmark_returns = backtest.loc[returns.index, "benchmark_return"]

    def summarize(series: pd.Series) -> dict[str, float]:
        wealth = (1 + series).cumprod()
        drawdown = wealth / wealth.cummax() - 1
        annual_return = (wealth.iloc[-1] ** (12 / len(series)) - 1) if len(series) else np.nan
        annual_vol = series.std(ddof=1) * math.sqrt(12)
        return {
            "annualized_return": annual_return,
            "annualized_volatility": annual_vol,
            "sharpe_zero_rf": annual_return / annual_vol if annual_vol > 0 else np.nan,
            "maximum_drawdown": drawdown.min(),
        }

    strategy_stats = summarize(returns)
    benchmark_stats = summarize(benchmark_returns)
    metrics = pd.DataFrame(
        [
            {
                "observations": len(returns),
                **strategy_stats,
                "average_turnover": backtest["turnover"].mean(),
                "certainty_equivalent_return": strategy_stats["annualized_return"]
                - 0.5 * 2.5 * strategy_stats["annualized_volatility"] ** 2,
                **{f"benchmark_{key}": value for key, value in benchmark_stats.items()},
                "annualized_excess_return": strategy_stats["annualized_return"]
                - benchmark_stats["annualized_return"],
            }
        ]
    )
    return backtest, metrics


def _json_value(value: object) -> object:
    if isinstance(value, (pd.Timestamp, np.datetime64)):
        return pd.Timestamp(value).strftime("%Y-%m-%d")
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if not np.isfinite(value) else float(value)
    if pd.isna(value):
        return None
    return value


def run(workbook: Path, output_dir: Path, supplemental_path: Path | None = None) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    releases = build_clean_releases(workbook)
    features = build_monthly_features(workbook, releases)
    quality = build_quality_report(releases, features)

    releases.to_csv(output_dir / "clean_releases.csv", index=False)
    features.to_csv(output_dir / "monthly_features.csv", index=False)
    surprise_columns = [
        "date",
        *[spec.name for spec in RELEASE_SPECS],
        "growth_surprise",
        "inflation_surprise",
        "growth_indicator_count",
        "inflation_indicator_count",
        "macro_release_count",
    ]
    surprise_signals = features[surprise_columns].copy()
    surprise_signals.to_csv(output_dir / "surprise_signals.csv", index=False)

    usable = features[features[BASE_FEATURES].notna().all(axis=1)].copy()
    latest = usable.iloc[-1].to_dict() if not usable.empty else {}
    latest_payload = {key: _json_value(value) for key, value in latest.items()}
    (output_dir / "latest_signal.json").write_text(json.dumps(latest_payload, indent=2), encoding="utf-8")
    latest_surprise = {key: latest_payload.get(key) for key in surprise_columns if key in latest_payload}
    (output_dir / "latest_surprise_signal.json").write_text(
        json.dumps(latest_surprise, indent=2), encoding="utf-8"
    )

    summary: dict[str, object] = {
        "status": "signal_only",
        "workbook": str(workbook.resolve()),
        "release_rows": len(releases),
        "feature_months": len(features),
        "first_complete_feature_month": _json_value(usable["date"].min()) if not usable.empty else None,
        "latest_complete_feature_month": _json_value(usable["date"].max()) if not usable.empty else None,
        "not_in_source_workbook": ["ANFCI", "GPR", "equity_return", "treasury_return", "ig_credit_return"],
    }

    if supplemental_path is not None:
        supplemental = load_supplemental(supplemental_path)
        required_row = quality["check"].eq("required_model_inputs")
        supplemental_complete = supplemental[SUPPLEMENTAL_COLUMNS].notna().all().all()
        quality.loc[required_row, "status"] = "PASS" if supplemental_complete else "REVIEW"
        quality.loc[required_row, "value"] = int(supplemental[SUPPLEMENTAL_COLUMNS].isna().sum().sum())
        quality.loc[required_row, "detail"] = (
            "online supplemental series supplied"
            if supplemental_complete
            else "supplemental series supplied with missing monthly values"
        )
        model = add_model_features(features, supplemental)
        model.to_csv(output_dir / "model_dataset.csv", index=False)
        predictions, alphas = walk_forward_ridge(model)
        predictions.to_csv(output_dir / "ridge_predictions.csv", index=False)
        fmetrics = forecast_metrics(predictions)
        fmetrics.to_csv(output_dir / "forecast_metrics.csv", index=False)
        backtest, pmetrics = portfolio_backtest(model, predictions)
        backtest.to_csv(output_dir / "portfolio_backtest.csv", index=False)
        pmetrics.to_csv(output_dir / "portfolio_metrics.csv", index=False)
        if not predictions.empty:
            latest_prediction_date = predictions["date"].max()
            latest_forecast = predictions[predictions["date"] == latest_prediction_date]
            latest_forecast_payload = {
                "decision_date": _json_value(latest_prediction_date),
                "forecast_horizon": "next month",
                "forecasts": {
                    row["asset"]: _json_value(row["forecast_next_month"])
                    for _, row in latest_forecast.iterrows()
                },
            }
            (output_dir / "latest_forecast.json").write_text(
                json.dumps(latest_forecast_payload, indent=2), encoding="utf-8"
            )
        if not backtest.empty:
            latest_portfolio = backtest.iloc[-1]
            latest_portfolio_payload = {
                "decision_date": _json_value(latest_portfolio["date"]),
                "weights": {
                    asset: _json_value(latest_portfolio[f"{asset}_weight"])
                    for asset in ASSETS
                },
                "turnover": _json_value(latest_portfolio["turnover"]),
            }
            (output_dir / "latest_portfolio.json").write_text(
                json.dumps(latest_portfolio_payload, indent=2), encoding="utf-8"
            )
        summary.update(
            {
                "status": "full_pipeline" if not predictions.empty else "insufficient_training_history",
                "supplemental": str(supplemental_path.resolve()),
                "prediction_rows": len(predictions),
                "portfolio_months": len(backtest),
                "latest_ridge_alphas": alphas,
                "supplemented_online": ["ANFCI", "GPR", "SPY", "IEF", "LQD"],
            }
        )

    quality.to_csv(output_dir / "data_quality.csv", index=False)
    (output_dir / "run_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the deterministic quantitative baseline MVP")
    parser.add_argument("--workbook", type=Path, required=True, help="Path to deterministic_data1.xlsx")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory for generated CSV/JSON outputs")
    parser.add_argument(
        "--supplemental",
        type=Path,
        default=None,
        help="Optional monthly CSV containing date, anfci, gpr, and three asset return columns",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    result = run(arguments.workbook, arguments.output_dir, arguments.supplemental)
    print(json.dumps(result, indent=2))
