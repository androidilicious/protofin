# Forecast stability investigation · November 5, 2026

This is a controlled diagnostic comparison of the existing repairs, not a new
model search or a production selection. The full record is the `stability`
section of `outputs/research_results.json`. The interactive review is under
**Signal research → Forecast stability**.

## Reproduced failure

The January 31, 2020 decision predicts the February holding interval (entry
February 3, exit March 2), not January's already-realized return.

The six-month policy-rate change has 2 finite training values, approximately
0.2388 and 0.2378 percentage points, among 58 completed targets. The other
56 values are filled with the training median, approximately 0.2383. The
observed-only population standard deviation is 0.0005 percentage points;
the standard deviation after imputation is 0.0000928476691.

January's original workbook change is −0.2681 percentage points:

```
z = (−0.2681 − 0.2383) / 0.0000928476691 ≈ −5454.09
forecast = training target mean + sum(z_feature × fitted coefficient_feature)
```

The six-month change alone contributes about +593.47 percentage points to the
SPY forecast. All contributions plus the training target mean reconstruct
the original **+589.45% SPY forecast**. The original LQD forecast is even larger:
**+677.48%**. Targets/forecasts use monthly decimal total returns; policy levels
and differences use the workbook's percentage-point units. A consistent change
of predictor units does not fix standardized extrapolation.

The trace includes original source-sheet snapshots, completed-target policy
rows, imputation, scaling, chosen penalties, coefficients and contribution
reconciliation for all three assets. This confirms the numerical mechanism in
the supplied workbook. It does not validate the workbook against an external
policy-data provider or reconstruct historical vintages.

## Controlled comparison

All versions use 57 common forecasts (April 2018–December 2022 holding months,
including portfolio warm-up) and 44 common portfolio holdings (May 2019–December
2022). The largest forecast below is the absolute value across **all three
assets**. Flags count asset-months with absolute forecasts strictly above 20%.

| Existing version | Largest absolute monthly forecast | Flags / 171 asset-months | Net portfolio return, 44 months |
| --- | ---: | ---: | ---: |
| Original rerun, diagnostic reference | 677.48% | 3 | 23.99% |
| Require 12 finite policy training values | 42.61% | 1 | 16.99% |
| Remove policy fields | 42.61% | 1 | 17.95% |
| Clip inputs only | 6.24% | 0 | 13.32% |
| Stronger Ridge grid only | 83.81% | 2 | 17.04% |
| Clip inputs + stronger Ridge grid | 4.39% | 0 | 10.70% |
| Expanding historical mean → BL | 1.27% | 0 | 14.59% |

Coverage gating and no-policy fix the January sparse-policy failure but leave
a −42.61% SPY forecast at the June 30, 2020 decision. Its largest feature
contribution is Growth surprise × ANFCI, showing that policy coverage alone
cannot address extrapolation in the remaining inputs. Stronger shrinkage alone
also leaves extreme forecasts. Both existing clipping versions remove warning
flags over the entire observed development sample; there is no forecast cap.

On both the 57-month forecast sample and 44-month portfolio-date sample,
**every learned version has negative OOS R² for each asset against the matched
expanding historical mean**. Therefore the stable versions still do not show
better squared-error forecast skill. MAE, RMSE, all extreme events, calendar
years and allocation-bound frequency are available in the report/page.

The original 23.99% remains visible for comparison. It is not a return target
for choosing safeguards. More stable forecasts do not automatically improve
portfolio drawdown or returns. Each version retains its own completed prior
forecast errors for BL uncertainty; this is the same estimation rule, not an
identical numeric uncertainty matrix.

## Recommendation and evaluation boundary

Keep the historical mean as the primary forecast benchmark. For a numerically
stable learned sensitivity, retain the existing clipping versions; do not
present the original or a coverage-only repair as a reliable forecasting model.
The combined clipping/shrinkage version is closer to the historical mean in
squared error, but neither clipping version establishes predictive improvement.
This investigation does not promote a replacement production specification.

Before the final test, record one selected candidate and its complete rules:
inputs, coverage, imputation, clipping, scaling, tuning grid and fold timing,
target/execution timing, BL uncertainty, allocation bounds/costs, and acceptance
and reporting criteria. Define how warning flags will be treated before seeing
test outcomes. Freeze the specification and code hashes; confirm with the team
whether 2023 onward remains unexamined. If it was examined, label it accordingly
rather than claiming an untouched test. No reserved holding month is evaluated.

The remaining real-time-data limitation is separate. Revised histories and
assumed availability lags are retained. Historical vintages for supported
economic series may be collected from [ALFRED](https://fred.stlouisfed.org/docs/api/fred/alfred.html)
in a later data-provenance task.

## Reproduce

From `deterministic_mvp`, with its Python dependencies available:

```sh
python3 src/research_backtest.py
node site/scripts/build-research.mjs "$PWD/research/outputs"
python3 -m unittest discover -s tests -p 'test_research*.py' -v
node site/scripts/test-research-stability.mjs
```

`experiment_spec.v2.json` preserves the previous settings. The v3 specification
records these evaluation rules after the v2 results were already observed;
this is exploratory, not a preregistered independent confirmation. Forecasting
rules and allocations remain unchanged; this iteration adds forensic evidence
and comparisons. Model Comparison is regenerated to refresh shared-source
fingerprints, with forecasts/allocations checked against its saved run.

Validation: the research/model-comparison suites pass 41 tests, the stability
panel passes 42 cohort/asset/model combinations, and the existing Model Comparison
panel passes 216 window/model/asset combinations. All original research forecasts,
penalty choices, development decisions and portfolio metrics are unchanged.
The legacy MVP test class still expects the absent `deterministic_data1.xlsx`
fixture; the newer Oct26 workbook has a different coverage period and cannot be
silently substituted for that fixture's fixed expectations.
