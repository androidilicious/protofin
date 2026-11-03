"""Matched samples, stable estimators, target timing and historical-mean OOS R²."""
import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from model_comparison import (
    METHODS, SPEC_PATH, OUT, adjusted_prices, build_comparison_panel,
    feature_columns, prepare_fold, fit_method, comparison_forecasts, per_asset_metrics,
)


class ModelComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = json.loads(SPEC_PATH.read_text())
        cls.prices = adjusted_prices()
        cls.panel, _ = build_comparison_panel(cls.prices, cls.spec)
        cls.report = json.loads((OUT / 'model_comparison_results.json').read_text())
        cls.forecasts = json.loads((OUT / 'model_comparison_forecasts.json').read_text())

    def test_same_core_inputs_and_common_training_dates(self):
        for key in ['historical_mean', 'ols', 'ridge', 'elastic_net']:
            self.assertEqual(feature_columns(key, self.spec), self.spec['core_features'])
        expected = [(p['date'], p['training_rows'], p['last_training_exit']) for p in self.forecasts['historical_mean']]
        for key, rows in self.forecasts.items():
            self.assertEqual([(p['date'], p['training_rows'], p['last_training_exit']) for p in rows], expected)
            self.assertTrue(all(p['last_training_exit'] <= p['decision_date'] for p in rows))

    def test_lagged_returns_are_known_at_cutoff(self):
        for _, row in self.panel.iterrows():
            self.assertLessEqual(row.lag_return_source_date, row.decision_date)
            self.assertLess(row.lag_macro_source_date, row.decision_date)
            prior = self.prices[self.prices.index.to_period('M') < row.date.to_period('M')].iloc[-1]
            expected = self.prices.loc[row.decision_date] / prior - 1
            np.testing.assert_allclose(row[self.spec['lag_features'][:3]].to_numpy(float), expected.to_numpy())
        altered = self.prices.copy()
        cutoff = pd.Timestamp('2020-01-31')
        altered.loc[altered.index > cutoff] *= 50
        changed, _ = build_comparison_panel(altered, self.spec)
        columns = self.spec['lag_features']
        pd.testing.assert_frame_equal(self.panel.loc[self.panel.decision_date <= cutoff, columns], changed.loc[changed.decision_date <= cutoff, columns])

    def test_preprocessing_uses_training_only_and_does_not_clip_targets(self):
        rng = np.random.default_rng(8)
        x, y = rng.normal(size=(40,4)), rng.normal(size=(40,3))
        y[-1] = 100
        a = prepare_fold(x, y, np.full((1,4), 1e6), self.spec)
        b = prepare_fold(x, y, np.full((1,4), 1e12), self.spec)
        np.testing.assert_allclose(a['test'], b['test'])
        np.testing.assert_allclose(a['target_mean'], y.mean(axis=0))
        np.testing.assert_allclose(a['y']*a['target_scale']+a['target_mean'], y)

    def test_ols_recovers_linear_relation_and_zero_ridge_matches_ols(self):
        rng=np.random.default_rng(4)
        x=rng.normal(size=(100,4)); test=np.array([[.2,-.1,.3,.4]])
        beta=np.array([[1.,2.,3.],[-.5,.2,.4],[.1,.5,-.2],[0.,.2,.7]])
        y=x@beta+np.array([.5,2.,-.2])
        spec=copy.deepcopy(self.spec);spec['preprocessing']['quantiles']=[0,1]
        fold=prepare_fold(x,y,test,spec)
        ols,_=fit_method(fold,'ols',spec); ridge,_=fit_method(fold,'ridge',spec,0.)
        np.testing.assert_allclose(ols,(test@beta+np.array([.5,2.,-.2]))[0],atol=1e-10)
        np.testing.assert_allclose(ridge,ols,atol=1e-10)

    def test_elastic_net_can_remove_irrelevant_predictors(self):
        rng=np.random.default_rng(11);x=rng.normal(size=(200,4))
        y=np.column_stack([x[:,0],2*x[:,0],-x[:,0]])+rng.normal(0,.005,size=(200,3))
        fold=prepare_fold(x,y,x[[0]],self.spec)
        _,info=fit_method(fold,'elastic_net',self.spec,.1,.8)
        np.testing.assert_array_equal(info['nonzero'],[1,1,1])
        self.assertTrue((np.abs(info['coefficients'][:,0])>0).all())

    def test_inner_and_outer_folds_exclude_unfinished_targets(self):
        panel=self.panel.iloc[:43].copy()
        panel['growth_surprise']=np.arange(len(panel),dtype=float)
        calls=[]
        def checked(x,y,test,spec):
            training=x[:,0].astype(int);target=int(test[0,0])
            self.assertTrue((panel.iloc[training].exit<=panel.iloc[target].decision_date).all())
            calls.append(target)
            return prepare_fold(x,y,test,spec)
        for key in ['ridge','elastic_net']:
            with patch('model_comparison.prepare_fold',side_effect=checked):
                comparison_forecasts(panel,key,self.spec)
        self.assertGreater(len(calls),10)

    def test_future_targets_do_not_change_earlier_forecast_or_parameters(self):
        panel=self.panel.iloc[:44].copy()
        cutoff=panel.iloc[-1].decision_date
        changed=panel.copy(deep=True)
        index=changed.exit>cutoff
        changed.loc[index,'asset_returns']=pd.Series([np.array([9.,-9.,5.]) for _ in changed.index[index]],index=changed.index[index])
        for key in ['historical_mean','ols','ridge','elastic_net']:
            original=comparison_forecasts(panel,key,self.spec)[-1]
            updated=comparison_forecasts(changed,key,self.spec)[-1]
            np.testing.assert_allclose(original['q'],updated['q'])
            self.assertEqual(original['alpha'],updated['alpha'])
            self.assertEqual(original['l1_ratio'],updated['l1_ratio'])

    def test_oos_r2_uses_historical_forecasts_not_test_mean(self):
        actual=[np.array([v,v,v]) for v in [1.,2.,4.]]
        means=[{'date':i,'q':np.array([.5,.5,.5])} for i in range(3)]
        perfect=[{'date':i,'q':a,'actual':a,'nonzero_features':[1,1,1]} for i,a in enumerate(actual)]
        mean_rows=[{**p,'actual':actual[i],'nonzero_features':[0,0,0]} for i,p in enumerate(means)]
        for value in per_asset_metrics(perfect,means).values():self.assertAlmostEqual(value['oos_r2_vs_mean'],1.)
        for value in per_asset_metrics(mean_rows,means).values():self.assertAlmostEqual(value['oos_r2_vs_mean'],0.)
        miss=[{**p,'q':p['q']+1} for p in perfect]
        expected=1-3/sum((v-.5)**2 for v in [1.,2.,4.])
        self.assertAlmostEqual(per_asset_metrics(miss,means)['equity']['oos_r2_vs_mean'],expected)

    def test_extensions_change_only_predefined_features(self):
        self.assertEqual(feature_columns('ridge_lags',self.spec),self.spec['core_features']+self.spec['lag_features'])
        self.assertEqual(feature_columns('ridge_interactions',self.spec),self.spec['core_features']+self.spec['interaction_features'])
        self.assertNotIn('policy_6m_change',feature_columns('ridge',self.spec))
        self.assertFalse(self.report['bvar']['implemented'])

    def test_saved_portfolio_dates_costs_weights_and_metrics_reconcile(self):
        for window in self.report['windows']:
            expected=None
            for key,result in window['results'].items():
                rows=result['decisions']; dates=[r['holding_month'] for r in rows]
                if expected is None:expected=dates
                self.assertEqual(dates,expected)
                self.assertTrue(all(d<='2022-12-31' for d in dates))
                wealth=100.
                for row in rows:
                    weights=np.array(row['weights'])
                    self.assertAlmostEqual(weights.sum(),1.)
                    self.assertTrue((weights>=0).all())
                    self.assertAlmostEqual(row['cost'],row['turnover']*.0005)
                    returns=(self.prices.loc[row['exit']]/self.prices.loc[row['entry']]-1).to_numpy()
                    self.assertAlmostEqual(row['net_return'],(1-row['cost'])*(1+weights@returns)-1)
                    wealth*=1+row['net_return']
                self.assertAlmostEqual(wealth,result['path'][-1]['wealth'])
                self.assertAlmostEqual(wealth/100-1,result['portfolio']['cumulative_return'])
                if key in METHODS:
                    for metric in result['forecast'].values():self.assertEqual(metric['months'],len(rows))

    def test_data_and_code_hashes_match_saved_run(self):
        self.assertEqual(self.report['specification_sha256'],hashlib.sha256(SPEC_PATH.read_bytes()).hexdigest())
        for name,digest in self.report['code_hashes'].items():
            self.assertEqual(digest,hashlib.sha256((ROOT/'src'/name).read_bytes()).hexdigest())
        for name,digest in self.report['input_hashes'].items():
            self.assertEqual(digest,hashlib.sha256((ROOT/name).read_bytes()).hexdigest())
        self.assertEqual(self.report['environment']['scikit_learn'],'1.6.1')

    def test_visual_explanations_reconstruct_every_saved_forecast(self):
        for key, rows in self.forecasts.items():
            for row in rows:
                contribution = np.asarray(row['feature_contributions'])
                np.testing.assert_allclose(np.asarray(row['base_return']) + contribution.sum(axis=1), row['q'], atol=1e-12)
                prep = row['preprocessing']
                np.testing.assert_allclose(prep['used_input'], np.clip(prep['raw_input'], prep['clip_low'], prep['clip_high']))
                np.testing.assert_allclose(prep['standardized_input'], (np.asarray(prep['used_input'])-prep['training_mean'])/prep['training_scale'])
                self.assertEqual(contribution.shape, (3,len(row['feature_columns'])))
                if key=='historical_mean':
                    np.testing.assert_allclose(contribution, 0.)

    def test_displayed_bl_prior_and_posterior_match_exact_allocation_math(self):
        from deterministic_mvp import black_litterman_posterior
        benchmark=np.array([.45,.35,.20])
        for key, result in self.report['windows'][0]['results'].items():
            for row in result['decisions']:
                covariance=np.asarray(row['covariance'])
                if key in METHODS:
                    prior=2.5*(covariance+np.eye(3)*1e-8)@benchmark
                    np.testing.assert_allclose(row['bl_prior'], prior)
                    posterior=black_litterman_posterior(covariance,np.asarray(row['forecast']),np.asarray(row['view_error_variance']),benchmark)
                    np.testing.assert_allclose(row['posterior'],posterior)


if __name__=='__main__':
    unittest.main()
