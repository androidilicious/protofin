import sys
import unittest
from unittest.mock import patch
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from deterministic_mvp import (  # noqa: E402
    BASE_FEATURES,
    FULL_FEATURES,
    RELEASE_SPECS,
    black_litterman_posterior,
    build_clean_releases,
    build_monthly_features,
    portfolio_backtest,
    optimize_weights_grid,
    walk_forward_ridge,
    _excel_dates,
    _trade_period,
    _json_value,
    load_release_table,
    _completed_month_cutoff,
)
from prepare_online_data import prepare_anfci, prepare_gpr  # noqa: E402


class DeterministicMvpTests(unittest.TestCase):
    def test_only_completed_months_are_used(self):
        self.assertEqual(_completed_month_cutoff("2026-10-26"), pd.Timestamp("2026-09-30"))
        self.assertEqual(_completed_month_cutoff("2026-10-31"), pd.Timestamp("2026-09-30"))
        self.assertEqual(_completed_month_cutoff("2026-11-01"), pd.Timestamp("2026-10-31"))

    def test_model_and_benchmark_pay_same_cost_for_same_trades(self):
        rng = np.random.default_rng(9)
        dates = pd.date_range("2020-01-31", periods=40, freq="ME")
        model = pd.DataFrame({"date": dates})
        rows = []
        for asset, column in zip(["equity", "treasury", "ig_credit"],
                                 ["equity_return", "treasury_return", "ig_credit_return"]):
            model[column] = rng.normal(.003, .02, len(dates))
            model[f"next_{column}"] = model[column].shift(-1)
            rows.extend({"date": date, "asset": asset, "forecast_next_month": .005,
                         "realized_next_month": model.at[i, f"next_{column}"]}
                        for i, date in enumerate(dates))
        benchmark = np.array([.45, .35, .20])
        with patch("deterministic_mvp.optimize_weights_grid", return_value=benchmark):
            backtest, metrics = portfolio_backtest(model, pd.DataFrame(rows))
        scored = backtest.dropna(subset=["net_return"])
        self.assertTrue(np.allclose(scored.net_return, scored.benchmark_return))
        self.assertTrue(np.allclose(scored.transaction_cost, scored.benchmark_transaction_cost))
        self.assertGreater(scored.benchmark_transaction_cost.sum(), 0.)
        self.assertEqual(int(metrics.iloc[0].observations), len(scored))
        self.assertFalse(bool(backtest.iloc[-1].evaluated))

    def test_excel_serial_dates_match_formatted_dates(self):
        values = pd.Series([pd.Timestamp("2026-10-14"), 46309, "#N/A Requesting Data...", None])
        parsed = _excel_dates(values)
        self.assertEqual(parsed.iloc[0], parsed.iloc[1])
        self.assertTrue(parsed.iloc[2:].isna().all())

    def test_drift_requires_trades_even_when_target_does_not_change(self):
        target = np.array([0.45, 0.35, 0.20])
        _, _, _, _, drifted = _trade_period(target, target, np.array([0.10, 0., 0.]), 5.)
        turnover, cost, gross, net, after = _trade_period(target, drifted, np.zeros(3), 5.)
        expected_turnover = abs(target[0] - (0.45 * 1.10 / 1.045))
        self.assertAlmostEqual(turnover, expected_turnover)
        self.assertAlmostEqual(cost, expected_turnover * 0.0005)
        self.assertAlmostEqual(net, -cost)
        self.assertTrue(np.allclose(after, target))

    def test_cost_is_deducted_before_holding_return(self):
        target = np.array([0.6, 0.2, 0.2])
        turnover, cost, gross, net, _ = _trade_period(target, np.array([0.4, 0.4, 0.2]), np.full(3, .10), 100.)
        self.assertAlmostEqual(turnover, .2)
        self.assertAlmostEqual(net, (1 - .002) * 1.1 - 1)

    def test_empty_download_fails_with_actionable_message(self):
        release = pd.DataFrame({"Release Date": ["#N/A Requesting Data..."],
                                **{name: [None] for name in ["Actual", "Median", "Average", "High", "Low", "Std. dev"]}})
        with patch("deterministic_mvp.pd.read_excel", side_effect=[release, pd.DataFrame()]):
            with self.assertRaisesRegex(ValueError, "refresh Bloomberg"):
                load_release_table(self.workbook, RELEASE_SPECS[0])

    def test_json_supports_native_dates_and_nat(self):
        import datetime
        self.assertEqual(_json_value(datetime.datetime(2026, 9, 30)), "2026-09-30")
        self.assertIsNone(_json_value(pd.NaT))

    @classmethod
    def setUpClass(cls):
        cls.workbook = ROOT.parent / "deterministic_data1.xlsx"
        cls.releases = build_clean_releases(cls.workbook)
        cls.features = build_monthly_features(cls.workbook, cls.releases)

    def test_all_eight_release_series_are_loaded(self):
        self.assertEqual(set(self.releases["variable"]), {spec.name for spec in RELEASE_SPECS})
        self.assertEqual(len(self.releases), 744)

    def test_duplicate_reference_dates_do_not_duplicate_releases(self):
        counts = self.releases.groupby(["variable", "release_date"]).size()
        self.assertEqual(int(counts.max()), 1)
        ambiguous = self.releases[self.releases["reference_status"] == "ambiguous_multiple_periods"]
        self.assertEqual(len(ambiguous), 4)

    def test_standardization_is_point_in_time(self):
        nfp = self.releases[self.releases["variable"] == "nfp"].sort_values("release_date")
        row = nfp.iloc[20]
        expected_sigma = nfp.iloc[:20]["raw_surprise"].std(ddof=1)
        self.assertAlmostEqual(row["historical_surprise_sigma"], expected_sigma)
        self.assertAlmostEqual(row["standardized_surprise"], row["raw_surprise"] / expected_sigma)

    def test_feature_panel_has_complete_rows(self):
        complete = self.features[BASE_FEATURES].notna().all(axis=1)
        self.assertGreater(int(complete.sum()), 60)
        self.assertLessEqual(self.features.loc[complete, "date"].max(), pd.Timestamp("2026-09-30"))

    def test_optimizer_respects_bounds_and_sum(self):
        expected = np.array([0.01, 0.002, 0.004])
        covariance = np.diag([0.003, 0.001, 0.0015])
        previous = np.array([0.45, 0.35, 0.20])
        weights = optimize_weights_grid(expected, covariance, previous)
        self.assertAlmostEqual(float(weights.sum()), 1.0, places=10)
        self.assertTrue(0.20 <= weights[0] <= 0.70)
        self.assertTrue(0.15 <= weights[1] <= 0.60)
        self.assertTrue(0.10 <= weights[2] <= 0.40)

    def test_black_litterman_returns_finite_vector(self):
        covariance = np.diag([0.003, 0.001, 0.0015])
        posterior = black_litterman_posterior(
            covariance,
            np.array([0.01, 0.002, 0.004]),
            np.array([0.002, 0.001, 0.001]),
            np.array([0.45, 0.35, 0.20]),
        )
        self.assertEqual(posterior.shape, (3,))
        self.assertTrue(np.isfinite(posterior).all())

    def test_full_forecast_and_portfolio_path_on_deterministic_fixture(self):
        rng = np.random.default_rng(7)
        rows = 84
        frame = pd.DataFrame({"date": pd.date_range("2018-01-31", periods=rows, freq="ME")})
        for column in FULL_FEATURES:
            frame[column] = rng.normal(size=rows)
        frame["equity_return"] = 0.004 + 0.002 * frame["growth_surprise"] + rng.normal(0, 0.02, rows)
        frame["treasury_return"] = 0.002 - 0.001 * frame["inflation_surprise"] + rng.normal(0, 0.01, rows)
        frame["ig_credit_return"] = 0.003 + 0.001 * frame["growth_surprise"] + rng.normal(0, 0.012, rows)
        for column in ["equity_return", "treasury_return", "ig_credit_return"]:
            frame[f"next_{column}"] = frame[column].shift(-1)

        predictions, _ = walk_forward_ridge(frame, min_train=36)
        backtest, metrics = portfolio_backtest(frame, predictions)
        self.assertGreater(len(predictions), 100)
        self.assertGreater(len(backtest), 12)
        self.assertEqual(len(metrics), 1)
        weight_sum = backtest[["equity_weight", "treasury_weight", "ig_credit_weight"]].sum(axis=1)
        self.assertTrue(np.allclose(weight_sum, 1.0))
        # Future outcomes and features must not alter earlier decisions.
        altered = frame.copy()
        altered.loc[75:, FULL_FEATURES] = 1000.
        altered.loc[75:, ["equity_return", "treasury_return", "ig_credit_return"]] = .9
        for column in ["equity_return", "treasury_return", "ig_credit_return"]:
            altered[f"next_{column}"] = altered[column].shift(-1)
        changed_predictions, _ = walk_forward_ridge(altered)
        changed_backtest, _ = portfolio_backtest(altered, changed_predictions)
        cutoff = frame.at[73, "date"]
        pd.testing.assert_frame_equal(
            backtest.loc[backtest.date <= cutoff].reset_index(drop=True),
            changed_backtest.loc[changed_backtest.date <= cutoff].reset_index(drop=True))

    def test_gpr_is_available_in_following_decision_month(self):
        data = prepare_gpr(ROOT / "data" / "raw" / "gpr_caldara_iacoviello.dta")
        sample = data.iloc[-1]
        expected = (sample["gpr_reference_month"].to_period("M") + 1).to_timestamp("M")
        self.assertEqual(sample["date"], expected)

    def test_anfci_publication_lag_prevents_month_end_lookahead(self):
        data = prepare_anfci(ROOT / "data" / "raw" / "anfci_fred.csv")
        self.assertTrue((data["available_date"] <= data["date"]).all())
        self.assertTrue(((data["available_date"] - data["observation_date"]).dt.days == 5).all())


if __name__ == "__main__":
    unittest.main()
