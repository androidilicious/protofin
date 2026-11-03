"""Checks for timing, cost accounting, and isolation of research experiments."""
import json
import hashlib
import sys
import unittest
from unittest.mock import patch
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from research_backtest import adjusted_prices, make_panel, forecasts, summarize, fit_predict, input_hashes, WORKBOOK, POLICY_FEATURES, VARIANTS


class ResearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prices = adjusted_prices()
        cls.panel, _ = make_panel(cls.prices)
        cls.report = json.loads((ROOT / "research/outputs/research_results.json").read_text())

    def test_all_variants_have_same_complete_episode_months(self):
        for period, count in zip(self.report["periods"], [3, 8, 12]):
            dates = []
            for result in period["results"].values():
                self.assertEqual(result["stats"]["months"], count)
                dates.append([r["holding_month"] for r in result["decisions"]])
            self.assertTrue(all(d == dates[0] for d in dates))

    def test_information_and_execution_dates(self):
        for _, row in self.panel.iterrows():
            self.assertLess(row.decision_date, row.entry)
            self.assertLess(row.entry, row.exit)
            for key in ["claims", "credit", "curve"]:
                self.assertLessEqual(row[f"{key}_available_date"], row.decision_date)
        for period in self.report["periods"]:
            for key in [*VARIANTS, "historical_mean", "prior_only"]:
                for row in period["results"][key]["decisions"]:
                    self.assertLessEqual(row["last_training_exit"], row["decision_date"])
                    self.assertLessEqual(row["last_error_exit"], row["decision_date"])

    def test_candidate_features_cover_the_same_training_rows(self):
        columns = ["claims_change_3m", "credit_level", "credit_change_1m", "curve_level"]
        self.assertTrue(self.panel[columns].notna().all().all())
        self.assertEqual(self.panel.iloc[0].date, pd.Timestamp("2015-02-28"))

    def test_future_targets_cannot_change_a_forecast(self):
        early = self.panel[self.panel.date <= "2019-12-31"].copy()
        original = forecasts(early, ["credit_level", "credit_change_1m"])
        changed = early.copy(deep=True)
        cutoff = original[-1]["decision_date"]
        changed.loc[changed.exit > cutoff, "asset_returns"] = pd.Series(
            [np.array([9., -9., 4.]) for _ in changed[changed.exit > cutoff].index],
            index=changed[changed.exit > cutoff].index,
        )
        updated = forecasts(changed, ["credit_level", "credit_change_1m"])
        np.testing.assert_allclose(original[-1]["q"], updated[-1]["q"])
        np.testing.assert_allclose(original[-1]["alpha"], updated[-1]["alpha"])

    def test_weights_costs_and_path_reconcile(self):
        for period in self.report["periods"]:
            for key, result in period["results"].items():
                wealth = 100.
                for row in result["decisions"]:
                    weights = np.array(row["weights"])
                    self.assertAlmostEqual(weights.sum(), 1.)
                    self.assertTrue((weights >= 0).all())
                    if key in [*VARIANTS, "historical_mean", "prior_only"]:
                        self.assertTrue(.2-1e-10 <= weights[0] <= .7+1e-10)
                        self.assertTrue(.15-1e-10 <= weights[1] <= .6+1e-10)
                        self.assertTrue(.1-1e-10 <= weights[2] <= .4+1e-10)
                    self.assertAlmostEqual(row["cost"], row["turnover"] * .0005)
                    returns = (self.prices.loc[row["exit"]] / self.prices.loc[row["entry"]] - 1).to_numpy()
                    expected = (1-row["cost"])*(1+weights@returns)-1
                    self.assertAlmostEqual(row["net_return"], expected)
                    wealth *= 1+expected
                self.assertAlmostEqual(wealth, result["path"][-1]["wealth"])
                values = np.array([p["wealth"] for p in result["path"]])
                dd = (values / np.maximum.accumulate(values)-1).min()
                self.assertAlmostEqual(dd, result["stats"]["maximum_drawdown"])

    def test_short_episode_metrics_are_not_annualized(self):
        for period in self.report["periods"][:2]:
            for result in period["results"].values():
                self.assertIsNone(result["stats"]["annualized_return"])
                self.assertIsNone(result["stats"]["sharpe_zero_rf"])

    def test_holdout_is_not_in_research(self):
        self.assertTrue((self.panel.holding_month <= "2022-12-31").all())
        for period in self.report["periods"]:
            for result in period["results"].values():
                for d in result["decisions"]:
                    self.assertLessEqual(d["holding_month"], "2022-12-31")

    def test_policy_observations_after_cutoff_are_withheld(self):
        late = self.panel.policy_data_date > self.panel.decision_date
        self.assertTrue(self.panel.loc[late, POLICY_FEATURES].isna().all().all())
        for key in ["anfci", "gpr"]:
            self.assertTrue((self.panel[f"{key}_assumed_available_date"] <= self.panel.decision_date).all())

    def test_inner_folds_only_use_completed_targets(self):
        panel = self.panel[self.panel.date <= "2019-01-31"].copy()
        panel["growth_surprise"] = np.arange(len(panel), dtype=float)
        calls = []

        def checked_fit(x, y, test, *args, **kwargs):
            train_ids, test_id = x[:, 0].astype(int), int(test[0, 0])
            self.assertTrue((panel.iloc[train_ids].exit <= panel.iloc[test_id].decision_date).all())
            calls.append(test_id)
            return fit_predict(x, y, test, *args, **kwargs)

        with patch("research_backtest.fit_predict", side_effect=checked_fit):
            forecasts(panel, [])
        self.assertGreater(len(calls), 0)

    def test_robust_inputs_and_forecast_decomposition(self):
        rng = np.random.default_rng(18)
        x = rng.normal(size=(45, 3))
        x[:30, 2] = np.nan
        y = rng.normal(0, .01, size=(45, 3))
        first, info = fit_predict(x, y, np.full((1, 3), 1e6), 10., robust=True, details=True)
        second = fit_predict(x, y, np.full((1, 3), 1e12), 10., robust=True)
        np.testing.assert_allclose(first, second)
        np.testing.assert_allclose(first[0], info["intercept"] + info["contributions"].sum(axis=0))
        self.assertEqual(info["observed_training_rows"][2], 15)
        self.assertTrue(info["input_clipped"].all())

    def test_forecast_audit_reconstructs_predictions(self):
        rows = forecasts(self.panel[self.panel.date <= "2019-01-31"], [])
        for row in rows:
            for j, asset in enumerate(["equity", "treasury", "ig_credit"]):
                audit = row["audit"][asset]
                self.assertAlmostEqual(row["q"][j], audit["intercept"] + sum(f["contribution"] for f in audit["features"]))

    def test_attribution_and_development_samples_reconcile(self):
        report = self.report
        samples = [r["stats"]["months"] for r in report["development"]["results"].values()]
        self.assertEqual(len(set(samples)), 1)
        self.assertIn("historical_mean", report["development"]["results"])
        self.assertIn("prior_only", report["development"]["results"])
        for key, rows in report["monthly_attribution"].items():
            self.assertEqual(len(rows), samples[0])
            for row in rows:
                self.assertAlmostEqual(sum(row["asset_return_contribution"]) + row["cost_effect"], row["net_return_difference"])
        self.assertEqual(sum(y["results"]["baseline"]["months"] for y in report["calendar_years"]), samples[0])

    def test_historical_mean_uses_only_observed_returns(self):
        rows = forecasts(self.panel[self.panel.date <= "2019-01-31"], [], historical_mean=True)
        for row in rows:
            train = self.panel[self.panel.exit <= row["decision_date"]]
            expected = np.stack(train.asset_returns).mean(axis=0)
            np.testing.assert_allclose(row["q"], expected)

    def test_report_fingerprints_every_consumed_data_source(self):
        expected = input_hashes()
        self.assertEqual(len(expected), 8)
        self.assertIn("data/raw/anfci_fred.csv", expected)
        self.assertIn("data/raw/gpr_caldara_iacoviello.dta", expected)
        self.assertEqual(self.report["input_hashes"], expected)
        self.assertEqual(self.report["workbook_sha256"], hashlib.sha256(WORKBOOK.read_bytes()).hexdigest())
        self.assertEqual(self.report["specification_sha256"], hashlib.sha256((ROOT / "research/experiment_spec.json").read_bytes()).hexdigest())
        for name, digest in self.report["code_hashes"].items():
            self.assertEqual(digest, hashlib.sha256((ROOT / "src" / name).read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
