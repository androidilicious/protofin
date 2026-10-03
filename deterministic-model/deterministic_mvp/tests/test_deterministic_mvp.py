import sys
import unittest
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
)
from prepare_online_data import prepare_anfci, prepare_gpr  # noqa: E402


class DeterministicMvpTests(unittest.TestCase):
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
