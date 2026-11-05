"""Checks for the sparse-feature mechanism and fair repair comparisons."""
import json
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from research_backtest import fit_predict
from research_stability import allocation_limits, matched_metrics


class StabilityTests(unittest.TestCase):
    def test_sparse_imputation_scale_and_units_reconstruct_forecast(self):
        x = np.full((58, 1), np.nan)
        x[-2:, 0] = [.2388, .2378]
        y = np.zeros((58, 3))
        y[-2:] = [[.03, .01, .02], [-.03, -.01, -.02]]
        q, info = fit_predict(x, y, np.array([[-.2681]]), 100., details=True)
        filled = np.where(np.isfinite(x), x, .2383)
        z = (-.2681 - filled.mean()) / filled.std(ddof=0)
        self.assertAlmostEqual(info["standardized_input"][0], z)
        self.assertEqual(info["observed_training_rows"][0], 2)
        self.assertEqual(info["distinct_observed_values"][0], 2)
        self.assertFalse(info["input_imputed"][0])
        self.assertGreater(abs(z), 5000)
        np.testing.assert_allclose(q[0], info["intercept"] + z * info["coefficient"][0])
        # Consistently changing feature units cannot fix a standardized extrapolation.
        converted = fit_predict(x / 100, y, np.array([[-.2681]]) / 100, 100.)
        np.testing.assert_allclose(q, converted, rtol=1e-10)

    def test_supported_policy_zeroes_sparse_feature_even_for_extreme_test(self):
        x = np.full((58, 1), np.nan)
        x[-2:, 0] = [.2388, .2378]
        y = np.arange(174).reshape(58, 3) / 1000
        q, info = fit_predict(x, y, np.array([[-1e9]]), .1, details=True,
                              feature_names=["policy_6m_change"], min_policy_observations=12)
        np.testing.assert_allclose(q[0], y.mean(axis=0))
        self.assertFalse(info["supported"][0])
        self.assertEqual(info["contributions"][0].tolist(), [0., 0., 0.])

    def test_metrics_use_matched_expanding_mean_and_strict_warning(self):
        rows = [{"date": d, "decision_date": d, "q": [q] * 3, "actual": [a] * 3}
                for d, q, a in [("2020-01-31", .2, .1), ("2020-02-29", -.3, -.1)]]
        reference = [{**r, "q": [.05] * 3} for r in rows]
        metrics = matched_metrics(rows, reference)
        expected = 1 - (.1 ** 2 + (-.2) ** 2) / (.05 ** 2 + (-.15) ** 2)
        self.assertAlmostEqual(metrics["assets"]["equity"]["oos_r2_vs_historical_mean"], expected)
        self.assertEqual(metrics["extreme_asset_months"], 3)
        self.assertEqual(metrics["months_with_any_extreme"], 1)
        self.assertEqual(matched_metrics(reference, reference)["assets"]["equity"]["oos_r2_vs_historical_mean"], 0.)
        mismatched = [{**r, "actual": [0.] * 3} for r in reference]
        with self.assertRaises(AssertionError):
            matched_metrics(rows, mismatched)

    def test_allocation_limits_count_months_once_and_assets_separately(self):
        result = allocation_limits([{"weights": [.7, .2, .1]}, {"weights": [.45, .35, .2]}])
        self.assertEqual(result["months_at_any_limit"], 1)
        self.assertEqual(result["assets"]["equity"]["upper_count"], 1)
        self.assertEqual(result["assets"]["ig_credit"]["lower_count"], 1)
        self.assertEqual(result["fraction_at_any_limit"], .5)

    def test_generated_trace_and_both_cohorts_reconcile(self):
        report = json.loads((ROOT / "research/outputs/research_results.json").read_text())
        stability = report["stability"]
        trace = stability["january_2020"]
        self.assertEqual(trace["training_rows"], 58)
        self.assertEqual(trace["missing_training_rows"], 56)
        self.assertEqual(trace["distinct_observed_values"], 2)
        np.testing.assert_allclose(trace["observed_values"], [.2388, .2378])
        self.assertAlmostEqual(trace["raw_decision_input"], -.2681)
        self.assertAlmostEqual(trace["assets"]["equity"]["forecast"], 5.894544161780397, places=7)
        for audit in trace["assets"].values():
            self.assertAlmostEqual(audit["reconstructed_forecast"], audit["forecast"])
            self.assertAlmostEqual(trace["standardized_input"] * audit["policy_change_coefficient"], audit["policy_change_contribution"])
        cohorts = stability["cohorts"]
        self.assertGreater(cohorts["all_forecasts"]["results"]["baseline"]["months"], cohorts["portfolio_dates"]["results"]["baseline"]["months"])
        for cohort in cohorts.values():
            dates = [[r["holding_month"] for r in rows] for rows in cohort["timeline"].values()]
            self.assertTrue(all(d == dates[0] for d in dates))
            self.assertTrue(all(d < "2023-01-01" for d in dates[0]))
            for key, rows in cohort["timeline"].items():
                metrics = cohort["results"][key]
                self.assertEqual(metrics["extreme_asset_months"], len(cohort["extreme_events"][key]))
                for j, asset in enumerate(["equity", "treasury", "ig_credit"]):
                    ref = cohort["timeline"]["historical_mean"]
                    error = sum((r["q"][j] - r["actual"][j]) ** 2 for r in rows)
                    denominator = sum((r["q"][j] - r["actual"][j]) ** 2 for r in ref)
                    self.assertAlmostEqual(metrics["assets"][asset]["oos_r2_vs_historical_mean"], 1 - error / denominator)


if __name__ == "__main__":
    unittest.main()
