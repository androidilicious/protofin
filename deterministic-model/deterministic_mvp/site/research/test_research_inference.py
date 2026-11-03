"""Independent checks of paired inference, fold safeguards and coverage limits."""
import json
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from research_backtest import fit_predict, make_panel, adjusted_prices
from research_inference import paired_block_interval, credit_shared_information


class InferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads((ROOT / "research/outputs/research_results.json").read_text())

    def test_paired_bootstrap_cancels_shared_market_noise(self):
        base = np.random.default_rng(9).normal(0, .2, 36)
        for block in [3, 6, 12]:
            result = paired_block_interval(base + .01, base, block_length=block, replications=500)
            self.assertAlmostEqual(result["mean_monthly_difference"], .01)
            self.assertAlmostEqual(result["lower"], .01)
            self.assertAlmostEqual(result["upper"], .01)
            self.assertEqual(result, paired_block_interval(base + .01, base, block_length=block, replications=500))
        zero = paired_block_interval(base, base, replications=500)
        self.assertEqual(zero["lower"], 0.)
        self.assertEqual(zero["upper"], 0.)

    def test_bootstrap_rejects_invalid_inputs(self):
        for a, b, block in [([], [], 3), ([0., np.nan], [0., 0.], 1), ([0., 0.], [0.], 1), ([0.], [0.], 2)]:
            with self.assertRaises(ValueError):
                paired_block_interval(a, b, block_length=block)

    def test_sparse_policy_feature_has_zero_influence_until_supported(self):
        rng = np.random.default_rng(4)
        x = rng.normal(size=(36, 2))
        x[:25, 1] = np.nan  # Eleven observed policy values.
        y = rng.normal(size=(36, 3))
        test = np.array([[.5, 1e8]])
        pred, info = fit_predict(x, y, test, 1., details=True,
                                 feature_names=["growth_surprise", "policy_6m_change"], min_policy_observations=12)
        expected = fit_predict(x[:, :1], y, test[:, :1], 1.)
        np.testing.assert_allclose(pred, expected)
        np.testing.assert_allclose(info["contributions"][1], 0.)
        self.assertFalse(info["supported"][1])
        x[24, 1] = .1  # Twelfth observed value.
        _, enabled = fit_predict(x, y, test, 1., details=True,
                                  feature_names=["growth_surprise", "policy_6m_change"], min_policy_observations=12)
        self.assertTrue(enabled["supported"][1])

    def test_original_episode_results_equal_zero_shift(self):
        report = self.report
        self.assertEqual(len(report["episode_boundary_checks"]), 27)
        for period in report["periods"]:
            row = next(r for r in report["episode_boundary_checks"] if r["episode"] == period["id"] and r["start_offset"] == r["end_offset"] == 0)
            self.assertTrue(row["complete"])
            for key, result in period["results"].items():
                self.assertAlmostEqual(row["results"][key]["cumulative_return"], result["stats"]["cumulative_return"])
                self.assertEqual(row["results"][key]["months"], result["stats"]["months"])

    def test_boundary_requests_never_evaluate_reserved_months(self):
        unavailable = [r for r in self.report["episode_boundary_checks"] if not r["complete"]]
        self.assertEqual(len(unavailable), 3)
        self.assertTrue(all(r["requested_end"] == "2023-01" for r in unavailable))
        self.assertTrue(all(not r["results"] for r in unavailable))
        for r in self.report["episode_boundary_checks"]:
            if r["complete"]:
                self.assertLessEqual(r["requested_end"], "2022-12")

    def test_episode_exclusion_counts_and_compounding(self):
        report = self.report
        for exclusion, period in zip(report["leave_episode_out"], report["periods"]):
            for key, result in exclusion["results"].items():
                full = report["development"]["results"][key]["stats"]
                episode = period["results"][key]["stats"]
                self.assertEqual(result["months"], full["months"]-episode["months"])
                self.assertAlmostEqual(1+result["cumulative_return"], (1+full["cumulative_return"])/(1+episode["cumulative_return"]))

    def test_credit_projection_does_not_learn_from_future_features(self):
        panel, _ = make_panel(adjusted_prices())
        common = set(panel.loc[panel.date.between("2019-01-31", "2019-06-30"), "date"])
        original = credit_shared_information(panel, common)
        changed = panel.copy()
        changed.loc[changed.date > "2019-06-30", ["credit_level", "credit_change_1m", "anfci"]] = 1e6
        updated = credit_shared_information(changed, common)
        self.assertEqual(len(original["predictions"]), len(common))
        for before, after in zip(original["predictions"], updated["predictions"]):
            self.assertLess(before["last_training_date"], before["date"])
            np.testing.assert_allclose(before["predicted"], after["predicted"])

    def test_clipping_and_shrinkage_are_separate_experiments(self):
        report = self.report
        self.assertTrue({"clip_only", "shrink_only", "supported_policy"}.issubset(report["variants"]))
        settings = report["specification"]["robustness_checks"]
        self.assertIn("original Ridge grid", settings["clip_only"])
        self.assertIn("No input clipping", settings["shrink_only"])
        self.assertEqual(report["paired_block_bootstrap"]["settings"]["block_lengths"], [3, 6, 12])

    def test_recorded_forecasts_use_the_intended_safeguards(self):
        forecasts = json.loads((ROOT / "research/outputs/research_forecasts.json").read_text())
        clipped = []
        for row in forecasts["clip_only"]:
            for audit in row["audit"].values():
                clipped.extend(f["input_clipped"] for f in audit["features"])
        self.assertTrue(any(clipped))
        for row in forecasts["shrink_only"]:
            self.assertTrue(set(row["alpha"]).issubset({1., 10., 100., 1000.}))
            self.assertTrue(all(not f["input_clipped"] for a in row["audit"].values() for f in a["features"]))
        disabled = 0
        for row in forecasts["supported_policy"]:
            for audit in row["audit"].values():
                for feature in audit["features"]:
                    if feature["feature"].startswith("policy_"):
                        self.assertEqual(feature["enabled"], feature["observed_training_rows"] >= 12)
                        if not feature["enabled"]:
                            disabled += 1
                            self.assertEqual(feature["contribution"], 0.)
        self.assertGreater(disabled, 0)


if __name__ == "__main__":
    unittest.main()
