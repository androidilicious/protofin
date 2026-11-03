# Matched model comparison

This is a separate experiment from Signal Research. It holds the information set
fixed for historical mean → OLS → Ridge → Elastic Net, then tests two isolated
Ridge extensions. The settings are recorded in `experiment_spec.json` before
this run; prior signal-research results were already known, so this remains
exploratory. No model is automatically selected for production.

## Reproduce

From `deterministic_mvp`:

```bash
python3 -m pip install -r requirements-comparison.txt
python3 src/model_comparison.py
node site/scripts/build-model-comparison.mjs "$PWD/model_comparison/outputs"
python3 -m unittest discover -s tests -v
node site/scripts/test-model-comparison.mjs
python3 -m http.server 4173 --directory site/dist
```

Open `http://localhost:4173/models.html`. The main MVP and Signal Research both
link to the Model Comparison tab. This generator writes only
`model_comparison/outputs/`; it does not replace the Signal Research artifacts.

## What is held fixed

- Core predictors: Growth surprise, Inflation surprise, ANFCI and GPR.
- Historical mean uses the exact same training target rows but ignores inputs.
- All six methods share the same eligible rows, including availability of the
  extension inputs, to avoid silently changing the comparison sample. The first
  macro-lag row is unavailable; all methods therefore start training in March
  2015 rather than February 2015. There are 56 common one-month forecasts and
  43 common portfolio holdings (June 2019–December 2022).
- Forward return targets run from the first trading close after the decision
  to the next rebalance close. A training target must finish by the decision
  cutoff. The inner validation loop enforces the same rule, with at least 24
  completed inner-training targets and 36 outer-training targets.
- All features use training-only median imputation, 1st/99th percentile clipping
  and scaling, fitted independently in every inner/outer fold. Returns are
  standardized per asset in training and converted back to decimal total
  returns afterward. Targets and predicted returns are never capped.
- No sparse policy-path fields appear in this experiment. They caused extreme
  extrapolation in earlier research and cannot supply a long observed history.
  The wider-input Ridge remains in Signal Research. The core comparison is
  conditional on the shared feature set and clipping, rather than a replacement
  of that earlier experiment.
- All learners use the same covariance estimator, BL code, bounds, grid,
  execution, cost and drift rules from `research_backtest.py`. Each learner's
  view uncertainty uses its own completed earlier forecast errors. Initial
  mix is 45/35/20 and cost is 5bp per dollar traded (full absolute weight change).

## Methods and compact tuning grids

OLS uses scikit-learn `LinearRegression`. Ridge uses `solver="svd"` with a
normalized grid `[0.01, 0.1, 1, 10]`; scikit-learn receives `alpha * n_train`
so the regularization strength is defined relative to mean squared loss.
Elastic Net uses alpha `[0.01, 0.1, 1]` and L1 ratio `[0.2, 0.8]`, separately
per asset. Its deterministic cyclic solver uses 20,000 iterations and tolerance
1e-7; a convergence warning fails the run. No grids are chosen by episode
portfolio returns. The best completed chronological validation MSE selects
parameters per asset, with fixed parameter order breaking ties. Cached fold
fits are reused only within the same estimator run and never score a validation
outcome before it has ended.

The package is pinned to scikit-learn 1.6.1 for compatibility with the existing
Python environment. Exact Python/NumPy/pandas/SciPy/scikit-learn versions, raw
input hashes, workbook hash, source hashes and specification hash accompany
the results. See the official [OLS](https://scikit-learn.org/1.6/modules/generated/sklearn.linear_model.LinearRegression.html),
[Ridge](https://scikit-learn.org/1.6/modules/generated/sklearn.linear_model.Ridge.html),
and [Elastic Net](https://scikit-learn.org/1.6/modules/generated/sklearn.linear_model.ElasticNet.html)
documentation for estimator definitions and penalty conventions.

## Focused Ridge extensions

The core set is additive, without interactions. Two extensions are separate:

- **Dynamic Ridge:** add SPY/IEF/LQD calendar-month returns already known at the
  decision close and the previous decision month's Growth/Inflation surprises.
  `lag_return_source_date` and `lag_macro_source_date` are exported. A simple
  shift of the previous forward holding return would leak information because
  that interval may not finish until after the current decision; it is not used.
- **Interaction Ridge:** add Growth surprise × ANFCI and Inflation surprise ×
  ANFCI. Those interactions exist in the wider original model; separating them
  here identifies their contribution relative to additive Ridge.

No combined lags-plus-interactions model is selected or run. A small one-lag BVAR
is optional and deferred pending a compact variable-system specification and a
matched-information comparison with Dynamic Ridge. SVAR, neural networks and a
broad search across tree models are outside this experiment.

## Evaluation

Per asset, report MAE, RMSE, forecast range, extreme-forecast counts, average
active predictor count, and:

```
OOS R² = 1 − sum((actual − model forecast)²)
             / sum((actual − expanding historical-mean forecast)²)
```

Both sums use identical dates. The historical-mean model has R² = 0; this is not
scikit-learn's `score()` or an R² against the realized test-period mean.

Headline forecast tables use common portfolio dates, after the allocator has
12 earlier completed forecast errors. `all_forecast_metrics` additionally reports
the longer common forecast-only sample. Full history is the primary comparison;
COVID shock/recovery and 2022 are diagnostic windows. Calendar years label partial
years and reuse continuous holdings. Portfolios report net total return, daily
maximum drawdown, average monthly turnover, costs and annualized metrics where
the window has at least 12 observations. Historical-mean and fixed/prior-only
portfolio references are retained.

## Limits

The data are revised histories with assumed publication lags, not real-time
vintages. Clipping reduces extrapolation but does not establish predictive
accuracy; inspect OLS, Ridge and Elastic Net errors before interpreting portfolio
returns. Comparisons are exploratory, not multiple-testing-adjusted discoveries.
No risk-free return series is supplied; views are monthly total returns.
No 2023-onward holding month is evaluated. The January 3, 2023 quote only closes
December 2022. The production model and final evaluation remain unfrozen.


## Reading the model visually

The Model Comparison tab now starts with a linked monthly decision explorer.
Choose a period, model, asset and holding month. The first selected month is the
largest absolute forecast miss in the current window; month/model/asset choices
remain linked across the charts. Previous/next and the month picker provide
keyboard access to the same decisions as the chart hit areas.

The explorer shows:

1. Raw input values, any training-quantile clipping, and optional scaling details.
2. The fitted intercept and signed per-input contributions in percentage points
   of monthly return. The terms exactly sum to the forecast at full precision.
   Contributions depend on the current fitted model; they are not causal effects.
3. The exact historical-risk prior, raw forecast and BL estimate, plus the
   standard deviation of earlier forecast errors. BL uses all three assets and
   their covariance, so no one-dimensional confidence or blend percentage is
   invented. The displayed prior includes the same tiny covariance regularizer
   used by the actual BL function.
4. The fully invested allocation, actual binding bounds, turnover and cost, then
   the observed asset return and net portfolio return, explicitly labeled as
   outcomes observed afterward.

Additional views compare monthly forecasts with realized returns, rank RMSE on
a shared zero-based scale, display per-asset OOS R², and show daily growth,
drawdowns and monthly asset weights. Models and assets keep separate color
mappings; line styles, direct values and native controls supplement color.
Charts size their axes and text from the actual container width instead of
shrinking fixed desktop viewboxes. Exact tables remain available in details.

`base_return`, `feature_contributions` and `preprocessing` are explanatory
metadata saved with each forecast. The generator retains fitted intercepts
including target-scaling reversal; contributions are scaled back to return
units. Exporting this metadata does not change forecasts, penalties, weights,
returns or the experiment specification.


### All-model cumulative return chart

The portfolio chart now defaults to the six forecasting models on one shared
cumulative-net-return axis. Each starts at 0%; the optional dollar view starts
at $100. The inspected model is drawn last with a thicker line. Colors and line
patterns remain consistent between returns and drawdowns. Legend buttons show
each model's exact ending result and toggle line visibility; at least one line
remains. Hiding lines does not rescale the axis. `Show all lines` restores the
current view. The comparison menu can include both fixed/prior-only references,
or focus on the inspected model and references. This is a presentation change;
all saved forecasts, returns, dates and trading rules remain unchanged.
