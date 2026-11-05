"""Reproducible, past-only signal experiments for the deterministic MVP.

Run from deterministic_mvp: python3 src/research_backtest.py
This writes a separate research artifact; it does not overwrite the original run.
"""
from __future__ import annotations

import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from research_diagnostics import research_diagnostics, forecast_diagnostics
from research_stability import stability_report
from corrected_primary import primary_spec, policy_source_dates, policy_support, verify_freeze, FREEZE_PATH, PRIMARY_SPEC_PATH, SOURCE_FILES

from deterministic_mvp import (
    ASSETS, FULL_FEATURES, REQUIRED_SIGNAL_FEATURES,
    build_clean_releases, build_monthly_features,
    black_litterman_posterior, optimize_weights_grid,
)

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "research" / "raw"
OUT = ROOT / "research" / "outputs"
WORKBOOK_NAME = "deterministic_data2 - Oct26.xlsx"
# The repository keeps inputs beside deterministic_mvp. The second location
# also supports the original capstone workspace layout.
WORKBOOK = next(
    (p for p in [ROOT.parent / WORKBOOK_NAME, ROOT.parents[1] / WORKBOOK_NAME] if p.exists()),
    ROOT.parent / WORKBOOK_NAME,
)
BENCHMARK = np.array([.45, .35, .20])
VARIANTS = {
    "corrected": {"name": "Corrected primary · clipped + policy checks", "extra": [], "color": "#087e8b", "primary": True},
    "baseline": {"name": "Original model · unstable diagnostic", "extra": [], "color": "#008aa1"},
    "claims": {"name": "+ Unemployment claims", "extra": ["claims_change_3m"], "color": "#9261bd"},
    "credit": {"name": "+ Credit spread", "extra": ["credit_level", "credit_change_1m"], "color": "#db7931"},
    "curve": {"name": "+ Yield curve", "extra": ["curve_level"], "color": "#3b71d1"},
    "robust": {"name": "Robust-input sensitivity", "extra": [], "color": "#ad4c69", "robust": True},
    "clip_only": {"name": "Input clipping only", "extra": [], "color": "#c56483", "robust": True, "stronger_shrinkage": False},
    "shrink_only": {"name": "Stronger shrinkage only", "extra": [], "color": "#6867b1", "stronger_shrinkage": True},
    "supported_policy": {"name": "Policy coverage safeguard", "extra": [], "color": "#39786d", "min_policy_observations": 12},
    "no_policy": {"name": "Without policy fields", "extra": [], "color": "#76633d", "include_policy": False},
}
POLICY_FEATURES = [c for c in FULL_FEATURES if c.startswith("policy_")]
SPEC_PATH = ROOT / "research" / "experiment_spec.json"
MODEL_REFERENCES = {
    "historical_mean": {"name": "Historical mean → BL", "color": "#5f6ea1"},
    "prior_only": {"name": "BL prior only", "color": "#877f78"},
}
PASSIVE = {
    "fixed453520": {"name": "Fixed 45 / 35 / 20", "weights": BENCHMARK, "color": "#64748b"},
    "sixtyForty": {"name": "Fixed 60% SPY / 40% IEF", "weights": np.array([.6, .4, 0]), "color": "#4f9677"},
    "spyOnly": {"name": "100% SPY", "weights": np.array([1., 0, 0]), "color": "#bd9526"},
}
PERIODS = [
    {"id": "covid_shock", "name": "COVID shock", "start": "2020-02-29", "end": "2020-04-30", "description": "February–April 2020 holding months. Tests loss protection during the sudden market disruption."},
    {"id": "covid_recovery", "name": "COVID recovery", "start": "2020-05-31", "end": "2020-12-31", "description": "May–December 2020 holding months. Tests participation in the recovery after the initial shock."},
    {"id": "inflation_2022", "name": "Inflation / rate shock", "start": "2022-01-31", "end": "2022-12-31", "description": "January–December 2022 holding months. Tests the model during the inflation and rate-shock environment."},
]


def input_hashes() -> dict[str, str]:
    """Fingerprint every raw data file consumed by this experiment.

    The workbook is fingerprinted separately because it lives above ROOT.
    Availability lags do not turn these latest-history inputs into real-time vintages.
    """
    inputs = [
        *sorted(RAW.glob("*")),
        ROOT / "data/raw/anfci_fred.csv",
        ROOT / "data/raw/gpr_caldara_iacoviello.dta",
    ]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in inputs if p.is_file()}


def adjusted_prices() -> pd.DataFrame:
    prices = []
    for ticker, asset in zip(["spy", "ief", "lqd"], ASSETS):
        result = json.loads((RAW / f"{ticker}_history.json").read_text())["chart"]["result"][0]
        dates = pd.to_datetime(result["timestamp"], unit="s", utc=True).tz_convert("America/New_York").normalize().tz_localize(None)
        price = pd.Series(result["indicators"]["adjclose"][0]["adjclose"], index=dates, name=asset).dropna()
        if price.index.has_duplicates or not (price > 0).all():
            raise ValueError(f"Invalid price history: {ticker}")
        prices.append(price)
    return pd.concat(prices, axis=1, join="inner").sort_index()


def economic_observations() -> dict[str, pd.DataFrame]:
    result = {}
    for key, series in [("claims", "ICSA"), ("credit", "BAA10Y"), ("curve", "T10Y3M")]:
        df = pd.read_csv(RAW / f"{key}.csv", parse_dates=["observation_date"])
        df[series] = pd.to_numeric(df[series], errors="coerce")
        df = df.dropna().sort_values("observation_date")
        # Weekly claims refer to a Saturday and normally arrive on Thursday.
        # Market yields/spreads use a conservative one-business-day delay.
        df["available_date"] = df["observation_date"] + (pd.Timedelta(days=5) if key == "claims" else pd.offsets.BDay(1))
        if key == "claims":
            df["value"] = df[series].rolling(4, min_periods=4).mean()
        else:
            df["value"] = df[series]
        result[key] = df
    return result


def make_panel(prices: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    releases = build_clean_releases(WORKBOOK)
    features = build_monthly_features(WORKBOOK, releases).set_index("date")
    anfci = pd.read_csv(ROOT / "data/raw/anfci_fred.csv", parse_dates=["observation_date"])
    anfci["available_date"] = anfci.observation_date + pd.Timedelta(days=5)
    gpr = pd.read_stata(ROOT / "data/raw/gpr_caldara_iacoviello.dta", columns=["month", "GPR"])
    gpr["available_date"] = pd.to_datetime(gpr.month) + pd.offsets.MonthBegin(1) + pd.Timedelta(days=6)
    economic = economic_observations()
    policy_sources = policy_source_dates(WORKBOOK)
    rows = []
    # Build an unscored lookback before training so every candidate feature,
    # including the three-month claims change, exists by February 2015.
    for date in pd.date_range("2014-08-31", "2022-11-30", freq="ME"):
        before = prices.loc[prices.index <= date]
        after = prices.index[prices.index > date]
        next_month = date + pd.offsets.MonthEnd(1)
        exits = prices.index[prices.index > next_month]
        if before.empty or len(after) == 0 or len(exits) == 0 or date not in features.index:
            continue
        decision_date, entry, exit_date = before.index[-1], after[0], exits[0]
        row = features.loc[date].to_dict()
        row.update(date=date, decision_date=decision_date, holding_month=next_month, entry=entry, exit=exit_date)
        # Month-end workbook snapshots can occur after the last trading-day cutoff.
        # Retain the source date for audit, but never consume those policy values.
        row["policy_withheld_after_cutoff"] = bool(pd.notna(row.get("policy_data_date")) and row["policy_data_date"] > decision_date)
        if row["policy_withheld_after_cutoff"]:
            for feature in POLICY_FEATURES:
                row[feature] = np.nan
        for feature in POLICY_FEATURES:
            source = policy_sources.loc[date, f"{feature}__source"] if date in policy_sources.index else pd.NaT
            row[f"{feature}__source"] = source if pd.notna(source) and source <= decision_date else pd.NaT
        # Rebuild the month's composites at the actual last trading-day cutoff.
        known = releases[(releases.decision_month == date) & (releases.release_date <= decision_date)]
        for group in ["growth", "inflation"]:
            row[f"{group}_surprise"] = known.loc[known.group == group].groupby("variable").standardized_surprise.mean().mean()
        a = anfci.loc[anfci.available_date <= decision_date].dropna(subset=["ANFCI"])
        g = gpr.loc[gpr.available_date <= decision_date].dropna(subset=["GPR"])
        row["anfci"] = float(a.iloc[-1].ANFCI) if not a.empty else np.nan
        row["anfci_source_date"] = a.iloc[-1].observation_date if not a.empty else pd.NaT
        row["anfci_assumed_available_date"] = a.iloc[-1].available_date if not a.empty else pd.NaT
        row["gpr_source_date"] = g.iloc[-1].month if not g.empty else pd.NaT
        row["gpr_assumed_available_date"] = g.iloc[-1].available_date if not g.empty else pd.NaT
        row["gpr"] = float(g.iloc[-1].GPR) if not g.empty else np.nan
        for group in ["growth", "inflation"]:
            for risk in ["anfci", "gpr"]:
                row[f"{group}_x_{risk}"] = row[f"{group}_surprise"] * row[risk]
        for key, df in economic.items():
            known_values = df[(df.available_date <= decision_date) & df.value.notna()]
            last = known_values.iloc[-1]
            row[f"{key}_source_date"] = last.observation_date
            row[f"{key}_available_date"] = last.available_date
            row[f"{key}_level"] = float(last.value)
        row["asset_returns"] = (prices.loc[exit_date] / prices.loc[entry] - 1).to_numpy(float)
        rows.append(row)
    panel = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    panel["claims_change_3m"] = panel.claims_level / panel.claims_level.shift(3) - 1
    panel["credit_change_1m"] = panel.credit_level.diff()
    # Calendar-month returns are known by decision close and used for covariance.
    monthly = prices.resample("ME").last().pct_change().dropna()
    return panel[panel.date >= "2015-02-28"].reset_index(drop=True), monthly


def fit_predict(x: np.ndarray, y: np.ndarray, test: np.ndarray, alpha: float,
                robust: bool = False, details: bool = False,
                feature_names: list[str] | None = None, min_policy_observations: int = 0,
                primary: dict | None = None, policy_sources: np.ndarray | None = None):
    """All preprocessing is fitted on this training fold, never on test rows.

    The optional robust sensitivity clips *inputs*, not predicted returns, to
    fixed training quantiles. The original model remains unchanged for comparison.
    """
    if primary:
        robust = True
        if feature_names is None:
            raise ValueError("Corrected primary requires named features")
    if min_policy_observations and (feature_names is None or len(feature_names) != x.shape[1]):
        raise ValueError("Feature names are required for the policy coverage safeguard")
    original_x, original_test = x.copy(), test.copy()
    observed = np.isfinite(x).sum(axis=0)
    supported = np.ones(x.shape[1], dtype=bool)
    if min_policy_observations:
        supported = np.array([not c.startswith("policy_") or observed[i] >= min_policy_observations
                              for i, c in enumerate(feature_names)])
    medians = pd.DataFrame(np.where(np.isfinite(x), x, np.nan)).median().fillna(0).to_numpy()
    x = np.where(np.isfinite(x), x, medians)
    test = np.where(np.isfinite(test), test, medians)
    raw_test = test.copy()
    if robust:
        quantiles = primary["preprocessing"]["clip_quantiles"] if primary else [.01, .99]
        lower, upper = np.quantile(x, quantiles, axis=0)
        x, test = np.clip(x, lower, upper), np.clip(test, lower, upper)
    mean = x.mean(axis=0)
    std = x.std(axis=0)
    processed_std = std.copy()
    constant = std < (primary["preprocessing"]["numerical_constant_std"] if primary else 1e-12)
    guard = None
    if primary:
        guard = policy_support(original_x, processed_std, feature_names, policy_sources, primary["preprocessing"]["policy"])
        supported &= guard["supported"] & ~constant
        for i in np.flatnonzero(constant):
            guard["disabled_reasons"][i].append("constant_processed_training")
    std[constant] = 1
    scaled = (x - mean) / std
    standardized_test = (test - mean) / std
    # Disabling a feature must also disable its test input, not just its training values.
    scaled[:, ~supported] = 0.0
    standardized_test[:, ~supported] = 0.0
    y_mean = y.mean(axis=0)
    beta = np.linalg.solve(scaled.T @ scaled + alpha * np.eye(x.shape[1]), scaled.T @ (y - y_mean))
    prediction = y_mean + standardized_test @ beta
    if not np.isfinite(prediction).all():
        raise ValueError("Non-finite Ridge forecast; inspect training inputs and scaling")
    if not details:
        return prediction
    return prediction, {
        "intercept": y_mean, "contributions": standardized_test[0, :, None] * beta,
        "standardized_input": standardized_test[0], "observed_training_rows": observed,
        "training_scale": std, "constant_training_column": constant,
        "input_clipped": (test[0] != raw_test[0]), "supported": supported,
        "training_return_min": y.min(axis=0), "training_return_max": y.max(axis=0),
        "raw_input": original_test[0], "input_imputed": ~np.isfinite(original_test[0]),
        "imputation_median": medians, "training_mean": mean,
        "processed_input": test[0], "coefficient": beta,
        "distinct_observed_values": np.array([len(np.unique(c[np.isfinite(c)])) for c in original_x.T]),
        "processed_std": processed_std, "policy_guard": guard,
    }


def forecasts(panel: pd.DataFrame, extra: list[str], include_policy: bool = True,
              robust: bool = False, historical_mean: bool = False,
              stronger_shrinkage: bool | None = None, min_policy_observations: int = 0,
              primary: dict | None = None) -> list[dict]:
    columns = [c for c in FULL_FEATURES if include_policy or c not in POLICY_FEATURES] + extra
    if primary:
        if columns != primary["features"] or extra or not include_policy or historical_mean:
            raise ValueError("Corrected primary requires its recorded feature set")
        if (panel.holding_month > primary["evaluation"]["development_last_holding_month"]).any():
            raise ValueError("Reserved holding months cannot enter the corrected-primary development run")
        robust, stronger_shrinkage = True, False
    valid = panel[[*REQUIRED_SIGNAL_FEATURES, *extra]].notna().all(axis=1)
    predictions = []
    for idx, row in panel[valid].iterrows():
        train = panel[(panel.exit <= row.decision_date) & valid]
        if len(train) < (primary["training"]["min_completed_outer_targets"] if primary else 36):
            continue
        x = train[columns].to_numpy(float)
        y = np.stack(train.asset_returns.to_numpy())
        if primary and any((train[f"{c}__source"] > train.decision_date).any() for c in POLICY_FEATURES):
            raise ValueError("Policy source after its historical decision cutoff")
        sources = np.column_stack([train[f"{c}__source"].to_numpy(dtype="datetime64[ns]") if c in POLICY_FEATURES
                                   else np.full(len(train), np.datetime64("NaT", "ns")) for c in columns]) if primary else None
        audit = {}
        if historical_mean:
            q, chosen = y.mean(axis=0), None
        else:
            errors = []
            stronger = robust if stronger_shrinkage is None else stronger_shrinkage
            alphas = primary["ridge"]["alphas"] if primary else ([1., 10., 100., 1000.] if stronger else [.01, .1, 1., 10., 100.])
            folds = range(max(24, len(train) // 2), len(train))
            for alpha in alphas:
                squared = []
                for end in folds:
                    # Embargo overlapping intervals inside tuning, as at the outer decision.
                    available = train.iloc[:end].exit <= train.iloc[end].decision_date
                    pred = fit_predict(x[:end][available], y[:end][available], x[end:end+1], alpha, robust,
                                       feature_names=columns, min_policy_observations=min_policy_observations,
                                       primary=primary, policy_sources=sources[:end][available] if primary else None)[0]
                    squared.append((pred - y[end]) ** 2)
                errors.append(np.mean(squared, axis=0))
            chosen = np.array(alphas)[np.argmin(np.array(errors), axis=0)]
            q = np.empty(len(ASSETS))
            for j, asset in enumerate(ASSETS):
                pred, info = fit_predict(x, y, row[columns].to_numpy(float)[None, :], chosen[j], robust, details=True,
                                         feature_names=columns, min_policy_observations=min_policy_observations,
                                         primary=primary, policy_sources=sources)
                q[j] = pred[0, j]
                audit[asset] = {
                    "intercept": info["intercept"][j],
                    "training_return_min": info["training_return_min"][j],
                    "training_return_max": info["training_return_max"][j],
                    "features": [{"feature": c, "contribution": info["contributions"][i, j],
                                  "standardized_input": info["standardized_input"][i],
                                  "observed_training_rows": int(info["observed_training_rows"][i]),
                                  "training_scale": info["training_scale"][i],
                                  "constant_training_column": bool(info["constant_training_column"][i]),
                                  "input_clipped": bool(info["input_clipped"][i]),
                                  "enabled": bool(info["supported"][i]),
                                  "raw_input": info["raw_input"][i],
                                  "input_imputed": bool(info["input_imputed"][i]),
                                  "imputation_median": info["imputation_median"][i],
                                  "training_mean": info["training_mean"][i],
                                  "processed_input": info["processed_input"][i],
                                  "coefficient": info["coefficient"][i, j],
                                  "distinct_observed_values": int(info["distinct_observed_values"][i]),
                                  **({"unique_source_observations": int(info["policy_guard"]["unique_source_observations"][i]),
                                      "distinct_resolution_bins": int(info["policy_guard"]["distinct_resolution_bins"][i]),
                                      "observed_source_std": info["policy_guard"]["observed_source_std"][i],
                                      "processed_training_std": info["processed_std"][i],
                                      "disabled_reasons": info["policy_guard"]["disabled_reasons"][i]} if primary else {})}
                                 for i, c in enumerate(columns)],
                }
        predictions.append({"idx": idx, "date": row.date, "decision_date": row.decision_date,
                            "exit": row.exit, "q": q, "actual": row.asset_returns, "alpha": chosen,
                            "training_rows": len(train), "audit": audit,
                            "last_training_exit": train.exit.max()})
    return predictions


def monthly_allocation(panel: pd.DataFrame, covariance_returns: pd.DataFrame, prediction_rows: list[dict], use_views: bool = True,
                       primary: dict | None = None) -> list[dict]:
    settings = primary["portfolio"] if primary else {}
    benchmark = np.array(settings.get("starting_weights", BENCHMARK))
    previous = benchmark.copy()
    decisions = []
    for pred in prediction_rows:
        row = panel.loc[pred["idx"]]
        past = [p for p in prediction_rows if p["exit"] <= row.decision_date]
        if len(past) < settings.get("min_prior_errors", 12):
            continue
        observed_returns = covariance_returns[covariance_returns.index <= row.decision_date].tail(settings.get("covariance_months", 36))
        if len(observed_returns) < settings.get("min_covariance_months", 24):
            continue
        cov = observed_returns.cov().to_numpy(float)
        omega = np.stack([p["q"] - p["actual"] for p in past]).var(axis=0, ddof=1)
        posterior = (black_litterman_posterior(cov, pred["q"], omega, benchmark,
                                             tau=settings.get("tau", .05), risk_aversion=settings.get("risk_aversion", 2.5))
                     if use_views else 2.5 * cov @ benchmark)
        weights = optimize_weights_grid(posterior, cov, previous, **({"bounds": settings["bounds"],
                                        "risk_aversion": settings["risk_aversion"], "turnover_penalty": settings["turnover_penalty"],
                                        "step": settings["grid_step"]} if primary else {}))
        turnover = float(np.abs(weights - previous).sum())
        gross = float(weights @ row.asset_returns)
        cost = turnover * (settings["cost_bps_per_dollar_traded"] / 10000 if primary else .0005)
        net = (1 - cost) * (1 + gross) - 1
        decisions.append({
            "date": row.date, "decision_date": row.decision_date, "holding_month": row.holding_month,
            "entry": row.entry, "exit": row.exit, "weights": weights,
            "forecast": pred["q"] if use_views else None, "posterior": posterior,
            "actual": row.asset_returns,
            "view_error_variance": omega if use_views else None,
            "gross_return": gross,
            "turnover": turnover, "cost": cost, "net_return": net,
            "training_rows": pred["training_rows"],
            "last_training_exit": pred["last_training_exit"],
            "last_error_exit": max(p["exit"] for p in past),
        })
        previous = weights * (1 + row.asset_returns) / (1 + gross)
    return decisions


def passive_decisions(panel: pd.DataFrame, target: np.ndarray, dates: set[pd.Timestamp]) -> list[dict]:
    previous = target.copy()
    result = []
    for _, row in panel[panel.date.isin(dates)].iterrows():
        turnover = float(np.abs(target - previous).sum())
        gross = float(target @ row.asset_returns)
        cost = turnover * .0005
        result.append({"date": row.date, "decision_date": row.decision_date, "holding_month": row.holding_month, "entry": row.entry, "exit": row.exit,
                       "weights": target.copy(), "turnover": turnover, "cost": cost, "net_return": (1 - cost) * (1 + gross) - 1})
        previous = target * (1 + row.asset_returns) / (1 + gross)
    return result


def summarize(decisions: list[dict], prices: pd.DataFrame) -> tuple[dict, list[dict]]:
    if not decisions:
        raise ValueError("No common decisions in this period")
    wealth = 100.
    path = [{"date": decisions[0]["entry"], "wealth": wealth}]
    for row in decisions:
        segment = prices.loc[row["entry"]:row["exit"]]
        opening = wealth * (1 - row["cost"])
        factors = segment / segment.iloc[0]
        values = opening * (factors.to_numpy() @ row["weights"])
        path.extend({"date": d, "wealth": float(v)} for d, v in zip(segment.index, values))
        wealth = float(values[-1])
    monthly = np.array([d["net_return"] for d in decisions])
    wealth_values = np.array([p["wealth"] for p in path])
    peaks = np.maximum.accumulate(wealth_values)
    drawdowns = wealth_values / peaks - 1
    worst_idx = int(drawdowns.argmin())
    prior_peak_idx = int(wealth_values[:worst_idx+1].argmax())
    recovered = np.flatnonzero(wealth_values[worst_idx+1:] >= wealth_values[prior_peak_idx])
    recovered_date = path[worst_idx+1+int(recovered[0])]["date"] if len(recovered) else None
    errors_check = np.prod(1 + monthly)
    if not np.isclose(wealth / 100, errors_check, atol=1e-10):
        raise AssertionError("Daily wealth and monthly net returns do not reconcile")
    vol = float(monthly.std(ddof=1) * np.sqrt(12)) if len(monthly) > 1 else None
    ann = float((wealth / 100) ** (12 / len(monthly)) - 1)
    # Do not annualize short episode returns or present a 3-month Sharpe ranking.
    stats = {
        "months": len(monthly), "cumulative_return": wealth / 100 - 1,
        "annualized_return": ann if len(monthly) >= 12 else None,
        "annualized_volatility": vol,
        "sharpe_zero_rf": float(monthly.mean() * 12 / vol) if len(monthly) >= 12 and vol and vol > 0 else None,
        "maximum_drawdown": float(drawdowns.min()), "average_turnover": float(np.mean([r["turnover"] for r in decisions])),
        "cost_bps_sum": float(sum(r["cost"] for r in decisions) * 10000),
        "end_value": wealth, "entry": decisions[0]["entry"], "exit": decisions[-1]["exit"],
        "recovery_date": recovered_date,
        "drawdown_trough": path[worst_idx]["date"],
    }
    return stats, path


def serializable(value):
    if value is None or value is pd.NaT:
        return None
    if isinstance(value, dict):
        return {k: serializable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [serializable(v) for v in value]
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return float(value) if np.isfinite(value) else None
    return value


def main():
    if FREEZE_PATH.exists():
        verify_freeze()
    OUT.mkdir(parents=True, exist_ok=True)
    specification = json.loads(SPEC_PATH.read_text())
    primary = primary_spec()
    prices = adjusted_prices()
    panel, monthly_returns = make_panel(prices)
    all_decisions = {}
    all_forecasts = {}
    for key, meta in VARIANTS.items():
        prediction_rows = forecasts(panel, meta["extra"],
                                   include_policy=meta.get("include_policy", True), robust=meta.get("robust", False),
                                   stronger_shrinkage=meta.get("stronger_shrinkage"),
                                   min_policy_observations=meta.get("min_policy_observations", 0),
                                   primary=primary if meta.get("primary") else None)
        all_forecasts[key] = prediction_rows
        all_decisions[key] = monthly_allocation(panel, monthly_returns, prediction_rows, primary=primary if meta.get("primary") else None)
        print(key, "predictions", len(prediction_rows), "allocations", len(all_decisions[key]), flush=True)
    all_forecasts["historical_mean"] = forecasts(panel, [], historical_mean=True)
    all_decisions["historical_mean"] = monthly_allocation(panel, monthly_returns, all_forecasts["historical_mean"])
    all_decisions["prior_only"] = monthly_allocation(panel, monthly_returns, all_forecasts["baseline"], use_views=False)
    common = set.intersection(*(set(d["date"] for d in rows) for rows in all_decisions.values()))
    for key, meta in PASSIVE.items():
        all_decisions[key] = passive_decisions(panel, meta["weights"], common)
    series_meta = {**VARIANTS, **MODEL_REFERENCES, **PASSIVE}
    periods = []
    for period in PERIODS:
        selected = {}
        for key, rows in all_decisions.items():
            chosen = [d for d in rows if d["date"] in common and pd.Timestamp(period["start"]) <= d["holding_month"] <= pd.Timestamp(period["end"])]
            stats, path = summarize(chosen, prices)
            errors = [p for p in all_forecasts.get(key, []) if p["date"] in {d["date"] for d in chosen}]
            stats["forecast_rmse"] = float(np.sqrt(np.mean(np.stack([(e["q"] - e["actual"]) ** 2 for e in errors])))) if errors else None
            selected[key] = {"stats": stats, "path": path, "decisions": chosen,
                             "forecast_diagnostics": forecast_diagnostics(errors)}
        baseline_return = selected["baseline"]["stats"]["cumulative_return"]
        for key, result in selected.items():
            result["stats"]["difference_vs_baseline"] = result["stats"]["cumulative_return"] - baseline_return
        periods.append({**period, "results": selected})
    signal_rows = panel[["date", "decision_date", "claims_change_3m", "credit_level", "credit_change_1m", "curve_level", "claims_source_date", "claims_available_date", "credit_source_date", "credit_available_date", "curve_source_date", "curve_available_date", "anfci_source_date", "anfci_assumed_available_date", "gpr_source_date", "gpr_assumed_available_date", "policy_data_date", "policy_withheld_after_cutoff", "growth_surprise", "inflation_surprise", "anfci", "gpr", *POLICY_FEATURES, *[f"{c}__source" for c in POLICY_FEATURES]]]
    signal_rows.to_csv(OUT / "research_signals.csv", index=False)
    # Include monthly outputs for the development interval only, never the sealed test.
    rolling = []
    holding_months = sorted({d["holding_month"] for d in all_decisions["baseline"] if d["date"] in common})
    for end in range(11, len(holding_months)):
        first, last = holding_months[end-11], holding_months[end]
        results = {}
        for key, rows in all_decisions.items():
            chosen = [d for d in rows if d["date"] in common and first <= d["holding_month"] <= last]
            stats, _ = summarize(chosen, prices)
            results[key] = stats
        rolling.append({"start": first, "end": last, "results": results})
    sources = [
        {"name": "Initial unemployment claims", "url": "https://fred.stlouisfed.org/series/ICSA", "file": "claims.csv", "feature": "Three-month percentage change in the latest available four-week average", "availability": "Observation Saturday + five calendar days (Thursday); latest revised vintage"},
        {"name": "Baa corporate–Treasury spread", "url": "https://fred.stlouisfed.org/series/BAA10Y", "file": "credit.csv", "feature": "Spread level and one-month change, percentage points", "availability": "One business day after observation; broad Baa proxy, not LQD OAS"},
        {"name": "10-year minus 3-month yield curve", "url": "https://fred.stlouisfed.org/series/T10Y3M", "file": "curve.csv", "feature": "Latest available spread level, percentage points", "availability": "One business day after observation"},
    ]
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "environment": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__},
        "specification": specification,
        "specification_sha256": hashlib.sha256(SPEC_PATH.read_bytes()).hexdigest(),
        "code_hashes": {name: hashlib.sha256((ROOT / "src" / name).read_bytes()).hexdigest()
                        for name in SOURCE_FILES},
        "periods": periods,
        "rolling_windows": rolling,
        "variants": {key: {"name": meta["name"], "color": meta["color"], "kind": "model" if key in VARIANTS else "model_reference" if key in MODEL_REFERENCES else "reference"} for key, meta in series_meta.items()},
        "signal_observations": signal_rows.to_dict("records"),
        "sources": sources,
        "settings": {"risk_aversion": 2.5, "tau": .05, "cost_bps_per_dollar": 5, "min_train": 36, "min_prior_errors": 12, "training_start": "2015-02-28", "covariance_months": 36,
                     "common_first_decision": min(common), "common_last_decision": max(common), "trade_timing": "Last-trading-day decision; enter next trading-day close and exit next rebalance close. Holding month names the entry month.", "development_only": True},
        "input_hashes": input_hashes(),
        "workbook_sha256": hashlib.sha256(WORKBOOK.read_bytes()).hexdigest(),
    }
    output.update(research_diagnostics(all_decisions, all_forecasts, prices, common, summarize, VARIANTS, panel, PERIODS, specification))
    output["stability"] = stability_report(panel, all_forecasts, all_decisions, common, WORKBOOK, specification)
    from research_stability import primary_report
    output["primary"] = primary_report(primary, output, all_forecasts, all_decisions, common, hashlib.sha256(PRIMARY_SPEC_PATH.read_bytes()).hexdigest())
    (OUT / "research_forecasts.json").write_text(json.dumps(serializable(all_forecasts), indent=2, allow_nan=False))
    (OUT / "research_results.json").write_text(json.dumps(serializable(output), indent=2, allow_nan=False))
    # Persist all pre-2023 decisions for rolling-window diagnostics and reproducibility.
    (OUT / "research_decisions.json").write_text(json.dumps(serializable(all_decisions), indent=2, allow_nan=False))
    print("Saved", OUT / "research_results.json")


if __name__ == "__main__":
    main()
