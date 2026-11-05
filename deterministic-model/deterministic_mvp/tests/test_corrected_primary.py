"""Coverage, variation, timing, end-to-end uncertainty and freeze regressions."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from corrected_primary import primary_spec, policy_support, verify_freeze, FREEZE_PATH
from research_backtest import adjusted_prices, make_panel, forecasts, fit_predict


class CorrectedPrimaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = primary_spec()
        cls.panel, _ = make_panel(adjusted_prices())

    def policy_fit(self, values, sources, test=10000.):
        x = np.array(values, float)[:, None]
        y = np.column_stack([np.linspace(-.03, .03, len(x))] * 3)
        return fit_predict(x, y, np.array([[test]]), 1., robust=True, details=True,
                           feature_names=["policy_6m_change"], primary=self.spec,
                           policy_sources=np.array(sources, dtype="datetime64[ns]")[:, None])

    def test_carried_forward_rows_do_not_create_policy_history(self):
        dates = np.repeat(pd.date_range("2018-01-31", periods=6, freq="ME").to_numpy(), 6)
        q, info = self.policy_fit(np.repeat(np.linspace(-.2, .2, 6), 6), dates)
        self.assertEqual(info["policy_guard"]["unique_source_observations"][0], 6)
        self.assertFalse(info["supported"][0])
        np.testing.assert_allclose(info["coefficient"], 0)
        np.testing.assert_allclose(q[0], info["intercept"])

    def test_nearly_constant_observations_are_disabled_with_enough_history(self):
        dates = pd.date_range("2018-01-31", periods=36, freq="ME")
        _, info = self.policy_fit(.2383 + np.linspace(-1e-7, 1e-7, 36), dates)
        self.assertEqual(info["policy_guard"]["unique_source_observations"][0], 36)
        self.assertIn("near_constant_observations", info["policy_guard"]["disabled_reasons"][0])
        self.assertFalse(info["supported"][0])

    def test_distinct_economic_values_and_imputation_dilution_are_checked(self):
        dates = pd.date_range("2018-01-31", periods=36, freq="ME")
        _, info = self.policy_fit([0.] * 18 + [.1] * 18, dates)
        self.assertIn("insufficient_distinct_values", info["policy_guard"]["disabled_reasons"][0])
        # Enough raw observations and variation, but median imputation dilutes
        # the fitted scale below one basis point in a long sparse training fold.
        values = np.r_[np.full(500, np.nan), np.linspace(-.02, .02, 12)]
        sources = np.r_[np.full(500, np.datetime64("NaT", "ns")), dates[:12].to_numpy()]
        _, info = self.policy_fit(values, sources)
        self.assertGreater(info["policy_guard"]["observed_source_std"][0], .01)
        self.assertIn("near_constant_processed_training", info["policy_guard"]["disabled_reasons"][0])

    def test_eligible_feature_is_clipped_and_test_input_cannot_set_scale(self):
        values = np.linspace(-.3, .3, 36)
        dates = pd.date_range("2018-01-31", periods=36, freq="ME")
        first, info = self.policy_fit(values, dates, 1e6)
        second, later = self.policy_fit(values, dates, 1e12)
        self.assertTrue(info["supported"][0])
        self.assertTrue(info["input_clipped"][0])
        np.testing.assert_allclose(first, second)
        np.testing.assert_allclose(info["training_scale"], later["training_scale"])
        np.testing.assert_allclose(first[0], info["intercept"] + info["contributions"].sum(axis=0))

    def test_sources_and_policy_support_are_refit_inside_every_fold(self):
        panel = self.panel[self.panel.date <= "2020-04-30"].copy()
        calls = []
        real_support = policy_support

        def checked(x, std, names, sources, rules):
            result = real_support(x, std, names, sources, rules)
            for i, name in enumerate(names):
                if not name.startswith("policy_"):
                    continue
                ids = sources[:, i][np.isfinite(x[:, i]) & ~np.isnat(sources[:, i])]
                self.assertEqual(result["unique_source_observations"][i], len(np.unique(ids)))
            calls.append(len(x))
            return result

        with patch("research_backtest.policy_support", side_effect=checked):
            original = forecasts(panel, [], primary=self.spec)
        self.assertGreater(len(calls), len(original) * 3)
        self.assertGreater(len(set(calls)), 1)
        changed = panel.copy(deep=True)
        cutoff = original[-1]["decision_date"]
        pending = changed.exit > cutoff
        changed.loc[pending, "asset_returns"] = pd.Series([np.array([9., -9., 3.]) for _ in changed[pending].index], index=changed[pending].index)
        updated = forecasts(changed, [], primary=self.spec)
        np.testing.assert_allclose(updated[-1]["q"], original[-1]["q"])
        np.testing.assert_allclose(updated[-1]["alpha"], original[-1]["alpha"])

    def test_reserved_rows_and_after_cutoff_sources_are_rejected(self):
        future = self.panel.copy()
        future.loc[future.index[-1], "holding_month"] = pd.Timestamp("2023-01-31")
        with self.assertRaisesRegex(ValueError, "Reserved"):
            forecasts(future, [], primary=self.spec)
        late = self.panel[self.panel.date <= "2020-01-31"].copy()
        late.loc[late.index[0], "policy_6m_level__source"] = pd.Timestamp("2099-01-01")
        with self.assertRaisesRegex(ValueError, "source after"):
            forecasts(late, [], primary=self.spec)
        for feature in [c for c in self.spec["features"] if c.startswith("policy_")]:
            source = self.panel[f"{feature}__source"]
            self.assertTrue((source.isna() | (source <= self.panel.decision_date)).all())

    def test_generated_primary_recomputes_own_bl_errors_and_preserves_diagnostics(self):
        report = json.loads((ROOT / "research/outputs/research_results.json").read_text())
        all_rows = json.loads((ROOT / "research/outputs/research_forecasts.json").read_text())
        self.assertEqual(report["primary"]["key"], "corrected")
        self.assertTrue(report["primary"]["numerical_acceptance"]["passed"])
        self.assertFalse(report["primary"]["reserved_test"]["evaluated"])
        self.assertAlmostEqual(report["development"]["results"]["baseline"]["stats"]["cumulative_return"], .23987341420441188)
        self.assertAlmostEqual(report["development"]["results"]["clip_only"]["stats"]["cumulative_return"], .13324778491334377)
        rules = self.spec["preprocessing"]["policy"]
        for row in all_rows["corrected"]:
            for audit in row["audit"].values():
                for f in audit["features"]:
                    if f["feature"].startswith("policy_"):
                        eligible = (f["unique_source_observations"] >= rules["min_source_observations"]
                                    and f["distinct_resolution_bins"] >= rules["min_distinct_resolution_bins"]
                                    and f["observed_source_std"] >= rules["min_observed_std_percentage_points"]
                                    and f["processed_training_std"] >= rules["min_processed_std_percentage_points"])
                        self.assertEqual(f["enabled"], eligible)
                        if not f["enabled"]:
                            self.assertEqual(f["contribution"], 0.)
        for d in report["development"]["results"]["corrected"]["decisions"]:
            errors = [np.array(r["q"]) - r["actual"] for r in all_rows["corrected"] if r["exit"] <= d["decision_date"]]
            np.testing.assert_allclose(np.var(errors, axis=0, ddof=1), d["view_error_variance"], rtol=0, atol=1e-14)

    def test_freeze_rejects_modified_source_fingerprints(self):
        manifest = verify_freeze()
        self.assertEqual(manifest["id"], self.spec["id"])
        changed = copy.deepcopy(manifest)
        changed["files"]["src/research_backtest.py"] = "0" * 64
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "changed_freeze.json"
            path.write_text(json.dumps(changed))
            with self.assertRaisesRegex(ValueError, "code/specification changed"):
                verify_freeze(path)
        self.assertEqual(json.loads(FREEZE_PATH.read_text()), manifest)


if __name__ == "__main__":
    unittest.main()
