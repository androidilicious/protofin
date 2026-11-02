"""Checks for timing, cost accounting, and isolation of research experiments."""
import json
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from research_backtest import adjusted_prices, make_panel, forecasts, summarize


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
            for key in ["baseline", "claims", "credit", "curve"]:
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
                    if key in ["baseline", "claims", "credit", "curve"]:
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


if __name__ == "__main__":
    unittest.main()
