# Deterministic signal research

**Current primary:** [Corrected primary model v1](PRIMARY_MODEL.md), specified
in `primary_spec.json` and fingerprinted in `primary_freeze.json`. V1–V3 notes
below are historical investigations; the v4 run adds the explicitly selected
corrected model. The original 23.99% is an unstable diagnostic comparison.

The original website remains at `dist/index.html`. New experiments are at
`dist/research.html`. These are development experiments, not a replacement
for the locked model or an evaluation of 2023 onward.

Local model source:
`src/research_backtest.py` (relative to `deterministic_mvp`).

The code in `src/` imports the existing deterministic model's
release cleaning, macro features, Black–Litterman, and constrained optimizer.
The reproducible original run and raw downloads live in `deterministic_mvp/research/`.

## Rebuild

1. In deterministic_mvp, download adjusted daily SPY/IEF/LQD prices beginning
   January 2010 through January 3, 2023 from Yahoo Finance chart endpoints.
   Store as `research/raw/{spy,ief,lqd}_history.json`.
2. Download FRED graph CSVs for ICSA, BAA10Y and T10Y3M, January 2014 through
   December 2022, as `research/raw/{claims,credit,curve}.csv`.
3. Retain the Oct 26 workbook, ANFCI CSV and GPR DTA from the original project.
4. Run `python3 src/research_backtest.py` then
   `python3 -m unittest discover -s tests -v`.
5. Run the site's `scripts/build-research.mjs` with the absolute path to
   `deterministic_mvp/research/outputs` as its argument.

## Method

- Core model and three independent additions: claims, credit spread, yield curve.
- Expanding training from February 2015, at least 36 completed targets.
- Five fixed Ridge penalties tuned in chronological inner folds. Imputation and
  scaling are fit inside each training fold. No episode-specific tuning.
- At least 12 prior out-of-sample forecast errors for view uncertainty.
- Same BL settings (tau 0.05, risk aversion 2.5), starting mix (45/35/20),
  bounds (SPY 20–70, IEF 15–60, LQD 10–40), 1% grid, turnover penalty.
- Decision: 8pm New York on last trading day. Entry: following trading-day
  adjusted close. Exit: next rebalance adjusted close. Holding month is entry month.
- Trading costs: 5bp per dollar traded, based on full absolute weight changes
  from drifted pretrade weights. Cost deducted before the holding-period return.
  Initial allocations are treated as already funded, without entry funding costs.
- Daily buy-and-hold paths and daily peak-to-trough drawdown. Annualized return
  and zero-cash arithmetic Sharpe omitted for episodes shorter than 12 months.
- Passive 45/35/20, 60/40 and SPY-only references share execution/cost rules.
- COVID shock: Feb–Apr 2020 holding months. Recovery: May–Dec 2020.
  Inflation/rate shock: Jan–Dec 2022. December exits on January 3, 2023; this
  exit quote closes 2022, rather than evaluating a January 2023 strategy decision.
- Rolling 12-month windows overlap and are descriptive, not independent trials.

## Limits and differences from the original site

Longer ETF history enables the COVID experiment. Exact next-trading-close
execution, stricter target availability, fold-local imputation, and daily
drawdown differ from the earlier approximate monthly MVP. Every research
variant, including the baseline, is recomputed identically. Compare new signals
with this research baseline, not the older site's numerical results.

Claims, ANFCI and GPR use revised histories with assumed availability lags,
not a full real-time vintage archive. The policy-path workbook starts September
2019; earlier missing values use training-only medians (zero if the entire
training column is missing). No policy history is synthesized. Small samples,
limited recessions, and overlapping rolling windows cannot establish robustness.
The experiments do not automatically select a new production model.

## Forecast audit iteration (November 2026)

The settings for this exploratory iteration are recorded in `experiment_spec.json`
and its hash is embedded in the report, along with the exact model/research code
hashes. This is **not** a preregistered independent confirmation: the earlier
COVID and 2022 results had already been examined.

Priorities implemented:

- Per-asset RMSE, MAE, bias, forecast/realized ranges, and worst-error dates.
  The largest miss is decomposed into the training return mean plus feature
  contributions, with standardized inputs and observed training-row counts.
  The 20% monthly forecast flag is an inspection aid, not a forecast cap.
- Historical-mean returns are computed from completed training targets and
  passed through the same empirical-uncertainty BL pipeline. Prior-only
  portfolios omit predictive views, using the same covariance, bounds and cost
  accounting. Both wait for the same evaluation dates as the learned models.
- Fixed robustness checks retain the original as a reference: `robust` clips
  inputs to training-only 1st/99th percentiles and uses Ridge penalties
  `[1, 10, 100, 1000]`; `no_policy` removes the five policy-path fields. Neither
  is automatically selected or optimized against episode portfolio returns.
- Inner tuning folds now require each training return interval to have ended
  by its validation decision date, just as the outer forecast does. Policy
  snapshots after the last trading-day cutoff are withheld, retaining the
  source date and a withholding flag for audit. These timing corrections apply
  to all variants, so previously saved episode numbers can change.
- The primary result is the full common development history. Calendar-year
  results label partial years; the 2020-excluded summary compounds retained
  months from the continuous run without retraining/resetting holdings. Those
  disconnected intervals do not define an uninterrupted investable path.
- Monthly candidate-minus-baseline forecast, BL-return, weight and realized
  asset-contribution differences are recorded. Gross asset contributions plus
  the multiplicative cost effect reconcile exactly to the monthly net-return
  difference. They are not an attribution of compounded episode returns.

`research_forecasts.json` retains all past-only forecasts and their complete
feature diagnostics. `research_decisions.json` retains continuous portfolio
paths; `research_results.json` contains page-ready comparisons and attribution.
Regenerate the research page with
`node site/scripts/build-research.mjs "$PWD/research/outputs"`
from the model directory. The builder also refreshes
`site/research/` source snapshots, avoiding stale copies.

Units are monthly **decimal total returns** for targets and views and monthly
decimal-return covariance for BL. Feature yields/spreads remain in percentage
points and are scaled inside training folds. There is no risk-free return series
in this experiment; the views are not converted to cash-excess returns. No
annualization is applied before BL. This audit exposes that convention rather
than inventing a cash history.

ANFCI and GPR now retain source and **assumed** availability dates in the signal
export. These remain revised histories, not actual release timestamps or an
ALFRED vintage reconstruction. The reserved January 2023 onward test is still
untouched. The separate three- and six-month horizon extension is recorded in
`horizons_spec.json` and writes `outputs/horizon_results.json`; vintage collection
remains deferred. Paired
block-bootstrap inference is implemented in the v2 extension below. Existing growth/inflation × ANFCI/GPR interactions
already test conditional responses; no duplicate interaction search was added.

## Coverage check against the research review

This is an implemented first iteration, not completion of every recommendation.
The review priorities map to the repository as follows:

| Recommendation | Current coverage |
| --- | --- |
| Audit extreme forecasts and units | Implemented: per-asset errors/ranges, feature contributions, standardized inputs, observed training counts, monthly unit conventions and robust-input sensitivity. The original unstable model is retained as a diagnostic reference, not certified as stable. |
| Attribute gains and add simple model references | Implemented: monthly forecast → BL → weights → realized-return attribution, historical mean through BL, prior-only BL, and fixed 45/35/20 on common dates and cost rules. |
| Distinguish conditions from surprises | Labels and descriptions preserve the distinction. Shared-information diagnostics compare credit with ANFCI using correlations and past-only projections; they do not establish causal redundancy. Claims consensus surprises and duration-adjusted credit remain deferred. |
| Test conditional responses and horizons | Growth/inflation × ANFCI/GPR interactions already exist. The one-month allocation remains the frozen primary; a separate corrected-model development extension now evaluates three- and six-month cumulative targets with explicit overlap and non-overlap rules. |
| Strengthen episode evidence | Full eligible history, calendar years, continuous holdings and a 2020-excluded summary are implemented. Event-boundary shifts, paired block bootstrap and a leave-each-named-episode-out set are implemented in v2. Earlier stress episodes cannot be forced into the sample before its May 2019 allocation start. |
| Improve data provenance and protect the test | Assumed source/availability dates, all eight consumed data-file hashes, workbook hash, code hashes, recorded experiment settings and a pre-2023 research boundary are implemented. Actual historical release timestamps and real-time vintages are not reconstructed. The final model/evaluation criteria have not been frozen, and no reserved-period evaluation was added. |
| Quantify missing policy history | The no-policy ablation uses identical dates to the imputed-policy baseline. A separate policy model trained only on fully observed policy history is not implemented: there are only 37 complete feature rows before the research cutoff, and none of its decision dates has 36 completed complete-policy targets, even before requiring 12 prior forecast errors. |
| Decision-support diagnostics | Extreme-forecast flags, training coverage, model sensitivities and saved view-error variance are available. The page now displays historical source ages, assumed availability dates and prior forecast-error standard deviations. These are not real-time vintages or calibrated predictive confidence intervals. |

ANFCI/GPR hashes identify the exact revised files used; they do **not** cure the
vintage limitation. Similarly, an exploratory settings record is not a frozen
production specification or evidence of out-of-sample success. The original robust-input sensitivity combines clipping and stronger shrinkage.
V2 adds separate clipping-only and shrinkage-only comparisons to isolate those
changes, alongside a policy-coverage safeguard.


## V2: stability safeguards and dependence-aware evaluation

`experiment_spec.v1.json` preserves the earlier settings. The current
`experiment_spec.json` records the extension before its run and references that
previous file's SHA-256. The earlier results were already known; these remain
exploratory analyses, without automatic model selection.

- **Policy coverage safeguard:** each policy feature contributes zero until the
  current training fold contains at least 12 finite observed values. Imputed
  entries do not count. The check is repeated inside every tuning fold. Twelve
  is a fixed sensitivity threshold, not proof of sufficient economic history.
- **Isolated stability changes:** `clip_only` keeps the original Ridge grid;
  `shrink_only` keeps unclipped features. The existing combined `robust` and
  `no_policy` comparisons remain available. All share the same evaluation dates.
- **Paired circular moving-block bootstrap:** 3,000 resamples, fixed seed
  20261102, block lengths 3/6/12 months and 95% percentile intervals for the
  *mean monthly net-return difference* versus baseline. Exactly the same month
  indices are sampled for both strategies. The intervals condition on fitted
  portfolio paths, do not refit models, and are not adjusted for trying multiple
  variants. They are neither compounded-return intervals nor a formal discovery
  of statistical significance. The 44-month sample makes block-length sensitivity
  especially important.
- **Episode sensitivity:** each episode start and end independently shifts by
  -1/0/+1 month. Only complete windows inside common development coverage are
  evaluated; requests including January 2023 remain unscored. Original holdings
  and costs are retained. Separate leave-each-episode-out summaries compound
  retained months without retraining or resetting portfolios. These disconnected
  intervals are diagnostics, not tradable uninterrupted paths.
- **Credit and ANFCI:** report contemporaneous correlations and expanding
  past-only projections of credit level/change from known ANFCI level/change,
  requiring 24 earlier feature observations. Projection R² compares squared
  errors with a past-only mean of the credit feature. It measures shared
  conditions, not whether credit predicts asset returns. The existing credit
  versus original Ridge/portfolio experiment provides the incremental return
  comparison. Revised-data limitations apply to both.
- **Freshness and uncertainty:** the page shows source-observation ages and
  assumed availability dates at the last decision of the selected window, and
  each decision's earlier forecast-error standard deviations. The signal export
  also includes actual context values used, with after-cutoff policy values
  withheld. Availability is assumed; actual historical release timestamps and
  full vintages still require external data.

Release-day and 3/6-month targets, new consensus/duration-adjusted credit inputs,
real-time vintage reconstruction, and a final production freeze/test are not
implemented by this extension. The reserved historical test remains excluded.

## V3: focused forecast-stability investigation

See [STABILITY_REVIEW.md](STABILITY_REVIEW.md) for the reproduced January 2020
calculation, controlled comparison, findings and pre-test decision requirements.
The new **Forecast stability** section in Signal Research compares existing
repairs before portfolio returns. It reports per-asset MAE, RMSE, matched
historical-mean OOS R², largest absolute forecasts and all 20% warning events
on both the full 57-forecast sample and the 44 common portfolio months.
Calendar-year forecast metrics and allocation-limit frequencies are included.

The trace retains original workbook levels/differences, completed-target policy
rows, medians, raw/processed inputs, scale, distinct finite training values and
coefficients. The original forecasts and 23.99% portfolio result are preserved.
No model, signal, penalty grid or output cap is added. No final specification is
selected, and no post-2022 holding month is evaluated. Prior v2 settings are
preserved in `experiment_spec.v2.json`. All comparisons remain exploratory.
